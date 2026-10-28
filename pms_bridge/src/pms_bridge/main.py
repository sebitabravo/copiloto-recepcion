"""Puente Beds24 → contrato del copiloto.

Expone `GET /api/v1/availability` con el contrato de docs/conector-pms.md y traduce las filas por día
de Beds24 a ofertas por habitación. No escribe reservas: la confirmación es humana, en Beds24.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from .beds24 import DEFAULT_API, Beds24Client, Beds24Error, parse_rooms, read_at, stay_offers


def create_app(client=None, rooms=None, timezone_name: str | None = None,
               clp_rate: float | None = None) -> FastAPI:
    app = FastAPI(title="Puente de PMS · Beds24")

    def config():
        zone = timezone_name or os.environ.get("BEDS24_TZ", "America/Santiago")
        rate = clp_rate if clp_rate is not None else float(os.environ.get("BEDS24_CLP_RATE", "1"))
        room_list = rooms if rooms is not None else parse_rooms(os.environ.get("BEDS24_ROOMS", ""))
        connector = client or Beds24Client(
            access_token=os.environ.get("BEDS24_ACCESS_TOKEN", ""),
            refresh_token=os.environ.get("BEDS24_REFRESH_TOKEN", ""),
            base_url=os.environ.get("BEDS24_API_URL", DEFAULT_API))
        return zone, rate, room_list, connector

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/api/v1/availability")
    async def availability(checkin: date = Query(...), checkout: date = Query(...),
                           adults: int = Query(ge=1, le=10), children: int = Query(ge=0, le=10)):
        if checkout <= checkin:
            raise HTTPException(status_code=422, detail="La salida debe ser posterior a la entrada")
        try:
            zone, rate, room_list, connector = config()
        except (Beds24Error, ValueError) as error:
            return JSONResponse({"detail": str(error)}, status_code=503)
        candidates = [room for room in room_list
                      if room.max_adults >= adults and room.max_children >= children]
        days = []
        if candidates:
            try:
                days = await connector.calendar([room.room_id for room in candidates], checkin, checkout)
            except Beds24Error as error:
                return JSONResponse({"detail": str(error)}, status_code=502)
        return {"read_at": read_at(datetime.now(timezone.utc), zone), "source": "beds24", "simulated": False,
                "room_types": stay_offers(candidates, days, checkin, checkout, clp_rate=rate)}

    @app.post("/api/v1/bookings")
    async def bookings():
        raise HTTPException(status_code=501,
                            detail="El puente no escribe reservas: recepción confirma en Beds24")

    return app


app = create_app()
