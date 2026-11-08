#!/usr/bin/env bash
# Demo local SIN Docker: PMS simulado (:8200), copiloto (:8100) y la portada (:8080), todo con uv/Python.
#
# Flujo guiado (sin IA), Hotel Boutique Bordeluz de la portada y PMS simulado con cupos ficticios.
# Sin Chatwoot, sin modelo y sin credenciales externas. Los datos viven en .demo-local/ (fuera de git).
#
# Uso (la entrada oficial es `make demo-local`; esto es lo mismo):
#   ./scripts/demo-local.sh            # conserva las solicitudes de la sesión anterior
#   ./scripts/demo-local.sh --limpio   # escenario limpio: borra SOLO las bases de .demo-local/
#   SHIFT_OVERRIDE=closed ./scripts/demo-local.sh   # todo el servidor fuera de turno
#   DEMO_TIMEOUT=180 ./scripts/demo-local.sh        # más plazo para que respondan los servicios
#
# Antes de arrancar comprueba que los puertos estén libres; después espera (con plazo) a que los tres
# servicios respondan y recién ahí imprime «listo». Si uno falla, dice cuál, muestra el final de su log y
# detiene solo los procesos que lanzó este script. Ctrl+C detiene la demo y conserva los datos.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$ROOT/.demo-local"
LOGS="$STATE/logs"
DB="$STATE/copiloto.sqlite"
PMS_DB="$STATE/pms.sqlite"
TIMEOUT="${DEMO_TIMEOUT:-90}"
PMS_PORT=8200
COPILOTO_PORT=8100
LANDING_PORT=8080
# Windows con Git Bash trae `python`, no `python3`.
PYTHON="$(command -v python3 || command -v python || true)"

usage() {
  sed -n '7,11p' "$0" | sed 's/^# \{0,1\}//'
}

clean=0
for arg in "$@"; do
  case "$arg" in
    --limpio) clean=1 ;;
    -h | --help) usage; exit 0 ;;
    *) echo "Opción desconocida: $arg" >&2; usage >&2; exit 2 ;;
  esac
done
case "$TIMEOUT" in
  '' | *[!0-9]*) echo "DEMO_TIMEOUT debe ser un número de segundos (recibido: $TIMEOUT)." >&2; exit 2 ;;
esac

if [ -z "$PYTHON" ]; then
  echo "Error: falta Python 3 (python3 o python en el PATH)." >&2
  exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "Error: falta uv. Instálalo con: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

# ── Puertos: si alguno está tomado no se arranca nada (ni se toca el proceso que lo usa). ──
port_busy() {
  "$PYTHON" - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
# Ocupado si algo ya responde en localhost (IPv4 o IPv6) o si no se puede escuchar en 127.0.0.1.
for family, kind, proto, _, address in socket.getaddrinfo("localhost", port, type=socket.SOCK_STREAM):
    with socket.socket(family, kind, proto) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(address) == 0:
            sys.exit(0)
with socket.socket() as listener:
    # Igual que uvicorn: SO_REUSEADDR ignora las conexiones en TIME_WAIT de un arranque anterior.
    # En Windows esa opción permite robar el puerto, así que allá se prueba sin ella.
    if sys.platform != "win32":
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind(("127.0.0.1", port))
    except OSError:
        sys.exit(0)
sys.exit(1)
PY
}

busy=""
for entry in "$LANDING_PORT:portada" "$COPILOTO_PORT:copiloto" "$PMS_PORT:PMS simulado"; do
  if port_busy "${entry%%:*}"; then
    busy="$busy  - $entry"$'\n'
  fi
done
if [ -n "$busy" ]; then
  echo "Error: estos puertos ya están en uso y la demo los necesita:" >&2
  printf '%s' "$busy" | sed 's/:/ (/; s/$/)/' >&2
  echo "¿Quedó otra demo abierta (Ctrl+C en su terminal) o el stack Docker levantado (make down)?" >&2
  echo "No se inició ningún proceso." >&2
  exit 1
fi

mkdir -p "$STATE" "$LOGS"
if [ "$clean" = 1 ]; then
  for file in "$DB" "$DB-wal" "$DB-shm" "$PMS_DB" "$PMS_DB-wal" "$PMS_DB-shm"; do
    if [ -f "$file" ]; then rm -- "$file"; fi
  done
  echo "Escenario limpio: se borraron conversaciones, solicitudes y reservas simuladas de la demo local."
elif [ -f "$DB" ]; then
  echo "Se conservan las solicitudes de la sesión anterior (.demo-local/). Para partir de cero: make demo-local LIMPIO=1"
fi

# Secretos locales, generados una vez y fuera del repositorio.
for name in panel-token staff-token events-token; do
  if [ ! -f "$STATE/$name" ]; then
    "$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(24))' >"$STATE/$name"
  fi
done

# Dependencias primero (visible y fuera del plazo de arranque): la primera vez descarga paquetes.
echo "Preparando dependencias con uv…"
(cd "$ROOT/pms_mock" && uv sync --quiet)
(cd "$ROOT/copiloto" && uv sync --quiet)

# ── Procesos: cada uno en su propio grupo, para detener exactamente lo que se lanzó aquí. ──
PMS_PID=""
COPILOTO_PID=""
LANDING_PID=""
stopped=0

stop_all() {
  [ "$stopped" = 1 ] && return
  stopped=1
  local pid
  for pid in $LANDING_PID $COPILOTO_PID $PMS_PID; do
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done
  for _ in $(seq 1 50); do
    local alive=0
    for pid in $LANDING_PID $COPILOTO_PID $PMS_PID; do
      if kill -0 -- "-$pid" 2>/dev/null || kill -0 "$pid" 2>/dev/null; then alive=1; fi
    done
    [ "$alive" = 0 ] && return
    sleep 0.1
  done
  for pid in $LANDING_PID $COPILOTO_PID $PMS_PID; do
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  done
}
trap stop_all EXIT
trap 'echo; echo "Deteniendo la demo… (los datos quedan en .demo-local/)"; exit 130' INT TERM

run_pms() {
  cd "$ROOT/pms_mock"
  HOTEL_DATA_PATH=../data/hotel.yaml \
  PMS_DB_PATH="$PMS_DB" \
  STAFF_TOKEN="$(cat "$STATE/staff-token")" \
  DEMO_MODE=1 \
  COPILOTO_EVENTS_URL="http://127.0.0.1:$COPILOTO_PORT/webhooks/pms" \
  COPILOTO_EVENTS_TOKEN="$(cat "$STATE/events-token")" \
  exec uv run --quiet uvicorn pms_mock.main:app --host 127.0.0.1 --port "$PMS_PORT" --no-access-log
}

run_copiloto() {
  cd "$ROOT/copiloto"
  HOTEL_DATA_PATH=../data/hotel.yaml \
  COPILOTO_DB_PATH="$DB" \
  PANEL_TOKEN="$(cat "$STATE/panel-token")" \
  PMS_URL="http://127.0.0.1:$PMS_PORT" \
  PMS_STAFF_URL="http://localhost:$PMS_PORT" \
  PMS_STAFF_TOKEN="$(cat "$STATE/staff-token")" \
  PMS_EVENTS_SECRET="$(cat "$STATE/events-token")" \
  LANDING_ORIGIN="http://localhost:$LANDING_PORT" \
  CHATWOOT_ENABLED=0 \
  AI_MODE=off \
  SHIFT_OVERRIDE="${SHIFT_OVERRIDE:-}" \
  exec uv run --quiet uvicorn copiloto.app:create_app --factory --host 127.0.0.1 --port "$COPILOTO_PORT" --no-access-log
}

run_landing() {
  # /config.js lo genera el servidor: un landing/config.js de un túnel o del stack Docker no se usa.
  exec "$PYTHON" "$ROOT/scripts/serve-landing.py" --root "$ROOT/landing" --port "$LANDING_PORT" \
    --upstream "http://127.0.0.1:$COPILOTO_PORT" \
    --copiloto-url "http://localhost:$COPILOTO_PORT" --pms-url "http://localhost:$PMS_PORT"
}

launch() { # nombre-de-variable función log
  set -m
  "$2" >"$3" 2>&1 &
  eval "$1=$!"
  set +m
}

launch PMS_PID run_pms "$LOGS/pms.log"
launch COPILOTO_PID run_copiloto "$LOGS/copiloto.log"
launch LANDING_PID run_landing "$LOGS/portada.log"

http_ok() {
  "$PYTHON" -c '
import sys
import urllib.request

# Sin proxy: la demo vive en esta máquina aunque el sistema tenga HTTP(S)_PROXY configurado.
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
try:
    sys.exit(0 if opener.open(sys.argv[1], timeout=2).status == 200 else 1)
except Exception:
    sys.exit(1)
' "$1"
}

alive() { kill -0 "$1" 2>/dev/null; }

fail() { # mensaje log
  echo >&2
  echo "Error: $1" >&2
  if [ -s "$2" ]; then
    echo "Últimas líneas de ${2#"$ROOT"/}:" >&2
    tail -n 15 "$2" | sed 's/^/  │ /' >&2
  fi
  echo "Se detuvieron los procesos que inició este lanzador; no se tocó nada más." >&2
  exit 1
}

# ── Espera con plazo: los tres deben responder antes de anunciar «listo». ──
echo "Esperando a que respondan los servicios (plazo: ${TIMEOUT} s)…"
deadline=$(($(date +%s) + TIMEOUT))
pms_ok=0
copiloto_ok=0
landing_ok=0
while :; do
  if [ "$pms_ok" = 0 ]; then
    alive "$PMS_PID" || fail "el PMS simulado (:$PMS_PORT) terminó al arrancar." "$LOGS/pms.log"
    if http_ok "http://127.0.0.1:$PMS_PORT/health"; then pms_ok=1; echo "  ✓ PMS simulado    http://localhost:$PMS_PORT"; fi
  fi
  if [ "$copiloto_ok" = 0 ]; then
    alive "$COPILOTO_PID" || fail "el copiloto (:$COPILOTO_PORT) terminó al arrancar." "$LOGS/copiloto.log"
    if http_ok "http://127.0.0.1:$COPILOTO_PORT/health?probe=readiness"; then
      copiloto_ok=1
      echo "  ✓ Copiloto        http://localhost:$COPILOTO_PORT"
    fi
  fi
  if [ "$landing_ok" = 0 ]; then
    alive "$LANDING_PID" || fail "la portada (:$LANDING_PORT) terminó al arrancar." "$LOGS/portada.log"
    if http_ok "http://127.0.0.1:$LANDING_PORT/demo"; then landing_ok=1; echo "  ✓ Portada         http://localhost:$LANDING_PORT"; fi
  fi
  [ "$pms_ok$copiloto_ok$landing_ok" = 111 ] && break
  if [ "$(date +%s)" -ge "$deadline" ]; then
    pending=""
    [ "$pms_ok" = 0 ] && pending="$pending PMS simulado (logs/pms.log)"
    [ "$copiloto_ok" = 0 ] && pending="$pending copiloto (logs/copiloto.log)"
    [ "$landing_ok" = 0 ] && pending="$pending portada (logs/portada.log)"
    log="$LOGS/copiloto.log"
    [ "$pms_ok" = 0 ] && log="$LOGS/pms.log"
    [ "$landing_ok" = 0 ] && [ "$copiloto_ok" = 1 ] && log="$LOGS/portada.log"
    fail "no respondieron en ${TIMEOUT} s:${pending}. Sube el plazo con DEMO_TIMEOUT=180." "$log"
  fi
  sleep 0.5
done

cat <<EOF

listo · demo local con datos de prueba
  Abre:                 http://localhost:$LANDING_PORT/demo   (huésped y recepción en una sola pantalla)
  Dos ventanas:         en /demo, «Abrir huésped/recepción en otra ventana» (comparten la corrida ?corrida=)
  Portada:              http://localhost:$LANDING_PORT
  PMS simulado:         http://localhost:$PMS_PORT/admin?demo=1
  Fuera del horario de recepción, activa «Simular en turno» en la barra de la demo.
  Logs: .demo-local/logs/ · Ctrl+C detiene la demo y conserva los datos (LIMPIO=1 los borra).
EOF

# ── Vigilancia: si un servicio se cae durante la presentación, se avisa cuál y se detiene el resto. ──
while :; do
  alive "$PMS_PID" || fail "el PMS simulado (:$PMS_PORT) se detuvo." "$LOGS/pms.log"
  alive "$COPILOTO_PID" || fail "el copiloto (:$COPILOTO_PORT) se detuvo." "$LOGS/copiloto.log"
  alive "$LANDING_PID" || fail "la portada (:$LANDING_PORT) se detuvo." "$LOGS/portada.log"
  sleep 1
done
