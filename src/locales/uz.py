"""Узбекские строки интерфейса. Ключи идентичны ru.py (инвариант i18n)."""

from __future__ import annotations

TEXTS: dict[str, str] = {
    "price_on_request": "narxi so'rov bo'yicha",
    "label_wholesale": "Optom",
    "label_retail": "Chakana",
    "label_packaging": "Qadoq",
    "currency.UZS": "so'm",
    # --- bot interfeysi ---
    "welcome": "Xush kelibsiz! Bu katalog-narxnoma.",
    "choose_language": "Tilni tanlang / Выберите язык:",
    "menu_title": "Katalog. Kategoriyani tanlang:",
    "btn_search": "🔎 Qidiruv",
    "btn_change_language": "🌐 Tilni almashtirish",
    "btn_back": "◀ Orqaga",
    "btn_prev": "◀",
    "btn_next": "▶",
    "btn_cancel": "✖ Bekor qilish",
    "btn_new_search": "🔎 Yangi qidiruv",
    "search_prompt": "Mahsulot nomini kiriting:",
    "search_not_found": "Hech narsa topilmadi. Boshqa so'rov kiriting.",
    "search_enter_text": "Iltimos, qidiruv uchun matn kiriting.",
    "empty_category": "Bu kategoriyada hozircha mahsulot yo'q.",
    "catalog_updating": "Katalog yangilanmoqda, bir daqiqadan so'ng urinib ko'ring.",
    "stale_notice": "Katalog yangilandi, qaytadan oching.",
    "throttled": "Juda tez-tez. Biroz kuting.",
    "page_counter": "{page}/{total}-bet",
}
