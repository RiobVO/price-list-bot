"""Тесты презентации: формат цены, фолбэк desc/name, сборка и обрезка карточки."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from src.data.models import Product
from src.services.formatting import format_price, localized_desc, localized_name, product_list_item
from src.services.ids import group_id

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


def test_localized_name_uses_current_lang(make_product: Callable[..., Product]) -> None:
    p = make_product(name_ru="Сок", name_uz="Sharbat")
    assert localized_name(p, "ru") == "Сок"
    assert localized_name(p, "uz") == "Sharbat"


def test_localized_name_falls_back_when_empty(make_product: Callable[..., Product]) -> None:
    """Дефенсивный фолбэк: пустое имя на языке → второй язык."""
    p = make_product(name_uz="")
    assert localized_name(p, "uz") == "Сок"  # name_ru


def test_localized_desc_falls_back_to_other_language(make_product: Callable[..., Product]) -> None:
    p = make_product(desc_ru="Описание", desc_uz=None)
    assert localized_desc(p, "uz") == "Описание"


def test_localized_desc_none_when_both_empty(make_product: Callable[..., Product]) -> None:
    p = make_product(desc_ru=None, desc_uz=None)
    assert localized_desc(p, "ru") is None


def test_product_list_item_id_and_title(make_product: Callable[..., Product]) -> None:
    p = make_product(id="abc", name_ru="Сок")
    item = product_list_item(p, "ru")
    assert item.id == group_id("abc")
    assert item.title == "Сок"
