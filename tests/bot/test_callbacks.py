"""Тесты callback-фабрик: pack/unpack, префиксы, бюджет 64 байта."""

from __future__ import annotations

import pytest

from src.bot.callbacks import (
    CategoryCB,
    LangCB,
    NavCB,
    PageCB,
    ProductCB,
    SearchPageCB,
    SearchProductCB,
    SubcatCB,
)

H = "0123456789ab"  # 12-hex как у group_id


def test_pack_unpack_roundtrip() -> None:
    cb = PageCB(cat=H, sub=H, page=7)
    packed = cb.pack()
    assert packed == f"pg:{H}:{H}:7"
    assert PageCB.unpack(packed) == cb


def test_prefixes() -> None:
    assert LangCB(code="ru").pack() == "lang:ru"
    assert NavCB(to="menu").pack() == "nav:menu"
    assert CategoryCB(cat=H).pack() == f"c:{H}"
    assert SubcatCB(cat=H, sub=H).pack() == f"s:{H}:{H}"
    assert ProductCB(prod=H, cat=H, sub=H, page=1).pack() == f"p:{H}:{H}:{H}:1"
    assert SearchPageCB(page=3).pack() == "sp:3"
    assert SearchProductCB(prod=H).pack() == f"ps:{H}"


@pytest.mark.parametrize(
    "cb",
    [
        ProductCB(prod=H, cat=H, sub=H, page=9999),  # худший каталожный пакет
        PageCB(cat=H, sub=H, page=9999),
        SubcatCB(cat=H, sub=H),
    ],
)
def test_worst_case_within_64_bytes(cb: object) -> None:
    assert len(cb.pack().encode("utf-8")) <= 64  # type: ignore[attr-defined]
