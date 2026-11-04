# Voz con ElevenLabs

Dos usos distintos, con la misma cuenta:

1. **Agentes de desarrollo** (Claude Code, Codex, OpenCode) usan el servidor MCP oficial para probar voces y generar audios de ejemplo mientras se desarrolla.
2. **La app** (demo de voz) llama a la API de ElevenLabs por su cuenta, desde el servidor, con la clave en `.env`. No depende del MCP.

## Voz sin costo (por defecto)

Si no configuras `ELEVENLABS_API_KEY`, la demo habla con la voz del navegador (`speechSynthesis`, con preferencia por es-CL y luego latinoamericano). No cuesta nada y no sale ningún audio del servidor. Depende de las voces instaladas en el equipo: en macOS hay voces chilenas; en otros equipos puede sonar más distinto.

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

## Demo de voz en el navegador

Una tarjeta nueva en la landing (aparece solo si la voz está configurada) permite hablar con el asistente: el navegador reconoce tu voz (Web Speech API, `es-CL`), el servidor consulta al mismo asistente con IA y devuelve la respuesta con la voz de ElevenLabs. **No es una llamada de WhatsApp** y no hay interrupción en pleno habla: se toca para hablar, se espera la respuesta y se vuelve a tocar.

**Activarla**

1. En tu cuenta de ElevenLabs elige una voz en español (idealmente latinoamericana) y copia su ID. Si es de la Voice Library, agrégala antes a tu cuenta.
2. En `.env`: `ELEVENLABS_API_KEY=...`, `ELEVENLABS_VOICE_ID=...` (español) y, si quieres inglés, `ELEVENLABS_VOICE_ID_EN=...`. El modelo por defecto es `eleven_flash_v2_5` (baja latencia, 32 idiomas); se cambia con `ELEVENLABS_MODEL`.
3. `make up` y abre la landing. Sin clave o sin voz, la tarjeta no se muestra y todo sigue en texto.

**Cómo está acotado**

- **Siempre avisa que es una IA.** El saludo es una constante del servidor (no pasa por el modelo): "Hola, soy el asistente virtual del hotel...". La voz es natural, no pretende ser una persona.
- **Nunca reserva por voz.** El reconocimiento puede errar nombres y fechas: por voz el asistente corre siempre en modo asistido, aunque `AI_MODE` sea `full`. Recepción confirma.
- **Solo sintetiza lo que responde el asistente**, nunca texto enviado por el navegador, así nadie puede gastar tus créditos con texto propio.
- **Respuestas cortas para el oído:** máximo 3 frases, sin listas ni enlaces (se reemplazan por "te lo envío por escrito"), tope de `450` caracteres por respuesta, de `VOICE_CHARS_PER_HOUR` (20 000) por hora y de `VOICE_CHARS_PER_MONTH` (30 000) por mes. El plan Starter incluye 40 000 caracteres al mes: el tope mensual queda bajo ese límite.
- **Degrada, no falla:** si ElevenLabs responde 401, 402, 429 o 5xx, o se acaba el tope, el huésped ve el texto y la tarjeta avisa "sin audio por ahora".
- **Privacidad:** el navegador envía el audio al servicio de reconocimiento (en Chrome, Google) y el texto de las respuestas va a ElevenLabs. No se guarda audio. `/privacidad` lo declara cuando la voz está activa.

**Costo orientativo:** ElevenLabs cobra créditos por carácter. Con respuestas de unos 300 caracteres, 1 000 respuestas son unos 300 000 caracteres: revisa tu plan antes de una presentación larga (`check_subscription` en el MCP).

**Pendiente de validar con tu cuenta:** calidad y acento de la voz elegida, el micrófono en tu navegador y que el ID de voz funcione por API.

## Voces candidatas (español chileno)

La biblioteca compartida de ElevenLabs tiene más de 30 voces con acento `chilean` (filtro `GET /v1/shared-voices?accent=chilean`). Son **candidatas**: no las he escuchado en audio. Escúchalas en la biblioteca antes de elegir.

| Voz | ID | Género / edad | Uso declarado |
|---|---|---|---|
| Marcela - Chilean Sales & Customer Care | `PeRxbnxvwcESkQcDM8Fi` | F / media | conversacional, atención al cliente |
| Javiera | `uQKt669VHGzAA4LAJAaT` | F / joven | conversacional |
| Paulina - Warm | `nU2Od41FnF7WAvt16wiO` | F / joven | conversacional, cálida |
| Silvana - Warm | `PFIHlfMr2oOjR5RKVg2N` | F / media | informativa |
| Cristóbal | `IhY4M972n9BRInNffBsN` | M / joven | conversacional |
| Joaquín | `HqDjrw2JtdcxsDBOK5ZW` | M / joven | conversacional |
| Alejandro - Neutral studio accent | `m3IrTXgclGG0hR8ORocn` | M / media | informativa, neutra |

**Qué puede y qué no puede hacer una voz:**

- La biblioteca etiqueta el acento como `chilean`. **No hay etiqueta de Temuco, Araucanía ni campo.** Ninguna voz reproduce el habla rural de la zona por sí sola.
- Lo que sí cambia la forma de hablar es el texto: frases cortas, palabras de uso común, fechas y precios dichos en palabras. Eso lo hace el prompt (`MODO VOZ` en `ai/prompts.py`).
- Para entender a hablantes rurales, el reconocimiento (`es-CL` en el navegador) es la parte más débil. No he medido su precisión con hablantes de la zona. Hay que probarlo con personas reales antes de prometerlo.
- **Entrenar la voz con grabaciones de la zona** (clonación) exige consentimiento de cada persona y verificación. No lo hago sin eso.

**Inglés:** usa una voz en inglés para `ELEVENLABS_VOICE_ID_EN`. Una voz chilena hablando inglés suena con acento. Si no la pones, el inglés usa la misma voz española.

**Pendiente:** no he verificado qué modelos aceptan diccionarios de pronunciación (para Temuco, Pucón, Traiguén, Molco). La API lo permite (`POST /v1/pronunciation-dictionaries/add-from-rules`), pero no lo he creado.
