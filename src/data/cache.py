"""In-memory кэш каталога: атомарный снимок, порог качества, single-flight swap."""

from __future__ import annotations

from datetime import UTC, datetime

from src.data.models import ParseResult, Snapshot

# Максимальная доля битых строк, при которой снимок ещё принимается.
# Строго выше порога (доля битых > 0.5) — снимок отвергается целиком.
_MAX_BROKEN_RATIO = 0.5

# Старт: cold-start пустой снимок (каталога ещё нет, см. контракт Snapshot).
_EMPTY_SNAPSHOT = Snapshot(catalog=None, updated_at=None, valid_rows=0, skipped_rows=0)


class CatalogCache:
    """Хранит единственную ссылку на актуальный Snapshot каталога.

    Чтение (get_snapshot) — синхронно, без сети и без Lock: хендлеры читают снимок
    напрямую. Запись (try_swap) — под asyncio.Lock, проверяет порог качества и
    атомарно заменяет ссылку на новый снимок.
    """

    def __init__(self, *, min_valid_rows: int = 1) -> None:
        self._min_valid_rows = min_valid_rows
        self._snapshot: Snapshot = _EMPTY_SNAPSHOT

    def get_snapshot(self) -> Snapshot:
        """Текущий снимок. Без сети, без Lock — атомарное чтение ссылки."""
        return self._snapshot

    def _passes_threshold(self, result: ParseResult) -> bool:
        """Снимок принимается, если доля битых <= 0.5 И valid >= min_valid_rows.

        Пустой результат (valid+skipped == 0) отвергается безусловно — предотвращает
        деление на ноль и гарантирует, что пустой снимок не заменяет живой кэш.
        """
        if result.valid_rows < self._min_valid_rows:
            return False
        total = result.valid_rows + result.skipped_rows
        if total == 0:
            return False  # пустой результат -> отклонить, старый снимок жив (guard ZeroDivision)
        return result.skipped_rows / total <= _MAX_BROKEN_RATIO

    async def try_swap(self, result: ParseResult, *, now: datetime | None = None) -> bool:
        """Поставить новый снимок, если он прошёл порог качества.

        Возвращает True при успешной замене, False — если порог не пройден
        (тогда прежний снимок остаётся в силе). Замена ссылки атомарна.
        """
        if not self._passes_threshold(result):
            return False
        stamp = now if now is not None else datetime.now(UTC)
        self._snapshot = Snapshot(
            catalog=result.catalog,
            updated_at=stamp,
            valid_rows=result.valid_rows,
            skipped_rows=result.skipped_rows,
        )
        return True
