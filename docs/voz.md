# Voz con ElevenLabs

Dos usos distintos, con la misma cuenta:

1. **Agentes de desarrollo** (Claude Code, Codex, OpenCode) usan el servidor MCP oficial para probar voces y generar audios de ejemplo mientras se desarrolla.
2. **La app** (demo de voz) llama a la API de ElevenLabs por su cuenta, desde el servidor, con la clave en `.env`. No depende del MCP.

## Servidor MCP para los agentes

Los tres agentes lanzan lo mismo, `scripts/elevenlabs-mcp.sh`, que fija la versión del paquete (`elevenlabs-mcp==0.12.2`, publicado por ElevenLabs) y acota los archivos de entrada y salida a `.voice-assets/` (ignorada por git).

| Agente | Archivo | Notas |
|---|---|---|
| Claude Code | `.mcp.json` + `.claude/settings.json` | Pide aprobación la primera vez que abres el proyecto |
| Codex | `.codex/config.toml` | Solo se carga en proyectos de confianza |
| OpenCode | `opencode.json` | |

**Clave:** crea una API key en ElevenLabs (Settings → API keys) y deja `ELEVENLABS_API_KEY=...` en tu `.env` (archivo ignorado por git) o expórtala en tu shell. El script la toma de ahí; nunca se escribe en archivos versionados.

**Herramientas bloqueadas a propósito** en los tres agentes: `make_outbound_call` (llama a teléfonos reales), `create_agent`, `add_knowledge_base_to_agent`, `simulate_conversation`, `voice_clone`, `create_voice_from_preview` y `list_phone_numbers`. Las demás, como `text_to_speech`, `search_voices` y `check_subscription`, gastan créditos de tu plan: revisa `check_subscription` antes de generar mucho.

**Actualizar la versión:** cambia `VERSION` en `scripts/elevenlabs-mcp.sh` tras revisar el paquete en PyPI.

**Probar sin gastar créditos:** `check_subscription` y `list_models` no generan audio.
