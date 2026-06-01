"""Middleware языка: инъекция выбранного lang + перехват, когда язык не выбран.

Пропускает без языка только сам выбор языка (callback lang:*) и команды /start,
/menu (их обрабатывает start-роутер, показывая выбор). Прочее без языка → показать
выбор и остановить пропаганду.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from src.bot.keyboards import language_keyboard
from src.locales import get_text
from src.services.language import LanguageStore

_ALLOW_WITHOUT_LANG_COMMANDS = {"/start", "/menu"}


class LanguageMiddleware(BaseMiddleware):
    """Кладёт в data 'lang' и 'lang_store'; без языка — показывает выбор."""

    def __init__(self, store: LanguageStore) -> None:
        self._store = store

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["lang_store"] = self._store
        user = data.get("event_from_user") or getattr(event, "from_user", None)
        lang = self._store.get(user.id) if user is not None else None
        if lang is not None:
            data["lang"] = lang
            return await handler(event, data)

        if self._is_lang_selection(event):
            return await handler(event, data)

        await self._prompt_language(event)
        return None

    @staticmethod
    def _is_lang_selection(event: TelegramObject) -> bool:
        cb_data = getattr(event, "data", None)
        if isinstance(cb_data, str) and cb_data.startswith("lang:"):
            return True
        text = getattr(event, "text", None)
        return isinstance(text, str) and text.split()[0] in _ALLOW_WITHOUT_LANG_COMMANDS

    @staticmethod
    async def _prompt_language(event: TelegramObject) -> None:
        answer = getattr(event, "answer", None)
        if answer is None:
            return
        if isinstance(event, Message):
            await answer(get_text("choose_language", "ru"), reply_markup=language_keyboard())
        else:
            # CallbackQuery: гасим спиннер и шлём выбор в чат через message.
            await answer()
            message = getattr(event, "message", None)
            if message is not None:
                await message.answer(
                    get_text("choose_language", "ru"), reply_markup=language_keyboard()
                )
