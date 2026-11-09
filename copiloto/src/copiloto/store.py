"""Persistencia del estado conversacional, las pre-reservas auxiliares y la retención de datos."""

import hashlib
import hmac
import json
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date

from copiloto.events import record_event

# Origen de una conversación: la operación real (Chatwoot) o el espacio aislado de la demostración.
DEMO_SOURCE = "demo"
OPERATIONAL_SOURCE = "chatwoot"


@contextmanager
def transaction(db: sqlite3.Connection):
    """Agrupa escrituras en una transacción: o quedan todas o ninguna si el proceso falla a mitad.

    Anidada (dentro de otra) usa un SAVEPOINT: la transacción de afuera decide el COMMIT final. Nunca debe
    abarcar un `await`: la conexión es compartida y otra corrutina escribiría dentro de esta transacción.
    """
    if db.in_transaction:
        db.execute("SAVEPOINT nested")
        try:
            yield
        except BaseException:
            db.execute("ROLLBACK TO nested")
            db.execute("RELEASE nested")
            raise
        db.execute("RELEASE nested")
        return
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        db.execute("ROLLBACK")
        raise
    db.execute("COMMIT")


# ---------- llaves de idempotencia de las acciones ----------


class DuplicateAction(Exception):
    """La acción con esta llave ya terminó: el reintento devuelve el estado actual sin repetir nada."""


class ActionConflict(Exception):
    """La llave ya se usó con otro contenido: se rechaza en vez de descartar el mensaje nuevo en silencio."""


def fingerprint(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def get_action(db: sqlite3.Connection, scope: str, client_id: str) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM action_keys WHERE scope = ? AND client_id = ?", (scope, client_id)
    ).fetchone()


def check_action(db: sqlite3.Connection, scope: str, client_id: str, digest: str) -> sqlite3.Row | None:
    """La acción ya registrada con esta llave (o None). Con otro contenido levanta ActionConflict."""
    row = get_action(db, scope, client_id)
    if row is not None and row["fingerprint"] != digest:
        raise ActionConflict("Esa llave ya se usó con otro mensaje")
    return row


def claim_action(
    db: sqlite3.Connection, scope: str, client_id: str, digest: str, now: float, state: str,
    message_id: int | None = None,
) -> None:
    """Registra la llave DENTRO de la transacción que guarda el efecto: o quedan ambos o ninguno."""
    existing = check_action(db, scope, client_id, digest)
    if existing is not None:
        raise DuplicateAction(existing["state"])
    db.execute(
        """INSERT INTO action_keys(scope, client_id, fingerprint, state, message_id, created_at, completed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (scope, client_id, digest, state, message_id, now, now if state == "done" else None),
    )


def complete_action(db: sqlite3.Connection, scope: str, client_id: str, now: float) -> None:
    db.execute(
        "UPDATE action_keys SET state = 'done', completed_at = ? WHERE scope = ? AND client_id = ?",
        (now, scope, client_id),
    )


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


def events_scope(source: str) -> tuple[str, list]:
    """Filtro SQL de eventos por origen. Los históricos sin `source` siguen la regla de metrics.HISTORICAL_RULE."""
    legacy = "conversation_id > 0" if source == OPERATIONAL_SOURCE else "conversation_id = 0"
    return f"(source = ? OR (source IS NULL AND {legacy}))", [source]


RUN_CONVERSATIONS = "conversation_id IN (SELECT conversation_id FROM demo_conversations WHERE run_id = ?)"


def shift_summary(
    db: sqlite3.Connection, since: float, now: float, source: str = OPERATIONAL_SOURCE, run_id: str | None = None
) -> dict:
    """Lo que pasó en el turno: es el handover que la recepción hoy escribe a mano en un cuaderno.

    Solo cuenta el mundo pedido (`source`): la demo nunca aparece en el resumen de la operación, ni al revés; y
    en la demo, solo la corrida de la sesión (sin corrida, nada).
    """
    scope, scope_params = events_scope(source)
    owned, owned_params = "1 = 1", []
    if source == DEMO_SOURCE:
        owned, owned_params = RUN_CONVERSATIONS, [run_id]
    scope, scope_params = f"{scope} AND {owned}", [*scope_params, *owned_params]

    def events(kind: str) -> int:
        row = db.execute(
            f"SELECT COUNT(*) AS n FROM events WHERE kind = ? AND ts >= ? AND ts < ? AND {scope}",
            (kind, since, now, *scope_params),
        ).fetchone()
        return row["n"]

    received = db.execute(
        f"SELECT COUNT(DISTINCT conversation_id) AS n FROM events WHERE kind = 'inbound' AND ts >= ? AND ts < ? "
        f"AND {scope}",
        (since, now, *scope_params),
    ).fetchone()["n"]
    pending = db.execute(
        "SELECT COUNT(*) AS n FROM conversation_state WHERE sla_started_at IS NOT NULL AND sla_stopped_at IS NULL "
        f"AND source = ? AND {owned}",
        (source, *owned_params),
    ).fetchone()["n"]
    active = db.execute(
        "SELECT COUNT(*) AS n FROM prebookings WHERE status = 'active' AND expires_at > ? AND conversation_id IN "
        f"(SELECT conversation_id FROM conversation_state WHERE source = ?) AND {owned}",
        (now, source, *owned_params),
    ).fetchone()["n"]
    return {
        "since": since,
        "until": now,
        "scope": "demo" if source == DEMO_SOURCE else "operation",
        "received": received,
        "faq_answered": events("faq_answered"),
        "night_capture": events("night_capture"),
        "handoffs": events("handoff"),
        "prebookings_active": active,
        "prebookings_expired": events("prebooking_expired"),
        "bookings_confirmed": events("booking_confirmed"),
        "pending_human": pending,
    }


SAFE_PAYLOAD_KEYS = (
    "greeting", "in_shift", "handoff_in_shift", "complete", "inbound_ts", "faq_id", "status", "ok", "latency_ms",
    "reason",
)


def list_conversations(
    db: sqlite3.Connection, now: float, limit: int = 40, scope: str | None = None, run_id: str | None = None
) -> list[dict]:
    """Cola de recepción: primero lo que corre riesgo de vencerse, después lo reciente.

    Sin esto, la persona de recepción solo puede mirar una conversación si ya sabe su id.
    `scope` separa la operación real del espacio de demostración: la demo nunca ve datos de huéspedes
    reales y el personal nunca recibe las conversaciones de prueba en su cola.
    """
    where, params = "", []
    if scope == DEMO_SOURCE:
        # Solo las conversaciones de la corrida de la sesión; sin corrida, ninguna.
        where = ("WHERE source = ? AND conversation_id IN "
                 "(SELECT conversation_id FROM demo_conversations WHERE run_id = ?)")
        params = [DEMO_SOURCE, run_id]
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


class RunMismatch(Exception):
    """La sesión del huésped ya pertenece a otra corrida: no se mezcla con esta."""


def create_demo_run(db: sqlite3.Connection, now: float) -> str:
    """Corrida nueva emitida por el servidor: id aleatorio, imposible de adivinar o de elegir desde el cliente."""
    run_id = secrets.token_urlsafe(12)
    db.execute("INSERT INTO demo_runs(run_id, created_at, last_seen) VALUES (?, ?, ?)", (run_id, now, now))
    return run_id


def demo_run_active(db: sqlite3.Connection, run_id: str, now: float, ttl_s: int) -> bool:
    """True si la corrida existe y no venció; cada uso la mantiene viva."""
    cursor = db.execute(
        "UPDATE demo_runs SET last_seen = ? WHERE run_id = ? AND last_seen >= ?", (now, run_id, now - ttl_s)
    )
    return cursor.rowcount == 1


def demo_session_run(db: sqlite3.Connection, session_id: str) -> str | None:
    row = db.execute("SELECT run_id FROM demo_conversations WHERE session_id = ?", (session_id,)).fetchone()
    return row["run_id"] if row is not None else None


def ensure_demo_conversation(db: sqlite3.Connection, session_id: str, now: float, run_id: str | None = None) -> int:
    """Una conversación de demo por sesión, marcada para que la operación real no la reciba.

    Con `run_id`, la sesión queda unida a esa corrida; si ya era de otra, `RunMismatch` (nunca se cambia de
    corrida: recepción de la otra corrida dejaría de ver su caso, o vería uno ajeno).
    """
    row = db.execute(
        "SELECT conversation_id, run_id FROM demo_conversations WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is not None:
        if run_id is not None and row["run_id"] not in (None, run_id):
            raise RunMismatch(session_id)
        if run_id is not None and row["run_id"] is None:
            db.execute("UPDATE demo_conversations SET run_id = ? WHERE session_id = ?", (run_id, session_id))
        return row["conversation_id"]
    conversation_id = demo_conversation_id(session_id)
    with transaction(db):
        db.execute(
            "INSERT OR IGNORE INTO demo_conversations(session_id, conversation_id, created_at, run_id) "
            "VALUES (?, ?, ?, ?)",
            (session_id, conversation_id, now, run_id),
        )
        created = db.execute(
            "SELECT 1 FROM conversation_state WHERE conversation_id = ?", (conversation_id,)
        ).fetchone()
        if created is None:
            db.execute(
                """INSERT INTO conversation_state(conversation_id, step, data, contact_name, updated_at, source)
                   VALUES (?, 'start', '{}', 'Huésped demo', ?, ?)""",
                (conversation_id, now, DEMO_SOURCE),
            )
    return conversation_id


def demo_conversation_for_session(db: sqlite3.Connection, session_id: str) -> int | None:
    row = db.execute(
        "SELECT conversation_id FROM demo_conversations WHERE session_id = ?", (session_id,)
    ).fetchone()
    return row["conversation_id"] if row is not None else None


def add_demo_message(
    db: sqlite3.Connection,
    conversation_id: int,
    role: str,
    body: str,
    now: float,
    options: list[str] | None = None,
    author: str | None = None,
    kind: str | None = None,
    request_id: int | None = None,
) -> dict:
    """Turno de la transcripción de demo: huésped, asistente, persona de recepción o nota interna.

    `note` es la pre-información privada del traspaso: solo la ve recepción, nunca el huésped.
    """
    with transaction(db):
        message = insert_demo_message(db, conversation_id, role, body, now, options, author, kind, request_id)
    return message


def insert_demo_message(db, conversation_id, role, body, now, options=None, author=None, kind=None, request_id=None):
    """Inserción sin transacción propia: para escrituras que agrupan varias filas en una sola transacción."""
    cursor = db.execute(
        """INSERT INTO demo_messages(conversation_id, role, body, created_at, options, author, kind, request_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            conversation_id,
            role,
            body,
            now,
            json.dumps(options, ensure_ascii=False) if options else None,
            author,
            kind,
            request_id,
        ),
    )
    db.execute("UPDATE conversation_state SET updated_at = ? WHERE conversation_id = ?", (now, conversation_id))
    return _message_dict(
        {"id": cursor.lastrowid, "role": role, "body": body, "created_at": now, "options": options,
         "author": author, "kind": kind}
    )


def _message_dict(row) -> dict:
    options = row["options"]
    if isinstance(options, str):
        options = json.loads(options)
    return {
        "id": row["id"],
        "role": row["role"],
        "body": row["body"],
        "created_at": row["created_at"],
        "options": options or None,
        "author": row["author"],
        "kind": row["kind"],
    }


def list_demo_messages(
    db: sqlite3.Connection, conversation_id: int, limit: int = 80, guest_view: bool = False, after_id: int = 0
) -> list[dict]:
    """Transcripción en orden de conversación; el tope se queda con lo último dicho.

    `guest_view` deja fuera las notas internas: el huésped nunca lee la pre-información de recepción.
    """
    hidden = "AND role <> 'note'" if guest_view else ""
    rows = db.execute(
        f"""SELECT id, role, body, created_at, options, author, kind FROM demo_messages
           WHERE conversation_id = ? AND id > ? {hidden} ORDER BY id DESC LIMIT ?""",
        (conversation_id, after_id, limit),
    ).fetchall()
    return [_message_dict(row) for row in reversed(rows)]


def reset_demo_conversation(db: sqlite3.Connection, session_id: str) -> None:
    """Reiniciar el historial de la demo borra solo su espacio aislado."""
    conversation_id = demo_conversation_for_session(db, session_id)
    if conversation_id is None:
        return
    with transaction(db):
        db.execute("DELETE FROM demo_messages WHERE conversation_id = ?", (conversation_id,))
        db.execute("DELETE FROM staff_notes WHERE conversation_id = ?", (conversation_id,))
        db.execute("DELETE FROM prebookings WHERE conversation_id = ?", (conversation_id,))
        db.execute(
            "DELETE FROM action_keys WHERE scope = ? OR scope IN "
            "(SELECT 'staff:' || id FROM requests WHERE conversation_id = ?)",
            (f"guest:{session_id}", conversation_id),
        )
        db.execute("DELETE FROM requests WHERE conversation_id = ?", (conversation_id,))
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
    db.execute("DELETE FROM action_keys WHERE created_at < ?", (cutoff,))
    cursor_ai = db.execute("DELETE FROM ai_sessions WHERE updated_at < ?", (cutoff,))
    cursor_notes = db.execute("DELETE FROM staff_notes WHERE created_at < ?", (cutoff,))
    cursor_requests = db.execute("DELETE FROM requests WHERE updated_at < ?", (cutoff,))
    anonymized = 0
    for row in db.execute("SELECT id, payload FROM events WHERE ts < ? AND conversation_id > 0", (cutoff,)).fetchall():
        payload = json.loads(row["payload"])
        safe = {key: payload[key] for key in SAFE_PAYLOAD_KEYS if key in payload}
        # El número interno de solicitud (entero) mantiene la medición por solicitud tras la retención; el
        # request_id de las trazas de IA es texto con el id de la conversación y no se conserva.
        if isinstance(payload.get("request_id"), int):
            safe["request_id"] = payload["request_id"]
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
        "requests": cursor_requests.rowcount,
    }


def purge_demo(db: sqlite3.Connection, cutoff: float) -> int:
    """Borra las conversaciones de demo sin actividad desde `cutoff`: transcripción, solicitudes y estado.

    La demo no es operación real: sus datos no esperan la retención de 90 días. Los eventos quedan
    (no guardan texto) para que la medición siga siendo reproducible.
    """
    rows = db.execute(
        """SELECT d.session_id, d.conversation_id FROM demo_conversations d
           LEFT JOIN conversation_state s ON s.conversation_id = d.conversation_id
           WHERE COALESCE(s.updated_at, d.created_at) < ?""",
        (cutoff,),
    ).fetchall()
    for row in rows:
        reset_demo_conversation(db, row["session_id"])
    db.execute("DELETE FROM demo_runs WHERE last_seen < ?", (cutoff,))
    return len(rows)


# ---------- solicitudes a recepción ----------

ATTENTION_LABELS = {
    "pendiente": "Pendiente de recepción",
    "en_atencion": "En atención",
    "respondida": "Respondida",
    "cerrada": "Cerrada",
}
# El estado de la RESERVA es otro concepto: responder una consulta no confirma nada.
RESERVATION_LABELS = {
    "pendiente_confirmacion": "Pendiente de confirmación",
    "confirmada": "Confirmada por recepción en el PMS",
}
OPEN_STATUSES = ("pendiente", "en_atencion", "respondida")
REASON_LABELS = {
    "commercial": "Consulta de fechas",
    "human_requested": "Pidió hablar con recepción",
    "pms_down": "Cupos sin verificar (PMS sin respuesta)",
    "no_entendi_tres_veces": "El asistente no entendió",
    "error": "Falla técnica del asistente",
    "ai_handoff": "Derivada por el asistente con IA",
}
CHANNEL_LABELS = {"demo": "WhatsApp simulado", "Channel::WebWidget": "Chat web", "Channel::Whatsapp": "WhatsApp"}


class RequestConflict(Exception):
    """La acción no aplica al estado actual de la solicitud (p. ej. otra persona ya la tomó)."""


def create_request(
    db: sqlite3.Connection,
    conversation_id: int,
    *,
    prefix: str,
    source: str,
    channel: str,
    reason: str,
    in_shift: bool,
    commercial_at: float,
    now: float,
    data: dict,
    intake_in_shift: bool | None = None,
) -> dict:
    """Solicitud nueva vinculada al hilo. Corre dentro de la transacción del traspaso (sin una propia).

    `intake_in_shift` es el turno cuando ENTRÓ la consulta comercial (decide si cuenta para la meta); `in_shift`
    es el turno al derivar (qué se le dice al huésped). Sin el primero, valen lo mismo.
    Una solicitud abierta anterior del mismo hilo queda cerrada: el huésped volvió con otra consulta.
    """
    db.execute(
        f"UPDATE requests SET status = 'cerrada', closed_at = ?, updated_at = ? "
        f"WHERE conversation_id = ? AND status IN ({','.join('?' for _ in OPEN_STATUSES)})",
        (now, now, conversation_id, *OPEN_STATUSES),
    )
    # Una solicitud de la demo hereda la corrida de la sesión del huésped: solo esa recepción la ve.
    run = db.execute(
        "SELECT run_id FROM demo_conversations WHERE conversation_id = ?", (conversation_id,)
    ).fetchone() if source == DEMO_SOURCE else None
    cursor = db.execute(
        """INSERT INTO requests(code, conversation_id, source, channel, reason, in_shift, intake_in_shift,
               commercial_at, created_at, checkin, checkout, adults, children, room_code, updated_at, run_id)
           VALUES ('', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            conversation_id,
            source,
            channel,
            reason,
            int(in_shift),
            int(in_shift if intake_in_shift is None else intake_in_shift),
            commercial_at,
            now,
            data.get("checkin"),
            data.get("checkout"),
            data.get("adults"),
            data.get("children"),
            data.get("room_code"),
            now,
            run["run_id"] if run is not None else None,
        ),
    )
    request_id = cursor.lastrowid
    code = f"{prefix}-{request_id:03d}"
    db.execute("UPDATE requests SET code = ? WHERE id = ?", (code, request_id))
    return get_request_row(db, request_id)


def get_request_row(db: sqlite3.Connection, request_id: int) -> sqlite3.Row | None:
    return db.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()


def open_request(db: sqlite3.Connection, conversation_id: int) -> sqlite3.Row | None:
    """Solicitud que recepción tiene abierta en este hilo: mientras exista, el bot no contesta."""
    return db.execute(
        f"SELECT * FROM requests WHERE conversation_id = ? AND status IN ({','.join('?' for _ in OPEN_STATUSES)}) "
        "ORDER BY id DESC LIMIT 1",
        (conversation_id, *OPEN_STATUSES),
    ).fetchone()


def latest_request(db: sqlite3.Connection, conversation_id: int) -> sqlite3.Row | None:
    return db.execute(
        "SELECT * FROM requests WHERE conversation_id = ? ORDER BY id DESC LIMIT 1", (conversation_id,)
    ).fetchone()


def intake_in_shift(row) -> bool:
    """Turno al ingreso. Solicitudes anteriores a la columna (NULL) usan el turno al derivar: dato histórico."""
    value = row["intake_in_shift"]
    return bool(row["in_shift"] if value is None else value)


def measurement(row, now: float, target_s: int) -> dict:
    """Primera respuesta humana pertinente contra la meta, desde que ENTRÓ la consulta comercial.

    Tomar la solicitud no reinicia ni detiene el reloj. Una consulta que entró fuera de turno no cuenta para la
    meta aunque se derive ya en turno; una que entró en turno sí cuenta aunque se derive después del cierre.
    """
    if not intake_in_shift(row):
        return {"state": "fuera_de_turno", "elapsed_s": None, "target_s": target_s,
                "label": "Fuera de turno: no cuenta para la meta de primera respuesta"}
    if row["first_answer_at"] is not None:
        elapsed = int(row["first_answer_at"] - row["commercial_at"])
        met = elapsed < target_s
        return {"state": "cumplida" if met else "vencida", "elapsed_s": elapsed, "target_s": target_s,
                "label": f"Primera respuesta en {_clock(elapsed)} ({'dentro' if met else 'fuera'} de la meta)"}
    elapsed = max(int(now - row["commercial_at"]), 0)
    if elapsed >= target_s:
        return {"state": "vencida", "elapsed_s": elapsed, "target_s": target_s,
                "label": f"Sin respuesta pertinente tras {_clock(elapsed)}: meta vencida"}
    return {"state": "en_curso", "elapsed_s": elapsed, "target_s": target_s,
            "label": f"Esperando primera respuesta · {_clock(elapsed)}"}


def _clock(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def request_dict(row, now: float, target_s: int) -> dict:
    nights = None
    if row["checkin"] and row["checkout"]:
        nights = (date.fromisoformat(row["checkout"]) - date.fromisoformat(row["checkin"])).days
    return {
        "id": row["id"],
        "code": row["code"],
        "conversation_id": row["conversation_id"],
        "channel": row["channel"],
        "channel_label": CHANNEL_LABELS.get(row["channel"], row["channel"].removeprefix("Channel::")),
        "reason": row["reason"],
        "reason_label": REASON_LABELS.get(row["reason"], row["reason"]),
        "in_shift": bool(row["in_shift"]),
        "intake_in_shift": intake_in_shift(row),
        "commercial_at": row["commercial_at"],
        "created_at": row["created_at"],
        "checkin": row["checkin"],
        "checkout": row["checkout"],
        "nights": nights,
        "adults": row["adults"],
        "children": row["children"],
        "room_code": row["room_code"],
        "status": row["status"],
        "status_label": ATTENTION_LABELS.get(row["status"], row["status"]),
        "reservation_status": row["reservation_status"],
        "reservation_label": RESERVATION_LABELS.get(row["reservation_status"], row["reservation_status"]),
        "assignee": row["assignee"],
        "taken_at": row["taken_at"],
        "first_answer_at": row["first_answer_at"],
        "last_guest_at": row["last_guest_at"],
        "breached_at": row["breached_at"],
        "closed_at": row["closed_at"],
        "updated_at": row["updated_at"],
        "measurement": measurement(row, now, target_s),
    }


def list_requests(
    db: sqlite3.Connection, now: float, target_s: int, scope: str, limit: int = 50, run_id: str | None = None,
    operator: str | None = None,
) -> list[dict]:
    """Bandeja ordenada EN SQL antes del límite: una pendiente antigua nunca queda fuera por cerradas nuevas.

    1) pendientes y 2) en atención: la que más espera primero (desde que entró la consulta comercial);
    3) respondidas (abiertas, esperan al huésped); 4) cerradas, la más reciente primero. Empate: el id menor
    (la que llegó antes), así el orden no cambia entre lecturas.
    """
    if scope == DEMO_SOURCE:
        # La demo ve solo su corrida; una sesión sin corrida no ve ningún caso.
        if run_id is None:
            return []
        where, params = "source = ? AND run_id = ?", [DEMO_SOURCE, run_id]
    else:
        where, params = "source <> ?", [DEMO_SOURCE]
    rows = db.execute(
        f"""SELECT r.*, (SELECT body FROM demo_messages m WHERE m.conversation_id = r.conversation_id
                         AND m.role <> 'note' ORDER BY m.id DESC LIMIT 1) AS preview
            FROM requests r WHERE {where}
            ORDER BY CASE r.status WHEN 'pendiente' THEN 0 WHEN 'en_atencion' THEN 1
                                   WHEN 'respondida' THEN 2 ELSE 3 END,
                     CASE WHEN r.status = 'cerrada' THEN -COALESCE(r.closed_at, r.updated_at)
                          ELSE r.commercial_at END,
                     CASE WHEN r.status = 'cerrada' THEN -r.id ELSE r.id END
            LIMIT ?""",
        (*params, limit),
    ).fetchall()
    items = []
    for row in rows:
        item = request_dict(row, now, target_s)
        item["preview"] = row["preview"]
        item["mine"] = operator is not None and owned_by(row, None, operator)
        items.append(item)
    return items


def owned_by(row, name: str | None, operator: str | None) -> bool:
    """¿La solicitud es de esta persona? Por id de operador (estable); el nombre es solo una etiqueta.

    Dos «Sofía» son dos operadores distintos. Las filas sin id (anteriores) se comparan por nombre.
    """
    if row["assignee_id"]:
        return operator is not None and row["assignee_id"] == operator
    return bool(row["assignee"]) and name is not None and row["assignee"] == name


def take_request(
    db: sqlite3.Connection, request_id: int, assignee: str, now: float, assignee_id: str | None = None
) -> tuple[sqlite3.Row, bool]:
    """Asigna responsable y pasa de «Pendiente de recepción» a «En atención». Idempotente para la misma persona.

    Devuelve (fila, cambió). Si otra persona ya la tomó, `RequestConflict`: no se pisa al responsable.
    """
    with transaction(db):
        row = get_request_row(db, request_id)
        if row is None:
            raise LookupError(request_id)
        if row["status"] == "cerrada":
            raise RequestConflict("La solicitud está cerrada")
        if row["assignee"] and not owned_by(row, assignee, assignee_id):
            raise RequestConflict(f"Ya la tomó {row['assignee']}")
        if row["assignee"]:
            return row, False
        status = "en_atencion" if row["status"] == "pendiente" else row["status"]
        db.execute(
            "UPDATE requests SET assignee = ?, assignee_id = ?, taken_at = ?, status = ?, updated_at = ? WHERE id = ?",
            (assignee, assignee_id, now, status, now, request_id),
        )
        _record(db, row["conversation_id"], "request_taken", now, {"request_id": request_id, "assignee": assignee})
        return get_request_row(db, request_id), True


def staff_reply(
    db: sqlite3.Connection, request_id: int, author: str, body: str, kind: str, now: float,
    client_id: str | None = None, author_id: str | None = None,
) -> tuple[sqlite3.Row, dict]:
    """Respuesta escrita por recepción en el mismo hilo del huésped.

    Una respuesta pertinente (`answer`) deja la solicitud «Respondida» y, si es la primera, detiene el
    reloj y registra `human_first_reply`. Un acuse (`ack`) se envía igual pero NO cuenta como respuesta.
    Todo ocurre en una transacción —llave, mensaje, cambio de estado y evento—: o queda todo, o nada. Así un
    reintento con la misma `client_id` nunca duplica una respuesta ya guardada (DuplicateAction).
    """
    with transaction(db):
        if client_id is not None:
            claim_action(db, f"staff:{request_id}", client_id, fingerprint(kind, body), now, "done")
        row = get_request_row(db, request_id)
        if row is None:
            raise LookupError(request_id)
        if row["status"] == "cerrada":
            raise RequestConflict("La solicitud está cerrada")
        if not owned_by(row, author, author_id):
            raise RequestConflict("Toma la solicitud antes de responder" if not row["assignee"]
                                  else f"La atiende {row['assignee']}")
        message = insert_demo_message(db, row["conversation_id"], "staff", body, now, author=author, kind=kind,
                                       request_id=request_id)
        if client_id is not None:
            db.execute(
                "UPDATE action_keys SET message_id = ? WHERE scope = ? AND client_id = ?",
                (message["id"], f"staff:{request_id}", client_id),
            )
        conversation_id = row["conversation_id"]
        if kind == "answer":
            first = row["first_answer_at"] is None
            db.execute(
                "UPDATE requests SET status = 'respondida', first_answer_at = COALESCE(first_answer_at, ?), "
                "updated_at = ? WHERE id = ?",
                (now, now, request_id),
            )
            if first and stop_sla(db, conversation_id, now):
                _record(db, conversation_id, "human_first_reply", now,
                        {"user_id": None, "author": author, "request_id": request_id})
        else:
            db.execute("UPDATE requests SET updated_at = ? WHERE id = ?", (now, request_id))
            _record(db, conversation_id, "human_ack", now, {"author": author, "request_id": request_id})
        return get_request_row(db, request_id), message


def guest_wrote_to_reception(db: sqlite3.Connection, conversation_id: int, now: float) -> sqlite3.Row | None:
    """El huésped escribe mientras recepción tiene el caso: el bot calla y la solicitud vuelve a pedir respuesta."""
    row = open_request(db, conversation_id)
    if row is None:
        return None
    status = "en_atencion" if row["status"] == "respondida" else row["status"]
    db.execute(
        "UPDATE requests SET last_guest_at = ?, status = ?, updated_at = ? WHERE id = ?",
        (now, status, now, row["id"]),
    )
    return get_request_row(db, row["id"])


def close_request(
    db: sqlite3.Connection, request_id: int, now: float, *, author: str | None = None, author_id: str | None = None,
) -> sqlite3.Row:
    """Cierra la atención y devuelve el hilo al asistente. Con autor, exige que sea su responsable.

    La autorización y el cierre comparten transacción; las llamadas internas sin autor conservan su uso previo.
    """
    with transaction(db):
        row = get_request_row(db, request_id)
        if row is None:
            raise LookupError(request_id)
        if author is not None and not owned_by(row, author, author_id):
            raise RequestConflict("Toma la solicitud antes de cerrar" if not row["assignee"]
                                  else f"La atiende {row['assignee']}")
        if row["status"] != "cerrada":
            db.execute(
                "UPDATE requests SET status = 'cerrada', closed_at = ?, updated_at = ? WHERE id = ?",
                (now, now, request_id),
            )
            _record(db, row["conversation_id"], "request_closed", now, {"request_id": request_id})
        return get_request_row(db, request_id)


def mark_request_breached(db: sqlite3.Connection, conversation_id: int, now: float) -> None:
    db.execute(
        "UPDATE requests SET breached_at = COALESCE(breached_at, ?) WHERE conversation_id = ? "
        f"AND status IN ({','.join('?' for _ in OPEN_STATUSES)})",
        (now, conversation_id, *OPEN_STATUSES),
    )


def human_answered(db: sqlite3.Connection, conversation_id: int, now: float) -> None:
    """Respuesta humana en Chatwoot (canal real): la solicitud abierta queda «Respondida»."""
    db.execute(
        "UPDATE requests SET status = 'respondida', first_answer_at = COALESCE(first_answer_at, ?), "
        f"updated_at = ? WHERE conversation_id = ? AND status IN ({','.join('?' for _ in OPEN_STATUSES)})",
        (now, now, conversation_id, *OPEN_STATUSES),
    )


def confirm_reservation(db: sqlite3.Connection, conversation_id: int, now: float) -> None:
    """Reserva confirmada por una persona en el PMS: es el único camino a «confirmada»."""
    db.execute(
        "UPDATE requests SET reservation_status = 'confirmada', updated_at = ? WHERE id = "
        "(SELECT id FROM requests WHERE conversation_id = ? ORDER BY id DESC LIMIT 1)",
        (now, conversation_id),
    )


def request_events(db: sqlite3.Connection, conversation_id: int, since: float) -> list[dict]:
    """Eventos del hilo desde que entró la consulta: con ellos se recalcula la medición a mano."""
    rows = db.execute(
        "SELECT kind, ts, payload FROM events WHERE conversation_id = ? AND ts >= ? ORDER BY ts, id",
        (conversation_id, since),
    ).fetchall()
    return [{"kind": row["kind"], "ts": row["ts"], "payload": json.loads(row["payload"])} for row in rows]


def _record(db: sqlite3.Connection, conversation_id: int, kind: str, now: float, payload: dict) -> None:
    record_event(db, conversation_id, kind, now, payload)
