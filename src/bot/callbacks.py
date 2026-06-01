"""Типизированные callback_data-фабрики (короткие хеш-id + page, ≤64 байта).

Строки/UZ-названия/поисковый запрос в callback запрещены (CLAUDE.md). Все id —
12-hex group_id фиксированной длины, поэтому пакет влезает в лимит Telegram.
"""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class LangCB(CallbackData, prefix="lang"):
    """Выбор языка интерфейса."""

    code: str


class NavCB(CallbackData, prefix="nav"):
    """Навигация без контекста: to ∈ {menu, search, lang}."""

    to: str


class CategoryCB(CallbackData, prefix="c"):
    """Открыть подкатегории категории."""

    cat: str


class SubcatCB(CallbackData, prefix="s"):
    """Открыть страницу 1 товаров подкатегории."""

    cat: str
    sub: str


class PageCB(CallbackData, prefix="pg"):
    """Страница N товаров подкатегории (пагинация + цель «назад» из карточки)."""

    cat: str
    sub: str
    page: int


class ProductCB(CallbackData, prefix="p"):
    """Карточка товара из каталога; cat/sub/page — контекст возврата к списку."""

    prod: str
    cat: str
    sub: str
    page: int


class SearchPageCB(CallbackData, prefix="sp"):
    """Страница N результатов поиска (запрос живёт в FSM-data)."""

    page: int


class SearchProductCB(CallbackData, prefix="ps"):
    """Карточка товара из результатов поиска; возврат — на текущую страницу поиска (FSM)."""

    prod: str
