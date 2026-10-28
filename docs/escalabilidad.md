# Escalabilidad y comparación con la competencia

Este documento responde dos preguntas: qué tan lejos está el prototipo de un producto que aguante
varios hoteles, y qué tiene la competencia que aquí no existe. Está escrito para decidir, no para
lucirse.

## Qué es hoy

Una instancia por hotel. Un proceso de FastAPI, una base SQLite, una cuenta de Chatwoot, un archivo
de datos del hotel y un modelo local. Levanta con `docker compose` y atiende una propiedad.

Eso no es un defecto accidental: es el modelo de negocio declarado en la Unidad 2 —instalación,
capacitación y soporte por pyme—. Pero conviene saber exactamente dónde se rompe si mañana entra el
segundo hotel.

## Los cinco límites reales

| Límite | Dónde se ve | Qué exigiría un cliente nuevo |
|---|---|---|
| Un hotel por instancia | `hotel.yaml` se carga una vez al arrancar (`app.py`) | Multi-inquilino: columna `hotel_id` en cada tabla, datos por hotel y selección por canal |
| Webhooks en proceso | `BackgroundTasks` en `app.py` | Cola durable con reintentos y visibilidad; hoy un reinicio pierde el trabajo en vuelo |
| Sin roles ni sesión | Token en la URL del panel | Login, roles (recepción, gerencia) y registro de quién confirma |
| Observabilidad mínima | Métricas de negocio, sin trazas técnicas | Identificador de petición, tiempos por etapa, alertas |
| Una inferencia a la vez | Un `llama-server` sin cola propia | Presupuesto de tokens por hotel y cola con prioridad |

Ninguno es grave para una demo ni para un piloto con un hotel. Todos son obligatorios para vender
el segundo.

## Lo que ya está bien resuelto

- **Idempotencia**: `processed_messages` evita procesar dos veces el mismo webhook.
- **Pérdida de datos**: SQLite en modo WAL, respaldo con `make backup`, purga por retención.
- **Aislamiento del modelo**: corre fuera del contenedor; el stack tiene su propio presupuesto de memoria.
- **Pruebas**: 139 casos del copiloto y 25 del PMS, más cuatro escenarios end-to-end contra el stack real.
- **Degradación**: si el modelo no responde, el flujo guiado por reglas sigue atendiendo.

## La competencia, con números

Investigado en octubre de 2026 sobre precios y capacidades públicas.

| Plataforma | Precio publicado | Fuerte en | Lo que no tiene |
|---|---|---|---|
| HiJiffy | desde €99/mes; Premium con PMS desde €319 + setup | Consola omnicanal, FAQ automáticas, 132 idiomas | No contesta llamadas; sin voz real |
| Asksuite | por cotización | Conversión de reservas directas, español y portugués | Sin operación post-llegada |
| Duve | desde US$120/mes | App de huésped, check-in online, upsell | La mensajería es un módulo del paquete |
| Akia | por cotización | Tareas de staff dentro del chat, handoff de turno | Voz solo en el plan más alto |
| Mise / HelloShift | por cotización | Handover de turno con checklist, tareas con evidencia | No son un asistente de huéspedes |

Dos cosas que ellos tienen y aquí no: **muchos canales** (Instagram, Facebook, email, OTA) y
**muchas integraciones de PMS** (100 a 250). Dos que aquí sí hay y allá no: **autohospedaje real con
modelo local** —sin costo por consulta ni datos saliendo del hotel— y **guardrails medidos** con una
batería reproducible: no inventa datos, no reserva sin el «sí» del huésped y nunca confirma solo.

## Lo que le faltaba al lado del hotel

La investigación sobre operación de recepción coincide en un punto: el problema no es responder, es
**no perder el hilo**. Las herramientas que usan los equipos de front desk giran alrededor de tres
cosas: una cola visible, tareas con dueño y hora, y un handover de turno que no dependa de la memoria
de quien se va.

De eso, el prototipo no tenía nada: el panel solo mostraba una conversación si ya sabías su
identificador. Lo agregado en esta iteración:

- **Cola de recepción** en `/panel` sin `conversation_id`: todas las conversaciones, ordenadas por
  riesgo, con el tiempo de espera, el paso del flujo y el estado de la pre-reserva.
- Umbrales de color por los mismos 3 minutos del SLA, con el tiempo en horas cuando pasa de una hora.
- Navegación entre cola y detalle, sin perder el token de la sesión.

## Roadmap en tres fases

**Fase 1 — piloto con un hotel (semanas).**
Cola de recepción (hecho), login simple para el personal, nota privada editable desde el panel y
prueba con recepción real. Sin cambios de arquitectura.

**Fase 2 — segundo hotel (meses).**
Multi-inquilino con `hotel_id`, cola durable para webhooks, roles y registro de confirmaciones.
Aquí se justifica cambiar de SQLite a PostgreSQL.

**Fase 3 — producto (año).**
Canales múltiples, conector de PMS por hotel, voz entrante si un cliente la paga, y panel de
gerencia con costo por consulta y tiempo ahorrado.

## Lo que no haría

**Voz.** Tres competidores la cobran aparte y ninguno la incluye en el plan base; agrega telefonía,
latencia y un segundo modelo. Para una pyme hotelera el WhatsApp escrito cubre la ventana de tres
minutos.

**Upsell automático.** Es la función que más diferencia a Duve y compañía, pero exige catálogo de
extras, precios y reglas comerciales que el hotel todavía no tiene digitalizadas.

**Multi-idioma completo.** El problema de origen es local. Traducir 132 idiomas antes de validar el
primero es gastar donde no duele.
