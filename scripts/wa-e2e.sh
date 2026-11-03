#!/usr/bin/env bash
# Prueba E2E del canal de WhatsApp SIN teléfono: reemplaza OpenWA por uno simulado y recorre el flujo real
# (puente + Chatwoot + copiloto). Uso: scripts/wa-e2e.sh [--sla]   (--sla agrega la prueba de 195 s)
set -euo pipefail
cd "$(dirname "$0")/.."

dc() { docker compose -f infra/docker-compose.yml --project-directory . --profile whatsapp "$@"; }

dc ps --status running --services | grep -qx wa-bridge || { echo "Corre antes: make wa-up" >&2; exit 1; }

# Nunca se pisa una sesión real vinculada: el OpenWA real se detiene unos minutos y vuelve a arrancar
if dc ps --status running --services | grep -qx openwa; then
  ready="$(dc exec -T wa-bridge python - <<'PY'
import os, httpx
r = httpx.get(os.environ["OPENWA_API_URL"] + "/api/sessions", headers={"X-API-Key": os.environ["OPENWA_API_KEY"]})
print(sum(1 for s in r.json() if s.get("status") in ("ready", "active")))
PY
)"
  if [ "${ready:-0}" != "0" ] && [ "${WA_E2E_FORCE:-0}" != "1" ]; then
    echo "OpenWA tiene una sesión vinculada. La prueba la interrumpiría unos minutos; repite con WA_E2E_FORCE=1." >&2
    exit 1
  fi
fi

secret="$(dc exec -T wa-bridge printenv OPENWA_WEBHOOK_SECRET)"
apikey="$(dc exec -T wa-bridge printenv OPENWA_API_KEY)"
container="$(dc ps -q wa-bridge)"
network="$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' "$container")"
image="$(docker inspect -f '{{.Config.Image}}' "$container")"

cleanup() {
  docker rm -f wa-e2e-fake-openwa >/dev/null 2>&1 || true
  dc start openwa >/dev/null 2>&1 || true
  dc restart wa-bridge >/dev/null 2>&1 || true
  dc up -d --force-recreate copiloto >/dev/null 2>&1 || true
}
trap cleanup EXIT

dc stop openwa >/dev/null
docker run -d --rm --name wa-e2e-fake-openwa --network "$network" --network-alias openwa \
  -e OPENWA_WEBHOOK_SECRET="$secret" -e OPENWA_API_KEY="$apikey" -v "$PWD/wa_bridge/e2e:/e2e:ro" \
  --read-only --user 10003 "$image" python /e2e/fake_openwa.py >/dev/null

for _ in $(seq 1 20); do
  dc exec -T wa-bridge python -c "import urllib.request;urllib.request.urlopen('http://openwa:2785/api/health')" \
    >/dev/null 2>&1 && break
  sleep 1
done

# El puente cachea la sesión: se reinicia para que descubra la simulada
dc restart wa-bridge >/dev/null
# La prueba es determinista y no gasta saldo del modelo: el copiloto corre con la IA apagada y se restaura al final
AI_MODE=off dc up -d --force-recreate copiloto >/dev/null
for _ in $(seq 1 30); do
  dc exec -T wa-bridge python -c "import urllib.request;urllib.request.urlopen('http://copiloto:8100/health')" \
    >/dev/null 2>&1 && break
  sleep 2
done
sleep 3

dc exec -T wa-bridge python - "$@" <wa_bridge/e2e/scenario.py
