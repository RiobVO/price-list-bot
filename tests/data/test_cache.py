"""Тесты CatalogCache: cold-start, atomic swap, порог качества, single-flight."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from src.data.cache import CatalogCache
from src.data.models import Catalog, ParseResult, Product


def _product(pid: str) -> Product:
    """Минимальный валидный Product для наполнения каталога в тестах."""
    return Product(
        id=pid,
        category="cat",
        subcategory="sub",
        name_ru="имя",
        name_uz="nom",
        desc_ru=None,
        desc_uz=None,
        price_wholesale=Decimal("100"),
        price_retail=Decimal("150"),
        currency="UZS",
        packaging=None,
        photo=None,
        is_active=True,
    )


def _result(*, valid: int, skipped: int) -> ParseResult:
    """ParseResult с `valid` валидными товарами и счётчиком `skipped` битых строк.

    issues для счётчиков несущественны — порог считается по valid_rows/skipped_rows.
    """
    products = tuple(_product(f"p{i}") for i in range(valid))
    return ParseResult(
        catalog=Catalog.build(products),
        issues=(),
        valid_rows=valid,
        skipped_rows=skipped,
    )


def test_cold_start_snapshot_is_empty() -> None:
    cache = CatalogCache()
    snap = cache.get_snapshot()
    assert snap.catalog is None
    assert snap.updated_at is None
    assert snap.valid_rows == 0
    assert snap.skipped_rows == 0


def test_get_snapshot_returns_same_reference_until_swap() -> None:
    cache = CatalogCache()
    assert cache.get_snapshot() is cache.get_snapshot()


@pytest.mark.asyncio
async def test_try_swap_success_sets_snapshot_with_passed_now() -> None:
    cache = CatalogCache(min_valid_rows=1)
    now = datetime(2026, 5, 31, 12, 0, 0, tzinfo=UTC)
    result = _result(valid=3, skipped=0)

    swapped = await cache.try_swap(result, now=now)

    assert swapped is True
    snap = cache.get_snapshot()
    assert snap.catalog is result.catalog
    assert snap.updated_at == now
    assert snap.valid_rows == 3
    assert snap.skipped_rows == 0


@pytest.mark.asyncio
async def test_try_swap_now_none_uses_utc() -> None:
    cache = CatalogCache(min_valid_rows=1)
    before = datetime.now(UTC)

    swapped = await cache.try_swap(_result(valid=2, skipped=0))

    after = datetime.now(UTC)
    assert swapped is True
    updated_at = cache.get_snapshot().updated_at
    assert updated_at is not None
    assert updated_at.tzinfo == UTC
    assert before <= updated_at <= after


@pytest.mark.asyncio
async def test_try_swap_rejects_when_broken_ratio_above_half() -> None:
    cache = CatalogCache(min_valid_rows=1)
    # 2 валидных / 3 битых => 3/5 = 0.6 > 0.5 => reject, старый (пустой) снимок жив.
    swapped = await cache.try_swap(_result(valid=2, skipped=3))

    assert swapped is False
    snap = cache.get_snapshot()
    assert snap.catalog is None
    assert snap.updated_at is None


@pytest.mark.asyncio
async def test_try_swap_accepts_when_broken_ratio_exactly_half() -> None:
    cache = CatalogCache(min_valid_rows=1)
    # 2 валидных / 2 битых => 2/4 = 0.5, НЕ > 0.5 => swap проходит (граница включительно).
    swapped = await cache.try_swap(_result(valid=2, skipped=2))

    assert swapped is True
    assert cache.get_snapshot().valid_rows == 2


@pytest.mark.asyncio
async def test_try_swap_rejects_when_valid_below_min() -> None:
    cache = CatalogCache(min_valid_rows=5)
    # valid=4 < min=5 => reject даже при нулевой доле битых.
    swapped = await cache.try_swap(_result(valid=4, skipped=0))

    assert swapped is False
    assert cache.get_snapshot().catalog is None


@pytest.mark.asyncio
async def test_try_swap_rejects_empty_catalog() -> None:
    cache = CatalogCache(min_valid_rows=1)
    # valid=0 (пустой каталог) < min=1 => reject; деления на ноль нет.
    swapped = await cache.try_swap(_result(valid=0, skipped=0))

    assert swapped is False
    assert cache.get_snapshot().catalog is None


@pytest.mark.asyncio
async def test_try_swap_keeps_previous_snapshot_on_reject() -> None:
    cache = CatalogCache(min_valid_rows=1)
    good_now = datetime(2026, 5, 31, 10, 0, 0, tzinfo=UTC)
    await cache.try_swap(_result(valid=5, skipped=0), now=good_now)

    # Плохой снимок: доля битых 0.75 => reject, прежний валидный снимок остаётся.
    swapped = await cache.try_swap(_result(valid=1, skipped=3))

    assert swapped is False
    snap = cache.get_snapshot()
    assert snap.valid_rows == 5
    assert snap.updated_at == good_now


@pytest.mark.asyncio
async def test_try_swap_rejects_empty_result_even_when_min_zero() -> None:
    cache = CatalogCache(min_valid_rows=0)
    swapped = await cache.try_swap(_result(valid=0, skipped=0))
    assert swapped is False
    assert cache.get_snapshot().catalog is None  # old (cold-start) snapshot alive


@pytest.mark.asyncio
async def test_try_swap_is_single_flight_serialized() -> None:
    cache = CatalogCache(min_valid_rows=1)

    concurrent = 0
    max_concurrent = 0
    enter_gate = asyncio.Event()  # держит первую корутину внутри секции
    first_inside = asyncio.Event()  # сигнал, что кто-то уже в секции

    async def hook() -> None:
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        if not first_inside.is_set():
            # Первая вошедшая корутина застревает в секции, давая шанс второй
            # войти параллельно, ЕСЛИ сериализации (Lock) нет.
            first_inside.set()
            await enter_gate.wait()
        concurrent -= 1

    # Внедряем наблюдаемый хук в критическую секцию try_swap.
    cache._on_enter_critical = hook

    async def opener() -> bool:
        return await cache.try_swap(_result(valid=3, skipped=0))

    task_a = asyncio.create_task(opener())
    task_b = asyncio.create_task(opener())

    # Дать первой корутине войти в секцию и застрять на enter_gate.
    await first_inside.wait()
    # Дать второй корутине шанс войти (если Lock есть — она ждёт снаружи).
    await asyncio.sleep(0.05)
    # Отпустить первую — обе завершатся.
    enter_gate.set()

    results = await asyncio.gather(task_a, task_b)

    assert list(results) == [True, True]
    # Под Lock одновременно внутри секции только одна корутина.
    assert max_concurrent == 1
