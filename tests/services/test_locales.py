"""Тесты i18n-реестра: равенство ключей, выбор языка, фолбэк по default."""

from __future__ import annotations

import pytest

from src.locales import get_text, ru, uz


def test_ru_and_uz_have_identical_keys() -> None:
    """Инвариант: наборы ключей ru и uz совпадают (иначе дыра в переводе)."""
    assert set(ru.TEXTS.keys()) == set(uz.TEXTS.keys())


def test_get_text_returns_localized_value() -> None:
    assert get_text("price_on_request", "ru") == "цена по запросу"
    assert get_text("price_on_request", "uz") == "narxi so'rov bo'yicha"


def test_get_text_unknown_key_with_default_returns_default() -> None:
    assert get_text("currency.USD", "ru", default="USD") == "USD"


def test_get_text_unknown_key_without_default_raises() -> None:
    with pytest.raises(KeyError):
        get_text("nonexistent.key", "ru")
