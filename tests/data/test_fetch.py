"""Тесты грязного I/O-слоя fetch поверх gspread."""

from __future__ import annotations

import pytest
import requests
from gspread.exceptions import APIError

from src.data.fetch import FetchError, fetch_rows


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


class _FakeWorksheet:
    """Двойник gspread Worksheet: возвращает заранее заданные записи."""

    def __init__(self, records: list[dict[str, object]]) -> None:
        self._records = records

    def get_all_records(self) -> list[dict[str, object]]:
        return self._records


class _FakeSpreadsheet:
    """Двойник gspread Spreadsheet: отдаёт лист по имени, проверяет имя."""

    def __init__(self, worksheet: _FakeWorksheet, expected_title: str) -> None:
        self._worksheet = worksheet
        self._expected_title = expected_title

    def worksheet(self, title: str) -> _FakeWorksheet:
        assert title == self._expected_title
        return self._worksheet


class _FakeClient:
    """Двойник gspread Client: отдаёт книгу по ключу, проверяет ключ."""

    def __init__(self, spreadsheet: _FakeSpreadsheet, expected_key: str) -> None:
        self._spreadsheet = spreadsheet
        self._expected_key = expected_key

    def open_by_key(self, key: str) -> _FakeSpreadsheet:
        assert key == self._expected_key
        return self._spreadsheet


def _make_client(records: list[dict[str, object]]) -> _FakeClient:
    ws = _FakeWorksheet(records)
    sheet = _FakeSpreadsheet(ws, expected_title="products")
    return _FakeClient(sheet, expected_key="SHEET_KEY")


def test_fetch_rows_coerces_every_cell_to_str() -> None:
    """int/float/bool/None приводятся к str; None -> пустая строка, не 'None'."""
    records: list[dict[str, object]] = [
        {"id": "A1", "price": 120000, "ratio": 12.5, "is_active": True, "desc": None},
    ]
    client = _make_client(records)

    rows = fetch_rows(client, "SHEET_KEY", "products")

    assert rows == [
        {"id": "A1", "price": "120000", "ratio": "12.5", "is_active": "True", "desc": ""},
    ]
    # Тип возврата — именно str по каждой ячейке.
    assert all(isinstance(v, str) for row in rows for v in row.values())


def test_fetch_rows_returns_empty_list_for_empty_sheet() -> None:
    """Лист с заголовком, но без строк данных -> пустой list (НЕ ошибка)."""
    client = _make_client([])
    assert fetch_rows(client, "SHEET_KEY", "products") == []


class _FakeResponse:
    """Двойник requests.Response: только то, что читает классификатор fetch."""

    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


class _FakeAPIError(APIError):
    """Двойник gspread.APIError без парсинга JSON-тела.

    Реальный __init__ лезет в response.json() — обходим, оставляя только .response.
    """

    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        # НЕ вызываем APIError.__init__ — он требует валидный JSON; нам нужен только .response.
        Exception.__init__(self, f"api error {status_code}")
        self.response = _FakeResponse(status_code, headers)  # type: ignore[assignment]


class _RaisingWorksheet:
    """Двойник Worksheet: get_all_records бросает заданное исключение."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def get_all_records(self) -> list[dict[str, object]]:
        raise self._exc


def _client_raising(exc: BaseException) -> _FakeClient:
    ws = _RaisingWorksheet(exc)
    sheet = _FakeSpreadsheet(ws, expected_title="products")  # type: ignore[arg-type]
    return _FakeClient(sheet, expected_key="SHEET_KEY")


def test_fetch_rows_429_is_transient_with_retry_after() -> None:
    """429 -> FetchError(transient=True, retry_after=float(Retry-After))."""
    client = _client_raising(_FakeAPIError(429, {"Retry-After": "30"}))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is True
    assert exc_info.value.retry_after == 30.0


def test_fetch_rows_429_without_retry_after_header() -> None:
    """429 без заголовка Retry-After -> transient=True, retry_after=None."""
    client = _client_raising(_FakeAPIError(429))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is True
    assert exc_info.value.retry_after is None


@pytest.mark.parametrize("status", [401, 403, 404])
def test_fetch_rows_auth_errors_are_non_transient(status: int) -> None:
    """401/403/404 -> FetchError(transient=False) (main завершит процесс)."""
    client = _client_raising(_FakeAPIError(status))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is False
    assert exc_info.value.retry_after is None


def test_fetch_rows_5xx_is_transient() -> None:
    """5xx (например 500) -> FetchError(transient=True) без retry_after."""
    client = _client_raising(_FakeAPIError(500))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is True
    assert exc_info.value.retry_after is None


def test_fetch_rows_network_error_is_transient() -> None:
    """Сетевой сбой (requests.ConnectionError) -> FetchError(transient=True)."""
    client = _client_raising(requests.exceptions.ConnectionError("conn reset"))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is True
    assert exc_info.value.retry_after is None


def test_fetch_rows_timeout_is_transient() -> None:
    """Таймаут (requests.Timeout) -> FetchError(transient=True)."""
    client = _client_raising(requests.exceptions.Timeout("read timed out"))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is True
