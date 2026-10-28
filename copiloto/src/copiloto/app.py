"""Aplicación FastAPI del copiloto: webhooks, panel, métricas y aviso de privacidad."""

import asyncio
import hashlib
import hmac
import json
import logging
import re
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlencode

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.gzip import GZipMiddleware

from copiloto import privacy, store
from copiloto.ai import sessions as ai_sessions
from copiloto.ai.agent import Agent
from copiloto.ai.llm import LlmClient, LlmUnavailable
from copiloto.ai.tools import ToolHooks
from copiloto.chatwoot import ChatwootClient
from copiloto.config import Settings
from copiloto.events import connect, init_db, record_event
from copiloto.flow import Copiloto
from copiloto.guided import guided_reply
from copiloto.hotel import HotelData
from copiloto.pms import MockPxsolAdapter, PmsAdapter
from copiloto.ratelimit import SlidingWindowLimiter
from copiloto.sla import SlaWorker

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
PURGE_INTERVAL_S = 86400
DEMO_SESSION_ID = re.compile(r"^[A-Za-z0-9-]{16,64}$")
DEMO_MAX_MESSAGE = 400


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
               db: sqlite3.Connection | None = None, llm_agent: Agent | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.env == "production":
        settings.validate_runtime()
    hotel = HotelData.load(settings.hotel_data_path)
    if db is None:
        db = connect(settings.db_path)
        init_db(db)
    chatwoot = chatwoot or ChatwootClient(settings.chatwoot_url, settings.chatwoot_account_id,
                                          settings.chatwoot_bot_token, settings.chatwoot_team_id)
    pms = pms or MockPxsolAdapter(settings.pms_url, settings.pms_timeout_s, staff_token=settings.pms_staff_token)
    agent = llm_agent or (Agent(LlmClient(settings.llm_base_url, settings.llm_api_key, settings.llm_model,
                                          settings.llm_timeout_s), hotel, pms, settings, clock)
                          if settings.ai_active else None)
    core = Copiloto(settings, hotel, db, chatwoot, pms, clock, agent)
    sla = SlaWorker(settings, db, chatwoot, clock)

    async def purge_loop() -> None:
        while True:
            try:
                result = store.purge_personal_data(db, clock(), settings.retention_days, settings.pseudonym_salt)
                logger.info("Purga de retención: %s", result)
            except Exception:
                logger.exception("Falla en la purga de retención")
            await asyncio.sleep(PURGE_INTERVAL_S)

    async def demo_purge_loop() -> None:
        while True:
            try:
                ai_sessions.purge_expired(db, clock(), settings.demo_session_ttl_s, "demo:")
            except Exception:
                logger.exception("Falla al purgar sesiones de la demo")
            await asyncio.sleep(3600)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        tasks = [asyncio.create_task(sla.run()), asyncio.create_task(purge_loop()),
                 asyncio.create_task(demo_purge_loop())] if run_workers else []
        yield
        for task in tasks:
            task.cancel()

    app = FastAPI(title="Copiloto de Recepción", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=[settings.landing_origin], allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"], max_age=600)
    # Las páginas del panel y las métricas viajan comprimidas.
    app.add_middleware(GZipMiddleware, minimum_size=600)
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
        source = body.get("source") if body.get("source") in ("personal", "ia") else "personal"
        await core.on_booking_confirmed(body.get("conversation_id"), booking_id, source)
        return {"status": "recorded"}

    @app.get("/panel", response_class=HTMLResponse, dependencies=limited)
    async def panel():
        return (STATIC / "panel.html").read_text(encoding="utf-8")

    @app.get("/api/panel/queue", dependencies=limited)
    async def panel_queue(request: Request):
        if not _token_ok(settings.panel_token, request.headers.get("x-panel-token", "")):
            raise HTTPException(status_code=401, detail="Token del panel requerido")
        return {"now": clock(), "amber_s": settings.sla_amber_s, "red_s": settings.sla_red_s,
                "conversations": store.list_conversations(db, clock())}

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
        return privacy.render(hotel, settings.llm_model if agent is not None else None, settings.llm_base_url)

    demo_ip_limiter = SlidingWindowLimiter(settings.demo_ip_per_min, clock=clock)
    demo_global_limiter = SlidingWindowLimiter(settings.demo_global_per_hour, 3600, clock=clock)

    def demo_error(status: int, detail: str, retry_after: int | None = None) -> JSONResponse:
        body = {"detail": detail}
        headers = {}
        if retry_after is not None:
            body["retry_after_s"] = retry_after
            headers["Retry-After"] = str(retry_after)
        return JSONResponse(body, status_code=status, headers=headers)

    async def demo_body(request: Request) -> dict | JSONResponse:
        if not settings.demo_enabled:
            return demo_error(503, "demo_disabled")
        wait = demo_ip_limiter.check(request.client.host if request.client else "desconocido")
        if wait is not None:
            return demo_error(429, "Demasiadas solicitudes, espera un momento", int(wait) + 1)
        try:
            body = json.loads(await read_capped(request, 8192))
        except ValueError:
            return demo_error(400, "JSON inválido")
        if not isinstance(body, dict):
            return demo_error(400, "Cuerpo inválido")
        session_id = body.get("session_id")
        if not isinstance(session_id, str) or not DEMO_SESSION_ID.match(session_id):
            return demo_error(422, "session_id inválido")
        return body

    @app.get("/api/demo/status", dependencies=limited)
    async def demo_status():
        return {"ai_enabled": agent is not None, "mode": settings.ai_mode if agent is not None else "off",
                "model": settings.llm_model if agent is not None else None,
                "autonomous_booking": settings.autonomous_booking and agent is not None,
                "max_message_chars": DEMO_MAX_MESSAGE, "messages_per_session": settings.demo_messages_per_session,
                "disclaimer": "Demo con IA: no escribas datos personales reales."}

    @app.post("/api/demo/chat")
    async def demo_chat(request: Request):
        body = await demo_body(request)
        if isinstance(body, JSONResponse):
            return body
        message = body.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > DEMO_MAX_MESSAGE:
            return demo_error(400, f"El mensaje debe tener entre 1 y {DEMO_MAX_MESSAGE} caracteres")
        session = ai_sessions.load(db, f"demo:{body['session_id']}", clock())
        if session.msg_count >= settings.demo_messages_per_session:
            return demo_error(429, "Límite de mensajes de esta conversación: reiníciala para seguir", 3600)
        wait = demo_global_limiter.check("global")
        if wait is not None:
            return demo_error(429, "La demo alcanzó su límite por hora, vuelve en un rato", int(wait) + 1)
        message = message.strip()
        session.msg_count += 1
        events: list[dict] = []
        reply, quick, mode, usage = "", [], "guided", {"llm_ms": 0, "tokens": None}
        if agent is not None:
            hooks = ToolHooks(conversation_id=None, in_shift=settings.in_shift(clock()),
                              record=lambda kind, payload: record_demo_event(kind, payload))
            try:
                result = await agent.respond(session, message, hooks)
                reply, quick, mode, events = result.reply or "", result.quick_replies, "ai", result.events
                usage = {"llm_ms": result.llm_ms, "tokens": result.tokens}
                record_demo_event("ai_reply", {"latency_ms": result.llm_ms, "tools": result.tools,
                                               "tokens": result.tokens})
                for rule in result.guardrails:
                    record_demo_event("ai_guardrail", {"rule": rule})
                if result.booking:
                    record_demo_event("ai_booking", {"booking_id": result.booking["booking_id"]})
            except LlmUnavailable:
                events = [{"type": "fallback", "reason": "ia_no_disponible"}]
                reply, quick = guided_reply(hotel, message)
        else:
            events = [{"type": "fallback", "reason": "ia_no_configurada"}]
            reply, quick = guided_reply(hotel, message)
        ai_sessions.save(db, session, clock())
        return {"reply": reply, "mode": mode, "events": events, "quick_replies": quick[:4],
                "usage": {"messages_left": max(settings.demo_messages_per_session - session.msg_count, 0),
                          **usage}}

    @app.post("/api/demo/reset")
    async def demo_reset(request: Request):
        body = await demo_body(request)
        if isinstance(body, JSONResponse):
            return body
        ai_sessions.delete(db, f"demo:{body['session_id']}")
        return {"status": "ok"}

    def record_demo_event(kind: str, payload: dict) -> None:
        record_event(db, 0, kind, clock(), payload)

    return app
