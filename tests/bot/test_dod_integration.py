"""Интеграционные тесты под DoD брифа §8: cold-start при недоступном API и SIGTERM-остановка.

Сшивают слои (data refresh ↔ services ↔ bot ↔ main.serve) без сети.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable, Mapping, Sequence
from unittest.mock import AsyncMock

import pytest

from src.bot.handlers.start import on_to_menu
from src.config import Settings
from src.data.cache import CatalogCache
from src.data.fetch import FetchError
from src.data.models import ParseResult
from src.data.refresh import BackoffConfig, run_refresh_loop
from src.main import _idle, serve
from src.services.catalog import CatalogService


class _Sleeper:
    """async-sleeper: на stop_after-м вызове бросает CancelledError (обрывает вечный цикл)."""

    def __init__(self, stop_after: int) -> None:
        self.calls = 0
        self.stop_after = stop_after

    async def __call__(self, delay: float) -> None:
        self.calls += 1
        if self.calls >= self.stop_after:
            raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_cold_start_api_down_keeps_bot_up_in_updating_mode(
    bot_settings: Settings,
    make_callback: Callable[..., AsyncMock],
    make_state: Callable[..., AsyncMock],
) -> None:
    """API недоступен на cold-start → кэш пуст, бот отвечает «обновляется», не падает."""
    cache = CatalogCache(min_valid_rows=1)  # холодный, пустой снимок

    async def failing_fetch() -> list[dict[str, str]]:
        raise FetchError("503 service unavailable", transient=True)

    def never_parse(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise AssertionError("parse не должен вызываться при недоступном fetch")

    sleeper = _Sleeper(stop_after=1)
    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache,
            failing_fetch,
            never_parse,
            300.0,
            BackoffConfig(base_s=2.0, max_s=60.0),
            sleeper=sleeper,
            rng=random.Random(0),
        )

    # Цикл ушёл в backoff (один sleep) и не свалился; снимок всё ещё холодный.
    assert sleeper.calls == 1
    assert cache.get_snapshot().catalog is None

    # Бот над холодным кэшем: меню → «каталог обновляется», а не пустота/падение.
    service = CatalogService(cache, bot_settings)
    callback = make_callback()
    await on_to_menu(callback, lang="ru", service=service, state=make_state())
    callback.answer.assert_awaited()
    text = callback.message.answer.await_args.args[0]
    assert "обновляется" in text.lower()


@pytest.mark.asyncio
async def test_stop_signal_triggers_graceful_teardown() -> None:
    """SIGTERM (stop.set) → serve() гасит polling и refresh-task, закрывает сессию."""
    refresh_task: asyncio.Task[None] = asyncio.create_task(_idle())

    class _FakeDp:
        async def start_polling(self, bot: object, handle_signals: bool = True) -> None:
            await asyncio.Event().wait()  # «вечный» polling, пока не отменят

    bot = AsyncMock()  # delete_webhook/get_me/close — async-методы
    stop = asyncio.Event()
    stop.set()  # эмулируем уже пришедший SIGTERM

    await serve(_FakeDp(), bot, refresh_task, stop, shutdown_timeout=5.0)  # type: ignore[arg-type]

    bot.delete_webhook.assert_awaited_once()  # старый webhook снят перед polling
    bot.close.assert_awaited()  # сессия закрыта
    assert refresh_task.cancelled()  # refresh-task погашен, не висит
