#!/usr/bin/env bash
# Demo local SIN Docker: copiloto (:8100), PMS simulado (:8200) y la portada (:8080), todo con uv/Python.
#
# Flujo guiado (sin IA), Hotel Bordeluz de la portada y PMS simulado con cupos ficticios. Los datos viven en
# .demo-local/ (fuera de git). Ctrl+C detiene los tres procesos.
#
# Uso:
#   ./scripts/demo-local.sh            # conserva las solicitudes de la sesión anterior
#   ./scripts/demo-local.sh --limpio   # escenario limpio: borra solo las bases de .demo-local/
#   SHIFT_OVERRIDE=closed ./scripts/demo-local.sh   # todo el servidor fuera de turno
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/.demo-local"
DB="$STATE/copiloto.sqlite"
PMS_DB="$STATE/pms.sqlite"
# Windows con Git Bash trae `python`, no `python3`.
PYTHON="$(command -v python3 || command -v python)"

mkdir -p "$STATE"
if [ "${1:-}" = "--limpio" ]; then
  for file in "$DB" "$DB-wal" "$DB-shm" "$PMS_DB" "$PMS_DB-wal" "$PMS_DB-shm"; do
    [ -f "$file" ] && rm -- "$file"
  done
  echo "Escenario limpio: se borraron conversaciones, solicitudes y reservas simuladas de la demo local."
fi

# Secretos locales, generados una vez y fuera del repositorio.
for name in panel-token staff-token events-token; do
  if [ ! -f "$STATE/$name" ]; then
    "$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(24))' >"$STATE/$name"
  fi
done

# La portada apunta la API al copiloto local. config.js no se versiona: si ya existe, no se toca.
if [ ! -f "$ROOT/landing/config.js" ]; then
  printf 'window.COPILOTO_CONFIG = {\n  copilotoUrl: "http://localhost:8100",\n  pmsUrl: "http://localhost:8200",\n  privacyUrl: "/privacidad",\n};\n' \
    >"$ROOT/landing/config.js"
fi

trap 'kill 0' EXIT INT TERM
(
  cd "$ROOT/pms_mock"
  HOTEL_DATA_PATH=../data/hotel.yaml \
  PMS_DB_PATH="$PMS_DB" \
  STAFF_TOKEN="$(cat "$STATE/staff-token")" \
  DEMO_MODE=1 \
  COPILOTO_EVENTS_URL=http://127.0.0.1:8100/webhooks/pms \
  COPILOTO_EVENTS_TOKEN="$(cat "$STATE/events-token")" \
  uv run uvicorn pms_mock.main:app --host 127.0.0.1 --port 8200 --no-access-log
) &
(
  cd "$ROOT/copiloto"
  HOTEL_DATA_PATH=../data/hotel.yaml \
  COPILOTO_DB_PATH="$DB" \
  PANEL_TOKEN="$(cat "$STATE/panel-token")" \
  PMS_URL=http://127.0.0.1:8200 \
  PMS_STAFF_URL=http://localhost:8200 \
  PMS_STAFF_TOKEN="$(cat "$STATE/staff-token")" \
  PMS_EVENTS_SECRET="$(cat "$STATE/events-token")" \
  LANDING_ORIGIN=http://localhost:8080 \
  AI_MODE=off \
  SHIFT_OVERRIDE="${SHIFT_OVERRIDE:-}" \
  uv run uvicorn copiloto.app:create_app --factory --host 127.0.0.1 --port 8100 --no-access-log
) &
"$PYTHON" "$ROOT/scripts/serve-landing.py" --root "$ROOT/landing" --port 8080 --upstream http://127.0.0.1:8100 &

echo "Demo local (datos de prueba):"
echo "  Portada:             http://localhost:8080"
echo "  Vista partida:       http://localhost:8080/demo"
echo "  Huésped (ventana):   http://localhost:8080/demo?vista=huesped"
echo "  Recepción (ventana): http://localhost:8080/demo?vista=recepcion"
echo "  PMS simulado:        http://localhost:8200/admin?demo=1"
echo "Ctrl+C para detener."
wait
