#!/usr/bin/env bash
# Quick tunnel HTTPS gratuito hacia Chatwoot (para Telegram o WhatsApp). No instala nada en el host.
# La URL cambia en cada ejecución: ver docs/canales.md.
set -euo pipefail
exec docker run --rm --name copiloto-tunnel --network copiloto_default \
  cloudflare/cloudflared:2026.9.3 tunnel --no-autoupdate --url http://chatwoot:3000
