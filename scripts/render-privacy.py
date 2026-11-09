"""Escribe la página de privacidad como HTML estático para el build sin backend.

`privacy.render` es la única fuente del texto legal: la vista dinámica del copiloto y la copia
estática salen del mismo lugar. Sin proveedor de IA, el aviso declara el modo guiado.

Uso (lo llama `scripts/build-static-demo.sh`):
    python scripts/render-privacy.py <salida> <home_url>
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "copiloto" / "src"))

from copiloto.hotel import HotelData  # noqa: E402
from copiloto.privacy import render  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print("Uso: render-privacy.py <salida> <home_url>", file=sys.stderr)
        return 2
    out = pathlib.Path(sys.argv[1])
    home = sys.argv[2]
    page = render(HotelData.load(ROOT / "data" / "hotel.yaml"), home_url=home)
    target = out / "privacidad.html"
    target.write_text(page, encoding="utf-8", newline="\n")
    print(target.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
