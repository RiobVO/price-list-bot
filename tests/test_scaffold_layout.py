"""Проверка инвариантов каркаса: дерево каталогов и пакеты-маркеры на месте."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

EXPECTED_DIRS = (
    "src/data",
    "src/services",
    "src/bot/handlers",
    "src/bot/middlewares",
    "src/locales",
    "tests/data",
    "tests/services",
    "tests/bot",
    "tests/fixtures",
    "docs/adr",
)

EXPECTED_INIT = (
    "src/__init__.py",
    "src/data/__init__.py",
    "src/services/__init__.py",
    "src/bot/__init__.py",
    "src/bot/handlers/__init__.py",
    "src/bot/middlewares/__init__.py",
    "src/locales/__init__.py",
    "tests/__init__.py",
    "tests/data/__init__.py",
    "tests/services/__init__.py",
    "tests/bot/__init__.py",
)


@pytest.mark.parametrize("rel", EXPECTED_DIRS)
def test_directory_exists(rel: str) -> None:
    assert (ROOT / rel).is_dir(), f"missing directory: {rel}"


@pytest.mark.parametrize("rel", EXPECTED_INIT)
def test_init_marker_exists(rel: str) -> None:
    assert (ROOT / rel).is_file(), f"missing package marker: {rel}"
