"""Тесты сборки gspread-клиента: путь к файлу vs base64, ошибка декодирования."""

from __future__ import annotations

import base64
import json

import gspread
import pytest

from src.config import Settings
from src.data import auth


def _settings(**over: object) -> Settings:
    base: dict[str, object] = {
        "BOT_TOKEN": "1:a",
        "SPREADSHEET_ID": "sid",
        "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/sa.json",
        "_env_file": None,
    }
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def test_uses_file_path(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_service_account(filename: str) -> str:
        seen["path"] = filename
        return "CLIENT"

    monkeypatch.setattr(gspread, "service_account", fake_service_account)
    client = auth.build_gspread_client(_settings())
    assert client == "CLIENT"  # type: ignore[comparison-overlap]
    assert seen["path"] == "/tmp/sa.json"


def test_uses_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    creds = {"type": "service_account", "project_id": "x"}
    b64 = base64.b64encode(json.dumps(creds).encode()).decode()
    seen: dict[str, object] = {}

    def fake_from_dict(info: dict[str, object]) -> str:
        seen["info"] = info
        return "CLIENT"

    monkeypatch.setattr(gspread, "service_account_from_dict", fake_from_dict)
    s = _settings(GOOGLE_APPLICATION_CREDENTIALS=None, GOOGLE_CREDENTIALS_B64=b64)
    client = auth.build_gspread_client(s)
    assert client == "CLIENT"  # type: ignore[comparison-overlap]
    assert seen["info"] == creds


def test_bad_base64_raises_valueerror() -> None:
    s = _settings(GOOGLE_APPLICATION_CREDENTIALS=None, GOOGLE_CREDENTIALS_B64="not-base64-!!!")
    with pytest.raises(ValueError):
        auth.build_gspread_client(s)
