"""Тесты сборочных функций main: parse_fn применяет конфиг, fetch_fn — async-адаптер."""

from __future__ import annotations

import pytest

from src.config import Settings
from src.main import build_fetch_fn, build_parse_fn


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "BOT_TOKEN": "1:a",
        "SPREADSHEET_ID": "sid",
        "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/sa.json",
        "CURRENCIES": "UZS,USD",
        "DEFAULT_CURRENCY": "UZS",
        "FALLBACK_SUBCATEGORY": "Прочее",
        "_env_file": None,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def test_parse_fn_applies_currency_and_fallback() -> None:
    parse_fn = build_parse_fn(_settings())
    rows = [
        {
            "id": "1",
            "category": "Напитки",
            "name_ru": "Сок",
            "name_uz": "S",
            "price_wholesale": "100",
            "price_retail": "120",
            "is_active": "TRUE",
            "subcategory": "",
            "currency": "",
        }
    ]
    result = parse_fn(rows)
    product = result.catalog.products[0]
    assert product.subcategory == "Прочее"  # пустая subcategory → fallback
    assert product.currency == "UZS"  # пустая currency → default


@pytest.mark.asyncio
async def test_fetch_fn_runs_sync_fetch_in_thread() -> None:
    calls: list[tuple[object, str, str]] = []

    def fake_fetch(client: object, sid: str, sheet: str) -> list[dict[str, str]]:
        calls.append((client, sid, sheet))
        return [{"id": "1"}]

    fetch_fn = build_fetch_fn("CLIENT", _settings(SHEET_NAME="products"), fetch=fake_fetch)
    rows = await fetch_fn()
    assert rows == [{"id": "1"}]
    assert calls == [("CLIENT", "sid", "products")]
