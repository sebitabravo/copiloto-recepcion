# Copiloto de Recepción · demo Hotel Bordeluz
COMPOSE = docker compose -f infra/docker-compose.yml --project-directory .

.PHONY: up down reset env ps logs test seed health e2e creds smoke backup

env:
	./scripts/bootstrap.sh

# Levanta todo el stack local; el primer arranque de Chatwoot puede tardar varios minutos.
up: env
	$(COMPOSE) build
	$(COMPOSE) up -d postgres redis
	$(COMPOSE) run --rm chatwoot bundle exec rails db:chatwoot_prepare
	$(COMPOSE) up -d chatwoot sidekiq pms-mock landing
	./scripts/wait-healthy.sh
	./scripts/seed-chatwoot.sh
	$(COMPOSE) up -d --force-recreate copiloto
	./scripts/wait-healthy.sh
	@echo "Listo. Landing: http://localhost:8080 · Recepción: http://localhost:3000 · Métricas: http://localhost:8100/metricas"

seed:
	./scripts/seed-chatwoot.sh

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100 copiloto pms-mock

health:
	./scripts/wait-healthy.sh

test:
	cd copiloto && uv run pytest -q
	cd pms_mock && uv run pytest -q

e2e:
	uv run --with httpx python scripts/e2e.py

# Detiene los contenedores y conserva los datos
down:
	@read -p "Esto detiene el stack (los datos se conservan). ¿Seguir? [s/N] " ok; [ "$$ok" = "s" ] && $(COMPOSE) down

# Borra los volúmenes: conversaciones, reservas simuladas y cuentas demo
reset:
	@read -p "ATENCIÓN: borra TODOS los volúmenes (conversaciones, base de Chatwoot, reservas simuladas). ¿Seguir? [s/N] " ok; \
	  [ "$$ok" = "s" ] && $(COMPOSE) down -v && rm -f .env.runtime landing/config.js

creds:
	./scripts/show-credentials.sh

# Construye las imágenes y comprueba que arrancan (lo que los tests unitarios no ven)
smoke:
	./scripts/smoke-docker.sh

# Respaldo en caliente de Chatwoot y las bases SQLite en backups/
backup:
	./scripts/backup.sh
