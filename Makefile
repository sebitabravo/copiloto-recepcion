# Copiloto de Recepción · demo Hotel Bordeluz
COMPOSE = docker compose -f infra/docker-compose.yml --project-directory .

.DEFAULT_GOAL := help
.PHONY: help up down reset env ps logs test bridge seed health e2e creds smoke backup ai-smoke demo model ui-test piloto beds24-check wa-up wa-down wa-qr wa-e2e

help: ## Muestra esta ayuda
	@awk 'BEGIN {FS = ":.*## "} /^[a-z0-9_-]+:.*## / {printf "  \033[1m%-8s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

env: ## Crea .env con secretos aleatorios si falta
	./scripts/bootstrap.sh

# Levanta todo el stack local; el primer arranque de Chatwoot puede tardar varios minutos.
up: env ## Levanta todo el stack (primer arranque: varios minutos)
	$(COMPOSE) build
	$(COMPOSE) up -d postgres redis
	$(COMPOSE) run --rm chatwoot bundle exec rails db:chatwoot_prepare
	$(COMPOSE) up -d chatwoot sidekiq pms-mock landing
	./scripts/wait-healthy.sh
	./scripts/seed-chatwoot.sh
	$(COMPOSE) up -d --force-recreate copiloto
	./scripts/wait-healthy.sh
	@echo "Listo. Landing: http://localhost:8080 · Recepción: http://localhost:3000 · Métricas: http://localhost:8100/metricas"

seed: ## Vuelve a sembrar Chatwoot (idempotente)
	./scripts/seed-chatwoot.sh

ps: ## Estado de los contenedores
	$(COMPOSE) ps

logs: ## Sigue los logs del copiloto y el PMS
	$(COMPOSE) logs -f --tail=100 copiloto pms-mock

health: ## Espera y comprueba los healthchecks
	./scripts/wait-healthy.sh

test: ## Tests de copiloto, pms_mock y los puentes (PMS y WhatsApp)
	cd copiloto && uv run pytest -q
	cd pms_mock && uv run pytest -q
	cd pms_bridge && uv run pytest -q
	cd wa_bridge && uv run pytest -q

bridge: ## Levanta el puente Beds24 en 8300 (requiere BEDS24_* configurado)
	cd pms_bridge && uv run uvicorn pms_bridge.main:app --port 8300

e2e: ## 4 casos reales contra el stack levantado
	uv run --with httpx --with tzdata python scripts/e2e.py

# Detiene los contenedores y conserva los datos
down: ## Detiene el stack (conserva los datos; pide confirmación)
	@read -p "Esto detiene el stack (los datos se conservan). ¿Seguir? [s/N] " ok || true; \
	  case "$$ok" in \
	    s) $(COMPOSE) down ;; \
	    *) echo "Cancelado: el stack sigue levantado." ;; \
	  esac

# Borra los volúmenes: conversaciones, reservas simuladas y cuentas demo
reset: ## BORRA volúmenes y datos (pide confirmación)
	@read -p "ATENCIÓN: borra TODOS los volúmenes (conversaciones, base de Chatwoot, reservas simuladas). ¿Seguir? [s/N] " ok || true; \
	  case "$$ok" in \
	    s) $(COMPOSE) down -v && rm -f .env.runtime landing/config.js ;; \
	    *) echo "Cancelado: los datos se conservan." ;; \
	  esac

creds: ## Muestra usuarios demo y contraseña locales
	./scripts/show-credentials.sh

# Construye las imágenes y comprueba que arrancan (lo que los tests unitarios no ven)
smoke: ## Construye las imágenes y comprueba que arrancan
	./scripts/smoke-docker.sh

# Respaldo en caliente de Chatwoot y las bases SQLite en backups/
backup: ## Respaldo en caliente en backups/
	./scripts/backup.sh

# Prueba en vivo de la IA (necesita LLM_API_KEY en .env; consume unos pocos centavos de la API)
ai-smoke: ## Prueba en vivo del asistente con IA
	uv run --with httpx python scripts/ai-smoke.py

demo: ## Chequeo previo a la presentación: verifica, levanta el modelo y precalienta
	./scripts/preflight.sh

model: ## Levanta el modelo local (llama.cpp) que usa el copiloto
	./scripts/local-model.sh

piloto: ## Informe del piloto: métricas contra las metas de la Unidad 2 (DAYS=14)
	uv run python scripts/pilot_report.py --days $${DAYS:-14}

beds24-check: ## Verifica credenciales y lectura de Beds24 antes de conectar el copiloto
	uv run python scripts/beds24_check.py

# Tests de la UI de la demo contra los módulos de landing (corre en CI también; Ubuntu trae Node)
ui-test: ## Tests de la UI de la demo (node --test)
	node --test scripts/test-demo-ui.mjs

# Canal de WhatsApp (OpenWA, no oficial). Requiere `make up` previo. Re-siembra para crear el inbox de WhatsApp.
wa-up: env ## Levanta el canal de WhatsApp de la demo (OpenWA + puente); luego escanea el QR
	$(COMPOSE) --profile whatsapp build wa-bridge
	$(COMPOSE) --profile whatsapp up -d openwa
	WA_BRIDGE_URL=http://wa-bridge:8400 ./scripts/seed-chatwoot.sh
	$(COMPOSE) --profile whatsapp up -d --force-recreate wa-bridge
	$(COMPOSE) up -d --force-recreate copiloto
	@echo "Siguiente paso: make wa-qr (crea la sesión y muestra dónde escanear el QR)"

wa-qr: ## Muestra cómo vincular el teléfono dedicado (QR de OpenWA)
	./scripts/wa-session.sh

wa-down: ## Detiene OpenWA y el puente (conserva la sesión vinculada)
	$(COMPOSE) --profile whatsapp stop openwa wa-bridge

wa-e2e: ## Prueba E2E del canal de WhatsApp sin teléfono (OpenWA simulado). SLA=1 agrega la prueba de 195 s
	./scripts/wa-e2e.sh $(if $(SLA),--sla,)
