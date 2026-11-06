"""Transcripción local de notas de voz con Whisper (faster-whisper, MIT). Sin API de pago.

El audio se escribe en un directorio temporal y se borra al terminar, aunque la transcripción falle.
Nunca se guarda el texto ni el audio en la base de datos.
"""

import asyncio
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path


class AudioTooLong(ValueError):
    pass


class WhisperTranscriber:
    def __init__(self, model_size: str = "small", cache_dir: str | None = None, max_seconds: float = 60.0,
                 tmp_dir: str | None = None, model_factory: Callable[[], object] | None = None):
        self._size = model_size
        self._cache_dir = cache_dir
        self._max_seconds = max_seconds
        self._tmp_dir = tmp_dir
        self._factory = model_factory or self._default_factory
        self._model = None
        self._lock = threading.Lock()

    def _default_factory(self):
        from faster_whisper import WhisperModel
        # int8 en CPU: el servidor del hotel no tiene GPU
        return WhisperModel(self._size, device="cpu", compute_type="int8", download_root=self._cache_dir)

    def _get_model(self):
        with self._lock:
            if self._model is None:
                self._model = self._factory()
            return self._model

    def _transcribe_sync(self, audio: bytes) -> str:
        with tempfile.TemporaryDirectory(dir=self._tmp_dir) as folder:
            path = Path(folder) / "nota.ogg"
            path.write_bytes(audio)
            segments, info = self._get_model().transcribe(str(path), language="es", beam_size=1, vad_filter=True)
            if info.duration > self._max_seconds:
                raise AudioTooLong(f"nota de {info.duration:.0f} s, máximo {self._max_seconds:.0f} s")
            return " ".join(segment.text.strip() for segment in segments).strip()

    async def __call__(self, audio: bytes) -> str:
        return await asyncio.to_thread(self._transcribe_sync, audio)
