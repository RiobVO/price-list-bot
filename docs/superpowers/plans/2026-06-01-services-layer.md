# План реализации: слой `services`

> **Для агентов-исполнителей:** ОБЯЗАТЕЛЬНЫЙ СУБ-СКИЛЛ — superpowers:subagent-driven-development
> (рекомендуется) или superpowers:executing-plans. Шаги используют чекбоксы `- [ ]`.

**Goal:** Построить чистый, полностью протестированный слой `services` — единственный мост бот↔кэш:
двухуровневая навигация, пагинация, поиск с UZ-нормализацией, форматирование цены/карточки, протухание
callback-id, per-user язык. Без сети в тестах.

**Architecture:** Чистое ядро над иммутабельным `Catalog` (`normalize`, `ids`, `pagination`, `formatting`,
`index`, `search` — чистые, тестируются на статических `Catalog`-фикстурах) + тонкий cache-aware фасад
`CatalogService` (читает снимок 1×/запрос через `get_snapshot()`, мемоизирует индекс по идентичности
снимка, заворачивает исход в `Ok | Stale`). `services` не импортирует aiogram, не ходит в gspread/data.

**Tech Stack:** Python 3.11+, pydantic-settings (`Settings`), pytest + pytest-asyncio (strict), ruff,
mypy --strict. Хеш id — `hashlib.blake2s`.

**Источники:** дизайн — `docs/superpowers/specs/2026-06-01-services-layer-design.md`; инварианты — `CLAUDE.md`;
готовый слой `data` — `src/data/`. Второй план серии: data → **services** → bot → infra.

## Порядок и зависимости

Реализовывать строго по порядку (каждый модуль предполагает предыдущие готовы):

`models → normalize → ids → locales → pagination → conftest-factory → formatting → index → search → catalog → language`

Предусловие (готово после слоя `data`): git-репо на `main`, `pyproject.toml` (ruff select E,F,I,UP,B,ASYNC;
mypy --strict; pytest asyncio_mode=strict; coverage source=src), пакеты `src/services/__init__.py`,
`tests/services/__init__.py`, `tests/conftest.py` (autouse socket-guard), `src/config.py`, `src/data/*`,
установленные зависимости. Файлов модулей `services` (кроме `__init__.py`) ещё НЕТ — первый Red каждой
задачи это `ImportError: cannot import name … from src.services.…` (символ из НАШЕГО файла), а не
`No module named src`.

Команды кроссплатформенны, запускать из корня `E:\ADEL`. Где `python` недоступен — `py`.

## Правки ревью

План прошёл двойное adversarial-ревью (согласованность типов + полнота/TDD). Оба вердикта — CHANGES
REQUESTED; правки применены инлайн в план/спеку:

- **Спека §4/§141:** сигнатура `product_card(product, lang)` — лимит caption это Telegram-константа
  (1024/4096 по `photo`), не конфиг-параметр. (Ревьюер-1 предлагал param — отклонено как over-engineering.)
- **Task 6.4:** исправлен ассерт обрезки (многоточие в среднем сегменте `desc`, не в конце текста).
- **Task 3.1:** добавлен тест `len(callback) ≤ 64` байта на длинных UZ-именах (§10, инвариант CLAUDE.md).
- **Task 4.1:** `get_text(lang: str)` — убрана зависимость `locales → services.models` (инверсия слоёв).
  Уточнён честный Red (`cannot import name 'get_text'`).
- **Task 1.1:** `test_stale` заменён с тавтологии на проверку value-equality.
- **Task 2.1:** добавлены кросс-скрипт кейсы диграфов `yu/ya/ng/sh`.
- **Task 7.1:** добавлены тесты единственной группы «Прочее» и коллизии хешей (покрывает error-ветку
  `_register`).
- **Tasks 2.1/3.1/9.4:** добавлены шаги создания ADR (0007/0006/0012) с коммитами.
- **Task 6.2:** ревьюер счёл negative-ветку `format_price` мёртвой — **отклонено** (проверено: `parse_number`
  принимает `-N`, ветка достижима И нужна для верной группировки разрядов); вместо удаления добавлен тест
  на отрицательную цену.

Остаточные known-limitations (осознанно не закрываются тестами): вырожденный caption (имя+цены > лимита);
фасадные обёртки clamp/пустоты не дублируют ядро отдельными тестами (тонкое делегирование).

---

# Группа задач 1: src/services/models.py

Чистый модуль типов: frozen view-модели + `Ok`/`Stale` (+ alias `ViewResult`) + `Lang`. Зависимостей от
других модулей проекта нет (только stdlib/typing). Импортируемые символы: `Lang`, `Ok`, `Stale`,
`ViewResult`, `CategoryItem`, `SubcategoryItem`, `ProductListItem`, `Page`, `ProductCard`.

Декомпозиция: две подзадачи — (1) исход `Ok`/`Stale`/`ViewResult`/`Lang`; (2) view-модели. Каждая вводит
НОВЫЕ символы, чей импорт реально падает до реализации.

---

### Task 1.1 — `Lang`, `Ok`, `Stale`, `ViewResult`

**Files:**
- Create: `src/services/models.py`
- Test: `tests/services/test_models.py`

- [ ] **Write failing test** — `tests/services/test_models.py`:

```python
"""Тесты view-моделей и исхода ViewResult слоя services."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.services.models import Ok, Stale


def test_ok_carries_value() -> None:
    ok = Ok(value=(1, 2, 3))
    assert ok.value == (1, 2, 3)


def test_ok_is_frozen() -> None:
    ok: Ok[int] = Ok(value=1)
    with pytest.raises(FrozenInstanceError):
        ok.value = 2  # type: ignore[misc]


def test_stale_instances_are_value_equal() -> None:
    """Stale — пустой frozen-маркер протухания: два экземпляра равны по значению."""
    assert Stale() == Stale()
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_models.py -q`
  Expected: `ImportError: cannot import name 'Ok' from 'src.services.models'` (символ отсутствует — честный Red).

- [ ] **Minimal CORRECT impl** — `src/services/models.py`:

```python
"""View-модели слоя services и единый исход запроса по id (ViewResult).

Чистый модуль типов: без зависимостей на data/bot/aiogram.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeAlias, TypeVar

Lang = Literal["ru", "uz"]

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Успешный исход запроса по id: несёт готовую view-модель."""

    value: T


@dataclass(frozen=True, slots=True)
class Stale:
    """Протухший callback-id: «каталог обновился, откройте заново» + возврат в меню."""


# Документационный и аннотационный alias. В сигнатурах допустимы обе формы:
# ViewResult[X] и явная Ok[X] | Stale — они эквивалентны.
ViewResult: TypeAlias = Ok[T] | Stale
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_models.py -q`
  Expected: зелёные.

- [ ] **Lint/type green** — `ruff check src/services/models.py tests/services/test_models.py && ruff format --check src/services/models.py tests/services/test_models.py && mypy --strict src/services/models.py tests/services/test_models.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/models.py tests/services/test_models.py && git commit -m "feat(services): add Lang and ViewResult (Ok/Stale) outcome types"`

---

### Task 1.2 — view-модели `CategoryItem`, `SubcategoryItem`, `ProductListItem`, `Page`, `ProductCard`

**Files:**
- Modify: `src/services/models.py`
- Test: `tests/services/test_models.py`

- [ ] **Write failing test** — в `tests/services/test_models.py` заменить верхний импорт `from src.services.models import Ok, Stale` на расширенный (все импорты в шапке файла, без `# noqa`), затем добавить тела тестов:

```python
from src.services.models import (
    CategoryItem,
    Ok,
    Page,
    ProductCard,
    ProductListItem,
    Stale,
    SubcategoryItem,
)


def test_view_items_hold_id_and_title() -> None:
    assert CategoryItem(id="ab12", title="Напитки").title == "Напитки"
    assert SubcategoryItem(id="cd34", title="Соки").id == "cd34"
    assert ProductListItem(id="ef56", title="Сок яблочный").title == "Сок яблочный"


def test_view_items_are_frozen() -> None:
    item = CategoryItem(id="ab12", title="Напитки")
    with pytest.raises(FrozenInstanceError):
        item.title = "Еда"  # type: ignore[misc]


def test_page_holds_items_and_navigation_flags() -> None:
    page: Page[CategoryItem] = Page(
        items=(CategoryItem(id="a", title="A"),),
        page=1,
        total_pages=3,
        has_prev=False,
        has_next=True,
    )
    assert page.items[0].title == "A"
    assert page.page == 1
    assert page.total_pages == 3
    assert page.has_prev is False
    assert page.has_next is True


def test_product_card_holds_text_and_optional_photo() -> None:
    card = ProductCard(text="Сок\n\nОпт: 100 сум", photo=None)
    assert card.text.startswith("Сок")
    assert card.photo is None
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_models.py -q`
  Expected: `ImportError: cannot import name 'CategoryItem' from 'src.services.models'`.

- [ ] **Minimal CORRECT impl** — добавить в `src/services/models.py` (после `ViewResult`):

```python
@dataclass(frozen=True, slots=True)
class CategoryItem:
    """Пункт меню категории. id — стабильный хеш для callback; title — сырое имя категории."""

    id: str
    title: str


@dataclass(frozen=True, slots=True)
class SubcategoryItem:
    """Пункт меню подкатегории. id — хеш пары (category, subcategory)."""

    id: str
    title: str


@dataclass(frozen=True, slots=True)
class ProductListItem:
    """Строка списка товаров. id — хеш product.id; title — name_{lang} с фолбэком."""

    id: str
    title: str


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    """Страница пагинации (1-based) с флагами навигации."""

    items: tuple[T, ...]
    page: int
    total_pages: int
    has_prev: bool
    has_next: bool


@dataclass(frozen=True, slots=True)
class ProductCard:
    """Готовая карточка товара: локализованный текст (≤ лимита) + сырой photo (URL/file_id)."""

    text: str
    photo: str | None
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_models.py -q`
  Expected: все тесты файла зелёные.

- [ ] **Lint/type green** — `ruff check src/services/models.py tests/services/test_models.py && ruff format --check src/services/models.py tests/services/test_models.py && mypy --strict src/services/models.py tests/services/test_models.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/models.py tests/services/test_models.py && git commit -m "feat(services): add view models (category/subcategory/product/page/card)"`

---

# Группа задач 2: src/services/normalize.py

Чистая нормализация строк для поиска и хеш-id. UZ — **явная таблица** кириллица→латиница + унификация
апострофов; обе письменности сводятся к единому канону (латиница), поэтому запрос на любой письменности
находит имя на другой. `ru` — короткий путь (`lower+trim+collapse+ё→е`). Импортируемый символ: `normalize`.
Зависит только от `src.services.models` (`Lang`).

Одна задача = вся функция (структурная, не наращиваемая). 100% покрытие.

---

### Task 2.1 — `normalize(text, lang)`

**Files:**
- Create: `src/services/normalize.py`
- Test: `tests/services/test_normalize.py`

- [ ] **Write failing test** — `tests/services/test_normalize.py`:

```python
"""Тесты UZ-нормализации: кросс-скрипт совпадение, апострофы, ru-путь."""
from __future__ import annotations

import pytest

from src.services.normalize import normalize


@pytest.mark.parametrize(
    ("latin", "cyrillic"),
    [
        ("olma", "олма"),          # яблоко
        ("sharbat", "шарбат"),     # сок
        ("choʻchqa", "чўчқа"),     # oʻ ↔ ў
        ("gʻalla", "ғалла"),       # gʻ ↔ ғ
        ("qand", "қанд"),          # q ↔ қ
        ("halqa", "ҳалқа"),        # h ↔ ҳ (и q↔қ)
        ("yongʻoq", "ёнғоқ"),      # ё→yo, нғ→ngʻ→ng..., қ→q
        ("yulduz", "юлдуз"),       # диграф yu ↔ ю
        ("yangi", "янги"),         # диграф ya ↔ я
        ("shamol", "шамол"),       # диграф sh ↔ ш
        ("tong", "тонг"),          # ng (н+г) ↔ нг
    ],
)
def test_uz_cross_script_canonical_equal(latin: str, cyrillic: str) -> None:
    """Латиница и кириллица одного слова дают одинаковый канон."""
    assert normalize(latin, "uz") == normalize(cyrillic, "uz")


@pytest.mark.parametrize("apostrophe", ["ʻ", "’", "ʼ", "`", "‘"])
def test_uz_apostrophe_variants_unified(apostrophe: str) -> None:
    """Любой вариант апострофа в oʻ сводится к каноническому U+0027."""
    assert normalize(f"o{apostrophe}simlik", "uz") == normalize("o'simlik", "uz")


def test_uz_lower_trim_collapse_whitespace() -> None:
    assert normalize("  OLMA   sharbati  ", "uz") == "olma sharbati"


def test_ru_lowercases_trims_and_folds_yo() -> None:
    assert normalize("  Ёлка  ", "ru") == "елка"


def test_ru_does_not_apply_uz_table() -> None:
    """ru-путь не транслитерирует кириллицу в латиницу (ч остаётся ч)."""
    assert normalize("Чай", "ru") == "чай"


def test_empty_and_whitespace_normalize_to_empty() -> None:
    assert normalize("", "uz") == ""
    assert normalize("   ", "ru") == ""
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_normalize.py -q`
  Expected: `ImportError: cannot import name 'normalize' from 'src.services.normalize'`.

- [ ] **Minimal CORRECT impl** — `src/services/normalize.py`:

```python
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
    "а": "a", "б": "b", "в": "v", "г": "g", "ғ": "g'", "д": "d", "е": "e",
    "ё": "yo", "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "қ": "q",
    "л": "l", "м": "m", "н": "n", "о": "o", "ў": "o'", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ҳ": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "ъ": "'", "ы": "i", "ь": "", "э": "e", "ю": "yu",
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
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_normalize.py -q`
  Expected: все кейсы зелёные.

- [ ] **Coverage 100% на модуле** — `python -m pytest tests/services/test_normalize.py --cov=src/services/normalize --cov-report=term-missing -q`
  Expected: `src/services/normalize.py` 100%, нет `Missing`.

- [ ] **Lint/type green** — `ruff check src/services/normalize.py tests/services/test_normalize.py && ruff format --check src/services/normalize.py tests/services/test_normalize.py && mypy --strict src/services/normalize.py tests/services/test_normalize.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/normalize.py tests/services/test_normalize.py && git commit -m "feat(services): add UZ-aware text normalization (cyrillic/latin + apostrophes)"`

- [ ] **ADR** — создать `docs/adr/0007-uz-normalization-table.md` (Nygard, Статус `Accepted`). Решение: единый канон-латиница, явная таблица кириллица→латиница + унификация апострофов, диграфы до одиночных букв; ru — короткий путь. Альтернатива (отвергнута): «замена пары символов». Коммит: `git add docs/adr/0007-uz-normalization-table.md && git commit -m "docs(adr): record UZ normalization table approach"`

---

# Группа задач 3: src/services/ids.py

Стабильный 12-hex id группы: `blake2s(normalize-join(parts), digest_size=6)`. Части нормализуются единым
каноном (uz), склеиваются разделителем `\x1f`. Импортируемый символ: `group_id`. Зависит от
`src.services.normalize`. 100% покрытие.

---

### Task 3.1 — `group_id(*parts)`

**Files:**
- Create: `src/services/ids.py`
- Test: `tests/services/test_ids.py`

- [ ] **Write failing test** — `tests/services/test_ids.py`:

```python
"""Тесты стабильного хеш-id групп для callback_data."""
from __future__ import annotations

from src.services.ids import group_id


def test_id_is_12_hex_chars() -> None:
    value = group_id("Напитки")
    assert len(value) == 12
    assert all(c in "0123456789abcdef" for c in value)


def test_id_is_deterministic() -> None:
    assert group_id("Напитки") == group_id("Напитки")


def test_id_is_case_and_whitespace_insensitive() -> None:
    assert group_id("  напитки ") == group_id("Напитки")


def test_id_is_script_insensitive_for_uz() -> None:
    """Одно имя на латинице и кириллице даёт один id (канон-нормализация)."""
    assert group_id("olma") == group_id("олма")


def test_pair_id_differs_from_bare_subcategory() -> None:
    """id пары (category, subcategory) ≠ id голой подкатегории — одноимённые
    подкатегории в разных категориях не склеиваются."""
    assert group_id("Напитки", "Прочее") != group_id("Еда", "Прочее")
    assert group_id("Напитки", "Прочее") != group_id("Прочее")


def test_different_inputs_give_different_ids() -> None:
    assert group_id("Напитки") != group_id("Еда")


def test_worst_case_callback_within_64_bytes() -> None:
    """Худший callback p:<prod>:<sub>:<page> из 12-hex id влезает в лимит Telegram (64 байта).

    Длинное UZ-имя категории не раздувает id (хеш фикс. длины) — инвариант callback_data ≤ 64.
    """
    long_uz = "узоқ номли категория " * 5
    prod = group_id("очень-длинный-идентификатор-товара-из-таблицы")
    sub = group_id(long_uz, "подкатегория")
    callback = f"p:{prod}:{sub}:9999"
    assert len(callback.encode("utf-8")) <= 64
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_ids.py -q`
  Expected: `ImportError: cannot import name 'group_id' from 'src.services.ids'`.

- [ ] **Minimal CORRECT impl** — `src/services/ids.py`:

```python
"""Стабильные короткие id групп для callback_data (blake2s от канона имени)."""
from __future__ import annotations

import hashlib

from src.services.normalize import normalize

# Разделитель частей ключа: управляющий символ, не встречающийся в именах.
_SEP = "\x1f"
# 6 байт → 12 hex: влезает в callback_data (≤64 байта) с большим запасом.
_DIGEST_SIZE = 6


def group_id(*parts: str) -> str:
    """Стабильный 12-hex id из частей ключа.

    Части нормализуются единым каноном (uz-таблица) и склеиваются разделителем,
    поэтому один и тот же ключ даёт один id независимо от письменности/регистра.
    Пара (category, subcategory) глобально уникальна — одноимённые подкатегории
    в разных категориях не склеиваются.
    """
    canon = _SEP.join(normalize(part, "uz") for part in parts)
    digest = hashlib.blake2s(canon.encode("utf-8"), digest_size=_DIGEST_SIZE)
    return digest.hexdigest()
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_ids.py -q`
  Expected: зелёные.

- [ ] **Coverage 100% на модуле** — `python -m pytest tests/services/test_ids.py --cov=src/services/ids --cov-report=term-missing -q`
  Expected: 100%.

- [ ] **Lint/type green** — `ruff check src/services/ids.py tests/services/test_ids.py && ruff format --check src/services/ids.py tests/services/test_ids.py && mypy --strict src/services/ids.py tests/services/test_ids.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/ids.py tests/services/test_ids.py && git commit -m "feat(services): add stable blake2s group id for callback data"`

- [ ] **ADR** — создать `docs/adr/0006-callback-id-strategy.md` (формат Nygard: Статус `Accepted` / Контекст / Решение / Последствия / Альтернативы). Решение: blake2s 12-hex для категории/подкатегории/товара; подкатегория от пары `(category, subcategory)`; протухание через `ViewResult.Stale`; коллизия хешей — known limitation с error-логом. Коммит: `git add docs/adr/0006-callback-id-strategy.md && git commit -m "docs(adr): record callback id hashing strategy"`

---

# Группа задач 4: src/locales (ru.py, uz.py, __init__.py)

i18n-реестр: `get_text(key, lang, default=None)`; инвариант `set(ru.keys()) == set(uz.keys())`. Ключи,
нужные `services`: `price_on_request`, `label_wholesale`, `label_retail`, `label_packaging`,
`currency.UZS`. Зависит от `src.services.models` (`Lang`). `src/locales/__init__.py` уже существует с
докстрингом — модифицируется.

---

### Task 4.1 — словари `ru.py` / `uz.py` + `get_text`

**Files:**
- Create: `src/locales/ru.py`
- Create: `src/locales/uz.py`
- Modify: `src/locales/__init__.py`
- Test: `tests/services/test_locales.py`

- [ ] **Write failing test** — `tests/services/test_locales.py`:

```python
"""Тесты i18n-реестра: равенство ключей, выбор языка, фолбэк по default."""
from __future__ import annotations

import pytest

from src.locales import get_text
from src.locales import ru, uz


def test_ru_and_uz_have_identical_keys() -> None:
    """Инвариант: наборы ключей ru и uz совпадают (иначе дыра в переводе)."""
    assert set(ru.TEXTS.keys()) == set(uz.TEXTS.keys())


def test_get_text_returns_localized_value() -> None:
    assert get_text("price_on_request", "ru") == "цена по запросу"
    assert get_text("price_on_request", "uz") == "narxi so'rov bo'yicha"


def test_get_text_unknown_key_with_default_returns_default() -> None:
    assert get_text("currency.USD", "ru", default="USD") == "USD"


def test_get_text_unknown_key_without_default_raises() -> None:
    with pytest.raises(KeyError):
        get_text("nonexistent.key", "ru")
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_locales.py -q`
  Expected: `ImportError: cannot import name 'get_text' from 'src.locales'` — пакет `src/locales/__init__.py` уже существует (scaffold), но `get_text` в нём ещё нет; импорт первой строки теста падает именно на этом символе (честный Red).

- [ ] **Minimal CORRECT impl** — `src/locales/ru.py`:

```python
"""Русские строки интерфейса. Ключи идентичны uz.py (инвариант i18n)."""
from __future__ import annotations

TEXTS: dict[str, str] = {
    "price_on_request": "цена по запросу",
    "label_wholesale": "Опт",
    "label_retail": "Розница",
    "label_packaging": "Фасовка",
    "currency.UZS": "сум",
}
```

`src/locales/uz.py`:

```python
"""Узбекские строки интерфейса. Ключи идентичны ru.py (инвариант i18n)."""
from __future__ import annotations

TEXTS: dict[str, str] = {
    "price_on_request": "narxi so'rov bo'yicha",
    "label_wholesale": "Optom",
    "label_retail": "Chakana",
    "label_packaging": "Qadoq",
    "currency.UZS": "so'm",
}
```

`src/locales/__init__.py` (заменить содержимое целиком):

```python
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
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_locales.py -q`
  Expected: зелёные.

- [ ] **Lint/type green** — `ruff check src/locales tests/services/test_locales.py && ruff format --check src/locales tests/services/test_locales.py && mypy --strict src/locales tests/services/test_locales.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/locales tests/services/test_locales.py && git commit -m "feat(locales): add ru/uz dictionaries and get_text registry"`

---

# Группа задач 5: src/services/pagination.py

Чистая пагинация: 1-based страница с clamp в `[1, total_pages]`, флаги `has_prev/has_next`. Импортируемый
символ: `paginate`. Зависит от `src.services.models` (`Page`). 100% покрытие.

---

### Task 5.1 — `paginate(items, page, page_size)`

**Files:**
- Create: `src/services/pagination.py`
- Test: `tests/services/test_pagination.py`

- [ ] **Write failing test** — `tests/services/test_pagination.py`:

```python
"""Тесты чистой пагинации: clamp, total_pages, флаги навигации."""
from __future__ import annotations

from src.services.pagination import paginate


def test_empty_yields_single_empty_page() -> None:
    page = paginate([], page=1, page_size=8)
    assert page.items == ()
    assert page.total_pages == 1
    assert page.page == 1
    assert page.has_prev is False
    assert page.has_next is False


def test_exact_one_page() -> None:
    page = paginate(list(range(8)), page=1, page_size=8)
    assert page.items == tuple(range(8))
    assert page.total_pages == 1
    assert page.has_next is False


def test_two_pages_first() -> None:
    page = paginate(list(range(9)), page=1, page_size=8)
    assert page.items == tuple(range(8))
    assert page.total_pages == 2
    assert page.has_prev is False
    assert page.has_next is True


def test_two_pages_second_partial() -> None:
    page = paginate(list(range(9)), page=2, page_size=8)
    assert page.items == (8,)
    assert page.page == 2
    assert page.has_prev is True
    assert page.has_next is False


def test_page_above_range_clamps_to_last() -> None:
    page = paginate(list(range(9)), page=99, page_size=8)
    assert page.page == 2
    assert page.items == (8,)


def test_page_below_one_clamps_to_first() -> None:
    page = paginate(list(range(9)), page=0, page_size=8)
    assert page.page == 1
    assert page.items == tuple(range(8))
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_pagination.py -q`
  Expected: `ImportError: cannot import name 'paginate' from 'src.services.pagination'`.

- [ ] **Minimal CORRECT impl** — `src/services/pagination.py`:

```python
"""Чистая пагинация: срез страницы + флаги навигации."""
from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from src.services.models import Page

T = TypeVar("T")


def paginate(items: Sequence[T], page: int, page_size: int) -> Page[T]:
    """Вернуть страницу 1-based. page клампится в [1, total_pages].

    Пустой items → одна пустая страница (total_pages=1). page_size >= 1 (контракт config).
    """
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    current = min(max(page, 1), total_pages)
    start = (current - 1) * page_size
    chunk = tuple(items[start : start + page_size])
    return Page(
        items=chunk,
        page=current,
        total_pages=total_pages,
        has_prev=current > 1,
        has_next=current < total_pages,
    )
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_pagination.py -q`
  Expected: зелёные.

- [ ] **Coverage 100% на модуле** — `python -m pytest tests/services/test_pagination.py --cov=src/services/pagination --cov-report=term-missing -q`
  Expected: 100%.

- [ ] **Lint/type green** — `ruff check src/services/pagination.py tests/services/test_pagination.py && ruff format --check src/services/pagination.py tests/services/test_pagination.py && mypy --strict src/services/pagination.py tests/services/test_pagination.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/pagination.py tests/services/test_pagination.py && git commit -m "feat(services): add pure paginate with page clamping"`

---

# Группа задач 6: tests/services/conftest.py + src/services/formatting.py

`conftest.py` — фабрика `Product` для тестов (DRY между formatting/index/search/catalog). `formatting.py`
— презентация: `format_price`, `localized_name`, `localized_desc`, `product_list_item`, `product_card`.
Зависит от `src.data.models` (`Product`), `src.locales` (`get_text`), `src.services.ids` (`group_id`),
`src.services.models`.

---

### Task 6.1 — `tests/services/conftest.py` фабрика `make_product`

**Files:**
- Create: `tests/services/conftest.py`
- Test: `tests/services/test_conftest_factory.py`

- [ ] **Write failing test** — `tests/services/test_conftest_factory.py`:

```python
"""Проверка тест-фабрики make_product (общая инфраструктура services-тестов)."""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from src.data.models import Product


def test_make_product_defaults(make_product: Callable[..., Product]) -> None:
    p = make_product()
    assert p.id == "p1"
    assert p.is_active is True
    assert p.currency == "UZS"


def test_make_product_overrides(make_product: Callable[..., Product]) -> None:
    p = make_product(id="x", price_retail=None, is_active=False)
    assert p.id == "x"
    assert p.price_retail is None
    assert p.is_active is False
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_conftest_factory.py -q`
  Expected: fixture `make_product` не найдена → `fixture 'make_product' not found`, тесты падают (errors).

- [ ] **Minimal CORRECT impl** — `tests/services/conftest.py`:

```python
"""Фикстуры services-тестов: фабрика Product с валидными дефолтами."""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

import pytest

from src.data.models import Product


@pytest.fixture
def make_product() -> Callable[..., Product]:
    """Фабрика Product: дефолты валидны, overrides переопределяют поля."""

    def _make(**overrides: object) -> Product:
        base: dict[str, object] = {
            "id": "p1",
            "category": "Напитки",
            "subcategory": "Соки",
            "name_ru": "Сок",
            "name_uz": "Sharbat",
            "desc_ru": None,
            "desc_uz": None,
            "price_wholesale": Decimal("100"),
            "price_retail": Decimal("120"),
            "currency": "UZS",
            "packaging": None,
            "photo": None,
            "is_active": True,
        }
        base.update(overrides)
        return Product(**base)  # type: ignore[arg-type]

    return _make
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_conftest_factory.py -q`
  Expected: зелёные.

- [ ] **Lint/type green** — `ruff check tests/services/conftest.py tests/services/test_conftest_factory.py && ruff format --check tests/services/conftest.py tests/services/test_conftest_factory.py && mypy --strict tests/services/conftest.py tests/services/test_conftest_factory.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add tests/services/conftest.py tests/services/test_conftest_factory.py && git commit -m "test(services): add make_product factory fixture"`

---

### Task 6.2 — `format_price` (мультивалюта, None, тысячи)

**Files:**
- Create: `src/services/formatting.py`
- Test: `tests/services/test_formatting.py`

- [ ] **Write failing test** — `tests/services/test_formatting.py`:

```python
"""Тесты презентации: формат цены, фолбэк desc/name, сборка и обрезка карточки."""
from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from src.data.models import Product
from src.services.formatting import format_price

NBSP = " "


def test_format_price_none_is_on_request() -> None:
    assert format_price(None, "UZS", "ru") == "цена по запросу"
    assert format_price(None, "UZS", "uz") == "narxi so'rov bo'yicha"


def test_format_price_groups_thousands_with_nbsp_and_symbol_after() -> None:
    assert format_price(Decimal("120000"), "UZS", "ru") == f"120{NBSP}000 сум"
    assert format_price(Decimal("120000"), "UZS", "uz") == f"120{NBSP}000 so'm"


def test_format_price_keeps_decimal_with_comma() -> None:
    assert format_price(Decimal("1200.50"), "UZS", "ru") == f"1{NBSP}200,50 сум"


def test_format_price_short_number_no_separator() -> None:
    assert format_price(Decimal("100"), "UZS", "ru") == "100 сум"


def test_format_price_unknown_currency_falls_back_to_code() -> None:
    assert format_price(Decimal("100"), "USD", "ru") == "100 USD"


def test_format_price_negative_groups_without_sign_in_thousands() -> None:
    """Отрицательная цена (parse_number принимает '-N'): знак вне группировки разрядов."""
    assert format_price(Decimal("-120000"), "UZS", "ru") == f"-120{NBSP}000 сум"
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_formatting.py -q`
  Expected: `ImportError: cannot import name 'format_price' from 'src.services.formatting'`.

- [ ] **Minimal CORRECT impl** — `src/services/formatting.py`:

```python
"""Презентация слоя services: формат цены, фолбэк desc/name, сборка карточки.

Зависит от locales (i18n) и data.Product, но НЕ от aiogram.
"""
from __future__ import annotations

from decimal import Decimal

from src.locales import get_text
from src.services.models import Lang

_THOUSANDS_SEP = " "  # неразрывный пробел


def _group_thousands(digits: str) -> str:
    """Сгруппировать целую часть по 3 справа неразрывным пробелом."""
    parts: list[str] = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    parts.insert(0, digits)
    return _THOUSANDS_SEP.join(parts)


def format_price(value: Decimal | None, currency: str, lang: Lang) -> str:
    """Локализованная цена: «12 000 сум». None → «цена по запросу».

    Число форматируется единообразно (пробел-тысячи, запятая-десятичная); символ
    валюты — переводимая строка (currency.<code>), неизвестная валюта → её код.
    """
    if value is None:
        return get_text("price_on_request", lang)
    symbol = get_text(f"currency.{currency}", lang, default=currency)
    text = format(value, "f")
    # Знак снимается ДО группировки тысяч, иначе "-" попадёт в разряд (−120000 → −1 120 000).
    # parse_number принимает отрицательные ("-5" → Decimal("-5")), поэтому ветка достижима.
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    integer_part, _, fractional = text.partition(".")
    grouped = _group_thousands(integer_part)
    rendered = f"{grouped},{fractional}" if fractional else grouped
    if negative:
        rendered = f"-{rendered}"
    return f"{rendered} {symbol}"
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_formatting.py -q`
  Expected: зелёные.

- [ ] **Lint/type green** — `ruff check src/services/formatting.py tests/services/test_formatting.py && ruff format --check src/services/formatting.py tests/services/test_formatting.py && mypy --strict src/services/formatting.py tests/services/test_formatting.py`
  Expected: без ошибок. Импорт минимален (`Decimal`, `get_text`, `Lang`) — символы `Product`/`group_id`/`ProductListItem`/`ProductCard` добавляются в импорт в подзадачах-потребителях 6.3/6.4, чтобы не держать неиспользуемые импорты (ruff F401).

- [ ] **Commit** — `git add src/services/formatting.py tests/services/test_formatting.py && git commit -m "feat(services): add localized price formatting"`

---

### Task 6.3 — `localized_name` / `localized_desc` / `product_list_item` (фолбэк языка)

**Files:**
- Modify: `src/services/formatting.py`
- Test: `tests/services/test_formatting.py`

- [ ] **Write failing test** — в `tests/services/test_formatting.py` дополнить верхний блок импортов (в шапке файла, без `# noqa`): к `from src.services.formatting import format_price` добавить `localized_desc, localized_name, product_list_item`, и добавить `from src.services.ids import group_id`. Затем добавить тела тестов:

```python
def test_localized_name_uses_current_lang(make_product: Callable[..., Product]) -> None:
    p = make_product(name_ru="Сок", name_uz="Sharbat")
    assert localized_name(p, "ru") == "Сок"
    assert localized_name(p, "uz") == "Sharbat"


def test_localized_name_falls_back_when_empty(make_product: Callable[..., Product]) -> None:
    """Дефенсивный фолбэк: пустое имя на языке → второй язык."""
    p = make_product(name_uz="")
    assert localized_name(p, "uz") == "Сок"  # name_ru


def test_localized_desc_falls_back_to_other_language(make_product: Callable[..., Product]) -> None:
    p = make_product(desc_ru="Описание", desc_uz=None)
    assert localized_desc(p, "uz") == "Описание"


def test_localized_desc_none_when_both_empty(make_product: Callable[..., Product]) -> None:
    p = make_product(desc_ru=None, desc_uz=None)
    assert localized_desc(p, "ru") is None


def test_product_list_item_id_and_title(make_product: Callable[..., Product]) -> None:
    p = make_product(id="abc", name_ru="Сок")
    item = product_list_item(p, "ru")
    assert item.id == group_id("abc")
    assert item.title == "Сок"
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_formatting.py -q`
  Expected: `ImportError: cannot import name 'localized_name' from 'src.services.formatting'`.

- [ ] **Minimal CORRECT impl** — добавить в `src/services/formatting.py` (и расширить импорт `Product`, `group_id`, `ProductListItem`):

```python
def localized_name(product: Product, lang: Lang) -> str:
    """Имя на выбранном языке; пустое → фолбэк на второй (data гарантирует непустые)."""
    primary = product.name_ru if lang == "ru" else product.name_uz
    secondary = product.name_uz if lang == "ru" else product.name_ru
    return primary or secondary


def localized_desc(product: Product, lang: Lang) -> str | None:
    """Описание на выбранном языке; пустое → фолбэк на второй; оба пусты → None."""
    primary = product.desc_ru if lang == "ru" else product.desc_uz
    secondary = product.desc_uz if lang == "ru" else product.desc_ru
    return primary or secondary or None


def product_list_item(product: Product, lang: Lang) -> ProductListItem:
    """Строка списка: хеш-id товара + локализованное имя."""
    return ProductListItem(id=group_id(product.id), title=localized_name(product, lang))
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_formatting.py -q`
  Expected: зелёные.

- [ ] **Lint/type green** — `ruff check src/services/formatting.py tests/services/test_formatting.py && ruff format --check src/services/formatting.py tests/services/test_formatting.py && mypy --strict src/services/formatting.py tests/services/test_formatting.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/formatting.py tests/services/test_formatting.py && git commit -m "feat(services): add localized name/desc fallback and list item builder"`

---

### Task 6.4 — `product_card` (сборка + обрезка caption по лимиту)

**Files:**
- Modify: `src/services/formatting.py`
- Test: `tests/services/test_formatting.py`

- [ ] **Write failing test** — в `tests/services/test_formatting.py` добавить `product_card` к верхнему импорту `from src.services.formatting import ...` (в шапке файла, без `# noqa`), затем добавить тела тестов:

```python
def test_product_card_assembles_name_desc_prices(make_product: Callable[..., Product]) -> None:
    p = make_product(name_ru="Сок", desc_ru="Яблочный", packaging="1 л")
    card = product_card(p, "ru")
    assert "Сок" in card.text
    assert "Яблочный" in card.text
    assert "Опт: 100 сум" in card.text
    assert "Розница: 120 сум" in card.text
    assert "Фасовка: 1 л" in card.text
    assert card.photo is None


def test_product_card_omits_packaging_when_absent(make_product: Callable[..., Product]) -> None:
    card = product_card(make_product(packaging=None), "ru")
    assert "Фасовка" not in card.text


def test_product_card_price_on_request(make_product: Callable[..., Product]) -> None:
    card = product_card(make_product(price_wholesale=None), "ru")
    assert "Опт: цена по запросу" in card.text


def test_product_card_truncates_desc_to_photo_limit(make_product: Callable[..., Product]) -> None:
    long_desc = "слово " * 400  # ~2400 символов
    p = make_product(desc_ru=long_desc, photo="http://example.com/a.jpg")
    card = product_card(p, "ru")
    assert card.photo == "http://example.com/a.jpg"
    assert len(card.text) <= 1024
    # структура: title \n\n desc \n\n tail; обрезается ТОЛЬКО desc (средний сегмент)
    segments = card.text.split("\n\n")
    assert segments[1].rstrip().endswith("…")
    # имя и цены не срезаны — присутствуют целиком после обрезанного описания
    assert segments[0] == "Сок"
    assert "Опт: 100 сум" in card.text


def test_product_card_without_photo_uses_text_limit(make_product: Callable[..., Product]) -> None:
    long_desc = "слово " * 400
    p = make_product(desc_ru=long_desc, photo=None)
    card = product_card(p, "ru")
    assert card.photo is None
    assert len(card.text) <= 4096
    assert "Опт: 100 сум" in card.text
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_formatting.py -q`
  Expected: `ImportError: cannot import name 'product_card' from 'src.services.formatting'`.

- [ ] **Minimal CORRECT impl** — добавить в `src/services/formatting.py` (и расширить импорт `ProductCard`):

```python
_CAPTION_LIMIT_WITH_PHOTO = 1024
_CAPTION_LIMIT_TEXT = 4096
_ELLIPSIS = "…"


def _truncate(text: str, budget: int) -> str:
    """Обрезать text под budget символов по границе слова + многоточие."""
    if budget <= 0:
        return ""
    if len(text) <= budget:
        return text
    hard = text[: budget - len(_ELLIPSIS)].rstrip()
    cut = hard.rsplit(" ", 1)[0] if " " in hard else hard
    return f"{cut}{_ELLIPSIS}"


def product_card(product: Product, lang: Lang) -> ProductCard:
    """Собрать карточку: имя + (фолбэк) описание + опт/розница + фасовка.

    Лимит caption = 1024 при наличии фото, иначе 4096 (лимит сообщения). При
    превышении обрезается ТОЛЬКО описание — имя и цены не режутся.
    Known limitation: вырожденный случай (само имя+цены > лимита) не клампится —
    имена коротки по контракту данных.
    """
    title = localized_name(product, lang)
    desc = localized_desc(product, lang)

    tail_lines = [
        f"{get_text('label_wholesale', lang)}: "
        f"{format_price(product.price_wholesale, product.currency, lang)}",
        f"{get_text('label_retail', lang)}: "
        f"{format_price(product.price_retail, product.currency, lang)}",
    ]
    if product.packaging:
        tail_lines.append(f"{get_text('label_packaging', lang)}: {product.packaging}")
    tail = "\n".join(tail_lines)

    limit = _CAPTION_LIMIT_WITH_PHOTO if product.photo else _CAPTION_LIMIT_TEXT
    if not desc:
        text = f"{title}\n\n{tail}"
    else:
        # фиксированная часть = title + 4 перевода строки + tail; остаток — под desc
        fixed_len = len(title) + 4 + len(tail)
        desc = _truncate(desc, limit - fixed_len)
        text = f"{title}\n\n{desc}\n\n{tail}"
    return ProductCard(text=text, photo=product.photo)
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_formatting.py -q`
  Expected: все тесты файла зелёные.

- [ ] **Lint/type green** — `ruff check src/services/formatting.py tests/services/test_formatting.py && ruff format --check src/services/formatting.py tests/services/test_formatting.py && mypy --strict src/services/formatting.py tests/services/test_formatting.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/formatting.py tests/services/test_formatting.py && git commit -m "feat(services): add product card assembly with caption truncation"`

---

# Группа задач 7: src/services/index.py

Двухуровневый навигационный индекс над иммутабельным `Catalog`: активные товары, сгруппированные
категория→подкатегория, обратные карты `id→группа`. Импортируемый символ: `CatalogIndex`. Зависит от
`src.data.models` (`Catalog`, `Product`), `src.services.ids` (`group_id`), `src.services.models`.

---

### Task 7.1 — `CatalogIndex.build` + методы поиска групп

**Files:**
- Create: `src/services/index.py`
- Test: `tests/services/test_index.py`

- [ ] **Write failing test** — `tests/services/test_index.py`:

```python
"""Тесты двухуровневого индекса: сборка, active-only, порядок, обратные карты."""
from __future__ import annotations

import logging
from collections.abc import Callable

import pytest

from src.data.models import Catalog, Product
from src.services.ids import group_id
from src.services.index import CatalogIndex


def _catalog(products: list[Product]) -> Catalog:
    return Catalog.build(products)


def test_build_none_catalog_is_empty() -> None:
    index = CatalogIndex.build(None)
    assert index.categories == ()
    assert index.active_products == ()


def test_categories_in_table_order(make_product: Callable[..., Product]) -> None:
    products = [
        make_product(id="1", category="Напитки", subcategory="Соки"),
        make_product(id="2", category="Еда", subcategory="Хлеб"),
    ]
    index = CatalogIndex.build(_catalog(products))
    assert [c.title for c in index.categories] == ["Напитки", "Еда"]
    assert index.categories[0].id == group_id("Напитки")


def test_inactive_products_excluded(make_product: Callable[..., Product]) -> None:
    products = [
        make_product(id="1", category="Напитки", subcategory="Соки", is_active=True),
        make_product(id="2", category="Еда", subcategory="Хлеб", is_active=False),
    ]
    index = CatalogIndex.build(_catalog(products))
    assert [c.title for c in index.categories] == ["Напитки"]
    assert len(index.active_products) == 1


def test_category_with_only_inactive_is_absent(make_product: Callable[..., Product]) -> None:
    products = [make_product(id="1", category="Скрытая", subcategory="X", is_active=False)]
    index = CatalogIndex.build(_catalog(products))
    assert index.categories == ()


def test_subcategories_lookup(make_product: Callable[..., Product]) -> None:
    products = [
        make_product(id="1", category="Напитки", subcategory="Соки"),
        make_product(id="2", category="Напитки", subcategory="Воды"),
    ]
    index = CatalogIndex.build(_catalog(products))
    cat_id = group_id("Напитки")
    subs = index.subcategories(cat_id)
    assert subs is not None
    assert [s.title for s in subs] == ["Соки", "Воды"]
    assert subs[0].id == group_id("Напитки", "Соки")


def test_subcategories_unknown_id_returns_none() -> None:
    index = CatalogIndex.build(None)
    assert index.subcategories("deadbeefdead") is None


def test_same_subcategory_name_in_two_categories_not_merged(
    make_product: Callable[..., Product],
) -> None:
    products = [
        make_product(id="1", category="Напитки", subcategory="Прочее"),
        make_product(id="2", category="Еда", subcategory="Прочее"),
    ]
    index = CatalogIndex.build(_catalog(products))
    sid_a = group_id("Напитки", "Прочее")
    sid_b = group_id("Еда", "Прочее")
    assert sid_a != sid_b
    pa = index.products(sid_a)
    pb = index.products(sid_b)
    assert pa is not None and pb is not None
    assert pa[0].id == "1"
    assert pb[0].id == "2"


def test_products_in_table_order(make_product: Callable[..., Product]) -> None:
    products = [
        make_product(id="1", category="Напитки", subcategory="Соки"),
        make_product(id="2", category="Напитки", subcategory="Соки"),
    ]
    index = CatalogIndex.build(_catalog(products))
    sid = group_id("Напитки", "Соки")
    prods = index.products(sid)
    assert prods is not None
    assert [p.id for p in prods] == ["1", "2"]


def test_product_lookup_by_hashed_id(make_product: Callable[..., Product]) -> None:
    products = [make_product(id="abc", category="Напитки", subcategory="Соки")]
    index = CatalogIndex.build(_catalog(products))
    found = index.product(group_id("abc"))
    assert found is not None
    assert found.id == "abc"
    assert index.product("missingidxxx") is None


def test_single_other_subcategory_navigates(make_product: Callable[..., Product]) -> None:
    """Единственная группа «Прочее»: обычная двухуровневая навигация, без авто-схлопывания."""
    products = [make_product(id="1", category="Напитки", subcategory="Прочее", name_ru="Сок")]
    index = CatalogIndex.build(_catalog(products))
    assert len(index.categories) == 1
    subs = index.subcategories(group_id("Напитки"))
    assert subs is not None
    assert [s.title for s in subs] == ["Прочее"]
    prods = index.products(group_id("Напитки", "Прочее"))
    assert prods is not None
    assert len(prods) == 1


def test_hash_collision_keeps_first_and_logs_error(
    make_product: Callable[..., Product],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Коллизия хеша (разные имена → один id) логируется error, первый wins (known limitation)."""
    monkeypatch.setattr("src.services.index.group_id", lambda *parts: "collide12hash")
    products = [
        make_product(id="1", category="Напитки", subcategory="Соки"),
        make_product(id="2", category="Еда", subcategory="Хлеб"),
    ]
    with caplog.at_level(logging.ERROR):
        index = CatalogIndex.build(_catalog(products))
    assert any("collision" in record.message for record in caplog.records)
    # первый wins: единственная категория несёт title первого товара
    assert [c.title for c in index.categories] == ["Напитки"]
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_index.py -q`
  Expected: `ImportError: cannot import name 'CatalogIndex' from 'src.services.index'`.

- [ ] **Minimal CORRECT impl** — `src/services/index.py`:

```python
"""Двухуровневый навигационный индекс над иммутабельным Catalog.

Строится из плоского Catalog один раз на снимок. В индекс попадают только
активные товары; порядок — по первому появлению в строках (insertion order).
Category/Subcategory — навигационные view, в data-моделях их НЕТ.
"""
from __future__ import annotations

import logging

from src.data.models import Catalog, Product
from src.services.ids import group_id
from src.services.models import CategoryItem, SubcategoryItem

_log = logging.getLogger(__name__)


def _register(mapping: dict[str, str], key: str, title: str) -> None:
    """Запомнить title по key; коллизия хеша (разные имена → один id) → error-лог."""
    existing = mapping.get(key)
    if existing is None:
        mapping[key] = title
    elif existing != title:
        _log.error("group id hash collision: %r vs %r -> %s", existing, title, key)


class CatalogIndex:
    """Активные товары, сгруппированные категория→подкатегория, + обратные карты id→группа."""

    __slots__ = (
        "categories",
        "active_products",
        "_subcats_by_cat",
        "_products_by_sub",
        "_product_by_id",
    )

    def __init__(
        self,
        categories: tuple[CategoryItem, ...],
        active_products: tuple[Product, ...],
        subcats_by_cat: dict[str, tuple[SubcategoryItem, ...]],
        products_by_sub: dict[str, tuple[Product, ...]],
        product_by_id: dict[str, Product],
    ) -> None:
        self.categories = categories
        self.active_products = active_products
        self._subcats_by_cat = subcats_by_cat
        self._products_by_sub = products_by_sub
        self._product_by_id = product_by_id

    @classmethod
    def build(cls, catalog: Catalog | None) -> CatalogIndex:
        """Собрать индекс из Catalog. None или 0 активных → пустой индекс."""
        products = catalog.products if catalog is not None else ()
        cat_titles: dict[str, str] = {}
        sub_titles: dict[str, dict[str, str]] = {}
        prods_by_sub: dict[str, list[Product]] = {}
        product_by_id: dict[str, Product] = {}
        active: list[Product] = []

        for product in products:
            if not product.is_active:
                continue
            active.append(product)
            cat_id = group_id(product.category)
            sub_id = group_id(product.category, product.subcategory)
            prod_id = group_id(product.id)

            _register(cat_titles, cat_id, product.category)
            _register(sub_titles.setdefault(cat_id, {}), sub_id, product.subcategory)
            prods_by_sub.setdefault(sub_id, []).append(product)

            existing = product_by_id.get(prod_id)
            if existing is None:
                product_by_id[prod_id] = product
            elif existing.id != product.id:
                _log.error("product id hash collision: %r vs %r", existing.id, product.id)

        categories = tuple(CategoryItem(id=cid, title=title) for cid, title in cat_titles.items())
        subcats_by_cat = {
            cid: tuple(SubcategoryItem(id=sid, title=title) for sid, title in subs.items())
            for cid, subs in sub_titles.items()
        }
        products_by_sub = {sid: tuple(items) for sid, items in prods_by_sub.items()}
        return cls(categories, tuple(active), subcats_by_cat, products_by_sub, product_by_id)

    def subcategories(self, cat_id: str) -> tuple[SubcategoryItem, ...] | None:
        """Подкатегории категории; None — неизвестный (протухший) cat_id."""
        return self._subcats_by_cat.get(cat_id)

    def products(self, sub_id: str) -> tuple[Product, ...] | None:
        """Активные товары подкатегории; None — неизвестный (протухший) sub_id."""
        return self._products_by_sub.get(sub_id)

    def product(self, prod_id: str) -> Product | None:
        """Товар по хеш-id; None — неизвестный (протухший) prod_id."""
        return self._product_by_id.get(prod_id)
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_index.py -q`
  Expected: зелёные.

- [ ] **Lint/type green** — `ruff check src/services/index.py tests/services/test_index.py && ruff format --check src/services/index.py tests/services/test_index.py && mypy --strict src/services/index.py tests/services/test_index.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/index.py tests/services/test_index.py && git commit -m "feat(services): add two-level CatalogIndex over flat catalog"`

---

# Группа задач 8: src/services/search.py

Чистый подстрочный поиск по нормализованному `name_{lang}` среди активных товаров, с пагинацией.
Импортируемый символ: `search`. Зависит от `src.services.index` (`CatalogIndex`), `src.services.normalize`,
`src.services.formatting` (`localized_name`, `product_list_item`), `src.services.pagination`,
`src.services.models`.

---

### Task 8.1 — `search(index, query, lang, page, page_size)`

**Files:**
- Create: `src/services/search.py`
- Test: `tests/services/test_search.py`

- [ ] **Write failing test** — `tests/services/test_search.py`:

```python
"""Тесты поиска: подстрока, нормализация, кросс-скрипт, активные, пагинация, пусто."""
from __future__ import annotations

from collections.abc import Callable

from src.data.models import Catalog, Product
from src.services.index import CatalogIndex
from src.services.search import search


def _index(products: list[Product]) -> CatalogIndex:
    return CatalogIndex.build(Catalog.build(products))


def test_substring_match_current_lang(make_product: Callable[..., Product]) -> None:
    index = _index([
        make_product(id="1", name_ru="Сок яблочный"),
        make_product(id="2", name_ru="Вода"),
    ])
    page = search(index, "яблоч", "ru", page=1, page_size=8)
    assert [i.title for i in page.items] == ["Сок яблочный"]


def test_search_is_case_insensitive(make_product: Callable[..., Product]) -> None:
    index = _index([make_product(id="1", name_ru="Сок Яблочный")])
    page = search(index, "ЯБЛОЧ", "ru", page=1, page_size=8)
    assert len(page.items) == 1


def test_uz_cross_script_finds_latin_name(make_product: Callable[..., Product]) -> None:
    """Запрос кириллицей находит товар с name_uz на латинице (и наоборот)."""
    index = _index([make_product(id="1", name_uz="olma sharbati", name_ru="Сок")])
    page = search(index, "олма", "uz", page=1, page_size=8)
    assert len(page.items) == 1


def test_only_active_products_searched(make_product: Callable[..., Product]) -> None:
    index = _index([
        make_product(id="1", name_ru="Сок", is_active=False),
    ])
    page = search(index, "сок", "ru", page=1, page_size=8)
    assert page.items == ()


def test_empty_query_yields_empty_page(make_product: Callable[..., Product]) -> None:
    index = _index([make_product(id="1", name_ru="Сок")])
    page = search(index, "   ", "ru", page=1, page_size=8)
    assert page.items == ()


def test_no_match_yields_empty_page(make_product: Callable[..., Product]) -> None:
    index = _index([make_product(id="1", name_ru="Сок")])
    page = search(index, "телефон", "ru", page=1, page_size=8)
    assert page.items == ()
    assert page.total_pages == 1


def test_search_paginates(make_product: Callable[..., Product]) -> None:
    products = [make_product(id=str(n), name_ru=f"Сок {n}") for n in range(9)]
    index = _index(products)
    page = search(index, "сок", "ru", page=2, page_size=8)
    assert len(page.items) == 1
    assert page.page == 2
    assert page.has_prev is True
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_search.py -q`
  Expected: `ImportError: cannot import name 'search' from 'src.services.search'`.

- [ ] **Minimal CORRECT impl** — `src/services/search.py`:

```python
"""Подстрочный поиск по нормализованному name_{lang} среди активных товаров."""
from __future__ import annotations

from src.services.formatting import localized_name, product_list_item
from src.services.index import CatalogIndex
from src.services.models import Lang, Page, ProductListItem
from src.services.normalize import normalize
from src.services.pagination import paginate


def search(
    index: CatalogIndex, query: str, lang: Lang, page: int, page_size: int
) -> Page[ProductListItem]:
    """Найти активные товары, чьё нормализованное name_{lang} содержит запрос.

    Пустой/пробельный запрос (после нормализации) → пустая страница. Поиск по
    всему каталогу; кросс-скрипт обеспечен нормализацией обеих сторон.
    """
    needle = normalize(query, lang)
    if not needle:
        return paginate((), page, page_size)
    matched = [
        product
        for product in index.active_products
        if needle in normalize(localized_name(product, lang), lang)
    ]
    items = [product_list_item(product, lang) for product in matched]
    return paginate(items, page, page_size)
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_search.py -q`
  Expected: зелёные.

- [ ] **Lint/type green** — `ruff check src/services/search.py tests/services/test_search.py && ruff format --check src/services/search.py tests/services/test_search.py && mypy --strict src/services/search.py tests/services/test_search.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/search.py tests/services/test_search.py && git commit -m "feat(services): add substring search over active products"`

---

# Группа задач 9: src/services/catalog.py (фасад)

Cache-aware фасад: читает снимок 1×/запрос, мемоизирует `CatalogIndex` по идентичности снимка, заворачивает
исход в `Ok | Stale`. Импортируемый символ: `CatalogService`. Зависит от `src.config` (`Settings`),
`src.data.cache` (`CatalogCache`), `src.data.models` (`Snapshot`), и модулей `services`
(`index`, `formatting`, `search`, `pagination`, `models`).

Тесты — async (pytest-asyncio strict): кэш наполняется через `await cache.try_swap(parse_result)`.

---

### Task 9.1 — `CatalogService`: `categories` + мемоизация индекса

**Files:**
- Create: `src/services/catalog.py`
- Test: `tests/services/test_catalog_service.py`

- [ ] **Write failing test** — `tests/services/test_catalog_service.py`:

```python
"""Тесты фасада CatalogService: cold-start, мемоизация, Stale, валидный поток."""
from __future__ import annotations

from collections.abc import Callable

import pytest

from src.data.cache import CatalogCache
from src.data.models import Catalog, ParseResult, Product
from src.services import catalog as catalog_module
from src.services.catalog import CatalogService


class _Settings:
    """Минимальный стенд Settings: фасаду нужен лишь PAGE_SIZE."""

    PAGE_SIZE = 8


def _service(cache: CatalogCache) -> CatalogService:
    return CatalogService(cache, _Settings())  # type: ignore[arg-type]


def _result(products: list[Product]) -> ParseResult:
    catalog = Catalog.build(products)
    return ParseResult(catalog=catalog, issues=(), valid_rows=len(products), skipped_rows=0)


@pytest.mark.asyncio
async def test_cold_start_categories_empty() -> None:
    """catalog=None (cold-start) → categories() пуст (UX «обновляется»)."""
    service = _service(CatalogCache())
    assert service.categories() == ()


@pytest.mark.asyncio
async def test_categories_after_swap(make_product: Callable[..., Product]) -> None:
    cache = CatalogCache()
    await cache.try_swap(_result([make_product(id="1", category="Напитки", subcategory="Соки")]))
    service = _service(cache)
    titles = [c.title for c in service.categories()]
    assert titles == ["Напитки"]


@pytest.mark.asyncio
async def test_index_built_once_per_snapshot(
    monkeypatch: pytest.MonkeyPatch, make_product: Callable[..., Product]
) -> None:
    """Повторные вызовы на одном снимке строят индекс один раз (мемоизация)."""
    cache = CatalogCache()
    await cache.try_swap(_result([make_product(id="1")]))
    service = _service(cache)

    calls = {"n": 0}
    original_build = catalog_module.CatalogIndex.build

    def _counting_build(catalog: object) -> object:
        calls["n"] += 1
        return original_build(catalog)  # type: ignore[arg-type]

    monkeypatch.setattr(catalog_module.CatalogIndex, "build", staticmethod(_counting_build))
    service.categories()
    service.categories()
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_index_rebuilt_after_snapshot_swap(
    monkeypatch: pytest.MonkeyPatch, make_product: Callable[..., Product]
) -> None:
    cache = CatalogCache()
    await cache.try_swap(_result([make_product(id="1", category="A", subcategory="X")]))
    service = _service(cache)
    assert [c.title for c in service.categories()] == ["A"]
    await cache.try_swap(_result([make_product(id="2", category="B", subcategory="Y")]))
    assert [c.title for c in service.categories()] == ["B"]
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_catalog_service.py -q`
  Expected: `ImportError: cannot import name 'CatalogService' from 'src.services.catalog'`.

- [ ] **Minimal CORRECT impl** — `src/services/catalog.py`:

```python
"""Cache-aware фасад слоя services: единственный мост бот↔кэш.

Читает снимок ровно один раз на публичный вызов (консистентность в пределах
клика), мемоизирует CatalogIndex по идентичности снимка, заворачивает исход
запросов по id в Ok | Stale. Не импортирует aiogram, не ходит в gspread/data
напрямую (только CatalogCache.get_snapshot()).
"""
from __future__ import annotations

from src.config import Settings
from src.data.cache import CatalogCache
from src.data.models import Snapshot
from src.services.index import CatalogIndex
from src.services.models import CategoryItem


class CatalogService:
    """Навигация/поиск/карточка поверх кэша каталога."""

    def __init__(self, cache: CatalogCache, settings: Settings) -> None:
        self._cache = cache
        self._page_size = settings.PAGE_SIZE
        self._cached_snapshot: Snapshot | None = None
        self._cached_index: CatalogIndex | None = None

    def _index(self) -> CatalogIndex:
        """Индекс текущего снимка; строится один раз на снимок (мемоизация по identity).

        Ранний возврат локальной переменной в ветке пересборки — иначе mypy не сузит
        атрибут _cached_index до non-None.
        """
        snapshot = self._cache.get_snapshot()
        if snapshot is not self._cached_snapshot or self._cached_index is None:
            index = CatalogIndex.build(snapshot.catalog)
            self._cached_index = index
            self._cached_snapshot = snapshot
            return index
        return self._cached_index

    def categories(self) -> tuple[CategoryItem, ...]:
        """Категории меню. Пусто → cold-start/деградация (UX «каталог обновляется»)."""
        return self._index().categories
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_catalog_service.py -q`
  Expected: зелёные.

- [ ] **Lint/type green** — `ruff check src/services/catalog.py tests/services/test_catalog_service.py && ruff format --check src/services/catalog.py tests/services/test_catalog_service.py && mypy --strict src/services/catalog.py tests/services/test_catalog_service.py`
  Expected: без ошибок. Импорт минимален (`Settings`, `CatalogCache`, `Snapshot`, `CatalogIndex`, `CategoryItem`). Символы для методов 9.2–9.4 (`Lang`, `Ok`, `Stale`, `Page`, `SubcategoryItem`, `ProductListItem`, `ProductCard`, `product_list_item`, `product_card`, `paginate`, `search`) добавляются в импорт в соответствующих подзадачах.

- [ ] **Commit** — `git add src/services/catalog.py tests/services/test_catalog_service.py && git commit -m "feat(services): add CatalogService facade with snapshot-memoized index"`

---

### Task 9.2 — `subcategories` + `product_page` (Ok | Stale)

**Files:**
- Modify: `src/services/catalog.py`
- Test: `tests/services/test_catalog_service.py`

- [ ] **Write failing test** — в `tests/services/test_catalog_service.py` добавить в шапку файла (без `# noqa`): `from src.services.ids import group_id` и `from src.services.models import Ok, Stale`. Затем добавить тела тестов:

```python
@pytest.mark.asyncio
async def test_subcategories_ok(make_product: Callable[..., Product]) -> None:
    cache = CatalogCache()
    await cache.try_swap(_result([make_product(id="1", category="Напитки", subcategory="Соки")]))
    service = _service(cache)
    result = service.subcategories(group_id("Напитки"))
    assert isinstance(result, Ok)
    assert [s.title for s in result.value] == ["Соки"]


@pytest.mark.asyncio
async def test_subcategories_unknown_is_stale() -> None:
    service = _service(CatalogCache())
    assert isinstance(service.subcategories("deadbeefdead"), Stale)


@pytest.mark.asyncio
async def test_product_page_ok(make_product: Callable[..., Product]) -> None:
    cache = CatalogCache()
    await cache.try_swap(_result([
        make_product(id="1", category="Напитки", subcategory="Соки", name_ru="Сок"),
    ]))
    service = _service(cache)
    result = service.product_page(group_id("Напитки", "Соки"), 1, "ru")
    assert isinstance(result, Ok)
    assert [i.title for i in result.value.items] == ["Сок"]
    assert result.value.items[0].id == group_id("1")


@pytest.mark.asyncio
async def test_product_page_unknown_is_stale() -> None:
    service = _service(CatalogCache())
    assert isinstance(service.product_page("missingsubxx", 1, "ru"), Stale)
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_catalog_service.py -q`
  Expected: `AttributeError: 'CatalogService' object has no attribute 'subcategories'` (метод ещё не реализован — честный Red).

- [ ] **Minimal CORRECT impl** — добавить методы в класс `CatalogService`. Расширить импорты в шапке `catalog.py`: к `from src.services.models import CategoryItem` добавить `Lang, Ok, Page, ProductListItem, Stale, SubcategoryItem`; добавить `from src.services.formatting import product_list_item` и `from src.services.pagination import paginate`:

```python
    def subcategories(self, cat_id: str) -> Ok[tuple[SubcategoryItem, ...]] | Stale:
        """Подкатегории категории. Неизвестный cat_id → Stale (протух)."""
        subs = self._index().subcategories(cat_id)
        return Stale() if subs is None else Ok(subs)

    def product_page(
        self, sub_id: str, page: int, lang: Lang
    ) -> Ok[Page[ProductListItem]] | Stale:
        """Страница товаров подкатегории. Неизвестный sub_id → Stale; page клампится."""
        products = self._index().products(sub_id)
        if products is None:
            return Stale()
        items = [product_list_item(product, lang) for product in products]
        return Ok(paginate(items, page, self._page_size))
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_catalog_service.py -q`
  Expected: зелёные.

- [ ] **Lint/type green** — `ruff check src/services/catalog.py tests/services/test_catalog_service.py && ruff format --check src/services/catalog.py tests/services/test_catalog_service.py && mypy --strict src/services/catalog.py tests/services/test_catalog_service.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/catalog.py tests/services/test_catalog_service.py && git commit -m "feat(services): add subcategories and product_page with stale handling"`

---

### Task 9.3 — `product_card` (Ok | Stale)

**Files:**
- Modify: `src/services/catalog.py`
- Test: `tests/services/test_catalog_service.py`

- [ ] **Write failing test** — в `tests/services/test_catalog_service.py` добавить `ProductCard` к импорту `from src.services.models import Ok, Stale` в шапке файла (без `# noqa`), затем добавить тела тестов:

```python
@pytest.mark.asyncio
async def test_product_card_ok(make_product: Callable[..., Product]) -> None:
    cache = CatalogCache()
    await cache.try_swap(_result([make_product(id="1", name_ru="Сок")]))
    service = _service(cache)
    result = service.product_card(group_id("1"), "ru")
    assert isinstance(result, Ok)
    assert isinstance(result.value, ProductCard)
    assert "Сок" in result.value.text


@pytest.mark.asyncio
async def test_product_card_unknown_is_stale() -> None:
    service = _service(CatalogCache())
    assert isinstance(service.product_card("missingprodx", "ru"), Stale)
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_catalog_service.py -q`
  Expected: `AttributeError: 'CatalogService' object has no attribute 'product_card'`.

- [ ] **Minimal CORRECT impl** — добавить метод в `CatalogService`. Расширить импорты: добавить `ProductCard` к `from src.services.models import ...` и `product_card` к `from src.services.formatting import ...`:

```python
    def product_card(self, prod_id: str, lang: Lang) -> Ok[ProductCard] | Stale:
        """Карточка товара по хеш-id. Неизвестный prod_id → Stale (протух)."""
        product = self._index().product(prod_id)
        return Stale() if product is None else Ok(product_card(product, lang))
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_catalog_service.py -q`
  Expected: зелёные.

- [ ] **Lint/type green** — `ruff check src/services/catalog.py tests/services/test_catalog_service.py && ruff format --check src/services/catalog.py tests/services/test_catalog_service.py && mypy --strict src/services/catalog.py tests/services/test_catalog_service.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/catalog.py tests/services/test_catalog_service.py && git commit -m "feat(services): add product_card with stale handling"`

---

### Task 9.4 — `search` (делегирование чистому поиску)

**Files:**
- Modify: `src/services/catalog.py`
- Test: `tests/services/test_catalog_service.py`

- [ ] **Write failing test** — добавить в `tests/services/test_catalog_service.py`:

```python
@pytest.mark.asyncio
async def test_search_returns_page(make_product: Callable[..., Product]) -> None:
    cache = CatalogCache()
    await cache.try_swap(_result([
        make_product(id="1", name_ru="Сок яблочный"),
        make_product(id="2", name_ru="Вода"),
    ]))
    service = _service(cache)
    page = service.search("яблоч", "ru", 1)
    assert [i.title for i in page.items] == ["Сок яблочный"]


@pytest.mark.asyncio
async def test_search_empty_on_cold_start() -> None:
    service = _service(CatalogCache())
    page = service.search("сок", "ru", 1)
    assert page.items == ()
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_catalog_service.py -q`
  Expected: `AttributeError: 'CatalogService' object has no attribute 'search'`.

- [ ] **Minimal CORRECT impl** — добавить метод в `CatalogService`. Расширить импорты: добавить `from src.services.search import search` (имя `search` не конфликтует — метод класса и функция модуля в разных пространствах):

```python
    def search(self, query: str, lang: Lang, page: int) -> Page[ProductListItem]:
        """Подстрочный поиск по активным товарам. Без id → без Stale; пусто → пустой Page."""
        return search(self._index(), query, lang, page, self._page_size)
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_catalog_service.py -q`
  Expected: все тесты файла зелёные.

- [ ] **Lint/type green** — `ruff check src/services/catalog.py tests/services/test_catalog_service.py && ruff format --check src/services/catalog.py tests/services/test_catalog_service.py && mypy --strict src/services/catalog.py tests/services/test_catalog_service.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/catalog.py tests/services/test_catalog_service.py && git commit -m "feat(services): add search delegation on facade"`

- [ ] **ADR** — создать `docs/adr/0012-services-view-boundary.md` (Nygard, Статус `Accepted`). Решение: `services` отдаёт презентационно-готовые view-модели + `ViewResult(Ok/Stale)`, `bot` тонкий; чистое ядро над `Catalog` + cache-aware фасад (снимок 1×/запрос, мемо по identity). Альтернатива (отвергнута): отдавать сырые `Product`, форматировать в `bot`. Коммит: `git add docs/adr/0012-services-view-boundary.md && git commit -m "docs(adr): record services view-model boundary"`

---

# Группа задач 10: src/services/language.py

Per-user язык интерфейса, in-memory (сбрасывается при рестарте — ДОПУЩЕНИЕ, persist отложен). Отдельно от FSM,
чтобы сброс состояния поиска не стирал выбранный язык. Импортируемый символ: `LanguageStore`. Зависит от
`src.services.models` (`Lang`).

---

### Task 10.1 — `LanguageStore`

**Files:**
- Create: `src/services/language.py`
- Test: `tests/services/test_language.py`

- [ ] **Write failing test** — `tests/services/test_language.py`:

```python
"""Тесты per-user хранилища языка (in-memory)."""
from __future__ import annotations

from src.services.language import LanguageStore


def test_unknown_user_returns_none() -> None:
    store = LanguageStore()
    assert store.get(42) is None


def test_set_then_get() -> None:
    store = LanguageStore()
    store.set(42, "uz")
    assert store.get(42) == "uz"


def test_set_overwrites() -> None:
    store = LanguageStore()
    store.set(42, "ru")
    store.set(42, "uz")
    assert store.get(42) == "uz"


def test_users_are_independent() -> None:
    store = LanguageStore()
    store.set(1, "ru")
    store.set(2, "uz")
    assert store.get(1) == "ru"
    assert store.get(2) == "uz"
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/services/test_language.py -q`
  Expected: `ImportError: cannot import name 'LanguageStore' from 'src.services.language'`.

- [ ] **Minimal CORRECT impl** — `src/services/language.py`:

```python
"""Per-user язык интерфейса, in-memory.

ДОПУЩЕНИЕ: при рестарте процесса сбрасывается (persist в SQLite/Redis отложен, см. §11 дизайна).
Отдельно от FSM — сброс состояния поиска не стирает выбранный язык.
"""
from __future__ import annotations

from src.services.models import Lang


class LanguageStore:
    """Хранилище выбранного языка по user_id (None — язык ещё не выбран)."""

    def __init__(self) -> None:
        self._lang: dict[int, Lang] = {}

    def get(self, user_id: int) -> Lang | None:
        """Язык пользователя или None, если ещё не выбран (нужен экран выбора)."""
        return self._lang.get(user_id)

    def set(self, user_id: int, lang: Lang) -> None:
        """Запомнить выбранный язык пользователя."""
        self._lang[user_id] = lang
```

- [ ] **Run & verify PASS** — `python -m pytest tests/services/test_language.py -q`
  Expected: зелёные.

- [ ] **Lint/type green** — `ruff check src/services/language.py tests/services/test_language.py && ruff format --check src/services/language.py tests/services/test_language.py && mypy --strict src/services/language.py tests/services/test_language.py`
  Expected: без ошибок.

- [ ] **Commit** — `git add src/services/language.py tests/services/test_language.py && git commit -m "feat(services): add in-memory per-user language store"`

---

# Финальный гейт слоя `services`

### Прогон единого гейта на всём дереве

**Files:** (изменений нет — проверка)

- [ ] **Run & verify PASS** — единый гейт §10 SPEC на всём проекте:
  ```
  python -m ruff check E:\ADEL
  python -m ruff format --check E:\ADEL
  python -m mypy --strict E:\ADEL\src
  python -m pytest E:\ADEL --cov=src/services --cov-report=term-missing
  ```
  Expected: ruff `All checks passed!`; ruff format без изменений; mypy `Success`; pytest все зелёные,
  `normalize.py`/`ids.py`/`pagination.py` — 100%, остальные модули `services` — высокое покрытие, без
  непокрытых веток исходного потока.

- [ ] **Final verify** — рабочее дерево чистое:
  ```
  git -C E:\ADEL status --porcelain
  ```
  Expected: пустой вывод (всё закоммичено).

---

# ADR (Nygard, `docs/adr/`, по ходу реализации)

Завести при реализации соответствующих модулей (не задним числом):

- `docs/adr/0006-callback-id-strategy.md` — blake2s 12-hex для категории/подкатегории/товара; подкатегория
  от пары `(category, subcategory)`; протухание через `ViewResult.Stale`. Создать в группе 3 (ids).
- `docs/adr/0007-uz-normalization-table.md` — канон-латиница, явная таблица кириллица↔латиница, апострофы.
  Создать в группе 2 (normalize).
- `docs/adr/0012-services-view-boundary.md` — view-модели с готовыми строками + `ViewResult`; `bot` тонкий;
  чистое ядро + cache-aware фасад. Создать в группе 9 (catalog).

Каждый ADR — отдельный коммит `docs(adr): ...`, формат Nygard (Статус/Контекст/Решение/Последствия/Альтернативы).
