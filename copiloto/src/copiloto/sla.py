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
                 clock: Callable[[], float]):
        self.settings = settings
        self.db = db
        self.chatwoot = chatwoot
        self.clock = clock

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
            state = store.get_state(self.db, conversation_id)
            elapsed = now - state.sla_started_at
            try:
                if elapsed >= self.settings.sla_red_s:
                    await self.chatwoot.add_labels(conversation_id, ["sla-vencido"])
                    await self.chatwoot.send_message(
                        conversation_id,
                        f"SLA vencido: pasaron {int(elapsed)} s sin respuesta humana "
                        f"(meta {self.settings.sla_red_s} s).", private=True)
                    store.mark_sla(self.db, conversation_id, red=True)
                elif elapsed >= self.settings.sla_amber_s and not state.sla_amber_done:
                    await self.chatwoot.add_labels(conversation_id, ["sla-ambar"])
                    store.mark_sla(self.db, conversation_id, amber=True)
            except Exception:
                logger.exception("No se pudo actualizar el SLA de la conversación %s", conversation_id)

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Falla en el ciclo del worker SLA")
            await asyncio.sleep(self.settings.sla_interval_s)
