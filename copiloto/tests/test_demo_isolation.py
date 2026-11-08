"""Guardas del espacio aislado de la demo, fijadas como regresión.

Probes propuestos por la verificación independiente (T14) sobre los commits 273335c y 35e962f:
el personal no toca las conversaciones de demo, una respuesta se valida y nunca cruza de espacio,
el reinicio borra solo lo de demo y la migración deja las bases existentes como operativas.
"""

import sqlite3
from dataclasses import replace

from conftest import FakeChatwoot, new_run
from copiloto.app import create_app
from fastapi.testclient import TestClient

from copiloto import events, store

SESSION = "demo-guardas-0123456789"
OPERATIONAL_ID = 7


def client_for(settings, harness):
    # El aislamiento se prueba con el motor por defecto de la demo (flujo guiado, sin modelo).
    app = create_app(
        replace(settings, demo_ai=False),
        chatwoot=FakeChatwoot(),
        pms=harness.pms,
        demo_pms=harness.pms,
        clock=harness.clock,
        run_workers=False,
        db=harness.db,
    )
    return TestClient(app)


def demo_client(settings, harness):
    """Huésped y recepción de una misma corrida (la corrida la emite el servidor)."""
    client = client_for(settings, harness)
    client.run = new_run(client)
    assert client.post("/api/demo/session", json={"run": client.run}).status_code == 204
    return client


def demo_request(demo, session=SESSION):
    """El huésped pide recepción: queda una solicitud en la bandeja de la demo. Devuelve (conversación, id)."""
    conversation_id = demo.post(
        "/api/demo/chat", json={"session_id": session, "message": "Hablar con recepción", "run": demo.run}
    ).json()["conversation_id"]
    request_id = next(item["id"] for item in demo.get("/api/panel/requests").json()["requests"]
                      if item["conversation_id"] == conversation_id)
    return conversation_id, request_id


def seed_operational(harness):
    state = store.get_state(harness.db, OPERATIONAL_ID)
    state.step = "handed_off"
    state.contact_name = "Huésped operativo"
    store.save_state(harness.db, state, harness.clock())
    store.start_sla(harness.db, OPERATIONAL_ID, harness.clock())


def operational_row(harness):
    return dict(
        harness.db.execute(
            "SELECT * FROM conversation_state WHERE conversation_id = ?", (OPERATIONAL_ID,)
        ).fetchone()
    )


def test_staff_identity_cannot_read_or_note_demo_conversations(ai_settings, harness):
    demo = demo_client(ai_settings, harness)
    conversation_id, request_id = demo_request(demo)

    staff = client_for(ai_settings, harness)
    headers = {"X-Panel-Token": ai_settings.panel_token}
    assert staff.get(f"/api/panel/{conversation_id}", headers=headers).status_code == 404
    assert staff.post(f"/api/panel/{conversation_id}/note", json={"body": "nota"}, headers=headers).status_code == 404
    assert staff.get("/api/panel/requests", headers=headers).json()["requests"] == []
    for action in ("take", "reply", "close", "inventory"):
        response = staff.post(f"/api/panel/requests/{request_id}/{action}", json={"body": "hola"}, headers=headers)
        assert response.status_code == 404, action


def test_reply_validates_body_and_requires_identity(ai_settings, harness):
    demo = demo_client(ai_settings, harness)
    _, request_id = demo_request(demo)
    reply = f"/api/panel/requests/{request_id}/reply"
    untaken = demo.post(reply, json={"body": "hola"})
    assert untaken.status_code == 409 and untaken.json()["detail"] == "Toma la solicitud antes de responder"
    assert demo.post(f"/api/panel/requests/{request_id}/take").status_code == 200

    detail = "La respuesta debe tener entre 1 y 1000 caracteres"
    for body in ("", "   ", "x" * 1001):
        response = demo.post(reply, json={"body": body})
        assert response.status_code == 400 and response.json()["detail"] == detail, repr(body[:10])
    assert demo.post(reply, json={"body": "x", "kind": "otro"}).status_code == 422
    assert demo.post(reply, json={"body": "x", "client_id": "corto"}).status_code == 422
    assert demo.post(reply, json={"body": "x" * 1000}).status_code == 200

    anonymous = client_for(ai_settings, harness)
    assert anonymous.post(reply, json={"body": "hola"}).status_code == 401
    bad = demo.post(reply, content="no-json", headers={"content-type": "application/json"})
    assert bad.status_code == 400 and bad.json()["detail"] == "JSON inválido"


def test_unknown_session_polls_nothing_and_never_another_conversation(ai_settings, harness):
    demo = demo_client(ai_settings, harness)
    first = demo.post("/api/demo/chat", json={"session_id": SESSION, "message": "Hola",
                                              "run": demo.run}).json()["conversation_id"]

    unseen = demo.get("/api/demo/conversation", params={"session_id": "sesion-inexistente-01"})
    assert unseen.json() == {"conversation_id": None, "step": None, "messages": [], "request": None,
                             "handled_by": "asistente", "quick_replies": []}

    demo.post("/api/demo/chat", json={"session_id": "demo-guardas-9876543210", "message": "Otra", "run": demo.run})
    seen = demo.get("/api/demo/conversation", params={"session_id": SESSION}).json()
    assert seen["conversation_id"] == first
    assert all(message["role"] in {"guest", "assistant", "staff"} for message in seen["messages"])
    assert seen["messages"][0]["body"] == "Hola", "nunca aparece el mensaje de otra sesión"


def test_reset_clears_only_the_demo_space(ai_settings, harness):
    seed_operational(harness)
    before = operational_row(harness)
    demo = demo_client(ai_settings, harness)
    conversation_id = demo.post(
        "/api/demo/chat", json={"session_id": SESSION, "message": "Hola", "run": demo.run}
    ).json()["conversation_id"]
    demo.post(f"/api/panel/{conversation_id}/note", json={"body": "nota de demo"})

    assert demo.post("/api/demo/reset", json={"session_id": SESSION}).status_code == 200

    db = harness.db
    assert db.execute("SELECT 1 FROM demo_messages WHERE conversation_id = ?", (conversation_id,)).fetchone() is None
    def gone(sql):
        return db.execute(sql, (conversation_id,)).fetchone() is None

    assert db.execute(
        "SELECT 1 FROM demo_conversations WHERE session_id = ?", (SESSION,)
    ).fetchone() is None
    assert gone("SELECT 1 FROM staff_notes WHERE conversation_id = ?")
    assert gone("SELECT 1 FROM conversation_state WHERE conversation_id = ?")
    assert operational_row(harness) == before, "reiniciar la demo no toca la operación real"
    assert demo.get("/api/panel/queue").json()["conversations"] == []


def test_rejected_write_leaves_the_operational_row_untouched(ai_settings, harness):
    seed_operational(harness)
    with store.transaction(harness.db):
        real = store.create_request(
            harness.db, OPERATIONAL_ID, prefix="SOL", source=store.OPERATIONAL_SOURCE, channel="Channel::WebWidget",
            reason="commercial", in_shift=True, commercial_at=harness.clock(), now=harness.clock(), data={},
        )
    before = operational_row(harness)
    demo = demo_client(ai_settings, harness)
    for action in ("take", "reply", "close"):
        assert demo.post(f"/api/panel/requests/{real['id']}/{action}", json={"body": "x"}).status_code == 404
    assert demo.get(f"/api/panel/requests/{real['id']}").status_code == 404
    assert operational_row(harness) == before
    assert dict(store.get_request_row(harness.db, real["id"])) == dict(real)
    assert demo.get(f"/api/panel/{OPERATIONAL_ID}").status_code == 404


def test_operational_detail_has_no_demo_transcript(ai_settings, harness):
    seed_operational(harness)
    staff = client_for(ai_settings, harness)
    body = staff.get(f"/api/panel/{OPERATIONAL_ID}", headers={"X-Panel-Token": ai_settings.panel_token}).json()
    assert body["messages"] == []
    assert body["conversation_id"] == OPERATIONAL_ID


def test_panel_surfaces_still_require_identity(ai_settings, harness):
    anonymous = client_for(ai_settings, harness)
    for path in ("/api/panel/queue", "/api/panel/shift", "/metricas", "/metricas/data.json"):
        assert anonymous.get(path).status_code == 401, path


def test_migration_marks_existing_rows_as_operational(tmp_path):
    """Una base anterior no tiene `source`: al migrar, sus conversaciones siguen siendo de la operación."""
    path = tmp_path / "vieja.sqlite"
    connection = sqlite3.connect(path)
    connection.executescript(
        """CREATE TABLE conversation_state (
               conversation_id INTEGER PRIMARY KEY,
               step TEXT NOT NULL DEFAULT 'start',
               data TEXT NOT NULL DEFAULT '{}',
               contact_name TEXT,
               contact_ref TEXT,
               sla_started_at REAL,
               sla_stopped_at REAL,
               sla_amber_done INTEGER NOT NULL DEFAULT 0,
               sla_red_done INTEGER NOT NULL DEFAULT 0,
               updated_at REAL NOT NULL
           );"""
    )
    connection.execute(
        "INSERT INTO conversation_state(conversation_id, updated_at) VALUES (5, 1.0)"
    )
    connection.commit()
    connection.close()

    migrated = events.connect(str(path))
    events.init_db(migrated)
    row = migrated.execute("SELECT source FROM conversation_state WHERE conversation_id = 5").fetchone()
    assert row["source"] == "chatwoot"
    assert store.conversation_source(migrated, 5) == store.OPERATIONAL_SOURCE
    assert store.list_conversations(migrated, 10.0, scope=store.DEMO_SOURCE) == []
    assert [item["conversation_id"] for item in store.list_conversations(migrated, 10.0, scope="operational")] == [5]
    migrated.close()


def test_demo_reply_never_reaches_chatwoot_or_the_pms(ai_settings, harness):
    chatwoot, pms = FakeChatwoot(), harness.pms
    app = create_app(
        replace(ai_settings, demo_ai=False),
        chatwoot=chatwoot,
        pms=pms,
        demo_pms=pms,
        clock=harness.clock,
        run_workers=False,
        db=harness.db,
    )
    client = TestClient(app)
    client.run = new_run(client)
    assert client.post("/api/demo/session", json={"run": client.run}).status_code == 204
    _, request_id = demo_request(client)
    assert client.post(f"/api/panel/requests/{request_id}/take").status_code == 200
    assert client.post(f"/api/panel/requests/{request_id}/reply", json={"body": "Te espero"}).status_code == 200
    assert client.post(f"/api/panel/requests/{request_id}/inventory", json={}).status_code == 409, "sin fechas"
    # Todo el recorrido (bot guiado, traspaso, respuesta) quedó en el espacio de la demo.
    assert chatwoot.messages == [] and chatwoot.labels == {} and chatwoot.assigned == [] and chatwoot.statuses == {}
    assert pms.bookings == [] and pms.calls == 0
