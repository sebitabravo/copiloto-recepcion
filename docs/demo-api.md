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
  "max_message_chars": 400,
  "messages_per_session": 30,
  "disclaimer": "Demo con IA de un tercero: no escribas datos personales reales."
}
```

- `mode`: `full` (la IA también crea la reserva en el PMS simulado), `assisted` (la IA no reserva: deja la
  pre-información para recepción) u `off`.
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
- `label` es un texto legible para mostrar tal cual en la línea de tiempo «cómo piensa la IA».

Errores (JSON `{"detail": "...", ...}`):

| Código | Cuándo |
|---|---|
| 400 | Cuerpo inválido o mensaje vacío o de más de 400 caracteres |
| 422 | `session_id` con formato inválido |
| 429 | Límite de IP, de sesión (30 mensajes) o global; incluye `retry_after_s` y el header `Retry-After` |
| 503 | Demo deshabilitada (`DEMO_ENABLED=0`) |

## `POST /api/demo/reset`

Petición `{"session_id": "..."}`. Borra el historial de esa sesión. Respuesta `{"status": "ok"}`.
