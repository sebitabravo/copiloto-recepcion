"""Upstream free voice and sandbox booking permissions remain independent."""
from dataclasses import replace

import pytest
from copiloto.app import create_app
from fastapi.testclient import TestClient


@pytest.mark.parametrize("pms_url,can_book", [
    ("http://pms-mock:8200", True),
    ("https://pms.example", False),
])
def test_free_voice_survives_sandbox_policy_integration(make_ai, pms_url, can_book):
    h, _ = make_ai([])
    settings = replace(h.settings, pms_url=pms_url)
    app = create_app(settings, chatwoot=h.chatwoot, pms=h.pms, clock=h.clock,
                     run_workers=False, db=h.db, llm_agent=h.core.agent)
    with TestClient(app) as client:
        response = client.get("/api/demo/status")
    assert response.status_code == 200
    status = response.json()
    assert status["mode"] == "full"
    assert status["voice"] is True and status["tts"] == "browser"
    assert status["sandbox"] is can_book and status["autonomous_booking"] is can_book
    assert h.pms.bookings == []
