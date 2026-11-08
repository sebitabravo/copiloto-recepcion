"""Configuración del puente leída del entorno. Los secretos vacíos hacen que el puente rechace todo."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    openwa_url: str
    openwa_api_key: str
    openwa_webhook_secret: str
    chatwoot_url: str
    chatwoot_account_id: int
    chatwoot_admin_token: str
    inbox_identifier: str
    inbox_secret: str
    db_path: str
    retry_delays_s: tuple[float, ...] = (1.0, 3.0)
    # Notas de voz: transcripción local (Whisper). Apagada por defecto.
    voice_notes: bool = False
    whisper_model: str = "small"
    whisper_cache_dir: str = "/var/lib/wa-bridge/models"
    voice_max_seconds: float = 60.0
    max_voice_bytes: int = 1_000_000
    # Ventana para reordenar por id las respuestas que Chatwoot entrega en jobs paralelos
    reorder_window_s: float = 0.4
    max_body_bytes: int = 1_000_000
    max_text_chars: int = 1000
    signature_tolerance_s: int = 300

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ
        return cls(
            openwa_url=env.get("OPENWA_API_URL", "http://openwa:2785").rstrip("/"),
            openwa_api_key=env.get("OPENWA_API_KEY", ""),
            openwa_webhook_secret=env.get("OPENWA_WEBHOOK_SECRET", ""),
            chatwoot_url=env.get("CHATWOOT_URL", "http://chatwoot:3000").rstrip("/"),
            chatwoot_account_id=int(env.get("CHATWOOT_ACCOUNT_ID", "1")),
            chatwoot_admin_token=env.get("CHATWOOT_ADMIN_TOKEN", ""),
            inbox_identifier=env.get("CHATWOOT_WA_INBOX_IDENTIFIER", ""),
            inbox_secret=env.get("CHATWOOT_WA_INBOX_SECRET", ""),
            db_path=env.get("WA_BRIDGE_DB_PATH", "/var/lib/wa-bridge/bridge.sqlite"),
            voice_notes=env.get("VOICE_NOTES", "0").strip().lower() in ("1", "true", "yes"),
            whisper_model=env.get("WHISPER_MODEL", "small"),
            whisper_cache_dir=env.get("WHISPER_CACHE_DIR", "/var/lib/wa-bridge/models"),
        )
