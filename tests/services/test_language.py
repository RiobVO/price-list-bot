"""Тесты per-user хранилища языка (in-memory)."""

from __future__ import annotations

from src.services.language import LanguageStore


def test_unknown_user_returns_none() -> None:
    store = LanguageStore()
    assert store.get(42) is None


def test_set_then_get() -> None:
    store = LanguageStore()
    store.set(42, "uz")
    assert store.get(42) == "uz"


def test_set_overwrites() -> None:
    store = LanguageStore()
    store.set(42, "ru")
    store.set(42, "uz")
    assert store.get(42) == "uz"


def test_users_are_independent() -> None:
    store = LanguageStore()
    store.set(1, "ru")
    store.set(2, "uz")
    assert store.get(1) == "ru"
    assert store.get(2) == "uz"
