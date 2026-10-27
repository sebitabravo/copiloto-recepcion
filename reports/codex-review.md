4 high findings

# Read-only code review

## Findings

### 1. High — Accepted messages can be lost permanently (R6)
**Locations:** `copiloto/src/copiloto/app.py:86-88`, `copiloto/src/copiloto/flow.py:105-110`, `copiloto/src/copiloto/flow.py:128-140`, `copiloto/src/copiloto/events.py:98-103`.

The endpoint acknowledges HTTP 200 before background work is durable. The processed-message insert is autocommitted before handling or any outgoing delivery. A crash after acceptance loses work; a transient Chatwoot failure during both the normal reply and fallback leaves the processed marker intact and exceptions swallowed. Replaying the same message then skips it forever. This is at-most-once attempted handling, not exactly-once successful processing.

**Verified scenario:** in-memory database and fake Chatwoot client; fail message delivery, process message 777, restore delivery, replay 777. Result: zero replies and one processed marker.

**Minimal fix:** durably enqueue the inbound before acknowledgement, distinguish pending/failed/completed work, and retry unfinished work. Persist outgoing operations in an outbox with delivery deduplication/reconciliation; merely moving the marker after sending introduces duplicate-send windows instead.

### 2. High — Asking for a human during partial guest capture cannot hand off
**Locations:** `copiloto/src/copiloto/flow.py:471-472`, `copiloto/src/copiloto/flow.py:511-514`, `copiloto/src/copiloto/flow.py:136-140`.

`_note()` reads `data['children']` whenever adults have been captured, although children may still be unknown. The global human-request path can enter handoff at that exact stage. Handoff sends its success message before constructing the note; both it and the fallback raise the same `KeyError` before opening/assigning the conversation.

**Verified scenario:** `quiero reservar` → valid dates → `2` adults → `recepción`. The conversation remains at `ask_children`, no private note or open-status update occurs, and the guest receives two messages claiming the request was passed to reception.

**Minimal fix:** format incomplete party data explicitly without indexing missing fields; make handoff work from every state. Complete the durable transfer before claiming success.

### 3. High — Unauthenticated panel lookup exposes guest information
**Location:** `copiloto/src/copiloto/app.py:104-125`.

The panel-data endpoint has no authentication or conversation-level authorization. Any caller able to reach the service can enumerate integer IDs and obtain guest names, dates, party composition, selected rooms and operational state. Being embedded in a Chatwoot iframe does not authenticate the underlying request.

**Verified scenario:** store a named conversation with stay dates; unauthenticated `GET /api/panel/10` returns 200 with those fields.

**Minimal fix:** require authenticated staff access and authorize the requested conversation, using a validated staff session or scoped signed panel token. Current Compose defaults to loopback binding: this finding does not assert default Internet exposure; local callers and any deployment exposing the port still bypass staff authentication.

### 4. High — PMS callbacks log the shared Chatwoot signing secret
**Locations:** `infra/docker-compose.yml:92`, `copiloto/src/copiloto/app.py:90-93`; deployment command at `copiloto/Dockerfile:9`.

The callback URL embeds `WEBHOOK_SECRET` in its query string. The deployed Uvicorn command leaves access logging enabled. Inspection of installed Uvicorn confirms its access logger includes the path and query string. Each booking notification therefore puts the same secret used for Chatwoot HMAC verification into service access logs; possession permits forging signed Chatwoot webhook requests.

**Minimal fix:** authenticate PMS callbacks with a header or timestamped body signature, preferably using a separate credential. Remove credential-bearing URLs, rotate the exposed shared secret and handle existing secret-bearing logs. No real credential values were read or printed to verify this finding.

### 5. Medium — First human reply can arrive before the SLA start is persisted
**Locations:** `copiloto/src/copiloto/flow.py:517-524`, `copiloto/src/copiloto/flow.py:530-537`, state persistence at `copiloto/src/copiloto/flow.py:134`.

Handoff awaits setting Chatwoot status to open before initializing/persisting the clock. During that await, a receptionist's public outgoing User webhook can load the old state with no start timestamp. Its message is marked processed, but `on_human_reply()` returns without recording it. Handoff subsequently persists a running clock even though the first human reply already happened.

**Verified scenario:** inject `on_human_reply()` during the fake `set_status()` await. Final state has a start but no stop, with zero `human_first_reply` events.

**Minimal fix:** serialize handoff and human replies through the same per-conversation coordination, persist the handoff boundary before exposing it to staff, and reconcile early replies rather than irreversibly discarding them.

### 6. Medium — SLA worker overwrites an already-recorded human stop
**Locations:** `copiloto/src/copiloto/sla.py:41-57`, `copiloto/src/copiloto/store.py:38-50`.

The worker loads the whole state, awaits Chatwoot operations, then upserts its stale snapshot. A human reply during the await saves `sla_stopped_at`, which the worker replaces with its old `None`. This can resurrect a stopped clock and later issue a false breach; the full-state save can also overwrite other concurrent state changes. `check_same_thread=False` does not protect these read/await/write sequences.

**Verified scenario:** deliver a human reply during the worker's mocked amber-label update. The database contains a `human_first_reply` event but `sla_stopped_at` is again null. A red-update interleaving reproduces the same lost stop.

**Minimal fix:** use column-specific conditional updates preserving stop timestamps, with shared conversation synchronization and a fresh state check around external work. Do not hold a SQLite transaction open across network awaits. This is distinct from finding 5: here the stop was successfully persisted and then destroyed.

### 7. Medium — SLA timestamps and shift eligibility use inbound time, not handoff time
**Locations:** `copiloto/src/copiloto/flow.py:101`, `copiloto/src/copiloto/flow.py:502`, `copiloto/src/copiloto/flow.py:520-524`.

`ctx.now` is captured before lock waiting and all handoff network calls. It is reused for shift classification, commercial/handoff events and SLA initialization. Queued or slow handling can therefore start the clock in the past or select the wrong shift across an opening/closing boundary.

**Verified scenario:** advance the injected clock by 181 seconds during `set_status()`. Immediately after handoff the persisted clock is already 181 seconds old and the worker emits a red breach.

**Minimal fix:** capture clock and shift at the coordinated, persisted handoff boundary and consistently use that timestamp for events, SLA and staff deadline copy.

### 8. Medium — Retention preserves linkable histories and leaves Chatwoot copies intact (R6)
**Locations:** `copiloto/src/copiloto/store.py:91-101`, `copiloto/src/copiloto/events.py:31-36`, `copiloto/src/copiloto/privacy.py:48-50`.

The purge deletes local state/prebookings and removes inbound text, but retains individual events indefinitely with conversation IDs, exact timestamps and payload IDs such as `user_id` and `booking_id`. Those are linkable histories, not the notice's promised aggregate-only counts. The purge also never deletes guest messages or private notes from Chatwoot; those remain in its persistent database. No corresponding deletion client operation or retention job is present in the reviewed infrastructure.

**Concrete scenario:** after the retention cutoff, local state disappears, but historical events still identify the conversation and Chatwoot still holds its messages and dated private notes.

**Minimal fix:** replace expired identifiable events with non-linkable aggregates or remove/anonymize their identifiers. Define and implement retention for Chatwoot copies, or accurately narrow the notice and establish an explicit separate policy. This is a technical mismatch with the implemented/published policy, not a legal conclusion.

### 9. Medium — Retried PMS notifications duplicate effects
**Locations:** `copiloto/src/copiloto/app.py:95-98`, `copiloto/src/copiloto/flow.py:539-548`.

There is no persisted booking-callback identity check. Receiving the same valid `booking_id` twice records two `booking_confirmed` events and sends two private notes. This occurs naturally when the first request commits but its HTTP response is lost and the PMS retries. It inflates event counts and duplicates staff notifications.

**Minimal fix:** atomically deduplicate a source-qualified booking/event ID before recording conversion effects; enqueue the private note once in the same durable workflow. Repeated delivery should return success without repeating effects.

### 10. Low — Sold-out availability is not a dated reading (R3)
**Location:** `copiloto/src/copiloto/flow.py:387-389`.

The empty-offer branch formats only the reading's `HH:MM`, unlike the positive-offer branch. A historical sold-out reply cannot identify which calendar date the PMS was read.

**Verified scenario:** return an empty successful PMS reading; the guest sees “Según lectura del PMS a las 15:00…” without the reading date.

**Minimal fix:** use `_read_label(reading.read_at)` for the empty-offer branch as well.

## Five priority test gaps

1. Inject crashes/delivery failures before and after outgoing effects; replay the same inbound message and the same PMS booking callback to verify durable recovery without duplicates.
2. Request a human after adults but before children, asserting actual team assignment/open status rather than only closing text.
3. Use deterministic barriers for human replies during handoff initialization and amber/red worker awaits; assert the first public User reply remains the permanent stop.
4. Advance a fixed clock across a shift boundary and a delayed handoff; assert SLA starts at transfer time and empty availability includes the full reading date.
5. Exercise unauthorized panel access and retention end-to-end, including historical event identifiers and Chatwoot message/private-note copies.

## Verification and scope

Reviewed `copiloto/src/copiloto/*.py`, `copiloto/tests/*.py`, static panels for unsafe rendering, `pms_mock/src/pms_mock/main.py`, `infra/bootstrap/seed.rb`, `infra/docker-compose.yml` and `scripts/e2e.py`. No additional demonstrated defect was found in metrics calculations, PMS inventory transaction math, staff-token checks, seed logic or E2E assertions. Static guest-derived rendering uses escaping or `textContent`; no demonstrated XSS, SQL injection, SSRF or open redirect was found. Chatwoot signature verification matches timestamp-dot-body HMAC-SHA256 with a freshness check. No assignment-triggered SLA reset was found. PMS reads are GET-only; auxiliary prebookings stay local rather than blocking/writing the PMS.

Targeted reproductions used in-memory SQLite and existing fake clients, not live guest data or service mutations. Sources changed externally during review; a transient missing-method observation was rechecked, withdrawn and excluded. Line references above were checked against the current files. No git commands were run; only this report was authored.

Full service test command, from `copiloto/`: `uv run pytest -q`. Environment disabled bytecode and pytest cache creation (`PYTHONDONTWRITEBYTECODE=1`, `PYTEST_ADDOPTS='-p no:cacheprovider'`). Passing tests do not exercise the failing interleavings above.

```text
......................................................                   [100%]
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/sebitabravo/Developer/innovacio3/copiloto/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
54 passed, 1 warning in 1.03s
```

Engram tools were unavailable; no memory persistence is claimed.

## Resolución (orquestador)

Cada hallazgo se verificó leyendo el código antes de actuar.

| # | Estado | Qué se hizo |
|---|---|---|
| 1 | Aceptado como límite | Procesamiento a lo más una vez (sin duplicados). Cola durable queda para la fase real; documentado en el README |
| 2 | Corregido | `_note` tolera datos parciales; el fallback tras falla abre la conversación sin repetir eventos. Test `test_human_request_with_partial_party_data_still_hands_off` |
| 3 | Corregido | `/api/panel/*` exige `PANEL_TOKEN` (header `X-Panel-Token`); el seed lo deja en la URL del Dashboard App |
| 4 | Corregido | El PMS avisa con header `X-Events-Token` y un secreto propio (`PMS_EVENTS_SECRET`), ya no en la URL |
| 5 | Corregido | El traspaso persiste estado, eventos y reloj antes de abrir la conversación. Test `test_human_reply_during_handoff_is_not_lost` |
| 6 | Corregido | El SLA se actualiza con sentencias condicionales por columna (`start_sla`, `stop_sla`, `mark_sla`). Test `test_sla_worker_does_not_overwrite_a_recorded_human_stop` |
| 7 | Corregido | Hora de turno y SLA se toman en el traspaso (`self.clock()`), no al recibir el mensaje |
| 8 | Corregido (parcial) | La purga seudonimiza `conversation_id` y deja solo claves no identificables; la retención en Chatwoot queda como política del hotel (aviso de privacidad y docs lo dicen) |
| 9 | Corregido | `booking_id` se deduplica con `processed_messages`. Test en `test_app.py` |
| 10 | Corregido | La respuesta sin cupo incluye fecha y hora de la lectura |

## Segunda revisión: skill `code-review` (nivel medium, sobre `copiloto/src`, `pms_mock/src`, `infra`, `scripts`)

| Hallazgo | Estado |
|---|---|
| Worker SLA: `now - None` y alerta tras respuesta humana | Corregido: revalida el estado antes y después de cada await (`_running`); test `test_sla_worker_survives_a_clock_cleared_mid_check` |
| Fallback tras falla sin nota/eventos/SLA | Corregido: `_persist_handoff` + nota con motivo `error`; test `test_unexpected_failure_hands_off_with_note_and_events` |
| `booking:N` marcado antes de aplicar efectos | Corregido: se marca después de registrar y convertir |
| Mensaje en cola resetea el SLA de un traspaso activo | Corregido: `handoff_at`; los mensajes anteriores al traspaso se ignoran. Test `test_message_queued_behind_the_handoff_does_not_reset_the_clock` |
| «hola» de un huésped que vuelve cae en fallback y cuenta como consulta | Corregido: el reinicio de sesión ocurre antes de evaluar el saludo |
| `PANEL_TOKEN` en la query string quedaba en access logs | Corregido: uvicorn corre con `--no-access-log` |
| Seudónimo con `WEBHOOK_SECRET` (también está en la base de Chatwoot) | Corregido: sal = `PMS_EVENTS_SECRET`, que Chatwoot no guarda |
| Quick tunnel expone todo Chatwoot | Documentado como riesgo explícito en `docs/canales.md` |
| Rutas `async def` con SQLite en el event loop | Aceptado: consultas locales cortas; el hilo único evita compartir la conexión entre hilos |
| Métricas cuentan solo el primer traspaso por conversación | Aceptado y documentado: una conversación reabierta no se cuenta como lead nuevo |
| `scripts/e2e.py` usa la fecha fija 2027-03-15 | Pendiente: vence en marzo de 2027 |
| Purga fila por fila | Aceptado: volumen de prototipo |
