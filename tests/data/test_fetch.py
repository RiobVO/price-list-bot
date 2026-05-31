"""Тесты грязного I/O-слоя fetch поверх gspread."""

from __future__ import annotations

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
