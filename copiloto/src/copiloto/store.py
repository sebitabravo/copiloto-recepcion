"""Persistencia del estado conversacional, las pre-reservas auxiliares y la retención de datos."""

import json
import sqlite3
from dataclasses import dataclass, field


@dataclass
class ConversationState:
    conversation_id: int
    step: str = "start"
    data: dict = field(default_factory=dict)
    contact_name: str | None = None
    contact_ref: str | None = None
    sla_started_at: float | None = None
    sla_stopped_at: float | None = None
    sla_amber_done: bool = False
    sla_red_done: bool = False


def get_state(db: sqlite3.Connection, conversation_id: int) -> ConversationState:
    row = db.execute("SELECT * FROM conversation_state WHERE conversation_id = ?", (conversation_id,)).fetchone()
    if row is None:
        return ConversationState(conversation_id)
    return ConversationState(
        conversation_id, row["step"], json.loads(row["data"]), row["contact_name"], row["contact_ref"],
        row["sla_started_at"], row["sla_stopped_at"], bool(row["sla_amber_done"]), bool(row["sla_red_done"]),
    )


def save_state(db: sqlite3.Connection, state: ConversationState, now: float) -> None:
    db.execute(
        """INSERT INTO conversation_state(conversation_id, step, data, contact_name, contact_ref,
               sla_started_at, sla_stopped_at, sla_amber_done, sla_red_done, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(conversation_id) DO UPDATE SET step=excluded.step, data=excluded.data,
               contact_name=excluded.contact_name, contact_ref=excluded.contact_ref,
               sla_started_at=excluded.sla_started_at, sla_stopped_at=excluded.sla_stopped_at,
               sla_amber_done=excluded.sla_amber_done, sla_red_done=excluded.sla_red_done,
               updated_at=excluded.updated_at""",
        (state.conversation_id, state.step, json.dumps(state.data, ensure_ascii=False), state.contact_name,
         state.contact_ref, state.sla_started_at, state.sla_stopped_at, int(state.sla_amber_done),
         int(state.sla_red_done), now),
    )


def create_prebooking(db: sqlite3.Connection, conversation_id: int, data: dict, now: float,
                      minutes: int) -> int:
    """Pre-reserva auxiliar del copiloto. Vive solo aquí: nunca se escribe en el PMS."""
    db.execute("UPDATE prebookings SET status = 'superseded' WHERE conversation_id = ? AND status = 'active'",
               (conversation_id,))
    cursor = db.execute(
        """INSERT INTO prebookings(conversation_id, checkin, checkout, adults, children, room_code, read_at,
               created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (conversation_id, data["checkin"], data["checkout"], data["adults"], data["children"],
         data.get("room_code"), data.get("read_at"), now, now + minutes * 60),
    )
    return cursor.lastrowid


def active_prebooking(db: sqlite3.Connection, conversation_id: int) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM prebookings WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conversation_id,)
    ).fetchone()


def set_prebooking_room(db: sqlite3.Connection, conversation_id: int, room_code: str | None) -> None:
    db.execute("UPDATE prebookings SET room_code = ? WHERE conversation_id = ? AND status = 'active'",
               (room_code, conversation_id))


def expire_prebookings(db: sqlite3.Connection, now: float) -> list[sqlite3.Row]:
    due = db.execute("SELECT * FROM prebookings WHERE status = 'active' AND expires_at <= ?", (now,)).fetchall()
    for row in due:
        db.execute("UPDATE prebookings SET status = 'expired' WHERE id = ?", (row["id"],))
    return due


def convert_prebooking(db: sqlite3.Connection, conversation_id: int) -> None:
    db.execute("UPDATE prebookings SET status = 'converted' WHERE conversation_id = ? AND status IN "
               "('active', 'expired')", (conversation_id,))


def purge_personal_data(db: sqlite3.Connection, now: float, retention_days: int) -> dict:
    """Retención (Ley 21.719): borra datos personales vencidos y conserva los eventos agregados sin texto."""
    cutoff = now - retention_days * 86400
    cursor_state = db.execute("DELETE FROM conversation_state WHERE updated_at < ?", (cutoff,))
    cursor_pre = db.execute("DELETE FROM prebookings WHERE created_at < ?", (cutoff,))
    cursor_events = db.execute(
        """UPDATE events SET payload = json_object('greeting', json_extract(payload, '$.greeting'))
           WHERE ts < ? AND kind = 'inbound' AND json_extract(payload, '$.text') IS NOT NULL""", (cutoff,))
    cursor_msgs = db.execute("DELETE FROM processed_messages WHERE ts < ?", (cutoff,))
    return {"conversation_state": cursor_state.rowcount, "prebookings": cursor_pre.rowcount,
            "inbound_payloads": cursor_events.rowcount, "processed_messages": cursor_msgs.rowcount}
