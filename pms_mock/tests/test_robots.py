"""El panel del PMS es interno: no se indexa, y sus tipografías se sirven desde el mismo servicio."""

import pytest
from fastapi.testclient import TestClient
from pms_mock.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PMS_DB_PATH", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("STAFF_TOKEN", "test-staff-token")
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("HOTEL_DATA_PATH", raising=False)
    with TestClient(create_app()) as test_client:
        yield test_client


def test_admin_sends_noindex_header_and_meta(client):
    response = client.get("/admin")
    assert response.status_code == 200
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert '<meta name="robots" content="noindex, nofollow">' in response.text


def test_health_is_not_marked_noindex(client):
    assert "x-robots-tag" not in client.get("/health").headers


@pytest.mark.parametrize("name", ["instrument-serif-normal.woff2", "inter-normal.woff2"])
def test_admin_fonts_are_self_hosted(client, name):
    response = client.get(f"/admin/fonts/{name}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "font/woff2"
    assert f"/admin/fonts/{name}" in client.get("/admin").text


@pytest.mark.parametrize("name", ["../main.py", "admin.html", "missing.woff2", "x.ttf"])
def test_font_route_serves_only_bundled_woff2(client, name):
    assert client.get(f"/admin/fonts/{name}").status_code == 404
