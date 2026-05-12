"""Фоновый refresh-loop: периодическое обновление каталога с backoff на cold-start."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.data.fetch import FetchError
from src.data.models import ParseResult

if TYPE_CHECKING:
    from src.data.cache import CatalogCache

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BackoffConfig:
    """Параметры экспоненциального backoff с full-jitter (cold-start)."""

    base_s: float
    max_s: float


def _compute_backoff_delay(attempt: int, backoff: BackoffConfig, rng: random.Random) -> float:
    """Full-jitter задержка: равномерно в [0, cap], cap = min(max_s, base*2**attempt).

    attempt — 0-based номер попытки; rng инъектируется для детерминизма в тестах.
    """
    cap = min(backoff.max_s, backoff.base_s * (2**attempt))
    return rng.uniform(0.0, cap)


async def run_refresh_loop(
    cache: CatalogCache,
    fetch_fn: Callable[[], Awaitable[list[dict[str, str]]]],
    parse_fn: Callable[[Sequence[Mapping[str, str]]], ParseResult],
    ttl_seconds: float,
    backoff: BackoffConfig,
    *,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: random.Random | None = None,
) -> None:
    """Фоновый цикл обновления каталога.

    Happy path: fetch -> parse -> try_swap -> sleep(ttl). Ветви ошибок
    добавляются в последующих задачах.
    """
    rng = rng if rng is not None else random.Random()
    attempt = 0
    while True:
        started = time.monotonic()
        try:
            rows = await fetch_fn()
            result = parse_fn(rows)
        except FetchError as exc:
            if not exc.transient:
                raise  # non-transient: main ловит -> error + exit(1)
            if cache.get_snapshot().catalog is None:
                if exc.retry_after is not None:
                    delay = exc.retry_after  # 429: уважаем заголовок Retry-After
                else:
                    delay = _compute_backoff_delay(attempt, backoff, rng)
                    attempt += 1
            else:
                delay = ttl_seconds
            await sleeper(delay)
            continue
        swapped = await cache.try_swap(result)
        if swapped:
            attempt = 0
            duration_ms = (time.monotonic() - started) * 1000.0
            logger.info(
                "refresh_done",
                extra={
                    "rows_total": result.valid_rows + result.skipped_rows,
                    "valid": result.valid_rows,
                    "skipped": result.skipped_rows,
                    "duration_ms": duration_ms,
                    "snapshot_age_s": 0.0,
                    "schema_ok": True,
                },
            )
        await sleeper(ttl_seconds)
