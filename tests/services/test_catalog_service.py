"""Тесты фасада CatalogService: cold-start, мемоизация, Stale, валидный поток."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from src.data.cache import CatalogCache
from src.data.models import Catalog, ParseResult, Product
from src.services import catalog as catalog_module
from src.services.catalog import CatalogService
from src.services.ids import group_id
from src.services.models import Ok, Stale


class _Settings:
    """Минимальный стенд Settings: фасаду нужен лишь PAGE_SIZE."""

    PAGE_SIZE = 8


def _service(cache: CatalogCache) -> CatalogService:
    return CatalogService(cache, _Settings())  # type: ignore[arg-type]


def _result(products: list[Product]) -> ParseResult:
    catalog = Catalog.build(products)
    return ParseResult(catalog=catalog, issues=(), valid_rows=len(products), skipped_rows=0)


@pytest.mark.asyncio
async def test_cold_start_categories_empty() -> None:
    """catalog=None (cold-start) → categories() пуст (UX «обновляется»)."""
    service = _service(CatalogCache())
    assert service.categories() == ()


@pytest.mark.asyncio
async def test_categories_after_swap(make_product: Callable[..., Product]) -> None:
    cache = CatalogCache()
    await cache.try_swap(_result([make_product(id="1", category="Напитки", subcategory="Соки")]))
    service = _service(cache)
    titles = [c.title for c in service.categories()]
    assert titles == ["Напитки"]


@pytest.mark.asyncio
async def test_index_built_once_per_snapshot(
    monkeypatch: pytest.MonkeyPatch, make_product: Callable[..., Product]
) -> None:
    """Повторные вызовы на одном снимке строят индекс один раз (мемоизация)."""
    cache = CatalogCache()
    await cache.try_swap(_result([make_product(id="1")]))
    service = _service(cache)

    calls = {"n": 0}
    original_build = catalog_module.CatalogIndex.build

    def _counting_build(catalog: object) -> object:
        calls["n"] += 1
        return original_build(catalog)  # type: ignore[arg-type]

    monkeypatch.setattr(catalog_module.CatalogIndex, "build", staticmethod(_counting_build))
    service.categories()
    service.categories()
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_index_rebuilt_after_snapshot_swap(
    monkeypatch: pytest.MonkeyPatch, make_product: Callable[..., Product]
) -> None:
    cache = CatalogCache()
    await cache.try_swap(_result([make_product(id="1", category="A", subcategory="X")]))
    service = _service(cache)
    assert [c.title for c in service.categories()] == ["A"]
    await cache.try_swap(_result([make_product(id="2", category="B", subcategory="Y")]))
    assert [c.title for c in service.categories()] == ["B"]


@pytest.mark.asyncio
async def test_subcategories_ok(make_product: Callable[..., Product]) -> None:
    cache = CatalogCache()
    await cache.try_swap(_result([make_product(id="1", category="Напитки", subcategory="Соки")]))
    service = _service(cache)
    result = service.subcategories(group_id("Напитки"))
    assert isinstance(result, Ok)
    assert [s.title for s in result.value] == ["Соки"]


@pytest.mark.asyncio
async def test_subcategories_unknown_is_stale() -> None:
    service = _service(CatalogCache())
    assert isinstance(service.subcategories("deadbeefdead"), Stale)


@pytest.mark.asyncio
async def test_product_page_ok(make_product: Callable[..., Product]) -> None:
    cache = CatalogCache()
    await cache.try_swap(
        _result(
            [
                make_product(id="1", category="Напитки", subcategory="Соки", name_ru="Сок"),
            ]
        )
    )
    service = _service(cache)
    result = service.product_page(group_id("Напитки", "Соки"), 1, "ru")
    assert isinstance(result, Ok)
    assert [i.title for i in result.value.items] == ["Сок"]
    assert result.value.items[0].id == group_id("1")


@pytest.mark.asyncio
async def test_product_page_unknown_is_stale() -> None:
    service = _service(CatalogCache())
    assert isinstance(service.product_page("missingsubxx", 1, "ru"), Stale)
