"""Persistencia del estado conversacional, las pre-reservas auxiliares y la retención de datos."""

import hashlib
import hmac
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field

# Origen de una conversación: la operación real (Chatwoot) o el espacio aislado de la demostración.
DEMO_SOURCE = "demo"
OPERATIONAL_SOURCE = "chatwoot"


@contextmanager
def transaction(db: sqlite3.Connection):
    """Agrupa escrituras en una transacción: o quedan todas o ninguna si el proceso falla a mitad."""
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        db.execute("ROLLBACK")
        raise
    db.execute("COMMIT")


@dataclass
class ConversationState:
    conversation_id: int
    step: str = "start"
    data: dict = field(default_factory=dict)
    contact_name: str | None = None
    sla_started_at: float | None = None
    sla_stopped_at: float | None = None
    sla_amber_done: bool = False
    sla_red_done: bool = False

    def reset_session(self) -> None:
        """Nueva consulta de un huésped que ya fue derivado: conserva el nombre y reinicia el resto."""
        self.step, self.data = "start", {}
        self.sla_started_at = self.sla_stopped_at = None
        self.sla_amber_done = self.sla_red_done = False


def get_state(db: sqlite3.Connection, conversation_id: int) -> ConversationState:
    row = db.execute("SELECT * FROM conversation_state WHERE conversation_id = ?", (conversation_id,)).fetchone()
    if row is None:
        return ConversationState(conversation_id)
    return ConversationState(
        conversation_id,
        row["step"],
        json.loads(row["data"]),
        row["contact_name"],
        row["sla_started_at"],
        row["sla_stopped_at"],
        bool(row["sla_amber_done"]),
        bool(row["sla_red_done"]),
    )


def save_state(db: sqlite3.Connection, state: ConversationState, now: float) -> None:
    """Guarda el estado conversacional. Las columnas del SLA solo cambian con start/stop/mark/clear_sla,
    para que una escritura atrasada nunca pise el cronómetro (p. ej. una respuesta humana ya registrada)."""
    db.execute(
        """INSERT INTO conversation_state(conversation_id, step, data, contact_name,
               sla_started_at, sla_stopped_at, sla_amber_done, sla_red_done, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(conversation_id) DO UPDATE SET step=excluded.step, data=excluded.data,
               contact_name=excluded.contact_name, updated_at=excluded.updated_at""",
        (
            state.conversation_id,
            state.step,
            json.dumps(state.data, ensure_ascii=False),
            state.contact_name,
            state.sla_started_at,
            state.sla_stopped_at,
            int(state.sla_amber_done),
            int(state.sla_red_done),
            now,
        ),
    )


def start_sla(db: sqlite3.Connection, conversation_id: int, now: float) -> None:
    """Arranca el reloj una sola vez: asignar o reabrir no lo reinicia."""
    db.execute(
        "UPDATE conversation_state SET sla_started_at = ? WHERE conversation_id = ? AND sla_started_at IS NULL",
        (now, conversation_id),
    )


def stop_sla(db: sqlite3.Connection, conversation_id: int, now: float) -> bool:
    """Detiene el reloj con la primera respuesta humana. True si efectivamente lo detuvo."""
    cursor = db.execute(
        "UPDATE conversation_state SET sla_stopped_at = ? WHERE conversation_id = ? "
        "AND sla_started_at IS NOT NULL AND sla_stopped_at IS NULL",
        (now, conversation_id),
    )
    return cursor.rowcount == 1


def mark_sla(db: sqlite3.Connection, conversation_id: int, amber: bool = False, red: bool = False) -> None:
    if amber:
        db.execute("UPDATE conversation_state SET sla_amber_done = 1 WHERE conversation_id = ?", (conversation_id,))
    if red:
        db.execute(
            "UPDATE conversation_state SET sla_amber_done = 1, sla_red_done = 1 WHERE conversation_id = ?",
            (conversation_id,),
        )


def clear_sla(db: sqlite3.Connection, conversation_id: int) -> None:
    db.execute(
        "UPDATE conversation_state SET sla_started_at = NULL, sla_stopped_at = NULL, sla_amber_done = 0, "
        "sla_red_done = 0 WHERE conversation_id = ?",
        (conversation_id,),
    )


def create_prebooking(db: sqlite3.Connection, conversation_id: int, data: dict, now: float, minutes: int) -> int:
    """Pre-reserva auxiliar del copiloto. Vive solo aquí: nunca se escribe en el PMS."""
    db.execute(
        "UPDATE prebookings SET status = 'superseded' WHERE conversation_id = ? AND status = 'active'",
        (conversation_id,),
    )
    cursor = db.execute(
        """INSERT INTO prebookings(conversation_id, checkin, checkout, adults, children, room_code, read_at,
               created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            conversation_id,
            data["checkin"],
            data["checkout"],
            data["adults"],
            data["children"],
            data.get("room_code"),
            data.get("read_at"),
            now,
            now + minutes * 60,
        ),
    )
    return cursor.lastrowid


def active_prebooking(db: sqlite3.Connection, conversation_id: int) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM prebookings WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conversation_id,)
    ).fetchone()


def set_prebooking_room(db: sqlite3.Connection, conversation_id: int, room_code: str | None) -> None:
    db.execute(
        "UPDATE prebookings SET room_code = ? WHERE conversation_id = ? AND status = 'active'",
        (room_code, conversation_id),
    )


def expire_prebookings(db: sqlite3.Connection, now: float) -> list[sqlite3.Row]:
    due = db.execute("SELECT * FROM prebookings WHERE status = 'active' AND expires_at <= ?", (now,)).fetchall()
    for row in due:
        db.execute("UPDATE prebookings SET status = 'expired' WHERE id = ?", (row["id"],))
    return due


def convert_prebooking(db: sqlite3.Connection, conversation_id: int) -> None:
    db.execute(
        "UPDATE prebookings SET status = 'converted' WHERE conversation_id = ? AND status IN ('active', 'expired')",
        (conversation_id,),
    )


MAX_NOTE = 500


def add_note(db: sqlite3.Connection, conversation_id: int, author: str, body: str, now: float) -> dict:
    """Nota del turno: queda pegada a la conversación y la lee quien llegue después."""
    text = " ".join(str(body or "").split())[:MAX_NOTE]
    if not text:
        raise ValueError("La nota está vacía")
    who = " ".join(str(author or "recepción").split())[:40] or "recepción"
    cursor = db.execute(
        "INSERT INTO staff_notes(conversation_id, author, body, created_at) VALUES (?, ?, ?, ?)",
        (conversation_id, who, text, now),
    )
    return {"id": cursor.lastrowid, "author": who, "body": text, "created_at": now}


def list_notes(db: sqlite3.Connection, conversation_id: int, limit: int = 20) -> list[dict]:
    rows = db.execute(
        "SELECT id, author, body, created_at FROM staff_notes WHERE conversation_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    return [
        {"id": row["id"], "author": row["author"], "body": row["body"], "created_at": row["created_at"]} for row in rows
    ]


def shift_summary(db: sqlite3.Connection, since: float, now: float) -> dict:
    """Lo que pasó en el turno: es el handover que la recepción hoy escribe a mano en un cuaderno."""

    def events(kind: str) -> int:
        row = db.execute(
            "SELECT COUNT(*) AS n FROM events WHERE kind = ? AND ts >= ? AND ts < ?", (kind, since, now)
        ).fetchone()
        return row["n"]

    received = db.execute(
        "SELECT COUNT(DISTINCT conversation_id) AS n FROM events WHERE kind = 'inbound' AND ts >= ? AND ts < ?",
        (since, now),
    ).fetchone()["n"]
    pending = db.execute(
        "SELECT COUNT(*) AS n FROM conversation_state WHERE sla_started_at IS NOT NULL AND sla_stopped_at IS NULL"
    ).fetchone()["n"]
    active = db.execute(
        "SELECT COUNT(*) AS n FROM prebookings WHERE status = 'active' AND expires_at > ?", (now,)
    ).fetchone()["n"]
    booked = db.execute(
        "SELECT COUNT(*) AS n FROM events WHERE kind = 'booking_confirmed' AND ts >= ? AND ts < ?", (since, now)
    ).fetchone()["n"]
    return {
        "since": since,
        "until": now,
        "received": received,
        "faq_answered": events("faq_answered"),
        "night_capture": events("night_capture"),
        "handoffs": events("handoff"),
        "prebookings_active": active,
        "prebookings_expired": events("prebooking_expired"),
        "bookings_confirmed": booked,
        "pending_human": pending,
    }


SAFE_PAYLOAD_KEYS = ("greeting", "in_shift", "complete", "inbound_ts", "faq_id", "status", "ok", "latency_ms", "reason")


def list_conversations(db: sqlite3.Connection, now: float, limit: int = 40, scope: str | None = None) -> list[dict]:
    """Cola de recepción: primero lo que corre riesgo de vencerse, después lo reciente.

    Sin esto, la persona de recepción solo puede mirar una conversación si ya sabe su id.
    `scope` separa la operación real del espacio de demostración: la demo nunca ve datos de huéspedes
    reales y el personal nunca recibe las conversaciones de prueba en su cola.
    """
    where, params = "", []
    if scope == DEMO_SOURCE:
        where, params = "WHERE source = ?", [DEMO_SOURCE]
    elif scope:
        where, params = "WHERE source <> ?", [DEMO_SOURCE]
    rows = db.execute(
        f"""SELECT conversation_id, step, contact_name, sla_started_at, sla_stopped_at, updated_at, source
           FROM conversation_state {where} ORDER BY updated_at DESC LIMIT ?""",
        (*params, limit),
    ).fetchall()
    queue = []
    for row in rows:
        prebooking = active_prebooking(db, row["conversation_id"])
        running = row["sla_started_at"] is not None and row["sla_stopped_at"] is None
        waiting = int(now - row["sla_started_at"]) if running else None
        queue.append(
            {
                "conversation_id": row["conversation_id"],
                "step": row["step"],
                "contact_name": row["contact_name"],
                "running": running,
                "waiting_s": waiting,
                "needs_human": row["step"] == "handed_off" and running,
                "prebooking": prebooking["status"] if prebooking is not None else None,
                "prebooking_expires_at": prebooking["expires_at"] if prebooking is not None else None,
                "updated_at": row["updated_at"],
                "source": row["source"],
            }
        )
    queue.sort(key=lambda item: (not item["running"], -(item["waiting_s"] or 0), -item["updated_at"]))
    return queue


def conversation_source(db: sqlite3.Connection, conversation_id: int) -> str | None:
    """De dónde viene una conversación; sin fila devuelve None (no existe)."""
    row = db.execute(
        "SELECT source FROM conversation_state WHERE conversation_id = ?", (conversation_id,)
    ).fetchone()
    return row["source"] if row is not None else None


def demo_conversation_id(session_id: str) -> int:
    """Id negativo estable por sesión: nunca choca con los ids positivos que asigna Chatwoot."""
    digest = hashlib.sha256(f"demo:{session_id}".encode()).digest()
    return -(int.from_bytes(digest[:6], "big") + 1)


def ensure_demo_conversation(db: sqlite3.Connection, session_id: str, now: float) -> int:
    """Una conversación de demo por sesión, marcada para que la operación real no la reciba."""
    row = db.execute(
        "SELECT conversation_id FROM demo_conversations WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is not None:
        return row["conversation_id"]
    conversation_id = demo_conversation_id(session_id)
    with transaction(db):
        db.execute(
            "INSERT OR IGNORE INTO demo_conversations(session_id, conversation_id, created_at) VALUES (?, ?, ?)",
            (session_id, conversation_id, now),
        )
        created = db.execute(
            "SELECT 1 FROM conversation_state WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
        if created is None:
            db.execute(
                """INSERT INTO conversation_state(conversation_id, step, data, contact_name, updated_at, source)
                   VALUES (?, 'ai', '{}', 'Huésped demo', ?, ?)""",
                (conversation_id, now, DEMO_SOURCE),
            )
    return conversation_id


def demo_conversation_for_session(db: sqlite3.Connection, session_id: str) -> int | None:
    row = db.execute(
        "SELECT conversation_id FROM demo_conversations WHERE session_id = ?", (session_id,)
    ).fetchone()
    return row["conversation_id"] if row is not None else None


def add_demo_message(db: sqlite3.Connection, conversation_id: int, role: str, body: str, now: float) -> dict:
    """Turno de la transcripción de demo (huésped, asistente o persona de recepción)."""
    with transaction(db):
        cursor = db.execute(
            "INSERT INTO demo_messages(conversation_id, role, body, created_at) VALUES (?, ?, ?, ?)",
            (conversation_id, role, body, now),
        )
        db.execute(
            "UPDATE conversation_state SET updated_at = ? WHERE conversation_id = ?", (now, conversation_id)
        )
    return {"id": cursor.lastrowid, "role": role, "body": body, "created_at": now}


def list_demo_messages(db: sqlite3.Connection, conversation_id: int, limit: int = 60) -> list[dict]:
    """Transcripción en orden de conversación; el tope se queda con lo último dicho."""
    rows = db.execute(
        """SELECT id, role, body, created_at FROM demo_messages
           WHERE conversation_id = ? ORDER BY id DESC LIMIT ?""",
        (conversation_id, limit),
    ).fetchall()
    return [dict(row) for row in reversed(rows)]


def reset_demo_conversation(db: sqlite3.Connection, session_id: str) -> None:
    """Reiniciar el historial de la demo borra solo su espacio aislado."""
    conversation_id = demo_conversation_for_session(db, session_id)
    if conversation_id is None:
        return
    with transaction(db):
        db.execute("DELETE FROM demo_messages WHERE conversation_id = ?", (conversation_id,))
        db.execute("DELETE FROM staff_notes WHERE conversation_id = ?", (conversation_id,))
        db.execute("DELETE FROM demo_conversations WHERE session_id = ?", (session_id,))
        db.execute("DELETE FROM conversation_state WHERE conversation_id = ?", (conversation_id,))


def anonymous_id(conversation_id: int, salt: str) -> int:
    """Seudónimo negativo con sal secreta: sigue sirviendo para contar conversaciones, pero no se puede
    enlazar con el id de Chatwoot sin conocer la sal."""
    digest = hmac.new(salt.encode(), str(conversation_id).encode(), hashlib.sha256).digest()
    return -(int.from_bytes(digest[:7], "big") + 1)


def purge_personal_data(db: sqlite3.Connection, now: float, retention_days: int, salt: str = "") -> dict:
    """Retención (Ley 21.719): borra datos personales vencidos y deja los eventos sin texto ni identificadores
    enlazables (solo contadores con seudónimo)."""
    cutoff = now - retention_days * 86400
    cursor_state = db.execute("DELETE FROM conversation_state WHERE updated_at < ?", (cutoff,))
    cursor_pre = db.execute("DELETE FROM prebookings WHERE created_at < ?", (cutoff,))
    cursor_msgs = db.execute("DELETE FROM processed_messages WHERE ts < ?", (cutoff,))
    cursor_ai = db.execute("DELETE FROM ai_sessions WHERE updated_at < ?", (cutoff,))
    cursor_notes = db.execute("DELETE FROM staff_notes WHERE created_at < ?", (cutoff,))
    anonymized = 0
    for row in db.execute("SELECT id, payload FROM events WHERE ts < ? AND conversation_id > 0", (cutoff,)).fetchall():
        payload = json.loads(row["payload"])
        safe = {key: payload[key] for key in SAFE_PAYLOAD_KEYS if key in payload}
        db.execute("UPDATE events SET payload = ? WHERE id = ?", (json.dumps(safe), row["id"]))
        anonymized += 1
    for row in db.execute(
        "SELECT DISTINCT conversation_id FROM events WHERE ts < ? AND conversation_id > 0", (cutoff,)
    ).fetchall():
        db.execute(
            "UPDATE events SET conversation_id = ? WHERE conversation_id = ? AND ts < ?",
            (anonymous_id(row["conversation_id"], salt), row["conversation_id"], cutoff),
        )
    return {
        "conversation_state": cursor_state.rowcount,
        "prebookings": cursor_pre.rowcount,
        "events_anonymized": anonymized,
        "processed_messages": cursor_msgs.rowcount,
        "ai_sessions": cursor_ai.rowcount,
        "staff_notes": cursor_notes.rowcount,
    }
