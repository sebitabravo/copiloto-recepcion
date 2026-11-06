"""Métrica de ida y vuelta: qué tan bien se entiende lo que la voz dice (WER)."""

import pytest
from copiloto.quality import normalize_words, word_error_rate


def test_normalization_ignores_case_punctuation_and_extra_spaces():
    assert normalize_words("¡Hola,  Señor!  ¿Cómo estás?") == ["hola", "señor", "cómo", "estás"]


def test_identical_text_has_zero_error():
    assert word_error_rate("tenemos piscina temperada", "Tenemos piscina temperada.") == 0.0


def test_substitution_deletion_and_insertion_are_counted_once_each():
    # 4 palabras de referencia; una sustitución = 0.25
    assert word_error_rate("tenemos piscina temperada hoy", "tenemos alberca temperada hoy") == pytest.approx(0.25)
    # una eliminación
    assert word_error_rate("tenemos piscina temperada hoy", "tenemos temperada hoy") == pytest.approx(0.25)
    # una inserción sobre 4 palabras
    assert word_error_rate("tenemos piscina", "tenemos la piscina") == pytest.approx(0.5)


def test_empty_reference_with_empty_hypothesis_is_perfect_and_otherwise_maximal():
    assert word_error_rate("", "") == 0.0
    assert word_error_rate("", "algo") == 1.0


def test_totally_different_text_can_exceed_one_when_hypothesis_is_longer():
    assert word_error_rate("hola", "uno dos tres") == pytest.approx(3.0)
