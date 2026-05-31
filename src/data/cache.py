"""In-memory кэш каталога: атомарный снимок, порог качества, single-flight swap."""

from __future__ import annotations

from src.data.models import Snapshot

# Старт: cold-start пустой снимок (каталога ещё нет, см. контракт Snapshot).
_EMPTY_SNAPSHOT = Snapshot(catalog=None, updated_at=None, valid_rows=0, skipped_rows=0)


class CatalogCache:
    """Хранит единственную ссылку на актуальный Snapshot каталога.

    Чтение (get_snapshot) — синхронно, без сети и без Lock: хендлеры читают снимок
    напрямую. Запись (try_swap) — отдельная задача, появится в следующих шагах.
    """

    def __init__(self, *, min_valid_rows: int = 1) -> None:
        self._min_valid_rows = min_valid_rows
        self._snapshot: Snapshot = _EMPTY_SNAPSHOT

    def get_snapshot(self) -> Snapshot:
        """Текущий снимок. Без сети, без Lock — атомарное чтение ссылки."""
        return self._snapshot
