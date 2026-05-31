"""Русские строки интерфейса. Ключи идентичны uz.py (инвариант i18n)."""

from __future__ import annotations

TEXTS: dict[str, str] = {
    "price_on_request": "цена по запросу",
    "label_wholesale": "Опт",
    "label_retail": "Розница",
    "label_packaging": "Фасовка",
    "currency.UZS": "сум",
    # --- интерфейс бота ---
    "welcome": "Добро пожаловать! Это каталог-прайс.",
    "choose_language": "Выберите язык / Tilni tanlang:",
    "menu_title": "Каталог. Выберите категорию:",
    "btn_search": "🔎 Поиск",
    "btn_change_language": "🌐 Сменить язык",
    "btn_back": "◀ Назад",
    "btn_prev": "◀",
    "btn_next": "▶",
    "btn_cancel": "✖ Отмена",
    "btn_new_search": "🔎 Новый поиск",
    "search_prompt": "Введите название товара:",
    "search_not_found": "Ничего не найдено. Попробуйте другой запрос.",
    "search_enter_text": "Пожалуйста, введите текст для поиска.",
    "empty_category": "В этой категории пока нет товаров.",
    "catalog_updating": "Каталог обновляется, попробуйте через минуту.",
    "stale_notice": "Каталог обновился, откройте заново.",
    "throttled": "Слишком часто. Подождите немного.",
    "page_counter": "Стр. {page}/{total}",
}
