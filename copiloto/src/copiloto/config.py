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
    webhook_secret: str = ""
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
            webhook_secret=env.get("WEBHOOK_SECRET", ""),
            pms_events_secret=env.get("PMS_EVENTS_SECRET", ""),
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

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def local(self, epoch: float) -> datetime:
        return datetime.fromtimestamp(epoch, self.tz)

    def in_shift(self, epoch: float) -> bool:
        """True si `epoch` cae dentro del turno humano (soporta turnos que cruzan medianoche)."""
        start, end = _parse_hhmm(self.shift_start), _parse_hhmm(self.shift_end)
        current = self.local(epoch).time().replace(second=0, microsecond=0)
        if start <= end:
            return start <= current < end
        return current >= start or current < end
