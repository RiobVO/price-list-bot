"""Тесты наличия bot-ключей интерфейса в обоих языках."""

from __future__ import annotations

import pytest

from src.locales import get_text

BOT_KEYS = [
    "welcome",
    "choose_language",
    "menu_title",
    "btn_search",
    "btn_change_language",
    "btn_back",
    "btn_prev",
    "btn_next",
    "btn_cancel",
    "btn_new_search",
    "search_prompt",
    "search_not_found",
    "search_enter_text",
    "empty_category",
    "catalog_updating",
    "stale_notice",
    "throttled",
    "page_counter",
]


@pytest.mark.parametrize("key", BOT_KEYS)
@pytest.mark.parametrize("lang", ["ru", "uz"])
def test_bot_key_present_and_nonempty(key: str, lang: str) -> None:
    assert get_text(key, lang).strip() != ""
