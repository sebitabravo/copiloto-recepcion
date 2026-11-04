import json

import httpx
import pytest
from copiloto.voice import CharBudget, ElevenLabsClient, TtsUnavailable, greeting, speakable


def test_greeting_always_says_it_is_a_virtual_assistant_and_offers_a_person():
    text = greeting("Hotel Boutique Bordeluz")
    assert "asistente virtual" in text and "Hotel Boutique Bordeluz" in text and "persona" in text
    assert "humano" not in text.lower()


def test_speakable_removes_lists_markdown_and_links():
    raw = ("Hay opciones:\n- **Doble con Jacuzzi** (32 m²): $80.000/noche, total $240.000\n"
           "- Single (18 m²): $65.000/noche\nMás en https://hotel.example/habitaciones")
    spoken = speakable(raw, 500)
    assert "- " not in spoken and "*" not in spoken and "http" not in spoken and "\n" not in spoken
    assert "te lo envío por escrito" in spoken
    assert "80.000 pesos" in spoken and "$" not in spoken and "metros cuadrados" in spoken


def test_speakable_cuts_at_a_sentence_boundary_within_the_limit():
    text = "Primera frase corta. Segunda frase un poco más larga que la anterior. Tercera frase final."
    spoken = speakable(text, 60)
    assert len(spoken) <= 60 and spoken.endswith(".") and spoken.startswith("Primera frase corta.")


def test_speakable_keeps_short_text_untouched_and_never_returns_empty_for_a_long_word():
    assert speakable("Con gusto.", 100) == "Con gusto."
    assert speakable("a" * 300, 100) != ""


def test_char_budget_blocks_over_the_limit_and_recovers_after_the_window():
    now = {"t": 0.0}
    budget = CharBudget(100, window_s=60, clock=lambda: now["t"])
    assert budget.take(60) and not budget.take(50) and budget.take(40)
    now["t"] = 61.0
    assert budget.take(100)


def client(handler, model="eleven_flash_v2_5"):
    return ElevenLabsClient("sk-test", "voz123", model, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def test_synthesize_posts_the_documented_request_and_returns_the_audio():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), key=request.headers["xi-api-key"], body=request.read())
        return httpx.Response(200, content=b"audio-mp3")

    audio = await client(handler).synthesize("Hola")
    assert audio == b"audio-mp3"
    assert seen["url"] == "https://api.elevenlabs.io/v1/text-to-speech/voz123?output_format=mp3_44100_64"
    assert seen["key"] == "sk-test"
    assert json.loads(seen["body"]) == {"text": "Hola", "model_id": "eleven_flash_v2_5", "language_code": "es"}


async def test_language_code_is_omitted_for_models_that_reject_it():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, content=b"x")

    await client(handler, model="eleven_multilingual_v2").synthesize("Hola")
    assert b"language_code" not in seen["body"]


async def test_synthesize_maps_provider_and_network_failures_to_one_error():
    for status in (401, 402, 422, 429, 500, 503):
        with pytest.raises(TtsUnavailable):
            await client(lambda request, status=status: httpx.Response(status, json={"detail": "x"})).synthesize("Hola")
    with pytest.raises(TtsUnavailable):
        await client(lambda request: httpx.Response(200, content=b"")).synthesize("Hola")

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    with pytest.raises(TtsUnavailable):
        await client(boom).synthesize("Hola")
