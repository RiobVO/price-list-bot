"""Проверка bot-фикстур: засеянный CatalogService + fake message/callback/state."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock

from src.data.models import Product
from src.services.catalog import CatalogService


def test_seeded_service_lists_categories(
    seed_service: Callable[[list[Product]], CatalogService],
    make_product: Callable[..., Product],
) -> None:
    service = seed_service([make_product(id="1", category="Напитки", subcategory="Соки")])
    assert [c.title for c in service.categories()] == ["Напитки"]


def test_fake_callback_has_async_answer(make_callback: Callable[..., AsyncMock]) -> None:
    cb = make_callback(data="nav:menu", user_id=5)
    assert cb.data == "nav:menu"
    assert cb.from_user.id == 5


def test_fake_state_roundtrips(make_state: Callable[..., AsyncMock]) -> None:
    state = make_state({"query": "сок", "page": 2})

    async def _check() -> None:
        data = await state.get_data()
        assert data["query"] == "сок"
        await state.update_data(page=3)
        assert (await state.get_data())["page"] == 3

    asyncio.run(_check())
