from dataclasses import replace

import pytest
from conftest import call, say
from copiloto.ai.sessions import AiSession
from copiloto.ai.tools import ToolHooks, ToolRunner
from test_booking_proposal import BOOK, STAY, prepare


@pytest.mark.anyio
@pytest.mark.parametrize("authorized", [False, None, 1, "true"])
async def test_denial_withholds_booking_tool_and_full_prompt(make_ai, authorized):
    h, llm = make_ai([call("check_availability", **STAY), call("create_booking", **BOOK), say("Opciones")])
    result = await h.core.agent.respond(AiSession("demo:sandbox"), "Soy Camila Rojas", ToolHooks(
        extra={"sandbox_only": True, "sandbox_authorized": authorized}))
    assert h.pms.bookings == [] and result.booking is None
    assert "create_booking" not in llm.calls[0]["tools"]
    assert "MODO ASISTIDO" in llm.calls[0]["messages"][0]["content"]


async def test_sandbox_requires_simulated_reading(make_ai):
    h, _ = make_ai([])
    original = h.pms.availability

    async def real(*args):
        return replace(await original(*args), simulated=False)

    h.pms.availability = real
    runner = ToolRunner(h.hotel, h.pms, h.settings, h.clock,
                        AiSession("demo:real", state={"last_user_text": "Sí, soy Camila Rojas"}),
                        ToolHooks(extra={"sandbox_only": True, "sandbox_authorized": True}))
    await runner.run("check_availability", STAY)
    result = await runner.run("create_booking", BOOK)
    assert not result.ok and h.pms.bookings == []


async def test_handoff_without_callback_never_claims_notification(make_ai):
    h, _ = make_ai([])
    runner = ToolRunner(h.hotel, h.pms, h.settings, h.clock, AiSession("demo:handoff"), ToolHooks())
    result = await runner.run("handoff_to_human", {})
    assert result.data["avisado"] is False and result.data["simulado"] is True
    assert "simulad" in result.summary.lower()


async def test_authorized_simulated_demo_retains_full_booking_mode(make_ai):
    hooks = ToolHooks(extra={"sandbox_only": True, "sandbox_authorized": True})
    h, llm, session, result = await prepare(make_ai, hooks)
    assert result.booking is None and "create_booking" in llm.calls[0]["tools"]
    llm.script.extend([call("create_booking", **BOOK), say("Listo")])
    result = await h.core.agent.respond(session, "Sí", hooks)
    assert len(h.pms.bookings) == 1 and result.booking


async def test_voice_remains_assisted_even_after_a_text_proposal(make_ai):
    h, llm, session, _ = await prepare(make_ai)
    llm.script.extend([call("create_booking", **BOOK), say("Recepción te ayuda.")])
    result = await h.core.agent.respond(session, "Sí", ToolHooks(), voice=True)
    assert h.pms.bookings == [] and result.booking is None
    assert "create_booking" not in llm.calls[-1]["tools"]
    assert "MODO VOZ" in llm.calls[-1]["messages"][0]["content"]
