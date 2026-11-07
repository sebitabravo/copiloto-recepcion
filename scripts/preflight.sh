#!/usr/bin/env bash
# Chequeo previo a la presentación: verifica el stack, levanta el modelo local si falta y lo precalienta.
# No cambia configuración ni datos; solo comprueba y calienta.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/infra/docker-compose.yml" --project-directory "$ROOT")
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

echo "1) Servicios del stack"
check "landing $LANDING" http_ok "$LANDING/"
check "copiloto $COPILOTO/health" http_ok "$COPILOTO/health"
check "PMS simulado $PMS/health" http_ok "$PMS/health"
check "Chatwoot $CHATWOOT" http_ok "$CHATWOOT/"

echo "2) Modelo local en el puerto $MODEL_PORT"
model_dead=0
if ! curl -s -o /dev/null -m 2 "http://localhost:$MODEL_PORT/v1/models" && ! command -v llama-server >/dev/null; then
  # Sin llama-server en el host (el caso normal en Windows): el modelo va en Docker, en la GPU si la hay.
  echo "  · no está arriba: levantando el modelo en Docker (scripts/demo.sh ia)"
  model_log="$(mktemp "${TMPDIR:-/tmp}/local-model.XXXXXX.log")"
  if ! "$ROOT/scripts/demo.sh" ia >"$model_log" 2>&1; then
    printf '  \033[31m✗\033[0m scripts/demo.sh ia falló · log: %s\n' "$model_log"
    model_dead=1
    fail=$((fail + 1))
  fi
elif ! curl -s -o /dev/null -m 2 "http://localhost:$MODEL_PORT/v1/models"; then
  echo "  · no está arriba: levantando scripts/local-model.sh"
  model_log="$(mktemp "${TMPDIR:-/tmp}/local-model.XXXXXX.log")"
  nohup "$ROOT/scripts/local-model.sh" >"$model_log" 2>&1 &
  model_pid=$!
  for _ in $(seq 1 $((MODEL_WAIT / 5))); do
    curl -s -o /dev/null -m 2 "http://localhost:$MODEL_PORT/v1/models" && break
    if ! kill -0 "$model_pid" 2>/dev/null; then
      wait "$model_pid"; status=$?
      printf '  \033[31m✗\033[0m scripts/local-model.sh terminó con código %s · log: %s\n' "$status" "$model_log"
      model_dead=1
      fail=$((fail + 1))
      break
    fi
    sleep 5
  done
else
  model_log="/dev/null"
fi
if [ "$model_dead" = 0 ]; then
  check "servidor del modelo responde" http_ok "http://localhost:$MODEL_PORT/v1/models"
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
