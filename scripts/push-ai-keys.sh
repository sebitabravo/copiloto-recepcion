#!/usr/bin/env bash
# Sube las claves de IA del .env local al proyecto de Vercel y republica.
#
# No imprime los valores en ningún momento: los lee del archivo y los entrega por stdin a la CLI.
# Sin claves en el .env no hace nada y lo dice, así no se pisa una configuración existente.
#
#   ./scripts/push-ai-keys.sh --check   # solo dice qué encontró (seguro, no toca Vercel)
#   ./scripts/push-ai-keys.sh           # sube las claves y republica en producción
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PROJECT="${VERCEL_PROJECT:-copiloto-recepcion}"
SITE="${PUBLIC_SITE_URL:-https://copiloto-recepcion.vercel.app}"
KEYS=(LLM_API_KEY ELEVENLABS_API_KEY ELEVENLABS_VOICE_ID)
CHECK_ONLY=0
[[ "${1:-}" == "--check" ]] && CHECK_ONLY=1

command -v vercel >/dev/null || { echo "Falta la CLI de Vercel (npm i -g vercel)." >&2; exit 1; }
[[ -f .env ]] || { echo "No hay .env en $ROOT: deja ahí las claves y vuelve a correr." >&2; exit 1; }

# Lee una clave del .env sin exponerla: admite comillas y espacios alrededor del "=".
value_of() {
  local key="$1" raw value
  raw="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" .env | tail -1 || true)"
  [[ -n "$raw" ]] || return 0
  value="${raw#*=}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  value="${value%\"}"; value="${value#\"}"
  value="${value%\'}"; value="${value#\'}"
  printf '%s' "$value"
}

declare -A VALUES=()
MISSING=0
for key in "${KEYS[@]}"; do
  value="$(value_of "$key")"
  if [[ -z "$value" ]]; then
    echo "· $key: sin valor en .env"
    MISSING=$((MISSING + 1))
  else
    echo "· $key: listo (${#value} caracteres)"
    VALUES[$key]="$value"
  fi
done

if (( CHECK_ONLY )); then
  (( MISSING == 0 )) && echo "Todo listo para subir con: ./scripts/push-ai-keys.sh" \
    || echo "Faltan $MISSING claves en .env: agrégalas y vuelve a correr."
  exit 0
fi

(( MISSING == 0 )) || { echo "Faltan $MISSING claves en .env: no toqué Vercel." >&2; exit 1; }

echo "Subiendo a Vercel ($PROJECT)…"
for key in "${KEYS[@]}"; do
  for environment in production preview; do
    printf '%s' "${VALUES[$key]}" | vercel env add "$key" "$environment" --force --sensitive >/dev/null
  done
  echo "· $key cargada en producción y preview"
done

echo "Republicando…"
# Se re-despliega el último build de Git: `vercel --prod` desde la carpeta no empaqueta las funciones
# de `api/` y dejaría `/api/demo/chat` en 404.
vercel redeploy "https://${PROJECT}-git-main-sebitabravo-projects.vercel.app" --target production >/dev/null

echo "Verificando ${SITE}…"
for attempt in $(seq 1 40); do
  flags="$(curl -fsS "${SITE}/config.js" 2>/dev/null || true)"
  if grep -q 'aiChat: true' <<<"$flags" && grep -q 'voice: true' <<<"$flags"; then break; fi
  sleep 10
done
grep -q 'aiChat: true' <<<"$flags" && echo "· IA activa en la página publicada" || echo "· IA todavía apagada: revisa el redeploy"
grep -q 'voice: true' <<<"$flags" && echo "· Voz activa en la llamada" || echo "· Voz todavía apagada"

reply="$(curl -fsS -X POST "${SITE}/api/demo/chat" -H 'content-type: application/json' \
  -d '{"message":"hola, ¿tienen piscina?"}' 2>/dev/null || true)"
if grep -q '"reply"' <<<"$reply"; then
  echo "· El chat responde: $(printf '%s' "$reply" | head -c 160)"
else
  echo "· El chat no respondió: $(printf '%s' "$reply" | head -c 200)"
fi
