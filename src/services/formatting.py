"""Презентация слоя services: формат цены, фолбэк desc/name, сборка карточки.

Зависит от locales (i18n) и data.Product, но НЕ от aiogram.
"""

from __future__ import annotations

from decimal import Decimal

from src.data.models import Product
from src.locales import get_text
from src.services.ids import group_id
from src.services.models import Lang, ProductListItem

_THOUSANDS_SEP = " "  # неразрывный пробел


def _group_thousands(digits: str) -> str:
    """Сгруппировать целую часть по 3 справа неразрывным пробелом."""
    parts: list[str] = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    parts.insert(0, digits)
    return _THOUSANDS_SEP.join(parts)


def format_price(value: Decimal | None, currency: str, lang: Lang) -> str:
    """Локализованная цена: «12 000 сум». None → «цена по запросу».

    Число форматируется единообразно (пробел-тысячи, запятая-десятичная); символ
    валюты — переводимая строка (currency.<code>), неизвестная валюта → её код.
    """
    if value is None:
        return get_text("price_on_request", lang)
    symbol = get_text(f"currency.{currency}", lang, default=currency)
    text = format(value, "f")
    # Знак снимается ДО группировки тысяч, иначе "-" попадёт в разряд (−120000 → −1 120 000).
    # parse_number принимает отрицательные ("-5" → Decimal("-5")), поэтому ветка достижима.
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    integer_part, _, fractional = text.partition(".")
    grouped = _group_thousands(integer_part)
    rendered = f"{grouped},{fractional}" if fractional else grouped
    if negative:
        rendered = f"-{rendered}"
    return f"{rendered} {symbol}"


def localized_name(product: Product, lang: Lang) -> str:
    """Имя на выбранном языке; пустое → фолбэк на второй (data гарантирует непустые)."""
    primary = product.name_ru if lang == "ru" else product.name_uz
    secondary = product.name_uz if lang == "ru" else product.name_ru
    return primary or secondary


def localized_desc(product: Product, lang: Lang) -> str | None:
    """Описание на выбранном языке; пустое → фолбэк на второй; оба пусты → None."""
    primary = product.desc_ru if lang == "ru" else product.desc_uz
    secondary = product.desc_uz if lang == "ru" else product.desc_ru
    return primary or secondary or None


def product_list_item(product: Product, lang: Lang) -> ProductListItem:
    """Строка списка: хеш-id товара + локализованное имя."""
    return ProductListItem(id=group_id(product.id), title=localized_name(product, lang))
