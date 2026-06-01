"""Встроенный пример каталога для демо-режима (USE_SAMPLE_CATALOG).

Строки — в том же формате, что отдаёт fetch (все ячейки str), поэтому проходят
обычный parse без сети. Только для локального запуска/демонстрации.
"""

from __future__ import annotations

from collections.abc import Mapping

SAMPLE_ROWS: list[Mapping[str, str]] = [
    {
        "id": "1",
        "category": "Напитки",
        "subcategory": "Соки",
        "name_ru": "Сок яблочный",
        "name_uz": "Olma sharbati",
        "desc_ru": "Натуральный, без сахара.",
        "desc_uz": "Tabiiy, shakarsiz.",
        "price_wholesale": "12000",
        "price_retail": "15000",
        "currency": "UZS",
        "packaging": "1 л",
        "photo": "",
        "is_active": "TRUE",
    },
    {
        "id": "2",
        "category": "Напитки",
        "subcategory": "Соки",
        "name_ru": "Сок апельсиновый",
        "name_uz": "Apelsin sharbati",
        "desc_ru": "",
        "desc_uz": "",
        "price_wholesale": "13000",
        "price_retail": "16000",
        "currency": "UZS",
        "packaging": "1 л",
        "photo": "",
        "is_active": "TRUE",
    },
    {
        "id": "3",
        "category": "Напитки",
        "subcategory": "Воды",
        "name_ru": "Вода негазированная",
        "name_uz": "Gazsiz suv",
        "desc_ru": "",
        "desc_uz": "",
        "price_wholesale": "3000",
        "price_retail": "4000",
        "currency": "UZS",
        "packaging": "0.5 л",
        "photo": "",
        "is_active": "TRUE",
    },
    {
        "id": "4",
        "category": "Еда",
        "subcategory": "Хлеб",
        "name_ru": "Хлеб белый",
        "name_uz": "Oq non",
        "desc_ru": "Свежая выпечка.",
        "desc_uz": "Yangi pishirilgan.",
        "price_wholesale": "4000",
        "price_retail": "5000",
        "currency": "UZS",
        "packaging": "",
        "photo": "",
        "is_active": "TRUE",
    },
    {
        "id": "5",
        "category": "Еда",
        "subcategory": "",
        "name_ru": "Печенье овсяное",
        "name_uz": "Suli pechenesi",
        "desc_ru": "",
        "desc_uz": "",
        "price_wholesale": "8000",
        "price_retail": "10000",
        "currency": "UZS",
        "packaging": "300 г",
        "photo": "",
        "is_active": "TRUE",
    },
]
