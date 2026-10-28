"""Cola de recepción: sin ella, una persona solo puede abrir una conversación si ya sabe su id."""

import time

from copiloto import store
from copiloto.app import create_app
from fastapi.testclient import TestClient


def make_client(settings, harness):
    app = create_app(settings, chatwoot=harness.chatwoot, pms=harness.pms, clock=time.time, run_workers=False,
                     db=harness.db)
    return TestClient(app)


def test_queue_puts_running_timers_first_and_counts_the_wait(harness):
    now = harness.clock()

    handed_off = store.get_state(harness.db, 11)
    handed_off.step = "handed_off"
    store.save_state(harness.db, handed_off, now)
    store.start_sla(harness.db, 11, now - 200)

    in_progress = store.get_state(harness.db, 12)
    in_progress.step = "menu"
    store.save_state(harness.db, in_progress, now)
    store.start_sla(harness.db, 12, now - 30)

    idle = store.get_state(harness.db, 13)
    store.save_state(harness.db, idle, now)

    queue = store.list_conversations(harness.db, now)

    assert [item["conversation_id"] for item in queue] == [11, 12, 13]
    assert queue[0]["waiting_s"] >= 200
    assert queue[0]["needs_human"] is True
    assert queue[2]["waiting_s"] is None


def test_queue_requires_the_panel_token(settings, harness):
    client = make_client(settings, harness)

    assert client.get("/api/panel/queue").status_code == 401

    response = client.get("/api/panel/queue", headers={"X-Panel-Token": "panel-secret"})
    assert response.status_code == 200
    body = response.json()
    assert "conversations" in body and body["red_s"] > 0
