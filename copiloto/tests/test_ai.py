import json
from dataclasses import replace

from conftest import call, say
from copiloto.ai import sessions as ai_sessions
from copiloto.ai.llm import LlmUnavailable
from copiloto.ai.sessions import AiSession
from copiloto.ai.tools import ToolHooks, ToolRunner, tool_specs
from copiloto.pms import PmsConflict, PmsUnavailable

from copiloto import store

STAY = {"checkin": "2026-11-15", "checkout": "2026-11-18", "adults": 2, "children": 1}


def ai_events(harness, conversation_id=1):
    return [json.loads(e["payload"]) for e in harness.events("ai_reply", conversation_id)]


async def test_greeting_shows_the_ai_notice_and_location_without_calling_the_model(make_ai):
    h, llm = make_ai([])
    await h.say("hola")
    texts = h.chatwoot.guest_texts()
    assert "inteligencia artificial" in texts[0] and texts[1].startswith("Ubicación:")
    assert llm.calls == []


async def test_free_language_goes_to_the_model_not_a_rigid_format(make_ai):
    h, llm = make_ai([say("Claro, ¿cuántas personas viajan?")])
    await h.say("quiero ir el fin de semana largo con mi familia")
    assert "Escríbelas así" not in " ".join(h.chatwoot.guest_texts())
    assert llm.calls[0]["messages"][-1] == {"role": "user",
                                            "content": "quiero ir el fin de semana largo con mi familia"}
    assert h.chatwoot.guest_texts()[-1].startswith("Claro")


async def test_availability_tool_loop_records_prebooking_and_quick_replies(make_ai):
    h, llm = make_ai([call("check_availability", **STAY), say("Tengo estas opciones desde $75.000 por noche.")])
    await h.say("hola")
    await h.say("2 adultos y un niño del 15 al 18 de noviembre")
    assert h.pms.calls == 1
    assert llm.calls[1]["messages"][-1]["role"] == "tool"
    assert json.loads(llm.calls[1]["messages"][-1]["content"])["lectura_pms"] == "28-10-2026 15:00"
    assert store.active_prebooking(h.db, 1)["status"] == "active"
    last = h.chatwoot.messages[-1]
    assert last["options"] and last["options"][0][0].startswith("Quiero la")
    assert ai_events(h)[0]["tools"] == ["check_availability"]
    payload = h.db.execute("SELECT payload FROM events WHERE kind='ai_reply'").fetchone()["payload"]
    assert "niño" not in payload, "los eventos no guardan texto del huésped"


async def test_booking_without_a_fresh_matching_availability_reading_is_refused(make_ai):
    book = call("create_booking", guest_name="Camila Rojas", room_code="doble_con_jacuzzi", guest_confirmed=True,
                **STAY)
    h, _ = make_ai([book, say("Antes reviso la disponibilidad.")])
    await h.say("hola")
    await h.say("reserva la doble con jacuzzi, soy Camila Rojas")
    assert h.pms.bookings == []


async def test_booking_requires_an_explicit_guest_confirmation(make_ai):
    avail = call("check_availability", **STAY)
    book = call("create_booking", call_id="c2", guest_name="Camila Rojas", room_code="doble_con_jacuzzi",
                guest_confirmed=False, **STAY)
    h, _ = make_ai([avail, book, say("¿Me confirmas con un sí?")])
    await h.say("hola")
    await h.say("quiero reservar")
    assert h.pms.bookings == []


async def test_full_booking_flow_creates_one_booking_and_appends_the_server_summary(make_ai):
    avail = call("check_availability", **STAY)
    book = call("create_booking", call_id="c2", guest_name="Camila Rojas", room_code="doble_con_jacuzzi",
                guest_confirmed=True, **STAY)
    again = call("create_booking", call_id="c3", guest_name="Camila Rojas", room_code="doble_con_jacuzzi",
                 guest_confirmed=True, **STAY)
    h, _ = make_ai([avail, say("Opciones listas. ¿Te sirve alguna?"), book, again, say("¡Listo, Camila!")])
    await h.say("hola")
    await h.say("2 adultos y 1 niño del 15 al 18 de noviembre")
    await h.say("sí, la doble con jacuzzi, soy Camila Rojas")
    assert len(h.pms.bookings) == 1, "el segundo intento es idempotente"
    assert h.pms.bookings[0]["conversation_id"] == 1 and h.pms.bookings[0]["room_code"] == "doble_con_jacuzzi"
    reply = h.chatwoot.guest_texts()[-1]
    assert "Reserva de demostración #7" in reply and "no es una reserva real" in reply
    assert "$255.000" in reply and "2 adultos y 1 niño," in reply
    assert "reserva-ia" in h.chatwoot.labels[1]
    assert any("Reserva #7 creada por el asistente con IA" in n for n in h.chatwoot.notes(1))
    assert store.active_prebooking(h.db, 1)["status"] == "converted"
    assert len(h.events("ai_booking")) == 1


async def test_model_claiming_a_confirmed_booking_without_one_is_corrected(make_ai):
    h, _ = make_ai([say("¡Tu reserva está confirmada! Nos vemos.")])
    await h.say("hola")
    await h.say("reserva ya")
    text = h.chatwoot.guest_texts()[-1]
    assert "confirmada" not in text and "Todavía no hay una reserva creada" in text
    assert json.loads(h.events("ai_guardrail")[0]["payload"]) == {"rule": "confirmation_without_booking"}


async def test_tool_arguments_from_the_model_are_validated(make_ai):
    bad = [
        call("check_availability", checkin="2020-01-01", checkout="2020-01-03", adults=2, children=0),
        call("check_availability", checkin="2026-11-15", checkout="2026-11-14", adults=2, children=0),
        call("check_availability", checkin="2026-11-15", checkout="2026-11-18", adults=99, children=0),
        call("check_availability", checkin="mañana", checkout="pasado", adults=2, children=0),
        call("check_availability", checkin="2026-11-01", checkout="2027-01-30", adults=2, children=0),
    ]
    for item in bad:
        h, _ = make_ai([item, say("ok")])
        await h.say("hola")
        await h.say("consulta")
        assert h.pms.calls == 0


async def test_booking_rejects_names_that_look_like_personal_data_or_unknown_rooms(make_ai):
    h, _ = make_ai([])
    session = AiSession("cw:1", state={"last_availability": {
        **STAY, "read_label": "x", "options": {"doble_con_jacuzzi": {"name": "n", "price": 80000, "units": 1}},
        "ts": h.clock()}})
    runner = ToolRunner(h.hotel, h.pms, h.settings, h.clock, session, ToolHooks(conversation_id=1))
    base = {"room_code": "doble_con_jacuzzi", "guest_confirmed": True, **STAY}
    for name in ("camila@correo.cl", "12345678-9", "Camila", "+56 9 1234 5678"):
        result = await runner.run("create_booking", {**base, "guest_name": name})
        assert not result.ok, name
    result = await runner.run("create_booking", {**base, "guest_name": "Camila Rojas", "room_code": "suite_inventada"})
    assert not result.ok and h.pms.bookings == []


async def test_pms_conflict_or_outage_on_booking_never_claims_success(make_ai):
    for error in (PmsConflict("sin cupo"), PmsUnavailable("caído")):
        avail = call("check_availability", **STAY)
        book = call("create_booking", call_id="c2", guest_name="Camila Rojas", room_code="doble_con_jacuzzi",
                    guest_confirmed=True, **STAY)
        h, _ = make_ai([avail, book, say("Qué bien, tu reserva está lista y reservada")])
        h.pms.book_error = error
        await h.say("hola")
        await h.say("reserva")
        assert h.pms.bookings == []
        assert "Todavía no hay una reserva creada" in h.chatwoot.guest_texts()[-1]


async def test_assisted_mode_cannot_create_bookings(make_ai, ai_settings):
    assisted = replace(ai_settings, ai_mode="assisted")
    assert "create_booking" not in [t["function"]["name"] for t in tool_specs("assisted")]
    avail = call("check_availability", **STAY)
    book = call("create_booking", call_id="c2", guest_name="Camila Rojas", room_code="doble_con_jacuzzi",
                guest_confirmed=True, **STAY)
    h, _ = make_ai([avail, book, say("Queda pendiente con recepción.")], settings=assisted)
    await h.say("hola")
    await h.say("reserva")
    assert h.pms.bookings == []


async def test_handoff_tool_opens_the_conversation_with_the_assistant_detail(make_ai):
    h, _ = make_ai([call("handoff_to_human", reason="Quiere hablar por un reclamo")])
    await h.say("hola")
    await h.say("tengo un reclamo")
    assert h.chatwoot.statuses[1] == "open" and h.chatwoot.assigned == [1]
    note = h.chatwoot.notes(1)[0]
    assert "el asistente con IA derivó la conversación" in note and "Quiere hablar por un reclamo" in note
    assert store.get_state(h.db, 1).sla_started_at is not None
    assert "Ya pasé tu consulta a recepción" in h.chatwoot.guest_texts()[-1]


async def test_llm_outage_degrades_to_the_guided_menu(make_ai):
    h, _ = make_ai([LlmUnavailable("http 503")])
    await h.say("hola")
    await h.say("quiero reservar")
    assert any("no está disponible ahora" in t for t in h.chatwoot.guest_texts())
    assert h.chatwoot.messages[-1]["options"], "queda el menú de botones"
    assert store.get_state(h.db, 1).step == "menu"


async def test_conversation_cap_hands_off_to_a_person(make_ai):
    from copiloto.flow import AI_CONVERSATION_CAP
    h, _ = make_ai([say("ok")] * 3)
    await h.say("hola")
    session = ai_sessions.load(h.db, "cw:1", h.clock())
    session.msg_count = AI_CONVERSATION_CAP
    ai_sessions.save(h.db, session, h.clock())
    await h.say("otra pregunta")
    assert h.chatwoot.statuses[1] == "open"


async def test_history_is_bounded_and_system_prompt_carries_session_state(make_ai):
    h, llm = make_ai([call("check_availability", **STAY), say("a")] + [say("b")] * 8)
    await h.say("hola")
    await h.say("busca")
    for index in range(8):
        await h.say(f"mensaje {index}")
    session = ai_sessions.load(h.db, "cw:1", h.clock())
    assert len(session.history) <= h.settings.ai_max_history
    system = llm.calls[-1]["messages"][0]["content"]
    assert "ESTADO DE LA SESIÓN" in system and "doble_con_jacuzzi" in system
    assert "miércoles 2026-10-28" in system


async def test_retention_purge_deletes_old_ai_sessions(make_ai):
    h, _ = make_ai([say("ok")])
    await h.say("hola")
    await h.say("consulta")
    h.clock.advance(91 * 86400)
    assert store.purge_personal_data(h.db, h.clock(), 90, "salt")["ai_sessions"] == 1


async def test_server_templates_never_claim_a_confirmation():
    from copiloto.ai.agent import SAFE_NO_BOOKING, STUCK
    assert "confirmad" not in (SAFE_NO_BOOKING + STUCK).lower()
