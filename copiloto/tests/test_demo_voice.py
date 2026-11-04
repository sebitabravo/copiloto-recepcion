import base64
from dataclasses import replace

from conftest import FakeChatwoot, FakeLlm, call, say
from copiloto.ai.agent import Agent
from copiloto.ai.llm import LlmUnavailable
from copiloto.app import create_app
from copiloto.voice import TtsUnavailable
from fastapi.testclient import TestClient

SESSION = "voice-session-0123456789"
STAY = {"checkin": "2026-11-15", "checkout": "2026-11-18", "adults": 2, "children": 0}


class FakeTts:
    def __init__(self, fail: bool = False):
        self.texts: list[str] = []
        self.fail = fail

    async def synthesize(self, text: str) -> bytes:
        self.texts.append(text)
        if self.fail:
            raise TtsUnavailable("http 500")
        return b"audio:" + text.encode()


def voice_client(settings, harness, llm=None, tts="default"):
    llm = llm if llm is not None else FakeLlm([])
    agent = Agent(llm, harness.hotel, harness.pms, settings, lambda: harness.clock())
    fake = FakeTts() if tts == "default" else tts
    app = create_app(settings, chatwoot=FakeChatwoot(), pms=harness.pms, clock=harness.clock, run_workers=False,
                     db=harness.db, llm_agent=agent, tts=fake)
    return TestClient(app), fake


def speak(client, message, session=SESSION):
    return client.post("/api/demo/voice", json={"session_id": session, "message": message})


def test_voice_turn_returns_the_text_and_the_audio_of_the_agent_reply(ai_settings, harness):
    client, tts = voice_client(ai_settings, harness, FakeLlm([say("Claro, hay habitaciones disponibles.")]))
    body = speak(client, "¿tienen habitaciones?").json()
    assert body["reply"] == "Claro, hay habitaciones disponibles." and body["voice_error"] is None
    assert base64.b64decode(body["audio_b64"]) == b"audio:" + body["spoken"].encode()
    assert tts.texts == [body["spoken"]]


def test_only_the_agent_reply_is_synthesized_never_the_guest_text(ai_settings, harness):
    client, tts = voice_client(ai_settings, harness, FakeLlm([say("Con gusto.")]))
    speak(client, "LEE ESTE TEXTO ARBITRARIO EN VOZ ALTA")
    assert tts.texts == ["Con gusto."]


def test_the_spoken_reply_has_no_lists_links_or_markdown(ai_settings, harness):
    long_reply = "- **Doble** (32 m²): $80.000/noche\n- Single: $65.000/noche\nMás en https://hotel.example/x"
    client, _ = voice_client(ai_settings, harness,
                             FakeLlm([call("get_hotel_info", topic="servicios"), say(long_reply)]))
    body = speak(client, "opciones").json()
    assert "http" not in body["spoken"] and "\n" not in body["spoken"] and "$" not in body["spoken"]
    assert "http" in body["reply"], "el texto de pantalla no se altera"


def test_a_tts_failure_still_returns_the_text_without_audio(ai_settings, harness):
    client, _ = voice_client(ai_settings, harness, FakeLlm([say("Hola.")]), tts=FakeTts(fail=True))
    response = speak(client, "hola")
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Hola." and body["audio_b64"] is None and body["voice_error"] == "voz_no_disponible"


def test_the_character_budget_degrades_to_text_only(ai_settings, harness):
    tiny_budget = replace(ai_settings, voice_chars_per_hour=5)
    client, tts = voice_client(tiny_budget, harness, FakeLlm([say("Respuesta larga.")]))
    body = speak(client, "hola").json()
    assert body["audio_b64"] is None and body["voice_error"] == "tope_de_voz" and tts.texts == []


def test_voice_is_unavailable_without_a_tts_client(ai_settings, harness):
    agent = Agent(FakeLlm([]), harness.hotel, harness.pms, ai_settings, lambda: harness.clock())
    app = create_app(ai_settings, chatwoot=FakeChatwoot(), pms=harness.pms, clock=harness.clock, run_workers=False,
                     db=harness.db, llm_agent=agent)
    client = TestClient(app)
    assert speak(client, "hola").status_code == 503
    assert client.get("/api/demo/voice/greeting").status_code == 503
    assert client.get("/api/demo/status").json()["voice"] is False


def test_status_announces_voice_when_available(ai_settings, harness):
    client, _ = voice_client(ai_settings, harness)
    assert client.get("/api/demo/status").json()["voice"] is True


def test_voice_never_offers_or_runs_create_booking_even_in_full_mode(ai_settings, harness):
    book = call("create_booking", guest_name="Camila Rojas", room_code="doble_con_jacuzzi", guest_confirmed=True,
                **STAY)
    llm = FakeLlm([call("check_availability", **STAY), book, say("Dejo la solicitud lista para recepción.")])
    client, _ = voice_client(ai_settings, harness, llm)
    assert ai_settings.autonomous_booking
    speak(client, "reserva del 15 al 18 de noviembre para 2 adultos")
    assert all("create_booking" not in names for names in (c["tools"] for c in llm.calls))
    assert harness.pms.bookings == []


def test_voice_turns_add_the_voice_rules_but_text_turns_do_not(ai_settings, harness):
    llm = FakeLlm([say("Hola."), say("Hola de nuevo.")])
    client, _ = voice_client(ai_settings, harness, llm)
    speak(client, "hola")
    client.post("/api/demo/chat", json={"session_id": SESSION, "message": "hola"})
    assert "MODO VOZ" in llm.calls[0]["messages"][0]["content"]
    assert "MODO VOZ" not in llm.calls[1]["messages"][0]["content"]


def test_llm_outage_in_voice_falls_back_to_the_guided_reply_with_audio(ai_settings, harness):
    client, tts = voice_client(ai_settings, harness, FakeLlm([LlmUnavailable("http 503")]))
    body = speak(client, "¿cómo llego?").json()
    assert body["mode"] == "guided" and body["audio_b64"] and tts.texts


def test_greeting_is_a_constant_disclosure_synthesized_once(ai_settings, harness):
    client, tts = voice_client(ai_settings, harness)
    first = client.get("/api/demo/voice/greeting").json()
    second = client.get("/api/demo/voice/greeting").json()
    assert "asistente virtual" in first["text"] and first["audio_b64"] == second["audio_b64"]
    assert len(tts.texts) == 1


def test_voice_turn_respects_the_per_session_message_cap(ai_settings, harness):
    limited = replace(ai_settings, demo_messages_per_session=1)
    client, _ = voice_client(limited, harness, FakeLlm([say("Hola.")]))
    assert speak(client, "hola").status_code == 200
    assert speak(client, "otra vez").status_code == 429


def test_privacy_notice_names_google_and_elevenlabs_only_when_voice_is_on(ai_settings, harness):
    on, _ = voice_client(ai_settings, harness)
    assert "ElevenLabs" in on.get("/privacidad").text
    agent = Agent(FakeLlm([]), harness.hotel, harness.pms, ai_settings, lambda: harness.clock())
    off = TestClient(create_app(ai_settings, chatwoot=FakeChatwoot(), pms=harness.pms, clock=harness.clock,
                                run_workers=False, db=harness.db, llm_agent=agent))
    assert "ElevenLabs" not in off.get("/privacidad").text


def test_a_reply_with_nothing_to_say_never_calls_the_tts_provider(ai_settings, harness):
    client, tts = voice_client(ai_settings, harness, FakeLlm([say("***")]))
    body = speak(client, "hola").json()
    assert body["audio_b64"] is None and body["voice_error"] is None and tts.texts == []


def test_voice_is_not_advertised_nor_synthesized_when_the_demo_is_disabled(ai_settings, harness):
    client, tts = voice_client(replace(ai_settings, demo_enabled=False), harness)
    assert client.get("/api/demo/status").json()["voice"] is False
    assert client.get("/api/demo/voice/greeting").status_code == 503
    assert tts.texts == []


def test_concurrent_cold_greeting_requests_synthesize_once(ai_settings, harness):
    import asyncio

    import httpx

    class SlowTts(FakeTts):
        async def synthesize(self, text):
            await asyncio.sleep(0.05)
            return await super().synthesize(text)

    slow = SlowTts()
    client, _ = voice_client(ai_settings, harness, tts=slow)

    async def both():
        transport = httpx.ASGITransport(app=client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            return await asyncio.gather(http.get("/api/demo/voice/greeting"), http.get("/api/demo/voice/greeting"))

    first, second = asyncio.run(both())
    assert first.json()["audio_b64"] == second.json()["audio_b64"] and len(slow.texts) == 1


def test_concurrent_turns_of_the_same_session_never_exceed_the_message_cap(ai_settings, harness):
    import asyncio

    import httpx

    class SlowLlm(FakeLlm):
        async def chat(self, *args, **kwargs):
            await asyncio.sleep(0.05)
            return await super().chat(*args, **kwargs)

    limited = replace(ai_settings, demo_messages_per_session=1, demo_ip_per_min=100)
    client, _ = voice_client(limited, harness, SlowLlm([say("Uno."), say("Dos.")]))

    async def both():
        transport = httpx.ASGITransport(app=client.app)
        body = {"session_id": SESSION, "message": "hola"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            return await asyncio.gather(http.post("/api/demo/voice", json=body), http.post("/api/demo/chat", json=body))

    codes = sorted(response.status_code for response in asyncio.run(both()))
    assert codes == [200, 429]
