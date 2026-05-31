"""Грязный I/O-слой: чтение строк из Google Sheets через gspread.

Граница типов: всё, что приходит из gspread (Any), здесь приводится к str.
Чистое ядро (parse) этот модуль НЕ импортирует.
"""

from __future__ import annotations

from typing import Any


class FetchError(Exception):
    """Ошибка чтения данных из Google Sheets.

    transient=True — временная (429/5xx/таймаут/сеть): refresh уходит в backoff
    или уважает retry_after. transient=False — фатальная (401/403/404/битый creds):
    refresh пробрасывает наружу, main завершает процесс с exit(1).
    """

    def __init__(self, message: str, *, transient: bool, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.transient = transient
        self.retry_after = retry_after


def _cell_to_str(value: Any) -> str:
    """Привести значение ячейки к str. None -> пустая строка (а не 'None')."""
    if value is None:
        return ""
    return str(value)


def fetch_rows(client: object, spreadsheet_id: str, worksheet_name: str) -> list[dict[str, str]]:
    """Прочитать строки листа Google Sheets, приведя каждую ячейку к str.

    Граница типов: gspread отдаёт int/float/bool/None — здесь всё становится str,
    чтобы чистое ядро parse работало только со строками.
    """
    spreadsheet = client.open_by_key(spreadsheet_id)  # type: ignore[attr-defined]
    worksheet = spreadsheet.worksheet(worksheet_name)
    records: list[dict[str, Any]] = worksheet.get_all_records()
    return [{key: _cell_to_str(value) for key, value in record.items()} for record in records]
