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

docker compose -f infra/docker-compose.yml --project-directory . exec -T \
  -e DEMO_PASSWORD="$DEMO_PASSWORD" -e WEBHOOK_SECRET="$WEBHOOK_SECRET" -e PANEL_TOKEN="$PANEL_TOKEN" \
  chatwoot bundle exec rails runner /bootstrap/seed.rb >"$raw"

grep -q '^SEED_OK' "$raw" || { echo "El seed no terminó con SEED_OK" >&2; exit 1; }

: >"$runtime"
chmod 600 "$runtime"
sed -n 's/^RUNTIME_VAR //p' "$raw" >>"$runtime"

website_token="$(sed -n 's/^CHATWOOT_WEBSITE_TOKEN=//p' "$runtime")"
cat >landing/config.js <<EOF
window.COPILOTO_CONFIG = {
  chatwootUrl: "http://localhost:3000",
  copilotoUrl: "http://localhost:8100",
  websiteToken: "${website_token}",
};
EOF
echo "Seed OK. Variables runtime escritas ($(wc -l <"$runtime" | tr -d ' ') claves)."
