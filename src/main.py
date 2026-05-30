"""Composition root: сборка зависимостей и запуск бота (polling/webhook).

Единственный модуль, который проводит data↔services↔bot вместе. Граничные слои
сюда не импортируют. Тестируемые куски вынесены в отдельные функции.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from collections.abc import Awaitable, Callable, Mapping, Sequence
from functools import partial

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.bot.handlers import catalog as catalog_handlers
from src.bot.handlers import search as search_handlers
from src.bot.handlers import start as start_handlers
from src.bot.middlewares.language import LanguageMiddleware
from src.bot.middlewares.throttle import ThrottleMiddleware
from src.config import Settings
from src.data.auth import build_gspread_client
from src.data.cache import CatalogCache
from src.data.fetch import FetchError, fetch_rows
from src.data.models import ParseResult
from src.data.parse import parse
from src.data.refresh import BackoffConfig, run_refresh_loop
from src.data.sample import SAMPLE_ROWS
from src.logging_setup import setup_logging
from src.services.catalog import CatalogService
from src.services.language import LanguageStore

logger = logging.getLogger(__name__)


async def _idle() -> None:
    """Бесконечное ожидание: заглушка refresh-task в демо-режиме (гасится при shutdown)."""
    await asyncio.Event().wait()


def build_parse_fn(
    settings: Settings,
) -> Callable[[Sequence[Mapping[str, str]]], ParseResult]:
    """parse с зашитыми из конфига валютами и fallback-подкатегорией."""
    return partial(
        parse,
        default_currency=settings.DEFAULT_CURRENCY,
        fallback_subcategory=settings.FALLBACK_SUBCATEGORY,
        allowed_currencies=settings.allowed_currencies(),
    )


def build_fetch_fn(
    client: object,
    settings: Settings,
    *,
    fetch: Callable[[object, str, str], list[dict[str, str]]] = fetch_rows,
) -> Callable[[], Awaitable[list[dict[str, str]]]]:
    """async-адаптер синхронного fetch_rows (через asyncio.to_thread)."""

    async def _fetch() -> list[dict[str, str]]:
        return await asyncio.to_thread(fetch, client, settings.SPREADSHEET_ID, settings.SHEET_NAME)

    return _fetch


def build_dispatcher(
    service: CatalogService, lang_store: LanguageStore, settings: Settings
) -> Dispatcher:
    """Собрать Dispatcher: workflow-data, middlewares (троттлинг→язык), роутеры."""
    dp = Dispatcher(storage=MemoryStorage())
    dp["service"] = service
    dp["lang_store"] = lang_store

    throttle = ThrottleMiddleware(settings.THROTTLE_RATE_PER_SEC)
    language = LanguageMiddleware(lang_store)
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(throttle)
        observer.outer_middleware(language)

    dp.include_router(start_handlers.router)
    dp.include_router(catalog_handlers.router)
    dp.include_router(search_handlers.router)
    return dp


def choose_transport(settings: Settings) -> str:
    """Выбрать транспорт: 'webhook' при USE_WEBHOOK, иначе 'polling'."""
    return "webhook" if settings.USE_WEBHOOK else "polling"


async def shutdown(refresh_task: asyncio.Task[None], bot: Bot) -> None:
    """Отменить refresh-task (дождаться), закрыть сессию бота. Идемпотентно-безопасно."""
    refresh_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await refresh_task
    with contextlib.suppress(Exception):
        await bot.close()
    logger.info("shutdown_complete")


async def run(settings: Settings) -> None:
    """Поднять бота: кэш + refresh-task + dispatcher + транспорт + graceful shutdown."""
    setup_logging(level=settings.LOG_LEVEL, fmt=settings.LOG_FORMAT)
    cache = CatalogCache(min_valid_rows=settings.MIN_VALID_ROWS)
    service = CatalogService(cache, settings)
    lang_store = LanguageStore()
    parse_fn = build_parse_fn(settings)

    if settings.USE_SAMPLE_CATALOG:
        # Демо: засеять кэш встроенным примером, без Google Sheets и без refresh-loop.
        logger.info("sample_catalog_mode")
        await cache.try_swap(parse_fn(SAMPLE_ROWS))
        refresh_task: asyncio.Task[None] = asyncio.create_task(_idle())
    else:
        client = build_gspread_client(settings)
        fetch_fn = build_fetch_fn(client, settings)
        backoff = BackoffConfig(
            base_s=settings.COLD_START_BACKOFF_BASE_S, max_s=settings.COLD_START_BACKOFF_MAX_S
        )
        refresh_task = asyncio.create_task(
            run_refresh_loop(cache, fetch_fn, parse_fn, settings.CACHE_TTL_SECONDS, backoff)
        )

    bot = Bot(settings.BOT_TOKEN.get_secret_value())
    dp = build_dispatcher(service, lang_store, settings)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):  # Windows
            loop.add_signal_handler(sig, stop.set)

    if choose_transport(settings) == "webhook":
        raise NotImplementedError("webhook transport — каркас, см. ADR 0008 (TODO infra)")

    polling = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
    done, _ = await asyncio.wait(
        {polling, refresh_task, asyncio.create_task(stop.wait())},
        return_when=asyncio.FIRST_COMPLETED,
    )
    polling.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await polling
    await asyncio.wait_for(shutdown(refresh_task, bot), timeout=settings.SHUTDOWN_TIMEOUT_S)
    if refresh_task in done and not refresh_task.cancelled():
        exc = refresh_task.exception()
        if isinstance(exc, FetchError) and not exc.transient:
            logger.error("non_transient_fetch_error", extra={"error": str(exc)})
            raise SystemExit(1)


def main() -> None:
    """Точка входа `python -m src.main`."""
    asyncio.run(run(Settings()))  # type: ignore[call-arg]


if __name__ == "__main__":
    main()
