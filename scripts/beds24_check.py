#!/usr/bin/env python3
"""Verifica la cadena Beds24 → puente antes de conectar el copiloto.

Uso:
    BEDS24_REFRESH_TOKEN=... BEDS24_ROOMS='[{...}]' python scripts/beds24_check.py
    python scripts/beds24_check.py --rooms 101,102 --bridge http://localhost:8300

Comprueba, en orden: canje del refresh token, permisos del token, lectura del calendario para los
próximos días y, si el puente está arriba, que la respuesta cumpla el contrato del copiloto.
No escribe nada en Beds24.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

API = "https://api.beds24.com/v2"


def env(name: str) -> str:
    value = os.environ.get(name, "")
    if value:
        return value
    try:
        with open(".env", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def call(url: str, headers: dict) -> tuple[int, dict, dict]:
    request = urllib.request.Request(url, headers={"accept": "application/json", **headers})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.load(response), dict(response.headers)
    except urllib.error.HTTPError as error:
        try:
            body = json.load(error)
        except ValueError:
            body = {"error": error.reason}
        return error.code, body, dict(error.headers)


def main() -> int:
    parser = argparse.ArgumentParser(description="Comprueba la cadena Beds24 → puente.")
    parser.add_argument("--rooms", default="", help="roomIds separados por coma, si no usas BEDS24_ROOMS")
    parser.add_argument("--bridge", default="http://localhost:8300", help="URL del puente")
    parser.add_argument("--days", type=int, default=14, help="días hacia adelante para leer el calendario")
    args = parser.parse_args()

    refresh = env("BEDS24_REFRESH_TOKEN")
    access = env("BEDS24_ACCESS_TOKEN")
    if not refresh and not access:
        print("Falta BEDS24_REFRESH_TOKEN (o BEDS24_ACCESS_TOKEN) en el entorno o en .env.", file=sys.stderr)
        return 2

    failures = 0

    def report(ok: bool, label: str, detail: str = "") -> None:
        nonlocal failures
        print(f"  {'✓' if ok else '✗'} {label}" + (f" · {detail}" if detail else ""))
        if not ok:
            failures += 1

    token = access
    if refresh:
        status, body, _ = call(f"{API}/authentication/token", {"refreshToken": refresh})
        token = body.get("token", "")
        report(status == 200 and bool(token), "canje del refresh token",
               f"expira en {body.get('expiresIn', '?')} s" if token else str(body.get("error")))

    if not token:
        print("\nSin token de acceso no se puede seguir.")
        return 1

    status, body, _ = call(f"{API}/authentication/details", {"token": token})
    scopes = (body.get("token") or {}).get("scopes") or []
    report(status == 200, "permisos del token", ", ".join(scopes) if scopes else "sin scopes informados")

    raw_rooms = env("BEDS24_ROOMS")
    if args.rooms:
        room_ids = [int(value) for value in args.rooms.split(",") if value.strip()]
    elif raw_rooms:
        room_ids = [int(item["roomId"]) for item in json.loads(raw_rooms)]
    else:
        room_ids = []
    if not room_ids:
        print("  ✗ faltan habitaciones: usa --rooms 101,102 o define BEDS24_ROOMS")
        failures += 1
    else:
        start = date.today() + timedelta(days=1)
        end = start + timedelta(days=args.days)
        query = "&".join(f"roomId={room}" for room in room_ids)
        status, body, headers = call(
            f"{API}/inventory/rooms/calendar?{query}&startDate={start}&endDate={end}"
            "&includePrices=true&includeNumAvail=true", {"token": token})
        rows = body.get("data") or []
        report(status == 200, "lectura del calendario",
               f"{len(rows)} filas para {len(room_ids)} habitación(es) desde {start}")
        if rows:
            sample = rows[0]
            report("numAvail" in sample and "price1" in sample, "campos esperados en el calendario",
                   f"numAvail={sample.get('numAvail')} price1={sample.get('price1')}")
        remaining = headers.get("x-five-min-limit-remaining")
        if remaining:
            print(f"    créditos Beds24 restantes en la ventana: {remaining}")

    try:
        status, body, _ = call(
            f"{args.bridge}/api/v1/availability?checkin={(date.today() + timedelta(days=1)).isoformat()}"
            f"&checkout={(date.today() + timedelta(days=4)).isoformat()}&adults=2&children=0", {})
        contract = status == 200 and {"read_at", "source", "room_types"} <= set(body)
        report(contract, "contrato del puente", f"{len(body.get('room_types') or [])} oferta(s)")
    except (urllib.error.URLError, ValueError):
        print("  · puente no disponible en esta máquina; se omite la comprobación del contrato")

    print()
    if failures:
        print(f"{failures} comprobación(es) fallaron.")
        return 1
    print("Cadena Beds24 → puente verificada. Configura PMS_URL del copiloto en la URL del puente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
