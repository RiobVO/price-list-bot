"""Тесты презентации: формат цены, фолбэк desc/name, сборка и обрезка карточки."""

from __future__ import annotations

from decimal import Decimal

from src.services.formatting import format_price

NBSP = " "


def test_format_price_none_is_on_request() -> None:
    assert format_price(None, "UZS", "ru") == "цена по запросу"
    assert format_price(None, "UZS", "uz") == "narxi so'rov bo'yicha"


def test_format_price_groups_thousands_with_nbsp_and_symbol_after() -> None:
    assert format_price(Decimal("120000"), "UZS", "ru") == f"120{NBSP}000 сум"
    assert format_price(Decimal("120000"), "UZS", "uz") == f"120{NBSP}000 so'm"


def test_format_price_keeps_decimal_with_comma() -> None:
    assert format_price(Decimal("1200.50"), "UZS", "ru") == f"1{NBSP}200,50 сум"


def test_format_price_short_number_no_separator() -> None:
    assert format_price(Decimal("100"), "UZS", "ru") == "100 сум"


def test_format_price_unknown_currency_falls_back_to_code() -> None:
    assert format_price(Decimal("100"), "USD", "ru") == "100 USD"


def test_format_price_negative_groups_without_sign_in_thousands() -> None:
    """Отрицательная цена (parse_number принимает '-N'): знак вне группировки разрядов."""
    assert format_price(Decimal("-120000"), "UZS", "ru") == f"-120{NBSP}000 сум"
