"""Тесты доставки карточки: с фото, без фото, фолбэк при битом фото."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from src.bot.delivery import send_product_card
from src.services.models import ProductCard


def _target() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_text_only_card_uses_answer() -> None:
    target = _target()
    await send_product_card(target, ProductCard(text="Сок", photo=None), markup="KB")
    target.answer.assert_awaited_once()
    target.answer_photo.assert_not_awaited()


@pytest.mark.asyncio
async def test_photo_card_uses_answer_photo() -> None:
    target = _target()
    await send_product_card(target, ProductCard(text="Сок", photo="http://x/a.jpg"), markup="KB")
    target.answer_photo.assert_awaited_once()
    target.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_bad_photo_falls_back_to_text(caplog: pytest.LogCaptureFixture) -> None:
    target = _target()
    target.answer_photo.side_effect = TelegramBadRequest(
        method=AsyncMock(), message="wrong file identifier"
    )
    with caplog.at_level(logging.WARNING):
        await send_product_card(target, ProductCard(text="Сок", photo="http://x/bad"), markup="KB")
    target.answer_photo.assert_awaited_once()
    target.answer.assert_awaited_once()  # фолбэк: текст всё равно доставлен
    assert any("photo" in r.message for r in caplog.records)
