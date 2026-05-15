# Дизайн: слой `services` (мост бот↔кэш)

> Статус: **на ревью**. Источник требований — `BRIEF.md` (§5 UX, §6 архитектура), инварианты — `CLAUDE.md`.
> Продолжает серию `data → services → bot → infra`. Опирается на `data`-дизайн
> (`2026-05-31-price-list-bot-design.md`) и готовый слой `data`. Дата: 2026-06-01.

---

## 1. Роль и принцип

`services` — **единственный мост** между хендлерами `bot` и кэшем каталога. Зеркалит дисциплину `data`:
**чистое ядро над иммутабельным `Catalog`** (навигация, пагинация, поиск, форматирование — чистые функции,
тестируются на статических `Catalog`-фикстурах без сети) + **тонкий cache-aware фасад** `CatalogService`,
который читает снимок и заворачивает исход.

Жёсткие границы (инварианты `CLAUDE.md`):
- `services` **не импортирует aiogram** и **не ходит** в gspread/`data` напрямую.
- Чтение кэша — **только** `CatalogCache.get_snapshot()` (синхронно, без сети, без Lock).
- Работа с иммутабельными `Snapshot`/`Catalog`/`Product` из `src/data/models.py`.

`services` отдаёт **презентационно-готовые view-модели**; `bot` — тупой транспорт «view → клавиатура».
Вся презентация без aiogram (выбор языка, фолбэк `desc`, формат цены, обрезка caption, i18n) — здесь,
поэтому тестируется без aiogram-моков.

---

## 2. Решения штурма (2026-06-01)

| # | Решение | Почему |
|---|---|---|
| 1 | **View-модели с готовыми строками.** `services` делает всю презентацию, отдаёт frozen-dataclass + стабильные id. `bot` тонкий. | Единственное место презентации; тестируется без aiogram; ложится на скоуп services. |
| 2 | **Стабильный id группы = `blake2s(normalize(key), digest_size=6)` → 12 hex.** Категория, подкатегория, **и товар**. | ASCII, фикс. длина (влезает в 64 байта), стабилен между снимками, язык-агностичен. |
| 3 | **Порядок таблицы** на всех уровнях (insertion order строк листа). | Клиент управляет порядком через строки — главный принцип «клиент рулит таблицей, без кода». |
| 4 | **`ViewResult[T] = Ok[T] | Stale`** — единый union-исход для всех уровней. | Протухание — нормальный поток, не исключение; отличается от «пусто» (разный UX-текст). |
| 5 | **Чистое ядро + тонкий фасад.** Фасад читает снимок **1 раз/запрос**, мемоизирует индекс по идентичности снимка. | Консистентность снимка в пределах клика; 100% покрытие ядра на фикстурах. |
| 6 | **Символ валюты — в i18n** (`сум`/`so'm`), число форматируется единообразно (пробел-тысячи, символ после). | Язык-зависимый символ — переводимая строка; YAGNI на пер-валютный формат-движок. |

### Следствия (приняты, оспоримы)
- **Навигация строится только по активным товарам** (`is_active=True`). Категория/подкатегория, где все
  товары скрыты, в меню **не показывается** (клик не ведёт в пустоту). Совпадает с «клиент прячет галочкой».
- **Подкатегория хешируется от пары `(category, subcategory)`**, не от голого имени: «Прочее»/«0.5л»
  повторяются в разных категориях и голый хеш имени их склеит. Это правка callback-схемы `data`-дизайна
  (`pg:<sub>:<page>` без категории — баг): `sub_id = blake2s(normalize(cat) + "\x1f" + normalize(sub))`.
- **Товар тоже хешируется** (`Product.id` клиента может быть длинным → риск >64 байта в callback).
  Обратная карта `prod_id → Product` — в индексе.
- **Единственная группа «Прочее»** не схлопывается: обычная двухуровневая навигация (лишний клик принят).
- **Поиск:** подстрока по `name_{текущий язык}`, нормализованная, только активные, по всему каталогу.
  Запрос живёт в FSM-data; `search(query, lang, page)` перевыполняется на каждой странице (в callback —
  только номер страницы, не запрос и не списки).

### Что `services` НЕ делает (уже сделал `data`)
`category`/`subcategory`/`currency` приходят **непустыми** (`data` подставил fallback/default), имена
непусты, цены — `Decimal | None`. `services` трактует `category`/`subcategory`/`currency` как
непрозрачные непустые строки и не валидирует их повторно.

---

## 3. Дерево модулей

```
src/services/
  models.py     # view-модели (frozen) + ViewResult: Ok[T] | Stale + Lang
  ids.py        # group_id(*parts) -> 12 hex (blake2s(normalize), digest_size=6); чистая
  normalize.py  # UZ латиница↔кириллица + апострофы (явная таблица); normalize(text, lang)
  index.py      # CatalogIndex: двухуровневый индекс над Catalog + обратные карты id→группа
  pagination.py # paginate(items, page, page_size) -> Page[T]; чистая, clamp страницы
  formatting.py # format_price, desc-фолбэк, сборка+обрезка caption; через locales
  search.py     # search(index, query, lang, page, page_size) -> Page; чистая
  catalog.py    # CatalogService — фасад: cache+settings, snapshot 1x, мемо index, ViewResult
  language.py   # LanguageStore: per-user язык in-memory (dict), отдельно от FSM
src/locales/
  __init__.py   # get_text(key, lang); инвариант set(ru.keys()) == set(uz.keys())
  ru.py uz.py   # i18n словари (UI-строки + символы валют)
```

`data` не трогаем. `bot` (следующий план) импортирует `services`, но не наоборот.

---

## 4. Контракты (типы на стыках)

```python
type Lang = Literal["ru", "uz"]

# ── ViewResult: единый исход для запросов по id ──
@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T
@dataclass(frozen=True, slots=True)
class Stale:                       # «каталог обновился, откройте заново» + меню
    ...
type ViewResult[T] = Ok[T] | Stale

# ── view-модели (frozen) ──
@dataclass(frozen=True, slots=True)
class CategoryItem:    id: str; title: str          # id = group hash; title = сырое имя категории
@dataclass(frozen=True, slots=True)
class SubcategoryItem: id: str; title: str          # id = hash(category, subcategory)
@dataclass(frozen=True, slots=True)
class ProductListItem: id: str; title: str          # id = hash(product.id); title = name_{lang}+фолбэк
@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    items: tuple[T, ...]; page: int; total_pages: int; has_prev: bool; has_next: bool
@dataclass(frozen=True, slots=True)
class ProductCard:
    text: str                                       # готовый локализованный caption, ≤ лимита
    photo: str | None                               # сырой URL/file_id; доставку решает bot

# ── чистое ядро ──
ids.group_id(*parts: str) -> str                    # blake2s(normalize-join(parts), 6).hex() = 12 hex
normalize.normalize(text: str, lang: Lang) -> str   # lower+trim+collapse; uz: латиница↔кириллица+апостроф
pagination.paginate(items: Sequence[T], page: int, page_size: int) -> Page[T]   # page 1-based, clamp
formatting.format_price(value: Decimal | None, currency: str, lang: Lang) -> str # None → «цена по запросу»
formatting.product_card(product: Product, lang: Lang) -> ProductCard  # лимит caption — Telegram-константа, по photo
search.search(index: CatalogIndex, query: str, lang: Lang, page: int, page_size: int) -> Page[ProductListItem]

class CatalogIndex:                                 # чистая сборка над Catalog (active-only, table order)
    @classmethod
    def build(cls, catalog: Catalog | None) -> CatalogIndex: ...
    categories: tuple[CategoryItem, ...]
    def subcategories(self, cat_id: str) -> tuple[SubcategoryItem, ...] | None     # None = неизвестный id
    def products(self, sub_id: str) -> tuple[Product, ...] | None
    def product(self, prod_id: str) -> Product | None
    active_products: tuple[Product, ...]            # для поиска

# ── cache-aware фасад ──
class CatalogService:
    def __init__(self, cache: CatalogCache, settings: Settings) -> None: ...
    def categories(self) -> tuple[CategoryItem, ...]                         # пусто → «обновляется»
    def subcategories(self, cat_id: str) -> ViewResult[tuple[SubcategoryItem, ...]]
    def product_page(self, sub_id: str, page: int, lang: Lang) -> ViewResult[Page[ProductListItem]]
    def product_card(self, prod_id: str, lang: Lang) -> ViewResult[ProductCard]
    def search(self, query: str, lang: Lang, page: int) -> Page[ProductListItem]  # без id → без Stale; пусто → пустой Page

# ── per-user язык (in-memory, отдельно от FSM) ──
class LanguageStore:
    def get(self, user_id: int) -> Lang | None      # None → язык ещё не выбран → показать picker
    def set(self, user_id: int, lang: Lang) -> None
```

`PAGE_SIZE` фасад берёт из `Settings` и прокидывает в `paginate` параметром (ядро остаётся чистым).
Лимит caption — **протокольная Telegram-константа**, не конфиг: 1024 при наличии фото, иначе 4096
(лимит сообщения). `product_card` выбирает лимит детерминированно по `product.photo` (модульные
константы), обрезается только `desc`, цены/имя не режутся. Дегенеративный случай (само имя+цены > лимита)
— known limitation: имена коротки по контракту данных, отдельно не клампится.

---

## 5. CatalogIndex — двухуровневая сборка над плоским Catalog

Вход — `catalog.products`; в индекс попадают **только `is_active=True`**, в порядке строк:
- `categories: tuple[CategoryItem, ...]` — по первому появлению `category` среди активных.
- `subcats_by_cat: dict[cat_id, tuple[SubcategoryItem, ...]]` — по первому появлению `subcategory` в категории.
- `products_by_sub: dict[sub_id, tuple[Product, ...]]` — активные товары группы в порядке строк.
- `prod_by_id: dict[prod_id, Product]` — обратная карта для карточки.
- `active_products: tuple[Product, ...]` — плоско, для поиска.

`cat_id = group_id(category)`, `sub_id = group_id(category, subcategory)`, `prod_id = group_id(product.id)`.

**Категория/подкатегория видимы, только если содержат ≥1 активный товар** (пустые отсутствуют → клик в
пустоту невозможен). Если категория существует, у неё ≥1 подкатегория; если подкатегория существует, у неё
≥1 товар — поэтому `Ok` всегда непуст (кроме поиска).

**Коллизия хешей** (два разных нормализованных имени → один id): лог `error`, первый wins, остальные
склеиваются — документируется как known limitation (аналог коллизии заголовков в `data`). 48-битный
blake2s на ~50 группах делает это практически невозможным; явная проверка в `build` + лог.

`cold-start`: `catalog=None` → `CatalogIndex.build(None)` даёт пустой индекс (всё пусто, без падения).

---

## 6. Фасад: чтение снимка и мемоизация

`CatalogService` держит `CatalogCache` и `Settings`. На каждый публичный вызов:
1. `snap = cache.get_snapshot()` — **ровно один** read (консистентность в пределах клика).
2. Если `snap is self._cached_snap` — переиспользует `self._cached_index`; иначе строит
   `CatalogIndex.build(snap.catalog)` и кеширует (индекс строится **раз на снимок**, не на клик).
3. Делегирует чистому ядру, заворачивает в `Ok`/`Stale`.

`Snapshot` иммутабелен и свапается заменой ссылки → identity-сравнение `is` корректно различает снимки.

---

## 7. Поток данных (UX, §5/§6 брифа)

```
/start → LanguageStore.get(uid):
    None → выбор языка (lang:ru / lang:uz) → set → categories()
    есть → categories()
categories() → []  → «каталог обновляется»  (cold-start / всё неактивно)
              → items → меню: c:<cat_id> + «Поиск» + «Сменить язык»
c:<cat_id>     → subcategories(cat_id) → Ok(items) → g:<sub_id> | Stale → меню
g:<sub_id>     → product_page(sub_id, 1, lang)    → Ok(Page) → p:<prod_id> + ◀/▶ | Stale → меню
◀/▶ pg:<sub_id>:<page> → product_page(sub_id, page, lang)  (page clamp, не Stale)
p:<prod_id>    → product_card(prod_id, lang) → Ok(ProductCard) → фото+caption | Stale → меню
Поиск (FSM): запрос в FSM-data → search(query, lang, page) → Page (пусто → «ничего не найдено»)
```

callback-схема (`bot` строит строки; `services` лишь поставляет 12-hex id): `c:<cat>`, `g:<sub>`,
`pg:<sub>:<page>`, `p:<prod>:<sub>:<page>` (несёт origin для «Назад на ту же страницу»), `lang:<l>`,
`nav:<menu|back>`. Все ≤ 64 байта (id фиксированы 12 hex). **`bot` никогда не считает хеш сам** — кладёт
полученный id дословно и возвращает строку в `services`.

---

## 8. Граничные случаи (закрыты)

| Случай | Поведение |
|---|---|
| cold-start (`catalog=None`) / все товары неактивны | `categories()` → `()` → «каталог обновляется» |
| протухший cat/sub/prod id | `Stale` → мягко «обновилось» + меню |
| страница за пределом (каталог сжался) | clamp к последней валидной, **не** Stale |
| пустой/мусорный поиск | `Page(items=())` → «ничего не найдено» (≠ Stale) |
| единственная группа «Прочее» | обычная двухуровневая навигация, без авто-схлопывания |
| `price=None` | «цена по запросу» (i18n) |
| `desc_{lang}` пусто | фолбэк на второй язык; оба пусты → карточка без описания |
| `name_{lang}` пусто | дефенсивный фолбэк на второй язык (хотя `data` гарантирует непустые) |
| caption > лимита | обрезка `desc` по границе слова + «…»; имя/цены не режутся |
| кросс-скрипт поиск (uz латиница ↔ кириллица) | нормализация обоих к канону → находит |

---

## 9. Нормализация UZ (явная таблица, обязательные юнит-тесты)

Цель: запрос на любой письменности находит товар, чьё `name_uz` ведётся на другой. Реализация —
**явная таблица соответствий** латиница↔кириллица + варианты апострофа, не «заменить пару символов»:
- Обе стороны (запрос и `name_uz`) приводятся к **единому канону** (латиница), затем подстрочное сравнение.
- Диграфы (`ch/sh/ng/yo/yu/ya/oʻ/gʻ`) обрабатываются до одиночных букв.
- Апостроф-варианты (`ʻ` U+02BB, `'` U+2018, `'` U+2019, `` ` `` U+0060, `'` U+0027) унифицируются.
- `ru`-нормализация проще: `lower + trim + collapse whitespace` (+ `ё→е`).
- `normalize` под `lang`: для `ru` — короткий путь; для `uz` — полная таблица. Покрытие 100%.

Конкретная таблица фиксируется при реализации + ADR `UZ-нормализация (таблица)`.

---

## 10. Тест-стратегия (TDD, Red→Green, статические `Catalog`-фикстуры, без сети)

| Файл | Покрывает |
|---|---|
| `tests/services/test_normalize.py` | UZ обе письменности находят друг друга, апострофы, диграфы, ru; **100%** |
| `tests/services/test_ids.py` | стабильность (имя→id детерминирован), длина 12 hex, пара (cat,sub) ≠ голый sub, коллизии |
| `tests/services/test_index.py` | двухуровневая сборка, active-only, порядок таблицы, «Прочее», обратные карты, None-каталог |
| `tests/services/test_pagination.py` | clamp page, `total_pages`, `has_prev/next`, пусто, одна страница |
| `tests/services/test_formatting.py` | `format_price` мультивалюта/`None`/тысячи, desc-фолбэк, обрезка caption 1024 |
| `tests/services/test_search.py` | подстрока, нормализация, active-only, кросс-скрипт, пусто → Ok-пустой, пагинация |
| `tests/services/test_catalog_service.py` | cold-start→пусто, Stale на неизвестный id, валидный поток→Ok, мемо (1 build/снимок), ребилд при свапе |
| `tests/services/test_language.py` | get/set, unknown → None |

Инвариант i18n: тест `set(ru.keys()) == set(uz.keys())`. Тест `len(callback_data.encode()) ≤ 64` на
реальных UZ-именах категорий — формально это `bot`-слой, но id-генерация проверяется здесь.

Покрытие: 100% на `normalize.py`, `ids.py`, `pagination.py`, ядро `index/search/formatting` — близко к 100%.

---

## 11. ADR (Nygard, `docs/adr/`, по ходу реализации)

- `callback-id стратегия` — хеш `blake2s` 12 hex для всех уровней; подкатегория от пары `(cat, sub)`;
  стратегия протухания (`ViewResult.Stale`). (Сводит §9 `data`-дизайна 0006.)
- `UZ-нормализация (таблица)` — канон-латиница, диграфы, апострофы. (0007.)
- `services-граница` — view-модели с готовыми строками + `ViewResult`; `bot` тонкий; чистое ядро + фасад.

---

## 12. Открытые вопросы (вынесены, не выдуманы)

- Точная таблица UZ-соответствий (полнота диграфов/диакритик) — фиксируется при реализации `normalize`.
- Текст символов валют per-lang (`сум`/`so'm`, и для прочих валют из `CURRENCIES`) — подтвердить список
  при наполнении `locales`.
- Авто-схлопывание единственной подкатегории «Прочее» — пока **нет** (лишний клик принят); пересмотреть
  по фидбеку клиента.
