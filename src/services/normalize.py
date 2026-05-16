"""Нормализация строк для поиска и хеш-id.

UZ: явная таблица кириллица→латиница + унификация апострофов; обе письменности
сводятся к единому канону (латиница). RU: lower+trim+collapse+ё→е.
"""

from __future__ import annotations

import re

from src.services.models import Lang

# Варианты апострофа узбекской латиницы (oʻ/gʻ) сводятся к ASCII U+0027.
_APOSTROPHE_RE = re.compile("[ʻʼ‘’`']")
_CANONICAL_APOSTROPHE = "'"

_WS_RE = re.compile(r"\s+")

# Узбекская кириллица → латиница. Многобуквенные значения (ch/sh/yo/ts) и
# апострофные (oʻ→o', gʻ→g') дают тот же канон, что и латинский ввод.
_CYR_TO_LAT: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "ғ": "g'",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "j",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "қ": "q",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "ў": "o'",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "x",
    "ҳ": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "ъ": "'",
    "ы": "i",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def normalize(text: str, lang: Lang) -> str:
    """Привести строку к каноническому виду для подстрочного сравнения и хеширования.

    uz: lower → унификация апострофов → collapse whitespace → кириллица→латиница.
    ru: lower → collapse whitespace → ё→е. Пустое/пробелы → пустая строка.
    """
    folded = _WS_RE.sub(" ", text.strip().lower())
    folded = _APOSTROPHE_RE.sub(_CANONICAL_APOSTROPHE, folded)
    if lang == "uz":
        return "".join(_CYR_TO_LAT.get(ch, ch) for ch in folded)
    return folded.replace("ё", "е")
