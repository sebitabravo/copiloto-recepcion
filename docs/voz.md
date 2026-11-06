# Voz con ElevenLabs

La demo de voz llama a la API de ElevenLabs desde el servidor, con la clave en `.env`. Sin clave, todo funciona con la voz del navegador.

## Voz sin costo (por defecto)

Si no configuras `ELEVENLABS_API_KEY`, la demo habla con la voz del navegador (`speechSynthesis`, con preferencia por es-CL y luego latinoamericano). No cuesta nada y no sale ningún audio del servidor. Depende de las voces instaladas en el equipo: en macOS hay voces chilenas; en otros equipos puede sonar más distinto.

## Clave de API

**Clave:** crea una API key en ElevenLabs (Settings → API keys) y deja `ELEVENLABS_API_KEY=...` en tu `.env` (archivo ignorado por git) o expórtala en tu shell. La app la toma de ahí; nunca se escribe en archivos versionados.

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

**Costo orientativo:** ElevenLabs cobra créditos por carácter. Con respuestas de unos 300 caracteres, 1 000 respuestas son unos 300 000 caracteres: revisa tu plan antes de una presentación larga.

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

## Respaldo local con Piper (opcional)

Si ElevenLabs no responde o se agota su tope, la app puede responder con Piper (motor local, sin API de pago).

- Requiere instalar `piper-tts==1.2.0` (licencia MIT, verificada en PyPI) y un modelo ONNX con su configuración. Esta versión no se instala en el contenedor por defecto: su dependencia `piper-phonemize` no tiene wheel en macOS arm64. Probarla en el servidor real antes de usarla.
- Evita la versión nueva `piper-tts` 1.8.0 del repo `OHF-voice/piper1-gpl`: es **GPL-3.0-or-later**. Usarla en un repo público obliga a decisiones de licencia que no tomamos aquí.
- Modelo: `PIPER_MODEL_PATH` y `PIPER_CONFIG_PATH`. El modelo `es_MX-claude-high` tiene una model card que indica dataset y licencia Apache-2.0, según un resumen de la página; verifícala en el original antes de usarla.
- En inglés Piper no responde (su voz es solo española); el inglés queda con voz del navegador o texto.

