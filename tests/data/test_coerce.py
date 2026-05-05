"""Тесты чистых преобразователей строковых ячеек: parse_number, parse_bool."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.data.coerce import parse_bool, parse_number

NBSP = " "  # неразрывный пробел: трактуется как разделитель тысяч


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # пробелы = тысячи, удаляются
        ("120 000", Decimal("120000")),
        # одна запятая, < 3 цифр после → десятичная
        ("12,5", Decimal("12.5")),
        # одна запятая, ровно 3 цифры после → НЕ десятичная → None
        ("120,000", None),
        # пробел-тысячи + десятичная запятая
        ("1 200,50", Decimal("1200.50")),
        # точка = десятичная
        ("12.5", Decimal("12.5")),
        # точка-как-тысячи не поддерживается (несколько точек) → None
        ("1.234.567", None),
        # более одной запятой → None
        ("12,50,5", None),
        # нечисловое → None
        ("abc", None),
        # пустая строка → None
        ("", None),
        # неразрывный пробел тоже разделитель тысяч
        (f"120{NBSP}000", Decimal("120000")),
        # отрицательное число
        ("-5", Decimal("-5")),
    ],
)
def test_parse_number(raw: str, expected: Decimal | None) -> None:
    """Каждый кейс грамматики контракта даёт ожидаемый Decimal либо None."""
    assert parse_number(raw) == expected


# Три «не-ASCII» вида апострофа узбекского yo'q (канонический U+0027 проверяется отдельным кейсом).
_AP_VARIANTS = ["ʻ", "‘", "ʼ"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # true-множество (в т.ч. регистр и пробелы вокруг)
        ("true", True),
        ("TRUE", True),
        (" True ", True),
        ("1", True),
        ("да", True),
        ("ha", True),
        ("+", True),
        ("yes", True),
        # false-множество
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("нет", False),
        ("yoq", False),
        ("yo’q", False),  # апостроф U+2019 (типографский)
        ("yo'q", False),  # апостроф U+0027 (канонический)
        ("-", False),
        ("no", False),
        # нераспознанное → None
        ("maybe", None),
        ("", None),
        ("2", None),
    ],
)
def test_parse_bool(raw: str, expected: bool | None) -> None:
    """Каждый литерал true/false-множества (и мусор) даёт ожидаемый bool|None."""
    assert parse_bool(raw) is expected


@pytest.mark.parametrize("apostrophe", _AP_VARIANTS)
def test_parse_bool_uz_apostrophe_variants(apostrophe: str) -> None:
    """yo'q с любым из не-ASCII апострофов нормализуется и распознаётся как False."""
    assert parse_bool(f"yo{apostrophe}q") is False
