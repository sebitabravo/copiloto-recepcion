# Verificación de la demo · EVA 3 (D01–D10)

Fecha: 8-nov-2026. Rama `refactor/ux-logic-cleanup`. La demo usa la misma marca y los mismos datos que la portada:
**Hotel Boutique Bordeluz** (`data/hotel.yaml`) y el **PMS simulado** (`pms_mock`). Los huéspedes son ficticios y
los cupos y precios del PMS son simulados.

**Criterio central:** un huésped crea una consulta válida, recepción la toma con todo su contexto y una
respuesta escrita por recepción llega al hilo original, con estados, persistencia y mediciones coherentes.
**Resultado: cumple** en el arranque local con flujo guiado. Lo no verificado está marcado al final de la sección 2.

Evidencia: **[código]** lectura de código · **[auto]** prueba automatizada (pytest con el cliente HTTP de
FastAPI, o `node --test`) · **[UI]** recorrido real en navegador (Chromium con Playwright, contextos separados =
personas distintas) · **[HTTP]** llamadas a las rutas de los servicios levantados · **[proceso]** el lanzador real
contra una copia limpia del repositorio.

Este documento es **verificación técnica**. No reemplaza las dos rondas con personas que hace el equipo
(sección 6): sus tiempos y hallazgos se registran aparte y no se mezclan con los de aquí.

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
| **D01** Arranque reproducible | Parcial: `make up` exige Docker; sin daemon no hay ruta documentada | **Cumple** sin Docker; Docker **no verificable** aquí | [proceso] `make demo-local-check`: 13/13 en copia limpia (arranque con «listo», `LIMPIO=0` conserva, `LIMPIO=1` borra, puerto ocupado, plazo vencido, servicio caído, Ctrl+C, proceso ajeno intacto, `config.js` viejo ignorado). Perfil liviano de Docker: el copiloto arranca con el entorno exacto de compose sin `CHATWOOT_BOT_TOKEN` y `/webhooks/chatwoot` responde 503. `docker compose … config -q` válido. |
| **D02** Ubicación, FAQ, «Hablar con recepción» | Parcial: «Hablar con recepción» no deriva y ofrece el número real | **Cumple** | [auto] `test_location_and_faq_are_answered_before_asking_for_stay_data`, `test_talk_to_reception_works_without_dates_and_pending_fields_are_explicit`. [UI] atajos visibles; ubicación con enlace «Abrir en Google Maps». |
| **D03** Fechas invertidas y corrección | Falta: no capturaba fechas | **Cumple** | [auto] `test_inverted_dates_…`, `test_guest_can_correct_the_summary_before_sending`. [UI] «22 al 20 de noviembre · 2 adultos» → error; «20–22 nov» → solo pide niños. |
| **D04** Solicitud canónica localizable | Falta: sin solicitud ni ID | **Cumple** | [auto] `test_canonical_case_end_to_end`. [UI] BDL-001 con 20–22 nov, 2 adultos, 0 niños, canal, motivo, ingreso y espera; fila persistida en SQLite (`requests`). |
| **D05** Tomar, responder, recargar | Parcial: respuesta sin responsable ni estados | **Cumple** | [auto] mismo test + `test_the_bot_stays_silent_while_reception_owns_the_case`. [UI] Tomar → En atención (Sofía); respuesta → Respondida; el huésped ve «Sofía · Recepción»; reserva «Pendiente de confirmación»; la recarga muestra lo mismo. |
| **D06** Reintentos sin duplicar | Falta: sin llave de idempotencia | **Cumple** | [auto] `test_demo_retries.py`: fallas inyectadas antes y después de guardar (huésped y recepción), respuesta perdida, llave reutilizada con otro texto (409), llave por sesión y por caso. [UI] se cortó la respuesta de red después de procesar: «Reintentar» dejó 1 mensaje y 1 solicitud. |
| **D07** Fuera de turno | Falta en la demo | **Cumple** | [auto] `test_off_shift_request_is_saved_with_the_next_opening_and_kept_out_of_the_target`. [UI] con la hora real (≈05:25 en Chile): «…te responderá por aquí desde las 08:00 del domingo 8 de noviembre»; la bandeja marca «Fuera de turno»; sin reloj de 180 s. |
| **D08** Eventos y cálculo | Parcial: el reloj partía al derivar; la demo no tenía eventos por hilo | **Cumple** | [auto] `test_demo_shift_metrics.py` (turno al ingreso a ambos lados del cambio de turno, acuse y luego respuesta, dos solicitudes del mismo hilo, FAQ < 10 s, demo separada de operación, histórico incompleto, cola), `test_the_clock_starts_when_the_commercial_query_enters_and_an_ack_does_not_stop_it`, `test_a_missed_target_is_recorded_as_a_breach_in_the_demo_thread`. [UI] «Medición de esta solicitud» lista los eventos con su desfase. |
| **D09** Móvil, escritorio, otra sesión | Parcial | **Cumple** | [UI] dos presentaciones en contextos separados, cada una con su «Sofía»: cada bandeja ve solo su caso, el detalle ajeno da 404 y el huésped de una no recibe la respuesta de la otra. iPhone 13, 1280 y 1440 px sin desbordes; la vista `?vista=huesped` nunca abre sesión de recepción. [auto] `test_demo_runs.py`, `test_demo_isolation.py`. |
| **D10** PMS simulado (fase 2) | Parcial: el PMS no participaba en la demo | **Cumple** | [auto] `test_guest_can_correct_the_summary_…` (lectura con hora en el resumen), `test_a_pms_outage_never_reports_availability_and_stays_with_reception`, `test_the_demo_never_calls_the_operational_pms` (adaptador operativo instrumentado: 0 llamadas), `test_without_a_test_inventory_…`. [UI] el resumen del bot y «Consultar el PMS» de recepción muestran origen, hora y «preliminar»; caída real o simulada → «Disponibilidad por verificar» y el caso queda en recepción. |

Coherencia con la portada: [auto] `the demo keeps the landing name, brand and palette` (misma marca y hotel,
colores solo desde los tokens de la portada). [UI] desde la portada, «Probar la demo» abre `/demo` con la misma
marca, el mismo hotel y el acento bronce, sin errores de consola.

Versión estática (portfolio): [auto] `scripts/test-static-demo.mjs`. [UI] caso canónico en dos pestañas de
`dist/` con **cero** peticiones `/api` a la red.

### Recorrido completo en navegador (segunda verificación)

[UI] `make demo-local` y Chromium con tres contextos (huésped 1, huésped 2 y recepción) en la misma corrida:
ubicación → «22 al 20 de noviembre, 2 adultos» (error entendible) → «20 al 22 de noviembre» (no vuelve a pedir
adultos) → «Sin niños» → resumen con lectura del PMS y su hora → enviar (BDL-005). El huésped 2 abre BDL-006.
Recepción cambia de BDL-006 a BDL-005, la toma (En atención), envía un **acuse** (sigue En atención), consulta
cupos y envía la **respuesta pertinente** (Respondida). Huésped 1: la respuesta aparece 1 vez; huésped 2: 0.
Se recargan las tres vistas y luego se **reinician los servicios** (`LIMPIO=0`): misma corrida en la URL,
respuesta ×1 y acuse ×1 en el hilo correcto, ficha «Respondida» y reserva «Pendiente de confirmación».

### No verificado en este entorno

- `make up` / `make up-full` con Docker (el entorno no tiene daemon: `docker info` falla) y la bandeja real de
  **Chatwoot**. El perfil liviano se verificó arrancando el copiloto con el entorno exacto de compose.
- Modo con IA (`DEMO_AI=1`): sin `LLM_API_KEY`. Sus pruebas con modelo guionado siguen en verde.
- Voz y micrófono: la nueva `/demo` no expone la llamada; los endpoints `/api/demo/voice*` siguen con sus pruebas.
- Confirmar la reserva en el PMS desde la bandeja de la demo: el panel del PMS no enlaza conversaciones de demo
  (ids negativos). Fase siguiente si se quiere mostrar en vivo.

## 3. Correcciones de la auditoría técnica

Cada hallazgo se reprodujo **antes** de corregirlo (prueba en rojo o sonda sobre el código anterior).

| Hallazgo (reproducido) | Archivo | Cambio | Prueba | Resultado |
|---|---|---|---|---|
| Una lectura tardía del caso A se pintaba al elegir B y la respuesta podía ir a A; una lectura del huésped anterior aparecía en el huésped nuevo; sin espera ante 429 | `landing/demo-inbox.js`, `demo-guest.js`, `demo-shared.js` | Generación por selección y acción ligada al id; reintento con el caso, la llave y el texto originales; `epoch` por huésped; un solo ciclo de sondeo con `Retry-After` y espera creciente | `scripts/test-demo-races.mjs` (0/4 antes, 4/4 después) | Cumple |
| `LIMPIO=0` borraba los datos; `kill 0` detenía todo el grupo; sin espera ni «listo»; un `config.js` de túnel desviaba la demo; `make static-demo` fallaba (script sin permiso de ejecución) | `Makefile`, `scripts/demo-local.sh`, `serve-landing.py`, `demo.sh` | Solo `LIMPIO=1` borra; puertos, plazo, «listo», error con log y parada solo de lo propio; `config.js` generado; scripts ejecutables y comandos con el mismo nombre | `make demo-local-check` 13/13 | Cumple |
| El perfil liviano de Docker no arrancaba sin `CHATWOOT_BOT_TOKEN` | `config.py`, `app.py` | `CHATWOOT_ENABLED` se deduce del token; sin integración el webhook responde 503 | `test_config.py` (3 nuevas) y arranque con el entorno de compose | Cumple |
| Huésped: la llave se marcaba antes de guardar el mensaje (el reintento no guardaba nada); recepción: la respuesta se guardaba antes de la llave (el reintento la duplicaba); misma llave con otro texto se descartaba callada | `store.py`, `app.py`, `events.py` | Tabla `action_keys` por sesión o caso con hash del contenido; ingreso atómico `started`/`done`; llave, mensaje, estado y evento en una transacción | `test_demo_retries.py` (5 en rojo antes) | Cumple |
| 21:59:50 → 22:00:10 quedaba «fuera de turno»; métricas por conversación (la 2.ª solicitud del hilo no contaba); demo mezclada con operación; la cola cortaba con `LIMIT` antes de ordenar (una pendiente antigua desaparecía) | `flow.py`, `store.py`, `metrics.py`, `metricas.html` | Turno fijado al ingreso; métricas por solicitud, FAQ < 10 s, tomas y acuses aparte, `events.source`; regla para el histórico; orden en SQL antes del límite | `test_demo_shift_metrics.py` (10 en rojo antes) | Cumple |
| Cualquier sesión de la demo veía los casos de todas las presentaciones; dos «Sofía» eran la misma persona; la demo leía el PMS de la operación (2 llamadas por recorrido) | `app.py`, `store.py`, `pms.py`, `demo-page.js` | Corrida emitida por el servidor (`?corrida=`), operador con id estable firmado, verificación por corrida y operador en cada ruta; adaptador de PMS propio de la demo | `test_demo_runs.py` (11) y recorrido [UI] con dos contextos | Cumple |

## 4. Cambios y su motivo

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

Pruebas (segunda verificación): copiloto **479**, PMS simulado **47**, `pms_bridge` **16**, `wa_bridge` **59**,
interfaz **20** (`node --test scripts/*.mjs`) y lanzador **13/13** (`make demo-local-check`). `ruff` sin hallazgos.

## 5. Arranque oficial y escenario limpio

```bash
make demo-local
```

Espera «listo» y abre `http://localhost:8080/demo`. La página crea una corrida y la deja en la URL: los
enlaces «Abrir huésped/recepción en otra ventana» siguen en la misma. Fuera de 08:00–22:00, **Turno de recepción
→ Simular en turno**. Ctrl+C detiene la demo y **conserva** los datos. No hacen falta credenciales externas: los
secretos locales se generan en `.demo-local/`.

Escenario limpio, explícito: `make demo-local LIMPIO=1` (borra solo las bases de `.demo-local/`).
Guion de presentación: [docs/guion-demo.md](../guion-demo.md).

## 6. Trabajo académico pendiente (lo hace el equipo)

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
