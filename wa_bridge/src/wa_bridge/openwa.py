"""Cliente mínimo de OpenWA (gateway no oficial de WhatsApp Web) y verificación de sus webhooks."""

from __future__ import annotations

import hashlib
import hmac
from urllib.parse import quote

import httpx


class OpenWAError(Exception):
    pass


def verify_openwa_signature(secret: str, raw_body: bytes, header: str) -> bool:
    """HMAC-SHA256 del cuerpo, header `X-OpenWA-Signature: sha256=<hex>`. Sin secreto, rechaza todo."""
    if not secret or not header:
        return False
    given = header.strip().lower().removeprefix("sha256=")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), given.encode())


def to_chat_id(target: str) -> str:
    """Valida que el destino sea un chatId de WhatsApp (`...@c.us` / `...@lid`)."""
    target = target.strip()
    if not target.endswith(("@c.us", "@lid")):
        raise ValueError("Destino de WhatsApp inválido")
    return target


class OpenWAClient:
    def __init__(self, base_url: str, api_key: str, http: httpx.AsyncClient | None = None,
                 session_name: str = "default"):
        self.base_url = base_url.rstrip("/")
        self.session_name = session_name
        self._headers = {"X-API-Key": api_key} if api_key else {}
        self._http = http or httpx.AsyncClient(timeout=30.0)
        self._session_id: str | None = None
        self._known_ids: set[str] = {session_name}

    async def _list_sessions(self) -> list[dict]:
        response = await self._http.get(f"{self.base_url}/api/sessions", headers=self._headers)
        response.raise_for_status()
        return [s for s in response.json() if s.get("name") == self.session_name]

    async def _session(self) -> str:
        """Id de la sesión configurada, solo si está lista: otra cuenta vinculada jamás responde por ella."""
        if self._session_id is not None:
            return self._session_id
        for session in await self._list_sessions():
            if session.get("status") in ("ready", "active"):
                self._session_id = str(session["id"])
                return self._session_id
        raise OpenWAError(f"La sesión '{self.session_name}' de OpenWA no está lista: escanea el QR (make wa-qr)")

    async def allowed_session_ids(self) -> set[str]:
        """Identificadores (nombre e id) con que OpenWA puede etiquetar los eventos de la sesión configurada."""
        try:
            self._known_ids.update(str(s["id"]) for s in await self._list_sessions())
        except (httpx.HTTPError, ValueError):
            pass  # una falla pasajera del listado no debe descartar eventos de un id ya conocido
        return set(self._known_ids)

    async def resolve_lid(self, contact_id: str) -> str | None:
        """Mapea un `@lid` (identificador de privacidad) a su número real. Mejor esfuerzo."""
        try:
            session = await self._session()
            url = f"{self.base_url}/api/sessions/{session}/contacts/{quote(contact_id, safe='')}/phone"
            response = await self._http.get(url, headers=self._headers)
            response.raise_for_status()
            phone = response.json().get("phone")
            return f"{phone}@c.us" if phone else None
        except (httpx.HTTPError, OpenWAError, ValueError):
            return None

    async def send_text(self, target: str, text: str) -> None:
        chat_id = to_chat_id(target)
        if chat_id.endswith("@lid"):
            chat_id = await self.resolve_lid(chat_id) or chat_id
        session = await self._session()
        response = await self._http.post(f"{self.base_url}/api/sessions/{session}/messages/send-text",
                                         headers=self._headers, json={"chatId": chat_id, "text": text})
        if response.status_code == 404:
            self._session_id = None  # la sesión pudo reiniciarse con otro id
        response.raise_for_status()
