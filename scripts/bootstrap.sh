#!/usr/bin/env bash
# Crea el archivo de entorno local con secretos aleatorios si no existe y completa las claves que falten.
set -euo pipefail
cd "$(dirname "$0")/.."
target=".env"

generate() {
  # Reemplaza cada __GENERATE__ de la línea por un secreto distinto
  local line="$1"
  while [[ "$line" == *__GENERATE__* ]]; do
    line="${line/__GENERATE__/$(openssl rand -hex 24)}"
  done
  printf '%s\n' "$line"
}

if [ ! -f "$target" ]; then
  : >"$target"
  chmod 600 "$target"
  created=1
fi

added=0
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in
    ''|'#'*) continue ;;
  esac
  key="${line%%=*}"
  if ! grep -q "^${key}=" "$target"; then
    generate "$line" >>"$target"
    added=$((added + 1))
  fi
done <.env.example

# Chatwoot exige mayúscula y símbolo en las contraseñas: se corrige un entorno generado antes
if ! grep -q '^DEMO_PASSWORD=Demo-.*!$' "$target"; then
  sed -i '' -E 's/^DEMO_PASSWORD=(.*)$/DEMO_PASSWORD=Demo-\1!/' "$target"
fi

if [ "${created:-0}" = 1 ]; then
  echo "$target creado con secretos aleatorios"
else
  echo "$target existente: $added clave(s) nueva(s) agregada(s)"
fi
