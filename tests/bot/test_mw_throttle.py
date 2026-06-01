"""Тесты throttle-middleware: лимит, восстановление токенов, независимость юзеров."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery

from src.bot.middlewares.throttle import ThrottleMiddleware


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _event(user_id: int = 1) -> AsyncMock:
    ev = AsyncMock()
    ev.from_user.id = user_id
    return ev


@pytest.mark.asyncio
async def test_first_request_passes() -> None:
    mw = ThrottleMiddleware(rate_per_sec=1.0, clock=_Clock())
    handler = AsyncMock(return_value="ok")
    assert await mw(handler, _event(), {}) == "ok"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_burst_is_throttled() -> None:
    clock = _Clock()
    mw = ThrottleMiddleware(rate_per_sec=1.0, clock=clock)
    handler = AsyncMock(return_value="ok")
    await mw(handler, _event(), {})  # тратит токен
    await mw(handler, _event(), {})  # без восполнения → throttle
    assert handler.await_count == 1


@pytest.mark.asyncio
async def test_tokens_refill_over_time() -> None:
    clock = _Clock()
    mw = ThrottleMiddleware(rate_per_sec=1.0, clock=clock)
    handler = AsyncMock(return_value="ok")
    await mw(handler, _event(), {})
    clock.t = 1.0  # прошла секунда → +1 токен
    await mw(handler, _event(), {})
    assert handler.await_count == 2


@pytest.mark.asyncio
async def test_users_independent() -> None:
    mw = ThrottleMiddleware(rate_per_sec=1.0, clock=_Clock())
    handler = AsyncMock(return_value="ok")
    await mw(handler, _event(1), {})
    await mw(handler, _event(2), {})  # другой юзер — свой бакет
    assert handler.await_count == 2


@pytest.mark.asyncio
async def test_throttled_callback_is_answered() -> None:
    """Троттлинг callback всё равно гасит спиннер (answer)."""
    mw = ThrottleMiddleware(rate_per_sec=1.0, clock=_Clock())
    handler = AsyncMock()
    ev = _event(1)
    ev.__class__ = CallbackQuery  # type: ignore[assignment]  # isinstance→True, атрибуты свободны
    await mw(handler, ev, {})
    await mw(handler, ev, {})  # второй — throttle
    ev.answer.assert_awaited()
