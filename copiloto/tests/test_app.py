import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from copiloto.app import create_app


def signed(secret, body, ts=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = "sha256=" + hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Chatwoot-Timestamp": ts, "X-Chatwoot-Signature": sig, "Content-Type": "application/json"}


def make_client(settings, harness):
    app = create_app(settings, chatwoot=harness.chatwoot, pms=harness.pms, clock=time.time, run_workers=False,
                     db=harness.db)
    return TestClient(app)


def message(content="¿tienen piscina?", message_id=1):
    return {"event": "message_created", "id": message_id, "content": content, "message_type": "incoming",
            "private": False, "sender": {"id": 3, "name": "Ana", "type": "contact"},
            "conversation": {"id": 5, "status": "pending", "channel": "Channel::WebWidget"}}


def test_webhook_rejects_bad_signature(settings, harness):
    client = make_client(settings, harness)
    body = json.dumps(message()).encode()
    headers = signed("otro-secreto", body)
    assert client.post("/webhooks/chatwoot", content=body, headers=headers).status_code == 401
    assert client.post("/webhooks/chatwoot", content=body).status_code == 401


def test_webhook_rejects_stale_timestamp(settings, harness):
    client = make_client(settings, harness)
    body = json.dumps(message()).encode()
    headers = signed(settings.webhook_secret, body, ts=time.time() - 3600)
    assert client.post("/webhooks/chatwoot", content=body, headers=headers).status_code == 401


def test_signed_webhook_is_processed(settings, harness):
    client = make_client(settings, harness)
    body = json.dumps(message()).encode()
    response = client.post("/webhooks/chatwoot", content=body, headers=signed(settings.webhook_secret, body))
    assert response.status_code == 200
    assert any("piscina temperada" in t for t in harness.chatwoot.guest_texts(5))


def test_pms_webhook_requires_secret_and_records_event(settings, harness):
    client = make_client(settings, harness)
    payload = {"kind": "booking_confirmed", "conversation_id": 5, "booking_id": 7}
    assert client.post("/webhooks/pms?secret=nope", json=payload).status_code == 401
    assert client.post(f"/webhooks/pms?secret={settings.webhook_secret}", json=payload).status_code == 200
    assert len(harness.events("booking_confirmed")) == 1


def test_panel_endpoints_and_static_pages(settings, harness):
    client = make_client(settings, harness)
    assert "Pre-información lista" in client.get("/panel").text
    data = client.get("/api/panel/5").json()
    assert data["sla"]["red_s"] == 180 and data["prebooking"] is None
    assert "Aviso de privacidad" in client.get("/privacidad").text
    assert client.get("/metricas").status_code == 200
    assert "cost_per_query_clp" in client.get("/metricas/data.json?days=7").json()
    assert client.get("/health").json() == {"status": "ok"}
