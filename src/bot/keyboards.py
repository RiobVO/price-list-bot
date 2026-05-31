"""Билдеры inline-клавиатур из view-моделей services. Без сети и без сервиса."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

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
from src.locales import get_text
from src.services.models import (
    CategoryItem,
    Lang,
    Page,
    ProductListItem,
    SubcategoryItem,
)


def language_keyboard() -> InlineKeyboardMarkup:
    """Двуязычный выбор языка (нейтральные подписи, язык ещё не выбран)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Русский", callback_data=LangCB(code="ru"))
    builder.button(text="O'zbekcha", callback_data=LangCB(code="uz"))
    builder.adjust(2)
    return builder.as_markup()


def main_menu_keyboard(categories: tuple[CategoryItem, ...], lang: Lang) -> InlineKeyboardMarkup:
    """Категории (по одной в ряд) + «Поиск» + «Сменить язык»."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.button(text=cat.title, callback_data=CategoryCB(cat=cat.id))
    builder.button(text=get_text("btn_search", lang), callback_data=NavCB(to="search"))
    builder.button(text=get_text("btn_change_language", lang), callback_data=NavCB(to="lang"))
    builder.adjust(1)
    return builder.as_markup()


def subcategories_keyboard(
    cat_id: str, subcategories: tuple[SubcategoryItem, ...], lang: Lang
) -> InlineKeyboardMarkup:
    """Подкатегории категории + «Назад» в меню."""
    builder = InlineKeyboardBuilder()
    for sub in subcategories:
        builder.button(text=sub.title, callback_data=SubcatCB(cat=cat_id, sub=sub.id))
    builder.button(text=get_text("btn_back", lang), callback_data=NavCB(to="menu"))
    builder.adjust(1)
    return builder.as_markup()


def products_page_keyboard(
    cat_id: str, sub_id: str, page: Page[ProductListItem], lang: Lang
) -> InlineKeyboardMarkup:
    """Список товаров страницы + ◀/▶ (по флагам) + «Назад» к подкатегориям."""
    builder = InlineKeyboardBuilder()
    for item in page.items:
        builder.button(
            text=item.title,
            callback_data=ProductCB(prod=item.id, cat=cat_id, sub=sub_id, page=page.page),
        )
    builder.adjust(1)

    nav = InlineKeyboardBuilder()
    if page.has_prev:
        nav.button(
            text=get_text("btn_prev", lang),
            callback_data=PageCB(cat=cat_id, sub=sub_id, page=page.page - 1),
        )
    if page.has_next:
        nav.button(
            text=get_text("btn_next", lang),
            callback_data=PageCB(cat=cat_id, sub=sub_id, page=page.page + 1),
        )
    nav.adjust(2)
    builder.attach(nav)

    back = InlineKeyboardBuilder()
    back.button(text=get_text("btn_back", lang), callback_data=CategoryCB(cat=cat_id))
    builder.attach(back)
    return builder.as_markup()


def product_card_keyboard(cat_id: str, sub_id: str, page: int, lang: Lang) -> InlineKeyboardMarkup:
    """Карточка каталога: «Назад» на ту же страницу списка."""
    builder = InlineKeyboardBuilder()
    builder.button(
        text=get_text("btn_back", lang),
        callback_data=PageCB(cat=cat_id, sub=sub_id, page=page),
    )
    return builder.as_markup()


def search_page_keyboard(page: Page[ProductListItem], lang: Lang) -> InlineKeyboardMarkup:
    """Результаты поиска + ◀/▶ (page в callback, запрос в FSM) + «Назад» в меню."""
    builder = InlineKeyboardBuilder()
    for item in page.items:
        builder.button(text=item.title, callback_data=SearchProductCB(prod=item.id))
    builder.adjust(1)

    nav = InlineKeyboardBuilder()
    if page.has_prev:
        nav.button(
            text=get_text("btn_prev", lang),
            callback_data=SearchPageCB(page=page.page - 1),
        )
    if page.has_next:
        nav.button(
            text=get_text("btn_next", lang),
            callback_data=SearchPageCB(page=page.page + 1),
        )
    nav.adjust(2)
    builder.attach(nav)

    back = InlineKeyboardBuilder()
    back.button(text=get_text("btn_back", lang), callback_data=NavCB(to="menu"))
    builder.attach(back)
    return builder.as_markup()


def search_result_keyboard(page: int, lang: Lang) -> InlineKeyboardMarkup:
    """Карточка из поиска: «Назад» на текущую страницу результатов."""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_text("btn_back", lang), callback_data=SearchPageCB(page=page))
    return builder.as_markup()
