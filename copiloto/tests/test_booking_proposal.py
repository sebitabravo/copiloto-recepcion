"""Server proposals authorize a later identical transaction."""
from dataclasses import replace

import pytest
from conftest import call, say
from copiloto.ai.sessions import AiSession, load, save
from copiloto.ai.tools import ToolHooks, ToolRunner

STAY = {"checkin": "2026-11-15", "checkout": "2026-11-18", "adults": 2, "children": 1}
BOOK = {**STAY, "guest_name": "Camila Rojas", "room_code": "doble_con_jacuzzi", "guest_confirmed": True}


async def prepare(make_ai, hooks=None):
    h, llm = make_ai([call("check_availability", **STAY), call("create_booking", **BOOK),
                      say("Tu reserva está confirmada.")])
    session = AiSession("demo:proposal")
    result = await h.core.agent.respond(session, "Soy Camila Rojas, quiero reservar", hooks or ToolHooks())
    return h, llm, session, result


async def test_proposal_display_and_persistence_then_duplicate_safe_booking(make_ai):
    h, llm, session, result = await prepare(make_ai)
    assert h.pms.bookings == [] and result.booking is None
    proposal = next(e for e in result.events if e["type"] == "booking_proposal")
    assert proposal == {"type": "booking_proposal", "guest_name": "Camila Rojas",
                        "room_code": "doble_con_jacuzzi", "room_name": "Habitación Doble con Jacuzzi",
                        **STAY, "nights": 3, "total_clp": 255000, "simulated": True}
    for value in ("Camila Rojas", "Doble con Jacuzzi", "2026-11-15", "2026-11-18", "$255.000",
                  "3 noches", "2 adultos", "1 niño", "¿Confirmas"):
        assert value in result.reply
    save(h.db, session, h.clock())
    session = load(h.db, session.session_id, h.clock())
    llm.script.extend([call("create_booking", **BOOK), call("create_booking", **BOOK), say("Listo")])
    result = await h.core.agent.respond(session, "Sí, confirmo la reserva", ToolHooks())
    assert len(h.pms.bookings) == 1 and result.booking["booking_id"] == 7
    assert len([e for e in result.events if e["type"] == "booking_created"]) == 1


async def test_tool_execution_cannot_authorize_same_turn(make_ai):
    h, _ = make_ai([])
    session = AiSession("demo:proposal", state={"last_user_text": "Sí, soy Camila Rojas"})
    runner = ToolRunner(h.hotel, h.pms, h.settings, h.clock, session, ToolHooks())
    await runner.run("check_availability", STAY)
    for _ in range(2):
        result = await runner.run("create_booking", BOOK)
        assert result.event["type"] == "booking_proposal"
    assert h.pms.bookings == []


@pytest.mark.anyio
@pytest.mark.parametrize("change", ["price", "stay", "expired", "name", "room", "people"])
async def test_changed_or_expired_proposal_never_writes(make_ai, change):
    h, llm, session, _ = await prepare(make_ai)
    args = dict(BOOK)
    if change == "expired":
        h.clock.advance(h.settings.prebooking_minutes * 60 + 1)
    elif change == "price":
        h.pms.offers = [replace(o, nightly_price_clp=o.nightly_price_clp + 1) for o in h.pms.offers]
        llm.script.append(call("check_availability", **STAY))
    elif change == "stay":
        args["checkout"] = "2026-11-19"
    elif change == "name":
        args["guest_name"] = "Camila Inventada"
    elif change == "room":
        args["room_code"] = "doble_sin_vista"
    else:
        args["children"] = 0
    llm.script.extend([call("create_booking", **args), say("Listo")])
    result = await h.core.agent.respond(session, "Sí", ToolHooks())
    assert h.pms.bookings == [] and result.booking is None
    assert not any(e["type"] == "booking_created" for e in result.events)


async def test_zero_inventory_and_insufficient_capacity_are_filtered(make_ai):
    h, _ = make_ai([])
    h.pms.offers = [replace(h.pms.offers[0], available_units=0),
                    replace(h.pms.offers[1], max_children=0)]
    runner = ToolRunner(h.hotel, h.pms, h.settings, h.clock, AiSession("demo:offers"), ToolHooks())
    result = await runner.run("check_availability", STAY)
    assert result.ok and result.data["opciones"] == [] and h.pms.bookings == []


@pytest.mark.anyio
@pytest.mark.parametrize("text", ["sí, pero no reserves", "No, sí", "¿Sí?", "perfecto", "quiero una reserva"])
async def test_ambiguous_or_negative_answer_keeps_persisted_bookings_unchanged(make_ai, text):
    h, llm, session, _ = await prepare(make_ai)
    llm.script.extend([call("create_booking", **BOOK), say("Reserva confirmada")])
    result = await h.core.agent.respond(session, text, ToolHooks())
    save(h.db, session, h.clock())
    restored = load(h.db, session.session_id, h.clock())
    assert restored.state.get("bookings", []) == [] and h.pms.bookings == []
    assert result.booking is None and "¿Confirmas" in result.reply


async def test_false_confirmation_prepares_normalized_name_without_writing(make_ai):
    h, llm = make_ai([call("check_availability", **STAY),
                      call("create_booking", **{**BOOK, "guest_name": "  Camila   Rojas ", "guest_confirmed": False}),
                      say("Resumen")])
    session = AiSession("demo:normalized")
    result = await h.core.agent.respond(session, "Soy Camila Rojas", ToolHooks())
    assert "Camila Rojas" in result.reply and result.booking is None and h.pms.bookings == []
    llm.script.extend([call("create_booking", **BOOK), say("Listo")])
    result = await h.core.agent.respond(session, "Confirmo la reserva", ToolHooks())
    assert result.booking and len(h.pms.bookings) == 1


async def test_repeated_identical_reading_preserves_proposal_but_not_its_expiry(make_ai):
    h, llm, session, _ = await prepare(make_ai)
    h.clock.advance(h.settings.prebooking_minutes * 60 + 1)
    llm.script.extend([call("check_availability", **STAY), call("create_booking", **BOOK), say("Resumen")])
    result = await h.core.agent.respond(session, "Sí", ToolHooks())
    assert h.pms.bookings == [] and result.booking is None and "¿Confirmas" in result.reply


async def test_successful_real_channel_write_is_not_labelled_simulated(make_ai):
    h, llm = make_ai([call("check_availability", **STAY), call("create_booking", **BOOK), say("Resumen")])
    original = h.pms.availability

    async def real(*args):
        return replace(await original(*args), simulated=False)

    h.pms.availability = real
    session = AiSession("cw:realbooking")
    await h.core.agent.respond(session, "Soy Camila Rojas", ToolHooks(conversation_id=1))
    llm.script.extend([call("create_booking", **BOOK), say("Listo")])
    result = await h.core.agent.respond(session, "Sí", ToolHooks(conversation_id=1))
    assert result.booking and len(h.pms.bookings) == 1
    assert "simulado" not in result.reply and "demostración" not in result.reply
    assert next(e for e in result.events if e["type"] == "booking_created")["simulated"] is False


async def test_duplicate_does_not_write_again_after_price_changes(make_ai):
    h, llm, session, _ = await prepare(make_ai)
    llm.script.extend([call("create_booking", **BOOK), say("Listo")])
    await h.core.agent.respond(session, "Sí", ToolHooks())
    h.pms.offers = [replace(o, nightly_price_clp=o.nightly_price_clp + 1) for o in h.pms.offers]
    llm.script.extend([call("check_availability", **STAY), call("create_booking", **BOOK), say("Resumen"),
                       call("create_booking", **BOOK), say("Listo")])
    await h.core.agent.respond(session, "Revisa de nuevo", ToolHooks())
    result = await h.core.agent.respond(session, "Sí", ToolHooks())
    assert len(h.pms.bookings) == 1 and result.booking is None
    assert not any(e["type"] == "booking_created" for e in result.events)


async def test_existing_two_booking_limit_is_preserved(make_ai):
    h, llm, session, _ = await prepare(make_ai)
    llm.script.extend([call("create_booking", **BOOK), say("Listo")])
    await h.core.agent.respond(session, "Sí", ToolHooks())
    for name in ("Ignacio Perez", "Ana Torres"):
        args = {**BOOK, "guest_name": name}
        llm.script.extend([call("create_booking", **args), say("Resumen"),
                           call("create_booking", **args), say("Listo")])
        await h.core.agent.respond(session, f"Soy {name}", ToolHooks())
        result = await h.core.agent.respond(session, "Sí", ToolHooks())
    save(h.db, session, h.clock())
    restored = load(h.db, session.session_id, h.clock())
    assert len(restored.state["bookings"]) == len(h.pms.bookings) == 2
    assert result.booking is None
    assert any(e.get("summary") == "Límite de reservas de la demo" for e in result.events)
