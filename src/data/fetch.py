"""Грязный I/O-слой: чтение строк из Google Sheets через gspread.

Граница типов: всё, что приходит из gspread (Any), здесь приводится к str.
Чистое ядро (parse) этот модуль НЕ импортирует.
"""

from __future__ import annotations


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
