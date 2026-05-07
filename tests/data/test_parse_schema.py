"""Тесты схемы: SchemaError при отсутствии required колонки; пустой rows — не ошибка."""

from __future__ import annotations

import pytest

from src.data.models import ParseResult, SchemaError
from src.data.parse import parse
from tests.fixtures import (
    ALLOWED_CURRENCIES,
    DEFAULT_CURRENCY,
    FALLBACK_SUBCATEGORY,
    row_without_key,
    valid_row,
)


def _parse(rows: list[dict[str, str]]) -> ParseResult:
    return parse(
        rows,
        default_currency=DEFAULT_CURRENCY,
        fallback_subcategory=FALLBACK_SUBCATEGORY,
        allowed_currencies=ALLOWED_CURRENCIES,
    )


def test_empty_rows_returns_empty_result_not_schema_error() -> None:
    """Пустой список строк -> валидный пустой ParseResult, НЕ SchemaError."""
    result = _parse([])
    assert result.valid_rows == 0
    assert result.skipped_rows == 0
    assert result.issues == ()
    assert result.catalog.products == ()
    assert dict(result.catalog.by_id) == {}


@pytest.mark.parametrize(
    "missing",
    [
        "id",
        "category",
        "subcategory",
        "name_ru",
        "name_uz",
        "price_wholesale",
        "price_retail",
        "currency",
        "is_active",
    ],
)
def test_missing_required_column_raises_schema_error(missing: str) -> None:
    """Непустой rows без required колонки -> SchemaError."""
    rows = [row_without_key(missing)]
    with pytest.raises(SchemaError):
        _parse(rows)


def test_missing_optional_column_is_ok() -> None:
    """Отсутствие опциональной колонки (desc_ru) -> не ошибка, поле None."""
    rows = [valid_row()]
    del rows[0]["desc_ru"]
    result = _parse(rows)
    assert result.valid_rows == 1
    assert result.catalog.products[0].desc_ru is None


def test_headers_normalized_strip_lower() -> None:
    """Заголовки матчатся по strip+lower: ' ID ' и 'Name_RU' распознаются."""
    row = {
        "  ID  ": "p1",
        "Category": "C",
        "SubCategory": "S",
        "NAME_RU": "rn",
        "Name_Uz": "un",
        "Price_Wholesale": "10",
        "PRICE_RETAIL": "20",
        "Currency": "UZS",
        "Is_Active": "true",
    }
    result = _parse([row])
    assert result.valid_rows == 1
    assert result.catalog.products[0].id == "p1"
