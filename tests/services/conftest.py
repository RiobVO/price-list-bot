"""Фикстуры services-тестов: фабрика Product с валидными дефолтами."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from src.data.models import Product


@pytest.fixture
def make_product() -> Callable[..., Product]:
    """Фабрика Product: дефолты валидны, overrides переопределяют поля."""

    def _make(**overrides: object) -> Product:
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
        base.update(overrides)
        return Product(**base)  # type: ignore[arg-type]

    return _make
