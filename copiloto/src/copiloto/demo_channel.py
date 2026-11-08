"""Canal de la demo: la misma interfaz que el cliente de Chatwoot, sobre la transcripción aislada.

El motor guiado (`flow.Copiloto`) no sabe si habla con Chatwoot o con la demo: escribe por este canal y
todo queda en `demo_messages` del hilo, que es lo que leen el chat del huésped y la bandeja de recepción.
Así hay una sola fuente de verdad para la conversación y la solicitud, y el recorrido completo se puede
probar sin Chatwoot ni credenciales.
"""

import sqlite3
from collections.abc import Callable

from copiloto import store


class DemoChannel:
    def __init__(self, db: sqlite3.Connection, clock: Callable[[], float]):
        self.db = db
        self.clock = clock

    async def send_message(self, conversation_id: int, content: str, private: bool = False) -> None:
        # Una nota privada (pre-información, aviso de SLA) solo la lee recepción.
        store.add_demo_message(self.db, conversation_id, "note" if private else "assistant", content, self.clock())

    async def send_select(self, conversation_id: int, content: str, options: list[tuple[str, str]]) -> None:
        store.add_demo_message(
            self.db, conversation_id, "assistant", content, self.clock(), options=[title for title, _ in options]
        )

    async def add_labels(self, conversation_id: int, labels: list[str]) -> None:
        """Las etiquetas de Chatwoot (comercial, nocturna, sla-*) salen de la solicitud: no se duplican aquí."""

    async def assign_team(self, conversation_id: int) -> None:
        """En la demo la asignación es la acción «Tomar solicitud» de la bandeja."""

    async def set_status(self, conversation_id: int, status: str) -> None:
        """Abrir para personas = la solicitud abierta. Mientras exista, el bot no contesta ese hilo."""
