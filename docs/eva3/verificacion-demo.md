# Verificación de la demo · EVA 3 (D01–D10)

Fecha de la verificación: 8-nov-2026. Rama `refactor/ux-logic-cleanup`. Alojamiento: **Hostería Demo
Villarrica** (ficticio). Todos los datos de esta verificación son de prueba.

**Criterio central:** un huésped crea una consulta válida, recepción la toma con todo su contexto y una
respuesta escrita por recepción llega al hilo original, con estados, persistencia y mediciones coherentes.
**Resultado: cumple** en el arranque local con flujo guiado (detalle abajo). Lo no verificado está marcado.

Tipos de evidencia: **[código]** lectura de código · **[auto]** prueba automatizada · **[UI]** recorrido real
en navegador (Chromium con Playwright, ventanas de escritorio 1440 px y teléfono iPhone 13) · **[HTTP]**
llamadas a las rutas locales.

## 1. Primer punto de falla (antes de los cambios)

Arranque: copiloto con `uv run uvicorn` en `:8100`, `AI_MODE=off` (Docker sin daemon en el entorno).
Caso canónico por `POST /api/demo/chat` **[HTTP]**:

1. «¿Dónde queda la hostería?» → respuesta de ubicación (datos del hotel real del dataset, no ficticio).
2. «Quiero consultar del 20 al 22 de noviembre para 2 adultos» → **falla**: «No tengo ese dato publicado.
   Para confirmarlo, escribe a recepción: +56 9… o comercial@…» (contacto real del hotel).
3. «Hablar con recepción» → misma respuesta: **no deriva**. `GET /api/panel/queue` muestra la conversación en
   `step: ai`, sin reloj ni solicitud.

Causa: `/api/demo/chat` sin IA usaba `guided.guided_reply` (solo FAQ y ubicación), no el motor guiado
`flow.Copiloto` que sí captura fechas y deriva. La demo y el canal de Chatwoot eran dos lógicas distintas.

## 2. Matriz antes / después

| ID | Antes | Después | Evidencia (después) |
|---|---|---|---|
| **D01** Arranque reproducible | Parcial: `make up` exige Docker; sin daemon no hay ruta documentada | **Cumple** sin Docker; Docker **no verificable** aquí | [UI] `./scripts/demo-local.sh --limpio` levanta `:8100` y `:8080`; `/health` ok; `demo.html` 200. `docker compose … config -q` válido. `make up` no se ejecutó (sin daemon). |
| **D02** Ubicación, FAQ, «Hablar con recepción» | Parcial: ubicación sí; FAQ de otro hotel; «Hablar con recepción» no deriva | **Cumple** | [auto] `test_location_and_faq_are_answered_before_asking_for_stay_data`, `test_talk_to_reception_works_without_dates_and_pending_fields_are_explicit`. [UI] atajos visibles; respuesta «Cerca de la costanera de Villarrica». |
| **D03** Fechas invertidas y corrección | Falta: no capturaba fechas | **Cumple** | [auto] `test_inverted_dates_get_a_clear_error_and_the_guest_does_not_repeat_the_adults`, `test_guest_can_correct_the_summary_before_sending`. [UI] «22 al 20 de noviembre · 2 adultos» → error; «20–22 nov» → solo pide niños. |
| **D04** Solicitud canónica localizable | Falta: sin solicitud ni ID | **Cumple** | [auto] `test_canonical_case_end_to_end`. [UI] VLL-001 con 20–22 nov, 2 adultos, 0 niños, canal, motivo, ingreso y espera. Fila persistida en SQLite (`requests`). |
| **D05** Tomar, responder, recargar | Parcial: respuesta sin responsable ni estados | **Cumple** | [auto] mismo test + `test_the_bot_stays_silent_while_reception_owns_the_case`. [UI] Tomar → En atención (Sofía); respuesta → Respondida; huésped ve «Sofía · Recepción»; reserva «Pendiente de confirmación»; recarga muestra lo mismo. |
| **D06** Reintentos sin duplicar | Falta: sin llave de idempotencia | **Cumple** | [auto] `test_a_retried_guest_message_is_processed_once`, `test_a_retried_staff_reply_is_sent_once`. [UI] se cortó la respuesta de red tras procesar: «Reintentar» dejó 1 mensaje y 1 solicitud. |
| **D07** Fuera de turno | Falta en la demo | **Cumple** | [auto] `test_off_shift_request_is_saved_with_the_next_opening_and_kept_out_of_the_target`. [UI] con la hora real (≈04:50 en Chile): «…te responderá por aquí desde las 08:00 del domingo 8 de noviembre»; bandeja marca «Fuera de turno»; sin reloj de 180 s. |
| **D08** Eventos y cálculo | Parcial: el reloj partía al derivar; demo sin eventos por hilo | **Cumple** | [auto] `test_the_clock_starts_when_the_commercial_query_enters_and_an_ack_does_not_stop_it`, `test_a_missed_target_is_recorded_as_a_breach_in_the_demo_thread`, `test_faq_latency_is_reported_per_question`, `test_sla_starts_when_the_commercial_query_entered_not_at_handoff`. [UI] «Medición de esta solicitud» lista los eventos con su desfase. |
| **D09** Móvil, escritorio, otra sesión | Parcial | **Cumple** | [UI] iPhone 13 y 1440/1280 px sin desbordes; otra sesión de huésped no ve nada ajeno; la vista `?vista=huesped` nunca llamó a `/api/panel/*` ni abrió sesión de recepción. [auto] `test_guest_sessions_are_isolated`, `test_demo_isolation.py`. |
| **D10** PMS simulado (fase 2, opcional) | Parcial: PMS simulado fuera del recorrido de la demo | **Cumple** con inventario de prueba | [auto] `test_inventory_unknown_dates_or_outage_never_report_availability`. [UI] lectura con origen y hora, «preliminar»; fechas sin dato o «Simular caída» → «cupo desconocido», el caso queda en recepción. El servicio `pms_mock` no participa en `/demo`. |

Versión estática (portfolio): [auto] `scripts/test-static-demo.mjs` y [UI] caso canónico en dos pestañas de
`dist/` con **cero** peticiones `/api` a la red.

### No verificado en este entorno

- `make up` / `make up-full` (Docker sin daemon) y la bandeja real de **Chatwoot**.
- Modo con IA (`DEMO_AI=1`): sin `LLM_API_KEY`. Sus pruebas con modelo guionado siguen en verde.
- Voz y micrófono: la nueva `/demo` no expone la llamada; los endpoints `/api/demo/voice*` siguen con sus pruebas.
- Escritura en un PMS real (fase 3): fuera de alcance por diseño.

## 3. Cambios y su motivo

| Cambio | Motivo |
|---|---|
| `copiloto/demo_channel.py`: canal con la interfaz de Chatwoot que escribe en la transcripción de la demo | Una sola fuente de verdad: la demo usa **el mismo motor guiado** que el canal real. |
| Tabla `requests` (`events.py`, `store.py`) con estado de atención y de reserva por separado | Solicitud vinculada al hilo, con ID (VLL-NNN), responsable y estados persistentes. |
| `/api/panel/requests…` (listar, tomar, responder, cerrar, inventario) | Bandeja con la acción principal según el estado; solo sesiones de demo escriben en la demo. |
| Llaves de idempotencia (`client_message_id`, `client_id`) | D06: un reintento no duplica. |
| Reloj desde `commercial_at` (ingreso de la consulta comercial); acuse ≠ respuesta; `sla_breached` | D08 según la especificación de la EVA 3. |
| `FlowStyle` en `flow.py`: atajos fijos, resumen con «Enviar / Corregir», «Disponibilidad por verificar» | Captura validada y corregible; fase 1 sin afirmar cupos. El canal de Chatwoot conserva su presentación. |
| Fechas: «20–22 nov», abreviaturas, rangos invertidos; mensajes con fechas = consulta comercial | D03 y «reutiliza lo que el huésped ya dijo». |
| `SHIFT_OVERRIDE` y escenario por sesión; próximo horario con día y fecha | D07 reproducible sin cambiar la hora. |
| `data/hosteria-demo.yaml` + `demo_inventory.py` (inventario de prueba) | Alojamiento ficticio y dato de inventario que respalda «Hay una habitación doble…». |
| Worker del SLA enruta conversaciones de demo a su propio hilo | Antes llamaba a Chatwoot con ids de demo. |
| Purga de la demo al vencer su sesión (`purge_demo`) | La transcripción de demo no esperaba la retención de 90 días. |
| `/demo` nueva (`demo.html`, `demo-*.js`, `demo-split.css`); se retiran `demo.js`, `console.js`, `voice.js`, `demo-journey.js`, `demo-console.css` | Pedido explícito: rediseñar la demo según la referencia. La portada no cambia. |
| `static-demo.js` reescrito con el mismo contrato | El build estático seguía emulando la API anterior. Ya no copia un `config.js` local. |
| `scripts/demo-local.sh`, `make demo-local` | Arranque sin Docker, con escenario limpio. |

Pruebas: copiloto **452** (436 previas + 16 nuevas en `test_demo_requests.py`), PMS **47**, interfaz **14**
(`node --test scripts/*.mjs`, ahora todas en CI). `ruff` sin hallazgos.

## 4. Arranque y escenario limpio

```bash
make demo-local LIMPIO=1
```

Abre `http://localhost:8080/demo.html?vista=huesped` y `…?vista=recepcion` (o `demo.html` en vista partida).
Con Docker: `make up` y `http://localhost:8080/demo`. Las credenciales externas (IA, Chatwoot) no hacen falta;
la sesión de recepción se firma con un secreto local generado en `.demo-local/`.

Volver al escenario limpio: `make demo-local LIMPIO=1` (borra solo `.demo-local/copiloto.sqlite`).
Guion de presentación: [docs/guion-demo.md](../guion-demo.md).

## 5. Trabajo académico pendiente (lo hace el equipo)

La implementación aporta evidencia técnica; lo siguiente se acredita por separado y con datos reales.

1. **Guardar V1.** Etiqueta el estado actual (`git tag eva3-v1`) y guarda capturas de `docs/img/02-demo.webp`
   a `04-recepcion.webp`. Ese es el prototipo que se testea primero.
2. **Primera ronda.** Con [guion-sesion.md](testeo/guion-sesion.md): al menos una persona en rol huésped y una en
   rol recepción (idealmente de un alojamiento de Villarrica). Tareas: ubicación, consulta de fechas con un
   error y su corrección, tomar y responder. Anota en [registro-sesion.md](testeo/registro-sesion.md) tiempos
   reales (los muestra la ficha), resultado y dificultades. **No uses los tiempos de esta verificación**.
3. **Matriz CDM.** Vuelca cualidades, debilidades y mejoras en [matriz-cim.md](testeo/matriz-cim.md), por
   participante y rol.
4. **Ajustar a V2.** Elige cambios justificados por la matriz (no por gusto) y regístralos en
   [registro-de-iteraciones.md](registro-de-iteraciones.md) como iteración nueva: problema observado → cambio →
   cómo se verificará.
5. **Segunda ronda** con el mismo guion y compara tiempos y errores contra la primera.
6. **Conectar hallazgos:** cada debilidad observada debe aparecer en el [storyboard](testeo/storyboard.html)
   (escena afectada), en el [mock-up](testeo/mockup.html) iterado (antes/después) y, si toca tiempos de
   respuesta, temporada alta, privacidad o costos, en el **PESTAL** profundizado.
7. **Estado del arte y defensa.** La comparación con Chatwoot, HiJiffy, Chattigo, Rasa y Dialogflow y la defensa
   individual se redactan con fuentes citadas y con los resultados de las rondas, no con esta verificación.

Los datos de ejemplo (VLL-001, Sofía, 20–22 nov, 00:42) son ilustrativos: identifícalos así en cualquier
entregable.
