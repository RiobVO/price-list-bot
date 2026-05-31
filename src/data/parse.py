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

_FATAL_FIELDS: Final[tuple[str, ...]] = ("id", "category", "name_ru", "name_uz")


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


def _is_battered(row: Mapping[str, str]) -> bool:
    """Строка фатально битая, если любое из id/category/name_ru/name_uz пусто."""
    return any(not row.get(field, "").strip() for field in _FATAL_FIELDS)


def _resolve_is_active(raw: str, row_number: int, product_id: str) -> tuple[bool, RowIssue | None]:
    """Разрешить is_active: пусто/нераспозн -> True+issue; явный bool -> значение без issue."""
    if not raw.strip():
        return True, RowIssue(
            row_number=row_number,
            product_id=product_id,
            reason="empty_is_active",
            detail="empty is_active -> visible",
        )
    parsed = parse_bool(raw)
    if parsed is None:
        return True, RowIssue(
            row_number=row_number,
            product_id=product_id,
            reason="unrecognized_bool",
            detail=f"is_active={raw!r} -> visible",
        )
    return parsed, None


def _resolve_currency(
    raw: str,
    row_number: int,
    product_id: str,
    *,
    default_currency: str,
    allowed_currencies: frozenset[str],
) -> tuple[str, RowIssue | None]:
    """Пусто -> default+empty_currency; не из allowed -> default+unrecognized; иначе как есть."""
    value = raw.strip()
    if not value:
        return default_currency, RowIssue(
            row_number=row_number,
            product_id=product_id,
            reason="empty_currency",
            detail="empty currency -> default",
        )
    if value not in allowed_currencies:
        return default_currency, RowIssue(
            row_number=row_number,
            product_id=product_id,
            reason="unrecognized_currency",
            detail=f"currency={value!r} not in allowed",
        )
    return value, None


def _build_product(
    row: Mapping[str, str],
    row_number: int,
    *,
    default_currency: str,
    fallback_subcategory: str,
    allowed_currencies: frozenset[str],
) -> tuple[Product, list[RowIssue]]:
    """Собрать Product из не-битой строки + деградационные RowIssue."""
    row_issues: list[RowIssue] = []
    product_id = row["id"].strip()

    price_w = parse_number(row["price_wholesale"])
    if price_w is None:
        row_issues.append(
            RowIssue(
                row_number=row_number,
                product_id=product_id,
                reason="bad_number",
                detail=f"price_wholesale={row['price_wholesale']!r}",
            )
        )
    price_r = parse_number(row["price_retail"])
    if price_r is None:
        row_issues.append(
            RowIssue(
                row_number=row_number,
                product_id=product_id,
                reason="bad_number",
                detail=f"price_retail={row['price_retail']!r}",
            )
        )

    currency, currency_issue = _resolve_currency(
        row["currency"],
        row_number,
        product_id,
        default_currency=default_currency,
        allowed_currencies=allowed_currencies,
    )
    if currency_issue is not None:
        row_issues.append(currency_issue)

    subcategory_raw = row["subcategory"].strip()
    if subcategory_raw:
        subcategory = subcategory_raw
    else:
        subcategory = fallback_subcategory
        row_issues.append(
            RowIssue(
                row_number=row_number,
                product_id=product_id,
                reason="empty_subcategory",
                detail="empty subcategory -> fallback",
            )
        )

    is_active, active_issue = _resolve_is_active(row["is_active"], row_number, product_id)
    if active_issue is not None:
        row_issues.append(active_issue)

    product = Product(
        id=product_id,
        category=row["category"].strip(),
        subcategory=subcategory,
        name_ru=row["name_ru"].strip(),
        name_uz=row["name_uz"].strip(),
        desc_ru=_opt(row, "desc_ru"),
        desc_uz=_opt(row, "desc_uz"),
        price_wholesale=price_w,
        price_retail=price_r,
        currency=currency,
        packaging=_opt(row, "packaging"),
        photo=_opt(row, "photo"),
        is_active=is_active,
    )
    return product, row_issues


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
    skipped = 0
    for index, row in enumerate(normalized):
        row_number = index + 1
        if _is_battered(row):
            skipped += 1
            issues.append(
                RowIssue(
                    row_number=row_number,
                    product_id=(row.get("id") or "").strip() or None,
                    reason="missing_required",
                    detail="empty id/category/name_ru/name_uz",
                )
            )
            continue
        product, row_issues = _build_product(
            row,
            row_number,
            default_currency=default_currency,
            fallback_subcategory=fallback_subcategory,
            allowed_currencies=allowed_currencies,
        )
        products.append(product)
        issues.extend(row_issues)

    catalog = Catalog.build(products)
    return ParseResult(
        catalog=catalog,
        issues=tuple(issues),
        valid_rows=len(products),
        skipped_rows=skipped,
    )
