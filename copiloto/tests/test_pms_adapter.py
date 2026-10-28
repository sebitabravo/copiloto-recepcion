from datetime import date

import httpx
import pytest
from copiloto.pms import MockPxsolAdapter, PmsUnavailable

OFFER = {"code": "doble_con_jacuzzi", "name": "Habitación Doble con Jacuzzi", "max_adults": 2, "max_children": 1,
         "m2": 32, "available_units": 2, "nightly_price_clp": 80000}
READING = {"read_at": "2026-10-28T15:00:00-03:00", "source": "pms-mock", "simulated": True,
           "room_types": [OFFER]}


def adapter(handler) -> MockPxsolAdapter:
    return MockPxsolAdapter("http://pms.test", http=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def read(handler):
    return await adapter(handler).availability(date(2027, 3, 15), date(2027, 3, 18), 2, 1)


async def test_valid_reading_is_parsed_with_its_timestamp():
    reading = await read(lambda request: httpx.Response(200, json=READING))
    assert reading.read_at == "2026-10-28T15:00:00-03:00" and reading.simulated is True
    assert reading.offers[0].nightly_price_clp == 80000


async def test_query_carries_dates_and_party():
    seen = {}

    def handler(request):
        seen.update(request.url.params)
        return httpx.Response(200, json=READING)

    await read(handler)
    assert seen == {"checkin": "2027-03-15", "checkout": "2027-03-18", "adults": "2", "children": "1"}


async def test_bad_or_broken_responses_are_unavailable():
    responses = [
        httpx.Response(503),
        httpx.Response(200, text="<html>mantención</html>"),
        httpx.Response(200, json={"read_at": "2026-10-28T15:00:00-03:00", "source": "pms-mock"}),
        httpx.Response(200, json={**READING, "room_types": [{**OFFER, "available_units": -1}]}),
        httpx.Response(200, json={**READING, "room_types": [{k: v for k, v in OFFER.items() if k != "code"}]}),
        httpx.Response(200, json={**READING, "read_at": "ayer"}),
    ]
    for response in responses:
        with pytest.raises(PmsUnavailable):
            await read(lambda request, response=response: response)


async def test_connection_errors_are_unavailable():
    def handler(request):
        raise httpx.ConnectError("sin red")

    with pytest.raises(PmsUnavailable):
        await read(handler)
