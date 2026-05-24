"""Доставка карточки товара с graceful-фолбэком фото.

Фото может не уйти (404/не картинка/лимиты Telegram) — это не ошибка хендлера:
шлём карточку без фото + warning. Текст доходит всегда (бриф §5).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from src.services.models import ProductCard

logger = logging.getLogger(__name__)


class _CardTarget(Protocol):
    """Объект, умеющий отправлять сообщение/фото (Message)."""

    async def answer(self, text: str, **kwargs: Any) -> Any: ...
    async def answer_photo(self, photo: str, **kwargs: Any) -> Any: ...


async def send_product_card(
    target: _CardTarget,
    card: ProductCard,
    *,
    markup: InlineKeyboardMarkup | str | None,
) -> None:
    """Отправить карточку. С фото — answer_photo; битое фото → текст + warning."""
    if card.photo is not None:
        try:
            await target.answer_photo(card.photo, caption=card.text, reply_markup=markup)
            return
        except TelegramAPIError as exc:
            logger.warning("product_photo_failed", extra={"error": str(exc)})
    await target.answer(card.text, reply_markup=markup)
