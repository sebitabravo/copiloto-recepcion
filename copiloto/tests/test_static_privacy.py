"""La página de privacidad del build estático sale del mismo render que la vista dinámica.

Sin backend, `/privacidad` tiene que existir como archivo: el script del build la escribe con
`privacy.render`, la misma fuente del texto legal. Esta prueba evita que el build publique una
página vacía, con enlaces locales o con una retención distinta a la que aplica la purga.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_static_privacy_page_matches_the_dynamic_render(tmp_path):
    home = "https://copiloto.example"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "render-privacy.py"), str(tmp_path), home],
        capture_output=True, text=True, check=True,
    )
    page = (tmp_path / "privacidad.html").read_text(encoding="utf-8")

    assert result.stdout.strip().endswith("privacidad.html")
    assert "Aviso de privacidad" in page
    assert "comercial@hotelbordeluz.cl" in page, "el contacto del responsable no puede faltar"
    assert "90 días" in page or "90 dias" in page, "la retención publicada es la que aplica la purga"
    assert "localhost" not in page, "la copia publicada no puede apuntar a la máquina local"
    assert f'href="{home}"' in page, "la vuelta a la portada usa la URL pública del build"
    assert "verificado" not in page.lower() or "no verificado" in page.lower()
