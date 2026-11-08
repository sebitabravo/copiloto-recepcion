"""Recorrido de la EVA 3 en la demo: huésped → solicitud → recepción → respuesta en el mismo hilo.

Fija, con el flujo guiado (sin modelo), el Hotel Boutique Bordeluz de la portada y el PMS simulado:
- D02 ubicación y FAQ aprobadas antes de pedir datos; «Hablar con recepción» deriva sin fechas.
- Paso 03 de la portada: el resumen muestra la lectura del PMS con su hora, preliminar; sin PMS no promete.
- D03 fechas invertidas: error entendible y lo correcto (adultos) no se vuelve a pedir.
- D04 la solicitud queda con ID, fechas, huéspedes y canal, vinculada al hilo del huésped.
- D05 tomar → «En atención» con responsable; responder → «Respondida»; la reserva sigue pendiente.
- D06 reintentos con la misma llave no duplican mensajes ni solicitudes; una consulta nueva sí entra.
- D07 fuera de turno: horario informado, caso recuperable y fuera de la meta de 180 s.
- D08 el reloj parte al entrar la consulta comercial, asignar no lo reinicia, un acuse no lo detiene y
  un vencimiento queda registrado.
"""

from dataclasses import replace

import pytest
from conftest import FakeChatwoot, FakeClock, local_epoch
from copiloto.app import create_app
from fastapi.testclient import TestClient

from copiloto import store

SESSION = "eva3-huesped-0000000001"
OTHER = "eva3-huesped-0000000002"
REPLY = "Hay una habitación doble para esas fechas. ¿Quieres avanzar con la reserva?"


@pytest.fixture
def demo(settings, harness):
    """App con reloj en turno (domingo 8-nov-2026 10:14, Chile), huésped y recepción en sesiones distintas."""
    clock = FakeClock(local_epoch(2026, 11, 8, 10, 14))
    chatwoot = FakeChatwoot()
    app = create_app(
        replace(settings, demo_ai=False),
        chatwoot=chatwoot,
        pms=harness.pms,
        clock=clock,
        run_workers=False,
        db=harness.db,
    )

    class Demo:
        pass

    d = Demo()
    d.app, d.clock, d.db, d.chatwoot = app, clock, harness.db, chatwoot
    d.guest = TestClient(app)
    d.sofia = TestClient(app)
    assert d.sofia.post("/api/demo/session", json={"name": "Sofía"}).status_code == 204

    def say(text, session=SESSION, **extra):
        d.clock.advance(3)
        response = d.guest.post("/api/demo/chat", json={"session_id": session, "message": text, **extra})
        assert response.status_code == 200, response.text
        return response.json()

    def inbox(selected=None):
        params = {"selected": selected} if selected else {}
        return d.sofia.get("/api/panel/requests", params=params).json()

    d.say, d.inbox = say, inbox
    return d


def canonical(demo, **extra):
    """Caso canónico: ubicación, fechas, 2 adultos, sin niños, enviar."""
    demo.say("¿Dónde queda el hotel?", **extra)
    demo.say("Consultar fechas", **extra)
    demo.say("20–22 nov · 2 adultos", **extra)
    demo.say("Sin niños", **extra)
    return demo.say("Enviar a recepción", **extra)


def test_location_and_faq_are_answered_before_asking_for_stay_data(demo):
    body = demo.say("¿Dónde queda el hotel?")
    assert body["messages"][1]["body"].startswith("Hola, soy el asistente virtual de Hotel Boutique Bordeluz.")
    assert body["messages"][-1]["body"].startswith("Ubicación: Estamos en el sector Molco")
    assert "¿Para qué fechas?" not in body["reply"], "la ubicación no exige dar fechas"
    faq = demo.say("¿Tienen piscina?")
    assert faq["messages"][-1]["body"].startswith("Tenemos piscina temperada")
    assert faq["request"] is None and faq["handled_by"] == "asistente"
    assert "963949710" not in body["reply"] + faq["reply"], "la demo nunca da el número real del hotel"


def test_talk_to_reception_works_without_dates_and_pending_fields_are_explicit(demo):
    body = demo.say("Hablar con recepción")
    assert body["handled_by"] == "recepcion"
    assert body["messages"][-1]["body"].startswith("Solicitud enviada a recepción. Te responderán por aquí.")
    item = demo.inbox()["requests"][0]
    assert item["reason_label"] == "Pidió hablar con recepción"
    assert item["checkin"] is None and item["adults"] is None, "lo que falta queda explícito, no inventado"


def test_inverted_dates_get_a_clear_error_and_the_guest_does_not_repeat_the_adults(demo):
    demo.say("Consultar fechas")
    wrong = demo.say("22 al 20 de noviembre, 2 adultos")
    assert "tiene que ser después de la llegada" in wrong["reply"]
    fixed = demo.say("20 al 22 de noviembre")
    assert "adultos" not in fixed["reply"].lower(), "los 2 adultos ya estaban bien"
    assert fixed["quick_replies"] == ["Sin niños", "1 niño", "2 niños"]


def test_guest_can_correct_the_summary_before_sending(demo):
    demo.say("Quiero consultar del 20 al 22 de noviembre para 2 adultos")
    summary = demo.say("sin niños")
    assert "Revisa tu solicitud" in summary["reply"]
    assert "Disponible según lectura del PMS a las 15:00" in summary["reply"], "sello de hora de la lectura"
    assert "lectura preliminar" in summary["reply"] and "nada queda reservado" in summary["reply"]
    assert summary["quick_replies"] == ["Enviar a recepción", "Corregir fechas", "Corregir huéspedes"]
    corrected = demo.say("mejor 3 adultos")
    assert "3 adultos" in corrected["reply"] and "20 nov" in corrected["reply"]
    again = demo.say("Corregir fechas")
    assert "fechas correctas" in again["reply"]
    final = demo.say("21 al 23 de noviembre")
    assert "Llegada: sáb 21 nov" in final["reply"] and "3 adultos" in final["reply"]
    assert demo.inbox()["requests"] == [], "nada llega a recepción hasta que el huésped envía"


def test_canonical_case_end_to_end(demo):
    sent = canonical(demo)
    assert sent["messages"][-1]["body"].startswith("Solicitud enviada a recepción. Te responderán por aquí.")
    code = sent["request"]["code"]
    assert code.startswith("BDL-") and code in sent["reply"]
    assert "lectura del PMS es preliminar" in sent["reply"]

    inbox = demo.inbox()
    item = inbox["requests"][0]
    assert (item["code"], item["status"], item["status_label"]) == (code, "pendiente", "Pendiente de recepción")
    assert (item["checkin"], item["checkout"], item["nights"]) == ("2026-11-20", "2026-11-22", 2)
    assert (item["adults"], item["children"], item["channel_label"]) == (2, 0, "WhatsApp simulado")
    assert item["reservation_label"] == "Pendiente de confirmación"
    assert item["conversation_id"] == sent["conversation_id"], "la solicitud vive en el hilo del huésped"

    demo.clock.advance(10)
    taken = demo.sofia.post(f"/api/panel/requests/{item['id']}/take").json()
    assert (taken["status_label"], taken["assignee"]) == ("En atención", "Sofía")
    assert taken["commercial_at"] == item["commercial_at"], "asignar no reinicia el reloj"

    inventory = demo.sofia.post(f"/api/panel/requests/{item['id']}/inventory", json={}).json()
    assert inventory["ok"] is True and inventory["simulated"] is True and inventory["source"] == "PMS simulado"
    assert {offer["code"]: offer["available_units"] for offer in inventory["offers"]} == {
        "doble_con_jacuzzi": 2, "doble_sin_vista": 1}

    demo.clock.advance(15)
    answered = demo.sofia.post(f"/api/panel/requests/{item['id']}/reply", json={"body": REPLY}).json()["request"]
    assert answered["status_label"] == "Respondida"
    assert answered["reservation_label"] == "Pendiente de confirmación", "responder no confirma la reserva"
    assert answered["measurement"]["state"] == "cumplida"

    # «Recargar» ambas vistas: clientes nuevos leen el mismo caso desde el servidor.
    guest_again = TestClient(demo.app).get("/api/demo/conversation", params={"session_id": SESSION}).json()
    last = guest_again["messages"][-1]
    assert (last["role"], last["author"], last["body"]) == ("staff", "Sofía", REPLY)
    assert guest_again["conversation_id"] == sent["conversation_id"]
    assert all(message["role"] != "note" for message in guest_again["messages"]), "el huésped no lee notas"
    reloaded = demo.inbox(selected=item["id"])["selected"]
    assert (reloaded["status_label"], reloaded["assignee"]) == ("Respondida", "Sofía")
    assert any(message["role"] == "note" for message in reloaded["messages"]), "recepción ve la pre-información"
    assert demo.chatwoot.messages == [], "la demo nunca escribe a Chatwoot"


def test_the_bot_stays_silent_while_reception_owns_the_case(demo):
    canonical(demo)
    request_id = demo.inbox()["requests"][0]["id"]
    demo.sofia.post(f"/api/panel/requests/{request_id}/take")
    demo.sofia.post(f"/api/panel/requests/{request_id}/reply", json={"body": REPLY})
    follow_up = demo.say("Sí, quiero avanzar")
    assert [message["role"] for message in follow_up["messages"]] == ["guest"], "el bot no contesta"
    assert follow_up["mode"] == "human"
    assert demo.inbox()["requests"][0]["status_label"] == "En atención", "vuelve a pedir respuesta"


def test_closing_returns_the_thread_to_the_bot_and_a_new_query_is_a_new_request(demo):
    first = canonical(demo)["request"]["code"]
    request_id = demo.inbox()["requests"][0]["id"]
    demo.sofia.post(f"/api/panel/requests/{request_id}/take")
    assert demo.sofia.post(f"/api/panel/requests/{request_id}/close").json()["status_label"] == "Cerrada"
    again = demo.say("Hablar con recepción")
    assert again["request"]["code"] != first
    statuses = sorted(item["status"] for item in demo.inbox()["requests"])
    assert statuses == ["cerrada", "pendiente"]


def test_a_retried_guest_message_is_processed_once(demo):
    first = demo.say("Hablar con recepción", client_message_id="accion-00000001")
    retry = demo.say("Hablar con recepción", client_message_id="accion-00000001")
    assert retry["duplicate"] is True and retry["request"]["code"] == first["request"]["code"]
    guest_messages = [m for m in retry["messages"] if m["role"] == "guest"]
    assert len(guest_messages) == 1
    assert len(demo.inbox()["requests"]) == 1
    fresh = demo.say("¿Me confirman?", client_message_id="accion-00000002")
    assert fresh["duplicate"] is False, "una consulta nueva legítima sigue entrando"


def test_a_retried_staff_reply_is_sent_once(demo):
    demo.say("Hablar con recepción")
    request_id = demo.inbox()["requests"][0]["id"]
    demo.sofia.post(f"/api/panel/requests/{request_id}/take")
    body = {"body": REPLY, "client_id": "respuesta-000001"}
    first = demo.sofia.post(f"/api/panel/requests/{request_id}/reply", json=body).json()
    retry = demo.sofia.post(f"/api/panel/requests/{request_id}/reply", json=body).json()
    assert first["duplicate"] is False and retry["duplicate"] is True
    staff = [m for m in retry["request"]["messages"] if m["role"] == "staff"]
    assert len(staff) == 1


def test_another_person_cannot_take_over_a_taken_request(demo):
    demo.say("Hablar con recepción")
    request_id = demo.inbox()["requests"][0]["id"]
    assert demo.sofia.post(f"/api/panel/requests/{request_id}/take").status_code == 200
    assert demo.sofia.post(f"/api/panel/requests/{request_id}/take").status_code == 200, "idempotente"
    tomas = TestClient(demo.app)
    tomas.post("/api/demo/session", json={"name": "Tomás"})
    conflict = tomas.post(f"/api/panel/requests/{request_id}/take")
    assert conflict.status_code == 409 and conflict.json()["detail"] == "Ya la tomó Sofía"
    assert tomas.post(f"/api/panel/requests/{request_id}/reply", json={"body": "hola"}).status_code == 409
    assert demo.sofia.post("/api/demo/session", json={"name": "<script>"}).status_code == 422


def test_off_shift_request_is_saved_with_the_next_opening_and_kept_out_of_the_target(demo):
    sent = canonical(demo, shift="closed")
    closing = sent["messages"][-1]["body"]
    assert "Recepción atiende de 08:00 a 22:00" in closing
    assert "desde las 08:00 del lunes 9 de noviembre" in closing
    item = demo.inbox()["requests"][0]
    assert item["in_shift"] is False and item["measurement"]["state"] == "fuera_de_turno"
    state = store.get_state(demo.db, sent["conversation_id"])
    assert state.sla_started_at is None, "fuera de turno no corre el reloj de 180 s"
    kinds = [event["kind"] for event in demo.inbox(selected=item["id"])["selected"]["events"]]
    assert "night_capture" in kinds


def test_the_clock_starts_when_the_commercial_query_enters_and_an_ack_does_not_stop_it(demo):
    demo.say("¿Dónde queda el hotel?")
    entered = demo.say("Consultar fechas")
    demo.say("20–22 nov · 2 adultos")
    demo.say("Sin niños")
    demo.say("Enviar a recepción")
    item = demo.inbox()["requests"][0]
    started_at = store.get_state(demo.db, entered["conversation_id"]).sla_started_at
    assert item["commercial_at"] == started_at
    assert item["commercial_at"] < item["created_at"], "la medición parte antes de capturar los datos"

    demo.sofia.post(f"/api/panel/requests/{item['id']}/take")
    ack = demo.sofia.post(f"/api/panel/requests/{item['id']}/reply", json={"body": "Ya te reviso", "kind": "ack"})
    assert ack.json()["request"]["status_label"] == "En atención"
    assert ack.json()["request"]["measurement"]["state"] == "en_curso", "un acuse no es la respuesta"
    demo.clock.advance(20)
    answered = demo.sofia.post(f"/api/panel/requests/{item['id']}/reply", json={"body": REPLY}).json()["request"]
    measurement = answered["measurement"]
    assert measurement["elapsed_s"] == int(answered["first_answer_at"] - item["commercial_at"])
    kinds = [event["kind"] for event in answered["events"]]
    assert kinds.index("human_ack") < kinds.index("human_first_reply")
    assert kinds.count("human_first_reply") == 1


async def test_a_missed_target_is_recorded_as_a_breach_in_the_demo_thread(demo):
    demo.say("Hablar con recepción")
    item = demo.inbox()["requests"][0]
    demo.clock.advance(200)
    await demo.app.state.sla.tick()
    detail = demo.inbox(selected=item["id"])["selected"]
    assert detail["measurement"]["state"] == "vencida" and detail["breached_at"] is not None
    assert "sla_breached" in [event["kind"] for event in detail["events"]]
    assert any(m["role"] == "note" and "SLA vencido" in m["body"] for m in detail["messages"])
    assert demo.chatwoot.messages == [] and demo.chatwoot.labels == {}, "el aviso se queda en la demo"


def test_a_pms_outage_never_reports_availability_and_stays_with_reception(demo, harness):
    harness.pms.down = True
    demo.say("Quiero consultar del 10 al 12 de diciembre para 2 adultos")
    summary = demo.say("Sin niños")
    assert "No pude consultar el sistema de reservas" in summary["reply"]
    assert "Disponible" not in summary["reply"], "sin lectura no se promete cupo"
    sent = demo.say("Enviar a recepción")
    assert "Disponibilidad por verificar" in sent["reply"]
    item = demo.inbox()["requests"][0]
    assert item["reason_label"] == "Cupos sin verificar (PMS sin respuesta)"
    demo.sofia.post(f"/api/panel/requests/{item['id']}/take")
    down = demo.sofia.post(f"/api/panel/requests/{item['id']}/inventory", json={}).json()
    assert down["ok"] is False and down["reason"] == "el PMS no respondió"
    harness.pms.down = False
    simulated = demo.sofia.post(f"/api/panel/requests/{item['id']}/inventory", json={"simulate_down": True}).json()
    assert simulated["ok"] is False and "caída simulada" in simulated["reason"]
    notes = [m["body"] for m in simulated["request"]["messages"] if m["role"] == "note"]
    assert any("Cupo desconocido: no informar disponibilidad" in note for note in notes)


def test_guest_sessions_are_isolated(demo):
    canonical(demo)
    other = demo.say("¿Dónde queda el hotel?", session=OTHER)
    assert other["request"] is None and other["handled_by"] == "asistente"
    bodies = [m["body"] for m in other["messages"]]
    assert REPLY not in bodies and "Sin niños" not in bodies


def test_faq_latency_is_reported_per_question(demo):
    demo.say("¿Dónde queda el hotel?")
    demo.say("¿Tienen piscina?")
    demo.say("Hablar con recepción")
    detail = demo.inbox(selected=demo.inbox()["requests"][0]["id"])["selected"]
    assert detail["faq"] == [{"faq_id": "ubicacion", "latency_s": 0.0, "met": True},
                             {"faq_id": "piscina", "latency_s": 0.0, "met": True}]
