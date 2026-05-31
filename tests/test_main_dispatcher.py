"""Тесты сборки Dispatcher и выбора транспорта по USE_WEBHOOK."""

from __future__ import annotations

from collections.abc import Callable

from src.config import Settings
from src.data.models import Product
from src.main import build_dispatcher, choose_transport
from src.services.catalog import CatalogService
from src.services.language import LanguageStore


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "BOT_TOKEN": "1:a",
        "SPREADSHEET_ID": "sid",
        "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/sa.json",
        "_env_file": None,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def test_dispatcher_has_workflow_data_and_routers(
    seed_service: Callable[[list[Product]], CatalogService],
    make_product: Callable[..., Product],
) -> None:
    service = seed_service([make_product()])
    store = LanguageStore()
    dp = build_dispatcher(service, store, _settings())
    assert dp["service"] is service
    assert dp["lang_store"] is store
    assert dp.sub_routers  # роутеры подключены


def test_choose_transport_polling_vs_webhook() -> None:
    assert choose_transport(_settings(USE_WEBHOOK=False)) == "polling"
    assert choose_transport(_settings(USE_WEBHOOK=True)) == "webhook"
