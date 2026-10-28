"""Contrato del conector de PMS: lo que cualquier adaptador debe cumplir para servir al copiloto.

Estas pruebas describen el contrato de docs/conector-pms.md y corren contra `HttpPmsAdapter`, que es
el conector que se usa con un PMS real. Un proveedor que quiera integrarse tiene que pasar lo mismo.
"""

from dataclasses import replace
from datetime import date

import httpx
import pytest

from copiloto.config import Settings
from copiloto.pms import (HttpPmsAdapter, PmsConflict, PmsUnavailable, UnavailablePmsAdapter,
                          build_pms_adapter)

CHECKIN, CHECKOUT = date(2027, 3, 15), date(2027, 3, 18)
OFFER = {"code": "doble_con_jacuzzi", "name": "Habitación Doble con Jacuzzi", "max_adults": 2,
         "max_children": 1, "m2": 32, "available_units": 2, "nightly_price_clp": 80000}
READING = {"read_at": "2026-10-28T15:00:00-03:00", "source": "pms-hotel", "simulated": False,
           "room_types": [OFFER]}


def adapter(handler, **options) -> HttpPmsAdapter:
    return HttpPmsAdapter("http://pms.test", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                         **options)


async def read(handler, **options):
    return await adapter(handler, **options).availability(CHECKIN, CHECKOUT, 2, 1)


async def test_a_valid_reading_keeps_its_timestamp_and_source():
    reading = await read(lambda request: httpx.Response(200, json=READING))
    assert reading.read_at == "2026-10-28T15:00:00-03:00"
    assert reading.source == "pms-hotel" and reading.simulated is False
    assert reading.offers[0].available_units == 2


async def test_the_reading_asks_for_the_stay_it_was_given():
    seen = {}

    async def handler(request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=READING)

    await read(handler)
    assert seen == {"checkin": "2027-03-15", "checkout": "2027-03-18", "adults": "2", "children": "1"}


async def test_a_payload_outside_the_contract_is_unavailable():
    payloads = [
        {**READING, "room_types": [{**OFFER, "nightly_price_clp": -1}]},
        {**READING, "room_types": [{**OFFER, "available_units": -3}]},
        {"room_types": [OFFER]},
    ]
    for payload in payloads:
        with pytest.raises(PmsUnavailable):
            await read(lambda request, body=payload: httpx.Response(200, json=body))


async def test_any_failure_becomes_unavailable_never_a_promise():
    def timeout(request):
        raise httpx.ConnectTimeout("timeout")

    for handler in (lambda request: httpx.Response(500, text="boom"),
                    lambda request: httpx.Response(200, text="no es json"),
                    timeout):
        with pytest.raises(PmsUnavailable):
            await read(handler)


async def test_a_conflict_is_not_an_outage():
    with pytest.raises(PmsConflict):
        await adapter(lambda request: httpx.Response(409, text="sin cupo")).book(
            "Camila Rojas", "doble_con_jacuzzi", CHECKIN, CHECKOUT, 2, 1, 1)


async def test_a_booking_returns_its_identifier():
    booking = await adapter(lambda request: httpx.Response(
        201, json={"booking_id": 77, "room_code": "doble_con_jacuzzi", "checkin": "2027-03-15",
                   "checkout": "2027-03-18"})).book("Camila Rojas", "doble_con_jacuzzi", CHECKIN, CHECKOUT, 2, 1, 1)
    assert booking["booking_id"] == 77


async def test_the_connector_uses_the_configured_paths_and_header():
    seen = {}

    async def handler(request):
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json=READING)

    await read(handler, availability_path="/v2/rooms/availability", auth_header="Authorization",
               staff_token="Bearer abc")
    assert seen["path"] == "/v2/rooms/availability"


def test_a_hotel_without_a_pms_gets_the_unavailable_adapter():
    settings = replace(Settings.from_env(), pms_adapter="none")
    assert isinstance(build_pms_adapter(settings), UnavailablePmsAdapter)


async def test_without_a_pms_the_copilot_cannot_promise_availability():
    settings = replace(Settings.from_env(), pms_adapter="none")
    with pytest.raises(PmsUnavailable):
        await build_pms_adapter(settings).availability(CHECKIN, CHECKOUT, 2, 1)


def test_the_default_adapter_reads_the_configured_url_and_paths():
    settings = replace(Settings.from_env(), pms_adapter="http", pms_url="http://pms.hotel:9000",
                       pms_availability_path="/custom/availability")
    connector = build_pms_adapter(settings)
    assert isinstance(connector, HttpPmsAdapter)
    assert connector._base_url == "http://pms.hotel:9000"
    assert connector._availability_path == "/custom/availability"
