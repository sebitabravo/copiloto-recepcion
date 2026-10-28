"""Esquema SQLite de eventos del copiloto y escritura idempotente.

Todas las métricas (`metrics.py`) salen de la tabla `events`. Convenciones de `payload` (JSON):

- inbound:            {"text": str, "greeting": bool}
- faq_answered:       {"faq_id": str, "inbound_ts": float}   # ts - inbound_ts = latencia de la FAQ
- location_shown:     {}
- commercial_started: {"in_shift": bool}                     # in_shift=False es una consulta nocturna
- night_capture:      {"complete": bool}                     # complete=True si hay fechas y huéspedes
- pms_read:           {"ok": bool, "latency_ms": int}
- handoff:            {"reason": "commercial" | "night" | "pms_down" | "human_requested"}
- human_first_reply:  {"user_id": int}
- prebooking_created: {"prebooking_id": int}
- prebooking_expired: {"prebooking_id": int}
- booking_confirmed:  {"booking_id": int, "source": "personal" | "ia"}
- ai_reply:           {"latency_ms": int, "tools": [str], "tokens": int | None}   # nunca guarda texto
- ai_booking:         {"booking_id": int}
- ai_guardrail:       {"rule": str}      # la salida de la IA se corrigió (p. ej. confirmación sin reserva)

`ts` son segundos epoch UTC (REAL).
"""

import json
import sqlite3
from collections.abc import Iterable

EVENT_KINDS = frozenset({
    "inbound", "faq_answered", "location_shown", "commercial_started", "pms_read", "handoff",
    "human_first_reply", "night_capture", "prebooking_created", "prebooking_expired",
    "booking_confirmed", "ai_reply", "ai_booking", "ai_guardrail",
})

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    ts REAL NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS events_conv_ts ON events(conversation_id, ts);
CREATE INDEX IF NOT EXISTS events_kind_ts ON events(kind, ts);

CREATE TABLE IF NOT EXISTS processed_messages (
    message_id TEXT PRIMARY KEY,
    ts REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_state (
    conversation_id INTEGER PRIMARY KEY,
    step TEXT NOT NULL DEFAULT 'start',
    data TEXT NOT NULL DEFAULT '{}',
    contact_name TEXT,
    contact_ref TEXT,
    sla_started_at REAL,
    sla_stopped_at REAL,
    sla_amber_done INTEGER NOT NULL DEFAULT 0,
    sla_red_done INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_sessions (
    session_id TEXT PRIMARY KEY,
    history TEXT NOT NULL DEFAULT '[]',
    state TEXT NOT NULL DEFAULT '{}',
    msg_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS prebookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    checkin TEXT NOT NULL,
    checkout TEXT NOT NULL,
    adults INTEGER NOT NULL,
    children INTEGER NOT NULL,
    room_code TEXT,
    read_at TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS prebookings_conv ON prebookings(conversation_id);
"""


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=15, isolation_level=None, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)


def record_event(connection: sqlite3.Connection, conversation_id: int, kind: str, ts: float,
                 payload: dict | None = None) -> int:
    if kind not in EVENT_KINDS:
        raise ValueError(f"Unknown event kind: {kind}")
    cursor = connection.execute(
        "INSERT INTO events(conversation_id, kind, ts, payload) VALUES (?, ?, ?, ?)",
        (conversation_id, kind, ts, json.dumps(payload or {}, ensure_ascii=False)),
    )
    return cursor.lastrowid


def mark_processed(connection: sqlite3.Connection, message_id: str, ts: float) -> bool:
    """Devuelve True si el mensaje es nuevo; False si ya se procesó (idempotencia, R6)."""
    cursor = connection.execute(
        "INSERT OR IGNORE INTO processed_messages(message_id, ts) VALUES (?, ?)", (message_id, ts)
    )
    return cursor.rowcount == 1


def events_between(connection: sqlite3.Connection, start: float, end: float,
                   kinds: Iterable[str] | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM events WHERE ts >= ? AND ts < ?"
    params: list = [start, end]
    if kinds:
        kinds = list(kinds)
        sql += f" AND kind IN ({','.join('?' for _ in kinds)})"
        params.extend(kinds)
    return connection.execute(sql + " ORDER BY ts, id", params).fetchall()
