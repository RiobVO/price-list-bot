"""Фикстуры bot-тестов: fake Message/CallbackQuery/FSMContext + make_page.

Общие фабрики (make_product/bot_settings/seed_service) — в корневом tests/conftest.py.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.services.models import Page


@pytest.fixture
def make_page() -> Callable[..., Page[Any]]:
    def _make(**over: Any) -> Page[Any]:
        base: dict[str, Any] = {
            "items": (),
            "page": 1,
            "total_pages": 1,
            "has_prev": False,
            "has_next": False,
        }
        base.update(over)
        return Page(**base)

    return _make


@pytest.fixture
def make_callback() -> Callable[..., AsyncMock]:
    def _make(data: str = "", user_id: int = 1) -> AsyncMock:
        cb = AsyncMock()
        cb.data = data
        cb.from_user.id = user_id
        cb.message = AsyncMock()
        return cb

    return _make


@pytest.fixture
def make_message() -> Callable[..., AsyncMock]:
    def _make(text: str = "", user_id: int = 1) -> AsyncMock:
        msg = AsyncMock()
        msg.text = text
        msg.from_user.id = user_id
        return msg

    return _make


@pytest.fixture
def make_state() -> Callable[..., AsyncMock]:
    def _make(data: dict[str, object] | None = None) -> AsyncMock:
        store = dict(data or {})
        st = AsyncMock()

        async def get_data() -> dict[str, object]:
            return dict(store)

        async def update_data(**kw: object) -> dict[str, object]:
            store.update(kw)
            return dict(store)

        st.get_data.side_effect = get_data
        st.update_data.side_effect = update_data
        return st

    return _make
