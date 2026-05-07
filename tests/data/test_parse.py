"""Тесты parse: happy-path одной полностью валидной строки."""

from __future__ import annotations

from decimal import Decimal

from src.data.models import ParseResult
from src.data.parse import parse
from tests.fixtures import ALLOWED_CURRENCIES, DEFAULT_CURRENCY, FALLBACK_SUBCATEGORY, valid_row


def _parse(rows: list[dict[str, str]]) -> ParseResult:
    return parse(
        rows,
        default_currency=DEFAULT_CURRENCY,
        fallback_subcategory=FALLBACK_SUBCATEGORY,
        allowed_currencies=ALLOWED_CURRENCIES,
    )


def test_single_valid_row_builds_product() -> None:
    """Полностью валидная строка -> один Product, counts корректны, нет issues."""
    result = _parse([valid_row()])
    assert result.valid_rows == 1
    assert result.skipped_rows == 0
    assert result.issues == ()
    assert len(result.catalog.products) == 1
    p = result.catalog.products[0]
    assert p.id == "p1"
    assert p.category == "Напитки"
    assert p.subcategory == "Соки"
    assert p.name_ru == "Сок яблочный"
    assert p.name_uz == "Olma sharbati"
    assert p.desc_ru == "Натуральный"
    assert p.desc_uz == "Tabiiy"
    assert p.price_wholesale == Decimal("12000")
    assert p.price_retail == Decimal("15000")
    assert p.currency == "UZS"
    assert p.packaging == "1 л"
    assert p.photo == "https://example.com/p1.jpg"
    assert p.is_active is True
    assert result.catalog.by_id["p1"] is p


def test_empty_optional_fields_become_none() -> None:
    """Пустые опциональные поля (desc/packaging/photo) -> None в Product."""
    result = _parse([valid_row(desc_ru="", desc_uz="  ", packaging="", photo="")])
    p = result.catalog.products[0]
    assert p.desc_ru is None
    assert p.desc_uz is None
    assert p.packaging is None
    assert p.photo is None
