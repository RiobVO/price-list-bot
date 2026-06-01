"""Тесты search-роутера: FSM вход/выход, результаты, пусто, не-текст, карточка."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from src.bot.callbacks import NavCB, SearchPageCB, SearchProductCB
from src.bot.handlers.search import (
    on_enter_search,
    on_non_text,
    on_query,
    on_search_page,
    on_search_product,
)
from src.bot.states import SearchSG
from src.data.models import Product
from src.services.catalog import CatalogService
from src.services.ids import group_id


@pytest.mark.asyncio
async def test_enter_search_sets_state_and_prompts(
    make_callback: Callable[..., AsyncMock], make_state: Callable[..., AsyncMock]
) -> None:
    state = make_state()
    cb = make_callback(data=NavCB(to="search").pack())
    await on_enter_search(cb, lang="ru", state=state)
    cb.answer.assert_awaited()
    state.set_state.assert_awaited_with(SearchSG.waiting_query)
    cb.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_query_with_results_renders_page(
    make_message: Callable[..., AsyncMock],
    make_state: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
    make_product: Callable[..., Product],
) -> None:
    service = seed_service([make_product(id="1", name_ru="Сок яблочный")])
    state = make_state()
    msg = make_message(text="сок")
    await on_query(msg, lang="ru", state=state, service=service)
    state.update_data.assert_awaited()  # сохранён query + page
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_query_no_results_shows_not_found(
    make_message: Callable[..., AsyncMock],
    make_state: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
    make_product: Callable[..., Product],
) -> None:
    service = seed_service([make_product(name_ru="Хлеб")])
    msg = make_message(text="яхта")
    await on_query(msg, lang="ru", state=make_state(), service=service)
    text = msg.answer.await_args.args[0]
    assert "найдено" in text.lower()


@pytest.mark.asyncio
async def test_search_page_uses_stored_query(
    make_callback: Callable[..., AsyncMock],
    make_state: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
    make_product: Callable[..., Product],
) -> None:
    service = seed_service([make_product(id=str(i), name_ru=f"Сок {i}") for i in range(5)])
    state = make_state({"query": "сок", "page": 1})
    cb = make_callback(data=SearchPageCB(page=2).pack())
    await on_search_page(
        cb, callback_data=SearchPageCB(page=2), lang="ru", state=state, service=service
    )
    cb.answer.assert_awaited()
    cb.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_non_text_in_search_asks_for_text(
    make_message: Callable[..., AsyncMock], make_state: Callable[..., AsyncMock]
) -> None:
    msg = make_message()
    msg.text = None  # стикер/фото → text=None
    await on_non_text(msg, lang="ru", state=make_state())
    text = msg.answer.await_args.args[0]
    assert "текст" in text.lower()


@pytest.mark.asyncio
async def test_search_product_card(
    make_callback: Callable[..., AsyncMock],
    make_state: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
    make_product: Callable[..., Product],
) -> None:
    service = seed_service([make_product(id="abc", name_ru="Сок")])
    state = make_state({"query": "сок", "page": 1})
    cb = make_callback(data=SearchProductCB(prod=group_id("abc")).pack())
    await on_search_product(
        cb,
        callback_data=SearchProductCB(prod=group_id("abc")),
        lang="ru",
        state=state,
        service=service,
    )
    cb.answer.assert_awaited()
    cb.message.answer.assert_awaited()
