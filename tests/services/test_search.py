"""Тесты поиска: подстрока, нормализация, кросс-скрипт, активные, пагинация, пусто."""

from __future__ import annotations

from collections.abc import Callable

from src.data.models import Catalog, Product
from src.services.index import CatalogIndex
from src.services.search import search


def _index(products: list[Product]) -> CatalogIndex:
    return CatalogIndex.build(Catalog.build(products))


def test_substring_match_current_lang(make_product: Callable[..., Product]) -> None:
    index = _index(
        [
            make_product(id="1", name_ru="Сок яблочный"),
            make_product(id="2", name_ru="Вода"),
        ]
    )
    page = search(index, "яблоч", "ru", page=1, page_size=8)
    assert [i.title for i in page.items] == ["Сок яблочный"]


def test_search_is_case_insensitive(make_product: Callable[..., Product]) -> None:
    index = _index([make_product(id="1", name_ru="Сок Яблочный")])
    page = search(index, "ЯБЛОЧ", "ru", page=1, page_size=8)
    assert len(page.items) == 1


def test_uz_cross_script_finds_latin_name(make_product: Callable[..., Product]) -> None:
    """Запрос кириллицей находит товар с name_uz на латинице (и наоборот)."""
    index = _index([make_product(id="1", name_uz="olma sharbati", name_ru="Сок")])
    page = search(index, "олма", "uz", page=1, page_size=8)
    assert len(page.items) == 1


def test_only_active_products_searched(make_product: Callable[..., Product]) -> None:
    index = _index(
        [
            make_product(id="1", name_ru="Сок", is_active=False),
        ]
    )
    page = search(index, "сок", "ru", page=1, page_size=8)
    assert page.items == ()


def test_empty_query_yields_empty_page(make_product: Callable[..., Product]) -> None:
    index = _index([make_product(id="1", name_ru="Сок")])
    page = search(index, "   ", "ru", page=1, page_size=8)
    assert page.items == ()


def test_no_match_yields_empty_page(make_product: Callable[..., Product]) -> None:
    index = _index([make_product(id="1", name_ru="Сок")])
    page = search(index, "телефон", "ru", page=1, page_size=8)
    assert page.items == ()
    assert page.total_pages == 1


def test_search_paginates(make_product: Callable[..., Product]) -> None:
    products = [make_product(id=str(n), name_ru=f"Сок {n}") for n in range(9)]
    index = _index(products)
    page = search(index, "сок", "ru", page=2, page_size=8)
    assert len(page.items) == 1
    assert page.page == 2
    assert page.has_prev is True
