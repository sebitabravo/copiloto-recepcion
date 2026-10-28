"""Sesiones del asistente con IA: historial acotado y estado de las herramientas (lecturas del PMS, reservas)."""

import json
import re
import sqlite3
from dataclasses import dataclass, field

SESSION_ID = re.compile(r"^[A-Za-z0-9:_-]{8,80}$")
MAX_TEXT = 1200


@dataclass
class AiSession:
    session_id: str
    history: list[dict] = field(default_factory=list)
    state: dict = field(default_factory=dict)
    msg_count: int = 0
    created_at: float = 0.0

    def add(self, role: str, text: str, limit: int) -> None:
        self.history.append({"role": role, "content": text[:MAX_TEXT]})
        del self.history[:-limit]


def load(db: sqlite3.Connection, session_id: str, now: float) -> AiSession:
    row = db.execute("SELECT * FROM ai_sessions WHERE session_id = ?", (session_id,)).fetchone()
    if row is None:
        return AiSession(session_id, created_at=now)
    return AiSession(session_id, json.loads(row["history"]), json.loads(row["state"]), row["msg_count"],
                     row["created_at"])


def save(db: sqlite3.Connection, session: AiSession, now: float) -> None:
    db.execute(
        """INSERT INTO ai_sessions(session_id, history, state, msg_count, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(session_id) DO UPDATE SET history=excluded.history, state=excluded.state,
               msg_count=excluded.msg_count, updated_at=excluded.updated_at""",
        (session.session_id, json.dumps(session.history, ensure_ascii=False),
         json.dumps(session.state, ensure_ascii=False), session.msg_count, session.created_at or now, now))


def delete(db: sqlite3.Connection, session_id: str) -> None:
    db.execute("DELETE FROM ai_sessions WHERE session_id = ?", (session_id,))


def purge_expired(db: sqlite3.Connection, now: float, ttl_s: int, prefix: str) -> int:
    """Borra sesiones con el prefijo dado (p. ej. las de la demo web) inactivas por más de `ttl_s`."""
    cursor = db.execute("DELETE FROM ai_sessions WHERE session_id LIKE ? AND updated_at < ?",
                        (prefix + "%", now - ttl_s))
    return cursor.rowcount
