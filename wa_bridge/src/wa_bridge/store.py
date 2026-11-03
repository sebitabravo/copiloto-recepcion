"""Estado mínimo del puente: qué chat de WhatsApp corresponde a qué conversación de Chatwoot."""

from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (chat_id TEXT PRIMARY KEY, source_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id INTEGER PRIMARY KEY, chat_id TEXT NOT NULL, created_at REAL NOT NULL, last_seen REAL);
CREATE INDEX IF NOT EXISTS conversations_chat ON conversations (chat_id, created_at);
CREATE TABLE IF NOT EXISTS processed (key TEXT PRIMARY KEY, at REAL NOT NULL);
"""


def connect(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    columns = {row["name"] for row in db.execute("PRAGMA table_info(conversations)")}
    if "last_seen" not in columns:
        db.execute("ALTER TABLE conversations ADD COLUMN last_seen REAL")
        db.commit()
    return db


def is_processed(db: sqlite3.Connection, key: str) -> bool:
    return db.execute("SELECT 1 FROM processed WHERE key = ?", (key,)).fetchone() is not None


def mark_processed(db: sqlite3.Connection, key: str, now: float) -> bool:
    """True la primera vez que se registra la clave; False si ya estaba. Se llama DESPUÉS de entregar."""
    cursor = db.execute("INSERT OR IGNORE INTO processed (key, at) VALUES (?, ?)", (key, now))
    db.commit()
    return cursor.rowcount == 1


def purge_processed(db: sqlite3.Connection, older_than: float) -> int:
    """Borra claves de deduplicación antiguas: son técnicas y no deben crecer sin límite."""
    cursor = db.execute("DELETE FROM processed WHERE at < ?", (older_than,))
    db.commit()
    return cursor.rowcount


def purge_mappings(db: sqlite3.Connection, older_than: float) -> None:
    """Borra conversaciones sin actividad reciente y los contactos sin conversación (el chat incluye el teléfono)."""
    db.execute("DELETE FROM conversations WHERE COALESCE(last_seen, created_at) < ?", (older_than,))
    db.execute("DELETE FROM contacts WHERE chat_id NOT IN (SELECT chat_id FROM conversations)")
    db.commit()


def contact_source(db: sqlite3.Connection, chat_id: str) -> str | None:
    row = db.execute("SELECT source_id FROM contacts WHERE chat_id = ?", (chat_id,)).fetchone()
    return row["source_id"] if row else None


def save_contact(db: sqlite3.Connection, chat_id: str, source_id: str) -> None:
    db.execute("INSERT OR REPLACE INTO contacts (chat_id, source_id) VALUES (?, ?)", (chat_id, source_id))
    db.commit()


def current_conversation(db: sqlite3.Connection, chat_id: str) -> int | None:
    row = db.execute("SELECT conversation_id FROM conversations WHERE chat_id = ? "
                     "ORDER BY created_at DESC, rowid DESC LIMIT 1", (chat_id,)).fetchone()
    return row["conversation_id"] if row else None


def save_conversation(db: sqlite3.Connection, chat_id: str, conversation_id: int, now: float) -> None:
    db.execute("INSERT OR REPLACE INTO conversations (conversation_id, chat_id, created_at, last_seen) "
               "VALUES (?, ?, ?, ?)", (conversation_id, chat_id, now, now))
    db.commit()


def touch_conversation(db: sqlite3.Connection, conversation_id: int, now: float) -> None:
    """Registra actividad: el mapeo vive mientras la conversación se use, no desde que se creó."""
    db.execute("UPDATE conversations SET last_seen = ? WHERE conversation_id = ?", (now, conversation_id))
    db.commit()


def chat_for_conversation(db: sqlite3.Connection, conversation_id: int) -> str | None:
    row = db.execute("SELECT chat_id FROM conversations WHERE conversation_id = ?",
                     (conversation_id,)).fetchone()
    return row["chat_id"] if row else None
