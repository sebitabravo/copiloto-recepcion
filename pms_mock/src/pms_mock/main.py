import hmac
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager, closing
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Self
from zoneinfo import ZoneInfo

import httpx
import yaml
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

logger = logging.getLogger(__name__)
DEFAULT_HOTEL_PATH = Path(__file__).resolve().parents[3] / "data" / "hotel.yaml"


class RoomType(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    max_adults: int = Field(ge=1)
    max_children: int = Field(ge=0)
    m2: float = Field(gt=0)


def load_rooms(path: Path) -> list[RoomType]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(f"Cannot load hotel data from {path}: {exc}") from exc
    if not isinstance(data, dict) or "rooms" not in data:
        raise RuntimeError(f"Hotel data {path} is missing required key 'rooms'")
    if not isinstance(data["rooms"], list) or len(data["rooms"]) != 12:
        raise RuntimeError(f"Hotel data {path}: 'rooms' must contain exactly 12 room types")
    try:
        rooms = [RoomType.model_validate(room) for room in data["rooms"]]
    except ValidationError as exc:
        raise RuntimeError(f"Invalid room type in hotel data {path}: {exc}") from exc
    if len({room.code for room in rooms}) != len(rooms):
        raise RuntimeError(f"Hotel data {path} contains duplicate room codes")
    return rooms


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=15, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize(path: str, rooms: list[RoomType]) -> None:
    with closing(connect(path)) as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS rooms (
                room_id INTEGER PRIMARY KEY,
                room_code TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_name TEXT NOT NULL,
                checkin TEXT NOT NULL,
                checkout TEXT NOT NULL CHECK (checkout > checkin),
                room_code TEXT NOT NULL,
                adults INTEGER NOT NULL CHECK (adults > 0),
                children INTEGER NOT NULL CHECK (children >= 0),
                conversation_id INTEGER,
                simulated INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS booking_dates
                ON bookings(room_code, checkin, checkout);
        """)
        # Distribución simulada: dos unidades para los primeros ocho tipos del YAML.
        expected = [room.code for index, room in enumerate(rooms)
                    for _ in range(2 if index < 8 else 1)]
        connection.execute("BEGIN IMMEDIATE")
        try:
            current = connection.execute("SELECT room_code FROM rooms ORDER BY room_id").fetchall()
            if not current:
                connection.executemany(
                    "INSERT INTO rooms(room_id, room_code) VALUES (?, ?)",
                    enumerate(expected, start=1),
                )
            elif [row["room_code"] for row in current] != expected:
                raise RuntimeError("Existing database inventory differs from hotel data; use a new PMS_DB_PATH")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def available_units(connection: sqlite3.Connection, code: str, checkin: date, checkout: date) -> int:
    units = connection.execute("SELECT COUNT(*) FROM rooms WHERE room_code = ?", (code,)).fetchone()[0]
    bookings = connection.execute(
        "SELECT checkin, checkout FROM bookings WHERE room_code = ? AND checkin < ? AND checkout > ?",
        (code, checkout.isoformat(), checkin.isoformat()),
    ).fetchall()
    # Intervalos semiabiertos: una salida libera cupo el mismo día; medir el pico,
    # no sumar reservas de noches diferentes dentro de una estancia larga.
    events: dict[str, int] = {}
    for booking in bookings:
        start = max(booking["checkin"], checkin.isoformat())
        end = min(booking["checkout"], checkout.isoformat())
        events[start] = events.get(start, 0) + 1
        events[end] = events.get(end, 0) - 1
    occupied = peak = 0
    for day in sorted(events):
        occupied += events[day]
        peak = max(peak, occupied)
    return max(0, units - peak)


class Stay(BaseModel):
    checkin: date
    checkout: date
    adults: int = Field(ge=1)
    children: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_dates(self) -> Self:
        if self.checkout <= self.checkin:
            raise ValueError("checkout must be after checkin")
        return self


class BookingRequest(Stay):
    guest_name: str = Field(min_length=1, max_length=200)
    room_code: str = Field(min_length=1)
    conversation_id: int | None = None

    @field_validator("guest_name")
    @classmethod
    def validate_guest(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("guest_name must not be blank")
        return value.strip()


def require_staff(x_staff_token: Annotated[str | None, Header()] = None) -> None:
    expected = os.getenv("STAFF_TOKEN")
    if not expected or not x_staff_token or not hmac.compare_digest(
        x_staff_token.encode(), expected.encode()
    ):
        raise HTTPException(status_code=401, detail="Valid staff token required")


def emit_event(url: str, event: dict) -> None:
    # Tres reintentos después del primer intento; nunca propagar fallos al huésped.
    for attempt in range(4):
        try:
            headers = {}
            if os.getenv("COPILOTO_EVENTS_TOKEN"):
                # Secreto por header: así no queda en los access logs del receptor
                headers["X-Events-Token"] = os.environ["COPILOTO_EVENTS_TOKEN"]
            with httpx.Client(timeout=2.0, follow_redirects=False) as client:
                response = client.post(url, json=event, headers=headers)
                response.raise_for_status()
            return
        except Exception:
            if attempt < 3:
                time.sleep(0.05 * (2 ** attempt))
    logger.warning("Booking event delivery failed after retries")


def create_app() -> FastAPI:
    rooms = load_rooms(Path(os.getenv("HOTEL_DATA_PATH", str(DEFAULT_HOTEL_PATH))))
    database_path = os.getenv("PMS_DB_PATH", "./pms.sqlite")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        initialize(database_path, rooms)
        yield

    application = FastAPI(title="Hotel Boutique Bordeluz PMS mock", lifespan=lifespan)
    application.state.database_path = database_path
    application.state.room_types = rooms

    @application.get("/health")
    def health():
        return {"status": "ok"}

    @application.get("/api/v1/room-types")
    def room_types():
        return [room.model_dump() for room in rooms]

    @application.get("/api/v1/availability")
    def availability(
        checkin: date, checkout: date,
        adults: Annotated[int, Query(ge=1)], children: Annotated[int, Query(ge=0)],
    ):
        if checkout <= checkin:
            raise HTTPException(status_code=422, detail="checkout must be after checkin")
        if os.getenv("SIMULATE_DOWN") == "1":
            raise HTTPException(status_code=503, detail="Simulated PMS outage")
        result = []
        with closing(connect(database_path)) as connection:
            # Una instantánea mantiene coherentes todos los tipos durante la lectura.
            connection.execute("BEGIN")
            for index, room in enumerate(rooms):
                if adults > room.max_adults or children > room.max_children:
                    continue
                units = available_units(connection, room.code, checkin, checkout)
                if units:
                    result.append({**room.model_dump(), "available_units": units,
                                   "nightly_price_clp": 65000 + index * 5000})
            connection.rollback()
        return {"read_at": datetime.now(ZoneInfo("America/Santiago")).isoformat(),
                "source": "pms-mock", "simulated": True, "room_types": result}

    @application.post("/api/v1/bookings", dependencies=[Depends(require_staff)], status_code=201)
    def book(payload: BookingRequest, background_tasks: BackgroundTasks):
        room = next((room for room in rooms if room.code == payload.room_code), None)
        if room is None:
            raise HTTPException(status_code=422, detail="Unknown room_code")
        if payload.adults > room.max_adults or payload.children > room.max_children:
            raise HTTPException(status_code=422, detail="Party exceeds room capacity")
        with closing(connect(database_path)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if available_units(connection, payload.room_code, payload.checkin, payload.checkout) < 1:
                    raise HTTPException(status_code=409, detail="No available units for these dates")
                cursor = connection.execute(
                    """INSERT INTO bookings(guest_name, checkin, checkout, room_code,
                       adults, children, conversation_id) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (payload.guest_name, payload.checkin.isoformat(), payload.checkout.isoformat(),
                     payload.room_code, payload.adults, payload.children, payload.conversation_id),
                )
                booking_id = cursor.lastrowid
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        event_url = os.getenv("COPILOTO_EVENTS_URL")
        if event_url:
            background_tasks.add_task(emit_event, event_url, {
                "kind": "booking_confirmed", "conversation_id": payload.conversation_id,
                "booking_id": booking_id,
            })
        return {"booking_id": booking_id, **payload.model_dump(), "simulated": True}

    @application.get("/api/v1/bookings", dependencies=[Depends(require_staff)])
    def list_bookings():
        with closing(connect(database_path)) as connection:
            rows = connection.execute("SELECT * FROM bookings ORDER BY booking_id").fetchall()
        return [{**dict(row), "simulated": bool(row["simulated"])} for row in rows]

    @application.get("/admin", response_class=HTMLResponse)
    def admin():
        return Path(__file__).with_name("admin.html").read_text(encoding="utf-8")

    return application


app = create_app()
