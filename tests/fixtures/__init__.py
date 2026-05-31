"""Строковые фикстуры строк листа для тестов parse (все значения — str, как из fetch)."""

from __future__ import annotations

ALLOWED_CURRENCIES = frozenset({"UZS", "USD"})
DEFAULT_CURRENCY = "UZS"
FALLBACK_SUBCATEGORY = "Прочее"

# Полностью валидная строка: все required заполнены, цены валидны,
# currency в allowed, is_active явный.
_VALID_BASE: dict[str, str] = {
    "id": "p1",
    "category": "Напитки",
    "subcategory": "Соки",
    "name_ru": "Сок яблочный",
    "name_uz": "Olma sharbati",
    "desc_ru": "Натуральный",
    "desc_uz": "Tabiiy",
    "price_wholesale": "12000",
    "price_retail": "15000",
    "currency": "UZS",
    "packaging": "1 л",
    "photo": "https://example.com/p1.jpg",
    "is_active": "true",
}


def valid_row(**overrides: str) -> dict[str, str]:
    """Валидная строка с возможностью переопределить любые поля (значения — str)."""
    row = dict(_VALID_BASE)
    row.update(overrides)
    return row


def row_without_key(key: str, **overrides: str) -> dict[str, str]:
    """Валидная строка, но без указанной колонки (для эмуляции отсутствия колонки в схеме)."""
    row = valid_row(**overrides)
    row.pop(key, None)
    return row
