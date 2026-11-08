"""Contrato del puente WhatsApp: lo que entra al copiloto y, sobre todo, lo que NUNCA sale al huésped."""

import asyncio
import hashlib
import hmac
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient
from wa_bridge.bridge import Bridge, render_content
from wa_bridge.config import Settings
from wa_bridge.main import create_app, purge_once, verify_chatwoot_signature
from wa_bridge.openwa import OpenWAClient, to_chat_id, verify_openwa_signature

from wa_bridge import store

GUEST = "56911111111@c.us"
OPENWA_SECRET = "openwa-secret"
INBOX_SECRET = "inbox-secret"


class FakeChatwoot:
    def __init__(self):
        self.contacts, self.conversations, self.messages = [], [], []
        self.statuses: dict[int, str | None] = {}

    async def create_contact(self, chat_id, name):
        self.contacts.append((chat_id, name))
        return f"source-{len(self.contacts)}"

    async def create_conversation(self, source_id):
        conversation_id = 100 + len(self.conversations)
        self.conversations.append(conversation_id)
        self.statuses[conversation_id] = "pending"
        return conversation_id

    async def post_guest_message(self, source_id, conversation_id, content):
        self.messages.append((source_id, conversation_id, content))

    async def conversation_status(self, conversation_id):
        return self.statuses.get(conversation_id)


class FakeOpenWA:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.failures = 0
        self.session_ids = {"default", "sess-uuid"}

    async def send_text(self, target, text):
        if self.failures:
            self.failures -= 1
            raise httpx.ConnectError("openwa caído")
        self.sent.append((target, text))

    async def allowed_session_ids(self):
        return self.session_ids


def settings(**overrides) -> Settings:
    values = dict(
        openwa_url="http://openwa:2785",
        openwa_api_key="k",
        openwa_webhook_secret=OPENWA_SECRET,
        chatwoot_url="http://chatwoot:3000",
        chatwoot_account_id=1,
        chatwoot_admin_token="t",
        inbox_identifier="ident",
        inbox_secret=INBOX_SECRET,
        db_path=":memory:",
    )
    values.update(overrides)
    return Settings(**values)


async def no_sleep(seconds):
    await asyncio.sleep(0)


@pytest.fixture
def parts():
    chatwoot, openwa = FakeChatwoot(), FakeOpenWA()
    bridge = Bridge(settings(), store.connect(":memory:"), chatwoot, openwa, lambda: 1000.0, sleep=no_sleep)
    return bridge, chatwoot, openwa


def received(body="Hola", message_id="m1", **data):
    payload = {
        "id": message_id,
        "chatId": GUEST,
        "from": GUEST,
        "body": body,
        "type": "chat",
        "fromMe": False,
        "isGroup": False,
        "contact": {"pushName": "Ana"},
    }
    payload.update(data)
    return {"event": "message.received", "data": payload}


def outgoing(conversation_id=100, content="Hola, soy el asistente", message_id=7, **extra):
    event = {
        "event": "message_created",
        "id": message_id,
        "message_type": "outgoing",
        "private": False,
        "content": content,
        "conversation": {"id": conversation_id},
    }
    event.update(extra)
    return event


# ---------- firmas ----------


def sign_openwa(body: bytes, secret=OPENWA_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_openwa_signature_is_checked_and_an_empty_secret_rejects_everything():
    body = b'{"a":1}'
    assert verify_openwa_signature(OPENWA_SECRET, body, sign_openwa(body))
    assert not verify_openwa_signature(OPENWA_SECRET, body, sign_openwa(body, "otro"))
    assert not verify_openwa_signature(OPENWA_SECRET, body, "")
    assert not verify_openwa_signature("", body, sign_openwa(body, ""))


def chatwoot_headers(body: bytes, now=1000, secret=INBOX_SECRET) -> dict:
    digest = hmac.new(secret.encode(), f"{now}.".encode() + body, hashlib.sha256).hexdigest()
    return {"x-chatwoot-timestamp": str(now), "x-chatwoot-signature": f"sha256={digest}"}


def test_chatwoot_signature_rejects_stale_timestamps_wrong_secret_and_empty_secret():
    body = b"{}"
    assert verify_chatwoot_signature(INBOX_SECRET, chatwoot_headers(body), body, 1000, 300)
    assert not verify_chatwoot_signature(INBOX_SECRET, chatwoot_headers(body, now=100), body, 1000, 300)
    assert not verify_chatwoot_signature(INBOX_SECRET, chatwoot_headers(body, secret="x"), body, 1000, 300)
    assert not verify_chatwoot_signature("", chatwoot_headers(body, secret=""), body, 1000, 300)


def test_webhook_endpoints_return_401_without_a_valid_signature(parts):
    bridge, _, _ = parts
    client = TestClient(create_app(settings(), bridge, clock=lambda: 1000.0))
    assert client.post("/webhooks/openwa", content=b"{}").status_code == 401
    assert client.post("/webhooks/chatwoot", content=b"{}").status_code == 401


# ---------- arranque: los secretos de Chatwoot vacíos matan el canal en silencio ----------


def test_create_app_fails_fast_without_chatwoot_secrets():
    with pytest.raises(ValueError, match="CHATWOOT_ADMIN_TOKEN"):
        create_app(settings(chatwoot_admin_token=""))
    with pytest.raises(ValueError, match="CHATWOOT_WA_INBOX_SECRET"):
        create_app(settings(inbox_secret=""))
    with pytest.raises(ValueError, match="CHATWOOT_ADMIN_TOKEN, CHATWOOT_WA_INBOX_SECRET"):
        create_app(settings(chatwoot_admin_token="", inbox_secret=""))


def test_create_app_builds_when_the_chatwoot_secrets_are_present():
    assert create_app(settings(), clock=lambda: 1000.0).title


def test_purge_once_removes_old_dedupe_keys_and_stale_mappings():
    db = store.connect(":memory:")
    now = 1_000_000.0
    store.mark_processed(db, "viejo", now - 31 * 86400)
    store.mark_processed(db, "reciente", now - 86400)
    store.save_contact(db, "viejo@c.us", "src-1")
    store.save_conversation(db, "viejo@c.us", 1, now - 91 * 86400)
    store.save_contact(db, "activo@c.us", "src-2")
    store.save_conversation(db, "activo@c.us", 2, now - 86400)

    purged = purge_once(db, now)

    assert purged == 1
    assert not store.is_processed(db, "viejo") and store.is_processed(db, "reciente")
    assert store.chat_for_conversation(db, 1) is None
    assert store.chat_for_conversation(db, 2) == "activo@c.us" and store.contact_source(db, "activo@c.us") == "src-2"


def test_webhook_endpoints_accept_signed_requests_and_process_them(parts):
    bridge, chatwoot, openwa = parts
    store.save_conversation(bridge.db, GUEST, 100, 1.0)
    client = TestClient(create_app(settings(), bridge, clock=lambda: 1000.0))
    body = json.dumps(received("Hola")).encode()
    assert (
        client.post("/webhooks/openwa", content=body, headers={"x-openwa-signature": sign_openwa(body)}).status_code
        == 200
    )
    body = json.dumps(outgoing()).encode()
    assert client.post("/webhooks/chatwoot", content=body, headers=chatwoot_headers(body)).status_code == 200
    assert chatwoot.messages and openwa.sent == [(GUEST, "Hola, soy el asistente")]


def test_oversized_bodies_are_rejected_before_authentication(parts):
    bridge, _, _ = parts
    client = TestClient(create_app(settings(max_body_bytes=10), bridge, clock=lambda: 1000.0))
    assert client.post("/webhooks/openwa", content=b"x" * 50).status_code == 413


# ---------- huésped -> Chatwoot ----------


async def test_first_message_creates_contact_and_conversation_and_posts_the_text(parts):
    bridge, chatwoot, _ = parts
    await bridge.handle_openwa(received("Quiero una pieza"))
    assert chatwoot.contacts == [(GUEST, "Ana")]
    assert chatwoot.messages == [("source-1", 100, "Quiero una pieza")]


async def test_next_messages_reuse_the_open_conversation(parts):
    bridge, chatwoot, _ = parts
    await bridge.handle_openwa(received("Hola", message_id="m1"))
    await bridge.handle_openwa(received("1", message_id="m2"))
    assert len(chatwoot.conversations) == 1 and len(chatwoot.contacts) == 1
    assert [m[1] for m in chatwoot.messages] == [100, 100]


async def test_a_resolved_conversation_starts_a_new_one(parts):
    bridge, chatwoot, _ = parts
    await bridge.handle_openwa(received("Hola", message_id="m1"))
    chatwoot.statuses[100] = "resolved"
    await bridge.handle_openwa(received("Otra consulta", message_id="m2"))
    assert chatwoot.conversations == [100, 101]
    assert chatwoot.messages[-1][1] == 101


async def test_a_deleted_conversation_starts_a_new_one(parts):
    bridge, chatwoot, _ = parts
    await bridge.handle_openwa(received("Hola", message_id="m1"))
    chatwoot.statuses[100] = None
    await bridge.handle_openwa(received("Hola de nuevo", message_id="m2"))
    assert chatwoot.conversations == [100, 101]


async def test_messages_sent_by_the_bot_session_never_loop_back(parts):
    bridge, chatwoot, openwa = parts
    await bridge.handle_openwa(received("respuesta del bot", fromMe=True))
    assert chatwoot.messages == [] and openwa.sent == []


async def test_groups_and_status_broadcasts_are_ignored(parts):
    bridge, chatwoot, openwa = parts
    for number, extra in enumerate(
        [{"isGroup": True}, {"isStatusBroadcast": True}, {"chatId": "1203630@g.us", "from": "1203630@g.us"}]
    ):
        await bridge.handle_openwa(received("hola a todos", message_id=f"g{number}", **extra))
    assert chatwoot.messages == [] and openwa.sent == []


async def test_other_events_are_ignored(parts):
    bridge, chatwoot, _ = parts
    await bridge.handle_openwa({"event": "session.status", "data": {"status": "ready"}})
    assert chatwoot.messages == []


async def test_a_redelivered_webhook_is_processed_once(parts):
    bridge, chatwoot, _ = parts
    await bridge.handle_openwa(received("Hola", message_id="same"))
    await bridge.handle_openwa(received("Hola", message_id="same"))
    assert len(chatwoot.messages) == 1


async def test_voice_notes_get_a_polite_text_only_reply_and_never_reach_chatwoot(parts):
    bridge, chatwoot, openwa = parts
    await bridge.handle_openwa(received("", type="voice"))
    assert chatwoot.messages == []
    assert openwa.sent and openwa.sent[0][0] == GUEST and "texto" in openwa.sent[0][1]


async def test_long_texts_are_truncated(parts):
    bridge, chatwoot, _ = parts
    await bridge.handle_openwa(received("a" * 5000))
    assert len(chatwoot.messages[0][2]) == bridge.settings.max_text_chars


async def test_lid_senders_are_supported(parts):
    bridge, chatwoot, _ = parts
    await bridge.handle_openwa(received("Hola", chatId="248069442560050@lid", **{"from": "248069442560050@lid"}))
    assert chatwoot.contacts[0][0] == "248069442560050@lid"


async def test_an_error_in_chatwoot_does_not_crash_the_handler(parts):
    bridge, chatwoot, _ = parts

    async def boom(*args):
        raise httpx.ConnectError("down")

    chatwoot.create_contact = boom
    await bridge.handle_openwa(received("Hola"))


async def test_a_transient_chatwoot_failure_is_retried_and_the_message_arrives(parts):
    bridge, chatwoot, _ = parts
    original, calls = chatwoot.post_guest_message, {"n": 0}

    async def flaky(*args):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("down")
        await original(*args)

    chatwoot.post_guest_message = flaky
    await bridge.handle_openwa(received("Hola"))
    assert len(chatwoot.messages) == 1 and calls["n"] == 3


async def test_a_message_that_kept_failing_can_be_replayed_later(parts):
    """Regresión: marcar como procesado ANTES de entregar perdía el mensaje para siempre."""
    bridge, chatwoot, _ = parts
    original = chatwoot.post_guest_message

    async def down(*args):
        raise httpx.ConnectError("down")

    chatwoot.post_guest_message = down
    await bridge.handle_openwa(received("Hola", message_id="lost?"))
    assert chatwoot.messages == []
    chatwoot.post_guest_message = original
    await bridge.handle_openwa(received("Hola", message_id="lost?"))
    assert len(chatwoot.messages) == 1


async def test_events_from_another_openwa_session_are_ignored(parts):
    bridge, chatwoot, _ = parts
    await bridge.handle_openwa({**received("Hola"), "sessionId": "otra-cuenta"})
    assert chatwoot.messages == []


async def test_events_are_accepted_by_session_name_or_id(parts):
    bridge, chatwoot, _ = parts
    await bridge.handle_openwa({**received("uno", message_id="a"), "sessionId": "default"})
    await bridge.handle_openwa({**received("dos", message_id="b"), "sessionId": "sess-uuid"})
    await bridge.handle_openwa(received("tres", message_id="c"))
    assert len(chatwoot.messages) == 3


# ---------- Chatwoot -> huésped ----------


async def test_public_outgoing_messages_are_delivered_to_the_guest(parts):
    bridge, _, openwa = parts
    store.save_conversation(bridge.db, GUEST, 100, 1.0)
    await bridge.handle_chatwoot(outgoing(content="Te comunico con recepción"))
    assert openwa.sent == [(GUEST, "Te comunico con recepción")]


async def test_private_notes_are_never_delivered_to_the_guest(parts):
    """Regresión crítica: la nota del SLA vencido (sla.py) es privada y jamás debe llegar al huésped."""
    bridge, _, openwa = parts
    store.save_conversation(bridge.db, GUEST, 100, 1.0)
    await bridge.handle_chatwoot(outgoing(content="SLA vencido: pasaron 181 s sin respuesta humana", private=True))
    assert openwa.sent == []


async def test_only_outgoing_messages_are_delivered(parts):
    bridge, _, openwa = parts
    store.save_conversation(bridge.db, GUEST, 100, 1.0)
    for number, message_type in enumerate(["incoming", "activity", "template", 0, 2]):
        await bridge.handle_chatwoot(outgoing(message_type=message_type, message_id=number))
    assert openwa.sent == []


async def test_messages_of_conversations_the_bridge_does_not_own_are_ignored(parts):
    bridge, _, openwa = parts
    await bridge.handle_chatwoot(outgoing(conversation_id=999))
    assert openwa.sent == []


async def test_an_unmapped_conversation_is_logged_before_dropping(parts, caplog):
    bridge, _, openwa = parts
    with caplog.at_level(logging.WARNING, logger="wa_bridge.bridge"):
        await bridge.handle_chatwoot(outgoing(conversation_id=999, content="Secreto", message_id=55))
    assert openwa.sent == []
    dropped = [
        record for record in caplog.records if record.levelno == logging.WARNING and "999" in record.getMessage()
    ]
    assert dropped, "el descarte debe quedar registrado con la conversación"
    assert "Secreto" not in dropped[0].getMessage(), "el texto del mensaje no va al log"


async def test_replies_of_an_old_conversation_still_reach_the_same_guest(parts):
    bridge, chatwoot, openwa = parts
    await bridge.handle_openwa(received("Hola", message_id="m1"))
    chatwoot.statuses[100] = "resolved"
    await bridge.handle_openwa(received("Otra", message_id="m2"))
    await bridge.handle_chatwoot(outgoing(conversation_id=100, message_id=1))
    await bridge.handle_chatwoot(outgoing(conversation_id=101, message_id=2))
    assert [target for target, _ in openwa.sent] == [GUEST, GUEST]


def test_a_conversation_with_recent_activity_survives_the_mapping_purge():
    """Una conversación abierta hace más de 90 días pero con actividad reciente no puede quedar huérfana."""
    db = store.connect(":memory:")
    store.save_contact(db, "viva@c.us", "src-1")
    store.save_conversation(db, "viva@c.us", 7, 100.0)
    store.touch_conversation(db, 7, 900.0)
    store.purge_mappings(db, older_than=500.0)
    assert store.chat_for_conversation(db, 7) == "viva@c.us" and store.contact_source(db, "viva@c.us") == "src-1"


def test_an_old_database_without_the_activity_column_is_migrated(tmp_path):
    import sqlite3

    path = tmp_path / "migration-test.sqlite"
    legacy = sqlite3.connect(path)
    legacy.executescript(
        "CREATE TABLE conversations (conversation_id INTEGER PRIMARY KEY, chat_id TEXT NOT NULL, "
        "created_at REAL NOT NULL); INSERT INTO conversations VALUES (1, 'a@c.us', 50.0);"
    )
    legacy.commit()
    legacy.close()
    db = store.connect(str(path))
    store.purge_mappings(db, older_than=10.0)
    assert store.chat_for_conversation(db, 1) == "a@c.us"


async def test_a_session_list_failure_does_not_drop_events_tagged_with_the_session_uuid():
    state = {"fail": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["fail"]:
            return httpx.Response(503)
        return httpx.Response(200, json=[{"id": "uuid-1", "name": "default", "status": "ready"}])

    client = OpenWAClient("http://openwa:2785", "key", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await client.allowed_session_ids() == {"default", "uuid-1"}
    state["fail"] = True
    assert "uuid-1" in await client.allowed_session_ids()


def test_old_guest_mappings_are_purged_after_the_retention_period():
    """Los chats guardan el teléfono: el mapeo del puente no puede sobrevivir a la retención del copiloto."""
    db = store.connect(":memory:")
    store.save_contact(db, "viejo@c.us", "src-1")
    store.save_conversation(db, "viejo@c.us", 1, 100.0)
    store.save_contact(db, "activo@c.us", "src-2")
    store.save_conversation(db, "activo@c.us", 2, 900.0)
    store.save_contact(db, "sin-conversacion@c.us", "src-3")
    store.purge_mappings(db, older_than=500.0)
    assert store.chat_for_conversation(db, 1) is None and store.contact_source(db, "viejo@c.us") is None
    assert store.chat_for_conversation(db, 2) == "activo@c.us" and store.contact_source(db, "activo@c.us") == "src-2"
    assert store.contact_source(db, "sin-conversacion@c.us") is None


def test_old_deduplication_keys_are_purged_and_recent_ones_kept():
    db = store.connect(":memory:")
    store.mark_processed(db, "viejo", 100.0)
    store.mark_processed(db, "reciente", 900.0)
    assert store.purge_processed(db, older_than=500.0) == 1
    assert not store.is_processed(db, "viejo") and store.is_processed(db, "reciente")


async def test_a_burst_of_replies_reaches_the_guest_in_message_order(parts):
    """Chatwoot entrega cada webhook en un job distinto: el puente reordena por id antes de enviar."""
    bridge, _, openwa = parts
    store.save_conversation(bridge.db, GUEST, 100, 1.0)
    await asyncio.gather(*(bridge.handle_chatwoot(outgoing(content=f"mensaje {n}", message_id=n)) for n in (3, 1, 2)))
    assert [text for _, text in openwa.sent] == ["mensaje 1", "mensaje 2", "mensaje 3"]


async def test_replies_are_sent_one_at_a_time_per_guest(parts):
    bridge, _, openwa = parts
    store.save_conversation(bridge.db, GUEST, 100, 1.0)
    active, peak = 0, 0
    original = openwa.send_text

    async def tracked(target, text):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        await original(target, text)
        active -= 1

    openwa.send_text = tracked
    await asyncio.gather(*(bridge.handle_chatwoot(outgoing(content=f"m{n}", message_id=n)) for n in range(1, 5)))
    assert peak == 1 and len(openwa.sent) == 4


async def test_one_failing_reply_does_not_block_the_next_ones(parts):
    bridge, _, openwa = parts
    store.save_conversation(bridge.db, GUEST, 100, 1.0)
    openwa.failures = 99
    await bridge.handle_chatwoot(outgoing(content="se pierde", message_id=1))
    openwa.failures = 0
    await bridge.handle_chatwoot(outgoing(content="llega", message_id=2))
    assert [text for _, text in openwa.sent] == ["llega"]


async def test_a_failed_delivery_to_whatsapp_is_retried(parts):
    bridge, _, openwa = parts
    store.save_conversation(bridge.db, GUEST, 100, 1.0)
    openwa.failures = 2
    await bridge.handle_chatwoot(outgoing(message_id=11))
    assert openwa.sent == [(GUEST, "Hola, soy el asistente")]


async def test_a_delivery_that_keeps_failing_is_not_marked_as_sent(parts):
    bridge, _, openwa = parts
    store.save_conversation(bridge.db, GUEST, 100, 1.0)
    openwa.failures = 99
    await bridge.handle_chatwoot(outgoing(message_id=12))
    openwa.failures = 0
    await bridge.handle_chatwoot(outgoing(message_id=12))
    assert len(openwa.sent) == 1


async def test_a_redelivered_outgoing_event_is_sent_once(parts):
    bridge, _, openwa = parts
    store.save_conversation(bridge.db, GUEST, 100, 1.0)
    await bridge.handle_chatwoot(outgoing(message_id=5))
    await bridge.handle_chatwoot(outgoing(message_id=5))
    assert len(openwa.sent) == 1


async def test_empty_outgoing_content_is_not_sent(parts):
    bridge, _, openwa = parts
    store.save_conversation(bridge.db, GUEST, 100, 1.0)
    await bridge.handle_chatwoot(outgoing(content="   "))
    assert openwa.sent == []


def test_buttons_are_rendered_as_a_numbered_list():
    event = outgoing(
        content="¿En qué te ayudo?",
        content_type="input_select",
        content_attributes={"items": [{"title": "Reservar", "value": "a"}, {"title": "Consultar", "value": "b"}]},
    )
    assert render_content(event) == "¿En qué te ayudo?\n1. Reservar\n2. Consultar\nResponde con el número de la opción."


# ---------- cliente OpenWA ----------


def test_chat_ids_accept_whatsapp_ids_and_reject_anything_else():
    assert to_chat_id("56911111111@c.us") == "56911111111@c.us"
    assert to_chat_id("248069442560050@lid") == "248069442560050@lid"
    with pytest.raises(ValueError):
        to_chat_id("hola")
    with pytest.raises(ValueError):
        to_chat_id("+56911111111")


async def test_openwa_client_uses_the_configured_session_not_just_any_ready_one():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/api/sessions":
            return httpx.Response(
                200,
                json=[
                    {"id": "otra", "name": "personal", "status": "ready"},
                    {"id": "s1", "name": "default", "status": "ready"},
                ],
            )
        return httpx.Response(200, json={"ok": True})

    client = OpenWAClient(
        "http://openwa:2785", "key", httpx.AsyncClient(transport=httpx.MockTransport(handler)), session_name="default"
    )
    await client.send_text("56911111111@c.us", "Hola")
    assert calls[-1] == "/api/sessions/s1/messages/send-text"
    assert await client.allowed_session_ids() == {"default", "s1"}


async def test_openwa_client_sends_text_with_the_ready_session():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            (
                request.method,
                request.url.path,
                request.headers.get("x-api-key"),
                json.loads(request.content) if request.content else None,
            )
        )
        if request.url.path == "/api/sessions":
            sessions = [
                {"id": "s0", "name": "default", "status": "qr"},
                {"id": "s1", "name": "default", "status": "ready"},
            ]
            return httpx.Response(200, json=sessions)
        return httpx.Response(200, json={"ok": True})

    client = OpenWAClient("http://openwa:2785", "key", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await client.send_text("56911111111@c.us", "Hola")
    assert calls[-1] == (
        "POST",
        "/api/sessions/s1/messages/send-text",
        "key",
        {"chatId": "56911111111@c.us", "text": "Hola"},
    )


async def test_openwa_client_fails_loudly_when_no_session_is_ready():
    from wa_bridge.openwa import OpenWAError

    sessions = [{"id": "s0", "name": "default", "status": "qr"}]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=sessions))
    client = OpenWAClient("http://openwa:2785", "key", httpx.AsyncClient(transport=transport))
    with pytest.raises(OpenWAError):
        await client.send_text("56911111111@c.us", "Hola")
