"""Escribe el config.js del sitio publicado.

Dos cosas se deciden con el entorno del build (las variables del proyecto de Vercel):

- `aiChat`: hay `LLM_API_KEY`, así el chat pide sus respuestas a la función `api/demo/chat` (DeepSeek)
  en vez de usar el guion del navegador.
- `voice`: hay `ELEVENLABS_API_KEY` y `ELEVENLABS_VOICE_ID`, así la llamada usa `api/demo/tts`
  (ElevenLabs) en vez de la voz del navegador.

`staticDemo` queda siempre en `true`: la página no necesita backend propio, el estado de la demo
(conversación, bandeja, cronómetro) vive en el navegador y solo la conversación viaja a la función.

Uso: write-static-config.py <salida>
"""
import os
import pathlib
import sys


def truth(value: bool) -> str:
    return "true" if value else "false"


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: write-static-config.py <salida>", file=sys.stderr)
        return 2
    out = pathlib.Path(sys.argv[1])
    chat = bool(os.environ.get("LLM_API_KEY", "").strip())
    voice = bool(os.environ.get("ELEVENLABS_API_KEY", "").strip()
                 and os.environ.get("ELEVENLABS_VOICE_ID", "").strip())
    config = "".join([
        "window.COPILOTO_CONFIG = {\n",
        '  chatwootUrl: "",\n',
        '  copilotoUrl: "",\n',
        '  pmsUrl: "",\n',
        '  websiteToken: "",\n',
        '  privacyUrl: "",\n',
        "  staticDemo: true,\n",
        f"  aiChat: {truth(chat)},\n",
        f"  voice: {truth(voice)},\n",
        "};\n",
    ])
    (out / "config.js").write_text(config, encoding="utf-8", newline=chr(10))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
