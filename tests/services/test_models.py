"""Тесты view-моделей и исхода ViewResult слоя services."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.services.models import (
    CategoryItem,
    Ok,
    Page,
    ProductCard,
    ProductListItem,
    Stale,
    SubcategoryItem,
)


def test_ok_carries_value() -> None:
    ok = Ok(value=(1, 2, 3))
    assert ok.value == (1, 2, 3)


def test_ok_is_frozen() -> None:
    ok: Ok[int] = Ok(value=1)
    with pytest.raises(FrozenInstanceError):
        ok.value = 2  # type: ignore[misc]


def test_stale_instances_are_value_equal() -> None:
    """Stale — пустой frozen-маркер протухания: два экземпляра равны по значению."""
    assert Stale() == Stale()


def test_view_items_hold_id_and_title() -> None:
    assert CategoryItem(id="ab12", title="Напитки").title == "Напитки"
    assert SubcategoryItem(id="cd34", title="Соки").id == "cd34"
    assert ProductListItem(id="ef56", title="Сок яблочный").title == "Сок яблочный"


def test_view_items_are_frozen() -> None:
    item = CategoryItem(id="ab12", title="Напитки")
    with pytest.raises(FrozenInstanceError):
        item.title = "Еда"  # type: ignore[misc]


def test_page_holds_items_and_navigation_flags() -> None:
    page: Page[CategoryItem] = Page(
        items=(CategoryItem(id="a", title="A"),),
        page=1,
        total_pages=3,
        has_prev=False,
        has_next=True,
    )
    assert page.items[0].title == "A"
    assert page.page == 1
    assert page.total_pages == 3
    assert page.has_prev is False
    assert page.has_next is True


def test_product_card_holds_text_and_optional_photo() -> None:
    card = ProductCard(text="Сок\n\nОпт: 100 сум", photo=None)
    assert card.text.startswith("Сок")
    assert card.photo is None
