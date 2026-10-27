import re
import time

from conftest import local_epoch
from copiloto import store

FORBIDDEN = re.compile(r"(confirmad|reservad|garantizad)[oa]s?", re.IGNORECASE)


async def book(h, conversation_id=1, dates="15/11 al 18/11", adults="2", children="1"):
    await h.say("quiero reservar", conversation_id=conversation_id)
    await h.say(dates, conversation_id=conversation_id)
    await h.say(adults, conversation_id=conversation_id)
    await h.say(children, conversation_id=conversation_id)


async def test_faq_reply_latency_under_10s(harness):
    started = time.monotonic()
    await harness.say("¿tienen piscina?")
    assert time.monotonic() - started < 10
    faq_events = harness.events("faq_answered")
    assert len(faq_events) == 1
    import json
    payload = json.loads(faq_events[0]["payload"])
    assert payload["faq_id"] == "piscina"
    assert faq_events[0]["ts"] - payload["inbound_ts"] < 10
    assert harness.chatwoot.statuses == {}, "una FAQ no debe sacar la conversación de pending"


async def test_greeting_not_counted_as_resolution(harness):
    await harness.say("hola")
    assert harness.events("faq_answered") == []
    import json
    assert json.loads(harness.events("inbound")[0]["payload"])["greeting"] is True
    assert harness.chatwoot.messages[-1]["options"], "debe ofrecer el menú"


async def test_location_shown_before_booking_questions(harness):
    await harness.say("quiero reservar para el finde")
    texts = harness.chatwoot.guest_texts()
    location_index = next(i for i, t in enumerate(texts) if t.startswith("Ubicación:"))
    question_index = next(i for i, t in enumerate(texts) if "fechas" in t and "necesito" in t.lower())
    assert location_index < question_index
    assert len(harness.events("location_shown")) == 1


async def test_bot_never_asserts_confirmation(harness):
    h = harness
    await h.say("hola")
    for option in ("Ubicación", "Habitaciones y fotos", "Servicios y preguntas"):
        await h.say(option)
    for faq in h.hotel.faqs:
        await h.say(faq.keywords[0])
    await h.say("menu")
    await book(h, conversation_id=2)
    await h.say("1", conversation_id=2)
    await book(h, conversation_id=3)
    h.pms.down = True
    await book(h, conversation_id=4)
    for text in h.chatwoot.guest_texts() + [faq.answer for faq in h.hotel.faqs]:
        assert not FORBIDDEN.search(text), text


async def test_availability_text_is_dated_and_pending(harness):
    await book(harness)
    text = next(t for t in harness.chatwoot.guest_texts() if t.startswith("Disponible según lectura del PMS"))
    assert "15:00" in text and "Pendiente de confirmación por recepción" in text
    assert harness.pms.calls == 1


async def test_prebooking_expires_after_15min_without_touching_pms(harness, settings):
    from copiloto.sla import SlaWorker
    await book(harness)
    await harness.say("1")
    calls_before = harness.pms.calls
    worker = SlaWorker(settings, harness.db, harness.chatwoot, harness.clock)
    harness.clock.advance(14 * 60)
    await worker.tick()
    assert store.active_prebooking(harness.db, 1)["status"] == "active"
    harness.clock.advance(61)
    await worker.tick()
    assert store.active_prebooking(harness.db, 1)["status"] == "expired"
    assert len(harness.events("prebooking_expired")) == 1
    assert harness.pms.calls == calls_before


async def test_pms_down_falls_back_to_reception(harness):
    harness.pms.down = True
    await book(harness)
    texts = harness.chatwoot.guest_texts()
    assert any("Recepción verificará cupos" in t for t in texts)
    assert not any(t.startswith("Disponible según") for t in texts)
    assert harness.chatwoot.statuses[1] == "open"
    assert "comercial" in harness.chatwoot.labels[1]
    assert json_reason(harness.events("handoff")[0]) == "pms_down"


def json_reason(event):
    import json
    return json.loads(event["payload"])["reason"]


async def test_out_of_hours_capture_states_human_hours(harness, clock):
    clock.now = local_epoch(2026, 10, 28, 23, 30)
    await book(harness)
    await harness.say("1")
    closing = [t for t in harness.chatwoot.guest_texts() if "fuera del horario" in t]
    assert closing and "08:00" in closing[0]
    assert "nocturna" in harness.chatwoot.labels[1]
    import json
    night = harness.events("night_capture")
    assert len(night) == 1 and json.loads(night[0]["payload"])["complete"] is True
    assert store.get_state(harness.db, 1).sla_started_at is None, "fuera de turno no corre el SLA"


async def test_handoff_assigns_team_and_opens_conversation(harness):
    await book(harness)
    await harness.say("1")
    assert harness.chatwoot.statuses[1] == "open"
    assert harness.chatwoot.assigned == [1]
    assert {"comercial"} <= harness.chatwoot.labels[1]
    note = harness.chatwoot.notes(1)[0]
    assert "2026-11-15" in note and "2 adultos" in note and "Doble Sin Vista" in note
    assert "Revalidar antes de confirmar" in note
    assert store.get_state(harness.db, 1).sla_started_at == harness.clock.now


async def test_duplicate_webhook_creates_single_event(harness):
    payload = harness.payload("¿tienen piscina?", message_id=77)
    await harness.core.handle_webhook(payload)
    await harness.core.handle_webhook(payload)
    assert len(harness.events("inbound")) == 1
    assert len(harness.events("faq_answered")) == 1


async def test_conversation_not_pending_is_ignored(harness):
    await harness.say("hola", status="open")
    assert harness.chatwoot.messages == []


async def test_numbered_fallback_on_channels_without_buttons(harness):
    await harness.say("hola", channel="Channel::Telegram")
    last = harness.chatwoot.messages[-1]
    assert last["options"] is None and "1. Ubicación" in last["content"]
    await harness.say("2", channel="Channel::Telegram")
    assert any("Nuestras habitaciones" in t for t in harness.chatwoot.guest_texts())


async def test_human_request_hands_off_with_note(harness):
    await harness.say("quiero hablar con una persona")
    assert harness.chatwoot.statuses[1] == "open"
    assert "pidió hablar con una persona" in harness.chatwoot.notes(1)[0]


async def test_faq_menu_flow_answers_by_number(harness):
    await harness.say("hola")
    await harness.say("Servicios y preguntas")
    await harness.say("1")
    assert any("piscina temperada" in t for t in harness.chatwoot.guest_texts())


async def test_unknown_text_falls_back_to_menu(harness):
    await harness.say("asdf qwer")
    assert any("No estoy seguro" in t for t in harness.chatwoot.guest_texts())


async def test_retention_purge_removes_old_personal_data(harness):
    await harness.say("¿tienen piscina?")
    await book(harness, conversation_id=2)
    harness.clock.advance(91 * 86400)
    result = store.purge_personal_data(harness.db, harness.clock(), 90)
    assert result["conversation_state"] == 2 and result["prebookings"] == 1
    assert harness.db.execute("SELECT COUNT(*) FROM conversation_state").fetchone()[0] == 0
    texts = [r["payload"] for r in harness.events("inbound")]
    assert all("text" not in t for t in texts)
    assert len(harness.events("faq_answered")) == 1, "los conteos agregados se conservan"


async def test_retention_purge_keeps_recent_data(harness):
    await harness.say("¿tienen piscina?")
    harness.clock.advance(10 * 86400)
    result = store.purge_personal_data(harness.db, harness.clock(), 90)
    assert result["conversation_state"] == 0
    assert "text" in harness.events("inbound")[0]["payload"]


async def test_date_formats_reach_guest_question(harness):
    for conversation_id, text in enumerate(["15/11 al 18/11", "del 15 al 18 de noviembre", "este finde"], start=10):
        await harness.say("quiero reservar", conversation_id=conversation_id)
        await harness.say(text, conversation_id=conversation_id)
        assert any("adultos" in t for t in harness.chatwoot.guest_texts(conversation_id)), text


async def test_human_request_with_partial_party_data_still_hands_off(harness):
    await harness.say("quiero reservar")
    await harness.say("15/11 al 18/11")
    await harness.say("2")
    await harness.say("recepción")
    assert harness.chatwoot.statuses[1] == "open" and harness.chatwoot.assigned == [1]
    assert "niños sin informar" in harness.chatwoot.notes(1)[0]


async def test_sold_out_reply_carries_the_reading_date(harness):
    harness.pms.offers = []
    await book(harness)
    text = next(t for t in harness.chatwoot.guest_texts() if "no veo cupo" in t)
    assert "28-10-2026 15:00" in text
    assert harness.chatwoot.statuses[1] == "open"


async def test_retention_purge_anonymizes_events_and_drops_identifiers(harness):
    import json
    await book(harness)
    await harness.say("1")
    await harness.core.on_booking_confirmed(1, 99)
    harness.clock.advance(91 * 86400)
    store.purge_personal_data(harness.db, harness.clock(), 90, "salt")
    assert harness.db.execute("SELECT COUNT(*) FROM events WHERE conversation_id = 1").fetchone()[0] == 0
    rows = harness.db.execute("SELECT conversation_id, kind, payload FROM events").fetchall()
    assert rows and all(row["conversation_id"] < 0 for row in rows)
    assert all("booking_id" not in json.loads(row["payload"]) for row in rows)
    assert len({row["conversation_id"] for row in rows}) == 1, "un mismo huésped conserva un solo seudónimo"


async def test_past_dates_are_rejected_without_reading_the_pms(harness):
    await harness.say("quiero reservar")
    await harness.say("01/01/2020 al 03/01/2020")
    assert any("ya pasaron" in t for t in harness.chatwoot.guest_texts())
    assert harness.pms.calls == 0
    assert store.get_state(harness.db, 1).step == "ask_dates"
