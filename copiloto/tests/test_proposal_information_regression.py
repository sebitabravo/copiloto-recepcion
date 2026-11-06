"""A pending booking must not replace unrelated verified hotel answers."""
import hashlib

import httpx
from conftest import call, say
from copiloto.app import create_app


async def test_pending_proposal_preserves_hotel_information(make_ai):
    stay = {"checkin": "2026-11-15", "checkout": "2026-11-18", "adults": 2, "children": 1}
    booking = {**stay, "guest_name": "Camila Rojas", "room_code": "doble_con_jacuzzi",
               "guest_confirmed": True}
    h, llm = make_ai([call("check_availability", **stay), call("create_booking", **booking), say("Resumen")])
    app = create_app(h.settings, chatwoot=h.chatwoot, pms=h.pms, clock=h.clock,
                     run_workers=False, db=h.db, llm_agent=h.core.agent)
    body = {"session_id": "proposal-information-000001"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                base_url="http://localhost:8100") as client:
        first = await client.post("/api/demo/chat", json={**body, "message": "Soy Camila Rojas, quiero reservar"})
        assert first.status_code == 200
        assert any(event["type"] == "booking_proposal" for event in first.json()["events"])
        before = hashlib.sha256(repr(h.pms.bookings).encode()).digest()
        address = h.hotel.hotel["address"]
        llm.script.append(say("La dirección es " + address))
        response = await client.post("/api/demo/chat", json={**body, "message": "¿Cómo llego al hotel?"})
        assert response.status_code == 200
        assert address in response.json()["reply"]
        assert hashlib.sha256(repr(h.pms.bookings).encode()).digest() == before
