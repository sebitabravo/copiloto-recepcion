import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient
from pms_mock.main import DEFAULT_HOTEL_PATH, create_app

TOKEN = {"X-Staff-Token": "test-staff-token"}
DATES = {"checkin": "2026-11-01", "checkout": "2026-11-04", "adults": 1, "children": 0}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PMS_DB_PATH", str(tmp_path / "test.sqlite"))
    monkeypatch.setenv("STAFF_TOKEN", "test-staff-token")
    monkeypatch.delenv("SIMULATE_DOWN", raising=False)
    monkeypatch.delenv("COPILOTO_EVENTS_URL", raising=False)
    monkeypatch.delenv("HOTEL_DATA_PATH", raising=False)
    with TestClient(create_app()) as test_client:
        yield test_client


def payload(code="single_doble_vista_jardin", **changes):
    return {"guest_name": "Test Guest", "room_code": code, **DATES, **changes}


def book(client, **changes):
    return client.post("/api/v1/bookings", headers=TOKEN, json=payload(**changes))


def inventory(client, **changes):
    response = client.get("/api/v1/availability", params={**DATES, **changes})
    assert response.status_code == 200
    return {room["code"]: room for room in response.json()["room_types"]}


def test_health_and_seed(client):
    assert client.get("/health").json() == {"status": "ok"}
    data = client.get("/api/v1/availability", params=DATES).json()
    assert data["source"] == "pms-mock" and data["simulated"] is True
    read_at = datetime.fromisoformat(data["read_at"])
    assert read_at.utcoffset() == read_at.astimezone(ZoneInfo("America/Santiago")).utcoffset()
    assert len(data["room_types"]) == 12
    assert sum(room["available_units"] for room in data["room_types"]) == 20
    source = yaml.safe_load(DEFAULT_HOTEL_PATH.read_text())["rooms"]
    for actual, expected in zip(data["room_types"], source, strict=True):
        for field in ("code", "name", "max_adults", "max_children", "m2"):
            assert actual[field] == expected[field]
        assert actual["nightly_price_clp"] > 0
    with sqlite3.connect(client.app.state.database_path) as connection:
        assert connection.execute("SELECT count(*) FROM rooms").fetchone()[0] == 20


def test_availability_math_and_overlap_rejection(client):
    code = "single_doble_vista_jardin"
    assert inventory(client)[code]["available_units"] == 2
    first = book(client)
    assert first.status_code == 201
    assert first.json()["booking_id"] > 0
    assert inventory(client)[code]["available_units"] == 1
    assert book(client).status_code == 201
    assert code not in inventory(client)
    assert book(client).status_code == 409
    assert len(client.get("/api/v1/bookings", headers=TOKEN).json()) == 2
    assert inventory(client, checkin="2026-11-04", checkout="2026-11-05")[code]["available_units"] == 2


def test_disjoint_bookings_use_peak_not_sum(client):
    assert book(client, checkin="2026-11-01", checkout="2026-11-02").status_code == 201
    assert book(client, checkin="2026-11-02", checkout="2026-11-04").status_code == 201
    assert inventory(client)["single_doble_vista_jardin"]["available_units"] == 1
    assert book(client).status_code == 201
    assert book(client).status_code == 409


def test_capacity_filtering(client):
    rooms = inventory(client, adults=3, children=2)
    assert rooms
    assert all(room["max_adults"] >= 3 and room["max_children"] >= 2 for room in rooms.values())
    assert "doble_terraza_vista_lago" not in inventory(client, adults=2)
    assert inventory(client, adults=10) == {}
    assert book(client, adults=3).status_code == 422
    assert book(client, children=1).status_code == 422
    assert book(client, code="invented").status_code == 422


@pytest.mark.parametrize("dates", [
    {"checkout": "2026-11-01"}, {"checkout": "2026-10-30"}, {"checkin": "invalid"},
    {"adults": 0}, {"children": -1},
])
def test_validation(client, dates):
    assert client.get("/api/v1/availability", params={**DATES, **dates}).status_code == 422
    assert book(client, **dates).status_code == 422


def test_dynamic_outage(client, monkeypatch):
    assert inventory(client)
    monkeypatch.setenv("SIMULATE_DOWN", "1")
    assert client.get("/api/v1/availability", params=DATES).status_code == 503
    assert client.get("/health").status_code == 200
    monkeypatch.setenv("SIMULATE_DOWN", "0")
    assert inventory(client)


def test_authentication(client, monkeypatch):
    assert client.get("/api/v1/bookings").status_code == 401
    assert client.post("/api/v1/bookings", json=payload()).status_code == 401
    assert client.post("/api/v1/bookings", headers={"X-Staff-Token": "wrong"}, json=payload()).status_code == 401
    monkeypatch.delenv("STAFF_TOKEN")
    assert client.get("/api/v1/bookings", headers=TOKEN).status_code == 401
    monkeypatch.setenv("STAFF_TOKEN", "")
    assert client.get("/api/v1/bookings", headers={"X-Staff-Token": ""}).status_code == 401


def test_event_emitted_after_commit(client, monkeypatch):
    monkeypatch.setenv("COPILOTO_EVENTS_URL", "http://events.test/event")
    response = MagicMock()
    seen = []

    def post(url, json, headers):
        assert headers == {}
        with sqlite3.connect(client.app.state.database_path) as connection:
            assert connection.execute("SELECT booking_id FROM bookings").fetchone()[0] == json["booking_id"]
        seen.append((url, json))
        return response

    with patch("pms_mock.main.httpx.Client") as http_client:
        http_client.return_value.__enter__.return_value.post.side_effect = post
        result = book(client, conversation_id=42)
    assert result.status_code == 201
    assert seen == [("http://events.test/event", {"kind": "booking_confirmed", "conversation_id": 42,
                                               "booking_id": result.json()["booking_id"]})]
    response.raise_for_status.assert_called_once()


def test_event_carries_secret_in_header_not_in_url(client, monkeypatch):
    monkeypatch.setenv("COPILOTO_EVENTS_URL", "http://events.test/event")
    monkeypatch.setenv("COPILOTO_EVENTS_TOKEN", "shh")
    with patch("pms_mock.main.httpx.Client") as http_client:
        post = http_client.return_value.__enter__.return_value.post
        assert book(client).status_code == 201
    assert post.call_args.args[0] == "http://events.test/event"
    assert post.call_args.kwargs["headers"] == {"X-Events-Token": "shh"}


@pytest.mark.parametrize("failure", [httpx.ConnectError("offline"), httpx.HTTPStatusError(
    "unavailable", request=httpx.Request("POST", "http://events.test/event"),
    response=httpx.Response(503),
)])
def test_event_failure_isolated_and_retried(client, monkeypatch, failure):
    monkeypatch.setenv("COPILOTO_EVENTS_URL", "http://events.test/event")
    with patch("pms_mock.main.httpx.Client") as http_client, patch("pms_mock.main.time.sleep") as sleep:
        post = http_client.return_value.__enter__.return_value.post
        post.side_effect = failure
        response = book(client)
        assert post.call_count == 4
        assert sleep.call_count == 3
    assert response.status_code == 201
    assert len(client.get("/api/v1/bookings", headers=TOKEN).json()) == 1


def test_retry_recovers(client, monkeypatch):
    monkeypatch.setenv("COPILOTO_EVENTS_URL", "http://events.test/event")
    with patch("pms_mock.main.httpx.Client") as http_client, patch("pms_mock.main.time.sleep"):
        post = http_client.return_value.__enter__.return_value.post
        post.side_effect = [httpx.ConnectError("offline"), MagicMock()]
        assert book(client).status_code == 201
        assert post.call_count == 2


def test_no_event_without_url(client):
    with patch("pms_mock.main.emit_event") as emit:
        assert book(client).status_code == 201
        emit.assert_not_called()


def test_concurrent_requests_do_not_overbook(client):
    with ThreadPoolExecutor(max_workers=4) as executor:
        statuses = list(executor.map(lambda _: book(client).status_code, range(4)))
    assert sorted(statuses) == [201, 201, 409, 409]


def test_restart_preserves_bookings_and_inventory(client):
    assert book(client).status_code == 201
    with TestClient(create_app()) as second:
        assert inventory(second)["single_doble_vista_jardin"]["available_units"] == 1
        assert len(second.get("/api/v1/bookings", headers=TOKEN).json()) == 1


def test_hotel_override_and_fail_fast(tmp_path, monkeypatch):
    path = tmp_path / "hotel.yaml"
    monkeypatch.setenv("HOTEL_DATA_PATH", str(path))
    with pytest.raises(RuntimeError, match="Cannot load hotel data"):
        create_app()
    path.write_text("hotel: {}")
    with pytest.raises(RuntimeError, match="missing required key 'rooms'"):
        create_app()
    path.write_text("rooms: []")
    with pytest.raises(RuntimeError, match="exactly 12"):
        create_app()
    source = yaml.safe_load(DEFAULT_HOTEL_PATH.read_text())
    source["rooms"][0]["name"] = "Override room name"
    path.write_text(yaml.safe_dump(source))
    assert create_app().state.room_types[0].name == "Override room name"


def test_admin_is_local_spanish_and_manual(client):
    response = client.get("/admin", params={"guest": "<script>alert(1)</script>"})
    assert response.status_code == 200
    assert 'lang="es"' in response.text
    assert "Confirmar reserva" in response.text
    assert "URLSearchParams" in response.text
    assert "textContent" in response.text
    assert "innerHTML" not in response.text
    assert '<script src=' not in response.text
    assert client.get("/api/v1/bookings", headers=TOKEN).json() == []


def test_room_types_are_public_and_match_yaml_order(client):
    response = client.get("/api/v1/room-types")
    assert response.status_code == 200
    rooms = response.json()
    source = yaml.safe_load(DEFAULT_HOTEL_PATH.read_text())["rooms"]
    fields = {"code", "name", "m2", "max_adults", "max_children"}
    assert len(rooms) == 12
    assert [room["code"] for room in rooms] == [room["code"] for room in source]
    assert all(set(room) == fields for room in rooms)
    assert rooms == [{field: room[field] for field in fields} for room in source]


def test_admin_is_self_contained_html(client):
    response = client.get("/admin")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "http://" not in response.text
    assert "https://" not in response.text
    assert "innerHTML" not in response.text
    assert "localStorage" not in response.text
    assert "sessionStorage" in response.text
