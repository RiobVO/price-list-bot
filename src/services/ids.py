"""Стабильные короткие id групп для callback_data (blake2s от канона имени)."""

from __future__ import annotations

import hashlib

from src.services.normalize import normalize

# Разделитель частей ключа: управляющий символ, не встречающийся в именах.
_SEP = "\x1f"
# 6 байт → 12 hex: влезает в callback_data (≤64 байта) с большим запасом.
_DIGEST_SIZE = 6


def group_id(*parts: str) -> str:
    """Стабильный 12-hex id из частей ключа.

    Части нормализуются единым каноном (uz-таблица) и склеиваются разделителем,
    поэтому один и тот же ключ даёт один id независимо от письменности/регистра.
    Пара (category, subcategory) глобально уникальна — одноимённые подкатегории
    в разных категориях не склеиваются.
    """
    canon = _SEP.join(normalize(part, "uz") for part in parts)
    digest = hashlib.blake2s(canon.encode("utf-8"), digest_size=_DIGEST_SIZE)
    return digest.hexdigest()
