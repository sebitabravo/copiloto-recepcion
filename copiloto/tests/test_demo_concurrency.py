"""Deterministic ordering tests through the public demo routes, with no external calls."""

import asyncio
from dataclasses import replace

import httpx
import pytest
from conftest import FakeLlm, say
from copiloto.ai.agent import Agent
from copiloto.app import create_app

SESSION = "concurrency-session-0123456789"


class GatedLlm(FakeLlm):
    def __init__(self):
        super().__init__([say("First."), say("Next."), say("Third.")])
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.block = True

    async def chat(self, *args, **kwargs):
        if self.block:
            self.block = False
            self.entered.set()
            await self.release.wait()
        return await super().chat(*args, **kwargs)


def application(settings, harness, llm):
    agent = Agent(llm, harness.hotel, harness.pms, settings, harness.clock)
    return create_app(settings, chatwoot=harness.chatwoot, pms=harness.pms, clock=harness.clock,
                      run_workers=False, db=harness.db, llm_agent=agent)


@pytest.mark.parametrize("route", ["/api/demo/chat", "/api/demo/voice"])
@pytest.mark.anyio
async def test_reset_waits_for_active_turn_and_never_resurrects_history(ai_settings, harness, route):
    from test_demo_voice import FakeTts

    llm = GatedLlm()
    app = application(ai_settings, harness, llm)
    if route.endswith("voice"):
        agent = Agent(llm, harness.hotel, harness.pms, ai_settings, harness.clock)
        app = create_app(ai_settings, chatwoot=harness.chatwoot, pms=harness.pms, clock=harness.clock,
                         run_workers=False, db=harness.db, llm_agent=agent, tts=FakeTts())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        first = asyncio.create_task(client.post(route, json={"session_id": SESSION, "message": "old message"}))
        await asyncio.wait_for(llm.entered.wait(), 2)
        reset = asyncio.create_task(client.post("/api/demo/reset", json={"session_id": SESSION}))
        # A separate request is a deterministic scheduling barrier; sessions must stay independent.
        other = await client.post("/api/demo/chat", json={"session_id": SESSION + "-other", "message": "other"})
        assert other.status_code == 200
        try:
            assert not reset.done(), "reset must wait for the in-flight session turn"
        finally:
            llm.release.set()
            responses = await asyncio.gather(first, reset)
        assert [response.status_code for response in responses] == [200, 200]
        fresh = await client.post("/api/demo/chat", json={"session_id": SESSION, "message": "fresh message"})
        assert fresh.status_code == 200 and fresh.json()["usage"]["messages_left"] == 29
        assert "old message" not in str(llm.calls[-1]["messages"])


async def test_same_session_text_turns_share_quota_and_history(ai_settings, harness):
    llm = GatedLlm()
    settings = replace(ai_settings, demo_messages_per_session=1)
    app = application(settings, harness, llm)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        body = {"session_id": SESSION, "message": "hello"}
        first = asyncio.create_task(client.post("/api/demo/chat", json=body))
        await asyncio.wait_for(llm.entered.wait(), 2)
        second = asyncio.create_task(client.post("/api/demo/chat", json=body))
        llm.release.set()
        responses = await asyncio.gather(first, second)
        assert [response.status_code for response in responses] == [200, 429]
        assert len(llm.calls) == 1


@pytest.mark.parametrize("url,authorized", [("http://pms-mock:8200/", True), ("https://real.example", False)])
@pytest.mark.parametrize("route", ["/api/demo/chat", "/api/demo/voice"])
@pytest.mark.anyio
async def test_demo_status_and_all_agent_hooks_enforce_sandbox_policy(ai_settings, harness, url, authorized, route):
    from types import SimpleNamespace

    from test_demo_voice import FakeTts

    class RecordingAgent:
        async def respond(self, session, message, hooks, voice=False):
            assert hooks.extra == {"sandbox_only": True, "sandbox_authorized": authorized}
            return SimpleNamespace(reply="Hello.", quick_replies=[], events=[], llm_ms=0, tokens=0,
                                   tools=[], guardrails=[], booking=None)

    settings = replace(ai_settings, pms_url=url)
    app = create_app(settings, chatwoot=harness.chatwoot, pms=harness.pms, clock=harness.clock,
                     run_workers=False, db=harness.db, llm_agent=RecordingAgent(), tts=FakeTts())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        status = (await client.get("/api/demo/status")).json()
        assert status["mode"] == "full" and status["sandbox"] is authorized
        assert status["autonomous_booking"] is authorized
        response = await client.post(route, json={"session_id": SESSION, "message": "hello"})
        assert response.status_code == 200 and response.json()["reply"] == "Hello."
        assert harness.pms.bookings == []
