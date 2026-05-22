"""Тесты презентации: формат цены, фолбэк desc/name, сборка и обрезка карточки."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from src.data.models import Product
from src.services.formatting import (
    format_price,
    localized_desc,
    localized_name,
    product_card,
    product_list_item,
)
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


def test_product_card_assembles_name_desc_prices(make_product: Callable[..., Product]) -> None:
    p = make_product(name_ru="Сок", desc_ru="Яблочный", packaging="1 л")
    card = product_card(p, "ru")
    assert "Сок" in card.text
    assert "Яблочный" in card.text
    assert "Опт: 100 сум" in card.text
    assert "Розница: 120 сум" in card.text
    assert "Фасовка: 1 л" in card.text
    assert card.photo is None


def test_product_card_omits_packaging_when_absent(make_product: Callable[..., Product]) -> None:
    card = product_card(make_product(packaging=None), "ru")
    assert "Фасовка" not in card.text


def test_product_card_price_on_request(make_product: Callable[..., Product]) -> None:
    card = product_card(make_product(price_wholesale=None), "ru")
    assert "Опт: цена по запросу" in card.text


def test_product_card_truncates_desc_to_photo_limit(make_product: Callable[..., Product]) -> None:
    long_desc = "слово " * 400  # ~2400 символов
    p = make_product(desc_ru=long_desc, photo="http://example.com/a.jpg")
    card = product_card(p, "ru")
    assert card.photo == "http://example.com/a.jpg"
    assert len(card.text) <= 1024
    # структура: title \n\n desc \n\n tail; обрезается ТОЛЬКО desc (средний сегмент)
    segments = card.text.split("\n\n")
    assert segments[1].rstrip().endswith("…")
    # имя и цены не срезаны — присутствуют целиком после обрезанного описания
    assert segments[0] == "Сок"
    assert "Опт: 100 сум" in card.text


def test_product_card_without_photo_uses_text_limit(make_product: Callable[..., Product]) -> None:
    long_desc = "слово " * 400
    p = make_product(desc_ru=long_desc, photo=None)
    card = product_card(p, "ru")
    assert card.photo is None
    assert len(card.text) <= 4096
    assert "Опт: 100 сум" in card.text


def test_product_card_drops_desc_block_when_no_budget(make_product: Callable[..., Product]) -> None:
    """Имя длиннее лимита: описание опускается целиком, без пустого сегмента \\n\\n\\n\\n."""
    long_name = "Имя " * 400  # имя само превышает лимит фото
    p = make_product(name_ru=long_name, desc_ru="Описание", photo="http://example.com/a.jpg")
    card = product_card(p, "ru")
    assert "\n\n\n\n" not in card.text
    # последний блок — цены (tail), описание опущено
    assert card.text.split("\n\n")[-1].startswith("Опт:")
