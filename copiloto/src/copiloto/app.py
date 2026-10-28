"""Aplicación FastAPI del copiloto: webhooks, panel, métricas y aviso de privacidad."""

import asyncio
import hashlib
import hmac
import json
import logging
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from copiloto import privacy, store
from copiloto.chatwoot import ChatwootClient
from copiloto.config import Settings
from copiloto.events import connect, init_db
from copiloto.flow import Copiloto
from copiloto.hotel import HotelData
from copiloto.pms import MockPxsolAdapter, PmsAdapter
from copiloto.ratelimit import SlidingWindowLimiter
from copiloto.sla import SlaWorker

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
PURGE_INTERVAL_S = 86400


def verify_signature(settings: Settings, headers, raw_body: bytes, now: float) -> bool:
    """Valida la firma HMAC de Chatwoot: sha256(secret, '<timestamp>.<body>'). Sin secreto, rechaza todo."""
    secret = settings.webhook_secret
    timestamp = headers.get("x-chatwoot-timestamp", "")
    signature = headers.get("x-chatwoot-signature", "")
    if not secret or not timestamp.isdigit() or not signature:
        return False
    if abs(now - int(timestamp)) > settings.signature_tolerance_s:
        return False
    expected = "sha256=" + hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), signature.encode())


def _token_ok(expected: str, given: str) -> bool:
    """Comparación en tiempo constante; sin token configurado se rechaza todo."""
    return bool(expected) and hmac.compare_digest(expected.encode(), given.encode())


async def read_capped(request: Request, limit: int) -> bytes:
    """Lee el cuerpo con tope, antes de autenticar: un cuerpo enorme sin firma no debe consumir memoria."""
    declared = request.headers.get("content-length")
    if declared is not None:
        if not declared.isdigit():
            raise HTTPException(status_code=400, detail="Content-Length inválido")
        if int(declared) > limit:
            raise HTTPException(status_code=413, detail="Cuerpo demasiado grande")
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail="Cuerpo demasiado grande")
        chunks.append(chunk)
    return b"".join(chunks)


def create_app(settings: Settings | None = None, chatwoot: ChatwootClient | None = None,
               pms: PmsAdapter | None = None, clock=time.time, run_workers: bool = True,
               db: sqlite3.Connection | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.env == "production":
        settings.validate_runtime()
    hotel = HotelData.load(settings.hotel_data_path)
    if db is None:
        db = connect(settings.db_path)
        init_db(db)
    chatwoot = chatwoot or ChatwootClient(settings.chatwoot_url, settings.chatwoot_account_id,
                                          settings.chatwoot_bot_token, settings.chatwoot_team_id)
    pms = pms or MockPxsolAdapter(settings.pms_url, settings.pms_timeout_s)
    core = Copiloto(settings, hotel, db, chatwoot, pms, clock)
    sla = SlaWorker(settings, db, chatwoot, clock)

    async def purge_loop() -> None:
        while True:
            try:
                result = store.purge_personal_data(db, clock(), settings.retention_days, settings.pseudonym_salt)
                logger.info("Purga de retención: %s", result)
            except Exception:
                logger.exception("Falla en la purga de retención")
            await asyncio.sleep(PURGE_INTERVAL_S)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        tasks = [asyncio.create_task(sla.run()), asyncio.create_task(purge_loop())] if run_workers else []
        yield
        for task in tasks:
            task.cancel()

    app = FastAPI(title="Copiloto de Recepción", lifespan=lifespan)
    app.state.core, app.state.sla, app.state.db, app.state.settings = core, sla, db, settings

    limiter = SlidingWindowLimiter(settings.public_rate_per_min, clock=clock)
    limited = [Depends(limiter.dependency())]
    chatwoot_origin = settings.chatwoot_public_url.rstrip("/")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        # El panel lo enmarca Chatwoot (Dashboard App); el resto de las páginas no se puede enmarcar
        framing = chatwoot_origin if request.url.path == "/panel" else "'none'"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Content-Security-Policy", (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
            f"frame-ancestors {framing}"))
        return response

    @app.get("/health")
    async def health(probe: str = Query(default="liveness", pattern="^(liveness|readiness)$")):
        """liveness: el proceso responde. readiness: además la base SQLite responde."""
        if probe == "readiness":
            try:
                db.execute("SELECT 1").fetchone()
            except sqlite3.Error:
                logger.exception("Readiness: la base no responde")
                return JSONResponse({"status": "degraded"}, status_code=503)
        return {"status": "ok"}

    @app.post("/webhooks/chatwoot")
    async def chatwoot_webhook(request: Request, background: BackgroundTasks):
        raw = await read_capped(request, settings.max_body_bytes)
        if not verify_signature(settings, request.headers, raw, clock()):
            raise HTTPException(status_code=401, detail="Firma inválida")
        # Se responde 200 de inmediato: si Chatwoot no recibe respuesta a tiempo mueve la conversación a open
        try:
            event = json.loads(raw)
        except ValueError:
            raise HTTPException(status_code=400, detail="JSON inválido") from None
        background.add_task(core.handle_webhook, event)
        return {"status": "accepted"}

    @app.post("/webhooks/pms")
    async def pms_webhook(request: Request):
        # El secreto viaja en un header (no en la URL) para que no quede en los access logs
        if not _token_ok(settings.pms_events_secret, request.headers.get("x-events-token", "")):
            raise HTTPException(status_code=401, detail="Secreto inválido")
        try:
            body = json.loads(await read_capped(request, settings.max_body_bytes))
        except ValueError:
            raise HTTPException(status_code=422, detail="JSON inválido") from None
        if not isinstance(body, dict) or body.get("kind") != "booking_confirmed" or "booking_id" not in body:
            raise HTTPException(status_code=422, detail="Evento no soportado")
        try:
            booking_id = int(body["booking_id"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="booking_id inválido") from None
        await core.on_booking_confirmed(body.get("conversation_id"), booking_id)
        return {"status": "recorded"}

    @app.get("/panel", response_class=HTMLResponse, dependencies=limited)
    async def panel():
        return (STATIC / "panel.html").read_text(encoding="utf-8")

    @app.get("/api/panel/{conversation_id}", dependencies=limited)
    async def panel_data(conversation_id: int, request: Request):
        if not _token_ok(settings.panel_token, request.headers.get("x-panel-token", "")):
            raise HTTPException(status_code=401, detail="Token del panel requerido")
        state = store.get_state(db, conversation_id)
        data = dict(state.data)
        room = hotel.room(data["room_code"]) if data.get("room_code") else None
        row = store.active_prebooking(db, conversation_id)
        prebooking = None
        if row is not None:
            prebooking = {"status": row["status"], "expires_at": row["expires_at"], "room_code": row["room_code"]}
        pms_params = {"guest": state.contact_name or "", "conversation_id": conversation_id}
        if data.get("checkin"):
            pms_params.update(checkin=data["checkin"], checkout=data["checkout"], adults=data.get("adults", 1),
                              children=data.get("children", 0))
        if data.get("room_code"):
            pms_params["room_code"] = data["room_code"]
        return {
            "conversation_id": conversation_id, "contact_name": state.contact_name, "step": state.step,
            "data": data, "room_name": room["name"] if room else None, "prebooking": prebooking,
            "sla": {"started_at": state.sla_started_at, "stopped_at": state.sla_stopped_at,
                    "amber_s": settings.sla_amber_s, "red_s": settings.sla_red_s},
            "now": clock(), "pms_url": f"{settings.pms_staff_url.rstrip('/')}/admin?{urlencode(pms_params)}",
        }

    @app.get("/metricas", response_class=HTMLResponse, dependencies=limited)
    async def metrics_page():
        return (STATIC / "metricas.html").read_text(encoding="utf-8")

    @app.get("/metricas/data.json", dependencies=limited)
    async def metrics_data(days: int = Query(default=7, ge=1, le=366)):
        from copiloto.metrics import compute_metrics

        end = clock()
        return JSONResponse(compute_metrics(db, end - days * 86400, end + 1, settings))

    @app.get("/privacidad", response_class=HTMLResponse, dependencies=limited)
    async def privacy_page():
        return privacy.render(hotel)

    return app
