"""Тесты грязного I/O-слоя fetch поверх gspread."""

from __future__ import annotations

from src.data.fetch import FetchError


def test_fetch_error_stores_transient_and_retry_after() -> None:
    """FetchError хранит message, transient-флаг и retry_after (kwargs-only)."""
    err = FetchError("rate limited", transient=True, retry_after=30.0)
    assert str(err) == "rate limited"
    assert err.transient is True
    assert err.retry_after == 30.0


def test_fetch_error_retry_after_defaults_to_none() -> None:
    """retry_after по умолчанию None; transient остаётся обязательным kwarg."""
    err = FetchError("forbidden", transient=False)
    assert err.transient is False
    assert err.retry_after is None
