# Copiloto de Recepción · demo Hotel Bordeluz
COMPOSE = docker compose -f infra/docker-compose.yml --project-directory .

.DEFAULT_GOAL := help
.PHONY: help up down reset env ps logs test seed health e2e creds smoke backup ai-smoke demo model piloto

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

test: ## Tests de copiloto y pms_mock
	cd copiloto && uv run pytest -q
	cd pms_mock && uv run pytest -q

e2e: ## 4 casos reales contra el stack levantado
	uv run --with httpx python scripts/e2e.py

# Detiene los contenedores y conserva los datos
down: ## Detiene el stack (conserva los datos; pide confirmación)
	@read -p "Esto detiene el stack (los datos se conservan). ¿Seguir? [s/N] " ok; [ "$$ok" = "s" ] && $(COMPOSE) down

# Borra los volúmenes: conversaciones, reservas simuladas y cuentas demo
reset: ## BORRA volúmenes y datos (pide confirmación)
	@read -p "ATENCIÓN: borra TODOS los volúmenes (conversaciones, base de Chatwoot, reservas simuladas). ¿Seguir? [s/N] " ok; \
	  [ "$$ok" = "s" ] && $(COMPOSE) down -v && rm -f .env.runtime landing/config.js

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
	python3 scripts/pilot_report.py --days $${DAYS:-14}
