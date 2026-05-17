"""Тесты чистой пагинации: clamp, total_pages, флаги навигации."""

from __future__ import annotations

from src.services.pagination import paginate


def test_empty_yields_single_empty_page() -> None:
    page = paginate(list[int](), page=1, page_size=8)
    assert page.items == ()
    assert page.total_pages == 1
    assert page.page == 1
    assert page.has_prev is False
    assert page.has_next is False


def test_exact_one_page() -> None:
    page = paginate(list(range(8)), page=1, page_size=8)
    assert page.items == tuple(range(8))
    assert page.total_pages == 1
    assert page.has_next is False


def test_two_pages_first() -> None:
    page = paginate(list(range(9)), page=1, page_size=8)
    assert page.items == tuple(range(8))
    assert page.total_pages == 2
    assert page.has_prev is False
    assert page.has_next is True


def test_two_pages_second_partial() -> None:
    page = paginate(list(range(9)), page=2, page_size=8)
    assert page.items == (8,)
    assert page.page == 2
    assert page.has_prev is True
    assert page.has_next is False


def test_page_above_range_clamps_to_last() -> None:
    page = paginate(list(range(9)), page=99, page_size=8)
    assert page.page == 2
    assert page.items == (8,)


def test_page_below_one_clamps_to_first() -> None:
    page = paginate(list(range(9)), page=0, page_size=8)
    assert page.page == 1
    assert page.items == tuple(range(8))
