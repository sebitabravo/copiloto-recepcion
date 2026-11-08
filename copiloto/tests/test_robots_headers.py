"""Las vistas internas (panel, métricas, API) no se indexan; las páginas públicas sí pueden indexarse."""

import time

import pytest
from copiloto.app import create_app
from fastapi.testclient import TestClient

NOINDEX = "noindex, nofollow"


def make_client(settings, harness):
    app = create_app(settings, chatwoot=harness.chatwoot, pms=harness.pms, clock=time.time, run_workers=False,
                     db=harness.db)
    return TestClient(app)


@pytest.mark.parametrize(
    "path",
    ["/panel", "/metricas", "/metricas/data.json", "/api/panel/queue", "/api/panel/session", "/api/demo/status"],
)
def test_internal_views_and_api_send_noindex_header(settings, harness, path):
    response = make_client(settings, harness).get(path)
    assert response.headers["x-robots-tag"] == NOINDEX, f"{path} ({response.status_code})"


def test_noindex_header_also_on_authenticated_metrics(settings, harness):
    client = make_client(settings, harness)
    client.post("/api/panel/login", json={"password": settings.panel_token})
    response = client.get("/metricas")
    assert response.status_code == 200
    assert response.headers["x-robots-tag"] == NOINDEX
    assert '<meta name="robots" content="noindex, nofollow">' in response.text


def test_panel_html_carries_noindex_meta(settings, harness):
    assert '<meta name="robots" content="noindex, nofollow">' in make_client(settings, harness).get("/panel").text


@pytest.mark.parametrize("path", ["/privacidad", "/health"])
def test_public_pages_are_not_marked_noindex(settings, harness, path):
    assert "x-robots-tag" not in make_client(settings, harness).get(path).headers
