"""Cliente de Chatwoot para el inbox de tipo API.

Los mensajes del huésped entran por la API pública de cliente (inbox identifier): así llegan como
`incoming` con un contacto como remitente y el AgentBot los recibe igual que los del widget. El puente
nunca publica mensajes `outgoing`: el SLA solo se detiene con la respuesta de una persona.
"""

from __future__ import annotations

import httpx


class ChatwootClient:
    def __init__(self, base_url: str, inbox_identifier: str, account_id: int, admin_token: str,
                 http: httpx.AsyncClient | None = None):
        self._public = f"{base_url.rstrip('/')}/public/api/v1/inboxes/{inbox_identifier}"
        self._account = f"{base_url.rstrip('/')}/api/v1/accounts/{account_id}"
        self._admin_headers = {"api_access_token": admin_token}
        self._http = http or httpx.AsyncClient(timeout=10.0)

    async def create_contact(self, chat_id: str, name: str) -> str:
        response = await self._http.post(f"{self._public}/contacts", json={"identifier": chat_id, "name": name})
        response.raise_for_status()
        return str(response.json()["source_id"])

    async def create_conversation(self, source_id: str) -> int:
        response = await self._http.post(f"{self._public}/contacts/{source_id}/conversations", json={})
        response.raise_for_status()
        return int(response.json()["id"])

    async def post_guest_message(self, source_id: str, conversation_id: int, content: str) -> None:
        response = await self._http.post(
            f"{self._public}/contacts/{source_id}/conversations/{conversation_id}/messages",
            json={"content": content})
        response.raise_for_status()

    async def conversation_status(self, conversation_id: int) -> str | None:
        """Estado actual de la conversación, o None si ya no existe."""
        response = await self._http.get(f"{self._account}/conversations/{conversation_id}",
                                        headers=self._admin_headers)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json().get("status")
