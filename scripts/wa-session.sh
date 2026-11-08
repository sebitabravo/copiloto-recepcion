#!/usr/bin/env bash
# Crea (si falta) y arranca la sesión de OpenWA, abre el QR y espera a que el teléfono dedicado quede vinculado.
set -euo pipefail
cd "$(dirname "$0")/.."

set -a
# shellcheck disable=SC1091
. ./.env
set +a

api="http://localhost:2785"
name="default"
curl -fs -o /dev/null "$api/api/health" || { echo "OpenWA no responde en $api. Corre: make wa-up" >&2; exit 1; }

# Python portable: en Windows `python3` suele ser el stub de la Microsoft Store (igual que en backup.sh).
if command -v python >/dev/null 2>&1 && python -c 'import sys' >/dev/null 2>&1; then
  PY=python
else
  PY=python3
fi

call() { curl -fs -H "X-API-Key: $OPENWA_API_KEY" -H "Content-Type: application/json" "$@"; }

# Imprime "<id> <status>" de la sesión con ese nombre, o nada si no existe
session_line() {
  call "$api/api/sessions" | NAME="$name" "$PY" -c \
    'import json,os,sys; n=os.environ["NAME"]; print(next((f"{s[\"id\"]} {s[\"status\"]}" for s in json.load(sys.stdin) if s.get("name")==n), ""))'
}

line="$(session_line)"
if [ -z "$line" ]; then
  call -X POST "$api/api/sessions" -d "{\"name\":\"$name\"}" >/dev/null
  line="$(session_line)"
fi
id="${line%% *}"
status="${line#* }"

if [ "$status" = "ready" ] || [ "$status" = "active" ]; then
  echo "La sesión '$name' ya está vinculada y lista."
  exit 0
fi

# Arrancar una sesión ya iniciada puede fallar: no es un error
call -X POST "$api/api/sessions/$id/start" >/dev/null 2>&1 || true

# El QR es una credencial temporal: archivo privado que se borra al terminar
qr="$(mktemp -t wa-qr).png"
trap 'rm -f "$qr"' EXIT
chmod 600 "$qr"
shown=0

echo "En el teléfono DEDICADO: WhatsApp -> Ajustes -> Dispositivos vinculados -> Vincular dispositivo."
echo "Esperando la vinculación (Ctrl+C para salir)..."
for _ in $(seq 1 120); do
  line="$(session_line)"
  status="${line#* }"
  if [ "$status" = "ready" ] || [ "$status" = "active" ]; then
    echo "Sesión lista. Escribe al número del bot desde otro teléfono."
    exit 0
  fi
  if [ "$status" = "qr_ready" ]; then
    # El QR rota solo: se reescribe el mismo archivo y se abre una única vez (Vista Previa recarga los cambios)
    if call "$api/api/sessions/$id/qr" | "$PY" -c \
      'import base64,json,sys; q=json.load(sys.stdin)["qrCode"]; sys.stdout.buffer.write(base64.b64decode(q.split(",",1)[-1]))' >"$qr" 2>/dev/null \
      && [ "$shown" = 0 ]; then
      open "$qr" 2>/dev/null || echo "Abre manualmente $api/ y escanea el QR de la sesión '$name'."
      shown=1
    fi
  fi
  echo "estado: $status"
  sleep 15
done
echo "La sesión no quedó lista a tiempo." >&2
exit 1
