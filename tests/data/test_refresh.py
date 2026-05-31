"""Тесты refresh-loop: backoff-джиттер и фоновый цикл обновления."""

from __future__ import annotations

import asyncio
import dataclasses
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

import pytest

from src.data.fetch import FetchError
from src.data.models import Catalog, ParseResult, SchemaError, Snapshot
from src.data.refresh import BackoffConfig, _compute_backoff_delay, run_refresh_loop


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


# ---------------------------------------------------------------------------
# Тестовые двойники (R2+)
# ---------------------------------------------------------------------------


class RecordingSleeper:
    """async-sleeper: пишет задержки; на stop_after-м вызове бросает CancelledError."""

    def __init__(self, stop_after: int) -> None:
        self.delays: list[float] = []
        self._stop_after = stop_after

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
        if len(self.delays) >= self._stop_after:
            raise asyncio.CancelledError


class FakeCache:
    """Минимальный двойник CatalogCache: get_snapshot синхронно, try_swap пишет вызовы."""

    def __init__(self, snapshot: Snapshot, swap_returns: bool) -> None:
        self._snapshot = snapshot
        self._swap_returns = swap_returns
        self.swap_calls: list[ParseResult] = []

    def get_snapshot(self) -> Snapshot:
        return self._snapshot

    async def try_swap(self, result: ParseResult, *, now: datetime | None = None) -> bool:
        self.swap_calls.append(result)
        if self._swap_returns:
            self._snapshot = Snapshot(
                catalog=result.catalog,
                updated_at=now or datetime.now(UTC),
                valid_rows=result.valid_rows,
                skipped_rows=result.skipped_rows,
            )
        return self._swap_returns


def make_parse_result(valid: int, skipped: int) -> ParseResult:
    """Фабрика ParseResult с пустым Catalog и заданными счётчиками."""
    return ParseResult(
        catalog=Catalog.build([]),
        issues=(),
        valid_rows=valid,
        skipped_rows=skipped,
    )


def live_snapshot() -> Snapshot:
    """Снимок с непустым каталогом (live: catalog is not None)."""
    return Snapshot(
        catalog=Catalog.build([]),
        updated_at=datetime.now(UTC),
        valid_rows=5,
        skipped_rows=0,
    )


def cold_snapshot() -> Snapshot:
    """Cold-start снимок: catalog is None."""
    return Snapshot(catalog=None, updated_at=None, valid_rows=0, skipped_rows=0)


# ---------------------------------------------------------------------------
# R2: happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_fetch_parse_swap_then_sleep_ttl() -> None:
    """Happy: fetch -> parse -> try_swap(True) -> sleep(ttl). Цикл повторяется до cancel."""
    cache = FakeCache(live_snapshot(), swap_returns=True)
    fetch_calls = 0

    async def fetch_fn() -> list[dict[str, str]]:
        nonlocal fetch_calls
        fetch_calls += 1
        return [{"id": "1"}]

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        return make_parse_result(valid=3, skipped=0)

    sleeper = RecordingSleeper(stop_after=2)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache,
            fetch_fn,
            parse_fn,
            ttl_seconds=300.0,
            backoff=cfg,
            sleeper=sleeper,
        )

    assert len(cache.swap_calls) >= 1
    assert sleeper.delays[0] == pytest.approx(300.0)  # после успешного swap -> ttl
    assert fetch_calls >= 1


# ---------------------------------------------------------------------------
# R3: transient FetchError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transient_cold_start_backoff_grows() -> None:
    """Cold-start (catalog is None) + transient FetchError -> растущий backoff-джиттер."""

    class MaxRng(random.Random):
        def uniform(self, a: float, b: float) -> float:
            return b

    cache = FakeCache(cold_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        raise FetchError("503 transient", transient=True)

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise AssertionError("parse не должен вызываться при фейле fetch")

    sleeper = RecordingSleeper(stop_after=3)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache,
            fetch_fn,
            parse_fn,
            ttl_seconds=300.0,
            backoff=cfg,
            sleeper=sleeper,
            rng=MaxRng(),
        )

    # full-jitter cap при MaxRng: attempt 0,1,2 -> 2,4,8 (растёт)
    assert sleeper.delays == [pytest.approx(2.0), pytest.approx(4.0), pytest.approx(8.0)]
    assert cache.swap_calls == []  # swap не звали — fetch упал


@pytest.mark.asyncio
async def test_transient_live_keeps_ttl() -> None:
    """Live (catalog не None) + transient FetchError -> задержка == ttl (не backoff)."""
    cache = FakeCache(live_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        raise FetchError("503 transient", transient=True)

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise AssertionError("parse не должен вызываться")

    sleeper = RecordingSleeper(stop_after=2)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache,
            fetch_fn,
            parse_fn,
            ttl_seconds=300.0,
            backoff=cfg,
            sleeper=sleeper,
        )

    assert sleeper.delays == [pytest.approx(300.0), pytest.approx(300.0)]


# ---------------------------------------------------------------------------
# R4: non-transient propagates + 429 retry_after
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_non_transient_fetch_error_propagates() -> None:
    """non-transient FetchError (401/битый creds) -> не ловится, поднимается наружу."""
    cache = FakeCache(cold_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        raise FetchError("401 unauthorized", transient=False)

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise AssertionError("не вызывается")

    sleeper = RecordingSleeper(stop_after=99)  # не должен сработать
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(FetchError) as ei:
        await run_refresh_loop(
            cache,
            fetch_fn,
            parse_fn,
            ttl_seconds=300.0,
            backoff=cfg,
            sleeper=sleeper,
        )
    assert ei.value.transient is False
    assert sleeper.delays == []  # ни одной задержки — сразу проброс


@pytest.mark.asyncio
async def test_429_retry_after_is_respected_over_jitter() -> None:
    """429: transient + retry_after задан -> delay == retry_after (НЕ джиттер-backoff)."""

    class MaxRng(random.Random):
        def uniform(self, a: float, b: float) -> float:
            return b  # если бы взяли джиттер — было бы != 7.5

    cache = FakeCache(cold_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        raise FetchError("429 rate limited", transient=True, retry_after=7.5)

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise AssertionError("не вызывается")

    sleeper = RecordingSleeper(stop_after=2)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache,
            fetch_fn,
            parse_fn,
            ttl_seconds=300.0,
            backoff=cfg,
            sleeper=sleeper,
            rng=MaxRng(),
        )

    assert sleeper.delays == [pytest.approx(7.5), pytest.approx(7.5)]


# ---------------------------------------------------------------------------
# R5: SchemaError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_error_live_keeps_snapshot_and_sleeps_ttl() -> None:
    """SchemaError при живом каталоге -> снимок держим, try_swap НЕ зван, sleep(ttl)."""
    cache = FakeCache(live_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        return [{"name_ru": "x"}]  # нет required колонки -> parse бросит SchemaError

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise SchemaError("missing required column: id")

    sleeper = RecordingSleeper(stop_after=2)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache,
            fetch_fn,
            parse_fn,
            ttl_seconds=300.0,
            backoff=cfg,
            sleeper=sleeper,
        )

    assert cache.swap_calls == []  # частичный/битый снимок в кэш не кладём
    assert sleeper.delays == [pytest.approx(300.0), pytest.approx(300.0)]


@pytest.mark.asyncio
async def test_schema_error_cold_uses_backoff() -> None:
    """SchemaError на cold-start (нет снимка) -> backoff (как transient cold)."""

    class MaxRng(random.Random):
        def uniform(self, a: float, b: float) -> float:
            return b

    cache = FakeCache(cold_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        return [{"name_ru": "x"}]

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise SchemaError("missing required column: id")

    sleeper = RecordingSleeper(stop_after=2)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache,
            fetch_fn,
            parse_fn,
            ttl_seconds=300.0,
            backoff=cfg,
            sleeper=sleeper,
            rng=MaxRng(),
        )

    assert cache.swap_calls == []
    assert sleeper.delays == [pytest.approx(2.0), pytest.approx(4.0)]


# ---------------------------------------------------------------------------
# R6: CancelledError пробрасывается (контрактный тест, see honesty note in plan)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancelled_error_from_fetch_propagates() -> None:
    """CancelledError (отмена во время fetch) пробрасывается, НЕ уходит в backoff."""
    cache = FakeCache(cold_snapshot(), swap_returns=False)
    fetch_calls = 0

    async def fetch_fn() -> list[dict[str, str]]:
        nonlocal fetch_calls
        fetch_calls += 1
        raise asyncio.CancelledError

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise AssertionError("не вызывается")

    sleeper = RecordingSleeper(stop_after=99)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache,
            fetch_fn,
            parse_fn,
            ttl_seconds=300.0,
            backoff=cfg,
            sleeper=sleeper,
        )

    assert fetch_calls == 1  # отмена на первом fetch, без повторов
    assert sleeper.delays == []  # backoff не сработал


# ---------------------------------------------------------------------------
# R7: refresh_done лог с обязательными полями (контрактный тест, see honesty note)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_done_logged_with_required_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """После успешного swap логируется refresh_done со всеми полями summary."""
    import logging as _logging

    cache = FakeCache(cold_snapshot(), swap_returns=True)

    async def fetch_fn() -> list[dict[str, str]]:
        return [{"id": "1"}]

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        return make_parse_result(valid=7, skipped=2)

    sleeper = RecordingSleeper(stop_after=1)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with caplog.at_level(_logging.INFO, logger="src.data.refresh"):
        with pytest.raises(asyncio.CancelledError):
            await run_refresh_loop(
                cache,
                fetch_fn,
                parse_fn,
                ttl_seconds=300.0,
                backoff=cfg,
                sleeper=sleeper,
            )

    recs = [r for r in caplog.records if r.message == "refresh_done"]
    assert len(recs) == 1
    rec = recs[0]
    assert rec.rows_total == 9
    assert rec.valid == 7
    assert rec.skipped == 2
    assert rec.schema_ok is True
    assert isinstance(rec.duration_ms, float)
    assert rec.snapshot_age_s >= 0.0
