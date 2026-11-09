"""Aplicación FastAPI del copiloto: webhooks, panel, métricas y aviso de privacidad."""

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
import weakref
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import date
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.gzip import GZipMiddleware

from copiloto import privacy, store
from copiloto.ai import sessions as ai_sessions
from copiloto.ai.agent import Agent
from copiloto.ai.llm import LlmClient, LlmTimeout, LlmUnavailable
from copiloto.ai.prompts import PROMPT_VERSION
from copiloto.ai.tools import ToolHooks
from copiloto.chatwoot import ChatwootClient
from copiloto.config import Settings, int_env
from copiloto.demo_channel import DemoChannel
from copiloto.events import connect, init_db, record_event
from copiloto.flow import DEMO_CHANNEL, DEMO_MENU, DEMO_STYLE, Copiloto, long_date
from copiloto.guided import guided_reply
from copiloto.hotel import HotelData
from copiloto.pms import PmsAdapter, PmsUnavailable, build_demo_pms_adapter, build_pms_adapter
from copiloto.ratelimit import SlidingWindowLimiter
from copiloto.sla import SlaWorker
from copiloto.voice import (
    CharBudget,
    ElevenLabsClient,
    PiperClient,
    TtsUnavailable,
    greeting_for,
    guess_language,
    speakable,
)

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"
PURGE_INTERVAL_S = 86400
AUDIO_CACHE_MAX = 200
DEMO_SESSION_ID = re.compile(r"^[A-Za-z0-9-]{16,64}$")
# Llave de idempotencia de una acción (mensaje del huésped o respuesta de recepción): un reintento con la
# misma llave no duplica nada.
ACTION_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
# Corrida de la demo (la emite el servidor) y llave estable del operador (la guarda el navegador de recepción).
RUN_ID = re.compile(r"^[A-Za-z0-9_-]{16,32}$")
OPERATOR_KEY = re.compile(r"^[A-Za-z0-9-]{16,64}$")
# Tope global de corridas nuevas por hora: la demo pública no puede usarse para llenar la base.
DEMO_RUNS_PER_HOUR = 300
DEMO_MAX_MESSAGE = 400
STAFF_NAME = re.compile(r"^[^\W\d_][\w .'-]{0,29}$")


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


PANEL_COOKIE = "panel_session"
PANEL_SESSION_HOURS = 12


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


def create_app(
    settings: Settings | None = None,
    chatwoot: ChatwootClient | None = None,
    pms: PmsAdapter | None = None,
    clock=time.time,
    run_workers: bool = True,
    db: sqlite3.Connection | None = None,
    llm_agent: Agent | None = None,
    tts: ElevenLabsClient | None = None,
    piper: PiperClient | None = None,
    demo_pms: PmsAdapter | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if settings.env == "production":
        settings.validate_runtime()
    hotel = HotelData.load(settings.hotel_data_path)
    # Una sola resolución de retención (el aviso publicado y la purga usan el mismo valor): un
    # Settings inyectado con valor propio gana; si quedó por defecto, manda RETENTION_DAYS del
    # entorno (ya parseado por Settings.from_env) y el YAML del hotel es el último recurso.
    retention = settings.retention_days
    if retention == Settings.retention_days:
        # Mismo helper que Settings: un valor en blanco (compose pasa `${VAR:-}`) cuenta como ausente.
        retention = int_env(os.environ, "RETENTION_DAYS", int(hotel.privacy["retention_days"]))
    settings = replace(settings, retention_days=retention)
    if db is None:
        db = connect(settings.db_path)
        init_db(db)
    chatwoot = chatwoot or ChatwootClient(
        settings.chatwoot_url, settings.chatwoot_account_id, settings.chatwoot_bot_token, settings.chatwoot_team_id
    )
    pms = pms or build_pms_adapter(settings)
    # La demo pública lee SU inventario de prueba: nunca el adaptador (ni el PMS) de la operación.
    demo_pms = demo_pms or build_demo_pms_adapter(settings)

    def build_agent(adapter: PmsAdapter) -> Agent | None:
        if not settings.ai_active:
            return None
        llm = LlmClient(settings.llm_base_url, settings.llm_api_key, settings.llm_model, settings.llm_timeout_s)
        return Agent(llm, hotel, adapter, settings, clock)

    agent = llm_agent or build_agent(pms)
    demo_agent = llm_agent or build_agent(demo_pms)
    if tts is None and agent is not None and settings.voice_active:
        tts = ElevenLabsClient(
            settings.elevenlabs_api_key,
            settings.elevenlabs_voice_id,
            settings.elevenlabs_model,
            voice_id_en=settings.elevenlabs_voice_id_en or None,
        )
    if piper is None and settings.piper_model_path:
        piper = PiperClient(settings.piper_model_path, settings.piper_config_path or None)
    # Cadena de voz: ElevenLabs (de pago, con topes) → Piper (local) → texto con voz del navegador
    voice_providers = []
    if tts is not None:
        voice_providers.append(("elevenlabs", tts, "mp3"))
    if piper is not None:
        voice_providers.append(("piper", piper, "wav"))
    voice_budget = CharBudget(settings.voice_chars_per_hour, clock=clock)
    voice_monthly_budget = CharBudget(settings.voice_chars_per_month, window_s=30 * 86400, clock=clock)
    greeting_audio: dict[str, tuple[str, str]] = {}
    audio_cache: OrderedDict[str, tuple[str, str]] = OrderedDict()
    greeting_lock = asyncio.Lock()
    session_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()
    core = Copiloto(settings, hotel, db, chatwoot, pms, clock, agent)
    # Espacio de la demo: el mismo hotel y el mismo PMS simulado que la portada, con un canal propio que
    # escribe en la transcripción aislada (nunca en Chatwoot).
    demo_channel = DemoChannel(db, clock)
    # Por defecto la demo corre el flujo guiado; con DEMO_AI=1 y un modelo configurado, el asistente con IA.
    demo_uses_ai = settings.demo_ai and demo_agent is not None
    sla = SlaWorker(settings, db, chatwoot, clock, demo_channel=demo_channel)

    def demo_settings(shift: str | None) -> Settings:
        """Escenario de turno de la sesión de prueba («open»/«closed»); sin escenario manda la configuración."""
        return replace(settings, shift_override=shift) if shift in ("open", "closed") else settings

    def demo_engine(shift: str | None) -> Copiloto:
        return Copiloto(
            demo_settings(shift), hotel, db, demo_channel, demo_pms, clock, None,
            style=DEMO_STYLE, source=store.DEMO_SOURCE,
        )

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
                store.purge_demo(db, clock() - settings.demo_session_ttl_s)
            except Exception:
                logger.exception("Falla al purgar sesiones de la demo")
            await asyncio.sleep(3600)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        tasks = (
            [asyncio.create_task(sla.run()), asyncio.create_task(purge_loop()), asyncio.create_task(demo_purge_loop())]
            if run_workers
            else []
        )
        yield
        for task in tasks:
            task.cancel()

    app = FastAPI(title="Copiloto de Recepción", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.landing_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Demo-Run"],
        allow_credentials=True,
        max_age=600,
    )
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
        # Las vistas internas y la API no se indexan (C4); la portada y el aviso de privacidad sí
        path = request.url.path
        if path in ("/panel", "/metricas") or path.startswith(("/metricas/", "/api/")):
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Content-Security-Policy",
            (
                "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; "
                f"frame-ancestors {framing}"
            ),
        )
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
        if not settings.chatwoot_enabled:
            # Sin integración configurada el webhook queda cerrado: no lee el cuerpo ni procesa nada.
            raise HTTPException(status_code=503, detail="chatwoot_disabled")
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

    def panel_session(name: str, expires: int, demo: bool = False, run: str | None = None,
                      operator: str | None = None) -> str:
        claims = {"n": name, "e": expires}
        if demo:
            claims["d"] = 1
            # Corrida y operador viajan firmados: el cliente no puede elegir ni otra corrida ni otro operador.
            if run:
                claims["r"] = run
            if operator:
                claims["o"] = operator
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()
        sig = hmac.new(settings.panel_token.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def panel_claims(request: Request) -> dict | None:
        """Claims firmados de la cookie del panel: nombre y si la sesión es de demostración."""
        if not settings.panel_token:
            return None
        payload, _, signature = request.cookies.get(PANEL_COOKIE, "").partition(".")
        if not payload or not signature:
            return None
        expected = hmac.new(settings.panel_token.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.encode(), expected.encode()):
            return None
        try:
            data = json.loads(base64.urlsafe_b64decode(payload.encode()))
            if not isinstance(data, dict) or type(data.get("e")) is not int or not isinstance(data.get("n"), str):
                return None
            expires = data["e"]
        except (ValueError, TypeError):
            return None
        if expires < clock():
            return None
        run, operator = data.get("r"), data.get("o")
        if not isinstance(run, str | None) or not isinstance(operator, str | None):
            return None
        # Otra pestaña abrió otra corrida con esta misma cookie: esta sesión no vale para la corrida pedida.
        wanted = request.headers.get("x-demo-run")
        if data.get("d") == 1 and wanted and wanted != run:
            return None
        return {"name": str(data.get("n") or "recepción"), "demo": data.get("d") == 1, "run": run,
                "operator": operator}

    def panel_identity(request: Request) -> str | None:
        """Quién mira el panel: sesión firmada por cookie, o el token del panel (app de Chatwoot)."""
        if not settings.panel_token:
            return None
        if _token_ok(settings.panel_token, request.headers.get("x-panel-token", "")):
            return "chatwoot"
        claims = panel_claims(request)
        return claims["name"] if claims else None

    def viewer(request: Request) -> dict:
        """Corrida y operador de una sesión de la demo (None fuera de la demo o sin corrida)."""
        claims = panel_claims(request) if panel_is_demo(request) else None
        return {"run": claims["run"], "operator": claims["operator"]} if claims else {"run": None, "operator": None}

    def run_conversations(run: str | None) -> set[int]:
        if run is None:
            return set()
        rows = db.execute("SELECT conversation_id FROM demo_conversations WHERE run_id = ?", (run,)).fetchall()
        return {row["conversation_id"] for row in rows}

    def conversation_visible(conversation_id: int, request: Request) -> bool:
        """Cada sesión ve solo su mundo: la demo, solo su corrida; el personal, nunca la demo."""
        source = store.conversation_source(db, conversation_id)
        if source is not None and (source == store.DEMO_SOURCE) != panel_is_demo(request):
            return False
        if panel_is_demo(request):
            return conversation_id in run_conversations(viewer(request)["run"])
        return True

    def panel_is_demo(request: Request) -> bool:
        """Sesión de demostración: solo ve y escribe el espacio aislado, nunca la operación real."""
        if not settings.panel_token:
            return False
        if _token_ok(settings.panel_token, request.headers.get("x-panel-token", "")):
            return False
        claims = panel_claims(request)
        return bool(claims and claims["demo"])

    @app.get("/panel", response_class=HTMLResponse, dependencies=limited)
    async def panel():
        return (STATIC / "panel.html").read_text(encoding="utf-8")

    @app.get("/static/{asset:path}", dependencies=limited)
    async def static_asset(asset: str):
        # Solo la hoja compartida y las tipografías: nada fuera de static/ se sirve por esta ruta.
        if asset == "theme.css":
            target = STATIC / asset
        elif asset.startswith("fonts/") and asset.endswith(".woff2") and "/" not in asset[6:]:
            target = STATIC / asset
        else:
            raise HTTPException(status_code=404)
        if not target.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(target, headers={"Cache-Control": "public, max-age=3600"})

    @app.post("/api/panel/login", dependencies=limited)
    async def panel_login(request: Request):
        try:
            body = json.loads(await read_capped(request, 4096))
        except ValueError:
            return JSONResponse({"detail": "JSON inválido"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"detail": "JSON inválido"}, status_code=400)
        if not _token_ok(settings.panel_token, str(body.get("password") or "")):
            return JSONResponse({"detail": "Contraseña incorrecta"}, status_code=401)
        name = " ".join(str(body.get("name") or "recepción").split())[:40] or "recepción"
        response = JSONResponse({"name": name})
        response.set_cookie(
            PANEL_COOKIE,
            panel_session(name, int(clock()) + PANEL_SESSION_HOURS * 3600),
            max_age=PANEL_SESSION_HOURS * 3600,
            httponly=True,
            samesite="lax",
            secure=urlsplit(settings.public_url).scheme == "https",
        )
        return response

    @app.post("/api/panel/logout", dependencies=limited)
    async def panel_logout():
        response = JSONResponse({"status": "ok"})
        response.delete_cookie(PANEL_COOKIE)
        return response

    @app.get("/api/panel/session", dependencies=limited)
    async def panel_session_info(request: Request):
        who = panel_identity(request)
        if who is None:
            return JSONResponse({"detail": "Sesión requerida"}, status_code=401)
        return {"name": who}

    @app.post("/api/demo/session", dependencies=limited)
    async def demo_session_create(request: Request):
        """Modo demo sin credenciales en el navegador (L8-L9): la sesión firmada del panel se crea aquí.

        Acepta cuerpo vacío con el mismo tope que el login; con la demo apagada responde 403 y sin cookie.
        Nunca devuelve el token ni ningún secreto: la sesión viaja solo en la cookie HttpOnly.
        """
        raw = await read_capped(request, 4096)
        if not settings.demo_enabled:
            raise HTTPException(status_code=403, detail="demo_disabled")
        name = "Recepción (demo)"
        body: dict = {}
        if raw.strip():
            try:
                body = json.loads(raw) or {}
                wanted = " ".join(str(body.get("name") or "").split())
            except (ValueError, AttributeError):
                raise HTTPException(status_code=400, detail="JSON inválido") from None
            if wanted:
                if not STAFF_NAME.match(wanted):
                    raise HTTPException(status_code=422, detail="Nombre inválido: letras, hasta 30 caracteres")
                name = wanted
        # Corrida: la recepción solo ve los casos de la corrida con que entra (sin corrida, ninguno).
        run = body.get("run")
        if run is not None and (not isinstance(run, str) or not RUN_ID.match(run)):
            raise HTTPException(status_code=422, detail="Corrida inválida")
        if run is not None and not store.demo_run_active(db, run, clock(), settings.demo_session_ttl_s):
            raise HTTPException(status_code=404, detail="corrida_desconocida")
        # Operador: id estable derivado de una llave que guarda este navegador. El nombre es solo una etiqueta;
        # dos «Sofía» con llaves distintas son dos operadores.
        key = body.get("operator_key")
        if key is not None and (not isinstance(key, str) or not OPERATOR_KEY.match(key)):
            raise HTTPException(status_code=422, detail="operator_key inválida")
        key = key or secrets.token_hex(16)
        operator = hmac.new(settings.panel_token.encode(), f"operador:{run}:{key}".encode(),
                            hashlib.sha256).hexdigest()[:20]
        response = Response(status_code=204)
        response.set_cookie(
            PANEL_COOKIE,
            panel_session(name, int(clock()) + PANEL_SESSION_HOURS * 3600, demo=True, run=run, operator=operator),
            max_age=PANEL_SESSION_HOURS * 3600,
            httponly=True,
            samesite="lax",
            secure=urlsplit(settings.public_url).scheme == "https",
        )
        return response

    @app.get("/api/demo/session", dependencies=limited)
    async def demo_session_info(request: Request):
        """La página de la demo pregunta si el modo demo está disponible y quién es la sesión; sin secretos."""
        return {"demo": settings.demo_enabled, "name": panel_identity(request), "run": viewer(request)["run"]}

    demo_run_limiter = SlidingWindowLimiter(DEMO_RUNS_PER_HOUR, 3600, clock=clock)

    @app.post("/api/demo/run", dependencies=limited)
    async def demo_run_create():
        """Corrida nueva: el servidor emite el id que une la vista del huésped con la de recepción."""
        if not settings.demo_enabled:
            raise HTTPException(status_code=403, detail="demo_disabled")
        wait = demo_run_limiter.check("global")
        if wait is not None:
            return JSONResponse({"detail": "La demo alcanzó su límite de corridas por hora", "retry_after_s":
                                 int(wait) + 1}, status_code=429, headers={"Retry-After": str(int(wait) + 1)})
        return JSONResponse({"run": store.create_demo_run(db, clock()), "ttl_s": settings.demo_session_ttl_s},
                            status_code=201)

    @app.get("/api/demo/run/{run_id}", dependencies=limited)
    async def demo_run_info(run_id: str):
        """¿Sigue viva la corrida del enlace? (otra ventana o una recarga). Vencida o inventada: 404."""
        if not settings.demo_enabled:
            raise HTTPException(status_code=403, detail="demo_disabled")
        if not RUN_ID.match(run_id) or not store.demo_run_active(db, run_id, clock(), settings.demo_session_ttl_s):
            raise HTTPException(status_code=404, detail="corrida_desconocida")
        return {"run": run_id}

    @app.get("/api/panel/queue", dependencies=limited)
    async def panel_queue(request: Request):
        if panel_identity(request) is None:
            raise HTTPException(status_code=401, detail="Sesión del panel requerida")
        return {
            "now": clock(),
            "amber_s": settings.sla_amber_s,
            "red_s": settings.sla_red_s,
            # La demo ve solo su espacio; el personal nunca recibe las conversaciones de prueba.
            "conversations": store.list_conversations(
                db, clock(), scope=store.DEMO_SOURCE if panel_is_demo(request) else "operational",
                run_id=viewer(request)["run"],
            ),
        }

    @app.get("/api/panel/shift", dependencies=limited)
    async def panel_shift(request: Request, hours: int = Query(default=12, ge=1, le=72)):
        if panel_identity(request) is None:
            raise HTTPException(status_code=401, detail="Sesión del panel requerida")
        now = clock()
        source = store.DEMO_SOURCE if panel_is_demo(request) else store.OPERATIONAL_SOURCE
        summary = store.shift_summary(db, now - hours * 3600, now, source, run_id=viewer(request)["run"])
        return {"hours": hours, **summary}

    # ---------- bandeja de solicitudes ----------

    def require_identity(request: Request) -> str:
        who = panel_identity(request)
        if who is None:
            raise HTTPException(status_code=401, detail="Sesión del panel requerida")
        return who

    def scoped_request(request_id: int, request: Request):
        """La solicitud, solo si pertenece al mundo de la sesión (demo u operación); si no, 404."""
        row = store.get_request_row(db, request_id)
        if row is None or (row["source"] == store.DEMO_SOURCE) != panel_is_demo(request):
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        # En la demo, además, solo la corrida de la sesión: otra corrida no sabe ni que existe.
        if panel_is_demo(request) and (viewer(request)["run"] is None or row["run_id"] != viewer(request)["run"]):
            raise HTTPException(status_code=404, detail="Solicitud no encontrada")
        return row

    def require_demo(request: Request) -> None:
        if not panel_is_demo(request):
            raise HTTPException(status_code=403, detail="La operación real se atiende en Chatwoot")

    def request_detail(row, me: str, operator: str | None = None) -> dict:
        now = clock()
        detail = store.request_dict(row, now, settings.sla_red_s)
        conversation_id = row["conversation_id"]
        demo = row["source"] == store.DEMO_SOURCE
        detail["contact_name"] = store.get_state(db, conversation_id).contact_name
        detail["messages"] = store.list_demo_messages(db, conversation_id) if demo else []
        detail["events"] = store.request_events(db, conversation_id, row["commercial_at"] - 0.001)
        faq = []
        for event in store.request_events(db, conversation_id, 0):
            # FAQ aprobadas y ubicación: misma meta (< 10 s desde que entró el mensaje).
            if event["kind"] in ("faq_answered", "location_shown") and "inbound_ts" in event["payload"]:
                latency = event["ts"] - event["payload"]["inbound_ts"]
                faq.append({"faq_id": event["payload"].get("faq_id", "ubicacion"), "latency_s": round(latency, 3),
                            "met": latency < 10})
        detail["faq"] = faq
        open_ = row["status"] != "cerrada"
        # Permisos por operador (id estable): dos personas con el mismo nombre no comparten casos.
        mine = store.owned_by(row, me, operator)
        detail["mine"] = mine
        detail["actions"] = {
            "take": demo and open_ and not row["assignee"],
            "reply": demo and open_ and mine,
            "close": demo and open_ and mine,
            "inventory": demo and open_ and bool(row["checkin"]),
        }
        return detail

    def shift_info(shift_settings: Settings) -> dict:
        now = clock()
        opening = shift_settings.next_shift_start(now)
        return {
            "start": shift_settings.shift_start,
            "end": shift_settings.shift_end,
            "timezone": shift_settings.timezone,
            "in_shift": shift_settings.in_shift(now),
            "override": shift_settings.shift_override or None,
            "next_opening": f"{opening.strftime('%H:%M')} del {long_date(opening.date())}",
        }

    @app.get("/api/panel/requests", dependencies=limited)
    async def panel_requests(request: Request, selected: int | None = Query(default=None, ge=1)):
        """Bandeja y, en la misma lectura, el detalle de la solicitud abierta (un solo sondeo por ciclo)."""
        me = require_identity(request)
        scope = store.DEMO_SOURCE if panel_is_demo(request) else "operational"
        who = viewer(request)
        detail = None
        if selected is not None:
            try:
                detail = request_detail(scoped_request(selected, request), me, who["operator"])
            except HTTPException:
                detail = None
        return {
            "now": clock(),
            "me": me,
            "target_s": settings.sla_red_s,
            "amber_s": settings.sla_amber_s,
            "shift": shift_info(settings),
            "requests": store.list_requests(db, clock(), settings.sla_red_s, scope, run_id=who["run"],
                                            operator=who["operator"]),
            "selected": detail,
        }

    @app.get("/api/panel/requests/{request_id}", dependencies=limited)
    async def panel_request(request_id: int, request: Request):
        me = require_identity(request)
        return request_detail(scoped_request(request_id, request), me, viewer(request)["operator"])

    @app.post("/api/panel/requests/{request_id}/take", dependencies=limited)
    async def panel_take(request_id: int, request: Request):
        """Tomar solicitud: asigna responsable y pasa a «En atención». No reinicia el reloj."""
        me = require_identity(request)
        row = scoped_request(request_id, request)
        require_demo(request)
        operator = viewer(request)["operator"]
        try:
            row, _ = store.take_request(db, row["id"], me, clock(), assignee_id=operator)
        except store.RequestConflict as exc:
            current = request_detail(scoped_request(request_id, request), me, operator)
            return JSONResponse({"detail": str(exc), "request": current}, status_code=409)
        return request_detail(row, me, operator)

    @app.post("/api/panel/requests/{request_id}/reply", dependencies=limited)
    async def panel_request_reply(request_id: int, request: Request):
        """Respuesta escrita por recepción en el hilo del huésped. `kind`: answer (pertinente) o ack (acuse).

        Con `client_id`, un reintento de la misma respuesta no la duplica.
        """
        me = require_identity(request)
        row = scoped_request(request_id, request)
        require_demo(request)
        operator = viewer(request)["operator"]
        try:
            body = json.loads(await read_capped(request, 8192))
        except ValueError:
            return JSONResponse({"detail": "JSON inválido"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"detail": "JSON inválido"}, status_code=400)
        text = " ".join(str(body.get("body") or "").split())
        kind = body.get("kind") or "answer"
        client_id = body.get("client_id")
        if not text or len(text) > 1000:
            return JSONResponse({"detail": "La respuesta debe tener entre 1 y 1000 caracteres"}, status_code=400)
        if kind not in ("answer", "ack"):
            return JSONResponse({"detail": "kind debe ser answer o ack"}, status_code=422)
        if client_id is not None and (not isinstance(client_id, str) or not ACTION_ID.match(client_id)):
            return JSONResponse({"detail": "client_id inválido"}, status_code=422)
        now = clock()
        try:
            # La llave (por caso), el mensaje, el estado y el evento se guardan en UNA transacción.
            updated, message = store.staff_reply(db, row["id"], me, text, kind, now, client_id=client_id,
                                                 author_id=operator)
        except store.DuplicateAction:
            # Reintento de una respuesta ya guardada (p. ej. se perdió la respuesta HTTP): no se reenvía.
            current = request_detail(scoped_request(request_id, request), me, operator)
            return {"duplicate": True, "message": None, "request": current}
        except store.ActionConflict as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        except store.RequestConflict as exc:
            current = request_detail(scoped_request(request_id, request), me, operator)
            return JSONResponse({"detail": str(exc), "request": current}, status_code=409)
        return {"duplicate": False, "message": message, "request": request_detail(updated, me, operator)}

    @app.post("/api/panel/requests/{request_id}/close", dependencies=limited)
    async def panel_close(request_id: int, request: Request):
        """Cierra la atención: el hilo vuelve al asistente y una consulta nueva crea otra solicitud."""
        me = require_identity(request)
        row = scoped_request(request_id, request)
        require_demo(request)
        operator = viewer(request)["operator"]
        try:
            closed = store.close_request(db, row["id"], clock(), author=me, author_id=operator)
        except store.RequestConflict as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        return request_detail(closed, me, operator)

    @app.post("/api/panel/requests/{request_id}/inventory", dependencies=limited)
    async def panel_inventory(request_id: int, request: Request):
        """Recepción verifica cupos en el PMS simulado. Lectura preliminar, con origen y hora.

        No bloquea cupos ni reserva. Ante caída (real o simulada con `simulate_down`) responde ok=false:
        el caso sigue a cargo de recepción y nada se presenta como disponible.
        """
        me = require_identity(request)
        row = scoped_request(request_id, request)
        require_demo(request)
        try:
            body = json.loads(await read_capped(request, 1024) or b"{}")
        except ValueError:
            return JSONResponse({"detail": "JSON inválido"}, status_code=400)
        if not row["checkin"] or not row["checkout"]:
            return JSONResponse({"detail": "La solicitud no tiene fechas: pídeselas al huésped"}, status_code=409)
        started = time.monotonic()
        now = clock()
        try:
            if isinstance(body, dict) and body.get("simulate_down"):
                # Caída simulada para la demostración: no se llama al PMS.
                raise PmsUnavailable("el PMS no respondió (caída simulada)")
            # Inventario de PRUEBA de la demo: este endpoint nunca toca el PMS de la operación.
            reading = await demo_pms.availability(
                date.fromisoformat(row["checkin"]), date.fromisoformat(row["checkout"]),
                int(row["adults"] or 1), int(row["children"] or 0),
            )
        except PmsUnavailable as exc:
            record_event(db, row["conversation_id"], "pms_read", now, {"ok": False, "latency_ms": 0})
            reason = str(exc) if "simulada" in str(exc) else "el PMS no respondió"
            text = f"Disponibilidad por verificar: PMS sin lectura ({reason}). No informar cupos al huésped."
            store.add_demo_message(db, row["conversation_id"], "note", text, now, author=me, request_id=row["id"])
            return {"ok": False, "reason": reason, "label": "Disponibilidad por verificar",
                    "request": request_detail(scoped_request(request_id, request), me, viewer(request)["operator"])}
        latency_ms = int((time.monotonic() - started) * 1000)
        record_event(db, row["conversation_id"], "pms_read", now, {"ok": True, "latency_ms": latency_ms})
        # Las 4 más económicas que caben: suficiente para responder sin un muro de texto (el PMS tiene 12 tipos).
        cheapest = sorted(reading.offers, key=lambda offer: offer.nightly_price_clp)[:4]
        offers = [
            {"code": offer.code, "name": offer.name, "available_units": offer.available_units,
             "nightly_price_clp": offer.nightly_price_clp}
            for offer in cheapest
        ]
        more = len(reading.offers) - len(offers)
        summary = ", ".join(f"{o['name']}: {o['available_units']} libre(s)" for o in offers) or "sin cupo"
        if more > 0:
            summary += f" y {more} tipo(s) más"
        source = "PMS simulado" if reading.simulated else "PMS"
        store.add_demo_message(
            db, row["conversation_id"], "note",
            f"{source} · lectura {reading.read_at[11:16]}: {summary}. Preliminar: no bloquea cupos.",
            now, author=me, request_id=row["id"],
        )
        return {"ok": True, "source": source, "read_at": reading.read_at, "simulated": reading.simulated,
                "offers": offers, "more": max(more, 0),
                "request": request_detail(scoped_request(request_id, request), me, viewer(request)["operator"])}

    @app.get("/api/panel/{conversation_id}", dependencies=limited)
    async def panel_data(conversation_id: int, request: Request):
        if panel_identity(request) is None:
            raise HTTPException(status_code=401, detail="Sesión del panel requerida")
        # Cada sesión ve solo su mundo: la demo no lee la operación real (ni otra corrida) y el personal no
        # lee la demo.
        if not conversation_visible(conversation_id, request):
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        source = store.conversation_source(db, conversation_id)
        state = store.get_state(db, conversation_id)
        data = dict(state.data)
        room = hotel.room(data["room_code"]) if data.get("room_code") else None
        row = store.active_prebooking(db, conversation_id)
        prebooking = None
        if row is not None:
            prebooking = {"status": row["status"], "expires_at": row["expires_at"], "room_code": row["room_code"]}
        pms_params = {"guest": state.contact_name or "", "conversation_id": conversation_id}
        if data.get("checkin"):
            pms_params.update(
                checkin=data["checkin"],
                checkout=data["checkout"],
                adults=data.get("adults", 1),
                children=data.get("children", 0),
            )
        if data.get("room_code"):
            pms_params["room_code"] = data["room_code"]
        return {
            "conversation_id": conversation_id,
            "contact_name": state.contact_name,
            "step": state.step,
            "data": data,
            "room_name": room["name"] if room else None,
            "prebooking": prebooking,
            "sla": {
                "started_at": state.sla_started_at,
                "stopped_at": state.sla_stopped_at,
                "amber_s": settings.sla_amber_s,
                "red_s": settings.sla_red_s,
            },
            "now": clock(),
            "pms_url": f"{settings.pms_staff_url.rstrip('/')}/admin?{urlencode(pms_params)}",
            "notes": store.list_notes(db, conversation_id),
            "messages": store.list_demo_messages(db, conversation_id) if source == store.DEMO_SOURCE else [],
        }

    @app.post("/api/panel/{conversation_id}/note", dependencies=limited)
    async def panel_add_note(conversation_id: int, request: Request):
        author = panel_identity(request)
        if author is None:
            raise HTTPException(status_code=401, detail="Sesión del panel requerida")
        if not conversation_visible(conversation_id, request):
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        try:
            body = json.loads(await read_capped(request, 4096))
        except ValueError:
            return JSONResponse({"detail": "JSON inválido"}, status_code=400)
        try:
            return store.add_note(db, conversation_id, author, body.get("body", ""), clock())
        except ValueError:
            return JSONResponse({"detail": "La nota está vacía"}, status_code=400)

    @app.get("/metricas", response_class=HTMLResponse, dependencies=limited)
    async def metrics_page(request: Request):
        # Invariante 8: las métricas exponen el operación del piloto; sin sesión ni token, 401 (nunca 403).
        if panel_identity(request) is None:
            raise HTTPException(status_code=401, detail="Sesión del panel requerida")
        return (STATIC / "metricas.html").read_text(encoding="utf-8")

    @app.get("/metricas/data.json", dependencies=limited)
    async def metrics_data(request: Request, days: int = Query(default=7, ge=1, le=366)):
        if panel_identity(request) is None:
            raise HTTPException(status_code=401, detail="Sesión del panel requerida")
        from copiloto.metrics import compute_metrics

        end = clock()
        # Cada sesión ve su mundo: la demo nunca se suma a las métricas de la operación (ni al revés), y una
        # sesión de la demo ve solo su corrida.
        if panel_is_demo(request):
            ids = run_conversations(viewer(request)["run"])
            return JSONResponse(compute_metrics(db, end - days * 86400, end + 1, settings, scope="demo",
                                                conversation_ids=ids))
        return JSONResponse(compute_metrics(db, end - days * 86400, end + 1, settings, scope="operation"))

    @app.get("/privacidad", response_class=HTMLResponse, dependencies=limited)
    async def privacy_page():
        return privacy.render(
            hotel,
            settings.llm_model if agent is not None else None,
            settings.llm_base_url,
            voice=tts is not None,
            retention_days=settings.retention_days,
            # Fuera de la portada (:8100 directo) el enlace de vuelta tiene que abrir la portada real.
            home_url=settings.landing_origin,
        )

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
        # El modo reportado es el que realmente sirve turnos: un agente inyectado sin AI_MODE sirve asistido.
        served_mode = (settings.ai_mode if settings.ai_mode != "off" else "assisted") if demo_uses_ai else "off"
        return {
            "engine": "ai" if demo_uses_ai else "guided",
            "hotel": {"name": hotel.hotel["name"], "channel_label": "WhatsApp simulado"},
            "menu": [title for title, _ in DEMO_MENU],
            "shift": shift_info(settings),
            "privacy_url": "/privacidad",
            "ai_enabled": demo_uses_ai,
            "mode": served_mode,
            "model": settings.llm_model if demo_uses_ai else None,
            "sandbox": settings.demo_sandbox_authorized,
            "autonomous_booking": (
                settings.autonomous_booking and settings.demo_sandbox_authorized and demo_uses_ai
            ),
            # Browser speech remains available without paid TTS credentials.
            "voice": demo_uses_ai and settings.demo_enabled,
            "tts": ("elevenlabs" if tts is not None else "piper" if piper is not None else "browser"),
            "max_message_chars": DEMO_MAX_MESSAGE,
            "messages_per_session": settings.demo_messages_per_session,
            "disclaimer": "Chat de prueba con datos ficticios: no escribas datos personales reales.",
        }

    async def demo_turn(request: Request, voice: bool) -> dict | JSONResponse:
        """Un turno de la demo, compartido por el chat de texto y la voz."""
        body = await demo_body(request)
        if isinstance(body, JSONResponse):
            return body
        message = body.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > DEMO_MAX_MESSAGE:
            return demo_error(400, f"El mensaje debe tener entre 1 y {DEMO_MAX_MESSAGE} caracteres")
        # Texto y voz comparten la sesión: el turno completo (cupo, modelo, guardado) va de a uno por sesión
        async with demo_session_lock(body["session_id"]):
            return await locked_demo_turn(body, message.strip(), voice)

    def demo_session_lock(session_id: str) -> asyncio.Lock:
        # Strong references from holders/waiters keep a shared lock alive; idle entries disappear.
        lock = session_locks.get(session_id)
        if lock is None:
            lock = session_locks[session_id] = asyncio.Lock()
        return lock

    def guest_request_view(conversation_id: int) -> dict | None:
        """Lo que el huésped sabe de su solicitud: número, quién la atiende y cuándo habrá respuesta.

        Nunca expone notas internas, el reloj de la meta ni datos de otras conversaciones.
        """
        row = store.latest_request(db, conversation_id)
        if row is None:
            return None
        status = row["status"]
        if status == "pendiente" and row["in_shift"]:
            label = "Enviada a recepción · te responderán por aquí"
        elif status == "pendiente":
            opening = settings.next_shift_start(row["created_at"])
            label = f"Guardada · recepción responde desde las {opening:%H:%M} del {long_date(opening.date())}"
        elif status == "en_atencion":
            label = f"{row['assignee']} de recepción está atendiendo tu solicitud"
        elif status == "respondida":
            label = f"Respondida por {row['assignee']} · recepción"
        else:
            label = "Atención cerrada · puedes escribir una nueva consulta"
        return {
            "code": row["code"],
            "status": status,
            "label": label,
            "assignee": row["assignee"],
            "in_shift": bool(row["in_shift"]),
            "open": status in store.OPEN_STATUSES,
        }

    def guest_snapshot(conversation_id: int | None, after_id: int = 0) -> dict:
        if conversation_id is None:
            return {"conversation_id": None, "step": None, "messages": [], "request": None,
                    "handled_by": "asistente", "quick_replies": []}
        messages = store.list_demo_messages(db, conversation_id, guest_view=True, after_id=after_id)
        request_view = guest_request_view(conversation_id)
        handled_by = "recepcion" if request_view and request_view["open"] else "asistente"
        quick: list[str] = []
        if handled_by == "asistente":
            last = store.list_demo_messages(db, conversation_id, limit=1, guest_view=True)
            if last and last[0]["role"] == "assistant" and last[0]["options"]:
                quick = last[0]["options"]
        return {
            "conversation_id": conversation_id,
            "step": store.get_state(db, conversation_id).step,
            "messages": messages,
            "request": request_view,
            "handled_by": handled_by,
            "quick_replies": quick,
        }

    def last_message_id(conversation_id: int) -> int:
        row = db.execute(
            "SELECT COALESCE(MAX(id), 0) AS id FROM demo_messages WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
        return row["id"]

    async def locked_demo_turn(body: dict, message: str, voice: bool) -> dict | JSONResponse:
        session_id = body["session_id"]
        client_id = body.get("client_message_id")
        if client_id is not None and (not isinstance(client_id, str) or not ACTION_ID.match(client_id)):
            return demo_error(422, "client_message_id inválido")
        shift = body.get("shift") if body.get("shift") in ("open", "closed") else None
        # Corrida (la emite el servidor): une este chat con la recepción que lo atiende. Una sesión no cambia de
        # corrida. Sin corrida (clientes antiguos o de prueba) el caso no llega a ninguna bandeja.
        run = body.get("run")
        if run is not None:
            if not isinstance(run, str) or not RUN_ID.match(run):
                return demo_error(422, "Corrida inválida")
            if not store.demo_run_active(db, run, clock(), settings.demo_session_ttl_s):
                return demo_error(404, "corrida_desconocida")
            if store.demo_session_run(db, session_id) not in (None, run):
                return demo_error(409, "Esta conversación es de otra corrida: empieza con «Otro huésped»")
        scope, digest = f"guest:{session_id}", store.fingerprint(message)
        action = None
        if client_id:
            try:
                action = store.check_action(db, scope, client_id, digest)
            except store.ActionConflict as exc:
                return demo_error(409, str(exc))
        if action is not None and action["state"] == "done":
            # Reintento de un mensaje ya procesado (p. ej. se cortó la respuesta): no se vuelve a ejecutar.
            snapshot = guest_snapshot(store.demo_conversation_for_session(db, session_id))
            return {**snapshot, "reply": "", "mode": "duplicate", "events": [], "duplicate": True,
                    "usage": {"messages_left": None, "llm_ms": 0, "tokens": None}}
        session = ai_sessions.load(db, f"demo:{session_id}", clock())
        saved = db.execute("SELECT * FROM demo_messages WHERE id = ?", (action["message_id"],)).fetchone() \
            if action is not None else None
        if saved is None:
            if session.msg_count >= settings.demo_messages_per_session:
                return demo_error(429, "Límite de mensajes de esta conversación: reiníciala para seguir", 3600)
            wait = demo_global_limiter.check("global")
            if wait is not None:
                return demo_error(429, "La demo alcanzó su límite por hora, vuelve en un rato", int(wait) + 1)
            session.msg_count += 1
            now = clock()
            # Ingreso atómico: el mensaje y su llave quedan juntos o no queda ninguno. Con recepción a cargo el
            # turno termina aquí ('done'); si no, queda 'started' hasta que el asistente conteste.
            with store.transaction(db):
                conversation_id = store.ensure_demo_conversation(db, session_id, now, run_id=run)
                open_row = store.guest_wrote_to_reception(db, conversation_id, now)
                saved = store.insert_demo_message(
                    db, conversation_id, "guest", message, now, request_id=open_row["id"] if open_row else None
                )
                if open_row is not None:
                    record_event(db, conversation_id, "inbound", now, {"greeting": False})
                if client_id:
                    state = "done" if open_row is not None else "started"
                    store.claim_action(db, scope, client_id, digest, now, state, saved["id"])
            ai_sessions.save(db, session, clock())
            answered = False
        else:
            # Reintento de un turno que se cortó después de guardar el mensaje: no se vuelve a guardar. Si el
            # asistente ya alcanzó a contestar, solo se cierra la llave; si no, se termina el turno con la hora
            # original del mensaje (así el motor reconoce un traspaso que ya ocurrió y no lo repite).
            conversation_id, now, open_row = saved["conversation_id"], saved["created_at"], None
            answered = db.execute(
                "SELECT 1 FROM demo_messages WHERE conversation_id = ? AND id > ? AND role != 'guest' LIMIT 1",
                (conversation_id, saved["id"]),
            ).fetchone() is not None
        first_new = saved["id"] - 1
        events: list[dict] = []
        reply, quick, mode, usage = "", [], "guided", {"llm_ms": 0, "tokens": None}
        # El id conversacional ya es un seudónimo estable de la sesión: los eventos sobreviven a su purga,
        # por lo que nunca deben retener la llave con la que el huésped accede a su hilo.
        request_id = f"demo:{conversation_id}:{session.msg_count}"

        def trace(outcome: str, latency_ms: int = 0, tools: list | None = None, tokens: int | None = None) -> None:
            """Traza por turno de la demo: sin texto del huésped, siempre etiquetada con su resultado."""
            record_demo_event(
                "ai_reply",
                {
                    "latency_ms": latency_ms,
                    "tools": tools or [],
                    "tokens": tokens,
                    "request_id": request_id,
                    "model": settings.llm_model,
                    "prompt_version": PROMPT_VERSION,
                    "outcome": outcome,
                },
            )

        if open_row is not None:
            # Recepción tiene el caso: el mensaje le llega a ella y el asistente no contesta (traspaso).
            mode, events = "human", [{"type": "to_reception", "request": open_row["code"]}]
        elif answered:
            events = [{"type": "recovered"}]
        elif demo_uses_ai:
            hooks = ToolHooks(
                conversation_id=None,
                in_shift=demo_settings(shift).in_shift(clock()),
                record=lambda kind, payload: record_demo_event(kind, payload),
                extra={"sandbox_only": True, "sandbox_authorized": settings.demo_sandbox_authorized},
            )
            try:
                result = await agent.respond(session, message, hooks, voice=voice)
                reply, quick, mode, events = result.reply or "", result.quick_replies, "ai", result.events
                usage = {"llm_ms": result.llm_ms, "tokens": result.tokens}
                trace(
                    "handoff" if getattr(result, "handed_off", False) or result.reply is None else "answered",
                    result.llm_ms,
                    result.tools,
                    result.tokens,
                )
                for rule in result.guardrails:
                    record_demo_event("ai_guardrail", {"rule": rule})
                if result.booking:
                    record_demo_event("ai_booking", {"booking_id": result.booking["booking_id"]})
            except LlmUnavailable as exc:
                reason = "timeout" if isinstance(exc, LlmTimeout) else "unavailable"
                trace("fallback")
                record_demo_event("ai_fallback", {"reason": reason})
                events = [{"type": "fallback", "reason": "ia_no_disponible"}]
                reply, quick = guided_reply(hotel, message)
            ai_sessions.save(db, session, clock())
            store.add_demo_message(db, conversation_id, "assistant", reply, now, options=quick[:4] or None)
            if any(event.get("type") == "handoff" for event in events):
                # Mismo traspaso que el flujo guiado: solicitud, reloj y estado en una transacción.
                demo_engine(shift).persist_external_handoff(conversation_id, DEMO_CHANNEL, "ai_handoff", now)
        else:
            # Flujo guiado real (el mismo motor del canal de Chatwoot) escribiendo por el canal de la demo.
            await demo_engine(shift)._guest_message(conversation_id, message, DEMO_CHANNEL, None, now)
            events = [{"type": "guided"}]
        if client_id and open_row is None:
            store.complete_action(db, scope, client_id, clock())
        snapshot = guest_snapshot(conversation_id, after_id=first_new)
        if mode == "guided":
            reply = "\n\n".join(item["body"] for item in snapshot["messages"] if item["role"] == "assistant")
            quick = snapshot["quick_replies"]
            if snapshot["request"] and snapshot["handled_by"] == "recepcion":
                events.append({"type": "handoff", "request": snapshot["request"]["code"]})
        payload = {
            **snapshot,
            "reply": reply,
            "mode": mode,
            "events": events,
            "quick_replies": list(quick)[:4],
            "duplicate": False,
            "usage": {"messages_left": max(settings.demo_messages_per_session - session.msg_count, 0), **usage},
        }
        if voice:
            payload["spoken_language"] = guess_language(message)
        return payload

    @app.post("/api/demo/chat")
    async def demo_chat(request: Request):
        return await demo_turn(request, voice=False)

    @app.get("/api/demo/conversation", dependencies=limited)
    async def demo_conversation(
        session_id: str = Query(min_length=1, max_length=64), after: int = Query(default=0, ge=0),
        run: str | None = Query(default=None, max_length=32),
    ):
        """Lo que ve el huésped: su hilo (sin notas internas), su solicitud y las respuestas de recepción."""
        if not settings.demo_enabled:
            raise HTTPException(status_code=404, detail="demo_disabled")
        if run is not None and store.demo_session_run(db, session_id) not in (None, run):
            # Una sesión de otra corrida se responde como desconocida: no se confirma que exista.
            return guest_snapshot(None)
        return guest_snapshot(store.demo_conversation_for_session(db, session_id), after_id=after)

    async def synthesize(text: str, language: str = "es") -> tuple[str | None, str | None, str | None]:
        """(audio base64, motivo si no hubo, formato). La voz nunca impide que el huésped lea la respuesta."""
        if not text.strip():
            return None, None, None
        if not voice_providers:
            return None, "voz_no_disponible", None
        key = hashlib.sha256(f"{language}|{text}".encode()).hexdigest()
        if key in audio_cache:
            audio_cache.move_to_end(key)
            encoded, fmt = audio_cache[key]
            return encoded, None, fmt
        size = len(text)
        error = "voz_no_disponible"
        for name, provider, fmt in voice_providers:
            if name == "elevenlabs" and not (voice_budget.fits(size) and voice_monthly_budget.fits(size)):
                error = "tope_de_voz"
                continue
            try:
                raw = await provider.synthesize(text, language=language)
            except TtsUnavailable:
                logger.warning("El proveedor de voz %s no respondió; se prueba el siguiente", name)
                continue
            if name == "elevenlabs":
                voice_budget.take(size)
                voice_monthly_budget.take(size)
            encoded = base64.b64encode(raw).decode("ascii")
            audio_cache[key] = (encoded, fmt)
            if len(audio_cache) > AUDIO_CACHE_MAX:
                audio_cache.popitem(last=False)
            return encoded, None, fmt
        return None, error, None

    @app.get("/api/demo/voice/greeting", dependencies=limited)
    async def demo_voice_greeting(lang: str = Query(default="es", pattern="^(es|en)$")):
        if not settings.demo_enabled:
            return demo_error(503, "voz_no_disponible")
        text = speakable(greeting_for(lang, hotel.hotel["name"]), settings.voice_max_chars + 120)
        async with greeting_lock:  # una sola síntesis en vuelo por idioma: cada saludo se paga una vez
            if lang not in greeting_audio:
                audio, error, fmt = await synthesize(text, lang)
                if audio is None:
                    return {
                        "text": text,
                        "audio_b64": None,
                        "audio_format": None,
                        "voice_error": error,
                        "language": lang,
                    }
                greeting_audio[lang] = (audio, fmt)
        audio, fmt = greeting_audio[lang]
        return {"text": text, "audio_b64": audio, "audio_format": fmt, "voice_error": None, "language": lang}

    @app.post("/api/demo/voice")
    async def demo_voice(request: Request):
        """Turno por voz: se sintetiza solo la respuesta del asistente, nunca texto enviado por el navegador."""
        turn = await demo_turn(request, voice=True)
        if isinstance(turn, JSONResponse):
            return turn
        language = turn["spoken_language"]
        spoken = speakable(turn["reply"], settings.voice_max_chars)
        audio, error, fmt = await synthesize(spoken, language)
        return {**turn, "spoken": spoken, "audio_b64": audio, "audio_format": fmt, "voice_error": error}

    @app.post("/api/demo/reset")
    async def demo_reset(request: Request):
        body = await demo_body(request)
        if isinstance(body, JSONResponse):
            return body
        async with demo_session_lock(body["session_id"]):
            ai_sessions.delete(db, f"demo:{body['session_id']}")
            store.reset_demo_conversation(db, body["session_id"])
        return {"status": "ok"}

    def record_demo_event(kind: str, payload: dict) -> None:
        record_event(db, 0, kind, clock(), payload)

    return app
