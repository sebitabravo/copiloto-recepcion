"""Voz de la demo: convierte en audio lo que el servidor decide decir, nunca texto arbitrario del navegador.

El saludo es una constante (no pasa por el modelo) para que siempre diga que es un asistente virtual.
"""

import re
import time
from collections import deque
from collections.abc import Callable

import httpx

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
# Estos modelos aceptan `language_code`; multilingual_v2 lo rechaza
LANGUAGE_MODELS = ("eleven_flash", "eleven_turbo", "eleven_v3")

URL = re.compile(r"https?://\S+|www\.\S+")
PRICE = re.compile(r"\$\s?(\d{1,3}(?:\.\d{3})+|\d+)")
BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.MULTILINE)
MARKDOWN = re.compile(r"[*_`#>]+")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class TtsUnavailable(Exception):
    """El proveedor de voz no respondió o rechazó la solicitud; el huésped sigue con el texto."""


def greeting(hotel_name: str) -> str:
    return (f"Hola, soy el asistente virtual del {hotel_name}. Puedo ayudarte con información y disponibilidad; "
            "recepción confirma cualquier reserva. Mantén presionado el botón para hablar, o dime si prefieres "
            "que te pase con una persona.")


def speakable(text: str, max_chars: int) -> str:
    """Texto apto para leer en voz alta: sin listas, markdown ni enlaces, y con un largo acotado."""
    text = URL.sub("te lo envío por escrito", text)
    text = PRICE.sub(lambda match: f"{match.group(1)} pesos", text)
    text = text.replace("m²", "metros cuadrados")
    text = BULLET.sub("", text)
    text = MARKDOWN.sub("", text)
    text = re.sub(r"\s*\n+\s*", ". ", text)
    text = re.sub(r"\.\s*\.", ".", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if len(text) <= max_chars:
        return text
    kept = ""
    for sentence in SENTENCE_END.split(text):
        if len(kept) + len(sentence) + 1 > max_chars:
            break
        kept = f"{kept} {sentence}".strip()
    return kept or text[:max_chars].rsplit(" ", 1)[0]


class CharBudget:
    """Tope de caracteres sintetizados por ventana: protege los créditos del plan de ElevenLabs."""

    def __init__(self, max_chars: int, window_s: float = 3600.0, clock: Callable[[], float] | None = None):
        self.max_chars, self.window_s, self.clock = max_chars, window_s, clock or time.time
        self._spent: deque[tuple[float, int]] = deque()

    def take(self, chars: int) -> bool:
        now = self.clock()
        while self._spent and now - self._spent[0][0] >= self.window_s:
            self._spent.popleft()
        if sum(amount for _, amount in self._spent) + chars > self.max_chars:
            return False
        self._spent.append((now, chars))
        return True


class ElevenLabsClient:
    def __init__(self, api_key: str, voice_id: str, model: str, http: httpx.AsyncClient | None = None,
                 timeout_s: float = 15.0):
        self._url = TTS_URL.format(voice_id=voice_id)
        self._headers = {"xi-api-key": api_key, "Content-Type": "application/json", "Accept": "audio/mpeg"}
        self._model = model
        self._http = http or httpx.AsyncClient(timeout=timeout_s)

    async def synthesize(self, text: str) -> bytes:
        body: dict = {"text": text, "model_id": self._model}
        if self._model.startswith(LANGUAGE_MODELS):
            body["language_code"] = "es"
        try:
            response = await self._http.post(self._url, params={"output_format": "mp3_44100_64"},
                                             json=body, headers=self._headers)
        except httpx.HTTPError as exc:
            raise TtsUnavailable(type(exc).__name__) from None
        if response.status_code != 200 or not response.content:
            raise TtsUnavailable(f"http {response.status_code}")
        return response.content
