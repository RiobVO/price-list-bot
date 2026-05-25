"""Глобальные фикстуры тестов: запрет реальной сети (socket-guard) + общие фабрики."""

from __future__ import annotations

import socket
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from src.config import Settings
from src.data.cache import CatalogCache
from src.data.models import Catalog, Product, Snapshot
from src.services.catalog import CatalogService

_LOOPBACK = ("127.0.0.1", "::1", "localhost")


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Блокировать любой реальный TCP-коннект в тестах.

    Создание сокетов разрешено (offline-фикстуры и заглушки их используют),
    запрещён только исходящий ``connect`` к внешним адресам. Loopback-соединения
    (127.0.0.1, ::1) разрешены — они нужны asyncio.ProactorEventLoop на Windows.
    """

    _real_connect = socket.socket.connect

    def _guard(self: socket.socket, address: Any, **kwargs: Any) -> None:
        host = address[0] if isinstance(address, (tuple, list)) else address
        if host in _LOOPBACK:
            return _real_connect(self, address, **kwargs)
        raise RuntimeError("network access disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", _guard)
    yield


@pytest.fixture
def make_product() -> Callable[..., Product]:
    """Фабрика Product с валидными дефолтами; overrides переопределяют поля."""

    def _make(**over: object) -> Product:
        base: dict[str, object] = {
            "id": "p1",
            "category": "Напитки",
            "subcategory": "Соки",
            "name_ru": "Сок",
            "name_uz": "Sharbat",
            "desc_ru": None,
            "desc_uz": None,
            "price_wholesale": Decimal("100"),
            "price_retail": Decimal("120"),
            "currency": "UZS",
            "packaging": None,
            "photo": None,
            "is_active": True,
        }
        base.update(over)
        return Product(**base)  # type: ignore[arg-type]

    return _make


@pytest.fixture
def bot_settings() -> Settings:
    """Валидные Settings для тестов (ровно один способ creds, маленький PAGE_SIZE)."""
    return Settings(  # type: ignore[call-arg]
        BOT_TOKEN="123:abc",  # type: ignore[arg-type]
        SPREADSHEET_ID="sid",
        GOOGLE_APPLICATION_CREDENTIALS="/tmp/sa.json",
        PAGE_SIZE=2,
        _env_file=None,
    )


@pytest.fixture
def seed_service(bot_settings: Settings) -> Callable[[list[Product]], CatalogService]:
    """CatalogService над засеянным снимком (без сети/try_swap — тест-инфраструктура)."""

    def _seed(products: list[Product]) -> CatalogService:
        cache = CatalogCache(min_valid_rows=1)
        cache._snapshot = Snapshot(  # noqa: SLF001
            catalog=Catalog.build(products),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            valid_rows=len(products),
            skipped_rows=0,
        )
        return CatalogService(cache, bot_settings)

    return _seed
