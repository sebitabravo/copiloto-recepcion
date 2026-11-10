"""Escribe el config.js del sitio publicado.

Dos modos:

- **Sin backend** (por defecto): `staticDemo: true`, y `static-demo.js` responde `/api/*` desde el
  navegador con los guiones preparados.
- **Con backend** (`COPILOTO_URL` definido): `staticDemo: false`; la página llama a `/api/*` del
  propio dominio, que el proxy `api/[...path].js` reenvía al copiloto real (IA y voz de verdad).

Uso: write-static-config.py <salida> [url-del-backend]
"""
import pathlib
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: write-static-config.py <salida> [url-del-backend]", file=sys.stderr)
        return 2
    out = pathlib.Path(sys.argv[1])
    backend = (sys.argv[2] if len(sys.argv) > 2 else "").strip()
    config = (
        "window.COPILOTO_CONFIG = {\n"
        '  chatwootUrl: "",\n'
        '  copilotoUrl: "",\n'
        '  pmsUrl: "",\n'
        '  websiteToken: "",\n'
        '  privacyUrl: "",\n'
        f'  staticDemo: {"false" if backend else "true"},\n'
        "};\n"
    )
    (out / "config.js").write_text(config, encoding="utf-8", newline=chr(10))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
