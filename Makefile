# Copiloto de Recepción · demo Hotel Bordeluz
COMPOSE = docker compose -f infra/docker-compose.yml --project-directory .
# Chatwoot, Postgres, Redis y Sidekiq solo existen con este perfil: la demo no los necesita.
COMPOSE_FULL = $(COMPOSE) --profile full

.DEFAULT_GOAL := help
.PHONY: help up up-full down reset env ps logs test lint seed health e2e creds smoke backup ai-smoke demo ui-test piloto config static-demo

help: ## Muestra esta ayuda
	@awk 'BEGIN {FS = ":.*## "} /^[a-z0-9_-]+:.*## / {printf "  \033[1m%-8s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

env: ## Crea .env con secretos aleatorios si falta
	./scripts/bootstrap.sh

# Demo liviana: landing + copiloto + PMS simulado. Sin Chatwoot no hay bandeja real ni widget,
# y el aviso de «canal no disponible» aparece solo. La IA usa DeepSeek con LLM_API_KEY.
up: env ## Levanta la demo liviana (landing, copiloto y PMS)
	$(COMPOSE) build copiloto pms-mock
	$(COMPOSE) up -d pms-mock landing copiloto
	./scripts/wait-healthy.sh
	$(COMPOSE) restart landing
	@echo "Demo: http://localhost:8080/demo · API: http://localhost:8100 · PMS: http://localhost:8200"

# Stack completo con Chatwoot (bandeja real, widget y WhatsApp). Primer arranque: varios minutos.
up-full: env ## Levanta todo el stack, incluido Chatwoot (primer arranque: varios minutos)
	$(COMPOSE_FULL) build
	$(COMPOSE_FULL) up -d postgres redis
	$(COMPOSE_FULL) run --rm chatwoot bundle exec rails db:chatwoot_prepare
	$(COMPOSE_FULL) up -d chatwoot sidekiq pms-mock landing
	./scripts/wait-healthy.sh
	./scripts/seed-chatwoot.sh
	$(COMPOSE_FULL) up -d --force-recreate copiloto
	./scripts/wait-healthy.sh
	# nginx lee el bind-mount de infra/landing/nginx.conf al arrancar: un reinicio evita que /demo
	# dé 404 en un stack ya levantado tras un cambio de configuración.
	$(COMPOSE_FULL) restart landing
	@echo "Listo. Landing: http://localhost:8080 · Recepción: http://localhost:3000 · Métricas: http://localhost:8100/metricas"

static-demo: ## Construye dist/ estático para portfolio (sin backend; Vercel/Netlify)
	./scripts/build-static-demo.sh

config: ## Regenera landing/config.js sin Chatwoot (modo demo o túnel)
	./scripts/landing-config.sh

seed: ## Vuelve a sembrar Chatwoot (idempotente; requiere --profile full)
	./scripts/seed-chatwoot.sh

ps: ## Estado de los contenedores
	$(COMPOSE_FULL) ps

logs: ## Sigue los logs del copiloto y el PMS
	$(COMPOSE) logs -f --tail=100 copiloto pms-mock

health: ## Espera y comprueba los healthchecks
	./scripts/wait-healthy.sh

test: ## Tests de copiloto y pms_mock
	cd copiloto && uv run pytest -q
	cd pms_mock && uv run pytest -q

lint: ## Lint de Python igual que CI (ruff con versión fijada)
	uvx ruff@0.17.3 check copiloto pms_mock scripts

e2e: ## 4 casos reales contra el stack levantado
	uv run --with httpx --with tzdata python scripts/e2e.py

# Detiene los contenedores y conserva los datos
down: ## Detiene el stack (conserva los datos; pide confirmación)
	@if ! read -p "Esto detiene el stack (los datos se conservan). ¿Seguir? [s/N] " ok; then \
	  echo "Error: confirmación requerida y la entrada está cerrada; el stack sigue levantado." >&2; \
	  exit 1; \
	fi; \
	case "$$ok" in \
	  s) $(COMPOSE_FULL) down ;; \
	  *) echo "Cancelado: el stack sigue levantado." ;; \
	esac

# Borra los volúmenes: conversaciones, reservas simuladas y cuentas demo
reset: ## BORRA volúmenes y datos (pide confirmación)
	@if ! read -p "ATENCIÓN: borra TODOS los volúmenes (conversaciones, base de Chatwoot, reservas simuladas). ¿Seguir? [s/N] " ok; then \
	  echo "Error: confirmación requerida y la entrada está cerrada; los datos se conservan." >&2; \
	  exit 1; \
	fi; \
	case "$$ok" in \
	  s) $(COMPOSE_FULL) down -v && rm -f .env.runtime landing/config.js ;; \
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

piloto: ## Informe del piloto: métricas contra las metas de la Unidad 2 (DAYS=14)
	uv run python scripts/pilot_report.py --days $${DAYS:-14}

# Tests de la UI de la demo contra los módulos de landing (corre en CI también; Ubuntu trae Node)
ui-test: ## Tests de la UI de la demo (node --test)
	node --test scripts/test-demo-ui.mjs

