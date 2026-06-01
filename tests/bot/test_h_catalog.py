"""Тесты catalog-роутера: навигация, пагинация, карточка, Stale, пустая подкатегория."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock

import pytest

from src.bot.callbacks import CategoryCB, ProductCB, SubcatCB
from src.bot.handlers.catalog import on_category, on_product, on_subcategory
from src.data.models import Product
from src.services.catalog import CatalogService
from src.services.ids import group_id


@pytest.mark.asyncio
async def test_category_lists_subcategories(
    make_callback: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
    make_product: Callable[..., Product],
) -> None:
    service = seed_service([make_product(category="Напитки", subcategory="Соки")])
    cb = make_callback()
    await on_category(
        cb, callback_data=CategoryCB(cat=group_id("Напитки")), lang="ru", service=service
    )
    cb.answer.assert_awaited()
    cb.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_unknown_category_is_stale(
    make_callback: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
) -> None:
    service = seed_service([])
    cb = make_callback()
    await on_category(cb, callback_data=CategoryCB(cat="deadbeefdead"), lang="ru", service=service)
    cb.answer.assert_awaited()
    text = cb.message.answer.await_args_list[0].args[0]
    assert "обновил" in text.lower()  # stale_notice


@pytest.mark.asyncio
async def test_subcategory_shows_products(
    make_callback: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
    make_product: Callable[..., Product],
) -> None:
    service = seed_service([make_product(id="1", category="Напитки", subcategory="Соки")])
    cb = make_callback()
    await on_subcategory(
        cb,
        callback_data=SubcatCB(cat=group_id("Напитки"), sub=group_id("Напитки", "Соки")),
        lang="ru",
        service=service,
    )
    cb.answer.assert_awaited()
    cb.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_subcategory_stale_when_unknown(
    make_callback: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
) -> None:
    service = seed_service([])
    cb = make_callback()
    await on_subcategory(
        cb, callback_data=SubcatCB(cat="x" * 12, sub="y" * 12), lang="ru", service=service
    )
    text = cb.message.answer.await_args_list[0].args[0]
    assert "обновил" in text.lower()


@pytest.mark.asyncio
async def test_product_card_sent(
    make_callback: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
    make_product: Callable[..., Product],
) -> None:
    service = seed_service([make_product(id="abc", category="Напитки", subcategory="Соки")])
    cb = make_callback()
    await on_product(
        cb,
        callback_data=ProductCB(
            prod=group_id("abc"),
            cat=group_id("Напитки"),
            sub=group_id("Напитки", "Соки"),
            page=1,
        ),
        lang="ru",
        service=service,
    )
    cb.answer.assert_awaited()
    cb.message.answer.assert_awaited()  # карточка без фото → answer


@pytest.mark.asyncio
async def test_product_card_stale(
    make_callback: Callable[..., AsyncMock],
    seed_service: Callable[[list[Product]], CatalogService],
) -> None:
    service = seed_service([])
    cb = make_callback()
    await on_product(
        cb,
        callback_data=ProductCB(prod="z" * 12, cat="c" * 12, sub="s" * 12, page=1),
        lang="ru",
        service=service,
    )
    text = cb.message.answer.await_args_list[0].args[0]
    assert "обновил" in text.lower()
