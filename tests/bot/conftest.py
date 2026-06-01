"""Фикстуры bot-тестов (расширяются в группах 6–7)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from src.services.models import Page


@pytest.fixture
def make_page() -> Callable[..., Page[Any]]:
    def _make(**over: Any) -> Page[Any]:
        base: dict[str, Any] = {
            "items": (),
            "page": 1,
            "total_pages": 1,
            "has_prev": False,
            "has_next": False,
        }
        base.update(over)
        return Page(**base)

    return _make
