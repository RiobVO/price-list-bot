"""FSM-состояния бота. Поиск — единственный режим ввода текста (см. §6 UX)."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class SearchSG(StatesGroup):
    """Режим поиска: ожидание текстового запроса от пользователя."""

    waiting_query = State()
