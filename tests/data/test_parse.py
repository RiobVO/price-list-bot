"""Тесты parse: happy-path одной полностью валидной строки."""

from __future__ import annotations

from decimal import Decimal

import pytest

from src.data.models import ParseResult, RowIssue
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


# --- P2: battered rows ---


@pytest.mark.parametrize("field", ["id", "category", "name_ru", "name_uz"])
def test_empty_required_field_skips_row(field: str) -> None:
    """Пустое обязательное поле -> строка пропущена, RowIssue(missing_required), не в каталоге."""
    result = _parse([valid_row(**{field: ""})])
    assert result.valid_rows == 0
    assert result.skipped_rows == 1
    assert result.catalog.products == ()
    assert len(result.issues) == 1
    issue: RowIssue = result.issues[0]
    assert issue.reason == "missing_required"
    assert issue.row_number == 1


@pytest.mark.parametrize("field", ["id", "category", "name_ru", "name_uz"])
def test_whitespace_required_field_skips_row(field: str) -> None:
    """Whitespace-only обязательное поле трактуется как пустое -> пропуск."""
    result = _parse([valid_row(**{field: "   "})])
    assert result.skipped_rows == 1
    assert result.issues[0].reason == "missing_required"


def test_valid_and_broken_rows_mixed_counts() -> None:
    """Смесь: 1 валидная + 1 битая -> valid=1, skipped=1, row_number битой = её позиция."""
    rows = [valid_row(id="ok"), valid_row(id="", category="X")]
    result = _parse(rows)
    assert result.valid_rows == 1
    assert result.skipped_rows == 1
    assert result.catalog.products[0].id == "ok"
    assert result.issues[0].row_number == 2
    assert result.issues[0].reason == "missing_required"


# --- P3: price degradation ---


def test_bad_price_degrades_to_none_keeps_product() -> None:
    """Невалидная цена -> None (цена по запросу), товар жив, RowIssue(bad_number)."""
    result = _parse([valid_row(id="p", price_wholesale="abc")])
    assert result.valid_rows == 1
    assert result.skipped_rows == 0
    p = result.catalog.products[0]
    assert p.price_wholesale is None
    assert p.price_retail == Decimal("15000")
    reasons = [i.reason for i in result.issues]
    assert reasons.count("bad_number") == 1
    issue = next(i for i in result.issues if i.reason == "bad_number")
    assert issue.product_id == "p"
    assert issue.row_number == 1


def test_both_prices_bad_two_issues_product_alive() -> None:
    """Обе цены невалидны -> обе None, товар жив, два RowIssue(bad_number)."""
    result = _parse([valid_row(id="p", price_wholesale="", price_retail="xx")])
    p = result.catalog.products[0]
    assert p.price_wholesale is None
    assert p.price_retail is None
    assert [i.reason for i in result.issues].count("bad_number") == 2
    assert result.valid_rows == 1


# --- P4: currency degradation ---


def test_empty_currency_uses_default_with_issue() -> None:
    """Пустая currency -> default_currency + RowIssue(empty_currency)."""
    result = _parse([valid_row(id="p", currency="")])
    p = result.catalog.products[0]
    assert p.currency == DEFAULT_CURRENCY
    assert [i.reason for i in result.issues] == ["empty_currency"]
    assert result.valid_rows == 1


def test_unrecognized_currency_uses_default_with_issue() -> None:
    """Непустая currency не из allowed -> default_currency + RowIssue(unrecognized_currency)."""
    result = _parse([valid_row(id="p", currency="EUR")])
    p = result.catalog.products[0]
    assert p.currency == DEFAULT_CURRENCY
    assert [i.reason for i in result.issues] == ["unrecognized_currency"]


def test_allowed_currency_kept_no_issue() -> None:
    """currency из allowed -> сохранена как есть, без issue."""
    result = _parse([valid_row(id="p", currency="USD")])
    assert result.catalog.products[0].currency == "USD"
    assert result.issues == ()
