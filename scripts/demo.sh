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
  ia      Levanta el modelo local en Docker y reconecta el copiloto con IA
  ia-off  Apaga el modelo y deja el copiloto en modo guiado
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
    # nginx lee el bind-mount de infra/landing/nginx.conf al arrancar: un reinicio evita que /demo
    # dé 404 en un stack ya levantado tras un cambio de configuración.
    "${COMPOSE[@]}" restart landing
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
  ia)
    compose_ia=(docker compose -f infra/docker-compose.yml -f infra/docker-compose.ia.yml)
    # GPU NVIDIA visible para Docker: el modelo corre en ella. Si no, la variante CPU (LLM_GPU=0 la fuerza).
    if [ "${LLM_GPU:-auto}" != 0 ] && MSYS_NO_PATHCONV=1 docker run --rm --gpus all --entrypoint /app/llama-server \
        ghcr.io/ggml-org/llama.cpp:server-cuda-b12169 --list-devices 2>/dev/null | grep -q CUDA0; then
      echo "GPU NVIDIA detectada: el modelo corre en la GPU."
    else
      compose_ia+=(-f infra/docker-compose.ia-cpu.yml)
      echo "Sin GPU NVIDIA en Docker: el modelo corre en CPU (más lento)."
    fi
    compose_ia+=(--project-directory .)
    echo "Levantando el modelo local (la primera vez descarga ~2,5 GB dentro de Docker)…"
    "${compose_ia[@]}" up -d llm
    ready=0
    for _ in $(seq 1 240); do
      if curl -fsS -o /dev/null http://localhost:11434/health 2>/dev/null; then ready=1; break; fi
      sleep 5
    done
    if [ "$ready" != 1 ]; then
      echo "El modelo no respondió. Revisa: docker compose -f infra/docker-compose.yml -f infra/docker-compose.ia.yml logs llm" >&2
      exit 1
    fi
    echo "Modelo listo. Reconectando el copiloto con IA…"
    "${compose_ia[@]}" up -d --force-recreate copiloto
    ./scripts/wait-healthy.sh
    curl -s http://localhost:8100/api/demo/status; echo
    ;;
  ia-off)
    docker compose -f infra/docker-compose.yml -f infra/docker-compose.ia.yml --project-directory . stop llm >/dev/null 2>&1 || true
    "${COMPOSE[@]}" up -d --force-recreate copiloto
    ./scripts/wait-healthy.sh
    curl -s http://localhost:8100/api/demo/status; echo
    ;;
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
