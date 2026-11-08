#!/usr/bin/env bash
# Demo local SIN Docker: copiloto (uv) en :8100 y la portada estática en :8080.
#
# Flujo guiado (sin IA), Hostería Demo Villarrica (ficticia) e inventario de prueba. Los datos viven en
# .demo-local/ (fuera de git). Ctrl+C detiene ambos procesos.
#
# Uso:
#   ./scripts/demo-local.sh            # conserva las solicitudes de la sesión anterior
#   ./scripts/demo-local.sh --limpio   # escenario limpio: borra solo la base de .demo-local/
#   SHIFT_OVERRIDE=closed ./scripts/demo-local.sh   # todo el servidor fuera de turno
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/.demo-local"
DB="$STATE/copiloto.sqlite"
# Windows con Git Bash trae `python`, no `python3`.
PYTHON="$(command -v python3 || command -v python)"

mkdir -p "$STATE"
if [ "${1:-}" = "--limpio" ]; then
  for file in "$DB" "$DB-wal" "$DB-shm"; do
    [ -f "$file" ] && rm -- "$file"
  done
  echo "Escenario limpio: se borraron las conversaciones y solicitudes de la demo local."
fi

# Firma de la sesión de recepción: secreto local, generado una vez y fuera del repositorio.
if [ ! -f "$STATE/panel-token" ]; then
  "$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(24))' >"$STATE/panel-token"
fi

# La portada apunta la API al copiloto local. config.js no se versiona: si ya existe, no se toca.
if [ ! -f "$ROOT/landing/config.js" ]; then
  printf 'window.COPILOTO_CONFIG = {\n  copilotoUrl: "http://localhost:8100",\n  privacyUrl: "/privacidad",\n};\n' \
    >"$ROOT/landing/config.js"
fi

trap 'kill 0' EXIT INT TERM
(
  cd "$ROOT/copiloto"
  HOTEL_DATA_PATH=../data/hotel.yaml \
  DEMO_HOTEL_DATA_PATH=../data/hosteria-demo.yaml \
  COPILOTO_DB_PATH="$DB" \
  PANEL_TOKEN="$(cat "$STATE/panel-token")" \
  LANDING_ORIGIN=http://localhost:8080 \
  AI_MODE=off \
  SHIFT_OVERRIDE="${SHIFT_OVERRIDE:-}" \
  uv run uvicorn copiloto.app:create_app --factory --host 127.0.0.1 --port 8100 --no-access-log
) &
"$PYTHON" -m http.server 8080 --bind 127.0.0.1 --directory "$ROOT/landing" >/dev/null 2>&1 &

echo "Demo local (datos de prueba):"
echo "  Vista partida:       http://localhost:8080/demo.html"
echo "  Huésped (ventana):   http://localhost:8080/demo.html?vista=huesped"
echo "  Recepción (ventana): http://localhost:8080/demo.html?vista=recepcion"
echo "Ctrl+C para detener."
wait
