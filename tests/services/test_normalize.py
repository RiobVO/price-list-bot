"""Тесты UZ-нормализации: кросс-скрипт совпадение, апострофы, ru-путь."""

from __future__ import annotations

import pytest

from src.services.normalize import normalize


@pytest.mark.parametrize(
    ("latin", "cyrillic"),
    [
        ("olma", "олма"),  # яблоко
        ("sharbat", "шарбат"),  # сок
        ("choʻchqa", "чўчқа"),  # oʻ ↔ ў
        ("gʻalla", "ғалла"),  # gʻ ↔ ғ
        ("qand", "қанд"),  # q ↔ қ
        ("halqa", "ҳалқа"),  # h ↔ ҳ (и q↔қ)
        ("yongʻoq", "ёнғоқ"),  # ё→yo, нғ→ngʻ→ng..., қ→q
        ("yulduz", "юлдуз"),  # диграф yu ↔ ю
        ("yangi", "янги"),  # диграф ya ↔ я
        ("shamol", "шамол"),  # диграф sh ↔ ш
        ("tong", "тонг"),  # ng (н+г) ↔ нг
    ],
)
def test_uz_cross_script_canonical_equal(latin: str, cyrillic: str) -> None:
    """Латиница и кириллица одного слова дают одинаковый канон."""
    assert normalize(latin, "uz") == normalize(cyrillic, "uz")


@pytest.mark.parametrize("apostrophe", ["ʻ", "'", "ʼ", "`", "‘", "’"])
def test_uz_apostrophe_variants_unified(apostrophe: str) -> None:
    """Любой вариант апострофа в oʻ сводится к каноническому U+0027."""
    assert normalize(f"o{apostrophe}simlik", "uz") == normalize("o'simlik", "uz")


def test_uz_lower_trim_collapse_whitespace() -> None:
    assert normalize("  OLMA   sharbati  ", "uz") == "olma sharbati"


def test_ru_lowercases_trims_and_folds_yo() -> None:
    assert normalize("  Ёлка  ", "ru") == "елка"


def test_ru_does_not_apply_uz_table() -> None:
    """ru-путь не транслитерирует кириллицу в латиницу (ч остаётся ч)."""
    assert normalize("Чай", "ru") == "чай"


def test_empty_and_whitespace_normalize_to_empty() -> None:
    assert normalize("", "uz") == ""
    assert normalize("   ", "ru") == ""
