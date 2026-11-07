# API de la demo con IA

La landing conversa con el copiloto por esta API, sin pasar por Chatwoot. Es pública y está limitada por IP,
por sesión y globalmente para acotar el costo de la IA. Base: `http://localhost:8100` (configurable en
`landing/config.js` como `copilotoUrl`). Solo se aceptan peticiones desde el origen de la landing
(`LANDING_ORIGIN`, por defecto `http://localhost:8080`).

Todo es ficticio: la reserva se crea en el PMS simulado y se rotula como demostración.

## `GET /api/demo/status`

```json
{
  "ai_enabled": true,
  "mode": "full",
  "model": "deepseek-flash",
  "autonomous_booking": true,
  "sandbox": true,
  "max_message_chars": 400,
  "messages_per_session": 30,
  "disclaimer": "Demo con IA de un tercero: no escribas datos personales reales."
}
```

- `mode`: configuración solicitada: `full`, `assisted` u `off`. No implica permiso efectivo de escritura.
- `autonomous_booking`: permiso efectivo para crear reservas. Puede ser `false` incluso con `mode=full`.
  La interfaz usa este campo, no solo `ai_enabled`, para habilitar el guion de disponibilidad y la confirmación.
- `sandbox`: indica si la configuración del PMS está autorizada como entorno simulado de la demo pública.
  El servidor aplica la restricción; modificar la interfaz no concede permisos.
- `ai_enabled` es `false` si falta la API key o el modo es `off`. La demo sigue funcionando con el flujo guiado
  (sin IA) y las respuestas llegan con `"mode": "guided"`.

## `POST /api/demo/chat`

Petición: `{"session_id": "<16 a 64 caracteres [A-Za-z0-9-]>", "message": "<1 a 400 caracteres>"}`.
El cliente genera el `session_id` (por ejemplo un UUID) y lo guarda en `sessionStorage`.

Respuesta 200:

```json
{
  "reply": "Estamos en el sector Molco...",
  "mode": "ai",
  "events": [
    {"type": "tool_call", "name": "check_availability", "label": "Consultando disponibilidad en el PMS",
     "arguments": {"checkin": "2027-03-15", "checkout": "2027-03-18", "adults": 2, "children": 1},
     "summary": "5 tipos de habitación disponibles", "ms": 412, "ok": true},
    {"type": "booking_proposal", "guest_name": "Huésped Ficticio", "room_name": "Doble con Jacuzzi",
     "room_code": "doble_con_jacuzzi", "checkin": "2027-03-15", "checkout": "2027-03-18",
     "nights": 3, "adults": 2, "children": 1, "total_clp": 240000, "simulated": true},
    {"type": "booking_created", "booking_id": 3, "room_name": "Doble con Jacuzzi", "checkin": "2027-03-15",
     "checkout": "2027-03-18", "nights": 3, "adults": 2, "children": 1, "total_clp": 240000, "simulated": true},
    {"type": "handoff", "reason": "El huésped pidió hablar con una persona", "simulated": true},
    {"type": "fallback", "reason": "ia_no_disponible"}
  ],
  "quick_replies": ["¿Tienen piscina?", "Quiero reservar", "¿Cómo llego?"],
  "usage": {"messages_left": 27, "llm_ms": 1380, "tokens": 912}
}
```

- `events` puede venir vacío. Los `tool_call` van en el orden en que la IA los usó. `tokens` puede ser `null`.
- `quick_replies`: hasta 4 sugerencias para mostrar como botones.
- Los eventos anteriores ilustran formatos, no una secuencia que deba suceder en un solo turno.
  `booking_proposal` muestra los datos autoritativos del servidor en el chat principal, aunque la traza esté
  cerrada. Incluye nombre ficticio, nombre y código de habitación, fechas, noches, ocupación, total y simulación.
- Solo después de mostrar la propuesta se ofrece el botón **Sí, confirmo la reserva**. El clic envía ese
  texto como un nuevo turno de `/api/demo/chat`; no hay envío automático. El servidor valida por separado
  permisos, coincidencia de la propuesta, vigencia, disponibilidad y duplicados. La interfaz no autoriza al servidor.
  Enviar otro mensaje o reiniciar invalida el botón anterior; si cambian los datos, solicita otra propuesta.
- `booking_created` es el comprobante posterior a una creación efectiva en el PMS simulado, no la propuesta.
- La traza opcional se llama **Acciones del asistente**: muestra operaciones, no razonamiento interno.
  El detalle técnico limita los argumentos a campos conocidos y escalares; no muestra credenciales.
- `handoff` y `handoff_to_human` en el simulador son demostraciones: no notifican a recepción. El widget
  separado de Chatwoot es el canal conectado, sin transferencia automática del historial del simulador.
- El guion de disponibilidad envía solo intención de consulta, fechas y ocupación; no selecciona una habitación,
  no inventa el nombre del huésped y no confirma. En modo sin permiso de reserva queda deshabilitado.

Errores (JSON `{"detail": "...", ...}`):

| Código | Cuándo |
|---|---|
| 400 | Cuerpo inválido o mensaje vacío o de más de 400 caracteres |
| 422 | `session_id` con formato inválido |
| 429 | Límite de IP, de sesión (30 mensajes) o global; incluye `retry_after_s` y el header `Retry-After` |
| 503 | Demo deshabilitada (`DEMO_ENABLED=0`) |

## `POST /api/demo/reset`

Petición `{"session_id": "..."}`. Borra el historial de esa sesión. Respuesta `{"status": "ok"}`.
No elimina reservas del PMS ni conversaciones de Chatwoot. El navegador inicia después un identificador nuevo.

## `POST /api/demo/session`

Crea la sesión firmada del panel sin credenciales en el navegador: es lo que usa la pestaña Recepción de la
consola con el **Modo demo** encendido. El cuerpo se ignora (tope de 4 KB).

Respuesta 204, sin cuerpo: la sesión viaja solo en una cookie `HttpOnly` (`SameSite=Lax`, `Secure` con
HTTPS). Nunca devuelve el token ni ningún secreto.

| Código | Cuándo |
|---|---|
| 204 | Sesión demo creada (`DEMO_ENABLED=1`, el valor por defecto) |
| 403 | Demo apagada (`DEMO_ENABLED=0`); no deja cookie |
| 413 | Cuerpo de más de 4 KB |

## `GET /api/demo/session`

```json
{"demo": true, "name": "Recepción (demo)"}
```

La página pregunta si el modo demo está disponible y quién es la sesión, sin secretos: `demo` refleja
`DEMO_ENABLED` y `name` es el nombre de la sesión del panel de esta cookie, o `null` si no hay sesión.

## `POST /api/demo/voice`

Mismo cuerpo y mismos límites que `POST /api/demo/chat` (`session_id` y `message`); comparten sesión,
cupo de mensajes y límites por IP con el chat de texto. A la respuesta del turno le agrega la síntesis:

```json
{
  "reply": "Estamos en el sector Molco...",
  "mode": "ai",
  "spoken": "Estamos en el sector Molco...",
  "spoken_language": "es",
  "audio_b64": "<base64>",
  "audio_format": "mp3",
  "voice_error": null
}
```

- Se sintetiza solo la respuesta del asistente (`spoken`), nunca texto enviado por el navegador.
- `audio_b64` y `audio_format` pueden ser `null` con `voice_error`: sin proveedor configurado, presupuesto
  de voz agotado (`tope_de_voz`) o falla del proveedor (`voz_no_disponible`). El texto siempre llega: la voz
  nunca impide que el huésped lea la respuesta.
- `audio_format` es `mp3` (ElevenLabs) o `wav` (Piper local), según el proveedor que respondió.
- `spoken_language` se deduce del mensaje del huésped (`es` o `en`).
- La voz no crea reservas autónomas.

## Canales y comprobaciones

- El simulador del navegador usa esta API: no es WhatsApp y no crea conversaciones en Chatwoot.
- El widget carga el SDK de Chatwoot solo al pulsar su botón; necesita su propia configuración y servicios.
- La voz usa su API independiente y no crea reservas autónomas. Su aviso de privacidad explica el
  reconocimiento del navegador y la síntesis de ElevenLabs; no se guarda audio en el prototipo.
- `/health?probe=readiness` comprueba proceso/SQLite, no todas las integraciones.
- `/metricas/data.json?days=7` muestra actividad realmente registrada de la demo, no métricas de huéspedes reales.
- El saludo y los números del hero son ilustrativos, no mediciones ni promesas de disponibilidad.

Para preparar y recorrer cada canal, consulta el [flujo del proyecto](workflow.md).
