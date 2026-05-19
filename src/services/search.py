"""Подстрочный поиск по нормализованному name_{lang} среди активных товаров."""

from __future__ import annotations

from src.services.formatting import localized_name, product_list_item
from src.services.index import CatalogIndex
from src.services.models import Lang, Page, ProductListItem
from src.services.normalize import normalize
from src.services.pagination import paginate


def search(
    index: CatalogIndex, query: str, lang: Lang, page: int, page_size: int
) -> Page[ProductListItem]:
    """Найти активные товары, чьё нормализованное name_{lang} содержит запрос.

    Пустой/пробельный запрос (после нормализации) → пустая страница. Поиск по
    всему каталогу; кросс-скрипт обеспечен нормализацией обеих сторон.
    """
    needle = normalize(query, lang)
    if not needle:
        return paginate((), page, page_size)
    matched = [
        product
        for product in index.active_products
        if needle in normalize(localized_name(product, lang), lang)
    ]
    items = [product_list_item(product, lang) for product in matched]
    return paginate(items, page, page_size)
