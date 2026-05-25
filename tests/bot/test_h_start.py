"""Тесты start-роутера: /start, выбор языка, меню, пустой каталог."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from src.bot.callbacks import LangCB
from src.bot.handlers.start import (
    cmd_start,
    on_change_language,
    on_set_language,
    on_to_menu,
)
from src.data.models import Product
from src.services.catalog import CatalogService
from src.services.language import LanguageStore


@pytest.mark.asyncio
async def test_start_without_lang_shows_picker(
    make_message: Callable[..., AsyncMock], make_state: Callable[..., AsyncMock]
) -> None:
    store = LanguageStore()
    msg = make_message(text="/start", user_id=7)
    await cmd_start(msg, lang_store=store, state=make_state(), service=None)
    msg.answer.assert_awaited()  # показан выбор языка


@pytest.mark.asyncio
async def test_set_language_stores_and_opens_menu(
    make_callback: Callable[..., AsyncMock],
    make_state: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
    make_product: Callable[..., Product],
) -> None:
    store = LanguageStore()
    service = seed_service([make_product(category="Напитки")])
    cb = make_callback(data=LangCB(code="uz").pack(), user_id=7)
    await on_set_language(
        cb, callback_data=LangCB(code="uz"), lang_store=store, service=service, state=make_state()
    )
    assert store.get(7) == "uz"
    cb.answer.assert_awaited()  # спиннер погашен
    cb.message.answer.assert_awaited()  # меню показано


@pytest.mark.asyncio
async def test_menu_empty_catalog_shows_updating(
    make_callback: Callable[..., AsyncMock],
    make_state: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
) -> None:
    service = seed_service([])  # каталог пуст → cold-start UX
    cb = make_callback(user_id=7)
    await on_to_menu(cb, lang="ru", service=service, state=make_state())
    cb.answer.assert_awaited()
    text = cb.message.answer.await_args.args[0]
    assert "обновляется" in text.lower()


@pytest.mark.asyncio
async def test_change_language_reopens_picker(make_callback: Callable[..., AsyncMock]) -> None:
    cb = make_callback(user_id=7)
    await on_change_language(cb)
    cb.answer.assert_awaited()
    cb.message.answer.assert_awaited()
