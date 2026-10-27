#!/usr/bin/env bash
# Espera a que respondan los servicios del stack (Chatwoot tarda en el primer arranque).
set -euo pipefail

wait_for() {
  local name="$1" url="$2" tries="${3:-90}"
  for _ in $(seq 1 "$tries"); do
    if curl -fsS -o /dev/null "$url"; then
      echo "OK   $name ($url)"
      return 0
    fi
    sleep 5
  done
  echo "FALLA $name ($url) no respondió a tiempo" >&2
  return 1
}

wait_for chatwoot http://localhost:3000/api 120
wait_for pms-mock http://localhost:8200/health 24
wait_for landing http://localhost:8080 24
# copiloto puede no existir aún en la primera pasada de `make up` (se recrea tras el seed)
if docker ps --format '{{.Names}}' | grep -q '^copiloto-copiloto-1$'; then
  wait_for copiloto http://localhost:8100/health 24
fi
