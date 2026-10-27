#!/usr/bin/env bash
# Muestra los usuarios demo de Chatwoot y la contraseña local (solo para la demo en tu máquina).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
. ./.env
set +a
cat <<TXT
Chatwoot  http://localhost:3000
  gerencia@bordeluz-demo.test     (administrador)
  recepcion1@bordeluz-demo.test   (agente)
  recepcion2@bordeluz-demo.test   (agente)
  Contraseña: ${DEMO_PASSWORD}

PMS simulado  http://localhost:8200/admin
  Token de personal: ${STAFF_TOKEN}
TXT
