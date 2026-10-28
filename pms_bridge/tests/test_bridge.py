"""Contrato del puente Beds24: lo que el copiloto recibe debe ser siempre una lectura fechada."""

import json
from datetime import date, datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from pms_bridge.beds24 import Beds24Client, Beds24Error, RoomMap, parse_rooms, read_at, stay_offers
from pms_bridge.main import create_app

ROOMS_JSON = json.dumps([
    {"code": "doble_con_jacuzzi", "roomId": 101, "name": "Doble con Jacuzzi", "max_adults": 2,
     "max_children": 1, "m2": 32},
    {"code": "single", "roomId": 102, "name": "Single", "max_adults": 1, "max_children": 0, "m2": 18},
])
CHECKIN, CHECKOUT = date(2027, 3, 15), date(2027, 3, 18)


def day(room_id: int, night: str, units: int, price: float) -> dict:
    return {"roomId": room_id, "date": night, "numAvail": units, "price1": price}


def nights(room_id: int, units: int = 2, price: float = 100000) -> list[dict]:
    return [day(room_id, "2027-03-15", units, price), day(room_id, "2027-03-16", units, price),
            day(room_id, "2027-03-17", units, price)]


def test_rooms_are_read_and_validated_at_startup():
    rooms = parse_rooms(ROOMS_JSON)
    assert rooms[0].code == "doble_con_jacuzzi" and rooms[0].room_id == 101

    for broken in ("no es json", "[]", json.dumps([{"code": "x"}])):
        with pytest.raises(Beds24Error):
            parse_rooms(broken)


def test_the_stay_uses_the_lowest_availability_and_the_average_price():
    offers = stay_offers(parse_rooms(ROOMS_JSON)[:1], nights(101, units=2, price=90000), CHECKIN, CHECKOUT)
    assert offers[0]["available_units"] == 2 and offers[0]["nightly_price_clp"] == 90000


def test_a_closed_or_missing_night_removes_the_offer():
    closed = nights(101)
    closed[1]["numAvail"] = 0
    assert stay_offers(parse_rooms(ROOMS_JSON)[:1], closed, CHECKIN, CHECKOUT) == []

    missing = nights(101)[:2]
    assert stay_offers(parse_rooms(ROOMS_JSON)[:1], missing, CHECKIN, CHECKOUT) == []


def test_the_currency_rate_is_applied():
    offers = stay_offers(parse_rooms(ROOMS_JSON)[:1], nights(101, price=100), CHECKIN, CHECKOUT, clp_rate=950)
    assert offers[0]["nightly_price_clp"] == 95000


async def test_the_client_refreshes_the_token_before_reading():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/authentication/token"):
            seen["refresh"] = request.headers.get("refreshToken")
            return httpx.Response(200, json={"token": "acc-1", "expiresIn": 3600})
        seen["token"] = request.headers.get("token")
        seen["roomIds"] = request.url.params.get_list("roomId")
        return httpx.Response(200, json={"success": True, "data": nights(101)})

    client = Beds24Client(refresh_token="ref-1", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    days = await client.calendar([101], CHECKIN, CHECKOUT)

    assert seen["refresh"] == "ref-1" and seen["token"] == "acc-1"
    assert seen["roomIds"] == ["101"] and len(days) == 3


async def test_a_beds24_error_is_raised_not_hidden():
    client = Beds24Client(access_token="acc",
                          http=httpx.AsyncClient(transport=httpx.MockTransport(
                              lambda request: httpx.Response(401, json={"success": False, "error": "Token is missing"}))))
    with pytest.raises(Beds24Error):
        await client.calendar([101], CHECKIN, CHECKOUT)


class FakeClient:
    def __init__(self, days=None, error=None):
        self.days, self.error = days or [], error

    async def calendar(self, room_ids, start, end):
        if self.error:
            raise self.error
        return [row for row in self.days if row["roomId"] in room_ids]


def app_with(days=None, error=None):
    return TestClient(create_app(client=FakeClient(days, error), rooms=parse_rooms(ROOMS_JSON),
                                 timezone_name="America/Santiago"))


def test_the_endpoint_returns_the_copilot_contract():
    response = app_with(nights(101) + nights(102)).get(
        "/api/v1/availability", params={"checkin": "2027-03-15", "checkout": "2027-03-18",
                                        "adults": 2, "children": 1})
    body = response.json()

    assert response.status_code == 200
    assert body["source"] == "beds24" and body["simulated"] is False
    assert body["read_at"].endswith("-03:00")
    assert [offer["code"] for offer in body["room_types"]] == ["doble_con_jacuzzi"]


def test_rooms_that_do_not_fit_the_party_are_not_offered():
    body = app_with(nights(101) + nights(102)).get(
        "/api/v1/availability", params={"checkin": "2027-03-15", "checkout": "2027-03-18",
                                        "adults": 2, "children": 1}).json()
    assert "single" not in [offer["code"] for offer in body["room_types"]]


def test_a_bad_range_is_rejected_without_calling_beds24():
    response = app_with(nights(101)).get(
        "/api/v1/availability", params={"checkin": "2027-03-18", "checkout": "2027-03-15",
                                        "adults": 2, "children": 0})
    assert response.status_code == 422


def test_a_beds24_failure_is_reported_as_unavailable():
    response = app_with(error=Beds24Error("Beds24 respondió 500")).get(
        "/api/v1/availability", params={"checkin": "2027-03-15", "checkout": "2027-03-18",
                                        "adults": 2, "children": 1})
    assert response.status_code == 502


def test_the_bridge_does_not_write_bookings():
    response = app_with().post("/api/v1/bookings", json={})
    assert response.status_code == 501


def test_the_timestamp_carries_the_hotel_zone():
    stamp = read_at(datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc), "America/Santiago")
    assert stamp.startswith("2026-10-28T15:00:00-03:00")
