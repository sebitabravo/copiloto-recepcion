"""Modo demo sin credenciales en el navegador (L8-L9): la sesión del panel la crea el servidor.

POST /api/demo/session entrega la misma cookie firmada que el login, nunca el token.
GET /api/demo/session informa si la demo está disponible y quién es la sesión actual.
"""

from dataclasses import replace

from copiloto.app import create_app
from fastapi.testclient import TestClient

DEMO_NAME = "Recepción (demo)"


def client_for(settings, harness):
    app = create_app(settings, chatwoot=harness.chatwoot, pms=harness.pms, clock=harness.clock, run_workers=False,
                     db=harness.db)
    return TestClient(app)


def test_demo_session_opens_the_panel_with_the_same_signed_cookie(settings, harness):
    client = client_for(settings, harness)
    response = client.post("/api/demo/session")
    assert response.status_code == 204 and response.content == b""
    cookie = response.headers["set-cookie"]
    assert "panel_session=" in cookie
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert client.get("/api/panel/queue").status_code == 200
    assert client.get("/api/panel/session").json() == {"name": DEMO_NAME}


def test_demo_session_is_refused_with_403_and_without_a_cookie_when_disabled(settings, harness):
    client = client_for(replace(settings, demo_enabled=False), harness)
    response = client.post("/api/demo/session")
    assert response.status_code == 403
    assert "set-cookie" not in response.headers
    assert client.get("/api/panel/queue").status_code == 401


def test_demo_session_responses_never_carry_a_secret(settings, harness):
    client = client_for(settings, harness)
    assert client.get("/api/demo/session").json() == {"demo": True, "name": None, "run": None}
    created = client.post("/api/demo/session")
    assert "panel-secret" not in created.text + created.headers.get("set-cookie", "")


def test_demo_session_reports_the_existing_panel_identity(settings, harness):
    client = client_for(settings, harness)
    client.post("/api/panel/login", json={"name": "Camila", "password": "panel-secret"})
    assert client.get("/api/demo/session").json() == {"demo": True, "name": "Camila", "run": None}


def test_demo_session_disabled_reports_false_without_a_name(settings, harness):
    client = client_for(replace(settings, demo_enabled=False), harness)
    assert client.get("/api/demo/session").json() == {"demo": False, "name": None, "run": None}


def test_demo_session_post_rejects_an_oversized_body(settings, harness):
    client = client_for(settings, harness)
    assert client.post("/api/demo/session", content=b"x" * 5000).status_code == 413


def test_demo_session_respects_the_rate_limiter(settings, harness):
    client = client_for(replace(settings, public_rate_per_min=1), harness)
    assert client.post("/api/demo/session").status_code == 204
    assert client.post("/api/demo/session").status_code == 429
