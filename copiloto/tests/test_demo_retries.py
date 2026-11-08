"""Reintentos recuperables: una falla a mitad de camino nunca deja una llave «gastada» sin su efecto.

Cada prueba inyecta una falla en un punto concreto y reintenta con la MISMA llave:
- Huésped: falla antes de guardar el mensaje → el reintento lo guarda y lo procesa una vez.
- Huésped: falla después de guardar el mensaje y antes de que el asistente conteste → el reintento termina
  el turno (sin volver a guardar el mensaje) y crea una sola solicitud.
- Recepción: la respuesta quedó guardada pero el servidor falló antes de contestar → el reintento no la duplica.
- Recepción: falla dentro de la transacción → no queda nada (ni mensaje, ni estado, ni evento, ni llave).
- La llave es por sesión (huésped) o por caso (recepción); con otro contenido se rechaza, no se descarta callada.
"""

import pytest
from conftest import DEMO_SESSION as SESSION
from test_demo_requests import REPLY

from copiloto import flow, store


class InjectedFailure(RuntimeError):
    """Falla inyectada por la prueba (simula un error de disco, un reinicio o un bug a mitad del turno)."""


def fail_once(monkeypatch, owner, name, *, before=True, when=lambda *args, **kwargs: True):
    """Reemplaza owner.name para que falle UNA vez (antes o después de ejecutar el original)."""
    original = getattr(owner, name)
    state = {"armed": True}

    def wrapper(*args, **kwargs):
        if state["armed"] and when(*args, **kwargs):
            state["armed"] = False
            if before:
                raise InjectedFailure(name)
            original(*args, **kwargs)
            raise InjectedFailure(name)
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, wrapper)
    return state


def chat(demo, text, key, session=SESSION):
    demo.clock.advance(3)
    return demo.guest.post("/api/demo/chat", json={"session_id": session, "message": text, "client_message_id": key,
                                                   "run": demo.run})


def guest_messages(demo, session=SESSION):
    conversation_id = store.demo_conversation_for_session(demo.db, session)
    if conversation_id is None:
        return []
    return [m for m in store.list_demo_messages(demo.db, conversation_id) if m["role"] == "guest"]


def request_count(demo):
    return demo.db.execute("SELECT COUNT(*) AS n FROM requests").fetchone()["n"]


def taken_request(demo):
    demo.say("Hablar con recepción")
    request_id = demo.inbox()["requests"][0]["id"]
    assert demo.sofia.post(f"/api/panel/requests/{request_id}/take").status_code == 200
    return request_id


def reply(demo, request_id, client_id, body=REPLY, kind="answer"):
    demo.clock.advance(5)
    return demo.sofia.post(f"/api/panel/requests/{request_id}/reply",
                           json={"body": body, "client_id": client_id, "kind": kind})


# ---------- huésped ----------

def test_a_guest_message_that_failed_before_saving_is_saved_once_on_retry(demo, monkeypatch):
    fail_once(monkeypatch, store, "insert_demo_message", when=lambda db, cid, role, *rest, **kw: role == "guest")
    with pytest.raises(InjectedFailure):
        chat(demo, "Hablar con recepción", "accion-falla-0001")
    assert guest_messages(demo) == [], "la falla no deja nada a medias"

    retry = chat(demo, "Hablar con recepción", "accion-falla-0001")
    assert retry.status_code == 200
    body = retry.json()
    assert body["duplicate"] is False, "la llave no quedó gastada por el intento fallido"
    assert [m["body"] for m in guest_messages(demo)] == ["Hablar con recepción"]
    assert body["request"] is not None and request_count(demo) == 1


def test_a_guest_turn_that_failed_after_saving_finishes_on_retry_without_duplicates(demo, monkeypatch):
    fail_once(monkeypatch, flow.Copiloto, "_guest_message")
    with pytest.raises(InjectedFailure):
        chat(demo, "Hablar con recepción", "accion-falla-0002")
    assert [m["body"] for m in guest_messages(demo)] == ["Hablar con recepción"], "el mensaje sí quedó guardado"
    assert request_count(demo) == 0

    retry = chat(demo, "Hablar con recepción", "accion-falla-0002")
    assert retry.status_code == 200
    body = retry.json()
    assert len(guest_messages(demo)) == 1, "el reintento no vuelve a guardar el mensaje"
    assert body["request"] is not None and request_count(demo) == 1, "el turno se terminó: una sola solicitud"
    assert body["handled_by"] == "recepcion"
    again = chat(demo, "Hablar con recepción", "accion-falla-0002").json()
    assert again["duplicate"] is True and request_count(demo) == 1 and len(guest_messages(demo)) == 1


def test_a_lost_response_is_recovered_with_the_reply_and_nothing_runs_twice(demo):
    first = chat(demo, "¿Dónde queda el hotel?", "accion-perdida-01").json()
    retry = chat(demo, "¿Dónde queda el hotel?", "accion-perdida-01").json()
    assert retry["duplicate"] is True
    answers = [m["body"] for m in retry["messages"] if m["role"] == "assistant"]
    assert any(body.startswith("Ubicación:") for body in answers), "el reintento trae la respuesta que se perdió"
    assert len(guest_messages(demo)) == 1
    assert [m["id"] for m in retry["messages"]] == [m["id"] for m in first["messages"]]
    fresh = chat(demo, "¿Tienen piscina?", "accion-nueva-0001").json()
    assert fresh["duplicate"] is False and len(guest_messages(demo)) == 2, "una acción nueva entra normal"


def test_a_guest_key_reused_with_other_text_is_rejected_not_silently_dropped(demo):
    assert chat(demo, "¿Dónde queda el hotel?", "accion-reusada-01").status_code == 200
    other = chat(demo, "¿Tienen piscina?", "accion-reusada-01")
    assert other.status_code == 409
    assert len(guest_messages(demo)) == 1


def test_guest_keys_are_scoped_to_the_session(demo):
    other_session = "eva3-huesped-0000000009"
    assert chat(demo, "¿Dónde queda el hotel?", "accion-compartida").json()["duplicate"] is False
    second = chat(demo, "¿Dónde queda el hotel?", "accion-compartida", session=other_session).json()
    assert second["duplicate"] is False, "la misma llave en otra sesión es otra acción"
    assert len(guest_messages(demo, other_session)) == 1


# ---------- recepción ----------

def first_reply_events(demo):
    return demo.db.execute("SELECT COUNT(*) AS n FROM events WHERE kind = 'human_first_reply'").fetchone()["n"]


def staff_messages(demo, request_id):
    rows = demo.db.execute(
        "SELECT body FROM demo_messages WHERE role = 'staff' AND request_id = ?", (request_id,)
    ).fetchall()
    return [row["body"] for row in rows]


def test_a_staff_reply_saved_before_a_failure_is_not_duplicated_on_retry(demo, monkeypatch):
    request_id = taken_request(demo)
    fail_once(monkeypatch, store, "staff_reply", before=False)
    with pytest.raises(InjectedFailure):
        reply(demo, request_id, "respuesta-falla-01")
    assert staff_messages(demo, request_id) == [REPLY], "la respuesta quedó guardada antes de la falla"

    retry = reply(demo, request_id, "respuesta-falla-01")
    assert retry.status_code == 200 and retry.json()["duplicate"] is True
    assert staff_messages(demo, request_id) == [REPLY], "el reintento no la vuelve a enviar"
    assert first_reply_events(demo) == 1
    assert retry.json()["request"]["status"] == "respondida"


def test_a_staff_reply_that_fails_inside_the_transaction_leaves_nothing_behind(demo, monkeypatch):
    request_id = taken_request(demo)
    fail_once(monkeypatch, store, "stop_sla")
    with pytest.raises(InjectedFailure):
        reply(demo, request_id, "respuesta-falla-02")
    row = store.get_request_row(demo.db, request_id)
    assert staff_messages(demo, request_id) == [] and row["status"] == "en_atencion"
    assert row["first_answer_at"] is None and first_reply_events(demo) == 0

    retry = reply(demo, request_id, "respuesta-falla-02")
    assert retry.status_code == 200 and retry.json()["duplicate"] is False
    assert staff_messages(demo, request_id) == [REPLY] and first_reply_events(demo) == 1


def test_a_staff_key_reused_with_other_text_is_rejected(demo):
    request_id = taken_request(demo)
    assert reply(demo, request_id, "respuesta-reusada").status_code == 200
    other = reply(demo, request_id, "respuesta-reusada", body="Otro texto distinto")
    assert other.status_code == 409
    assert staff_messages(demo, request_id) == [REPLY]


def test_staff_keys_are_scoped_to_the_case(demo):
    first = taken_request(demo)
    assert reply(demo, first, "respuesta-misma-1").json()["duplicate"] is False
    demo.sofia.post(f"/api/panel/requests/{first}/close")
    demo.say("Hablar con recepción")
    second = next(item["id"] for item in demo.inbox()["requests"] if item["id"] != first)
    demo.sofia.post(f"/api/panel/requests/{second}/take")
    again = reply(demo, second, "respuesta-misma-1")
    assert again.status_code == 200 and again.json()["duplicate"] is False, "otra solicitud, otra acción"
    assert staff_messages(demo, second) == [REPLY]
