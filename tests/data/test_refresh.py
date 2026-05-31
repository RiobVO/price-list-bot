"""Тесты refresh-loop: backoff-джиттер и фоновый цикл обновления."""

from __future__ import annotations

import dataclasses
import random

import pytest

from src.data.refresh import BackoffConfig, _compute_backoff_delay


def test_backoff_config_is_frozen() -> None:
    """BackoffConfig иммутабелен (frozen) — конфиг не мутируется в цикле."""
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)
    assert cfg.base_s == 2.0
    assert cfg.max_s == 60.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.base_s = 5.0  # type: ignore[misc]


def test_compute_delay_full_jitter_returns_cap_with_max_rng() -> None:
    """full-jitter: при rng.uniform->верхняя граница delay == cap = base*2**attempt."""

    class MaxRng(random.Random):
        def uniform(self, a: float, b: float) -> float:
            return b

    rng = MaxRng()
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)
    # attempt=0 -> cap=2*2**0=2.0; attempt=1 -> 4.0; attempt=2 -> 8.0
    assert _compute_backoff_delay(0, cfg, rng) == pytest.approx(2.0)
    assert _compute_backoff_delay(1, cfg, rng) == pytest.approx(4.0)
    assert _compute_backoff_delay(2, cfg, rng) == pytest.approx(8.0)


def test_compute_delay_grows_then_caps_at_max_s() -> None:
    """cap растёт экспоненциально, но не превышает max_s (потолок)."""

    class MaxRng(random.Random):
        def uniform(self, a: float, b: float) -> float:
            return b

    rng = MaxRng()
    cfg = BackoffConfig(base_s=2.0, max_s=10.0)
    # attempt=3 -> 2*8=16 > 10 -> потолок 10.0; attempt=10 -> тоже 10.0
    assert _compute_backoff_delay(3, cfg, rng) == pytest.approx(10.0)
    assert _compute_backoff_delay(10, cfg, rng) == pytest.approx(10.0)


def test_compute_delay_jitter_within_zero_and_cap() -> None:
    """full-jitter: реальный rng даёт значение в [0, cap]."""
    rng = random.Random(42)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)
    for attempt in range(5):
        cap = min(60.0, 2.0 * (2**attempt))
        delay = _compute_backoff_delay(attempt, cfg, rng)
        assert 0.0 <= delay <= cap
