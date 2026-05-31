"""Грязный I/O-слой: чтение строк из Google Sheets через gspread.

Граница типов: всё, что приходит из gspread (Any), здесь приводится к str.
Чистое ядро (parse) этот модуль НЕ импортирует.
"""

from __future__ import annotations

from typing import Any

from gspread.exceptions import APIError


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


def _retry_after_seconds(headers: object) -> float | None:
    """Извлечь Retry-After (секунды) из заголовков ответа; нераспознанное -> None."""
    get = getattr(headers, "get", None)
    if get is None:
        return None
    raw = get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        # Retry-After может быть HTTP-датой, а не числом — тогда не уважаем конкретное значение.
        return None


def _classify_api_error(exc: APIError) -> FetchError:
    """Преобразовать gspread APIError в FetchError по HTTP-статусу.

    429 -> transient + retry_after из заголовка; 401/403/404 -> non-transient;
    прочее (5xx и т.п.) -> transient (временный сбой сервиса).
    """
    status = getattr(exc.response, "status_code", None)
    if status == 429:
        return FetchError(
            "rate limited",
            transient=True,
            retry_after=_retry_after_seconds(getattr(exc.response, "headers", None)),
        )
    if status in (401, 403, 404):
        return FetchError(f"non-transient API error: {status}", transient=False)
    return FetchError(f"transient API error: {status}", transient=True)


def _cell_to_str(value: Any) -> str:
    """Привести значение ячейки к str. None -> пустая строка (а не 'None')."""
    if value is None:
        return ""
    return str(value)


def fetch_rows(client: object, spreadsheet_id: str, worksheet_name: str) -> list[dict[str, str]]:
    """Прочитать строки листа Google Sheets, приведя каждую ячейку к str."""
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)  # type: ignore[attr-defined]
        worksheet = spreadsheet.worksheet(worksheet_name)
        records: list[dict[str, Any]] = worksheet.get_all_records()
    except APIError as exc:
        raise _classify_api_error(exc) from exc
    return [{key: _cell_to_str(value) for key, value in record.items()} for record in records]
