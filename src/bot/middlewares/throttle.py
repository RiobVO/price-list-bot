"""Per-user token-bucket троттлинг (защита от спама пагинацией/поиском).

Часы инъектируются (тесты без реальных задержек). TTL-вытеснение неактивных
бакетов предотвращает утечку памяти. Троттлинг callback всё равно гасит спиннер.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

logger = logging.getLogger(__name__)

# Бакет неактивного юзера старше этого окна — выбрасывается (анти-утечка).
_EVICT_AFTER_S = 600.0


@dataclass
class _Bucket:
    tokens: float
    last: float


class ThrottleMiddleware(BaseMiddleware):
    """Token-bucket: rate токенов/сек, ёмкость = max(1, rate)."""

    def __init__(
        self,
        rate_per_sec: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._rate = rate_per_sec
        self._capacity = max(1.0, rate_per_sec)
        self._clock = clock
        self._buckets: dict[int, _Bucket] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user") or getattr(event, "from_user", None)
        if user is None:
            return await handler(event, data)
        now = self._clock()
        self._evict(now)
        if self._allow(user.id, now):
            return await handler(event, data)
        # Лимит превышен: гасим callback-спиннер, событие дропаем.
        if isinstance(event, CallbackQuery):
            await event.answer()
        logger.info("throttled", extra={"user_id": user.id})
        return None

    def _allow(self, user_id: int, now: float) -> bool:
        bucket = self._buckets.get(user_id)
        if bucket is None:
            self._buckets[user_id] = _Bucket(tokens=self._capacity - 1.0, last=now)
            return True
        bucket.tokens = min(self._capacity, bucket.tokens + (now - bucket.last) * self._rate)
        bucket.last = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True
        return False

    def _evict(self, now: float) -> None:
        stale = [uid for uid, b in self._buckets.items() if now - b.last > _EVICT_AFTER_S]
        for uid in stale:
            del self._buckets[uid]
