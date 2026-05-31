"""Тесты настройки логирования: JSON-формат, extra-поля, уровень."""

from __future__ import annotations

import json
import logging

from src.logging_setup import JsonFormatter, setup_logging


def test_json_formatter_emits_parseable_with_extra() -> None:
    rec = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="refresh_done",
        args=(),
        exc_info=None,
    )
    rec.valid = 7  # extra
    payload = json.loads(JsonFormatter().format(rec))
    assert payload["message"] == "refresh_done"
    assert payload["level"] == "INFO"
    assert payload["valid"] == 7


def test_setup_logging_sets_level_and_single_handler() -> None:
    setup_logging(level="WARNING", fmt="json")
    root = logging.getLogger()
    assert root.level == logging.WARNING
    assert len(root.handlers) == 1
    setup_logging(level="INFO", fmt="json")  # повторный вызов не плодит хендлеры
    assert len(logging.getLogger().handlers) == 1
