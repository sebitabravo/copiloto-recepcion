import json

from copiloto import store
from copiloto.sla import SlaWorker


async def handed_off(h):
    await h.say("quiero reservar")
    await h.say("15/11 al 18/11")
    await h.say("2")
    await h.say("0")
    await h.say("1")


async def test_sla_amber_120_red_180(harness, settings):
    await handed_off(harness)
    worker = SlaWorker(settings, harness.db, harness.chatwoot, harness.clock)
    harness.clock.advance(119)
    await worker.tick()
    assert "sla-ambar" not in harness.chatwoot.labels[1]
    harness.clock.advance(1)
    await worker.tick()
    assert "sla-ambar" in harness.chatwoot.labels[1]
    assert "sla-vencido" not in harness.chatwoot.labels[1]
    harness.clock.advance(59)
    await worker.tick()
    assert "sla-vencido" not in harness.chatwoot.labels[1]
    harness.clock.advance(1)
    await worker.tick()
    assert "sla-vencido" in harness.chatwoot.labels[1]
    assert any("SLA vencido" in n for n in harness.chatwoot.notes(1))
    notes_before = len(harness.chatwoot.notes(1))
    harness.clock.advance(60)
    await worker.tick()
    assert len(harness.chatwoot.notes(1)) == notes_before, "la alerta se emite una sola vez"


async def test_sla_clock_not_reset_on_assignment(harness):
    await handed_off(harness)
    started = store.get_state(harness.db, 1).sla_started_at
    harness.clock.advance(50)
    await harness.core.handle_webhook({"event": "conversation_updated", "conversation": {"id": 1}})
    await harness.core.handle_webhook({"event": "conversation_status_changed", "conversation": {"id": 1}})
    await harness.say("necesito hablar con recepción", status="open")
    assert store.get_state(harness.db, 1).sla_started_at == started


async def test_human_reply_stops_clock_and_records_event(harness, settings):
    await handed_off(harness)
    harness.clock.advance(42)
    await harness.say("Hola, soy de recepción", message_type="outgoing", sender_type="user", status="open")
    state = store.get_state(harness.db, 1)
    assert state.sla_stopped_at - state.sla_started_at == 42
    events = harness.events("human_first_reply")
    assert len(events) == 1
    harness.clock.advance(300)
    worker = SlaWorker(settings, harness.db, harness.chatwoot, harness.clock)
    await worker.tick()
    assert harness.chatwoot.labels[1].isdisjoint({"sla-ambar", "sla-vencido"})
    await harness.say("segunda respuesta", message_type="outgoing", sender_type="user", status="open")
    assert len(harness.events("human_first_reply")) == 1


async def test_bot_and_private_messages_do_not_stop_clock(harness):
    await handed_off(harness)
    await harness.say("respuesta del bot", message_type="outgoing", sender_type="agent_bot", status="open")
    await harness.say("nota interna", message_type="outgoing", sender_type="user", private=True, status="open")
    assert store.get_state(harness.db, 1).sla_stopped_at is None
    assert harness.events("human_first_reply") == []


async def test_booking_confirmed_event_marks_prebooking_converted(harness):
    await handed_off(harness)
    await harness.core.on_booking_confirmed(1, 55)
    assert store.active_prebooking(harness.db, 1)["status"] == "converted"
    assert json.loads(harness.events("booking_confirmed")[0]["payload"]) == {"booking_id": 55}
    assert any("Reserva #55" in n for n in harness.chatwoot.notes(1))


async def test_returning_guest_after_handoff_restarts_the_session(harness):
    await handed_off(harness)
    harness.clock.advance(400)
    await harness.say("hola otra vez", status="pending")
    assert any("Ubicación:" in t for t in harness.chatwoot.guest_texts()[-4:])
    state = store.get_state(harness.db, 1)
    assert state.sla_started_at is None and state.step == "menu"
