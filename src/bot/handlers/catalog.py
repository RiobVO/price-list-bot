"""Catalog-роутер: категория→подкатегории→страница товаров→карточка.

Любой неизвестный/протухший id → мягкий ответ stale + меню (CatalogService
вернул Stale). Пустая страница товаров → «в категории пока нет товаров».
"""

from __future__ import annotations

from aiogram import Router
from aiogram.types import CallbackQuery, Message

from src.bot.callbacks import CategoryCB, PageCB, ProductCB, SubcatCB
from src.bot.delivery import send_product_card
from src.bot.keyboards import (
    main_menu_keyboard,
    product_card_keyboard,
    products_page_keyboard,
    subcategories_keyboard,
)
from src.locales import get_text
from src.services.catalog import CatalogService
from src.services.models import Lang, Ok

router = Router(name="catalog")


async def _stale(callback: CallbackQuery, lang: Lang, service: CatalogService) -> None:
    """Единый ответ на протухший id: уведомление + возврат в меню."""
    if callback.message is None:
        return
    await callback.message.answer(get_text("stale_notice", lang))
    categories = service.categories()
    if categories:
        await callback.message.answer(
            get_text("menu_title", lang), reply_markup=main_menu_keyboard(categories, lang)
        )
    else:
        await callback.message.answer(get_text("catalog_updating", lang))


@router.callback_query(CategoryCB.filter())
async def on_category(
    callback: CallbackQuery, callback_data: CategoryCB, *, lang: Lang, service: CatalogService
) -> None:
    """Показать подкатегории категории."""
    await callback.answer()
    result = service.subcategories(callback_data.cat)
    if not isinstance(result, Ok):
        await _stale(callback, lang, service)
        return
    if callback.message:
        await callback.message.answer(
            get_text("menu_title", lang),
            reply_markup=subcategories_keyboard(callback_data.cat, result.value, lang),
        )


async def _render_page(
    callback: CallbackQuery, cat: str, sub: str, page: int, lang: Lang, service: CatalogService
) -> None:
    """Отрисовать страницу товаров подкатегории (общий код sub/pagination)."""
    result = service.product_page(sub, page, lang)
    if not isinstance(result, Ok):
        await _stale(callback, lang, service)
        return
    view = result.value
    if not view.items:
        if callback.message:
            await callback.message.answer(get_text("empty_category", lang))
        return
    counter = get_text("page_counter", lang).format(page=view.page, total=view.total_pages)
    if callback.message:
        await callback.message.answer(
            counter, reply_markup=products_page_keyboard(cat, sub, view, lang)
        )


@router.callback_query(SubcatCB.filter())
async def on_subcategory(
    callback: CallbackQuery, callback_data: SubcatCB, *, lang: Lang, service: CatalogService
) -> None:
    """Страница 1 товаров подкатегории."""
    await callback.answer()
    await _render_page(callback, callback_data.cat, callback_data.sub, 1, lang, service)


@router.callback_query(PageCB.filter())
async def on_page(
    callback: CallbackQuery, callback_data: PageCB, *, lang: Lang, service: CatalogService
) -> None:
    """Страница N товаров подкатегории (пагинация)."""
    await callback.answer()
    await _render_page(
        callback, callback_data.cat, callback_data.sub, callback_data.page, lang, service
    )


@router.callback_query(ProductCB.filter())
async def on_product(
    callback: CallbackQuery, callback_data: ProductCB, *, lang: Lang, service: CatalogService
) -> None:
    """Карточка товара из каталога; «назад» — на ту же страницу списка."""
    await callback.answer()
    result = service.product_card(callback_data.prod, lang)
    if not isinstance(result, Ok):
        await _stale(callback, lang, service)
        return
    if isinstance(callback.message, Message):
        keyboard = product_card_keyboard(
            callback_data.cat, callback_data.sub, callback_data.page, lang
        )
        await send_product_card(callback.message, result.value, markup=keyboard)
