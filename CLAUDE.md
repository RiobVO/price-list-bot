# CLAUDE.md — Telegram-бот «Каталог / Прайс-лист»

> Проектные правила. Дополняют глобальный `~/.claude/CLAUDE.md`, не дублируют его.
> Источник истины по требованиям — `BRIEF.md`. Дизайн — `docs/superpowers/specs/2026-05-31-price-list-bot-design.md`.
> Архитектурные решения — `docs/adr/`.

---

## Что это

Двуязычный (ru/uz) Telegram-бот — интерактивный прайс-лист. Контент (товары, цены) клиент
ведёт сам в Google Sheets; бот только читает и показывает. Заказов/корзины/оплаты нет.
**Главный принцип:** правка цены/товара не требует правки кода. Любое решение, требующее кода при
изменении цены — неверное.

---

## Зафиксированные решения Фазы 0 (2026-05-31)

Закрытые открытые вопросы §9 (решения клиента) и разрешённые противоречия брифа:

| Тема | Решение |
|---|---|
| Валюта | **Мультивалютность per-товар.** Колонка `currency` обязательна; набор валют и формат (символ/позиция/разделитель) — в конфиге; пустая/нераспознанная → `DEFAULT_CURRENCY` (env) + warning |
| Категории | **Двухуровневые:** категория → подкатегория. Колонка `subcategory`; пустая → группа «Прочее» + warning (товар не теряется) |
| Имена | **`name_ru` и `name_uz` оба обязательны.** Пустое любое → строка пропущена + warning. Языковой фолбэк §5 — только для `desc_*` |
| `is_active` пустое | **Товар ВИДЕН** + warning(id) + README. Скрытие — только явным FALSE. Дефолт не молчаливый (лог+метрика+доку), потому §4 не нарушен |
| Порог отказа снимка (§4↔§7) | битых строк > 50% ИЛИ valid < `MIN_VALID_ROWS` (env, дефолт 1) → снимок отвергнут целиком, старый кэш жив, `error`. Иначе битые пропустить, каталог жив |
| Пустой лист vs битая схема | нет заголовка/обязательной колонки = битая схема (отказ). Есть заголовок + 0 строк = валидный пустой каталог |
| Невалидная цена | поле деградирует («цена по запросу»), строку НЕ роняет. Фатальны для строки только пустые `id/category/name_*` |
| Заголовки таблицы | технические ключи (`id, category, subcategory, name_ru, …`), матчинг по нормализованному имени (strip+lower), README-шаблон 1-в-1 |

Допущения (помечать `ДОПУЩЕНИЕ` в коде/README; оспоримы): TTL=300с; `PAGE_SIZE`=8; транспорт polling
(webhook под флагом); SA-секрет = путь к файлу (`GOOGLE_APPLICATION_CREDENTIALS`), base64 опц.; язык/состояние
in-memory (TODO persist); cold-start = бесконечный backoff с джиттером, режим «обновляется»; форс-рефреш — нет.

---

## Инварианты (нарушение = баг, не вариация)

- **Парсер `parse` — чистая функция** `Sequence[Mapping[str, str]] -> ParseResult`. Не знает про gspread,
  сеть, aiogram. Тестируется на статических строковых фикстурах без сети.
- **Граница типов:** `Any` от gspread обрезается в `fetch` (всё → `str`). В ядро `str` входит, `Decimal/bool/str`
  выходит. Цена — `Decimal`, не `float`.
- **Битая строка ≠ битая схема.** Строка: пропуск/деградация + `warning`, каталог жив. Схема: отказ снимка
  целиком + `error`, старый кэш в силе. Частичный снимок в кэш **не кладётся**.
- **Атомарность кэша:** новый снимок ставится одной заменой ссылки только после полного парсинга и проверки
  схемы. `Catalog` иммутабелен (frozen). Чтение снимка хендлером — без сети и без Lock.
- **Обновление кэша — фоновая asyncio-задача по TTL** под `asyncio.Lock` (single-flight). Никакой ленивой
  подгрузки в хендлере. Хендлеры не ходят в Google API.
- **`callback_data` ≤ 64 байта.** Только короткие стабильные id (slug/хеш ключа, не голый индекс) + номер
  страницы. Строки/узбекские названия/поисковый запрос в callback — запрещены. Поиск — через FSM.
- **Любой callback-id может протухнуть** (категория/подкатегория/товар/страница). Единый ответ: мягкое
  «каталог обновился, откройте заново» + возврат в меню. Не падать, не отвечать пустотой.
- **Бот переживает кривые данные и недоступный API.** Граф-деградация, не падение процесса.
- **Все пользовательские строки — через i18n** (`locales/ru.py`, `locales/uz.py`, идентичные ключи). Никакого
  хардкода строк, цен, товаров, id книги, имени листа.
- **Узбекская нормализация поиска — явная таблица** латиница↔кириллица + варианты апострофа, с юнит-тестами.
  Не «заменить пару символов».

---

## Слои (границы — жёсткие)

```
bot (aiogram)  →  services  →  data (fetch dirty / parse pure / cache TTL)
                                        ↑ gspread только здесь
locales        — i18n, нормализация
config.py      — pydantic-settings, всё из env
```

- `data` не импортирует aiogram. `bot` не лезет в gspread/`data` напрямую — только через `services`.
- `services` — единственный мост бот↔кэш.

---

## Стек и команды

- Python 3.11+, aiogram 3.x, gspread, pydantic-settings, in-memory TTL-кэш, Docker (long-polling).
- Качество: `ruff` (lint+format), `mypy --strict`, `pytest` (+ `pytest-asyncio` strict, `pytest-cov`).
- Команды (`Makefile`/`nox`, единый гейт): lint → typecheck → test. Появятся при настройке тулинга.

## Порядок работы

TDD, начиная со слоя `data` (каркас всего). **Первый артефакт — падающий тест `parse` на фикстуре строк**,
затем парсер. Значимые решения — ADR (`docs/adr/NNNN-title.md`, формат Nygard) по ходу, не задним числом.

---

## Статус (2026-06-01)

**Все слои серии готовы: `data` → `services` → `bot` → `infra`.** 355 тестов зелёные;
`ruff` + `ruff format` + `mypy --strict src` чисто. Планы — `docs/superpowers/plans/` (4 файла),
ADR — `docs/adr/` (включая 0008 транспорт/shutdown, 0009 SA-секрет, 0013 навигация bot).

- **`data`:** `models, coerce, fetch, parse, cache, refresh, auth, sample`. `coerce`/`parse` — 100%.
- **`services`:** фасад `CatalogService` (`categories/subcategories/product_page/product_card/search`),
  `Ok|Stale`, UZ-нормализация, blake2s callback-id, формат цены, per-user `LanguageStore`.
- **`bot` (aiogram 3.28):** `callbacks, states, keyboards, delivery, middlewares (language/throttle),
  handlers (start/catalog/search)`. Двухуровневая навигация, поиск через FSM, фолбэк фото, протухание id.
- **`infra`:** `Makefile` (гейт `make check`), `Dockerfile`+`.dockerignore` (non-root, SIGTERM, образ собран),
  `docker-compose.yml`, `README.md`, `.env.example`, `.pre-commit-config.yaml`, CI (`.github/workflows/ci.yml`).
- **`main.py`:** composition root — настройки→логирование→кэш→refresh-task→dispatcher→polling→graceful
  shutdown. Перед polling: `delete_webhook(drop_pending_updates=True)`. **Демо-режим** `USE_SAMPLE_CATALOG`
  (каталог из `src/data/sample.py`, без Google — локальный запуск с одним токеном).

Запуск: `cp .env.example .env` (BOT_TOKEN [+ `USE_SAMPLE_CATALOG=true` для демо, либо доступ к таблице]),
затем `python -m src.main` / `docker compose up`. polling — строго одна реплика (иначе Telegram 409).

Отложено (вне серии, по желанию): полный **webhook** (сейчас каркас под `USE_WEBHOOK`); **persist**
языка/состояния (in-memory сбрасывается при рестарте); старт-валидация `DEFAULT_CURRENCY ∈ CURRENCIES`
и нижних границ `*_BACKOFF_*_S`/`SHUTDOWN_TIMEOUT_S`; форс-рефреш по whitelist user_id.

Known limitations (оспоримы): кэш не свапает пустой снимок (`valid+skipped==0` → `try_swap` False);
коллизия нормализованных заголовков — молча побеждает последняя; навигация рендерит новым сообщением
(не `edit`, см. ADR 0013).
