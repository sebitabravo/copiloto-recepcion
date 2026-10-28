"""Configuración del copiloto, leída del entorno."""

import os
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.strip().split(":")
    return time(int(hours), int(minutes))


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
    public_url: str = "http://localhost:8100"
    timezone: str = "America/Santiago"
    shift_start: str = "08:00"
    shift_end: str = "22:00"
    fixed_monthly_clp: int = 90000
    usage_m_clp: int = 0
    prebooking_minutes: int = 15
    retention_days: int = 90
    sla_amber_s: int = 120
    sla_red_s: int = 180
    sla_interval_s: float = 10.0
    signature_tolerance_s: int = 300
    # IA conversacional: off (flujo guiado), assisted (no reserva) o full (también reserva en el PMS simulado)
    ai_mode: str = "off"
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-flash"
    llm_timeout_s: float = 25.0
    llm_max_tokens: int = 500
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
            pms_staff_token=env.get("PMS_STAFF_TOKEN", ""),
            demo_enabled=env.get("DEMO_ENABLED", "1") not in ("0", "false", "no"),
            landing_origin=env.get("LANDING_ORIGIN", cls.landing_origin).rstrip("/"),
            panel_token=env.get("PANEL_TOKEN", ""),
            pms_url=env.get("PMS_URL", cls.pms_url),
            pms_staff_url=env.get("PMS_STAFF_URL", cls.pms_staff_url),
            public_url=env.get("COPILOTO_PUBLIC_URL", cls.public_url),
            timezone=env.get("TIMEZONE", cls.timezone),
            shift_start=env.get("SHIFT_START", cls.shift_start),
            shift_end=env.get("SHIFT_END", cls.shift_end),
            fixed_monthly_clp=int(env.get("FIXED_MONTHLY_CLP", "90000")),
            usage_m_clp=int(env.get("USAGE_M_CLP", "0")),
            retention_days=int(env.get("RETENTION_DAYS", "90")),
        )

    def validate_runtime(self) -> None:
        """Falla al arrancar si falta un secreto: sin esto cada webhook respondería 401 sin explicación."""
        secrets = {"WEBHOOK_SECRET": self.webhook_secret, "PMS_EVENTS_SECRET": self.pms_events_secret,
                   "PANEL_TOKEN": self.panel_token, "PSEUDONYM_SALT": self.pseudonym_salt,
                   "CHATWOOT_BOT_TOKEN": self.chatwoot_bot_token}
        weak = sorted(name for name, value in secrets.items() if len(value) < 16)
        if self.ai_mode not in ("off", "assisted", "full"):
            raise ValueError("AI_MODE debe ser off, assisted o full")
        if self.ai_mode == "full" and self.llm_api_key and not self.pms_staff_token:
            raise ValueError("AI_MODE=full necesita PMS_STAFF_TOKEN para crear reservas en el PMS")
        if weak:
            raise ValueError("Secretos ausentes o demasiado cortos (mínimo 16 caracteres): " + ", ".join(weak))

    @property
    def ai_active(self) -> bool:
        """La IA solo se usa con modo distinto de off y una API key; sin key el asistente sigue guiado."""
        return self.ai_mode in ("assisted", "full") and bool(self.llm_api_key)

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
