"""Чистые преобразователи сырых строковых ячеек таблицы в типы домена.

parse_number / parse_bool не знают про gspread, сеть, aiogram: только str -> тип|None.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

# Форма десятичного числа после удаления пробелов-тысяч и нормализации запятой:
# знак, цифры, опционально одна точка с дробной частью.
_DECIMAL_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

_NBSP = " "


def parse_number(raw: str) -> Decimal | None:
    """Разобрать сырую ячейку цены в Decimal по грамматике контракта.

    Пробелы (вкл. U+00A0) — разделители тысяч и удаляются. Запятая — десятичный
    разделитель только если она одна и после неё < 3 цифр. Точка — десятичный
    разделитель (точка-как-тысячи не поддерживается). Любая неоднозначность,
    нечисловой ввод или InvalidOperation → None (цена «по запросу» выше по стеку).
    """
    text = raw.strip().replace(_NBSP, " ").replace(" ", "")
    if not text:
        return None

    has_dot = "." in text
    comma_count = text.count(",")

    # Одновременно запятая и точка, либо более одной запятой — неоднозначно.
    if comma_count > 1 or (comma_count == 1 and has_dot):
        return None

    if comma_count == 1:
        integer_part, _, fractional_part = text.partition(",")
        # Ровно 3+ цифр после запятой трактуются как разделитель тысяч → отказ.
        if len(fractional_part) >= 3:
            return None
        text = f"{integer_part}.{fractional_part}"

    # Структурная проверка финальной формы: отсекает множественные точки и мусор.
    if not _DECIMAL_RE.match(text):
        return None

    try:
        return Decimal(text)
    except InvalidOperation:  # pragma: no cover — _DECIMAL_RE уже гарантирует корректность
        return None


# Апострофы узбекской латиницы: разные кодовые точки сводятся к ASCII U+0027,
# чтобы yoʻq / yo'q / yoʼq / yo'q совпадали с каноническим литералом.
_CANONICAL_APOSTROPHE = "'"
_APOSTROPHES = ("ʻ", "‘", "’", "ʼ")
_APOSTROPHE_RE = re.compile("[" + "".join(_APOSTROPHES) + "]")

_TRUE_LITERALS = frozenset({"true", "1", "да", "ha", "+", "yes"})
_FALSE_LITERALS = frozenset({"false", "0", "нет", "yoq", "yo'q", "-", "no"})


def parse_bool(raw: str) -> bool | None:
    """Разобрать сырую ячейку is_active в bool по множествам контракта.

    Регистронезависимо; апострофы узбекского yo'q нормализуются к ASCII U+0027,
    поэтому все начертания апострофа распознаются. Нераспознанный литерал → None
    (выше по стеку трактуется как «видим» + RowIssue, см. правила parse).
    """
    text = _APOSTROPHE_RE.sub(_CANONICAL_APOSTROPHE, raw.strip().lower())
    if text in _TRUE_LITERALS:
        return True
    if text in _FALSE_LITERALS:
        return False
    return None
