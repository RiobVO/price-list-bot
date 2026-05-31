"""Глобальные фикстуры тестов: запрет реальной сети (socket-guard)."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest

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
