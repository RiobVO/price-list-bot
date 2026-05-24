"""Тесты language-middleware: инъекция lang, перехват невыбранного языка."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.bot.callbacks import LangCB
from src.bot.middlewares.language import LanguageMiddleware
from src.services.language import LanguageStore


def _event(user_id: int = 1, data: str | None = None) -> AsyncMock:
    ev = AsyncMock()
    ev.from_user.id = user_id
    ev.data = data  # для callback; у message обычно нет
    return ev


@pytest.mark.asyncio
async def test_injects_known_lang_and_calls_handler() -> None:
    store = LanguageStore()
    store.set(1, "uz")
    mw = LanguageMiddleware(store)
    handler = AsyncMock(return_value="done")
    data: dict[str, object] = {}
    result = await mw(handler, _event(1), data)
    assert result == "done"
    handler.assert_awaited_once()
    assert data["lang"] == "uz"
    assert data["lang_store"] is store


@pytest.mark.asyncio
async def test_unknown_lang_blocks_handler_and_prompts() -> None:
    store = LanguageStore()
    mw = LanguageMiddleware(store)
    handler = AsyncMock()
    ev = _event(2)
    await mw(handler, ev, {})
    handler.assert_not_awaited()  # пропаганда остановлена
    ev.answer.assert_awaited()  # показан выбор языка


@pytest.mark.asyncio
async def test_lang_callback_passes_through_even_without_lang() -> None:
    """Сам выбор языка не должен блокироваться отсутствием языка."""
    store = LanguageStore()
    mw = LanguageMiddleware(store)
    handler = AsyncMock(return_value="ok")
    ev = _event(3, data=LangCB(code="ru").pack())
    result = await mw(handler, ev, {})
    assert result == "ok"
    handler.assert_awaited_once()
