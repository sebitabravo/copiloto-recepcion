#!/usr/bin/env bash
# Levanta el modelo local que usa el copiloto (llama.cpp, compatible con OpenAI).
#
# El modelo corre en el host, no dentro de Docker: el contenedor lo alcanza por
# host.docker.internal. Así el límite de memoria del stack no incluye la inferencia.
#
#   ./scripts/local-model.sh                     # 7B por defecto (dev en Mac)
#   LLM_MODEL_HF=Qwen/Qwen2.5-3B-Instruct-GGUF:Q4_K_M \
#     LLM_MODEL_NAME=qwen2.5-3b-instruct ./scripts/local-model.sh   # equipo con poca RAM
set -euo pipefail

MODEL="${LLM_MODEL_HF:-Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M}"
ALIAS="${LLM_MODEL_NAME:-qwen2.5-7b-instruct}"
PORT="${LLM_PORT:-11434}"
CTX="${LLM_CTX:-8192}"

command -v llama-server >/dev/null || {
  echo "Falta llama-server. Instálalo con: brew install llama.cpp" >&2
  exit 1
}

args=(-hf "$MODEL" --host 0.0.0.0 --port "$PORT" -c "$CTX" --alias "$ALIAS" --no-webui)

# Metal en macOS; en CPU pura se deja que llama.cpp decida.
if [[ "$(uname -s)" == "Darwin" ]]; then
  args+=(-ngl 99)
fi

echo "Modelo: $ALIAS  ·  puerto: $PORT  ·  contexto: $CTX"
echo "Deja estas variables en .env:"
echo "  AI_MODE=full"
echo "  LLM_BASE_URL=http://host.docker.internal:$PORT/v1"
echo "  LLM_MODEL=$ALIAS"
echo "  LLM_API_KEY=local"
echo

exec llama-server "${args[@]}"
