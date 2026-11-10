"""Escribe el config.js del sitio publicado.

Tres cosas se deciden aquí, según el entorno del build (las variables del proyecto de Vercel):

- `staticDemo`: `true` cuando no hay backend y las respuestas las simula `static-demo.js` en el
  navegador; `false` cuando `COPILOTO_URL` está definido y todo `/api/*` viaja al copiloto real.
- `aiChat`: `true` si hay `LLM_API_KEY`, así el chat pide sus respuestas a la función `api/demo/chat`
  (DeepSeek) en vez de usar el guion.
La voz de ElevenLabs no se decide aquí: el frontend de /demo hoy no tiene pantalla de llamada, así
que su función (`/api/demo/voice`) vive en el backend completo, no en el sitio estático.

Uso: write-static-config.py <salida> [url-del-backend]
"""
import os
import pathlib
import sys


def ai_chat_enabled() -> bool:
    """La IA del chat se activa con la clave del modelo en el entorno del build."""
    return bool(os.environ.get("LLM_API_KEY", "").strip())


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: write-static-config.py <salida> [url-del-backend]", file=sys.stderr)
        return 2
    out = pathlib.Path(sys.argv[1])
    backend = (sys.argv[2] if len(sys.argv) > 2 else "").strip()
    chat = ai_chat_enabled()
    truth = lambda value: "true" if value else "false"  # noqa: E731
    config = "".join([
        "window.COPILOTO_CONFIG = {\n",
        '  chatwootUrl: "",\n',
        '  copilotoUrl: "",\n',
        '  pmsUrl: "",\n',
        '  websiteToken: "",\n',
        '  privacyUrl: "",\n',
        f"  staticDemo: {truth(not backend)},\n",
        f"  aiChat: {truth(chat)},\n",
        "};\n",
    ])
    (out / "config.js").write_text(config, encoding="utf-8", newline=chr(10))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
