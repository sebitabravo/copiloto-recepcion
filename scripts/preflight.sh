#!/usr/bin/env bash
# Chequeo previo a la presentación: verifica el stack, levanta el modelo local si falta y lo precalienta.
# No cambia configuración ni datos; solo comprueba y calienta.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/infra/docker-compose.yml" --project-directory "$ROOT" --profile full)
COPILOTO="${COPILOTO_URL:-http://localhost:8100}"
LANDING="${LANDING_URL:-http://localhost:8080}"
PMS="${PMS_URL:-http://localhost:8200}"
CHATWOOT="${CHATWOOT_URL:-http://localhost:3000}"
MODEL_PORT="${LLM_PORT:-11434}"
MODEL_WAIT="${MODEL_WAIT_S:-240}"

ok=0
fail=0

check() { # nombre, comando...
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    printf '  \033[32m✓\033[0m %s\n' "$name"; ok=$((ok + 1))
  else
    printf '  \033[31m✗\033[0m %s\n' "$name"; fail=$((fail + 1))
  fi
}

http_ok() { [ "$(curl -s -o /dev/null -w '%{http_code}' -m 5 "$1")" = "200" ]; }

running() { docker ps --format '{{.Names}}' | grep -qx "copiloto-$1-1"; }

echo "1) Servicios del stack"
check "landing $LANDING" http_ok "$LANDING/"
check "copiloto $COPILOTO/health" http_ok "$COPILOTO/health"
check "PMS simulado $PMS/health" http_ok "$PMS/health"
# La demo liviana no incluye Chatwoot: se comprueba solo cuando forma parte del stack.
if running chatwoot; then
  check "Chatwoot $CHATWOOT" http_ok "$CHATWOOT/"
else
  echo "  · Chatwoot no está en este stack (modo demo): se omite"
fi


echo "3) Copiloto con IA"
status=$(curl -s -m 5 "$COPILOTO/api/demo/status")
case "$status" in
  *'"ai_enabled":true'*) printf '  \033[32m✓\033[0m IA activa · %s\n' "$(printf '%s' "$status" | sed -n 's/.*"model":"\([^"]*\)".*/\1/p')"; ok=$((ok + 1)) ;;
  *) printf '  \033[31m✗\033[0m IA desactivada (revisa AI_MODE y LLM_API_KEY en .env)\n'; fail=$((fail + 1)) ;;
esac

echo "4) Precalentado (la primera respuesta carga el modelo en memoria)"
sid="preflight-$(date +%s)"
started=$(date +%s)
reply=$(curl -s -m 200 -X POST "$COPILOTO/api/demo/chat" -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$sid\",\"message\":\"Hola, ¿dónde están ubicados?\"}" \
  | sed -n 's/.*"reply": *"\([^"]*\)".*/\1/p')
elapsed=$(( $(date +%s) - started ))
if [ -n "$reply" ]; then
  printf '  \033[32m✓\033[0m respondió en %s s\n' "$elapsed"
  printf '    «%s…»\n' "$(printf '%s' "$reply" | cut -c1-120)"
  ok=$((ok + 1))
else
  printf '  \033[31m✗\033[0m no hubo respuesta del asistente\n'; fail=$((fail + 1))
fi

echo
if [ "$fail" -eq 0 ]; then
  printf '\033[32mTodo listo para presentar\033[0m (%s comprobaciones)\n' "$ok"
  echo "La primera respuesta de la demo ya debería ser rápida: el modelo quedó cargado."
  exit 0
fi
printf '\033[31m%s comprobación(es) fallaron\033[0m · %s en verde\n' "$fail" "$ok"
echo "Revisa: make ps · docker compose logs copiloto · log del modelo en ${model_log:-/dev/null}"
exit 1
