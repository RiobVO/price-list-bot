"""Тест FSM-группы поиска."""

from __future__ import annotations

from aiogram.fsm.state import State

from src.bot.states import SearchSG


def test_search_state_exists() -> None:
    assert isinstance(SearchSG.waiting_query, State)
    assert SearchSG.waiting_query.state == "SearchSG:waiting_query"
