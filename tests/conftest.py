"""Глобальные фикстуры тестов: запрет реальной сети (socket-guard)."""
from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _block_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Блокировать любой реальный TCP-коннект в тестах.

    Создание сокетов разрешено (offline-фикстуры и заглушки их используют),
    запрещён только исходящий ``connect`` — гарантия, что тесты не ходят в сеть.
    """

    def _guard(self: socket.socket, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("network access disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", _guard)
    yield
