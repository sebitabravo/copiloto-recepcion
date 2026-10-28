"""Acceso del personal: el panel muestra datos de huéspedes, así que no puede quedar abierto.

La sesión es una cookie firmada; el token del panel se mantiene para la app incrustada en Chatwoot.
"""

import time

from copiloto import store
from copiloto.app import create_app
from fastapi.testclient import TestClient


def make_client(settings, harness):
    app = create_app(settings, chatwoot=harness.chatwoot, pms=harness.pms, clock=time.time, run_workers=False,
                     db=harness.db)
    return TestClient(app)


def login(client, name="Camila", password="panel-secret"):
    return client.post("/api/panel/login", json={"name": name, "password": password})


def test_panel_requires_a_session(settings, harness):
    client = make_client(settings, harness)
    assert client.get("/api/panel/session").status_code == 401
    assert client.get("/api/panel/queue").status_code == 401


def test_wrong_password_is_rejected(settings, harness):
    client = make_client(settings, harness)
    assert login(client, password="otra").status_code == 401


def test_login_opens_the_queue_and_logout_closes_it(settings, harness):
    client = make_client(settings, harness)

    response = login(client)
    assert response.status_code == 200 and response.json()["name"] == "Camila"
    assert client.get("/api/panel/queue").status_code == 200

    assert client.post("/api/panel/logout").status_code == 200
    assert client.get("/api/panel/queue").status_code == 401


def test_the_token_still_works_for_the_embedded_app(settings, harness):
    client = make_client(settings, harness)
    response = client.get("/api/panel/queue", headers={"X-Panel-Token": "panel-secret"})
    assert response.status_code == 200


def test_shift_summary_counts_what_happened(settings, harness):
    from copiloto.events import record_event

    now = harness.clock()
    record_event(harness.db, 21, "inbound", now - 60, {"greeting": False})
    record_event(harness.db, 21, "faq_answered", now - 50, {"faq_id": "piscina", "inbound_ts": now - 60})
    record_event(harness.db, 21, "handoff", now - 40, {"reason": "commercial"})

    summary = store.shift_summary(harness.db, now - 3600, now)
    assert summary["received"] == 1
    assert summary["faq_answered"] == 1
    assert summary["handoffs"] == 1

    client = make_client(settings, harness)
    login(client)
    response = client.get("/api/panel/shift")
    assert response.status_code == 200
    assert response.json()["hours"] == 12


def test_a_note_needs_a_session_and_is_attached_to_the_conversation(settings, harness):
    client = make_client(settings, harness)

    assert client.post("/api/panel/7/note", json={"body": "sin sesión"}).status_code == 401

    login(client)
    created = client.post("/api/panel/7/note", json={"body": "  pidió cuna,   confirmar antes de las 18  "})
    assert created.status_code == 200
    assert created.json()["body"] == "pidió cuna, confirmar antes de las 18"
    assert created.json()["author"] == "Camila"

    detail = client.get("/api/panel/7", headers={"X-Panel-Token": "panel-secret"}).json()
    assert [note["body"] for note in detail["notes"]] == ["pidió cuna, confirmar antes de las 18"]

    assert client.post("/api/panel/7/note", json={"body": "   "}).status_code == 400
