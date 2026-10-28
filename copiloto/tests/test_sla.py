import json

from copiloto.sla import SlaWorker

from copiloto import store


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
    assert json.loads(harness.events("booking_confirmed")[0]["payload"]) == {"booking_id": 55, "source": "personal"}
    assert any("Reserva #55" in n for n in harness.chatwoot.notes(1))


async def test_returning_guest_after_handoff_restarts_the_session(harness):
    await handed_off(harness)
    harness.clock.advance(400)
    await harness.say("hola otra vez", status="pending")
    assert any("Ubicación:" in t for t in harness.chatwoot.guest_texts()[-4:])
    state = store.get_state(harness.db, 1)
    assert state.sla_started_at is None and state.step == "menu"


async def test_human_reply_during_handoff_is_not_lost(harness):
    # Una respuesta humana que llega mientras el bot abre la conversación debe detener el reloj igual
    harness.chatwoot.during["set_status"] = lambda: harness.core.on_human_reply(1, 7, harness.clock() + 5)
    await handed_off(harness)
    state = store.get_state(harness.db, 1)
    assert state.sla_started_at is not None and state.sla_stopped_at is not None
    assert len(harness.events("human_first_reply")) == 1


async def test_sla_worker_does_not_overwrite_a_recorded_human_stop(harness, settings):
    await handed_off(harness)
    worker = SlaWorker(settings, harness.db, harness.chatwoot, harness.clock)
    harness.clock.advance(125)
    harness.chatwoot.during["add_labels"] = lambda: harness.core.on_human_reply(1, 7, harness.clock())
    await worker.tick()
    assert store.get_state(harness.db, 1).sla_stopped_at is not None
    harness.clock.advance(100)
    await worker.tick()
    assert "sla-vencido" not in harness.chatwoot.labels[1]


async def test_sla_starts_at_handoff_time_not_at_inbound_time(harness):
    await harness.say("quiero reservar")
    await harness.say("15/11 al 18/11")
    await harness.say("2")
    await harness.say("0")
    harness.chatwoot.during["set_status"] = lambda: None
    harness.clock.advance(30)
    await harness.say("1")
    assert store.get_state(harness.db, 1).sla_started_at == harness.clock.now


async def test_returning_guest_greeting_gets_the_menu_not_a_fallback(harness):
    await handed_off(harness)
    harness.clock.advance(400)
    await harness.say("hola", status="pending")
    assert not any("No estoy seguro" in t for t in harness.chatwoot.guest_texts())
    assert harness.chatwoot.messages[-1]["options"], "debe terminar en el menú"
    assert json.loads(harness.events("inbound")[-1]["payload"])["greeting"] is True


async def test_message_queued_behind_the_handoff_does_not_reset_the_clock(harness):
    await handed_off(harness)
    started = store.get_state(harness.db, 1).sla_started_at
    # Mensaje que llegó antes del traspaso (misma marca de tiempo) y recién se procesa
    await harness.say("gracias", status="pending")
    assert store.get_state(harness.db, 1).sla_started_at == started
    assert store.get_state(harness.db, 1).step == "handed_off"


async def test_sla_worker_survives_a_clock_cleared_mid_check(harness, settings):
    await handed_off(harness)
    worker = SlaWorker(settings, harness.db, harness.chatwoot, harness.clock)
    harness.clock.advance(200)
    harness.chatwoot.during["add_labels"] = lambda: store.clear_sla(harness.db, 1)
    await worker.tick()
    assert not any("SLA vencido" in n for n in harness.chatwoot.notes(1))


async def test_unexpected_failure_hands_off_with_note_and_events(harness):
    async def boom(*args):
        raise RuntimeError("falla inesperada")
    harness.pms.availability = boom
    await harness.say("quiero reservar")
    await harness.say("15/11 al 18/11")
    await harness.say("2")
    await harness.say("0")
    assert harness.chatwoot.statuses[1] == "open"
    assert any("falla técnica" in n for n in harness.chatwoot.notes(1))
    assert json.loads(harness.events("handoff")[0]["payload"])["reason"] == "error"
    assert store.get_state(harness.db, 1).sla_started_at is not None


async def test_handoff_is_atomic_when_a_write_fails_midway(harness, monkeypatch):
    await harness.say("quiero reservar")
    await harness.say("15/11 al 18/11")
    await harness.say("2")
    await harness.say("0")
    original = store.start_sla

    calls = []

    def boom_once(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("falla a mitad del traspaso")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "start_sla", boom_once)
    await harness.say("1")
    assert len(harness.events("handoff")) == 1, "solo el traspaso del fallback; el fallido hizo rollback"
    assert json.loads(harness.events("handoff")[0]["payload"])["reason"] == "error"
