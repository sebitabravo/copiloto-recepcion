# Verificación de la demo · EVA 3 (D01–D10)

Fecha: 8-nov-2026. Rama `refactor/ux-logic-cleanup`. La demo usa la misma marca y los mismos datos que la portada:
**Hotel Boutique Bordeluz** (`data/hotel.yaml`) y el **PMS simulado** (`pms_mock`). Los huéspedes son ficticios y
los cupos y precios del PMS son simulados.

**Criterio central:** un huésped crea una consulta válida, recepción la toma con todo su contexto y una
respuesta escrita por recepción llega al hilo original, con estados, persistencia y mediciones coherentes.
**Resultado: cumple** en el arranque local con flujo guiado. Lo no verificado está marcado al final de la sección 2.

Evidencia: **[código]** lectura de código · **[auto]** prueba automatizada · **[UI]** recorrido real en
navegador (Chromium con Playwright, escritorio 1440 px y iPhone 13) · **[HTTP]** llamadas a las rutas locales.

## 1. Primer punto de falla (antes de los cambios)

Arranque: copiloto con `uv run uvicorn` en `:8100`, `AI_MODE=off` (Docker sin daemon en el entorno).
Caso canónico por `POST /api/demo/chat` **[HTTP]**:

1. «¿Dónde queda el hotel?» → respuesta de ubicación correcta.
2. «Quiero consultar del 20 al 22 de noviembre para 2 adultos» → **falla**: «No tengo ese dato publicado.
   Para confirmarlo, escribe a recepción: +56 9… o comercial@…», es decir, el contacto real del hotel.
3. «Hablar con recepción» → misma respuesta: **no deriva**. `GET /api/panel/queue` muestra la conversación en
   `step: ai`, sin reloj ni solicitud.

Causa: `/api/demo/chat` sin IA usaba `guided.guided_reply` (solo FAQ y ubicación), no el motor guiado
`flow.Copiloto` que sí captura fechas, lee el PMS y deriva. La demo y el canal de Chatwoot eran dos lógicas.

## 2. Matriz antes / después

| ID | Antes | Después | Evidencia (después) |
|---|---|---|---|
| **D01** Arranque reproducible | Parcial: `make up` exige Docker; sin daemon no hay ruta documentada | **Cumple** sin Docker; Docker **no verificable** aquí | [UI] `make demo-local LIMPIO=1` levanta portada `:8080`, copiloto `:8100` y PMS `:8200`; `/`, `/demo`, `/privacidad`, `/api/demo/status` y los `/health` responden 200. `docker compose … config -q` válido en los perfiles full, whatsapp, beds24 e ia. |
| **D02** Ubicación, FAQ, «Hablar con recepción» | Parcial: «Hablar con recepción» no deriva y ofrece el número real | **Cumple** | [auto] `test_location_and_faq_are_answered_before_asking_for_stay_data`, `test_talk_to_reception_works_without_dates_and_pending_fields_are_explicit`. [UI] atajos visibles; ubicación con enlace «Abrir en Google Maps». |
| **D03** Fechas invertidas y corrección | Falta: no capturaba fechas | **Cumple** | [auto] `test_inverted_dates_…`, `test_guest_can_correct_the_summary_before_sending`. [UI] «22 al 20 de noviembre · 2 adultos» → error; «20–22 nov» → solo pide niños. |
| **D04** Solicitud canónica localizable | Falta: sin solicitud ni ID | **Cumple** | [auto] `test_canonical_case_end_to_end`. [UI] BDL-001 con 20–22 nov, 2 adultos, 0 niños, canal, motivo, ingreso y espera; fila persistida en SQLite (`requests`). |
| **D05** Tomar, responder, recargar | Parcial: respuesta sin responsable ni estados | **Cumple** | [auto] mismo test + `test_the_bot_stays_silent_while_reception_owns_the_case`. [UI] Tomar → En atención (Sofía); respuesta → Respondida; el huésped ve «Sofía · Recepción»; reserva «Pendiente de confirmación»; la recarga muestra lo mismo. |
| **D06** Reintentos sin duplicar | Falta: sin llave de idempotencia | **Cumple** | [auto] `test_a_retried_guest_message_is_processed_once`, `test_a_retried_staff_reply_is_sent_once`. [UI] se cortó la respuesta de red después de procesar: «Reintentar» dejó 1 mensaje y 1 solicitud. |
| **D07** Fuera de turno | Falta en la demo | **Cumple** | [auto] `test_off_shift_request_is_saved_with_the_next_opening_and_kept_out_of_the_target`. [UI] con la hora real (≈05:25 en Chile): «…te responderá por aquí desde las 08:00 del domingo 8 de noviembre»; la bandeja marca «Fuera de turno»; sin reloj de 180 s. |
| **D08** Eventos y cálculo | Parcial: el reloj partía al derivar; la demo no tenía eventos por hilo | **Cumple** | [auto] `test_the_clock_starts_when_the_commercial_query_enters_and_an_ack_does_not_stop_it`, `test_a_missed_target_is_recorded_as_a_breach_in_the_demo_thread`, `test_faq_latency_is_reported_per_question`, `test_sla_starts_when_the_commercial_query_entered_not_at_handoff`. [UI] «Medición de esta solicitud» lista los eventos con su desfase. |
| **D09** Móvil, escritorio, otra sesión | Parcial | **Cumple** | [UI] iPhone 13, 1280 y 1440 px sin desbordes; otra sesión de huésped no ve nada ajeno; la vista `?vista=huesped` nunca llamó a `/api/panel/*` ni abrió sesión de recepción. [auto] `test_guest_sessions_are_isolated`, `test_demo_isolation.py`. |
| **D10** PMS simulado (fase 2) | Parcial: el PMS no participaba en la demo | **Cumple** | [auto] `test_guest_can_correct_the_summary_…` (lectura con hora en el resumen), `test_a_pms_outage_never_reports_availability_and_stays_with_reception`. [UI] el resumen del bot y «Consultar el PMS» de recepción muestran origen, hora y «preliminar»; caída real o simulada → «cupo desconocido» y el caso queda en recepción. |

Coherencia con la portada: [auto] `the demo keeps the landing name, brand and palette` (misma marca y hotel,
colores solo desde los tokens de la portada). [UI] desde la portada, «Probar la demo» abre `/demo` con la misma
marca, el mismo hotel y el acento bronce, sin errores de consola.

Versión estática (portfolio): [auto] `scripts/test-static-demo.mjs`. [UI] caso canónico en dos pestañas de
`dist/` con **cero** peticiones `/api` a la red.

### No verificado en este entorno

- `make up` / `make up-full` (Docker sin daemon) y la bandeja real de **Chatwoot**.
- Modo con IA (`DEMO_AI=1`): sin `LLM_API_KEY`. Sus pruebas con modelo guionado siguen en verde.
- Voz y micrófono: la nueva `/demo` no expone la llamada; los endpoints `/api/demo/voice*` siguen con sus pruebas.
- Confirmar la reserva en el PMS desde la bandeja de la demo: el panel del PMS no enlaza conversaciones de demo
  (ids negativos). Fase siguiente si se quiere mostrar en vivo.

## 3. Cambios y su motivo

| Cambio | Motivo |
|---|---|
| `copiloto/demo_channel.py`: canal con la interfaz de Chatwoot que escribe en la transcripción de la demo | Una sola fuente de verdad: la demo usa **el mismo motor guiado** que el canal real. |
| Tabla `requests` con estado de atención y de reserva por separado | Solicitud vinculada al hilo, con ID (BDL-NNN), responsable y estados persistentes. |
| `/api/panel/requests…` (listar, tomar, responder, cerrar, consultar el PMS) | Bandeja con la acción principal según el estado; solo las sesiones de demo escriben en la demo. |
| Llaves de idempotencia (`client_message_id`, `client_id`) | D06: un reintento no duplica. |
| Reloj desde `commercial_at`; acuse ≠ respuesta; evento `sla_breached` | D08 según la especificación de la EVA 3. |
| `FlowStyle`: atajos fijos, resumen con lectura del PMS y «Enviar / Corregir» | Captura validada y corregible, y el paso 03 que promete la portada (PMS con sello de hora). |
| Fechas: «20–22 nov», abreviaturas, rangos invertidos; un mensaje con fechas es consulta comercial | D03 y «reutiliza lo que el huésped ya dijo». |
| `SHIFT_OVERRIDE` y escenario por sesión; próximo horario con día y fecha | D07 reproducible sin cambiar la hora. |
| El worker del SLA enruta las conversaciones de demo a su propio hilo | Antes llamaba a Chatwoot con ids de demo. |
| Purga de la demo al vencer su sesión (`purge_demo`) | La transcripción de demo no esperaba la retención de 90 días. |
| `/demo` nueva con la marca, el marco y los tokens de la portada | Pedido explícito: la demo se basa en el diseño, los colores y el nombre de la portada. |
| Portada: 10 líneas de texto (pasos 02, 04 y 05, «Hace», cinta y enlace a la bandeja) | Esas frases contradecían la demo (p. ej. «la derivación… sin notificar al equipo»). Diseño intacto. |
| `static-demo.js` reescrito con el mismo contrato y el mismo hotel | El build estático emulaba la API anterior; ya no copia un `config.js` local. |
| `scripts/demo-local.sh`, `scripts/serve-landing.py`, `make demo-local` | Arranque sin Docker con PMS simulado, URLs limpias y `/privacidad` como en nginx. |
| Se restauran `pms_bridge`, `wa_bridge` y el modelo local | Lo pidió la revisión de la PR #13: retirarlos va en una PR de deprecación aparte. |

Pruebas: copiloto **446** (incluye 16 de `test_demo_requests.py`), PMS simulado **47**, `pms_bridge` **16**,
`wa_bridge` **59**, interfaz **16** (`node --test scripts/*.mjs`, todas en CI) y `model_eval --fake` ok. `ruff`
sin hallazgos.

## 4. Arranque y escenario limpio

```bash
make demo-local LIMPIO=1
```

Abre `http://localhost:8080` y pulsa **Probar la demo**, o directamente `http://localhost:8080/demo?vista=huesped`
y `…?vista=recepcion`. Con Docker: `make up` y `http://localhost:8080/demo`. No hacen falta credenciales
externas: los secretos locales se generan en `.demo-local/`.

Volver al escenario limpio: `make demo-local LIMPIO=1` (borra solo las bases de `.demo-local/`).
Guion de presentación: [docs/guion-demo.md](../guion-demo.md).

## 5. Trabajo académico pendiente (lo hace el equipo)

La implementación aporta evidencia técnica; lo siguiente se acredita por separado y con datos reales.

1. **Guardar V1.** Etiqueta el estado actual (`git tag eva3-v1`) y guarda las capturas `docs/img/02-demo.webp`
   a `04-recepcion.webp`. Ese es el prototipo que se testea primero.
2. **Primera ronda.** Con [guion-sesion.md](testeo/guion-sesion.md): al menos una persona en rol huésped y una en
   rol recepción (idealmente de un alojamiento de Villarrica). Tareas: ubicación, consulta de fechas con un
   error y su corrección, tomar y responder. Anota en [registro-sesion.md](testeo/registro-sesion.md) tiempos
   reales (los muestra la ficha), resultado y dificultades. **No uses los tiempos de esta verificación**.
3. **Matriz CDM.** Vuelca cualidades, debilidades y mejoras en [matriz-cim.md](testeo/matriz-cim.md), por
   participante y rol.
4. **Ajustar a V2.** Elige cambios justificados por la matriz y regístralos en
   [registro-de-iteraciones.md](registro-de-iteraciones.md) como una iteración nueva: problema observado →
   cambio → cómo se verificará.
5. **Segunda ronda** con el mismo guion; compara tiempos y errores contra la primera.
6. **Conectar hallazgos:** cada debilidad observada debe aparecer en el [storyboard](testeo/storyboard.html)
   (escena afectada), en el [mock-up](testeo/mockup.html) iterado (antes/después) y, si toca tiempos de
   respuesta, temporada alta, privacidad o costos, en el **PESTAL** profundizado.
7. **Estado del arte y defensa.** La comparación con Chatwoot, HiJiffy, Chattigo, Rasa y Dialogflow y la defensa
   individual se redactan con fuentes citadas y con los resultados de las rondas, no con esta verificación.

Los datos de ejemplo (BDL-001, Sofía, 20–22 nov) son ilustrativos: identifícalos así en cualquier entregable.
