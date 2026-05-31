# Дизайн: Telegram-бот «Каталог / Прайс-лист»

> Статус: **на ревью** (Фаза 0). Источник требований — `BRIEF.md`. После одобрения → план реализации (TDD).
> Дата: 2026-05-31.

---

## 1. Контекст и цель

Двуязычный (ru/uz) Telegram-бот = интерактивный прайс-лист. Контент клиент ведёт сам в Google Sheets;
бот читает и показывает. Заказов нет. Главный принцип: правка цены/товара не требует кода.

---

## 2. Решения Фазы 0 (закрытые открытые вопросы §9 + разрешённые противоречия брифа)

**Решения клиента (2026-05-31):**

1. **Мультивалютность per-товар** — у каждого товара своя валюта (колонка `currency`).
2. **Двухуровневые категории** — категория → подкатегория.
3. **Оба имени обязательны** — `name_ru` И `name_uz`; пустое любое → строка пропущена.
4. **`is_active` пустое → товар ВИДЕН** (инженерное решение, не молчаливый дефолт: warning + метрика + README).

**Разрешённые противоречия брифа:**

- §4↔§7 **порог отказа снимка:** битых строк > 50% ИЛИ valid < `MIN_VALID_ROWS` (env, дефолт 1) → отказ снимка
  целиком, старый кэш жив, `error`. Иначе битые пропустить, каталог жив.
- §4↔§5/§7 **пустой лист:** нет заголовка/обязательной колонки = битая схема (отказ). Заголовок + 0 строк =
  валидный пустой каталог.
- §4 **невалидная цена** деградирует поле («цена по запросу»), строку не роняет. Фатальны для строки только
  пустые `id/category/name_ru/name_uz`.
- §4 **коллизия разделителей числа:** явная грамматика (см. §5), `Decimal`, неоднозначность → warning + «по запросу».

**Допущения (`ДОПУЩЕНИЕ` в коде/README, оспоримы):** TTL=300с; `PAGE_SIZE`=8; polling (webhook под флагом);
SA-секрет = путь к файлу, base64 опц.; язык/состояние in-memory (+TODO persist); cold-start = бесконечный
backoff с джиттером; форс-рефреш — нет; пустая `subcategory` → группа «Прочее»; пустая `currency` → `DEFAULT_CURRENCY`.

---

## 3. Модель данных (лист `products`)

Колонки сопоставляются по **нормализованному имени заголовка** (strip+lower), не по позиции. Лишние колонки
игнорируются. Заголовки — технические ключи (англ.), README даёт шаблон 1-в-1.

| Ключ | Тип | Обяз | Поведение при проблеме |
|---|---|---|---|
| `id` | str | да | пусто → строка битая (пропуск+warning) |
| `category` | str | да | пусто → строка битая |
| `subcategory` | str | да* | пусто → группа «Прочее» + warning (НЕ пропуск) |
| `name_ru` | str | да | пусто → строка битая |
| `name_uz` | str | да | пусто → строка битая |
| `desc_ru` | str | нет | пусто → фолбэк на `desc_uz` при показе |
| `desc_uz` | str | нет | пусто → фолбэк на `desc_ru` при показе |
| `price_wholesale` | Decimal | да | невалид → «цена по запросу» + warning (НЕ пропуск) |
| `price_retail` | Decimal | да | невалид → «цена по запросу» + warning |
| `currency` | str | да* | пусто/нераспозн → `DEFAULT_CURRENCY` + warning |
| `packaging` | str | нет | — |
| `photo` | str (URL/file_id) | нет | битый URL → карточка без фото + warning (на доставке) |
| `is_active` | bool | да | пусто → ВИДЕН + warning; явный FALSE → скрыт |

`Product` (frozen): `id, category, subcategory, name_ru, name_uz, desc_ru|None, desc_uz|None,
price_wholesale: Decimal|None, price_retail: Decimal|None, currency: str, packaging|None, photo|None, is_active: bool`.

---

## 4. Архитектура и дерево

```
src/
  main.py            # точка входа: сборка, регистрация роутеров/middleware, refresh-task, graceful shutdown
  config.py          # pydantic-settings: всё из env; model_validator на взаимоисключение SA-способов
  data/
    models.py        # Product, RowIssue, Catalog, ParseResult, SchemaError, Snapshot (frozen).
                     #   Category/Subcategory — навигационные view, строятся в services, НЕ здесь
    coerce.py        # parse_number(str)->Decimal|None, parse_bool(str)->bool|None — чистые
    parse.py         # parse(rows)->ParseResult — ЧИСТАЯ, ядро. SchemaError при битой схеме
    fetch.py         # gspread (dirty I/O), все ячейки → str на границе; классификация ошибок
    cache.py         # CatalogCache: снимок + метаданные, try_swap под Lock, get_snapshot() без сети
    refresh.py       # фоновая asyncio-задача по TTL + cold-start backoff; отмена при shutdown
  services/
    catalog.py       # категории/подкатегории/товары/пагинация/фолбэк desc/формат цены
    search.py        # подстрочный поиск по нормализованному name_{lang}
    pagination.py    # чистая пагинация (срез + prev/next)
    normalize.py     # UZ латиница↔кириллица + апострофы; normalize_uz/normalize_ru
  bot/
    handlers/        # start, menu, category, subcategory, product, search
    keyboards.py     # inline-клавиатуры; callback_data — только короткие id
    callbacks.py     # CallbackData-фабрики (короткие префиксы, ≤64 байта)
    states.py        # FSM SearchStates
    user_state.py    # per-user язык in-memory (отдельно от FSM, чтобы clear не стирал язык)
    middlewares/     # throttling (per-user, TTL-вытеснение), lang (инжект языка)
    formatting.py    # сборка карточек, format_price(value, currency, lang), truncate caption 1024
  locales/
    __init__.py      # get_text(key, lang); инвариант равенства ключей ru/uz
    ru.py  uz.py     # i18n словари
tests/
  conftest.py        # FakeFetcher (Protocol), MockedBot, socket-guard, caplog-хелперы
  fixtures/          # статические строки (всё str): valid/broken/dup-id/missing-header/tolerant
  data/              # test_parse, test_parse_schema, test_coerce, test_cache, test_refresh_coldstart
  services/          # test_search_normalize, test_catalog, test_pagination
  bot/               # test_callbacks (≤64 байта), test_product_card, test_handlers, test_shutdown
docs/adr/            # 0001..NNNN (Nygard)
Dockerfile  docker-compose.yml  pyproject.toml  .env.example  README.md
```

---

## 5. Правила парсинга (жёсткие)

- Конвейер: `normalize_headers` → `resolve_required_columns` (rows непуст, нет колонки → `SchemaError`) →
  per-row parse (битые отсеять) → **dedup среди валидных** (первый валидный wins) → build `Catalog`.
- **Пустой `rows` (`[]`) → валидный пустой `ParseResult`** (`valid_rows=0`), НЕ `SchemaError`. Защита от обнуления
  каталога пустым снимком — **порог в `cache.try_swap`** (`valid < MIN_VALID_ROWS` → не свапать, старый кэш жив),
  а не исключение в `parse`. `SchemaError` — только реальное отсутствие required колонки при непустых данных.
- **number:** regex-грамматика, не цепочка `replace`. Пробел/U+00A0 = тысячи; запятая = десятичная только если
  одна запятая и <3 цифр после; запятая+точка одновременно или >1 запятой → None; точка-как-тысячи не поддерживается.
  → `Decimal`. Невалид → `None` + `RowIssue(bad_number)` в `parse`, поле «цена по запросу» (строку не роняет).
- **bool:** `TRUE/FALSE`, `1/0`, `да/нет`, `ha/yo'q`, `+/-`, регистронезависимо, апострофы нормализованы. Нераспозн → `None`.
- **currency:** пустая → `default_currency` + `empty_currency`; **непустая не из `allowed_currencies` → `default_currency`
  + `unrecognized_currency`** (не теряем цену, но помечаем). Деградация поля, строку не роняет.
- **dedup `id`:** первый ВАЛИДНЫЙ wins; битые дубликаты не участвуют; прочие → `RowIssue(duplicate_id)`.
- Все issues агрегируются в один **refresh-summary** (`rows_total/valid/skipped, duration_ms, snapshot_age_s,
  schema_ok` + разбивка по `reason`), детали — на debug. Summary формирует `refresh`/`cache`.

## 6. UX / поведение (двухуровневое)

- `/start` → выбор языка (если не выбран) → главное меню. `/start` и `/menu` работают из любого состояния (сброс FSM).
- Меню: категории (inline) + «Поиск» + «Сменить язык».
- Категория → подкатегории (inline). Подкатегория → пагинированный список товаров (`◀/▶`).
- Товар → карточка: фото + имя + desc (фолбэк) + опт/розница (с валютой) + фасовка + «Назад» (на ту же страницу).
- Поиск — FSM (ввод текста), результаты в FSM-data, пагинация по индексам; в callback — только номер страницы.
  Не-текст в режиме поиска → мягко «введите текст». Кнопка «Отмена» сбрасывает FSM.
- callback-схема: `c:<cat>`, `s:<cat>:<sub>`, `pg:<sub>:<page>`, `p:<id>`, `lang:<l>`, `nav:<menu|back>` — все ≤64 байта.
- Протухший id (любого уровня) → мягкий ответ + меню. Фото не ушло → карточка без фото. Caption > 1024 → обрезка `desc`.
- Пустые состояния явны: нет результатов / пустая подкатегория / пустой каталог («обновляется»).
- Каждый `callback_query` обязательно `answer()` (гасить спиннер), в т.ч. в ранних return и при троттлинге.

## 7. Нефункциональные

- Cold-start: на **transient** ошибке (`FetchError.transient`, таймаут, 5xx) — бесконечный backoff с полным
  джиттером, режим «обновляется», не падать. На **non-transient** (битый creds, 401/403/404) — `refresh`
  ПРОБРАСЫВАЕТ `FetchError` наружу, `main` ловит → `error` + `exit(1)` (контейнер падает, оператор видит причину).
  `refresh` различает по `transient`-флагу, не уходит в вечный backoff на конфиг-ошибке.
- Рантайм: API недоступен → отдать последний валидный кэш + `error`. 429 → `refresh` уважает `FetchError.retry_after`
  (вместо джиттер-backoff). `SchemaError` при живом каталоге → keep snapshot + `ttl`.
- Атомарность (§3 инвариант). Single-flight refresh под `asyncio.Lock`.
- Graceful shutdown: `loop.add_signal_handler(SIGTERM/SIGINT)` → stop polling → cancel+await refresh-task
  (suppress CancelledError) → drain хендлеров с таймаутом (`SHUTDOWN_TIMEOUT_S`<grace) → close сессий.
- Docker: exec-форма ENTRYPOINT (или tini), non-root, `STOPSIGNAL SIGTERM`, creds — read-only mount, не в слой.
  polling — строго одна реплика (иначе 409). Healthcheck = liveness процесса, не «каталог загружен».
- Троттлинг: per-user token-bucket, лимит из env, TTL-вытеснение (без утечки памяти).
- Логи: stdlib logging → stdout, JSON; поля refresh: `rows_total/valid/skipped, duration_ms, snapshot_age_s, schema_ok`.
- Секреты: `SecretStr`; `.env`, `*service-account*.json` — в `.gitignore`.

## 8. Ключевые интерфейсы

```python
# ── data layer (чистое ядро) ──
parse(rows, *, default_currency: str, fallback_subcategory: str,
      allowed_currencies: frozenset[str]) -> ParseResult
    # ЧИСТАЯ. rows: Sequence[Mapping[str, str]]. БРОСАЕТ SchemaError при битой схеме
    # (rows непуст, но нет required колонки). Пустой rows → валидный пустой ParseResult (НЕ SchemaError).
ParseResult(catalog: Catalog, issues: tuple[RowIssue, ...], valid_rows: int, skipped_rows: int)
    # catalog НЕ Optional (пустой Catalog при 0 валидных). SchemaError бросается, НЕ хранится полем.
Catalog(products: tuple[Product, ...], by_id: Mapping[str, Product]); Catalog.build(products)
RowIssue(row_number: int, product_id: str | None, reason: str, detail: str)
    # reason: missing_required | bad_number | unrecognized_bool | duplicate_id
    #       | empty_subcategory | empty_currency | unrecognized_currency | empty_is_active
Snapshot(catalog: Catalog | None, updated_at: datetime | None, valid_rows: int, skipped_rows: int)
coerce.parse_number(raw: str) -> Decimal | None
coerce.parse_bool(raw: str) -> bool | None
# ── data layer (грязный I/O) ──
fetch.fetch_rows(client, spreadsheet_id, worksheet_name) -> list[dict[str, str]]   # все ячейки str
FetchError(Exception): transient: bool; retry_after: float | None
    # 429 → transient=True + retry_after из заголовка; 401/403/404/битый creds → transient=False
CatalogCache.get_snapshot() -> Snapshot                        # синхронно, без сети, без Lock
async CatalogCache.try_swap(result, *, now: datetime | None = None) -> bool
    # под asyncio.Lock; ставит снимок только если порог пройден
    # (skipped/(valid+skipped) ≤ 0.5 И valid ≥ MIN_VALID_ROWS). now=None → datetime.now(timezone.utc).
BackoffConfig(base_s: float, max_s: float)
async refresh.run_refresh_loop(cache, fetch_fn, parse_fn, ttl_seconds, backoff, *,
                               sleeper=asyncio.sleep, rng=None) -> None
    # fetch_fn: Callable[[], Awaitable[list[dict[str,str]]]] — async-АДАПТЕР, НЕ сам fetch_rows.
    # Адаптер собирается в main.py: lambda: asyncio.to_thread(fetch_rows, client, sid, sheet).
    # transient FetchError → backoff(cold-start) / ttl(live); 429 → уважать retry_after.
    # non-transient FetchError → ПРОБРОСИТЬ наружу (main: error + exit(1)). SchemaError → keep snapshot.
# ── services / bot (последующие планы) ──
CatalogService.list_categories(lang) / subcategories(cat_id, lang) / page(sub_id, page, lang) / product_card(id, lang)
SearchService.search(query, lang, page) -> PageView
normalize.normalize(text, lang) -> str
formatting.format_price(value: Decimal | None, currency: str, lang) -> str
formatting.truncate_caption(text, limit=1024) -> str
locales.get_text(key, lang) -> str
```

## 9. ADR (Nygard, `docs/adr/`, заводятся при одобрении)

0001 Источник = Google Sheets · 0002 fetch/parse split · 0003 in-memory TTL atomic single-flight ·
0004 фоновая refresh-task · 0005 границы слоёв · 0006 callback-id стратегия + протухание ·
0007 UZ-нормализация (таблица) · 0008 транспорт polling/webhook · 0009 доставка SA-секрета ·
0010 мультивалютность per-товар · 0011 двухуровневые категории.

## 10. Тест-стратегия и DoD

- `pytest` + `pytest-asyncio` (strict), хендлеры через `MockedBot`, без сети (socket-guard).
- TDD: **первый артефакт — падающий `tests/data/test_parse.py`** на строковых фикстурах (всё `str`).
- Покрытие: 100% на `data/parse.py` и `services/normalize.py`; ~80% агрегатно.
- Время-зависимое (backoff, single-flight) — через мок sleeper/`asyncio.Event`, без реальных задержек.
- DoD сверх §8 брифа: фолбэк `desc`; протухший callback (категория/подкатегория/товар/страница); обрезка caption;
  пустые состояния; `len(callback_data.encode()) ≤ 64` на UZ-категориях; `set(ru.keys())==set(uz.keys())`;
  мультивалютный `format_price`; пустая `subcategory`→«Прочее»; пустое `is_active`→видим+warning.
- Гейт `Makefile`/`nox`: ruff → mypy --strict → pytest --cov; тот же в pre-commit и CI.

---

## 11. Открытые вопросы (вынесены, не выдуманы)

- Точный набор валют и их формат-правила (символ/позиция/разделитель) — подтвердить список для `.env`/`locales`.
- Webhook-инфра клиента (домен/TLS/reverse-proxy) — пока флаг выключен.
- Persist языка/состояния (SQLite/Redis) — отложено, in-memory + TODO.
- Точная задержка видимости правок = TTL (документировать ожидание клиенту).
