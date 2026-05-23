"""Тесты билдеров клавиатур: структура, callback_data, кнопки навигации."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.bot.callbacks import (
    CategoryCB,
    LangCB,
    NavCB,
    PageCB,
    ProductCB,
    SearchPageCB,
    SearchProductCB,
    SubcatCB,
)
from src.bot.keyboards import (
    language_keyboard,
    main_menu_keyboard,
    product_card_keyboard,
    products_page_keyboard,
    search_page_keyboard,
    search_result_keyboard,
    subcategories_keyboard,
)
from src.services.models import CategoryItem, Page, ProductListItem, SubcategoryItem


def _all_buttons(markup: InlineKeyboardMarkup) -> list[InlineKeyboardButton]:
    return [btn for row in markup.inline_keyboard for btn in row]


def _nav_datas(markup: InlineKeyboardMarkup) -> list[str | None]:
    return [b.callback_data for b in _all_buttons(markup)]


def test_language_keyboard_has_both_languages() -> None:
    kb = language_keyboard()
    datas = {b.callback_data for b in _all_buttons(kb)}
    assert LangCB(code="ru").pack() in datas
    assert LangCB(code="uz").pack() in datas


def test_main_menu_lists_categories_plus_search_and_lang() -> None:
    cats = (CategoryItem(id="aa", title="Напитки"), CategoryItem(id="bb", title="Еда"))
    kb = main_menu_keyboard(cats, "ru")
    datas = _nav_datas(kb)
    assert CategoryCB(cat="aa").pack() in datas
    assert CategoryCB(cat="bb").pack() in datas
    assert NavCB(to="search").pack() in datas
    assert NavCB(to="lang").pack() in datas


def test_subcategories_keyboard_has_back_to_menu() -> None:
    subs = (SubcategoryItem(id="s1", title="Соки"),)
    kb = subcategories_keyboard("aa", subs, "ru")
    datas = _nav_datas(kb)
    assert SubcatCB(cat="aa", sub="s1").pack() in datas
    assert NavCB(to="menu").pack() in datas


def test_products_page_paginates_and_links_cards(make_page: Callable[..., Page[Any]]) -> None:
    page = make_page(
        items=(ProductListItem(id="p1", title="Сок"),),
        page=2,
        total_pages=3,
        has_prev=True,
        has_next=True,
    )
    kb = products_page_keyboard("aa", "s1", page, "ru")
    datas = _nav_datas(kb)
    assert ProductCB(prod="p1", cat="aa", sub="s1", page=2).pack() in datas
    assert PageCB(cat="aa", sub="s1", page=1).pack() in datas  # prev
    assert PageCB(cat="aa", sub="s1", page=3).pack() in datas  # next
    assert CategoryCB(cat="aa").pack() in datas  # back к подкатегориям


def test_products_page_no_prev_on_first(make_page: Callable[..., Page[Any]]) -> None:
    page = make_page(items=(), page=1, total_pages=1, has_prev=False, has_next=False)
    datas = _nav_datas(products_page_keyboard("aa", "s1", page, "ru"))
    assert PageCB(cat="aa", sub="s1", page=0).pack() not in datas


def test_product_card_keyboard_back_to_page() -> None:
    datas = _nav_datas(product_card_keyboard("aa", "s1", 2, "ru"))
    assert PageCB(cat="aa", sub="s1", page=2).pack() in datas


def test_search_page_keyboard_links_and_paginates(make_page: Callable[..., Page[Any]]) -> None:
    page = make_page(
        items=(ProductListItem(id="p9", title="Сок"),),
        page=1,
        total_pages=2,
        has_prev=False,
        has_next=True,
    )
    datas = _nav_datas(search_page_keyboard(page, "ru"))
    assert SearchProductCB(prod="p9").pack() in datas
    assert SearchPageCB(page=2).pack() in datas
    assert NavCB(to="menu").pack() in datas


def test_search_result_card_back_to_search_page() -> None:
    datas = _nav_datas(search_result_keyboard(3, "ru"))
    assert SearchPageCB(page=3).pack() in datas
