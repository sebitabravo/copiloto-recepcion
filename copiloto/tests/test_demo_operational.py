"""Caso operativo aislado de la demo: huésped escribe, recepción lee y responde.

Reglas que se fijan aquí:
1. Un turno de demo crea su propia conversación marcada como demo y devuelve su id.
2. La sesión de demo nunca lee conversaciones operativas, y el personal nunca recibe las de demo.
3. El detalle de una conversación de demo incluye la transcripción.
4. Solo se puede responder una conversación de demo desde una sesión de demo.
5. El huésped ve la respuesta de la persona al volver a consultar su conversación.
6. Dos sesiones de demo no se ven entre sí.
"""

from dataclasses import replace

from conftest import FakeChatwoot, FakeLlm, call, say
from copiloto.ai.agent import Agent
from copiloto.app import create_app
from fastapi.testclient import TestClient

from copiloto import store

SESSION = "demo-operativa-0123456789"
OTHER = "demo-operativa-9876543210"
OPERATIONAL_ID = 7


def client_for(settings, harness, llm=None):
    agent = Agent(llm, harness.hotel, harness.pms, settings, lambda: harness.clock()) if llm else None
    app = create_app(
        # Sin modelo guionado, la demo corre su motor por defecto: el flujo guiado.
        settings if llm else replace(settings, demo_ai=False),
        chatwoot=FakeChatwoot(),
        pms=harness.pms,
        clock=harness.clock,
        run_workers=False,
        db=harness.db,
        llm_agent=agent,
    )
    return TestClient(app)


def demo_client(settings, harness, llm=None):
    client = client_for(settings, harness, llm)
    assert client.post("/api/demo/session").status_code == 204
    return client


def chat(client, message, session=SESSION):
    return client.post("/api/demo/chat", json={"session_id": session, "message": message})


def seed_operational(harness):
    """Una conversación real ya derivada: la sesión de demo no debe verla nunca."""
    state = store.get_state(harness.db, OPERATIONAL_ID)
    state.step = "handed_off"
    state.contact_name = "Huésped operativo"
    store.save_state(harness.db, state, harness.clock())
    store.start_sla(harness.db, OPERATIONAL_ID, harness.clock())


def test_demo_turn_returns_its_own_isolated_conversation(ai_settings, harness):
    client = demo_client(ai_settings, harness)
    body = chat(client, "¿Cómo llego al hotel?").json()

    conversation_id = body["conversation_id"]
    assert isinstance(conversation_id, int)
    assert conversation_id < 0, "las conversaciones de demo viven en su propio espacio"
    row = harness.db.execute(
        "SELECT conversation_id, source FROM conversation_state WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()
    assert row is not None and row["source"] == "demo"
    assert chat(client, "¿Tienen piscina?").json()["conversation_id"] == conversation_id


def test_demo_queue_never_exposes_operational_conversations(ai_settings, harness):
    seed_operational(harness)
    staff = client_for(ai_settings, harness)
    staff_headers = {"X-Panel-Token": ai_settings.panel_token}
    staff_queue = staff.get("/api/panel/queue", headers=staff_headers).json()["conversations"]
    assert [item["conversation_id"] for item in staff_queue] == [OPERATIONAL_ID]

    demo = demo_client(ai_settings, harness)
    assert demo.get("/api/panel/queue").json()["conversations"] == []

    conversation_id = chat(demo, "¿Cómo llego al hotel?").json()["conversation_id"]
    demo_ids = [item["conversation_id"] for item in demo.get("/api/panel/queue").json()["conversations"]]
    assert demo_ids == [conversation_id]
    staff_queue = staff.get("/api/panel/queue", headers=staff_headers).json()["conversations"]
    staff_ids = [item["conversation_id"] for item in staff_queue]
    assert staff_ids == [OPERATIONAL_ID], "el personal no recibe conversaciones de demostración"


def test_handoff_marks_the_demo_conversation_as_waiting_for_a_person(ai_settings, harness):
    llm = FakeLlm([
        call("handoff_to_human", reason="Quiere hablar con recepción"),
        say("Te derivo a una persona del equipo."),
    ])
    client = demo_client(ai_settings, harness, llm)
    body = chat(client, "Quiero hablar con una persona").json()
    assert any(event["type"] == "handoff" for event in body["events"])

    queue = client.get("/api/panel/queue").json()["conversations"]
    row = next(item for item in queue if item["conversation_id"] == body["conversation_id"])
    assert row["step"] == "handed_off"
    assert row["needs_human"] is True


def test_demo_detail_returns_the_transcript(ai_settings, harness):
    client = demo_client(ai_settings, harness)
    body = chat(client, "¿Dónde queda la hostería?").json()
    conversation_id = body["conversation_id"]

    snapshot = client.get(f"/api/panel/{conversation_id}").json()
    roles = [message["role"] for message in snapshot["messages"]]
    assert roles[0] == "guest" and roles[-1] == "assistant"
    assert snapshot["messages"][0]["body"] == "¿Dónde queda la hostería?"
    assert snapshot["messages"][-1]["body"] in body["reply"]


def demo_request(client, session=SESSION):
    conversation_id = chat(client, "Hablar con recepción", session=session).json()["conversation_id"]
    request_id = next(item["id"] for item in client.get("/api/panel/requests").json()["requests"]
                      if item["conversation_id"] == conversation_id)
    return conversation_id, request_id


def test_reply_is_only_allowed_on_demo_conversations(ai_settings, harness):
    demo = demo_client(ai_settings, harness)
    _, request_id = demo_request(demo)
    staff = client_for(ai_settings, harness)
    headers = {"X-Panel-Token": ai_settings.panel_token}
    blocked = staff.post(f"/api/panel/requests/{request_id}/reply", json={"body": "Hola"}, headers=headers)
    assert blocked.status_code == 404, "el personal real no ve ni escribe solicitudes de demo"

    assert demo.post(f"/api/panel/requests/{request_id}/take").status_code == 200
    sent = demo.post(f"/api/panel/requests/{request_id}/reply", json={"body": "  Soy Camila, te ayudo.  "})
    assert sent.status_code == 200
    assert sent.json()["message"]["role"] == "staff"
    assert sent.json()["message"]["body"] == "Soy Camila, te ayudo."
    assert demo.post(f"/api/panel/requests/{request_id}/reply", json={"body": "   "}).status_code == 400


def test_guest_sees_the_staff_reply_when_asking_again(ai_settings, harness):
    demo = demo_client(ai_settings, harness)
    conversation_id, request_id = demo_request(demo)
    demo.post(f"/api/panel/requests/{request_id}/take")
    demo.post(f"/api/panel/requests/{request_id}/reply", json={"body": "Soy Camila de recepción."})

    seen = demo.get("/api/demo/conversation", params={"session_id": SESSION}).json()
    assert seen["conversation_id"] == conversation_id
    assert [message["role"] for message in seen["messages"]][-1] == "staff"
    assert seen["messages"][-1]["body"] == "Soy Camila de recepción."
    assert seen["messages"][-1]["author"] == "Recepción (demo)"
    assert seen["handled_by"] == "recepcion"


def test_demo_sessions_only_ever_see_the_demo_space(ai_settings, harness):
    seed_operational(harness)
    first = demo_client(ai_settings, harness)
    first_id = chat(first, "¿Tienen piscina?", session=SESSION).json()["conversation_id"]

    # Otra sesión de demo comparte el espacio sintético (como una cola real), pero nunca la operación.
    second = demo_client(ai_settings, harness)
    ids = [item["conversation_id"] for item in second.get("/api/panel/queue").json()["conversations"]]
    assert ids == [first_id] and OPERATIONAL_ID not in ids
    assert second.get(f"/api/panel/{first_id}").status_code == 200
    assert second.get(f"/api/panel/{OPERATIONAL_ID}").status_code == 404
    assert second.post(f"/api/panel/requests/{OPERATIONAL_ID}/reply", json={"body": "Hola"}).status_code == 404

    second_id = chat(second, "¿Cómo llego?", session=OTHER).json()["conversation_id"]
    assert second_id != first_id, "cada sesión de huésped escribe su propia conversación"
