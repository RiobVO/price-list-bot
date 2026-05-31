"""Cache-aware фасад слоя services: единственный мост бот↔кэш.

Читает снимок ровно один раз на публичный вызов (консистентность в пределах
клика), мемоизирует CatalogIndex по идентичности снимка, заворачивает исход
запросов по id в Ok | Stale. Не импортирует aiogram, не ходит в gspread/data
напрямую (только CatalogCache.get_snapshot()).
"""

from __future__ import annotations

from src.config import Settings
from src.data.cache import CatalogCache
from src.data.models import Snapshot
from src.services.formatting import product_list_item
from src.services.index import CatalogIndex as CatalogIndex
from src.services.models import (
    CategoryItem,
    Lang,
    Ok,
    Page,
    ProductListItem,
    Stale,
    SubcategoryItem,
)
from src.services.pagination import paginate


class CatalogService:
    """Навигация/поиск/карточка поверх кэша каталога."""

    def __init__(self, cache: CatalogCache, settings: Settings) -> None:
        self._cache = cache
        self._page_size = settings.PAGE_SIZE
        self._cached_snapshot: Snapshot | None = None
        self._cached_index: CatalogIndex | None = None

    def _index(self) -> CatalogIndex:
        """Индекс текущего снимка; строится один раз на снимок (мемоизация по identity).

        Ранний возврат локальной переменной в ветке пересборки — иначе mypy не сузит
        атрибут _cached_index до non-None.
        """
        snapshot = self._cache.get_snapshot()
        if snapshot is not self._cached_snapshot or self._cached_index is None:
            index = CatalogIndex.build(snapshot.catalog)
            self._cached_index = index
            self._cached_snapshot = snapshot
            return index
        return self._cached_index

    def categories(self) -> tuple[CategoryItem, ...]:
        """Категории меню. Пусто → cold-start/деградация (UX «каталог обновляется»)."""
        return self._index().categories

    def subcategories(self, cat_id: str) -> Ok[tuple[SubcategoryItem, ...]] | Stale:
        """Подкатегории категории. Неизвестный cat_id → Stale (протух)."""
        subs = self._index().subcategories(cat_id)
        return Stale() if subs is None else Ok(subs)

    def product_page(self, sub_id: str, page: int, lang: Lang) -> Ok[Page[ProductListItem]] | Stale:
        """Страница товаров подкатегории. Неизвестный sub_id → Stale; page клампится."""
        products = self._index().products(sub_id)
        if products is None:
            return Stale()
        items = [product_list_item(product, lang) for product in products]
        return Ok(paginate(items, page, self._page_size))
