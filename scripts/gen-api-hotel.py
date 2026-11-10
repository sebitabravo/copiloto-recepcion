"""Genera `api/_hotel.json`: los datos aprobados del hotel que usa el asistente en Vercel.

El servicio `copiloto` lee `data/hotel.yaml` en tiempo de ejecución; una función de Vercel no puede
hacer eso (no viaja PyYAML ni el archivo), así que los hechos aprobados se publican como JSON junto
al código de la función. Este script es la única fuente: `copiloto/tests/test_api_hotel.py` falla si
el JSON commiteado deja de coincidir con `data/hotel.yaml`.

Uso:
    python scripts/gen-api-hotel.py            # escribe api/_hotel.json
    python scripts/gen-api-hotel.py --check    # falla si quedó desactualizado
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "copiloto" / "src"))

from copiloto.hotel import HotelData  # noqa: E402

TARGET = ROOT / "api" / "_hotel.json"


def payload() -> dict:
    hotel = HotelData.load(ROOT / "data" / "hotel.yaml")
    return {
        "name": hotel.hotel["name"],
        "location": hotel.location,
        "policies": hotel.policies,
        "faqs": [{"id": faq.id, "label": faq.label, "answer": faq.answer, "source": faq.source,
                  "status": faq.status} for faq in hotel.faqs],
        "rooms": [{"code": room.get("code"), "name": room.get("name"),
                   "max_adults": room.get("max_adults"), "max_children": room.get("max_children"),
                   "m2": room.get("m2")} for room in hotel.rooms],
    }


def render() -> str:
    return json.dumps(payload(), ensure_ascii=False, indent=2, sort_keys=True, default=str) + chr(10)


def main() -> int:
    fresh = render()
    if "--check" in sys.argv[1:]:
        if not TARGET.is_file():
            print(f"Falta {TARGET.relative_to(ROOT)}: corre python scripts/gen-api-hotel.py", file=sys.stderr)
            return 1
        if TARGET.read_text(encoding="utf-8") != fresh:
            print(f"{TARGET.relative_to(ROOT)} quedó viejo: corre python scripts/gen-api-hotel.py", file=sys.stderr)
            return 1
        print("api/_hotel.json al día")
        return 0
    TARGET.write_text(fresh, encoding="utf-8", newline=chr(10))
    print(TARGET.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
