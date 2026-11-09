"""Genera la página de privacidad estática que se sirve en el build sin backend.

`privacy.render` es la única fuente del texto legal: la vista dinámica del copiloto y el archivo
commiteado `landing/privacidad.html` salen del mismo lugar. La página se guarda con el marcador
`__PUBLIC_SITE_URL__` en los enlaces, igual que el resto de las páginas, para que el build lo
reemplace por la URL pública.

Uso:
    python scripts/render-privacy.py            # escribe landing/privacidad.html
    python scripts/render-privacy.py --check    # falla si el archivo no coincide con el render
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "copiloto" / "src"))

from copiloto.hotel import HotelData  # noqa: E402
from copiloto.privacy import render  # noqa: E402

TARGET = ROOT / "landing" / "privacidad.html"
MARKER = "__PUBLIC_SITE_URL__"


def page() -> str:
    hotel = HotelData.load(ROOT / "data" / "hotel.yaml")
    return render(hotel, home_url=MARKER)


def main() -> int:
    fresh = page()
    if "--check" in sys.argv[1:]:
        if not TARGET.is_file():
            print(f"Falta {TARGET.relative_to(ROOT)}: corre python scripts/render-privacy.py", file=sys.stderr)
            return 1
        if TARGET.read_text(encoding="utf-8") != fresh:
            print(f"{TARGET.relative_to(ROOT)} quedó viejo: corre python scripts/render-privacy.py", file=sys.stderr)
            return 1
        print("privacidad.html al día")
        return 0
    TARGET.write_text(fresh, encoding="utf-8", newline=chr(10))
    print(TARGET.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
