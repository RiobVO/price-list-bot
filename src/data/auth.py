"""Сборка gspread-клиента из секрета сервис-аккаунта.

РОВНО один способ доставки (валидатор Settings гарантирует): путь к файлу
(GOOGLE_APPLICATION_CREDENTIALS) ИЛИ base64-JSON (GOOGLE_CREDENTIALS_B64).
gspread импортируется только здесь — граница грязного I/O.
"""

from __future__ import annotations

import base64
import binascii
import json

import gspread

from src.config import Settings


def build_gspread_client(settings: Settings) -> gspread.Client:
    """Создать авторизованный gspread.Client. base64 декодируется в JSON-dict."""
    path = settings.GOOGLE_APPLICATION_CREDENTIALS
    if path and path.strip():
        return gspread.service_account(filename=path)

    b64 = settings.GOOGLE_CREDENTIALS_B64
    assert b64 is not None  # гарантировано валидатором Settings
    try:
        raw = base64.b64decode(b64.get_secret_value(), validate=True)
        info = json.loads(raw)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"invalid GOOGLE_CREDENTIALS_B64: {exc}") from exc
    return gspread.service_account_from_dict(info)
