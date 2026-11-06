"""Acceso del personal: el panel muestra datos de huéspedes, así que no puede quedar abierto.

La sesión es una cookie firmada; el token del panel se mantiene para la app incrustada en Chatwoot.
"""

import base64
import hashlib
import hmac
import json
import time
from dataclasses import replace

import pytest
from copiloto.app import create_app
from fastapi.testclient import TestClient

from copiloto import store


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


def signed_cookie(data, key):
    payload = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()
    return payload + "." + hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def test_empty_signing_key_never_authenticates_even_a_signed_cookie(settings, harness):
    client = make_client(replace(settings, panel_token=""), harness)
    client.cookies.set("panel_session", signed_cookie({"n": "intruder", "e": 9999999999}, ""))
    for path in ("/api/panel/session", "/api/panel/queue", "/api/panel/shift", "/api/panel/7"):
        assert client.get(path).status_code == 401
    assert login(client, password="").status_code == 401
    assert client.post("/api/panel/7/note", json={"body": "denied"}).status_code == 401
    assert store.list_notes(harness.db, 7) == []


@pytest.mark.parametrize("data", [[], None, "staff", 42, {"n": [], "e": 9999999999},
                                       {"n": "staff", "e": "9999999999"},
                                       {"n": "staff", "e": True}, {"n": "staff", "e": None}])
def test_malformed_signed_cookie_types_fail_closed(settings, harness, data):
    client = make_client(settings, harness)
    client.cookies.set("panel_session", signed_cookie(data, settings.panel_token))
    assert client.get("/api/panel/session").status_code == 401
    assert client.get("/api/panel/queue").status_code == 401


@pytest.mark.parametrize("public_url", ["https://hotel.example", "http://localhost:8100", "http://127.0.0.1:8100"])
def test_cookie_transport_flags_preserve_https_and_local_http(settings, harness, public_url):
    strong = replace(settings, env="production", public_url=public_url, webhook_secret="w" * 32,
                     pms_events_secret="p" * 32, panel_token="t" * 32, pseudonym_salt="s" * 32,
                     chatwoot_bot_token="b" * 32)
    client = make_client(strong, harness)
    client.base_url = public_url
    response = login(client, password=strong.panel_token)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert ("Secure" in cookie) == public_url.startswith("https:")
    assert client.get("/api/panel/queue").status_code == 200


@pytest.mark.parametrize("body", [[], None, 1, "staff"])
def test_login_rejects_non_object_json(settings, harness, body):
    assert make_client(settings, harness).post("/api/panel/login", content=json.dumps(body)).status_code == 400


@pytest.mark.parametrize("valid", [True, False])
def test_panel_bootstrap_scrubs_token_before_exchange_and_guards_context(settings, harness, valid):
    import subprocess

    html = make_client(settings, harness).get("/panel").text
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    # Run the actual inline script against a bounded fake browser. No service or browser storage.
    harness_js = r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const events = [], requests = [], listeners = {};
const location = new URL('http://localhost/panel?conversation_id=7&token=bootstrap-secret');
let resolveLogin;
const login = new Promise(resolve => { resolveLogin = resolve; });
const app = {innerHTML: '', querySelector: () => ({addEventListener() {}})};
const parent = {postMessage() {}};
const context = {
  URL, URLSearchParams, location, console, Date,
  document: {getElementById: () => app},
  history: {replaceState(_a, _b, path) { events.push('scrub'); location.href = new URL(path, location).href; }},
  window: {parent, addEventListener(name, callback) { listeners[name] = callback; }},
  setInterval() {},
  fetch(path, options = {}) {
    requests.push({path, options});
    assert.equal(location.search.includes('token='), false, 'URL must be scrubbed before any request');
    if (path === '/api/panel/login') return login;
    assert.equal(options.headers?.['X-Panel-Token'], undefined);
    if (path === '/api/panel/session') return Promise.resolve({ok: true, json: async () => ({name: 'chatwoot'})});
    return Promise.resolve({ok: false, status: 401});
  },
};
vm.runInNewContext(SCRIPT, context);
listeners.message({source: parent, data: {event: 'appContext', data: {conversation: {id: 8}}}});
assert.deepEqual(requests.map(r => r.path), ['/api/panel/login']);
assert.equal(JSON.parse(requests[0].options.body).password, 'bootstrap-secret');
resolveLogin({ok: VALID, status: VALID ? 200 : 401, json: async () => ({name: 'chatwoot'})});
setImmediate(() => {
  assert.equal(location.search.includes('token='), false);
  assert.equal(requests.some(r => r.path === '/api/panel/8'), VALID);
  assert.equal(/localStorage|sessionStorage/.test(SCRIPT), false);
  assert.equal(SCRIPT.includes('&token='), false);
  assert.equal(SCRIPT.includes('?token='), false);
});
'''
    result = subprocess.run(["node", "-e", "const SCRIPT=" + json.dumps(script) + ";const VALID=" +
                             json.dumps(valid) + ";" + harness_js], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
