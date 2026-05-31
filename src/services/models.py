"""View-модели слоя services и единый исход запроса по id (ViewResult).

Чистый модуль типов: без зависимостей на data/bot/aiogram.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeAlias, TypeVar

Lang = Literal["ru", "uz"]

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Успешный исход запроса по id: несёт готовую view-модель."""

    value: T


@dataclass(frozen=True, slots=True)
class Stale:
    """Протухший callback-id: «каталог обновился, откройте заново» + возврат в меню."""


# Документационный и аннотационный alias. В сигнатурах допустимы обе формы:
# ViewResult[X] и явная Ok[X] | Stale — они эквивалентны.
ViewResult: TypeAlias = Ok[T] | Stale


@dataclass(frozen=True, slots=True)
class CategoryItem:
    """Пункт меню категории. id — стабильный хеш для callback; title — сырое имя категории."""

    id: str
    title: str


@dataclass(frozen=True, slots=True)
class SubcategoryItem:
    """Пункт меню подкатегории. id — хеш пары (category, subcategory)."""

    id: str
    title: str


@dataclass(frozen=True, slots=True)
class ProductListItem:
    """Строка списка товаров. id — хеш product.id; title — name_{lang} с фолбэком."""

    id: str
    title: str


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    """Страница пагинации (1-based) с флагами навигации."""

    items: tuple[T, ...]
    page: int
    total_pages: int
    has_prev: bool
    has_next: bool


@dataclass(frozen=True, slots=True)
class ProductCard:
    """Готовая карточка товара: локализованный текст (≤ лимита) + сырой photo (URL/file_id)."""

    text: str
    photo: str | None
