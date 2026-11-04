"""Respaldo local con Piper: voz en WAV sin API de pago. El motor se carga solo si el modelo está configurado."""

import io
import wave

import pytest
from copiloto.voice import PiperClient, TtsUnavailable


class FakePiperVoice:
    def __init__(self):
        self.calls: list[str] = []

    def synthesize(self, text, wav_file, **kwargs):
        self.calls.append(text)
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(22050)
        wav_file.writeframes(b"\x00\x00" * 2205)


async def test_piper_returns_wav_audio_for_spanish():
    voice = FakePiperVoice()
    audio = await PiperClient("model.onnx", voice_factory=lambda: voice).synthesize("Hola", language="es")
    assert audio[:4] == b"RIFF" and voice.calls == ["Hola"]
    with wave.open(io.BytesIO(audio)) as wav:
        assert wav.getframerate() == 22050


async def test_piper_refuses_english_because_its_voice_is_spanish():
    piper = PiperClient("model.onnx", voice_factory=FakePiperVoice)
    with pytest.raises(TtsUnavailable):
        await piper.synthesize("Hello", language="en")


async def test_piper_load_or_synthesis_failures_become_tts_unavailable():
    def broken():
        raise RuntimeError("modelo corrupto")

    with pytest.raises(TtsUnavailable):
        await PiperClient("model.onnx", voice_factory=broken).synthesize("Hola", language="es")
