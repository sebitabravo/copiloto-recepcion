#!/usr/bin/env bash
# Atajo sin `make` (Windows/Git Bash). Mismos comandos que el Makefile, sin depender de make.
# Uso: ./scripts/demo.sh {up|seed|status|creds|test|e2e|smoke|down|reset}
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f infra/docker-compose.yml --project-directory .)
cmd="${1:-help}"

usage() {
  cat <<'TXT'
Uso: ./scripts/demo.sh <comando>

  up      Levanta el stack completo (primer arranque: varios minutos)
  seed    Vuelve a sembrar Chatwoot (idempotente)
  status  Estado de los contenedores
  creds   Usuarios demo y token del PMS
  test    Tests de copiloto, pms_mock, pms_bridge y wa_bridge
  e2e     4 casos reales contra el stack levantado
  smoke   Construye las imágenes y comprueba que arrancan
  down    Detiene el stack (conserva los datos)
  reset   BORRA los volúmenes y los archivos generados
TXT
}

confirm() {
  local prompt="$1" answer
  if ! read -r -p "$prompt [s/N] " answer; then
    echo "Sin entrada: no se hace nada." >&2
    exit 1
  fi
  case "$answer" in
    s|S|si|sí|y|Y) return 0 ;;
    *) echo "Cancelado."; exit 0 ;;
  esac
}

case "$cmd" in
  up)
    ./scripts/bootstrap.sh
    "${COMPOSE[@]}" build
    "${COMPOSE[@]}" up -d postgres redis
    "${COMPOSE[@]}" run --rm -T chatwoot bundle exec rails db:chatwoot_prepare
    "${COMPOSE[@]}" up -d chatwoot sidekiq pms-mock landing
    ./scripts/wait-healthy.sh
    ./scripts/seed-chatwoot.sh
    "${COMPOSE[@]}" up -d --force-recreate copiloto
    ./scripts/wait-healthy.sh
    echo "Listo. Portada: http://localhost:8080 · Demo: http://localhost:8080/demo · Recepción: http://localhost:3000"
    ;;
  seed) ./scripts/seed-chatwoot.sh ;;
  status) "${COMPOSE[@]}" ps ;;
  creds) ./scripts/show-credentials.sh ;;
  test)
    for service in copiloto pms_mock pms_bridge wa_bridge; do
      echo "== $service"
      (cd "$service" && uv run pytest -q)
    done
    ;;
  e2e) uv run --with httpx --with tzdata python scripts/e2e.py ;;
  smoke) ./scripts/smoke-docker.sh ;;
  down)
    confirm "Esto detiene el stack (los datos se conservan). ¿Seguir?"
    "${COMPOSE[@]}" down
    ;;
  reset)
    confirm "ATENCIÓN: borra TODOS los volúmenes y los archivos generados. ¿Seguir?"
    "${COMPOSE[@]}" down -v
    rm -f .env.runtime landing/config.js
    ;;
  help|--help|-h|*) usage ;;
esac
