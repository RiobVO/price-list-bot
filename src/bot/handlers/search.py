"""Search-роутер: FSM-ввод запроса, результаты с пагинацией, карточка из поиска.

В callback — только номер страницы (sp:N); запрос хранится в FSM-data. Не-текст
в режиме поиска → мягко «введите текст». Кнопка «Назад/меню» сбрасывает FSM.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.callbacks import NavCB, SearchPageCB, SearchProductCB
from src.bot.delivery import send_product_card
from src.bot.keyboards import search_page_keyboard, search_result_keyboard
from src.bot.states import SearchSG
from src.locales import get_text
from src.services.catalog import CatalogService
from src.services.models import Lang, Ok

router = Router(name="search")


@router.callback_query(NavCB.filter(F.to == "search"))
async def on_enter_search(callback: CallbackQuery, *, lang: Lang, state: FSMContext) -> None:
    """Вход в режим поиска: ставим FSM-состояние и просим ввести текст."""
    await callback.answer()
    await state.set_state(SearchSG.waiting_query)
    if callback.message:
        await callback.message.answer(get_text("search_prompt", lang))


async def _render_results(
    message: Message, query: str, page: int, lang: Lang, service: CatalogService
) -> None:
    """Отрисовать страницу результатов; пусто → «ничего не найдено»."""
    view = service.search(query, lang, page)
    if not view.items:
        await message.answer(get_text("search_not_found", lang))
        return
    counter = get_text("page_counter", lang).format(page=view.page, total=view.total_pages)
    await message.answer(counter, reply_markup=search_page_keyboard(view, lang))


@router.message(SearchSG.waiting_query, F.text)
async def on_query(
    message: Message, *, lang: Lang, state: FSMContext, service: CatalogService
) -> None:
    """Принять текстовый запрос, сохранить его в FSM-data, показать страницу 1."""
    query = message.text or ""
    await state.update_data(query=query, page=1)
    await _render_results(message, query, 1, lang, service)


@router.message(SearchSG.waiting_query)
async def on_non_text(message: Message, *, lang: Lang, state: FSMContext) -> None:
    """Не-текст в режиме поиска → мягко просим текст (состояние не снимаем)."""
    await message.answer(get_text("search_enter_text", lang))


@router.callback_query(SearchPageCB.filter())
async def on_search_page(
    callback: CallbackQuery,
    callback_data: SearchPageCB,
    *,
    lang: Lang,
    state: FSMContext,
    service: CatalogService,
) -> None:
    """Пагинация результатов: запрос берём из FSM-data, page — из callback."""
    await callback.answer()
    data = await state.get_data()
    query = str(data.get("query", ""))
    await state.update_data(page=callback_data.page)
    if isinstance(callback.message, Message):
        await _render_results(callback.message, query, callback_data.page, lang, service)


@router.callback_query(SearchProductCB.filter())
async def on_search_product(
    callback: CallbackQuery,
    callback_data: SearchProductCB,
    *,
    lang: Lang,
    state: FSMContext,
    service: CatalogService,
) -> None:
    """Карточка товара из поиска; «назад» — на текущую страницу результатов (FSM)."""
    await callback.answer()
    result = service.product_card(callback_data.prod, lang)
    if not isinstance(result, Ok):
        if isinstance(callback.message, Message):
            await callback.message.answer(get_text("stale_notice", lang))
        return
    data = await state.get_data()
    page = int(data.get("page", 1))
    if isinstance(callback.message, Message):
        await send_product_card(
            callback.message, result.value, markup=search_result_keyboard(page, lang)
        )
