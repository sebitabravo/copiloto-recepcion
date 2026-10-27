#!/usr/bin/env bash
# Crea el archivo de entorno local con secretos aleatorios si no existe.
set -euo pipefail
cd "$(dirname "$0")/.."
target=".env"
if [ -f "$target" ]; then
  # Chatwoot exige mayúscula y símbolo en las contraseñas: se corrige un entorno generado antes
  if ! grep -q '^DEMO_PASSWORD=Demo-.*!$' "$target"; then
    sed -i '' -E 's/^DEMO_PASSWORD=(.*)$/DEMO_PASSWORD=Demo-\1!/' "$target"
    echo "DEMO_PASSWORD ajustada a la política de Chatwoot"
  fi
  echo "$target ya existe, no se toca el resto"
  exit 0
fi
cp .env.example "$target"
while grep -q '__GENERATE__' "$target"; do
  secret="$(openssl rand -hex 24)"
  # sed de macOS: reemplaza solo la primera ocurrencia
  sed -i '' "1,/__GENERATE__/ s/__GENERATE__/${secret}/" "$target"
done
chmod 600 "$target"
echo "$target creado con secretos aleatorios"
