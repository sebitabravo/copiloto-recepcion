# API de la demo

La página `/demo` conversa con el copiloto por esta API, sin pasar por Chatwoot. Base: `http://localhost:8100`
(configurable en `landing/config.js` como `copilotoUrl`, o la misma origen detrás de nginx). Solo se aceptan
peticiones desde el origen de la landing (`LANDING_ORIGIN`, por defecto `http://localhost:8080`).

Por defecto la demo corre el **flujo guiado** (`flow.Copiloto`, el mismo motor del canal de Chatwoot) con el
mismo hotel y el mismo PMS simulado que la portada (`data/hotel.yaml`, `pms_mock`). El resumen de la consulta
incluye una lectura preliminar del PMS con su hora. El motor escribe por `DemoChannel`, que guarda todo en la
transcripción aislada de la demo: hay una sola fuente de verdad para el hilo y la solicitud.
Con `DEMO_AI=1` y un modelo configurado, el turno lo responde el asistente con IA (sección final).

## Huésped

### `POST /api/demo/chat`

```json
{"session_id": "<16-64 [A-Za-z0-9-]>", "message": "<1-400>",
 "client_message_id": "<8-64 [A-Za-z0-9-], opcional>", "shift": "open | closed (opcional)"}
```

- `client_message_id`: llave de idempotencia. Si llega repetida, el turno **no** se vuelve a ejecutar: la
  respuesta trae el hilo completo con `"duplicate": true`. El cliente reintenta siempre con la misma llave.
- `shift`: escenario de prueba de la sesión (`open` en turno, `closed` fuera de turno). Sin él manda la hora de
  Chile y `SHIFT_START`/`SHIFT_END` (o `SHIFT_OVERRIDE` para todo el servidor).
- Mientras la solicitud está abierta en recepción, el mensaje le llega a ella y el asistente no contesta
  (`"mode": "human"`).

Respuesta 200 (además de `reply`, `mode`, `events`, `quick_replies` y `usage` de siempre):

```json
{
  "conversation_id": -1234567,
  "messages": [{"id": 7, "role": "assistant", "body": "Solicitud enviada a recepción. Te responderán por aquí.\n\nN.º BDL-024 · La lectbilidad por verificar: …",
                "created_at": 1794122324.4, "options": null, "author": null, "kind": null}],
  "request": {"code": "BDL-024", "status": "pendiente", "label": "Enviada a recepción · te responderán por aquí",
              "assignee": null, "in_shift": true, "open": true},
  "handled_by": "recepcion",
  "duplicate": false
}
```

- `messages`: solo lo nuevo de este turno (incluido el mensaje del huésped). Roles visibles: `guest`,
  `assistant`, `staff`. Las notas internas (`note`) nunca llegan al huésped.
- `options` de un mensaje del asistente son botones sugeridos (también en `quick_replies`).

### `GET /api/demo/conversation?session_id=…&after=<id>`

El hilo del huésped (solo mensajes con id mayor que `after`), su solicitud y quién lo atiende. Sin
conversación: `{"conversation_id": null, "step": null, "messages": [], "request": null, "handled_by":
"asistente", "quick_replies": []}`.

### `GET /api/demo/status`

Agrega `engine` (`guided` | `ai`), `hotel` (`name`, `channel_label`), `menu` (atajos), `shift` (`start`, `end`,
`timezone`, `in_shift`, `override`, `next_opening`) y `privacy_url` (`/privacidad`; vacío en la versión estática, que no publica el aviso).

## Recepción (sesión firmada)

`POST /api/demo/session` con `{"name": "Sofía"}` (opcional; letras, hasta 30) abre la sesión de demostración en
una cookie HttpOnly. Esa sesión **solo** ve y escribe solicitudes de la demo; el token del personal real
(`X-Panel-Token`) solo ve la operación y no puede responder desde aquí (se responde en Chatwoot).

| Método y ruta | Qué hace |
|---|---|
| `GET /api/panel/requests?selected=<id>` | Bandeja ordenada (pendientes con más espera primero) y, en la misma lectura, el detalle de `selected`. |
| `GET /api/panel/requests/{id}` | Detalle: datos, `messages` (con notas internas), `events`, `faq` (latencias), `measurement`, `actions`. |
| `POST /api/panel/requests/{id}/take` | Asigna a quien llama: **Pendiente de recepción → En atención**. No reinicia el reloj. Otra persona: 409. |
| `POST /api/panel/requests/{id}/reply` | `{"body": "…", "kind": "answer"\|"ack", "client_id": "…"}`. `answer` deja **Respondida** y, si es la primera, detiene el reloj (`human_first_reply`). `ack` se envía pero no cuenta. Sin tomarla: 409. Con `client_id` repetido: `"duplicate": true`, sin duplicar. |
| `POST /api/panel/requests/{id}/inventory` | `{"simulate_down": false}`. Lee el **PMS simulado**: origen, hora y las 4 opciones más económicas (`more` cuenta el resto), preliminar. PMS caído o `simulate_down`: `ok: false` y nota «cupo desconocido». |
| `POST /api/panel/requests/{id}/close` | **Cerrada**: el hilo vuelve al asistente; una consulta nueva crea otra solicitud. |

Estados: atención `pendiente`, `en_atencion`, `respondida`, `cerrada`; reserva `pendiente_confirmacion` (y
`confirmada` solo cuando una persona confirma en el PMS real del canal operativo). Son conceptos separados.

`measurement` de una solicitud: `state` (`en_curso`, `cumplida`, `vencida`, `fuera_de_turno`), `elapsed_s` desde
`commercial_at` (el ingreso de la consulta comercial, hora del servidor) y `target_s` (180).

---

# Modo con IA (`DEMO_AI=1`)

Pública y limitada por IP, por sesión y globalmente para acotar el costo de la IA. Todo es ficticio: la reserva
se crea en el PMS simulado y se rotula como demostración. Un traspaso de la IA crea la misma solicitud que el
flujo guiado.

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
