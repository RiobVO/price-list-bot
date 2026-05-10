"""Тесты CatalogCache: cold-start, atomic swap, порог качества, single-flight."""

from __future__ import annotations

from decimal import Decimal

from src.data.cache import CatalogCache
from src.data.models import Catalog, ParseResult, Product


def _product(pid: str) -> Product:
    """Минимальный валидный Product для наполнения каталога в тестах."""
    return Product(
        id=pid,
        category="cat",
        subcategory="sub",
        name_ru="имя",
        name_uz="nom",
        desc_ru=None,
        desc_uz=None,
        price_wholesale=Decimal("100"),
        price_retail=Decimal("150"),
        currency="UZS",
        packaging=None,
        photo=None,
        is_active=True,
    )


def _result(*, valid: int, skipped: int) -> ParseResult:
    """ParseResult с `valid` валидными товарами и счётчиком `skipped` битых строк.

    issues для счётчиков несущественны — порог считается по valid_rows/skipped_rows.
    """
    products = tuple(_product(f"p{i}") for i in range(valid))
    return ParseResult(
        catalog=Catalog.build(products),
        issues=(),
        valid_rows=valid,
        skipped_rows=skipped,
    )


def test_cold_start_snapshot_is_empty() -> None:
    cache = CatalogCache()
    snap = cache.get_snapshot()
    assert snap.catalog is None
    assert snap.updated_at is None
    assert snap.valid_rows == 0
    assert snap.skipped_rows == 0


def test_get_snapshot_returns_same_reference_until_swap() -> None:
    cache = CatalogCache()
    assert cache.get_snapshot() is cache.get_snapshot()
