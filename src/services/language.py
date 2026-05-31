"""Per-user язык интерфейса, in-memory.

ДОПУЩЕНИЕ: при рестарте процесса сбрасывается (persist в SQLite/Redis отложен, см. §11 дизайна).
Отдельно от FSM — сброс состояния поиска не стирает выбранный язык.
"""

from __future__ import annotations

from src.services.models import Lang


class LanguageStore:
    """Хранилище выбранного языка по user_id (None — язык ещё не выбран)."""

    def __init__(self) -> None:
        self._lang: dict[int, Lang] = {}

    def get(self, user_id: int) -> Lang | None:
        """Язык пользователя или None, если ещё не выбран (нужен экран выбора)."""
        return self._lang.get(user_id)

    def set(self, user_id: int, lang: Lang) -> None:
        """Запомнить выбранный язык пользователя."""
        self._lang[user_id] = lang
