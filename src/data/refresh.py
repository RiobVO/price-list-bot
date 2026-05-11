"""Фоновый refresh-loop: периодическое обновление каталога с backoff на cold-start."""

from __future__ import annotations

import random
from dataclasses import dataclass


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
