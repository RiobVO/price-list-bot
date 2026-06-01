# Telegram-бот «Каталог / Прайс-лист»

Двуязычный (ru/uz) Telegram-бот — интерактивный прайс-лист. Ассортимент и цены клиент ведёт сам в
**Google Sheets**; бот только читает и показывает. Оформления заказов, корзины и оплаты **нет**.

**Главный принцип:** правка цены или товара не требует правки кода — всё берётся из таблицы.

---

## Быстрый старт (Docker)

```bash
cp .env.example .env                 # заполнить BOT_TOKEN, SPREADSHEET_ID
# положить ключ сервис-аккаунта рядом как service-account.json
docker compose up --build
```

Бот поднимается в режиме polling. Пока каталог не загружен (cold-start) — отвечает «каталог обновляется»,
не падает.

Без Docker:

```bash
make install          # pip install -e ".[dev]"
make run              # python -m src.main
```

---

## Google service-account и доступ к таблице

1. В [Google Cloud Console](https://console.cloud.google.com/) создайте проект.
2. Включите **Google Sheets API** (APIs & Services → Library → Google Sheets API → Enable).
3. Создайте **Service Account** (IAM & Admin → Service Accounts), затем сгенерируйте **JSON-ключ**
   (Keys → Add key → JSON) и скачайте его.
4. **Расшарьте таблицу** на email сервис-аккаунта (вида `name@project.iam.gserviceaccount.com`) с
   правом **Viewer** (Чтение). Без этого бот не увидит таблицу.
5. Доставьте секрет одним из способов (РОВНО один, см. `.env`):
   - **путь к файлу** (дефолт): положите ключ как `./service-account.json` —
     `GOOGLE_APPLICATION_CREDENTIALS=./service-account.json` (в Docker монтируется read-only);
   - **base64**: `GOOGLE_CREDENTIALS_B64=$(base64 -i service-account.json)`.

Секреты в репозиторий не коммитятся: `.env` и `*service-account*.json` — в `.gitignore`.

---

## Шаблон таблицы (лист `products`)

Первая строка — **заголовки** (сопоставление по именам, не по позиции; лишние колонки игнорируются).
Имена колонок 1-в-1:

| id | category | subcategory | name_ru | name_uz | desc_ru | desc_uz | price_wholesale | price_retail | currency | packaging | photo | is_active |
|----|----------|-------------|---------|---------|---------|---------|-----------------|--------------|----------|-----------|-------|-----------|

Правила заполнения:

- **Обязательны:** `id`, `category`, `name_ru`, `name_uz`. Пустое любое из них → строка пропускается
  (с warning в логах), остальной каталог жив.
- **`subcategory`** пустая → товар попадает в группу «Прочее» (не теряется). Навигация двухуровневая:
  категория → подкатегория → товары.
- **Цены** (`price_wholesale`, `price_retail`): принимаются пробелы-разделители тысяч и запятая как
  десятичная (`120 000`, `12,5`). Невалидное число → «цена по запросу» (строка не падает).
- **`currency`**: пустая/нераспознанная → `DEFAULT_CURRENCY` (с warning). Набор валют — в `CURRENCIES`.
- **`is_active`**: `TRUE/FALSE`, `1/0`, `да/нет`, `ha/yo'q`, `+/-` (регистронезависимо). Пустое → товар
  виден (с warning). Скрытие — только явным `FALSE`.
- **`photo`**: публичный URL (рекомендуется) или Telegram `file_id`. Если фото не отправилось — карточка
  доходит без фото.
- **Дубликаты `id`**: берётся первый валидный, остальные логируются.

Битая **схема** (нет обязательной колонки в заголовке) → снимок отвергается целиком, старый кэш остаётся
в силе. Одна опечатка в заголовке не обнуляет магазин.

---

## Переменные окружения

Полный список с комментариями — в [`.env.example`](.env.example). Ключевые:

| Переменная | Дефолт | Назначение |
|---|---|---|
| `BOT_TOKEN` | — | Токен бота от @BotFather (обязателен) |
| `SPREADSHEET_ID` | — | id Google-таблицы (обязателен) |
| `SHEET_NAME` | `products` | Имя листа с товарами |
| `GOOGLE_APPLICATION_CREDENTIALS` / `GOOGLE_CREDENTIALS_B64` | путь к файлу | Секрет SA (ровно один) |
| `CACHE_TTL_SECONDS` | `300` | Период фонового обновления каталога |
| `DEFAULT_CURRENCY` / `CURRENCIES` | `UZS` | Валюта по умолчанию / разрешённые валюты |
| `FALLBACK_SUBCATEGORY` | `Прочее` | Группа для товаров с пустой подкатегорией |
| `PAGE_SIZE` | `8` | Товаров на странице (1..10) |
| `THROTTLE_RATE_PER_SEC` | `1.0` | Лимит запросов на пользователя в секунду |
| `USE_WEBHOOK` | `false` | Транспорт (false = polling) |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `json` | Логирование |
| `SHUTDOWN_TIMEOUT_S` | `8.0` | Таймаут graceful shutdown |

---

## Разработка

```bash
make install     # установить с dev-зависимостями
make check       # единый гейт: ruff check -> ruff format --check -> mypy --strict -> pytest
make cov         # тесты с покрытием
```

Код строился по TDD послойно: `data → services → bot → infra`. Планы и спеки — в
`docs/superpowers/`; архитектурные решения — в `docs/adr/` (формат Nygard). Границы слоёв жёсткие:
`bot` ходит в каталог только через `services`; `data` не знает про aiogram; `gspread` — только в `data`.

---

## Транспорт и эксплуатация

- **polling** (дефолт): запускать **ровно одну реплику** (несколько → Telegram 409). `docker-compose.yml`
  рассчитан на один сервис.
- **webhook**: сейчас каркас под флагом `USE_WEBHOOK` (см. `docs/adr/0008-transport-and-shutdown.md`);
  полная реализация — отдельная задача.
- **Graceful shutdown**: по `SIGTERM`/`SIGINT` бот отменяет фоновую refresh-задачу и закрывает сессию.
- **Логи**: структурные (JSON) в stdout; поле refresh-summary включает число валидных/пропущенных строк
  и возраст снимка.
- **Память языка/состояния**: in-memory (при рестарте сбрасывается). Persist (SQLite/Redis) — TODO.
