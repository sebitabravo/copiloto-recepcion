"""Lógica del puente: huésped (WhatsApp) <-> conversación de Chatwoot.

Entrada:  webhook de OpenWA  -> mensaje `incoming` en el inbox API (el AgentBot del copiloto responde).
Salida:   webhook del inbox API -> `send-text` de OpenWA, solo para mensajes salientes y públicos.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import weakref
from collections.abc import Awaitable, Callable

from . import store
from .chatwoot import ChatwootClient
from .config import Settings
from .openwa import OpenWAClient

logger = logging.getLogger(__name__)

TEXT_TYPES = {"chat", "text", ""}
UNSUPPORTED_REPLY = "Por ahora solo puedo leer mensajes de texto. ¿Me escribes tu consulta?"


def render_content(event: dict) -> str:
    """Texto a enviar al huésped. Los botones (input_select) se convierten en una lista numerada."""
    content = (event.get("content") or "").strip()
    if event.get("content_type") == "input_select":
        items = (event.get("content_attributes") or {}).get("items") or []
        lines = [f"{index}. {item.get('title', '')}" for index, item in enumerate(items, start=1)]
        if lines:
            hint = "Responde con el número de la opción."
            return "\n".join([content, *lines, hint]).strip()
    return content


class Bridge:
    def __init__(self, settings: Settings, db: sqlite3.Connection, chatwoot: ChatwootClient,
                 openwa: OpenWAClient, clock: Callable[[], float], sleep=asyncio.sleep):
        self.settings = settings
        self.sleep = sleep
        self._inflight: set[str] = set()
        self._outbox: dict[str, list[tuple[int, str, str]]] = {}
        self._flushing: set[str] = set()
        self.db = db
        self.chatwoot = chatwoot
        self.openwa = openwa
        self.clock = clock
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()

    def _lock(self, chat_id: str) -> asyncio.Lock:
        lock = self._locks.get(chat_id)
        if lock is None:
            lock = self._locks[chat_id] = asyncio.Lock()
        return lock

    async def _deliver(self, key: str, action: Callable[[], Awaitable[None]]) -> bool:
        """Ejecuta `action` con reintentos acotados y registra `key` solo si salió bien.

        Un fallo definitivo NO deja la clave: así un reenvío posterior del mismo evento se procesa.
        `_inflight` evita ejecutar dos veces un evento duplicado que llega mientras se reintenta.
        """
        if key in self._inflight or store.is_processed(self.db, key):
            return False
        self._inflight.add(key)
        try:
            delays = self.settings.retry_delays_s
            for attempt in range(len(delays) + 1):
                try:
                    await action()
                    store.mark_processed(self.db, key, self.clock())
                    return True
                except Exception:
                    if attempt == len(delays):
                        logger.exception("No se pudo entregar %s tras %d intentos", key, attempt + 1)
                        return False
                    logger.warning("Falló la entrega de %s (intento %d); reintentando", key, attempt + 1)
                    await self.sleep(delays[attempt])
            return False
        finally:
            self._inflight.discard(key)

    async def handle_openwa(self, event: dict) -> None:
        try:
            await self._on_guest_message(event)
        except Exception:
            logger.exception("Falla procesando un mensaje de OpenWA")

    async def handle_chatwoot(self, event: dict) -> None:
        try:
            await self._on_outgoing(event)
        except Exception:
            logger.exception("Falla enviando una respuesta a WhatsApp")

    async def _on_guest_message(self, event: dict) -> None:
        if event.get("event") != "message.received":
            return
        session_id = event.get("sessionId")
        if session_id and str(session_id) not in await self.openwa.allowed_session_ids():
            return
        data = event.get("data") or {}
        # Los mensajes que envía esta misma sesión vuelven como eventos: sin este filtro habría un bucle
        if data.get("fromMe") or data.get("isGroup") or data.get("isStatusBroadcast"):
            return
        chat_id = str(data.get("chatId") or data.get("from") or "")
        if not chat_id.endswith(("@c.us", "@lid")):
            return
        message_id = str(data.get("id") or event.get("idempotencyKey") or "")
        if not message_id:
            return
        body = str(data.get("body") or "").strip()
        if data.get("type", "") not in TEXT_TYPES or not body:
            await self._deliver(f"wa:{message_id}", lambda: self.openwa.send_text(chat_id, UNSUPPORTED_REPLY))
            return
        name = str((data.get("contact") or {}).get("pushName") or "") or "Huésped WhatsApp"

        async def post() -> None:
            async with self._lock(chat_id):
                source_id, conversation_id = await self._conversation_for(chat_id, name)
                await self.chatwoot.post_guest_message(source_id, conversation_id,
                                                       body[:self.settings.max_text_chars])
                store.touch_conversation(self.db, conversation_id, self.clock())

        await self._deliver(f"wa:{message_id}", post)

    async def _conversation_for(self, chat_id: str, name: str) -> tuple[str, int]:
        source_id = store.contact_source(self.db, chat_id)
        if source_id is None:
            source_id = await self.chatwoot.create_contact(chat_id, name)
            store.save_contact(self.db, chat_id, source_id)
        current = store.current_conversation(self.db, chat_id)
        if current is not None and await self.chatwoot.conversation_status(current) not in (None, "resolved"):
            return source_id, current
        conversation_id = await self.chatwoot.create_conversation(source_id)
        store.save_conversation(self.db, chat_id, conversation_id, self.clock())
        return source_id, conversation_id

    async def _on_outgoing(self, event: dict) -> None:
        if event.get("event") != "message_created" or event.get("private"):
            return
        if event.get("message_type") not in ("outgoing", 1):
            return
        conversation = event.get("conversation") or {}
        conversation_id = conversation.get("id") or event.get("conversation_id")
        chat_id = store.chat_for_conversation(self.db, conversation_id) if conversation_id else None
        if chat_id is None:
            return
        text = render_content(event)
        if text:
            store.touch_conversation(self.db, conversation_id, self.clock())
            await self._enqueue(chat_id, int(event.get("id") or 0), text)

    async def _enqueue(self, chat_id: str, message_id: int, text: str) -> None:
        """Cola por huésped: Chatwoot entrega cada mensaje en un job aparte y pueden llegar desordenados.

        El primero en llegar espera una ventana corta, ordena el lote por id y envía de a uno, para que el
        saludo, la ubicación y el menú lleguen en ese orden. Un envío fallido no frena a los siguientes.
        """
        self._outbox.setdefault(chat_id, []).append((message_id, f"cw:{message_id}", text))
        if chat_id in self._flushing:
            return
        self._flushing.add(chat_id)
        try:
            await self.sleep(self.settings.reorder_window_s)
            while self._outbox.get(chat_id):
                for _, key, content in sorted(self._outbox.pop(chat_id)):
                    await self._deliver(key, lambda content=content: self.openwa.send_text(chat_id, content))
        finally:
            self._flushing.discard(chat_id)
