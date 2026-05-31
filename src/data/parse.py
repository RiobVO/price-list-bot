"""Чистый парсер строк листа в ParseResult. Без сети/env/gspread/aiogram."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from src.data.coerce import parse_bool, parse_number
from src.data.models import Catalog, ParseResult, Product, RowIssue, SchemaError

# Обязательные колонки: их отсутствие в непустой схеме -> SchemaError.
_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "id",
        "category",
        "subcategory",
        "name_ru",
        "name_uz",
        "price_wholesale",
        "price_retail",
        "currency",
        "is_active",
    }
)
# Опциональные: если колонки нет -> поле None, без ошибки.
_OPTIONAL_COLUMNS: Final[frozenset[str]] = frozenset({"desc_ru", "desc_uz", "packaging", "photo"})


def normalize_headers(row: Mapping[str, str]) -> dict[str, str]:
    """Нормализовать ключи (strip+lower). Лишние колонки остаются (игнор позже)."""
    return {key.strip().lower(): value for key, value in row.items()}


def _resolve_required(first_row: Mapping[str, str]) -> None:
    """Проверить наличие всех required колонок. Иначе SchemaError."""
    present = set(first_row.keys())
    missing = _REQUIRED_COLUMNS - present
    if missing:
        raise SchemaError(f"missing required columns: {sorted(missing)}")


def _opt(row: Mapping[str, str], key: str) -> str | None:
    """Опциональное строковое поле: пусто/whitespace -> None, иначе strip-значение."""
    value = row.get(key, "").strip()
    return value or None


def _build_valid_product(row: Mapping[str, str]) -> Product:
    """Собрать Product из нормализованной строки (skeleton: без деградаций)."""
    price_w = parse_number(row["price_wholesale"])
    price_r = parse_number(row["price_retail"])
    return Product(
        id=row["id"].strip(),
        category=row["category"].strip(),
        subcategory=row["subcategory"].strip(),
        name_ru=row["name_ru"].strip(),
        name_uz=row["name_uz"].strip(),
        desc_ru=_opt(row, "desc_ru"),
        desc_uz=_opt(row, "desc_uz"),
        price_wholesale=price_w,
        price_retail=price_r,
        currency=row["currency"].strip(),
        packaging=_opt(row, "packaging"),
        photo=_opt(row, "photo"),
        is_active=bool(parse_bool(row["is_active"])),
    )


def parse(
    rows: Sequence[Mapping[str, str]],
    *,
    default_currency: str,
    fallback_subcategory: str,
    allowed_currencies: frozenset[str],
) -> ParseResult:
    """Распарсить строки листа в ParseResult. Чистая. БРОСАЕТ SchemaError при битой схеме."""
    if not rows:
        return ParseResult(catalog=Catalog.build(()), issues=(), valid_rows=0, skipped_rows=0)

    normalized = [normalize_headers(row) for row in rows]
    _resolve_required(normalized[0])

    products: list[Product] = []
    issues: list[RowIssue] = []
    for row in normalized:
        product = _build_valid_product(row)
        products.append(product)

    catalog = Catalog.build(products)
    return ParseResult(
        catalog=catalog,
        issues=tuple(issues),
        valid_rows=len(products),
        skipped_rows=len(normalized) - len(products),
    )
