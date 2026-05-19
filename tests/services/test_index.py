"""Тесты двухуровневого индекса: сборка, active-only, порядок, обратные карты."""

from __future__ import annotations

import logging
from collections.abc import Callable

import pytest

from src.data.models import Catalog, Product
from src.services.ids import group_id
from src.services.index import CatalogIndex


def _catalog(products: list[Product]) -> Catalog:
    return Catalog.build(products)


def test_build_none_catalog_is_empty() -> None:
    index = CatalogIndex.build(None)
    assert index.categories == ()
    assert index.active_products == ()


def test_categories_in_table_order(make_product: Callable[..., Product]) -> None:
    products = [
        make_product(id="1", category="Напитки", subcategory="Соки"),
        make_product(id="2", category="Еда", subcategory="Хлеб"),
    ]
    index = CatalogIndex.build(_catalog(products))
    assert [c.title for c in index.categories] == ["Напитки", "Еда"]
    assert index.categories[0].id == group_id("Напитки")


def test_inactive_products_excluded(make_product: Callable[..., Product]) -> None:
    products = [
        make_product(id="1", category="Напитки", subcategory="Соки", is_active=True),
        make_product(id="2", category="Еда", subcategory="Хлеб", is_active=False),
    ]
    index = CatalogIndex.build(_catalog(products))
    assert [c.title for c in index.categories] == ["Напитки"]
    assert len(index.active_products) == 1


def test_category_with_only_inactive_is_absent(make_product: Callable[..., Product]) -> None:
    products = [make_product(id="1", category="Скрытая", subcategory="X", is_active=False)]
    index = CatalogIndex.build(_catalog(products))
    assert index.categories == ()


def test_subcategories_lookup(make_product: Callable[..., Product]) -> None:
    products = [
        make_product(id="1", category="Напитки", subcategory="Соки"),
        make_product(id="2", category="Напитки", subcategory="Воды"),
    ]
    index = CatalogIndex.build(_catalog(products))
    cat_id = group_id("Напитки")
    subs = index.subcategories(cat_id)
    assert subs is not None
    assert [s.title for s in subs] == ["Соки", "Воды"]
    assert subs[0].id == group_id("Напитки", "Соки")


def test_subcategories_unknown_id_returns_none() -> None:
    index = CatalogIndex.build(None)
    assert index.subcategories("deadbeefdead") is None


def test_same_subcategory_name_in_two_categories_not_merged(
    make_product: Callable[..., Product],
) -> None:
    products = [
        make_product(id="1", category="Напитки", subcategory="Прочее"),
        make_product(id="2", category="Еда", subcategory="Прочее"),
    ]
    index = CatalogIndex.build(_catalog(products))
    sid_a = group_id("Напитки", "Прочее")
    sid_b = group_id("Еда", "Прочее")
    assert sid_a != sid_b
    pa = index.products(sid_a)
    pb = index.products(sid_b)
    assert pa is not None and pb is not None
    assert pa[0].id == "1"
    assert pb[0].id == "2"


def test_products_in_table_order(make_product: Callable[..., Product]) -> None:
    products = [
        make_product(id="1", category="Напитки", subcategory="Соки"),
        make_product(id="2", category="Напитки", subcategory="Соки"),
    ]
    index = CatalogIndex.build(_catalog(products))
    sid = group_id("Напитки", "Соки")
    prods = index.products(sid)
    assert prods is not None
    assert [p.id for p in prods] == ["1", "2"]


def test_product_lookup_by_hashed_id(make_product: Callable[..., Product]) -> None:
    products = [make_product(id="abc", category="Напитки", subcategory="Соки")]
    index = CatalogIndex.build(_catalog(products))
    found = index.product(group_id("abc"))
    assert found is not None
    assert found.id == "abc"
    assert index.product("missingidxxx") is None


def test_single_other_subcategory_navigates(make_product: Callable[..., Product]) -> None:
    """Единственная группа «Прочее»: обычная двухуровневая навигация, без авто-схлопывания."""
    products = [make_product(id="1", category="Напитки", subcategory="Прочее", name_ru="Сок")]
    index = CatalogIndex.build(_catalog(products))
    assert len(index.categories) == 1
    subs = index.subcategories(group_id("Напитки"))
    assert subs is not None
    assert [s.title for s in subs] == ["Прочее"]
    prods = index.products(group_id("Напитки", "Прочее"))
    assert prods is not None
    assert len(prods) == 1


def test_hash_collision_keeps_first_and_logs_error(
    make_product: Callable[..., Product],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Коллизия хеша (разные имена → один id) логируется error, первый wins (known limitation)."""
    monkeypatch.setattr("src.services.index.group_id", lambda *parts: "collide12hash")
    products = [
        make_product(id="1", category="Напитки", subcategory="Соки"),
        make_product(id="2", category="Еда", subcategory="Хлеб"),
    ]
    with caplog.at_level(logging.ERROR):
        index = CatalogIndex.build(_catalog(products))
    assert any("collision" in record.message for record in caplog.records)
    # первый wins: единственная категория несёт title первого товара
    assert [c.title for c in index.categories] == ["Напитки"]
