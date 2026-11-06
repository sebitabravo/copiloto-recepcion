#!/usr/bin/env python3
"""Ida y vuelta de la voz: respuestas del hotel → ElevenLabs → Whisper local → WER.

Mide qué tan bien se entiende la voz del copiloto. No mide naturalidad (eso requiere escucha humana).

Uso, desde copiloto/ (la clave se lee del entorno; nunca se imprime):
    uv run --with faster-whisper python ../scripts/voice_roundtrip.py --out <carpeta-fuera-del-repo>

Costo: una síntesis por respuesta del corpus (unos 800 caracteres en total con el corpus por defecto).
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx
from copiloto.hotel import HotelData
from copiloto.quality import normalize_words, word_error_rate
from copiloto.voice import greeting, speakable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VOICE = "EXAVITQu4vr4xnSDxMaL"  # Sarah: premade con español verificado en la API
DEFAULT_MODEL = "eleven_flash_v2_5"


def corpus(hotel: HotelData) -> list[tuple[str, str]]:
    """Textos que el copiloto dice de verdad. Sin cifras: el WER no debe medir el formato de los números."""
    items = [("saludo", greeting(hotel.hotel["name"]))]
    wanted = {"piscina", "desayuno", "estacionamiento", "wifi", "tinajas"}
    for faq in hotel.faqs:
        if faq.id in wanted and not any(char.isdigit() for char in faq.answer):
            items.append((faq.id, faq.answer))
    return [(name, speakable(text, 450)) for name, text in items]


def synthesize(api_key: str, voice: str, model: str, text: str, path: Path) -> None:
    if path.exists():
        return
    response = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}",
                          params={"output_format": "mp3_44100_64"},
                          headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                          json={"text": text, "model_id": model, "language_code": "es"}, timeout=60)
    if response.status_code != 200:
        raise SystemExit(f"ElevenLabs respondió {response.status_code}; no se gastó más crédito")
    path.write_bytes(response.content)


def transcribe(model, path: Path) -> str:
    segments, _ = model.transcribe(str(path), language="es", beam_size=5)
    return " ".join(segment.text.strip() for segment in segments)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="carpeta fuera del repo para audios y reporte")
    parser.add_argument("--whisper", default="small", help="tamaño del modelo Whisper (tiny, base, small...)")
    parser.add_argument("--voice", default=os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE))
    args = parser.parse_args()
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        raise SystemExit("Falta ELEVENLABS_API_KEY en el entorno")
    from faster_whisper import WhisperModel

    args.out.mkdir(parents=True, exist_ok=True)
    hotel = HotelData.load(ROOT / "data" / "hotel.yaml")
    items = corpus(hotel)
    whisper = WhisperModel(args.whisper, device="cpu", compute_type="int8")
    results, total_errors, total_words = [], 0.0, 0
    for name, text in items:
        audio = args.out / f"{name}.mp3"
        synthesize(api_key, args.voice, DEFAULT_MODEL, text, audio)
        started = time.monotonic()
        heard = transcribe(whisper, audio)
        ref_words = normalize_words(text)
        wer = word_error_rate(text, heard)
        total_errors += wer * len(ref_words)
        total_words += len(ref_words)
        results.append({"id": name, "reference": text, "heard": heard, "wer": round(wer, 4),
                        "reference_words": len(ref_words), "asr_seconds": round(time.monotonic() - started, 2)})
    report = {"date": time.strftime("%Y-%m-%d"), "voice_model": DEFAULT_MODEL, "whisper": args.whisper,
              "samples": len(results), "corpus_wer": round(total_errors / total_words, 4) if total_words else None,
              "results": results,
              "note": "Mide inteligibilidad de la voz de ElevenLabs con Whisper; no mide la voz del navegador "
                      "ni la naturalidad."}
    (args.out / "roundtrip-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"muestras={len(results)} corpus_wer={report['corpus_wer']}")
    for item in results:
        print(f"  {item['id']:18} wer={item['wer']:.3f} palabras={item['reference_words']}")
    sys.exit(0)


if __name__ == "__main__":
    main()
