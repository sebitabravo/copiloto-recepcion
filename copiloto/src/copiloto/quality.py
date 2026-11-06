"""Métrica de ida y vuelta para la voz: texto → audio → reconocimiento → comparación.

El WER mide cuántas palabras de la respuesta se pierden o cambian al escucharla. No mide
naturalidad: esa necesita escucha humana (MOS). Ver docs/evaluacion-voz.md.
"""

import re
import unicodedata


def normalize_words(text: str) -> list[str]:
    """Minúsculas, sin puntuación y con espacios simples. Los acentos se conservan: Whisper los escribe."""
    lowered = unicodedata.normalize("NFC", text).lower()
    cleaned = re.sub(r"[^\w\s]", " ", lowered)
    return cleaned.split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Distancia de edición a nivel de palabra dividida por el número de palabras de referencia."""
    ref, hyp = normalize_words(reference), normalize_words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            cost = 0 if ref_word == hyp_word else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1] / len(ref)
