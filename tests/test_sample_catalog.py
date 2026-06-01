"""Тест встроенного демо-каталога: парсится в непустой валидный каталог."""

from __future__ import annotations

from src.config import Settings
from src.data.sample import SAMPLE_ROWS
from src.main import build_parse_fn


def test_sample_rows_parse_into_catalog(bot_settings: Settings) -> None:
    result = build_parse_fn(bot_settings)(SAMPLE_ROWS)
    assert result.valid_rows == len(SAMPLE_ROWS)
    categories = {p.category for p in result.catalog.products}
    assert {"Напитки", "Еда"} <= categories
    # пустая subcategory у id=5 деградирует в fallback, строка не теряется
    assert any(p.subcategory == "Прочее" for p in result.catalog.products)
