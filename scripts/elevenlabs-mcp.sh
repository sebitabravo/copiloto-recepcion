#!/usr/bin/env bash
# Servidor MCP oficial de ElevenLabs para los agentes de desarrollo (Claude Code, Codex, OpenCode).
# Los tres lo lanzan igual (ver .mcp.json, .codex/config.toml y opencode.json), así la versión fijada y las
# protecciones viven en un solo lugar. No lo usa la app: el copiloto llama a la API de ElevenLabs por su cuenta.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="0.12.2"

# La clave sale del entorno o, si falta, de ELEVENLABS_API_KEY en .env o .env.local (el CLI de ElevenLabs la deja ahí).
# Nunca se escribe en archivos versionados.
for envfile in .env .env.local; do
  if [ -z "${ELEVENLABS_API_KEY:-}" ] && [ -f "$envfile" ]; then
    ELEVENLABS_API_KEY="$(sed -n 's/^ELEVENLABS_API_KEY=//p' "$envfile" | head -n 1 | tr -d '"' | tr -d "'")"
  fi
done
if [ -z "${ELEVENLABS_API_KEY:-}" ]; then
  echo "Falta ELEVENLABS_API_KEY: expórtala en tu shell o agrégala a .env o .env.local (ver docs/voz.md)." >&2
  exit 1
fi
export ELEVENLABS_API_KEY

# Los audios generados y los archivos de entrada quedan acotados a esta carpeta (ignorada por git)
export ELEVENLABS_MCP_BASE_PATH="${ELEVENLABS_MCP_BASE_PATH:-$PWD/.voice-assets}"
export ELEVENLABS_MCP_OUTPUT_MODE="${ELEVENLABS_MCP_OUTPUT_MODE:-files}"
mkdir -p "$ELEVENLABS_MCP_BASE_PATH"

exec uvx "elevenlabs-mcp@${VERSION}"
