"""Esquema SQLite de eventos del copiloto y escritura idempotente.

Todas las métricas (`metrics.py`) salen de la tabla `events`. Convenciones de `payload` (JSON):

- inbound:            {"greeting": bool}
- faq_answered:       {"faq_id": str, "inbound_ts": float}   # ts - inbound_ts = latencia de la FAQ
- location_shown:     {"inbound_ts": float}                     # ts - inbound_ts = latencia de la ubicación
- commercial_started: {"in_shift": bool, "inbound_ts": float, "handoff_in_shift": bool, "request_id": int}
                       # in_shift = turno AL INGRESO (inbound_ts, cuando ENTRÓ la consulta comercial, antes de
                       # capturar datos y de asignar): ahí parte el reloj de 180 s y eso decide si cuenta para
                       # la meta. handoff_in_shift = si recepción atendía al derivar (solo para el mensaje).
- night_capture:      {"complete": bool, "request_id": int}  # complete=True si hay fechas y huéspedes
- pms_read:           {"ok": bool, "latency_ms": int}
- handoff:            {"reason": "commercial" | "pms_down" | "human_requested"
                       | "no_entendi_tres_veces" | "error" | "ai_handoff"}
- human_first_reply:  {"user_id": int, "request_id": int}  # primera respuesta pertinente: detiene el reloj
- human_ack:          {"author": str, "request_id": int}     # acuse («ya te reviso»): NO detiene el reloj
- request_created:    {"request_id": int, "code": str, "in_shift": bool}
- request_taken:      {"request_id": int, "assignee": str}    # asignar no reinicia el reloj
- request_closed:     {"request_id": int}
- sla_breached:       {"elapsed_s": int}                      # venció el plazo sin respuesta pertinente
- prebooking_created: {"prebooking_id": int}
- prebooking_expired: {"prebooking_id": int}
- booking_confirmed:  {"booking_id": int, "source": "personal" | "ia"}
- ai_reply:           {"latency_ms": int, "tools": [str], "tokens": int | None,
                       "request_id": str, "model": str, "prompt_version": str,
                       "outcome": "answered" | "fallback" | "handoff" | "error"}
                       # request_id determinista (conversación + turno, sin PII); nunca guarda texto
- ai_fallback:        {"reason": "timeout" | "unavailable" | "invalid_output" | "guardrail"}
                       # el turno se degradó al flujo guiado; siempre con un ai_reply outcome=fallback par
- ai_booking:         {"booking_id": int}
- ai_guardrail:       {"rule": str}      # la salida de la IA se corrigió (p. ej. confirmación sin reserva)

`ts` son segundos epoch UTC (REAL). Cada evento guarda su `source` (columna): 'demo' o 'chatwoot' (operación),
para que la demo nunca se mezcle con las métricas reales. `request_id` en el payload mide por SOLICITUD (dos
solicitudes del mismo hilo son dos mediciones). Los eventos anteriores a esa columna y a `request_id` son datos
históricos incompletos: metrics.py los mide por conversación y lo informa aparte.
"""

import json
import sqlite3
from collections.abc import Iterable

EVENT_KINDS = frozenset(
    {
        "inbound",
        "faq_answered",
        "location_shown",
        "commercial_started",
        "pms_read",
        "handoff",
        "human_first_reply",
        "human_ack",
        "request_created",
        "request_taken",
        "request_closed",
        "sla_breached",
        "night_capture",
        "prebooking_created",
        "prebooking_expired",
        "booking_confirmed",
        "ai_reply",
        "ai_fallback",
        "ai_booking",
        "ai_guardrail",
    }
)

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

-- Llaves de idempotencia de las acciones de la demo (mensaje del huésped, respuesta de recepción).
-- scope = 'guest:<sesión>' o 'staff:<solicitud>': la misma llave en otra sesión u otro caso es otra acción.
-- fingerprint = hash del contenido: reutilizar la llave con otro texto es un conflicto, no un duplicado.
-- state: 'started' = el mensaje quedó guardado y falta terminar el turno; 'done' = la acción terminó.
CREATE TABLE IF NOT EXISTS action_keys (
    scope TEXT NOT NULL,
    client_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    state TEXT NOT NULL,
    message_id INTEGER,
    created_at REAL NOT NULL,
    completed_at REAL,
    PRIMARY KEY (scope, client_id)
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

-- Notas del personal: lo que la persona de recepción deja para el siguiente turno.
CREATE TABLE IF NOT EXISTS staff_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    author TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS staff_notes_conv ON staff_notes(conversation_id, created_at);

-- Espacio aislado de la demostración: mapa sesión → conversación propia (ids negativos) y su transcripción.
CREATE TABLE IF NOT EXISTS demo_conversations (
    session_id TEXT PRIMARY KEY,
    conversation_id INTEGER NOT NULL UNIQUE,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS demo_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS demo_messages_conv ON demo_messages(conversation_id, id);

-- Solicitud a recepción: una por traspaso, vinculada al hilo. Es la fuente de verdad de la bandeja:
-- estado de ATENCIÓN (pendiente → en_atencion → respondida → cerrada) y estado de RESERVA por separado.
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    conversation_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    channel TEXT NOT NULL,
    reason TEXT NOT NULL,
    in_shift INTEGER NOT NULL,
    commercial_at REAL NOT NULL,
    created_at REAL NOT NULL,
    checkin TEXT,
    checkout TEXT,
    adults INTEGER,
    children INTEGER,
    room_code TEXT,
    status TEXT NOT NULL DEFAULT 'pendiente',
    reservation_status TEXT NOT NULL DEFAULT 'pendiente_confirmacion',
    assignee TEXT,
    taken_at REAL,
    first_answer_at REAL,
    last_guest_at REAL,
    breached_at REAL,
    closed_at REAL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS requests_conv ON requests(conversation_id, id);
CREATE INDEX IF NOT EXISTS requests_source ON requests(source, status);
"""

# Columnas agregadas después de la primera versión del esquema: (tabla, columna, definición).
MIGRATIONS = (
    ("conversation_state", "source", "TEXT NOT NULL DEFAULT 'chatwoot'"),
    # Botones de una pregunta guiada, autor y tipo (respuesta o acuse) de un mensaje del personal, y la
    # solicitud a la que pertenece. La idempotencia de cada acción vive en processed_messages.
    ("demo_messages", "options", "TEXT"),
    ("demo_messages", "author", "TEXT"),
    ("demo_messages", "kind", "TEXT"),
    ("demo_messages", "request_id", "INTEGER"),
    # Turno al ingreso de la consulta comercial (decide la meta); in_shift queda como el turno al derivar.
    ("requests", "intake_in_shift", "INTEGER"),
    # Origen del evento: 'demo' u operación ('chatwoot'). NULL = evento histórico, anterior a la columna.
    ("events", "source", "TEXT"),
)

DEMO = "demo"
OPERATION = "chatwoot"


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=15, isolation_level=None, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_db(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA)
    # Migración de bases ya creadas: columnas nuevas sin perder datos.
    for table, column, definition in MIGRATIONS:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def event_source(connection: sqlite3.Connection, conversation_id: int) -> str:
    """Origen de una conversación al escribir el evento (cuando todavía existe su estado).

    0 = eventos de la demo sin conversación (trazas de IA). Un id negativo es de la demo si está registrado
    como tal; los ids positivos los asigna Chatwoot (operación).
    """
    if conversation_id == 0:
        return DEMO
    row = connection.execute(
        "SELECT source FROM conversation_state WHERE conversation_id = ?", (conversation_id,)
    ).fetchone()
    if row is not None:
        return row["source"]
    demo = connection.execute(
        "SELECT 1 FROM demo_conversations WHERE conversation_id = ?", (conversation_id,)
    ).fetchone()
    return DEMO if demo is not None else OPERATION


def record_event(
    connection: sqlite3.Connection, conversation_id: int, kind: str, ts: float, payload: dict | None = None,
    source: str | None = None,
) -> int:
    if kind not in EVENT_KINDS:
        raise ValueError(f"Unknown event kind: {kind}")
    cursor = connection.execute(
        "INSERT INTO events(conversation_id, kind, ts, payload, source) VALUES (?, ?, ?, ?, ?)",
        (
            conversation_id,
            kind,
            ts,
            json.dumps(payload or {}, ensure_ascii=False),
            source or event_source(connection, conversation_id),
        ),
    )
    return cursor.lastrowid


def mark_processed(connection: sqlite3.Connection, message_id: str, ts: float) -> bool:
    """Devuelve True si el mensaje es nuevo; False si ya se procesó (idempotencia, R6)."""
    cursor = connection.execute(
        "INSERT OR IGNORE INTO processed_messages(message_id, ts) VALUES (?, ?)", (message_id, ts)
    )
    return cursor.rowcount == 1


def events_between(
    connection: sqlite3.Connection, start: float, end: float, kinds: Iterable[str] | None = None
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM events WHERE ts >= ? AND ts < ?"
    params: list = [start, end]
    if kinds:
        kinds = list(kinds)
        sql += f" AND kind IN ({','.join('?' for _ in kinds)})"
        params.extend(kinds)
    return connection.execute(sql + " ORDER BY ts, id", params).fetchall()
