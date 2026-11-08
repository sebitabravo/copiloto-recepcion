"""Configuración del copiloto, leída del entorno."""

import os
from dataclasses import dataclass
from datetime import datetime, time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.strip().split(":")
    return time(int(hours), int(minutes))


# Valores que activan una bandera booleana del entorno; se comparan en minúsculas y sin espacios,
# igual que la lectura de AI_MODE.
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def int_env(env: dict[str, str], name: str, default: int) -> int:
    """Entero opcional del entorno. Ausente o en blanco cuenta como «sin configurar»: el compose pasa
    `${VAR:-}` para que las perillas documentadas existan aunque el .env no las defina, y un valor
    vacío antes rompía int(""). No muta el entorno; app.py resuelve su respaldo con este mismo helper."""
    raw = (env.get(name) or "").strip()
    return int(raw) if raw else default


def float_env(env: dict[str, str], name: str, default: float | None) -> float | None:
    """Decimal opcional del entorno, con la misma regla que `int_env`: ausente o en blanco usa el valor por defecto."""
    raw = (env.get(name) or "").strip()
    return float(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    hotel_data_path: str = "../data/hotel.yaml"
    db_path: str = "./copiloto.sqlite"
    chatwoot_url: str = "http://chatwoot:3000"
    chatwoot_public_url: str = "http://localhost:3000"
    chatwoot_account_id: int = 1
    chatwoot_bot_token: str = ""
    chatwoot_team_id: int | None = None
    env: str = "development"
    webhook_secret: str = ""
    pseudonym_salt: str = ""
    max_body_bytes: int = 262144
    public_rate_per_min: int = 60
    pms_events_secret: str = ""
    panel_token: str = ""
    pms_url: str = "http://pms-mock:8200"
    pms_staff_url: str = "http://localhost:8200"
    pms_timeout_s: float = 4.0
    # Conector del PMS: "http" usa el contrato HTTP del adaptador; "none" deja al hotel sin PMS.
    pms_adapter: str = "http"
    pms_availability_path: str = "/api/v1/availability"
    pms_booking_path: str = "/api/v1/bookings"
    pms_auth_header: str = "X-Staff-Token"
    public_url: str = "http://localhost:8100"
    timezone: str = "America/Santiago"
    shift_start: str = "08:00"
    shift_end: str = "22:00"
    fixed_monthly_clp: int = 90000
    usage_m_clp: int = 0
    prebooking_minutes: int = 15  # lo promete docs/ia.md vía la variable PREBOOKING_MINUTES
    retention_days: int = 90
    sla_amber_s: int = 120
    sla_red_s: int = 180
    sla_interval_s: float = 10.0
    signature_tolerance_s: int = 300
    # IA conversacional: off (flujo guiado), assisted (no reserva) o full (también reserva en el PMS simulado)
    ai_mode: str = "off"
    # Por defecto, modelo local: nada de APIs de pago. Sin `LLM_API_KEY` no hay IA (flujo guiado);
    # para el modelo local se pone cualquier valor, por ejemplo `local`.
    llm_base_url: str = "http://host.docker.internal:11434/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen2.5-7b-instruct"
    llm_timeout_s: float = 25.0
    # Tope del turno completo (reintentos y herramientas incluidos): pasado ese plazo se vuelve al menú guiado
    ai_turn_timeout_s: float = 12.0
    llm_max_tokens: int = 500
    # Muestreo: temperatura fija salvo `LLM_TEMPERATURE`; `top_p` solo se envía si `LLM_TOP_P` está definido
    llm_temperature: float = 0.3
    llm_top_p: float | None = None
    # Voz de la demo (opcional): sin clave y sin voz elegida, la demo sigue solo con texto
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_voice_id_en: str = ""
    elevenlabs_model: str = "eleven_flash_v2_5"
    voice_max_chars: int = 450
    voice_chars_per_hour: int = 20000
    # Starter de ElevenLabs incluye 40 000 caracteres al mes: el tope mensual queda bajo ese límite
    voice_chars_per_month: int = 30000
    # Respaldo local con Piper (opcional): ruta al modelo ONNX y a su configuración
    piper_model_path: str = ""
    piper_config_path: str = ""
    ai_max_history: int = 12
    pms_staff_token: str = ""
    demo_enabled: bool = True
    landing_origin: str = "http://localhost:8080"
    demo_messages_per_session: int = 30
    demo_ip_per_min: int = 20
    demo_global_per_hour: int = 300
    demo_session_ttl_s: int = 86400

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        team = env.get("CHATWOOT_TEAM_ID")
        return cls(
            hotel_data_path=env.get("HOTEL_DATA_PATH", cls.hotel_data_path),
            db_path=env.get("COPILOTO_DB_PATH", cls.db_path),
            chatwoot_url=env.get("CHATWOOT_URL", cls.chatwoot_url),
            chatwoot_public_url=env.get("CHATWOOT_PUBLIC_URL", cls.chatwoot_public_url),
            chatwoot_account_id=int(env.get("CHATWOOT_ACCOUNT_ID", "1")),
            chatwoot_bot_token=env.get("CHATWOOT_BOT_TOKEN", ""),
            chatwoot_team_id=int(team) if team else None,
            env=env.get("COPILOTO_ENV", "development"),
            webhook_secret=env.get("WEBHOOK_SECRET", ""),
            pseudonym_salt=env.get("PSEUDONYM_SALT", ""),
            pms_events_secret=env.get("PMS_EVENTS_SECRET", ""),
            ai_mode=env.get("AI_MODE", "off").strip().lower(),
            llm_base_url=env.get("LLM_BASE_URL", cls.llm_base_url).rstrip("/"),
            llm_api_key=env.get("LLM_API_KEY", ""),
            llm_model=env.get("LLM_MODEL", cls.llm_model),
            # Un modelo local en CPU puede necesitar más de 25 s por turno.
            llm_timeout_s=float(env.get("LLM_TIMEOUT_S", cls.llm_timeout_s)),
            ai_turn_timeout_s=float(env.get("AI_TURN_TIMEOUT_S", cls.ai_turn_timeout_s)),
            llm_temperature=float_env(env, "LLM_TEMPERATURE", cls.llm_temperature),
            llm_top_p=float_env(env, "LLM_TOP_P", cls.llm_top_p),
            elevenlabs_api_key=env.get("ELEVENLABS_API_KEY", ""),
            elevenlabs_voice_id=env.get("ELEVENLABS_VOICE_ID", ""),
            elevenlabs_voice_id_en=env.get("ELEVENLABS_VOICE_ID_EN", ""),
            elevenlabs_model=env.get("ELEVENLABS_MODEL", cls.elevenlabs_model),
            voice_chars_per_hour=int(env.get("VOICE_CHARS_PER_HOUR", cls.voice_chars_per_hour)),
            voice_chars_per_month=int(env.get("VOICE_CHARS_PER_MONTH", cls.voice_chars_per_month)),
            piper_model_path=env.get("PIPER_MODEL_PATH", ""),
            piper_config_path=env.get("PIPER_CONFIG_PATH", ""),
            pms_staff_token=env.get("PMS_STAFF_TOKEN", ""),
            demo_enabled=env.get("DEMO_ENABLED", "1").strip().lower() in _TRUTHY,
            landing_origin=env.get("LANDING_ORIGIN", cls.landing_origin).rstrip("/"),
            panel_token=env.get("PANEL_TOKEN", ""),
            pms_url=env.get("PMS_URL", cls.pms_url),
            pms_staff_url=env.get("PMS_STAFF_URL", cls.pms_staff_url),
            pms_adapter=env.get("PMS_ADAPTER", cls.pms_adapter).strip().lower(),
            pms_availability_path=env.get("PMS_AVAILABILITY_PATH", cls.pms_availability_path),
            pms_booking_path=env.get("PMS_BOOKING_PATH", cls.pms_booking_path),
            pms_auth_header=env.get("PMS_AUTH_HEADER", cls.pms_auth_header),
            public_url=env.get("COPILOTO_PUBLIC_URL", cls.public_url),
            timezone=env.get("TIMEZONE", cls.timezone),
            shift_start=env.get("SHIFT_START", cls.shift_start),
            shift_end=env.get("SHIFT_END", cls.shift_end),
            fixed_monthly_clp=int(env.get("FIXED_MONTHLY_CLP", "90000")),
            usage_m_clp=int(env.get("USAGE_M_CLP", "0")),
            prebooking_minutes=int_env(env, "PREBOOKING_MINUTES", cls.prebooking_minutes),
            retention_days=int_env(env, "RETENTION_DAYS", cls.retention_days),
        )

    def validate_runtime(self) -> None:
        """Falla al arrancar si falta un secreto: sin esto cada webhook respondería 401 sin explicación."""
        secrets = {
            "WEBHOOK_SECRET": self.webhook_secret,
            "PMS_EVENTS_SECRET": self.pms_events_secret,
            "PANEL_TOKEN": self.panel_token,
            "PSEUDONYM_SALT": self.pseudonym_salt,
            "CHATWOOT_BOT_TOKEN": self.chatwoot_bot_token,
        }
        weak = sorted(name for name, value in secrets.items() if len(value) < 16)
        if self.ai_mode not in ("off", "assisted", "full"):
            raise ValueError("AI_MODE debe ser off, assisted o full")
        if self.ai_mode == "full" and self.llm_api_key and not self.pms_staff_token:
            raise ValueError("AI_MODE=full necesita PMS_STAFF_TOKEN para crear reservas en el PMS")
        if weak:
            raise ValueError("Secretos ausentes o demasiado cortos (mínimo 16 caracteres): " + ", ".join(weak))
        public = urlsplit(self.public_url)
        if self.env == "production" and not (
            public.scheme == "https"
            and public.hostname
            or public.scheme == "http"
            and public.hostname in ("localhost", "127.0.0.1")
        ):
            raise ValueError("COPILOTO_PUBLIC_URL necesita HTTPS fuera de localhost/127.0.0.1")

    @property
    def demo_sandbox_authorized(self) -> bool:
        """Local demo allowlist, not proof that an arbitrary PMS is a sandbox."""
        return (
            self.pms_adapter == "http"
            and self.pms_booking_path == "/api/v1/bookings"
            and self.pms_url.rstrip("/") in {"http://pms-mock:8200", "http://localhost:8200", "http://127.0.0.1:8200"}
        )

    @property
    def ai_active(self) -> bool:
        """La IA solo se usa con modo distinto de off y una API key; sin key el asistente sigue guiado."""
        return self.ai_mode in ("assisted", "full") and bool(self.llm_api_key)

    @property
    def voice_active(self) -> bool:
        """La voz necesita la IA activa, la clave de ElevenLabs y una voz elegida."""
        return self.ai_active and bool(self.elevenlabs_api_key) and bool(self.elevenlabs_voice_id)

    @property
    def autonomous_booking(self) -> bool:
        return self.ai_active and self.ai_mode == "full" and bool(self.pms_staff_token)

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def local(self, epoch: float) -> datetime:
        return datetime.fromtimestamp(epoch, self.tz)

    def in_shift(self, epoch: float) -> bool:
        """True si `epoch` cae dentro del turno humano. Soporta turnos que cruzan medianoche y, con inicio
        igual al fin, un turno de 24 horas (sin la ventana muerta de un minuto de 23:59 a 00:00)."""
        start, end = _parse_hhmm(self.shift_start), _parse_hhmm(self.shift_end)
        if start == end:
            return True
        current = self.local(epoch).time().replace(second=0, microsecond=0)
        if start <= end:
            return start <= current < end
        return current >= start or current < end
