"""Стартовый роутер: /start, /menu, выбор/смена языка, главное меню."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.bot.callbacks import LangCB, NavCB
from src.bot.keyboards import language_keyboard, main_menu_keyboard
from src.locales import get_text
from src.services.catalog import CatalogService
from src.services.language import LanguageStore
from src.services.models import Lang

router = Router(name="start")


async def _show_menu(target: Message | CallbackQuery, service: CatalogService, lang: Lang) -> None:
    """Показать главное меню новым сообщением; пустой каталог → «обновляется»."""
    message = target if isinstance(target, Message) else target.message
    if message is None:
        return
    categories = service.categories()
    if not categories:
        await message.answer(get_text("catalog_updating", lang))
        return
    await message.answer(
        get_text("menu_title", lang), reply_markup=main_menu_keyboard(categories, lang)
    )


@router.message(Command("start", "menu"))
async def cmd_start(
    message: Message,
    *,
    lang_store: LanguageStore,
    state: FSMContext,
    service: CatalogService,
) -> None:
    """Сброс FSM; язык не выбран → выбор языка, иначе → меню."""
    await state.clear()
    lang = lang_store.get(message.from_user.id) if message.from_user else None
    if lang is None:
        await message.answer(get_text("choose_language", "ru"), reply_markup=language_keyboard())
        return
    await _show_menu(message, service, lang)


@router.callback_query(LangCB.filter())
async def on_set_language(
    callback: CallbackQuery,
    callback_data: LangCB,
    *,
    lang_store: LanguageStore,
    service: CatalogService,
    state: FSMContext,
) -> None:
    """Сохранить выбранный язык и открыть меню."""
    await callback.answer()
    await state.clear()
    lang: Lang = "uz" if callback_data.code == "uz" else "ru"
    if callback.from_user:
        lang_store.set(callback.from_user.id, lang)
    await _show_menu(callback, service, lang)


@router.callback_query(NavCB.filter(F.to == "menu"))
async def on_to_menu(
    callback: CallbackQuery, *, lang: Lang, service: CatalogService, state: FSMContext
) -> None:
    """Вернуться в меню (сброс FSM)."""
    await callback.answer()
    await state.clear()
    await _show_menu(callback, service, lang)


@router.callback_query(NavCB.filter(F.to == "lang"))
async def on_change_language(callback: CallbackQuery) -> None:
    """Заново открыть выбор языка."""
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            get_text("choose_language", "ru"), reply_markup=language_keyboard()
        )
