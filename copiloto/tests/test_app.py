import hashlib
import hmac
import json
import time

from copiloto.app import create_app
from fastapi.testclient import TestClient


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
    assert client.post("/webhooks/pms", json=payload).status_code == 401
    assert client.post("/webhooks/pms", json=payload, headers={"X-Events-Token": "nope"}).status_code == 401
    ok = {"X-Events-Token": settings.pms_events_secret}
    assert client.post("/webhooks/pms", json=payload, headers=ok).status_code == 200
    assert client.post("/webhooks/pms", json=payload, headers=ok).status_code == 200
    assert len(harness.events("booking_confirmed")) == 1, "un reintento del PMS no duplica la conversión"
    notes = [n for n in harness.chatwoot.notes(5) if "Reserva #7" in n]
    assert len(notes) == 1


def test_panel_endpoints_and_static_pages(settings, harness):
    client = make_client(settings, harness)
    assert "Pre-información lista" in client.get("/panel").text
    assert client.get("/api/panel/5").status_code == 401
    assert client.get("/api/panel/5", headers={"X-Panel-Token": "otro"}).status_code == 401
    data = client.get("/api/panel/5", headers={"X-Panel-Token": settings.panel_token}).json()
    assert data["sla"]["red_s"] == 180 and data["prebooking"] is None
    assert "Aviso de privacidad" in client.get("/privacidad").text
    assert client.get("/metricas").status_code == 200
    assert "cost_per_query_clp" in client.get("/metricas/data.json?days=7").json()
    assert client.get("/health").json() == {"status": "ok"}


def test_panel_and_pms_webhook_reject_everything_without_configured_secrets(settings, harness):
    from dataclasses import replace
    client = make_client(replace(settings, panel_token="", pms_events_secret=""), harness)
    assert client.get("/api/panel/5", headers={"X-Panel-Token": ""}).status_code == 401
    assert client.post("/webhooks/pms", json={"kind": "booking_confirmed", "booking_id": 1},
                       headers={"X-Events-Token": ""}).status_code == 401


def test_webhook_rejects_oversized_bodies_before_authenticating(settings, harness):
    client = make_client(settings, harness)
    assert client.post("/webhooks/chatwoot", content=b"x" * 300_000).status_code == 413
    assert client.post("/webhooks/pms", content=b"x" * 300_000,
                       headers={"X-Events-Token": settings.pms_events_secret}).status_code == 413


def test_non_ascii_signature_is_a_401_not_a_500(settings, harness):
    client = make_client(settings, harness)
    body = json.dumps(message()).encode()
    headers = {"X-Chatwoot-Timestamp": str(int(time.time())), "X-Chatwoot-Signature": "sha256=ñandú".encode("latin-1")}
    assert client.post("/webhooks/chatwoot", content=body, headers=headers).status_code == 401


def test_readiness_probe_checks_the_database(settings, harness):
    client = make_client(settings, harness)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/health?probe=readiness").json() == {"status": "ok"}
    harness.db.close()
    assert client.get("/health?probe=readiness").status_code == 503
    assert client.get("/health?probe=otra").status_code == 422


def test_security_headers_allow_only_chatwoot_to_frame_the_panel(settings, harness):
    client = make_client(settings, harness)
    panel = client.get("/panel")
    assert panel.headers["x-content-type-options"] == "nosniff"
    assert panel.headers["referrer-policy"] == "no-referrer"
    assert f"frame-ancestors {settings.chatwoot_public_url}" in panel.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in client.get("/privacidad").headers["content-security-policy"]


def test_public_reads_are_rate_limited_but_webhooks_are_not(settings, harness):
    from dataclasses import replace
    client = make_client(replace(settings, public_rate_per_min=3), harness)
    codes = [client.get("/privacidad").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert client.get("/privacidad").headers["retry-after"].isdigit()
    body = json.dumps(message()).encode()
    for index in range(6):
        response = client.post("/webhooks/chatwoot", content=body, headers=signed(settings.webhook_secret, body))
        assert response.status_code == 200, index


def test_signed_but_malformed_json_is_a_400(settings, harness):
    client = make_client(settings, harness)
    body = b"{no es json"
    assert client.post("/webhooks/chatwoot", content=body,
                       headers=signed(settings.webhook_secret, body)).status_code == 400
    ok = {"X-Events-Token": settings.pms_events_secret}
    assert client.post("/webhooks/pms", content=b"[", headers=ok).status_code == 422
    assert client.post("/webhooks/pms", json={"kind": "booking_confirmed", "booking_id": "abc"},
                       headers=ok).status_code == 422
