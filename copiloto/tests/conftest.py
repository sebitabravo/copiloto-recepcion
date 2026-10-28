import itertools
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from copiloto.config import Settings
from copiloto.events import connect, init_db
from copiloto.flow import Copiloto
from copiloto.hotel import HotelData
from copiloto.pms import PmsAdapter, PmsReading, PmsUnavailable, RoomOffer

HOTEL_PATH = Path(__file__).resolve().parents[2] / "data" / "hotel.yaml"
TZ = ZoneInfo("America/Santiago")


def local_epoch(year, month, day, hour, minute=0, second=0) -> float:
    return datetime(year, month, day, hour, minute, second, tzinfo=TZ).timestamp()


class FakeClock:
    def __init__(self, start: float):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeChatwoot:
    """Registra lo que el copiloto enviaría a Chatwoot."""

    def __init__(self):
        self.messages: list[dict] = []
        self.labels: dict[int, set[str]] = {}
        self.assigned: list[int] = []
        self.statuses: dict[int, str] = {}
        self.during: dict[str, object] = {}

    async def send_message(self, conversation_id, content, private=False):
        self.messages.append({"conversation_id": conversation_id, "content": content, "private": private,
                              "options": None})

    async def send_select(self, conversation_id, content, options):
        self.messages.append({"conversation_id": conversation_id, "content": content, "private": False,
                              "options": options})

    async def add_labels(self, conversation_id, labels):
        self.labels.setdefault(conversation_id, set()).update(labels)
        if "add_labels" in self.during:
            self.during.pop("add_labels")()

    async def assign_team(self, conversation_id):
        self.assigned.append(conversation_id)

    async def set_status(self, conversation_id, status):
        self.statuses[conversation_id] = status
        if "set_status" in self.during:
            self.during.pop("set_status")()

    def guest_texts(self, conversation_id=None) -> list[str]:
        return [m["content"] for m in self.messages
                if not m["private"] and (conversation_id is None or m["conversation_id"] == conversation_id)]

    def notes(self, conversation_id=None) -> list[str]:
        return [m["content"] for m in self.messages
                if m["private"] and (conversation_id is None or m["conversation_id"] == conversation_id)]


class FakePms(PmsAdapter):
    def __init__(self):
        self.calls = 0
        self.bookings: list[dict] = []
        self.book_error: Exception | None = None
        self.down = False
        self.offers = [
            RoomOffer("doble_con_jacuzzi", "Habitación Doble con Jacuzzi", 2, 1, 32, 2, 85000),
            RoomOffer("doble_sin_vista", "Habitación Doble Sin Vista", 2, 1, 12, 1, 70000),
        ]

    async def availability(self, checkin: date, checkout: date, adults: int, children: int) -> PmsReading:
        self.calls += 1
        if self.down:
            raise PmsUnavailable("simulado")
        return PmsReading("2026-10-28T15:00:00-03:00", "pms-mock", True, list(self.offers))


async def _fake_book(self, guest_name, room_code, checkin, checkout, adults, children, conversation_id):
    if self.book_error:
        raise self.book_error
    booking = {"booking_id": 7 + len(self.bookings), "guest_name": guest_name, "room_code": room_code,
               "checkin": checkin.isoformat(), "checkout": checkout.isoformat(), "adults": adults,
               "children": children, "conversation_id": conversation_id}
    self.bookings.append(booking)
    return booking


FakePms.book = _fake_book


class Harness:
    def __init__(self, settings, hotel, db, chatwoot, pms, clock, agent=None):
        self.settings, self.hotel, self.db = settings, hotel, db
        self.chatwoot, self.pms, self.clock = chatwoot, pms, clock
        self.core = Copiloto(settings, hotel, db, chatwoot, pms, clock, agent)
        self._ids = itertools.count(1)

    def payload(self, text, conversation_id=1, status="pending", message_type="incoming", sender_type="contact",
                private=False, name="Huésped Demo", channel="Channel::WebWidget", message_id=None):
        return {
            "event": "message_created", "id": message_id or next(self._ids), "content": text,
            "message_type": message_type, "private": private,
            "sender": {"id": 9, "name": name, "type": sender_type},
            "conversation": {"id": conversation_id, "status": status, "channel": channel},
        }

    async def say(self, text, **kwargs):
        await self.core.handle_webhook(self.payload(text, **kwargs))

    def events(self, kind=None, conversation_id=None) -> list:
        sql, params = "SELECT * FROM events WHERE 1=1", []
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if conversation_id:
            sql += " AND conversation_id = ?"
            params.append(conversation_id)
        return self.db.execute(sql + " ORDER BY id", params).fetchall()


@pytest.fixture
def clock():
    return FakeClock(local_epoch(2026, 10, 28, 15, 0))


@pytest.fixture
def settings():
    return Settings(hotel_data_path=str(HOTEL_PATH), db_path=":memory:", webhook_secret="s3cret",
                    pms_events_secret="pms-secret", panel_token="panel-secret", chatwoot_team_id=1,
                    public_url="http://localhost:8100")


@pytest.fixture
def harness(settings, clock):
    db = connect(":memory:")
    init_db(db)
    return Harness(settings, HotelData.load(settings.hotel_data_path), db, FakeChatwoot(), FakePms(), clock)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def pytest_collection_modifyitems(items):
    # Las pruebas async corren con el plugin anyio que ya trae starlette (sin dependencias nuevas)
    for item in items:
        if item.get_closest_marker("anyio") is None and getattr(item.function, "__code__", None) \
                and item.function.__code__.co_flags & 0x80:
            item.add_marker(pytest.mark.anyio)


class FakeLlm:
    """LLM guionado: devuelve respuestas predefinidas y registra lo que se le envió."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []

    async def chat(self, messages, tools=None, max_tokens=500, temperature=0.3):
        import copy
        self.calls.append({"messages": copy.deepcopy(messages),
                           "tools": [t["function"]["name"] for t in tools or []]})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def say(text, tokens=100):
    from copiloto.ai.llm import LlmReply
    return LlmReply(text, [], tokens, {"role": "assistant", "content": text})


def call(name, call_id="c1", **arguments):
    import json

    from copiloto.ai.llm import LlmReply, ToolCall
    raw = json.dumps(arguments)
    tool = ToolCall(call_id, name, raw)
    message = {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": raw}}]}
    return LlmReply(None, [tool], 50, message)


@pytest.fixture
def ai_settings(settings):
    return replace(settings, ai_mode="full", llm_api_key="k" * 20, pms_staff_token="t" * 20)


@pytest.fixture
def make_ai(ai_settings, clock):
    """Fábrica: build(script) -> (Harness con agente guionado, FakeLlm)."""
    from copiloto.ai.agent import Agent

    def build(script, settings=None):
        settings = settings or ai_settings
        db = connect(":memory:")
        init_db(db)
        hotel = HotelData.load(settings.hotel_data_path)
        pms = FakePms()
        llm = FakeLlm(script)
        agent = Agent(llm, hotel, pms, settings, clock)
        return Harness(settings, hotel, db, FakeChatwoot(), pms, clock, agent), llm

    return build
