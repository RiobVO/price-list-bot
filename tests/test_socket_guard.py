"""Проверка socket-guard: реальная сеть запрещена, монипуляция не ломает offline-логику."""

from __future__ import annotations

import socket

import pytest


def test_real_connect_is_blocked() -> None:
    """Попытка реального TCP-коннекта должна возбуждать RuntimeError от socket-guard."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(RuntimeError, match="network access disabled"):
        sock.connect(("93.184.216.34", 80))  # example.com — реальный адрес, коннект запрещён


def test_creating_socket_object_is_allowed() -> None:
    """Создание объекта socket разрешено — запрещён только connect.

    Offline-фикстуры и заглушки не ломаются.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    assert sock is not None
    sock.close()
