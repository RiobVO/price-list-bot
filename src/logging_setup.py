"""Структурное логирование в stdout: JSON (по умолчанию) или текст.

Поля refresh-summary (valid/skipped/duration_ms/snapshot_age_s/schema_ok) приходят
через logging extra и попадают в JSON автоматически.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

# Стандартные атрибуты LogRecord — всё, что вне их, считаем extra.
_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Сериализует LogRecord в одну JSON-строку с message/level/logger + extra."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(*, level: str = "INFO", fmt: str = "json") -> None:
    """Настроить корневой логгер: stdout + один хендлер, идемпотентно."""
    handler: logging.Handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
