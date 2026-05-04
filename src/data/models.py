"""Доменные типы data-слоя: иммутабельные модели каталога и результат парсинга.

Category/Subcategory здесь НЕТ — это навигационные view слоя services (другой план).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Product:
    """Единица каталога. price_*=None означает «цена по запросу» (поле деградировало)."""

    id: str
    category: str
    subcategory: str
    name_ru: str
    name_uz: str
    desc_ru: str | None
    desc_uz: str | None
    price_wholesale: Decimal | None
    price_retail: Decimal | None
    currency: str
    packaging: str | None
    photo: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class RowIssue:
    """Замечание по строке снимка. reason — стабильный код (см. parse)."""

    row_number: int  # 1-based номер строки данных (без заголовка)
    product_id: str | None
    # КОДЫ: missing_required | bad_number | unrecognized_bool | duplicate_id
    #     | empty_subcategory | empty_currency | unrecognized_currency | empty_is_active
    reason: str
    detail: str


class SchemaError(Exception):
    """Битая схема: rows непуст, но отсутствует обязательная колонка. parse() БРОСАЕТ это."""
