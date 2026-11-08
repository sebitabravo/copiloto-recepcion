#!/usr/bin/env bash
# Respaldo en caliente: base de Chatwoot (pg_dump) y bases SQLite del copiloto y del PMS simulado.
# Las SQLite se copian con la API de backup de sqlite3 (consistente aunque el servicio esté escribiendo)
# y se transmiten por stdout, porque los contenedores tienen el sistema de archivos de solo lectura.
set -euo pipefail
cd "$(dirname "$0")/.."

dest="backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$dest"
# NTFS no soporta el modelo de permisos de Unix: si chmod falla (Windows) se continúa.
chmod 700 backups "$dest" 2>/dev/null || true
compose=(docker compose -f infra/docker-compose.yml --project-directory . --profile full)

"${compose[@]}" exec -T postgres pg_dump -U postgres --no-owner chatwoot | gzip >"$dest/chatwoot.sql.gz"

sqlite_dump() {
  local service="$1" path="$2" out="$3"
  "${compose[@]}" exec -T "$service" python -c "
import sqlite3, sys
source = sqlite3.connect('file:$path?mode=ro', uri=True)
copy = sqlite3.connect(':memory:')
source.backup(copy)
sys.stdout.buffer.write(copy.serialize())
" >"$out"
}
sqlite_dump copiloto /var/lib/copiloto/copiloto.sqlite "$dest/copiloto.sqlite"
sqlite_dump pms-mock /var/lib/pms/pms.sqlite "$dest/pms.sqlite"
# Canal de WhatsApp (opcional). La sesión vinculada de OpenWA no se respalda a propósito: es una credencial de
# la cuenta de WhatsApp y se recupera volviendo a escanear el QR (make wa-qr).
databases=(copiloto pms)
if "${compose[@]}" ps --status running --services | grep -qx wa-bridge; then
  sqlite_dump wa-bridge /var/lib/wa-bridge/bridge.sqlite "$dest/wa-bridge.sqlite"
  databases+=(wa-bridge)
fi
chmod 600 "$dest"/* 2>/dev/null || true

# Python portátil: en Windows `python3` suele ser el stub de la Microsoft Store.
if command -v python >/dev/null 2>&1 && python -c 'import sys' >/dev/null 2>&1; then
  PY=python
else
  PY=python3
fi

for db in "${databases[@]}"; do
  "$PY" -I -c "
import sqlite3, sys
check = sqlite3.connect('$dest/$db.sqlite').execute('PRAGMA integrity_check').fetchone()[0]
sys.exit(0 if check == 'ok' else 'integridad fallida en $db: ' + check)
"
done
# serialize() nunca escribe -wal/-shm: la copia es un SQLite único y autónomo, no hace falta limpiar.
echo "Respaldo listo en $dest (chatwoot.sql.gz y SQLite: ${databases[*]})"
