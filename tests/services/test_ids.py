"""Тесты стабильного хеш-id групп для callback_data."""

from __future__ import annotations

from src.services.ids import group_id


def test_id_is_12_hex_chars() -> None:
    value = group_id("Напитки")
    assert len(value) == 12
    assert all(c in "0123456789abcdef" for c in value)


def test_id_is_deterministic() -> None:
    assert group_id("Напитки") == group_id("Напитки")


def test_id_is_case_and_whitespace_insensitive() -> None:
    assert group_id("  напитки ") == group_id("Напитки")


def test_id_is_script_insensitive_for_uz() -> None:
    """Одно имя на латинице и кириллице даёт один id (канон-нормализация)."""
    assert group_id("olma") == group_id("олма")


def test_pair_id_differs_from_bare_subcategory() -> None:
    """id пары (category, subcategory) ≠ id голой подкатегории — одноимённые
    подкатегории в разных категориях не склеиваются."""
    assert group_id("Напитки", "Прочее") != group_id("Еда", "Прочее")
    assert group_id("Напитки", "Прочее") != group_id("Прочее")


def test_different_inputs_give_different_ids() -> None:
    assert group_id("Напитки") != group_id("Еда")


def test_worst_case_callback_within_64_bytes() -> None:
    """Худший callback p:<prod>:<sub>:<page> из 12-hex id влезает в лимит Telegram (64 байта).

    Длинное UZ-имя категории не раздувает id (хеш фикс. длины) — инвариант callback_data ≤ 64.
    """
    long_uz = "узоқ номли категория " * 5
    prod = group_id("очень-длинный-идентификатор-товара-из-таблицы")
    sub = group_id(long_uz, "подкатегория")
    callback = f"p:{prod}:{sub}:9999"
    assert len(callback.encode("utf-8")) <= 64
