#!/usr/bin/env bash
# Construye las imágenes de los servicios y comprueba que arrancan y responden /health.
# Atrapa lo que los tests unitarios no ven: una imagen que no construye o que se cae al iniciar
# (en AgroVoz #270 el contenedor de producción moría al arrancar por una dependencia faltante).
set -euo pipefail
cd "$(dirname "$0")/.."

compose=(docker compose -f infra/docker-compose.yml --project-directory .)
"${compose[@]}" config --quiet

docker build -q -t smoke-copiloto ./copiloto >/dev/null
docker build -q -t smoke-pms ./pms_mock >/dev/null

cleanup() { docker rm -f smoke-copiloto smoke-pms >/dev/null 2>&1 || true; }
trap cleanup EXIT

secret="$(openssl rand -hex 24)"
docker run -d --name smoke-pms --read-only --tmpfs /tmp --cap-drop ALL \
  -e HOTEL_DATA_PATH=/app/data/hotel.yaml -e PMS_DB_PATH=/var/lib/pms/pms.sqlite -e STAFF_TOKEN="$secret" \
  -v "$PWD/data:/app/data:ro" --tmpfs /var/lib/pms:uid=10001,mode=700 smoke-pms >/dev/null
docker run -d --name smoke-copiloto --read-only --tmpfs /tmp --cap-drop ALL \
  -e COPILOTO_ENV=production -e HOTEL_DATA_PATH=/app/data/hotel.yaml \
  -e COPILOTO_DB_PATH=/var/lib/copiloto/copiloto.sqlite \
  -e WEBHOOK_SECRET="$secret" -e PMS_EVENTS_SECRET="$secret" -e PSEUDONYM_SALT="$secret" \
  -e PANEL_TOKEN="$secret" -e CHATWOOT_BOT_TOKEN="$secret" \
  -v "$PWD/data:/app/data:ro" --tmpfs /var/lib/copiloto:uid=10001,mode=700 smoke-copiloto >/dev/null

check() {
  local name="$1" url="$2"
  for _ in $(seq 1 30); do
    if docker exec "$name" python -c "import urllib.request,sys;sys.exit(0 if urllib.request.urlopen('$url').status==200 else 1)" 2>/dev/null; then
      echo "OK   $name responde $url"
      return 0
    fi
    sleep 1
  done
  echo "FALLA $name no respondió. Últimos logs:" >&2
  docker logs --tail 20 "$name" >&2
  return 1
}

check smoke-pms http://localhost:8200/health
check smoke-copiloto "http://localhost:8100/health?probe=readiness"
