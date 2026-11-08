"""Puente OpenWA <-> Chatwoot para el canal de WhatsApp de la demo.

Canal NO oficial (WhatsApp Web automatizado): solo para la demo, con un número dedicado.
Ver docs/whatsapp-demo.md.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import sqlite3
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from . import store
from .bridge import Bridge
from .chatwoot import ChatwootClient
from .config import Settings
from .openwa import OpenWAClient, verify_openwa_signature
from .transcribe import WhisperTranscriber

logger = logging.getLogger(__name__)

DEDUPE_RETENTION_S = 30 * 86400
MAPPING_RETENTION_S = 90 * 86400  # igual que la retención del copiloto (data/hotel.yaml: privacy.retention_days)
# Las purgas al arrancar dejan crecer la base en un proceso vivo: se repiten periódicamente.
PURGE_INTERVAL_S = 6 * 3600


def verify_chatwoot_signature(secret: str, headers, raw_body: bytes, now: float, tolerance_s: int) -> bool:
    """Firma de Chatwoot: sha256(secret, '<timestamp>.<body>'). Sin secreto, rechaza todo."""
    timestamp = headers.get("x-chatwoot-timestamp", "")
    signature = headers.get("x-chatwoot-signature", "")
    if not secret or not timestamp.isdigit() or not signature or abs(now - int(timestamp)) > tolerance_s:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), signature.encode())


async def read_capped(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > limit):
        raise HTTPException(status_code=413, detail="Cuerpo demasiado grande")
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail="Cuerpo demasiado grande")
        chunks.append(chunk)
    return b"".join(chunks)


def parse_json(raw: bytes) -> dict:
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="JSON inválido") from None
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail="JSON inválido")
    return event


def purge_once(db: sqlite3.Connection, now: float) -> int:
    """Una pasada de purga: dedupe vencido y mapeos sin actividad dentro de su retención."""
    purged = store.purge_processed(db, now - DEDUPE_RETENTION_S)
    store.purge_mappings(db, now - MAPPING_RETENTION_S)
    return purged


def create_app(settings: Settings | None = None, bridge: Bridge | None = None, clock=time.time) -> FastAPI:
    settings = settings or Settings.from_env()
    missing = [
        name
        for name, value in (
            ("CHATWOOT_ADMIN_TOKEN", settings.chatwoot_admin_token),
            ("CHATWOOT_WA_INBOX_SECRET", settings.inbox_secret),
        )
        if not value.strip()
    ]
    if missing:
        # Falla rápido como el copiloto: con un secreto vacío cada webhook de Chatwoot responde 401
        # mientras /health sigue ok, y el canal queda muerto en silencio.
        raise ValueError("Secretos de Chatwoot ausentes (el webhook respondería 401 a todo): " + ", ".join(missing))
    if bridge is None:
        db = store.connect(settings.db_path)
        purge_once(db, clock())
        transcriber = None
        if settings.voice_notes:
            transcriber = WhisperTranscriber(
                model_size=settings.whisper_model,
                cache_dir=settings.whisper_cache_dir,
                max_seconds=settings.voice_max_seconds,
            )
        bridge = Bridge(
            settings,
            db,
            ChatwootClient(
                settings.chatwoot_url,
                settings.inbox_identifier,
                settings.chatwoot_account_id,
                settings.chatwoot_admin_token,
            ),
            OpenWAClient(settings.openwa_url, settings.openwa_api_key),
            clock,
            transcriber=transcriber,
        )

    async def purge_periodically():
        while True:
            await asyncio.sleep(PURGE_INTERVAL_S)
            try:
                purge_once(bridge.db, clock())
            except Exception:
                logger.exception("Falló la purga periódica; se reintentará en el próximo ciclo")

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        purge_task = asyncio.create_task(purge_periodically())
        try:
            yield
        finally:
            purge_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await purge_task

    app = FastAPI(title="Puente WhatsApp · OpenWA", lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/webhooks/openwa")
    async def openwa_webhook(request: Request, background: BackgroundTasks):
        raw = await read_capped(request, settings.max_body_bytes)
        if not verify_openwa_signature(
            settings.openwa_webhook_secret, raw, request.headers.get("x-openwa-signature", "")
        ):
            raise HTTPException(status_code=401, detail="Firma inválida")
        background.add_task(bridge.handle_openwa, parse_json(raw))
        return {"status": "accepted"}

    @app.post("/webhooks/chatwoot")
    async def chatwoot_webhook(request: Request, background: BackgroundTasks):
        raw = await read_capped(request, settings.max_body_bytes)
        if not verify_chatwoot_signature(
            settings.inbox_secret, request.headers, raw, clock(), settings.signature_tolerance_s
        ):
            raise HTTPException(status_code=401, detail="Firma inválida")
        background.add_task(bridge.handle_chatwoot, parse_json(raw))
        return {"status": "accepted"}

    return app
