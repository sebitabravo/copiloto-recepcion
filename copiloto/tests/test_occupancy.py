"""Plano de ocupación: el panel lee el PMS por el copiloto, nunca desde el navegador."""

from datetime import date

import httpx
import pytest
from copiloto.app import create_app
from copiloto.pms import HttpPmsAdapter, PmsUnavailable
from fastapi.testclient import TestClient

OCCUPANCY = {
    "read_at": "2026-11-16T10:00:00-03:00", "source": "pms-mock", "simulated": True, "start": "2026-11-16", "days": 14,
    "units": [{"room_id": 1, "number": "101", "code": "doble_con_jacuzzi", "short": "DCJ",
               "name": "Habitación Doble con Jacuzzi", "nightly_price_clp": 80000}],
    "bookings": [{"booking_id": 7, "room_id": 1, "guest_name": "Ana Pérez", "checkin": "2026-11-17",
                  "checkout": "2026-11-19", "adults": 2, "children": 0, "source": "ia"}],
}


def adapter(handler) -> HttpPmsAdapter:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HttpPmsAdapter("http://pms.test", http=http, staff_token="secreto-de-prueba")


async def test_adapter_parses_the_plan_and_sends_the_staff_token():
    seen = {}

    def handler(request):
        seen["token"] = request.headers.get("x-staff-token")
        seen["params"] = dict(request.url.params)
        seen["path"] = request.url.path
        return httpx.Response(200, json=OCCUPANCY)

    plan = await adapter(handler).occupancy(date(2026, 11, 16), 14)
    assert seen == {"token": "secreto-de-prueba", "params": {"start": "2026-11-16", "days": "14"},
                    "path": "/api/v1/occupancy"}
    assert plan["units"][0]["short"] == "DCJ"
    assert plan["bookings"][0]["source"] == "ia"
    assert plan["simulated"] is True


async def test_adapter_treats_bad_responses_as_unavailable():
    broken = {k: v for k, v in OCCUPANCY.items() if k != "units"}
    responses = [
        httpx.Response(503),
        httpx.Response(401),
        httpx.Response(200, text="<html>mantención</html>"),
        httpx.Response(200, json=broken),
        httpx.Response(200, json={**OCCUPANCY, "bookings": [{"booking_id": 1}]}),
    ]
    for response in responses:
        with pytest.raises(PmsUnavailable):
            await adapter(lambda request, response=response: response).occupancy(date(2026, 11, 16), 14)


async def test_default_adapter_has_no_plan(harness):
    with pytest.raises(PmsUnavailable):
        await harness.pms.occupancy(date(2026, 11, 16), 14)


def serve_plan(harness, monkeypatch, result=OCCUPANCY):
    calls = []

    async def occupancy(start, days):
        calls.append((start, days))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(harness.pms, "occupancy", occupancy, raising=False)
    return calls


def test_plan_requires_a_panel_session(demo):
    anonymous = TestClient(demo.app)
    assert anonymous.get("/api/panel/occupancy").status_code == 401


def test_plan_is_proxied_for_a_demo_session(demo, harness, monkeypatch):
    calls = serve_plan(harness, monkeypatch)
    response = demo.sofia.get("/api/panel/occupancy", params={"start": "2026-11-16", "days": 14})
    assert response.status_code == 200
    assert response.json() == OCCUPANCY
    assert calls == [(date(2026, 11, 16), 14)]


def test_plan_defaults_to_today_and_fourteen_days(demo, harness, monkeypatch):
    calls = serve_plan(harness, monkeypatch)
    assert demo.sofia.get("/api/panel/occupancy").status_code == 200
    assert calls == [(date(2026, 11, 8), 14)]


def test_plan_rejects_bad_parameters(demo, harness, monkeypatch):
    calls = serve_plan(harness, monkeypatch)
    for params in ({"days": 0}, {"days": 32}, {"start": "mañana"}):
        assert demo.sofia.get("/api/panel/occupancy", params=params).status_code == 422
    assert calls == []


def test_plan_answers_503_when_the_pms_is_down(demo, harness, monkeypatch):
    serve_plan(harness, monkeypatch, PmsUnavailable("caído"))
    response = demo.sofia.get("/api/panel/occupancy")
    assert response.status_code == 503
    assert "PMS" in response.json()["detail"]


def test_plan_is_not_served_to_the_real_operation(settings, harness, monkeypatch):
    serve_plan(harness, monkeypatch)
    app = create_app(settings, chatwoot=harness.chatwoot, pms=harness.pms, clock=harness.clock, run_workers=False,
                     db=harness.db)
    response = TestClient(app).get("/api/panel/occupancy", headers={"X-Panel-Token": "panel-secret"})
    assert response.status_code == 403
