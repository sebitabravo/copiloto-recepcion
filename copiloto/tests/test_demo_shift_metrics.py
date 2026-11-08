"""Turno al ingreso, métricas por solicitud y orden de la cola.

- La clasificación de turno se fija cuando ENTRA la consulta comercial (`commercial_at`) y no cambia al derivar:
  21:59:50 → 22:00:10 sigue «en turno» para la meta; 07:59:50 → 08:00:10 sigue «fuera de turno». El mensaje al
  huésped usa el horario del momento del traspaso (si recepción está o no atendiendo).
- Métricas: FAQ < 10 s, primera respuesta humana pertinente < 180 s solo para ingresos en turno, por SOLICITUD
  (dos solicitudes del mismo hilo cuentan por separado); tomar y acusar recibo se informan aparte y nunca
  cuentan como respuesta; la demo no se mezcla con la operación; los datos históricos sin solicitud se
  informan como incompletos.
- Cola: el orden se aplica ANTES del límite (una pendiente antigua no desaparece tras 50 cerradas nuevas).
"""

import json

from conftest import local_epoch
from copiloto.metrics import compute_metrics
from test_demo_requests import REPLY

from copiloto import store

TARGET = 180


def booking_across(demo, intake, handoff):
    """Consulta comercial que entra a la hora `intake` y se envía a recepción a la hora `handoff`."""
    demo.clock.now = intake - 3
    # El salto de reloj supera la sesión firmada de recepción (horas): Sofía vuelve a entrar.
    assert demo.sofia.post("/api/demo/session", json={"name": "Sofía"}).status_code == 204
    demo.say("Consultar fechas")
    demo.say("20–22 nov · 2 adultos")
    demo.say("Sin niños")
    demo.clock.now = handoff - 3
    return demo.say("Enviar a recepción")


def only_request(demo):
    [item] = demo.inbox()["requests"]
    return item


def metrics(demo, scope="demo", days=30):
    return compute_metrics(demo.db, demo.clock.now - days * 86400, demo.clock.now + 1, {"sla_red_s": TARGET},
                           scope=scope)


# ---------- turno al ingreso ----------

def test_intake_at_21_59_50_keeps_the_shift_after_a_handoff_at_22_00_10(demo):
    intake, handoff = local_epoch(2026, 11, 9, 21, 59, 50), local_epoch(2026, 11, 9, 22, 0, 10)
    body = booking_across(demo, intake, handoff)
    item = only_request(demo)
    assert item["commercial_at"] == intake
    assert item["intake_in_shift"] is True, "entró en turno: cuenta para la meta de 180 s"
    assert item["measurement"]["state"] in ("en_curso", "vencida")
    assert item["measurement"]["elapsed_s"] == int(handoff - intake), "el reloj corre desde el ingreso"
    # El huésped recibe el horario del momento del traspaso: a las 22:00:10 recepción ya no atiende.
    closing = body["messages"][-1]["body"]
    assert "Solicitud guardada" in closing and "desde las 08:00" in closing
    assert body["request"]["label"].startswith("Guardada · recepción responde desde las 08:00")
    assert metrics(demo)["commercial_started_in_shift"] == 1


def test_intake_at_07_59_50_stays_out_of_shift_after_a_handoff_at_08_00_10(demo):
    intake, handoff = local_epoch(2026, 11, 9, 7, 59, 50), local_epoch(2026, 11, 9, 8, 0, 10)
    body = booking_across(demo, intake, handoff)
    item = only_request(demo)
    assert item["intake_in_shift"] is False, "entró fuera de turno: no cuenta para la meta"
    assert item["measurement"]["state"] == "fuera_de_turno"
    # A las 08:00:10 recepción ya atiende: el huésped lo sabe.
    assert body["messages"][-1]["body"].startswith("Solicitud enviada a recepción. Te responderán por aquí.")
    assert body["request"]["label"] == "Enviada a recepción · te responderán por aquí"
    result = metrics(demo)
    assert result["commercial_started_in_shift"] == 0 and result["commercial_started_out_of_shift"] == 1


# ---------- métricas por solicitud ----------

def take(demo, request_id):
    assert demo.sofia.post(f"/api/panel/requests/{request_id}/take").status_code == 200


def answer(demo, request_id, kind="answer", body=REPLY):
    response = demo.sofia.post(f"/api/panel/requests/{request_id}/reply", json={"body": body, "kind": kind})
    assert response.status_code == 200, response.text


def test_an_ack_then_a_pertinent_answer_counts_the_answer_and_reports_take_and_ack_apart(demo):
    demo.say("Hablar con recepción")
    request_id = only_request(demo)["id"]
    demo.clock.advance(20)
    take(demo, request_id)
    demo.clock.advance(10)
    answer(demo, request_id, kind="ack", body="Recibido, lo reviso y te escribo.")
    demo.clock.advance(70)
    answer(demo, request_id)
    result = metrics(demo)
    assert result["commercial_started_in_shift"] == 1
    assert result["commercial_answered_within_180"] == 1
    assert result["first_reply_median_s"] == 100, "la primera respuesta pertinente, no el acuse (30 s)"
    assert result["requests_taken"] == 1 and result["acks"] == 1


def test_an_ack_alone_never_meets_the_target(demo):
    demo.say("Hablar con recepción")
    request_id = only_request(demo)["id"]
    take(demo, request_id)
    demo.clock.advance(30)
    answer(demo, request_id, kind="ack", body="Recibido, lo reviso y te escribo.")
    demo.clock.advance(200)
    answer(demo, request_id)
    result = metrics(demo)
    assert result["commercial_answered_within_180"] == 0
    assert result["commercial_response_compliance_pct"] == 0


def test_two_requests_in_the_same_thread_are_measured_separately(demo):
    demo.say("Hablar con recepción")
    first = only_request(demo)["id"]
    take(demo, first)
    demo.clock.advance(60)
    answer(demo, first)
    demo.sofia.post(f"/api/panel/requests/{first}/close")
    demo.clock.advance(600)
    demo.say("Hablar con recepción")
    second = next(item["id"] for item in demo.inbox()["requests"] if item["id"] != first)
    take(demo, second)
    demo.clock.advance(250)
    answer(demo, second)
    result = metrics(demo)
    assert result["commercial_started_in_shift"] == 2, "una medición por solicitud, no por hilo"
    assert result["commercial_answered_within_180"] == 1
    assert result["commercial_response_compliance_pct"] == 50


def test_faq_latency_is_measured_against_10_seconds(demo):
    demo.say("¿Dónde queda el hotel?")
    demo.say("¿Tienen piscina?")
    result = metrics(demo)
    assert result["faq_target_s"] == 10
    assert result["faq_within_target_pct"] == 100


def test_demo_and_operation_are_measured_apart(demo):
    demo.say("Hablar con recepción")
    request_id = only_request(demo)["id"]
    take(demo, request_id)
    answer(demo, request_id)
    assert metrics(demo, scope="demo")["commercial_started_in_shift"] == 1
    operation = metrics(demo, scope="operation")
    assert operation["commercial_started_in_shift"] == 0 and operation["queries"] == 0
    # La sesión de la demo solo ve las métricas de la demo.
    data = demo.sofia.get("/metricas/data.json").json()
    assert data["scope"] == "demo" and data["commercial_started_in_shift"] == 1


def test_historical_events_without_request_are_reported_as_incomplete(demo):
    ts = demo.clock.now - 3600
    demo.db.execute(
        "INSERT INTO events(conversation_id, kind, ts, payload) VALUES (?, 'commercial_started', ?, ?)",
        (777, ts, json.dumps({"in_shift": True, "inbound_ts": ts})),
    )
    demo.db.execute(
        "INSERT INTO events(conversation_id, kind, ts, payload) VALUES (?, 'human_first_reply', ?, ?)",
        (777, ts + 60, json.dumps({"user_id": 1})),
    )
    result = metrics(demo, scope="operation")
    assert result["historical_incomplete"]["requests_without_id"] == 1
    # Regla declarada: se miden por conversación (como antes), y el informe lo dice.
    assert result["commercial_started_in_shift"] == 1 and result["commercial_answered_within_180"] == 1
    assert "por conversación" in result["historical_incomplete"]["rule"]


# ---------- cola ----------

def demo_request(demo, index, commercial_at, now):
    conversation_id = store.ensure_demo_conversation(demo.db, f"eva3-cola-{index:016d}", now)
    with store.transaction(demo.db):
        return store.create_request(
            demo.db, conversation_id, prefix="BDL", source=store.DEMO_SOURCE, channel="demo",
            reason="human_requested", in_shift=True, commercial_at=commercial_at, now=now, data={},
        )


def test_an_old_pending_request_is_not_hidden_by_50_newer_closed_ones(demo):
    demo.say("Hablar con recepción")
    old = only_request(demo)
    for index in range(50):
        demo.clock.advance(30)
        row = demo_request(demo, index, demo.clock.now, demo.clock.now)
        store.close_request(demo.db, row["id"], demo.clock.now)
    items = demo.inbox()["requests"]
    assert items[0]["id"] == old["id"], "la pendiente más antigua encabeza la cola"
    assert all(item["status"] == "cerrada" for item in items[1:])


def test_open_requests_come_first_by_priority_and_wait_with_a_stable_tiebreak(demo):
    now = demo.clock.now
    rows = [demo_request(demo, index, now - 100, now) for index in range(4)]
    store.take_request(demo.db, rows[1]["id"], "Sofía", now)
    store.close_request(demo.db, rows[2]["id"], now)
    order = [item["id"] for item in store.list_requests(demo.db, now, TARGET, store.DEMO_SOURCE)]
    # Pendientes (misma espera → la más antigua por id), luego en atención, al final las cerradas.
    assert order == [rows[0]["id"], rows[3]["id"], rows[1]["id"], rows[2]["id"]]
    again = [item["id"] for item in store.list_requests(demo.db, now, TARGET, store.DEMO_SOURCE)]
    assert again == order, "orden estable entre lecturas"

