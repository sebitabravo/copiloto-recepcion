#!/usr/bin/env bash
# Genera landing/config.js sin Chatwoot (modo demo liviano y presentación por túnel).
#
# El seed de Chatwoot ya escribe este archivo cuando hay bandeja real. Este script cubre el caso
# contrario: presentar /demo sin Chatwoot, con un único origen público.
#
# Uso:
#   ./scripts/landing-config.sh                          # local: API en http://localhost:8100
#   COPILOTO_PUBLIC_URL=https://mi-demo.trycloudflare.com ./scripts/landing-config.sh
#
# Con COPILOTO_PUBLIC_URL igual al origen de la portada, las llamadas a /api viajan por nginx
# (infra/landing/nginx.conf) y la cookie de sesión del panel sigue siendo same-site.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "$ROOT/.env" ] && set -a && . "$ROOT/.env" && set +a

public_url="${COPILOTO_PUBLIC_URL:-http://localhost:8100}"
chatwoot_url="${CHATWOOT_PUBLIC_URL:-http://localhost:3000}"
pms_url="${PMS_PUBLIC_URL:-http://localhost:8200}"
website_token="${CHATWOOT_WEBSITE_TOKEN:-}"

# Nunca se pisa un token existente con vacío: config.js no se versiona y perderlo rompe el widget.
if [ -z "$website_token" ] && [ -f "$ROOT/landing/config.js" ]; then
  website_token="$(grep -o 'websiteToken: "[^"]*"' "$ROOT/landing/config.js" | head -1 | cut -d'"' -f2)"
fi

cat >"$ROOT/landing/config.js" <<EOF
window.COPILOTO_CONFIG = {
  chatwootUrl: "${chatwoot_url}",
  copilotoUrl: "${public_url}",
  pmsUrl: "${pms_url}",
  websiteToken: "${website_token}",
  privacyUrl: "/privacidad",
};
EOF

chmod 600 "$ROOT/landing/config.js" 2>/dev/null || true
echo "config.js escrito · copiloto: ${public_url} · chatwoot: ${chatwoot_url}"
if [ -z "$website_token" ]; then
  echo "Sin token de Chatwoot: el botón «Escribir a recepción» mostrará el aviso de canal no disponible." >&2
fi
