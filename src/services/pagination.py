"""Чистая пагинация: срез страницы + флаги навигации."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from src.services.models import Page

T = TypeVar("T")


def paginate(items: Sequence[T], page: int, page_size: int) -> Page[T]:
    """Вернуть страницу 1-based. page клампится в [1, total_pages].

    Пустой items → одна пустая страница (total_pages=1). page_size >= 1 (контракт config).
    """
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    current = min(max(page, 1), total_pages)
    start = (current - 1) * page_size
    chunk = tuple(items[start : start + page_size])
    return Page(
        items=chunk,
        page=current,
        total_pages=total_pages,
        has_prev=current > 1,
        has_next=current < total_pages,
    )
