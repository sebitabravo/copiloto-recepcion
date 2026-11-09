"""La página de privacidad estática sale del mismo render que la vista dinámica.

Sin backend, `/privacidad` tiene que existir como archivo commiteado. Esta prueba impide que el
archivo se publique vacío, con enlaces locales, con otra retención o desactualizado respecto de
`privacy.render` (la fuente única del texto legal).
"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PAGE = ROOT / "landing" / "privacidad.html"
SCRIPT = ROOT / "scripts" / "render-privacy.py"


def test_the_committed_page_matches_the_render():
    result = subprocess.run([sys.executable, str(SCRIPT), "--check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def test_the_committed_page_is_publishable():
    page = PAGE.read_text(encoding="utf-8")
    assert "Aviso de privacidad" in page
    assert "comercial@hotelbordeluz.cl" in page, "el contacto del responsable no puede faltar"
    assert "90" in page, "la retención publicada es la que aplica la purga"
    assert "localhost" not in page, "la copia publicada no puede apuntar a la máquina local"
    assert page.count("__PUBLIC_SITE_URL__") >= 2, "los enlaces vuelven por el marcador del build"
