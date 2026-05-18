"""Проверка тест-фабрики make_product (общая инфраструктура services-тестов)."""

from __future__ import annotations

from collections.abc import Callable

from src.data.models import Product


def test_make_product_defaults(make_product: Callable[..., Product]) -> None:
    p = make_product()
    assert p.id == "p1"
    assert p.is_active is True
    assert p.currency == "UZS"


def test_make_product_overrides(make_product: Callable[..., Product]) -> None:
    p = make_product(id="x", price_retail=None, is_active=False)
    assert p.id == "x"
    assert p.price_retail is None
    assert p.is_active is False
