"""Cliente mínimo de un LLM con API compatible con OpenAI (DeepSeek por defecto, intercambiable por env).

No registra ni la API key ni el contenido de los mensajes: solo códigos de estado y duraciones.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


class LlmUnavailable(Exception):
    """El LLM no respondió o devolvió algo inutilizable; el asistente debe degradar al flujo guiado."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class LlmReply:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens: int | None = None
    message: dict = field(default_factory=dict)


class LlmClient:
    # El cliente declara si puede forzar una herramienta; los dobles de prueba no lo hacen.
    supports_tool_choice = True

    def __init__(self, base_url: str, api_key: str, model: str, timeout_s: float = 25.0,
                 http: httpx.AsyncClient | None = None, retries: int = 1):
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        self._model = model
        self._http = http or httpx.AsyncClient(timeout=timeout_s)
        self._retries = retries
        # DeepSeek razona por defecto: se apaga porque suma latencia y exige devolver el razonamiento
        # en cada turno de herramientas. Otros proveedores compatibles ignoran el campo.
        self._extra = {"thinking": {"type": "disabled"}} if "deepseek" in base_url else {}

    async def chat(self, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 500,
                   temperature: float = 0.3, tool_choice: str = "auto") -> LlmReply:
        body = {"model": self._model, "messages": messages, "max_tokens": max_tokens,
                "temperature": temperature, "stream": False, **self._extra}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice
        last_error = "sin intentos"
        for attempt in range(self._retries + 1):
            try:
                response = await self._http.post(self._url, json=body, headers=self._headers)
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
            else:
                if response.status_code == 200:
                    return self._parse(response)
                last_error = f"http {response.status_code}"
                if response.status_code not in (429, 500, 502, 503, 504):
                    break
            if attempt < self._retries:
                await asyncio.sleep(1.0)
        logger.warning("LLM no disponible: %s", last_error)
        raise LlmUnavailable(last_error)

    @staticmethod
    def _parse(response: httpx.Response) -> LlmReply:
        try:
            data = response.json()
            message = data["choices"][0]["message"]
            calls = [ToolCall(call["id"], call["function"]["name"], call["function"].get("arguments") or "{}")
                     for call in message.get("tool_calls") or []]
            usage = data.get("usage") or {}
            tokens = usage.get("total_tokens") if isinstance(usage.get("total_tokens"), int) else None
            clean = {"role": "assistant", "content": message.get("content")}
            if message.get("tool_calls"):
                clean["tool_calls"] = [{"id": c.id, "type": "function",
                                        "function": {"name": c.name, "arguments": c.arguments}} for c in calls]
            return LlmReply(message.get("content"), calls, tokens, clean)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LlmUnavailable(f"respuesta inválida: {type(exc).__name__}") from exc


def parse_arguments(raw: str) -> dict:
    """Los argumentos de una herramienta llegan como texto JSON que el modelo puede romper."""
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
