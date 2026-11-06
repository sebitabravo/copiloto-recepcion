#!/usr/bin/env bash
# Corre el seed idempotente dentro de Chatwoot y vuelca tokens a .env.runtime (gitignored)
# y el token del widget a landing/config.js (gitignored).
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
# shellcheck disable=SC1091
. ./.env
set +a

runtime=".env.runtime"
raw="$(mktemp)"
trap 'rm -f "$raw"' EXIT

# MSYS_NO_PATHCONV evita que Git Bash convierta /bootstrap/seed.rb en una ruta de Windows
MSYS_NO_PATHCONV=1 docker compose -f infra/docker-compose.yml --project-directory . exec -T \
  -e DEMO_PASSWORD="$DEMO_PASSWORD" -e WEBHOOK_SECRET="$WEBHOOK_SECRET" -e PANEL_TOKEN="$PANEL_TOKEN" \
  -e WA_BRIDGE_URL="${WA_BRIDGE_URL:-}" \
  chatwoot bundle exec rails runner /bootstrap/seed.rb >"$raw"

grep -q '^SEED_OK' "$raw" || { echo "El seed no terminó con SEED_OK" >&2; exit 1; }

: >"$runtime"
# NTFS no soporta el modelo de permisos de Unix: si chmod falla (Windows) se continúa; el archivo
# ya está protegido por el filesystem del usuario.
chmod 600 "$runtime" 2>/dev/null || true
sed -n 's/^RUNTIME_VAR //p' "$raw" >>"$runtime"

website_token="$(sed -n 's/^CHATWOOT_WEBSITE_TOKEN=//p' "$runtime")"
# Las URLs públicas respetan lo configurado en .env (set -a arriba); en local quedan los localhost.
public_url="${COPILOTO_PUBLIC_URL:-http://localhost:8100}"
chatwoot_url="${CHATWOOT_PUBLIC_URL:-http://localhost:3000}"
cat >landing/config.js <<EOF
window.COPILOTO_CONFIG = {
  chatwootUrl: "${chatwoot_url}",
  copilotoUrl: "${public_url}",
  websiteToken: "${website_token}",
  privacyUrl: "${public_url}/privacidad",
};
EOF
echo "Seed OK. Variables runtime escritas ($(wc -l <"$runtime" | tr -d ' ') claves)."
