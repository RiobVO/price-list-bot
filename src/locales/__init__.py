"""i18n-реестр: get_text(key, lang) с инвариантом равенства ключей ru/uz.

lang типизирован как str (не services.models.Lang): locales — отдельный слой,
не должен зависеть от services. Вызывающий передаёт Lang (подтип str).
"""

from __future__ import annotations

from src.locales import ru, uz

_TABLES: dict[str, dict[str, str]] = {"ru": ru.TEXTS, "uz": uz.TEXTS}


def get_text(key: str, lang: str, default: str | None = None) -> str:
    """Локализованная строка по ключу. Неизвестный ключ → default или KeyError."""
    table = _TABLES[lang]
    if key in table:
        return table[key]
    if default is not None:
        return default
    raise KeyError(f"missing i18n key {key!r} for lang {lang!r}")
