"""Worker del cronómetro SLA (180 s) y de la expiración de pre-reservas auxiliares.

El SLA nativo de Chatwoot es Enterprise, por eso el reloj es propio. El reloj arranca en el traspaso
dentro del turno, no se reinicia al asignar y se detiene con el primer mensaje saliente de una persona.
"""

import asyncio
import logging
import sqlite3
from collections.abc import Callable

from copiloto import store
from copiloto.chatwoot import ChatwootClient
from copiloto.config import Settings
from copiloto.events import record_event

logger = logging.getLogger(__name__)


class SlaWorker:
    def __init__(self, settings: Settings, db: sqlite3.Connection, chatwoot: ChatwootClient,
                 clock: Callable[[], float], demo_channel=None):
        self.settings = settings
        self.db = db
        self.chatwoot = chatwoot
        self.clock = clock
        # Las conversaciones de la demo avisan en su propio hilo: nunca se llama a Chatwoot con ellas.
        self.demo_channel = demo_channel

    def _channel(self, conversation_id: int):
        if self.demo_channel is not None and store.conversation_source(self.db, conversation_id) == store.DEMO_SOURCE:
            return self.demo_channel
        return self.chatwoot

    async def tick(self, now: float | None = None) -> None:
        """Una pasada: marca ámbar/vencido y expira pre-reservas. El reloj se inyecta para testear."""
        now = self.clock() if now is None else now
        await self._check_sla(now)
        for row in store.expire_prebookings(self.db, now):
            # Solo estado local del copiloto: la expiración jamás toca el PMS
            record_event(self.db, row["conversation_id"], "prebooking_expired", now, {"prebooking_id": row["id"]})

    async def _check_sla(self, now: float) -> None:
        rows = self.db.execute(
            "SELECT conversation_id FROM conversation_state WHERE sla_started_at IS NOT NULL "
            "AND sla_stopped_at IS NULL AND sla_red_done = 0").fetchall()
        for row in rows:
            conversation_id = row["conversation_id"]
            try:
                await self._check_one(conversation_id, now)
            except Exception:
                logger.exception("No se pudo actualizar el SLA de la conversación %s", conversation_id)

    def _running(self, conversation_id: int):
        """Estado fresco si el reloj sigue corriendo; None si se detuvo o reinició mientras tanto."""
        state = store.get_state(self.db, conversation_id)
        if state.sla_started_at is None or state.sla_stopped_at is not None:
            return None
        return state

    async def _check_one(self, conversation_id: int, now: float) -> None:
        state = self._running(conversation_id)
        if state is None:
            return
        elapsed = now - state.sla_started_at
        channel = self._channel(conversation_id)
        if elapsed >= self.settings.sla_red_s:
            # Si el worker se atrasó y nunca marcó el ámbar, la etiqueta se pone junto con la roja
            missed_amber = [] if state.sla_amber_done else ["sla-ambar"]
            await channel.add_labels(conversation_id, [*missed_amber, "sla-vencido"])
            if self._running(conversation_id) is None:
                return
            await channel.send_message(
                conversation_id,
                f"SLA vencido: pasaron {int(elapsed)} s sin respuesta humana pertinente "
                f"(meta {self.settings.sla_red_s} s).", private=True)
            # El incumplimiento queda registrado, no solo etiquetado: la medición lo puede recalcular.
            with store.transaction(self.db):
                store.mark_sla(self.db, conversation_id, red=True)
                store.mark_request_breached(self.db, conversation_id, now)
                record_event(self.db, conversation_id, "sla_breached", now, {"elapsed_s": int(elapsed)})
        elif elapsed >= self.settings.sla_amber_s and not state.sla_amber_done:
            await channel.add_labels(conversation_id, ["sla-ambar"])
            store.mark_sla(self.db, conversation_id, amber=True)

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Falla en el ciclo del worker SLA")
            await asyncio.sleep(self.settings.sla_interval_s)
