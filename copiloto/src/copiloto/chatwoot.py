"""Cliente mínimo de la API de Chatwoot. Todo sale con el token del AgentBot para que
los mensajes del bot no se confundan con una respuesta humana (el SLA solo se detiene con un User)."""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class ChatwootClient:
    def __init__(self, base_url: str, account_id: int, token: str, team_id: int | None = None,
                 http: httpx.AsyncClient | None = None):
        self.account_path = f"{base_url.rstrip('/')}/api/v1/accounts/{account_id}"
        self.team_id = team_id
        self._headers = {"api_access_token": token}
        self._http = http or httpx.AsyncClient(timeout=10.0)
        self._label_lock = asyncio.Lock()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = await self._http.request(method, f"{self.account_path}{path}", headers=self._headers,
                                            **kwargs)
        response.raise_for_status()
        return response

    async def send_message(self, conversation_id: int, content: str, private: bool = False) -> None:
        await self._request("POST", f"/conversations/{conversation_id}/messages",
                            json={"content": content, "message_type": "outgoing", "private": private})

    async def send_select(self, conversation_id: int, content: str, options: list[tuple[str, str]]) -> None:
        """Botones (input_select). `options` es una lista de (título, valor)."""
        items = [{"title": title, "value": value} for title, value in options]
        await self._request("POST", f"/conversations/{conversation_id}/messages", json={
            "content": content, "message_type": "outgoing", "content_type": "input_select",
            "content_attributes": {"items": items},
        })

    async def add_labels(self, conversation_id: int, labels: list[str]) -> None:
        # POST /labels reemplaza el conjunto completo, por eso se une con las etiquetas actuales
        async with self._label_lock:
            current = (await self._request("GET", f"/conversations/{conversation_id}/labels")).json()
            merged = sorted(set(current.get("payload", [])) | set(labels))
            await self._request("POST", f"/conversations/{conversation_id}/labels", json={"labels": merged})

    async def assign_team(self, conversation_id: int) -> None:
        if self.team_id is None:
            return
        await self._request("POST", f"/conversations/{conversation_id}/assignments",
                            json={"team_id": self.team_id})

    async def set_status(self, conversation_id: int, status: str) -> None:
        await self._request("POST", f"/conversations/{conversation_id}/toggle_status",
                            json={"status": status})

    async def aclose(self) -> None:
        await self._http.aclose()
