"""Двухуровневый навигационный индекс над иммутабельным Catalog.

Строится из плоского Catalog один раз на снимок. В индекс попадают только
активные товары; порядок — по первому появлению в строках (insertion order).
Category/Subcategory — навигационные view, в data-моделях их НЕТ.
"""

from __future__ import annotations

import logging

from src.data.models import Catalog, Product
from src.services.ids import group_id
from src.services.models import CategoryItem, SubcategoryItem

_log = logging.getLogger(__name__)


def _register(mapping: dict[str, str], key: str, title: str) -> None:
    """Запомнить title по key; коллизия хеша (разные имена → один id) → error-лог."""
    existing = mapping.get(key)
    if existing is None:
        mapping[key] = title
    elif existing != title:
        _log.error("group id hash collision: %r vs %r -> %s", existing, title, key)


class CatalogIndex:
    """Активные товары, сгруппированные категория→подкатегория, + обратные карты id→группа."""

    __slots__ = (
        "categories",
        "active_products",
        "_subcats_by_cat",
        "_products_by_sub",
        "_product_by_id",
    )

    def __init__(
        self,
        categories: tuple[CategoryItem, ...],
        active_products: tuple[Product, ...],
        subcats_by_cat: dict[str, tuple[SubcategoryItem, ...]],
        products_by_sub: dict[str, tuple[Product, ...]],
        product_by_id: dict[str, Product],
    ) -> None:
        self.categories = categories
        self.active_products = active_products
        self._subcats_by_cat = subcats_by_cat
        self._products_by_sub = products_by_sub
        self._product_by_id = product_by_id

    @classmethod
    def build(cls, catalog: Catalog | None) -> CatalogIndex:
        """Собрать индекс из Catalog. None или 0 активных → пустой индекс."""
        products = catalog.products if catalog is not None else ()
        cat_titles: dict[str, str] = {}
        sub_titles: dict[str, dict[str, str]] = {}
        prods_by_sub: dict[str, list[Product]] = {}
        product_by_id: dict[str, Product] = {}
        active: list[Product] = []

        for product in products:
            if not product.is_active:
                continue
            active.append(product)
            cat_id = group_id(product.category)
            sub_id = group_id(product.category, product.subcategory)
            prod_id = group_id(product.id)

            _register(cat_titles, cat_id, product.category)
            _register(sub_titles.setdefault(cat_id, {}), sub_id, product.subcategory)
            prods_by_sub.setdefault(sub_id, []).append(product)

            existing = product_by_id.get(prod_id)
            if existing is None:
                product_by_id[prod_id] = product
            elif existing.id != product.id:
                _log.error("product id hash collision: %r vs %r", existing.id, product.id)

        categories = tuple(CategoryItem(id=cid, title=title) for cid, title in cat_titles.items())
        subcats_by_cat = {
            cid: tuple(SubcategoryItem(id=sid, title=title) for sid, title in subs.items())
            for cid, subs in sub_titles.items()
        }
        products_by_sub = {sid: tuple(items) for sid, items in prods_by_sub.items()}
        return cls(categories, tuple(active), subcats_by_cat, products_by_sub, product_by_id)

    def subcategories(self, cat_id: str) -> tuple[SubcategoryItem, ...] | None:
        """Подкатегории категории; None — неизвестный (протухший) cat_id."""
        return self._subcats_by_cat.get(cat_id)

    def products(self, sub_id: str) -> tuple[Product, ...] | None:
        """Активные товары подкатегории; None — неизвестный (протухший) sub_id."""
        return self._products_by_sub.get(sub_id)

    def product(self, prod_id: str) -> Product | None:
        """Товар по хеш-id; None — неизвестный (протухший) prod_id."""
        return self._product_by_id.get(prod_id)
