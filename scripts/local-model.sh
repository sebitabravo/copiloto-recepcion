#!/usr/bin/env bash
# Levanta el modelo local que usa el copiloto con un llama-server instalado en el host (compatible con OpenAI).
#
# La vía recomendada es Docker (./scripts/demo.sh ia). Este script es para correr el modelo fuera de Docker:
# el contenedor del copiloto lo alcanza por host.docker.internal.
#
#   ./scripts/local-model.sh                          # Qwen3-4B-Instruct-2507, el mismo modelo del perfil Docker
#   LLM_MODEL_HF=<repo:quant> LLM_MODEL_NAME=<alias> ./scripts/local-model.sh   # otro modelo (evalúalo antes)
set -euo pipefail

MODEL="${LLM_MODEL_HF:-unsloth/Qwen3-4B-Instruct-2507-GGUF:Q4_K_M}"
ALIAS="${LLM_MODEL_NAME:-qwen3-4b-instruct-2507}"
PORT="${LLM_PORT:-11434}"
CTX="${LLM_CTX:-8192}"

command -v llama-server >/dev/null || {
  echo "Falta llama-server: instálalo y asegúrate de que quede en el PATH (llama-server --version)." >&2
  echo "  macOS (Homebrew): brew install llama.cpp" >&2
  exit 1
}

args=(-hf "$MODEL" --host 0.0.0.0 --port "$PORT" -c "$CTX" --alias "$ALIAS" --parallel 1
  --jinja --reasoning off --cache-reuse 256 --top-k 20 --top-p 0.8 --min-p 0 --no-webui)

# Metal en macOS y CUDA con una GPU NVIDIA: todas las capas en la GPU. En CPU pura decide llama.cpp.
if [[ "$(uname -s)" == "Darwin" ]] || command -v nvidia-smi >/dev/null 2>&1; then
  args+=(-ngl 99)
fi

echo "Modelo: $ALIAS  ·  puerto: $PORT  ·  contexto: $CTX"
echo "Deja estas variables en .env:"
echo "  AI_MODE=assisted"
echo "  LLM_BASE_URL=http://host.docker.internal:$PORT/v1"
echo "  LLM_MODEL=$ALIAS"
echo "  LLM_API_KEY=local"
echo

exec llama-server "${args[@]}"
