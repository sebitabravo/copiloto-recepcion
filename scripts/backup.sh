#!/usr/bin/env bash
# Respaldo en caliente: base de Chatwoot (pg_dump) y bases SQLite del copiloto y del PMS simulado.
# Las SQLite se copian con la API de backup de sqlite3 (consistente aunque el servicio esté escribiendo)
# y se transmiten por stdout, porque los contenedores tienen el sistema de archivos de solo lectura.
set -euo pipefail
cd "$(dirname "$0")/.."

dest="backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$dest"
chmod 700 backups "$dest"
compose=(docker compose -f infra/docker-compose.yml --project-directory .)

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
chmod 600 "$dest"/*

for db in copiloto pms; do
  python3 -I -c "
import sqlite3, sys
check = sqlite3.connect('$dest/$db.sqlite').execute('PRAGMA integrity_check').fetchone()[0]
sys.exit(0 if check == 'ok' else 'integridad fallida en $db: ' + check)
"
done
rm -f "$dest"/*-wal "$dest"/*-shm
echo "Respaldo listo en $dest (chatwoot.sql.gz, copiloto.sqlite, pms.sqlite)"
