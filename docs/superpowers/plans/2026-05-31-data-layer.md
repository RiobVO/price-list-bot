# План реализации: слой `data`

> **Для агентов-исполнителей:** ОБЯЗАТЕЛЬНЫЙ СУБ-СКИЛЛ — superpowers:subagent-driven-development
> (рекомендуется) или superpowers:executing-plans. Шаги используют чекбоксы `- [ ]`.

**Goal:** Построить чистое, полностью протестированное ядро слоя `data` — каркас бота (BRIEF §0):
модели, толерантный парсинг строк Google Sheets, атомарный TTL-кэш и фоновый refresh. Без сети в тестах.

**Architecture:** `fetch` (грязный gspread I/O, всё → str) → `parse` (чистая функция строки→Catalog,
бросает SchemaError) → `cache` (атомарная замена снимка под Lock, порог отказа) → `refresh` (фоновая
asyncio-задача, cold-start backoff, fail-fast на конфиг-ошибках). `config` — pydantic-settings.
Границы: `data` не знает про aiogram; `parse` не знает про сеть/env.

**Tech Stack:** Python 3.11+, pydantic-settings, gspread, pytest + pytest-asyncio (strict), ruff, mypy --strict.

**Источники:** дизайн — `docs/superpowers/specs/2026-05-31-price-list-bot-design.md`; инварианты — `CLAUDE.md`.
Первый план из серии: **data** → services → bot → infra.

## Порядок и зависимости

Реализовывать строго по порядку (каждый модуль предполагает предыдущие готовы):

`Task 0 scaffold → models → coerce → fetch → config → parse → cache → refresh`

## Правки ревью (применить при исполнении)

План прошёл двойное adversarial-ревью (согласованность типов + полнота/TDD), оба вердикта — APPROVED.
Три НЕ-блокирующих правки — применить по ходу:

1. **`cache.try_swap`** — добавить guard `valid + skipped == 0` ДО деления (иначе `ZeroDivisionError`
   при `MIN_VALID_ROWS=0` и пустом результате `valid=0, skipped=0`). Добавить тест: `min_valid_rows=0`
   + пустой результат → `False`, старый снимок жив.
2. **`parse` (тесты в Modify-задачах P2–P8)** — новые `import` переносить в шапку тест-файла
   (ruff `E402`), без `# noqa`.
3. **`parse._build_product`** — коммитить только финальную чистую версию, без иллюстративного `pass`.



---

# Группа задач 1: Task 0 — scaffold and tooling (единый владелец инфраструктуры)

Модуль scaffold — первая задача и ЕДИНСТВЕННЫЙ владелец инфраструктуры. Здесь нет бизнес-логики, поэтому «честный Red» — это **реальный отказ verify-команды** (ruff/mypy/pytest) на отсутствующей конфигурации/дереве ДО его создания, и зелёный — ПОСЛЕ. Исключение — `conftest.py` socket-guard: это исполняемая логика, у неё настоящий pytest Red→Green. Никаких заглушек, каждый коммит зелёный на тех инструментах, что уже установлены на этом шаге.

Платформа: Windows, Python 3.12 (соответствует `requires-python >=3.11`), git 2.53. Все команды кроссплатформенны.

---

### Init git repo on branch main

**Files:**
- Create: `E:\ADEL\.git\` (через `git init`)

**Steps:**

- [ ] Run & verify FAIL — репозитория ещё нет:
  ```
  git -C E:\ADEL rev-parse --abbrev-ref HEAD
  ```
  Expected FAIL: `fatal: not a git repository (or any of the parent directories): .git`, exit code 128.

- [ ] Minimal CORRECT impl — инициализировать репозиторий и явно задать ветку `main` (не полагаться на дефолт хоста):
  ```
  git -C E:\ADEL init
  git -C E:\ADEL symbolic-ref HEAD refs/heads/main
  git -C E:\ADEL config user.name "Adel"
  git -C E:\ADEL config user.email "eleru340@gmail.com"
  ```

- [ ] Run & verify PASS:
  ```
  git -C E:\ADEL rev-parse --abbrev-ref HEAD
  ```
  Expected PASS: печатает `main`, exit code 0.

- [ ] Commit (после создания `.gitignore` в следующей задаче не нужен здесь — первый коммит будет после `.gitignore`, чтобы не закоммитить мусор). На этом шаге коммита НЕТ.

---

### Create .gitignore guarding secrets and caches

**Files:**
- Create: `E:\ADEL\.gitignore`

**Steps:**

- [ ] Run & verify FAIL — файла ещё нет:
  ```
  python -c "import os,sys; sys.exit(0 if os.path.exists(r'E:\ADEL\.gitignore') else 1)"
  ```
  Expected FAIL: exit code 1 (файл отсутствует).

- [ ] Minimal CORRECT impl — содержимое `E:\ADEL\.gitignore` (порядок строк важен: общий glob `.env` идёт ДО исключения `!.env.example`):
  ```gitignore
  # secrets
  .env
  *.env
  !.env.example
  *service-account*.json
  *credentials*.json

  # python caches
  __pycache__/
  *.py[cod]
  .venv/
  .mypy_cache/
  .pytest_cache/
  .ruff_cache/
  .coverage
  *.egg-info/
  build/
  dist/
  ```

- [ ] Run & verify PASS — файл существует И правило исключения работает (git проверяет, что `.env` игнорируется, а `.env.example` — нет):
  ```
  python -c "import os,sys; sys.exit(0 if os.path.exists(r'E:\ADEL\.gitignore') else 1)"
  git -C E:\ADEL check-ignore -q .env; if ($LASTEXITCODE -ne 0) { throw 'FAIL: .env not ignored' }
  git -C E:\ADEL check-ignore -q .env.example; if ($LASTEXITCODE -eq 0) { throw 'FAIL: .env.example wrongly ignored' }
  Write-Host '[OK] gitignore secret rules correct'
  ```
  Expected PASS: печатает `[OK] gitignore secret rules correct`, exit code 0. (Bash-эквивалент: `git -C E:\ADEL check-ignore -q .env && ! git -C E:\ADEL check-ignore -q .env.example && echo '[OK]'`.)

- [ ] Commit:
  ```
  git -C E:\ADEL add .gitignore
  git -C E:\ADEL commit -m "chore: init repository with secret-guarding gitignore"
  ```

---

### Create directory tree and all __init__.py packages

**Files:**
- Create каталоги: `src/`, `src/data/`, `src/services/`, `src/bot/`, `src/bot/handlers/`, `src/bot/middlewares/`, `src/locales/`, `tests/`, `tests/data/`, `tests/services/`, `tests/bot/`, `tests/fixtures/`, `docs/adr/`
- Create `__init__.py`: `src/`, `src/data/`, `src/services/`, `src/bot/`, `src/bot/handlers/`, `src/bot/middlewares/`, `src/locales/`, `tests/`, `tests/data/`, `tests/services/`, `tests/bot/`

**Steps:**

- [ ] Write failing test — `E:\ADEL\tests\test_scaffold_layout.py` (ПОЛНЫЙ код; проверяет, что дерево и пакеты на месте — это исполняемая проверка инвариантов scaffold, а не бизнес-логика):
  ```python
  """Проверка инвариантов каркаса: дерево каталогов и пакеты-маркеры на месте."""
  from __future__ import annotations

  from pathlib import Path

  import pytest

  ROOT = Path(__file__).resolve().parent.parent

  EXPECTED_DIRS = (
      "src/data",
      "src/services",
      "src/bot/handlers",
      "src/bot/middlewares",
      "src/locales",
      "tests/data",
      "tests/services",
      "tests/bot",
      "tests/fixtures",
      "docs/adr",
  )

  EXPECTED_INIT = (
      "src/__init__.py",
      "src/data/__init__.py",
      "src/services/__init__.py",
      "src/bot/__init__.py",
      "src/bot/handlers/__init__.py",
      "src/bot/middlewares/__init__.py",
      "src/locales/__init__.py",
      "tests/__init__.py",
      "tests/data/__init__.py",
      "tests/services/__init__.py",
      "tests/bot/__init__.py",
  )


  @pytest.mark.parametrize("rel", EXPECTED_DIRS)
  def test_directory_exists(rel: str) -> None:
      assert (ROOT / rel).is_dir(), f"missing directory: {rel}"


  @pytest.mark.parametrize("rel", EXPECTED_INIT)
  def test_init_marker_exists(rel: str) -> None:
      assert (ROOT / rel).is_file(), f"missing package marker: {rel}"
  ```

- [ ] Run & verify FAIL — pytest пока не установлен и конфига нет, поэтому проверяем падение прямой проверкой существования (pytest появится позже; на этом шаге Red честный — каталогов нет):
  ```
  python -c "from pathlib import Path; import sys; r=Path(r'E:\ADEL'); missing=[p for p in ('src/data','tests/data','docs/adr') if not (r/p).is_dir()]; sys.exit(1 if missing else 0)"
  ```
  Expected FAIL: exit code 1 (каталоги `src/data`, `tests/data`, `docs/adr` отсутствуют).

- [ ] Minimal CORRECT impl — создать все каталоги и `__init__.py` (docstring в каждом маркере, чтобы прошёл ruff/mypy; контент english docstring per CLAUDE.md):
  ```
  $dirs = @('src\data','src\services','src\bot\handlers','src\bot\middlewares','src\locales','tests\data','tests\services','tests\bot','tests\fixtures','docs\adr')
  foreach ($d in $dirs) { New-Item -ItemType Directory -Force -Path (Join-Path 'E:\ADEL' $d) | Out-Null }
  ```
  Затем каждый `__init__.py` создаётся с одной строкой-докстрингом, например `src/__init__.py`:
  ```python
  """Application source root package."""
  ```
  `src/data/__init__.py`:
  ```python
  """Data layer: fetch, parse, cache, models."""
  ```
  `src/services/__init__.py`:
  ```python
  """Service layer: catalog, search, pagination, normalize."""
  ```
  `src/bot/__init__.py`:
  ```python
  """Bot layer: aiogram handlers, keyboards, middlewares."""
  ```
  `src/bot/handlers/__init__.py`:
  ```python
  """Aiogram message and callback handlers."""
  ```
  `src/bot/middlewares/__init__.py`:
  ```python
  """Aiogram middlewares: throttling, language injection."""
  ```
  `src/locales/__init__.py`:
  ```python
  """i18n locale registry."""
  ```
  `tests/__init__.py`, `tests/data/__init__.py`, `tests/services/__init__.py`, `tests/bot/__init__.py` — каждый:
  ```python
  """Test package."""
  ```

- [ ] Run & verify PASS — все каталоги и маркеры на месте:
  ```
  python -c "from pathlib import Path; import sys; r=Path(r'E:\ADEL'); dirs=('src/data','src/services','src/bot/handlers','src/bot/middlewares','src/locales','tests/data','tests/services','tests/bot','tests/fixtures','docs/adr'); inits=('src','src/data','src/services','src/bot','src/bot/handlers','src/bot/middlewares','src/locales','tests','tests/data','tests/services','tests/bot'); md=[d for d in dirs if not (r/d).is_dir()]; mi=[i for i in inits if not (r/i/'__init__.py').is_file()]; print('[OK] tree complete') if not md and not mi else print('[FAIL] missing dirs',md,'inits',mi); sys.exit(0 if not md and not mi else 1)"
  ```
  Expected PASS: печатает `[OK] tree complete`, exit code 0. (Сам `pytest tests/test_scaffold_layout.py` запустится зелёным в задаче установки зависимостей, где pytest уже есть.)

- [ ] Commit:
  ```
  git -C E:\ADEL add src tests docs
  git -C E:\ADEL commit -m "chore: scaffold package tree with init markers"
  ```

---

### Create final pyproject.toml (deps + ruff + mypy + pytest + coverage config)

**Files:**
- Create: `E:\ADEL\pyproject.toml`

**Steps:**

- [ ] Run & verify FAIL — конфига нет, поэтому tomllib не может его прочитать (честный Red: проверяем парсинг и наличие ключевых секций ДО создания):
  ```
  python -c "import tomllib,sys; open(r'E:\ADEL\pyproject.toml','rb')" 
  ```
  Expected FAIL: `FileNotFoundError: [Errno 2] No such file or directory: 'E:\\ADEL\\pyproject.toml'`, exit code 1.

- [ ] Minimal CORRECT impl — полный `E:\ADEL\pyproject.toml` (deps и dev-deps дословно из контракта; ruff select E,F,I,UP,B,ASYNC; mypy strict + override gspread; pytest asyncio_mode=strict testpaths=tests; coverage source=src; БЕЗ cov-fail-under в addopts — parse.py появится позже):
  ```toml
  [build-system]
  requires = ["setuptools>=68"]
  build-backend = "setuptools.build_meta"

  [project]
  name = "price-list-bot"
  version = "0.1.0"
  description = "Bilingual Telegram price-list bot backed by Google Sheets."
  requires-python = ">=3.11"
  dependencies = [
      "aiogram>=3,<4",
      "gspread>=6",
      "pydantic>=2",
      "pydantic-settings>=2",
  ]

  [project.optional-dependencies]
  dev = [
      "pytest>=8",
      "pytest-asyncio>=0.23",
      "pytest-cov>=5",
      "ruff>=0.6",
      "mypy>=1.11",
  ]

  [tool.setuptools.packages.find]
  where = ["src"]

  [tool.ruff]
  target-version = "py311"
  line-length = 100

  [tool.ruff.lint]
  select = ["E", "F", "I", "UP", "B", "ASYNC"]

  [tool.mypy]
  python_version = "3.11"
  strict = true
  warn_unused_configs = true

  [[tool.mypy.overrides]]
  module = ["gspread.*"]
  ignore_missing_imports = true

  [tool.pytest.ini_options]
  asyncio_mode = "strict"
  testpaths = ["tests"]

  [tool.coverage.run]
  source = ["src"]
  ```

- [ ] Run & verify PASS — файл парсится как валидный TOML И содержит обязательные секции/значения (проверяем контракт, не просто «файл есть»):
  ```
  python -c "import tomllib,sys; d=tomllib.load(open(r'E:\ADEL\pyproject.toml','rb')); assert d['tool']['ruff']['lint']['select']==['E','F','I','UP','B','ASYNC'], 'ruff select'; assert d['tool']['mypy']['strict'] is True, 'mypy strict'; assert d['tool']['pytest']['ini_options']['asyncio_mode']=='strict', 'asyncio strict'; assert d['tool']['coverage']['run']['source']==['src'], 'cov source'; assert 'fail_under' not in d['tool']['coverage'].get('report',{}), 'no fail_under yet'; assert d['tool']['setuptools']['packages']['find']['where']==['src'], 'pkg find'; print('[OK] pyproject contract satisfied')"
  ```
  Expected PASS: печатает `[OK] pyproject contract satisfied`, exit code 0.

- [ ] Commit:
  ```
  git -C E:\ADEL add pyproject.toml
  git -C E:\ADEL commit -m "chore: add pyproject with ruff, mypy strict, pytest, coverage config"
  ```

---

### Create .env.example with all contract env vars

**Files:**
- Create: `E:\ADEL\.env.example`

**Steps:**

- [ ] Run & verify FAIL — файла нет:
  ```
  python -c "import os,sys; sys.exit(0 if os.path.exists(r'E:\ADEL\.env.example') else 1)"
  ```
  Expected FAIL: exit code 1.

- [ ] Minimal CORRECT impl — полный `E:\ADEL\.env.example` со ВСЕМИ переменными из контракта config (комментарии — русские per CLAUDE.md; РОВНО один из двух creds-способов заполняется реально):
  ```dotenv
  # --- Telegram ---
  BOT_TOKEN=123456:REPLACE_WITH_BOT_TOKEN   # токен бота от @BotFather (обязателен)

  # --- Google Sheets ---
  SPREADSHEET_ID=REPLACE_WITH_SPREADSHEET_ID  # id таблицы (обязателен)
  SHEET_NAME=products                          # имя листа с товарами

  # --- Креды сервис-аккаунта: задать РОВНО ОДИН из двух ---
  GOOGLE_APPLICATION_CREDENTIALS=./service-account.json  # путь к json-файлу SA
  # GOOGLE_CREDENTIALS_B64=                              # base64 json SA (альтернатива пути)

  # --- Кэш и обновление ---
  CACHE_TTL_SECONDS=300        # период фонового refresh, сек (> 0)
  MIN_VALID_ROWS=1             # минимум валидных строк для принятия снимка (>= 0)
  COLD_START_BACKOFF_BASE_S=2.0  # база джиттер-backoff при cold-start, сек
  COLD_START_BACKOFF_MAX_S=60.0  # потолок backoff, сек

  # --- Каталог / валюты ---
  DEFAULT_CURRENCY=UZS         # валюта по умолчанию при пустой/нераспознанной
  CURRENCIES=UZS               # разрешённые валюты через запятую (csv)
  PAGE_SIZE=8                  # товаров на странице (1..10)

  # --- Бот / троттлинг ---
  THROTTLE_RATE_PER_SEC=1.0    # лимит запросов на пользователя в секунду (> 0)
  USE_WEBHOOK=false            # транспорт: false = polling

  # --- Логирование ---
  LOG_LEVEL=INFO               # уровень логов
  LOG_FORMAT=json              # формат логов: json|text

  # --- Shutdown ---
  SHUTDOWN_TIMEOUT_S=8.0       # таймаут graceful drain хендлеров, сек
  ```

- [ ] Run & verify PASS — файл существует И содержит все обязательные ключи из контракта (проверяем набор имён переменных, не просто существование):
  ```
  python -c "import sys; txt=open(r'E:\ADEL\.env.example',encoding='utf-8').read(); keys=[ln.split('=')[0].strip().lstrip('# ').strip() for ln in txt.splitlines() if '=' in ln]; req={'BOT_TOKEN','SPREADSHEET_ID','SHEET_NAME','CACHE_TTL_SECONDS','DEFAULT_CURRENCY','CURRENCIES','MIN_VALID_ROWS','PAGE_SIZE','THROTTLE_RATE_PER_SEC','GOOGLE_APPLICATION_CREDENTIALS','GOOGLE_CREDENTIALS_B64','USE_WEBHOOK','LOG_LEVEL','LOG_FORMAT','COLD_START_BACKOFF_BASE_S','COLD_START_BACKOFF_MAX_S','SHUTDOWN_TIMEOUT_S'}; got=set(keys); missing=req-got; print('[OK] env.example complete') if not missing else print('[FAIL] missing',missing); sys.exit(0 if not missing else 1)"
  ```
  Expected PASS: печатает `[OK] env.example complete`, exit code 0.

- [ ] Commit:
  ```
  git -C E:\ADEL add .env.example
  git -C E:\ADEL commit -m "chore: add .env.example documenting all settings"
  ```

---

### Install dependencies (pip install -e .[dev])

**Files:** (изменений в файлах нет — установка пакета)

**Steps:**

- [ ] Run & verify FAIL — dev-инструментов ещё нет в окружении (честный Red: ruff/mypy/pytest не установлены до `pip install`):
  ```
  python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('pytest') else 1)"
  ```
  Expected FAIL: exit code 1 (`pytest` не установлен). Аналогично `find_spec('ruff')`, `find_spec('mypy')` → None.

- [ ] Minimal CORRECT impl — установить проект в editable со всеми dev-зависимостями:
  ```
  python -m pip install -e "E:\ADEL[dev]"
  ```

- [ ] Run & verify PASS — все инструменты импортируются и пакет `src` доступен через editable install:
  ```
  python -c "import importlib.util,sys; need=['pytest','ruff','mypy','aiogram','gspread','pydantic','pydantic_settings']; missing=[m for m in need if importlib.util.find_spec(m) is None]; print('[OK] all deps importable') if not missing else print('[FAIL] missing',missing); sys.exit(0 if not missing else 1)"
  ```
  Expected PASS: печатает `[OK] all deps importable`, exit code 0.

- [ ] Commit (зависимости в lock не фиксируем — изменений файлов нет; коммита нет на этом шаге).

---

### Create conftest.py socket-guard (autouse, blocks real network)

**Files:**
- Create: `E:\ADEL\tests\conftest.py`
- Create: `E:\ADEL\tests\test_socket_guard.py`

**Steps:**

- [ ] Write failing test — `E:\ADEL\tests\test_socket_guard.py` (ПОЛНЫЙ код; реальная исполняемая логика — настоящий Red→Green: проверяет, что autouse-fixture блокирует сеть и не мешает локальным заглушкам):
  ```python
  """Проверка socket-guard: реальная сеть запрещена, монипуляция не ломает offline-логику."""
  from __future__ import annotations

  import socket

  import pytest


  def test_real_connect_is_blocked() -> None:
      """Попытка реального TCP-коннекта должна возбуждать RuntimeError от socket-guard."""
      sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      with pytest.raises(RuntimeError, match="network access disabled"):
          sock.connect(("93.184.216.34", 80))  # example.com — реальный адрес, коннект запрещён


  def test_creating_socket_object_is_allowed() -> None:
      """Создание объекта socket разрешено — запрещён только connect (offline-фикстуры не ломаются)."""
      sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      assert sock is not None
      sock.close()
  ```

- [ ] Run & verify FAIL — `conftest.py` ещё нет, guard не активен → `connect` НЕ бросает `RuntimeError` (а пытается реально/таймаутит), тест `test_real_connect_is_blocked` падает:
  ```
  python -m pytest E:\ADEL\tests\test_socket_guard.py -q
  ```
  Expected FAIL: `test_real_connect_is_blocked` падает с `Failed: DID NOT RAISE <class 'RuntimeError'>` (либо иной сетевой ошибкой/таймаутом вместо ожидаемого `RuntimeError`), exit code 1.

- [ ] Minimal CORRECT impl — `E:\ADEL\tests\conftest.py` (autouse-fixture патчит `socket.socket.connect`; типизировано под mypy --strict):
  ```python
  """Глобальные фикстуры тестов: запрет реальной сети (socket-guard)."""
  from __future__ import annotations

  import socket
  from collections.abc import Iterator
  from typing import Any

  import pytest


  @pytest.fixture(autouse=True)
  def _block_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
      """Блокировать любой реальный TCP-коннект в тестах.

      Создание сокетов разрешено (offline-фикстуры и заглушки их используют),
      запрещён только исходящий ``connect`` — гарантия, что тесты не ходят в сеть.
      """

      def _guard(self: socket.socket, *args: Any, **kwargs: Any) -> None:
          raise RuntimeError("network access disabled in tests")

      monkeypatch.setattr(socket.socket, "connect", _guard)
      yield
  ```

- [ ] Run & verify PASS:
  ```
  python -m pytest E:\ADEL\tests\test_socket_guard.py -q
  ```
  Expected PASS: `2 passed`, exit code 0.

- [ ] ruff + mypy зелёные на conftest и тестах:
  ```
  python -m ruff check E:\ADEL\tests
  python -m mypy E:\ADEL\tests\conftest.py
  ```
  Expected: ruff `All checks passed!`; mypy `Success: no issues found`.

- [ ] Commit:
  ```
  git -C E:\ADEL add tests/conftest.py tests/test_socket_guard.py
  git -C E:\ADEL commit -m "test: add autouse socket-guard blocking real network in tests"
  ```

---

### Final gate verify (ruff + mypy + pytest all green) and full-tree commit

**Files:** (изменений нет — финальная проверка всего каркаса и коммит ранее не добавленного тест-файла `test_scaffold_layout.py`)

**Steps:**

- [ ] Run & verify FAIL — `tests/test_scaffold_layout.py` создан в задаче дерева, но ещё не закоммичен; убедиться, что он есть и не в индексе (честный Red финального гейта: незакоммиченный артефакт каркаса):
  ```
  git -C E:\ADEL status --porcelain tests/test_scaffold_layout.py
  ```
  Expected FAIL-сигнал: строка `?? tests/test_scaffold_layout.py` (файл untracked → каркас не полностью зафиксирован).

- [ ] Minimal CORRECT impl — прогнать ЕДИНЫЙ гейт (ruff → mypy → pytest), как требует §10 SPEC, и зафиксировать оставшийся файл:
  ```
  python -m ruff check E:\ADEL
  python -m mypy E:\ADEL\src
  python -m pytest E:\ADEL
  ```

- [ ] Run & verify PASS — все три инструмента зелёные на полном дереве:
  - `python -m ruff check E:\ADEL` → `All checks passed!`, exit 0.
  - `python -m mypy E:\ADEL\src` → `Success: no issues found in N source files`, exit 0. (mypy на `src` — пакеты-маркеры с докстрингами проходят strict.)
  - `python -m pytest E:\ADEL` → собирает и проходит `test_socket_guard.py` (2 passed) и `test_scaffold_layout.py` (все parametrize-кейсы passed); итог `passed`, exit 0. Это и есть smoke-проверка `conftest`/коллекции из контракта (не «collected 0» — здесь уже есть зелёные scaffold-тесты, доказывающие живой каркас).

- [ ] Commit:
  ```
  git -C E:\ADEL add tests/test_scaffold_layout.py
  git -C E:\ADEL commit -m "test: add scaffold layout invariants test and finalize tooling gate"
  ```

- [ ] Final verify PASS — рабочее дерево чистое, каркас полностью зафиксирован:
  ```
  git -C E:\ADEL status --porcelain
  ```
  Expected PASS: пустой вывод (нет untracked/modified), exit 0. Печать `[OK] scaffold committed clean` подтверждает предусловие для всех последующих модулей (models → coerce → ...).


---

# Группа задач 2: src/data/models.py

## Модуль: `src/data/models.py` — доменные типы data-слоя

Чистый модуль типов: frozen-dataclass'ы контракта + `SchemaError` + `Catalog.build`.
Зависимостей от других модулей проекта нет (только stdlib). Scaffold (Task 0) уже создал
пакеты `src/`, `src/data/__init__.py`, `tests/`, `tests/data/__init__.py`, `conftest.py`,
`pyproject.toml`, `.gitignore` и установил зависимости. Здесь они НЕ создаются.

Файл `src/data/models.py` после Task 0 либо отсутствует, либо пуст/без нужных символов —
поэтому первый Red каждой подзадачи это `ImportError: cannot import name '<Symbol>' from 'src.data.models'`
(символ ИЗ нашего файла), а НЕ `No module named src`.

Декомпозиция: три подзадачи. Каждая добавляет НОВЫЙ символ контракта, чей импорт реально
падает до реализации, → честный Red-Green. `Catalog` несёт реальную логику (`build`), поэтому
не объединён с простыми типами; `ParseResult`/`Snapshot` зависят от `Catalog`, поэтому идут после него.

---

### Определения `Product`, `RowIssue`, `SchemaError` (иммутабельность, slots, None в опциональных)

**Files:**
- Modify: `src/data/models.py`
- Test: `tests/data/test_models.py`

- [ ] **Write failing test** — `tests/data/test_models.py`:

```python
"""Тесты доменных типов data-слоя."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from src.data.models import Product, RowIssue, SchemaError


def _make_product(**overrides: object) -> Product:
    """Фабрика Product с валидными дефолтами; overrides переопределяют поля."""
    base: dict[str, object] = {
        "id": "p1",
        "category": "cat",
        "subcategory": "sub",
        "name_ru": "Товар",
        "name_uz": "Mahsulot",
        "desc_ru": "опт",
        "desc_uz": "tavsif",
        "price_wholesale": Decimal("100"),
        "price_retail": Decimal("120"),
        "currency": "UZS",
        "packaging": "1 кг",
        "photo": "file_id",
        "is_active": True,
    }
    base.update(overrides)
    return Product(**base)  # type: ignore[arg-type]


def test_product_holds_all_fields() -> None:
    p = _make_product()
    assert p.id == "p1"
    assert p.category == "cat"
    assert p.subcategory == "sub"
    assert p.name_ru == "Товар"
    assert p.name_uz == "Mahsulot"
    assert p.price_wholesale == Decimal("100")
    assert p.price_retail == Decimal("120")
    assert p.currency == "UZS"
    assert p.is_active is True


def test_product_optional_fields_accept_none() -> None:
    p = _make_product(
        desc_ru=None,
        desc_uz=None,
        price_wholesale=None,  # цена по запросу
        price_retail=None,
        packaging=None,
        photo=None,
    )
    assert p.desc_ru is None
    assert p.desc_uz is None
    assert p.price_wholesale is None
    assert p.price_retail is None
    assert p.packaging is None
    assert p.photo is None


def test_product_is_frozen() -> None:
    p = _make_product()
    with pytest.raises(FrozenInstanceError):
        p.id = "other"  # type: ignore[misc]


def test_product_uses_slots_no_dict() -> None:
    """slots=True → нет __dict__ (защита памяти/опечаток в полях)."""
    p = _make_product()
    assert not hasattr(p, "__dict__")


def test_rowissue_holds_fields_and_optional_product_id() -> None:
    issue = RowIssue(row_number=3, product_id=None, reason="missing_required", detail="empty id")
    assert issue.row_number == 3
    assert issue.product_id is None
    assert issue.reason == "missing_required"
    assert issue.detail == "empty id"


def test_rowissue_is_frozen() -> None:
    issue = RowIssue(row_number=1, product_id="p1", reason="bad_number", detail="abc")
    with pytest.raises(FrozenInstanceError):
        issue.reason = "duplicate_id"  # type: ignore[misc]


def test_schema_error_is_exception() -> None:
    assert issubclass(SchemaError, Exception)
    with pytest.raises(SchemaError):
        raise SchemaError("missing column 'currency'")
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/data/test_models.py -q`
  Expected (collection error): `ImportError: cannot import name 'Product' from 'src.data.models'`
  (символ из нашего файла отсутствует — честный Red; НЕ `ModuleNotFoundError: No module named 'src'`).

- [ ] **Minimal CORRECT impl** — `src/data/models.py` (полные определения, без заглушек):

```python
"""Доменные типы data-слоя: иммутабельные модели каталога и результат парсинга.

Category/Subcategory здесь НЕТ — это навигационные view слоя services (другой план).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class Product:
    """Единица каталога. price_*=None означает «цена по запросу» (поле деградировало)."""

    id: str
    category: str
    subcategory: str
    name_ru: str
    name_uz: str
    desc_ru: str | None
    desc_uz: str | None
    price_wholesale: Decimal | None
    price_retail: Decimal | None
    currency: str
    packaging: str | None
    photo: str | None
    is_active: bool


@dataclass(frozen=True, slots=True)
class RowIssue:
    """Замечание по строке снимка. reason — стабильный код (см. parse)."""

    row_number: int  # 1-based номер строки данных (без заголовка)
    product_id: str | None
    # КОДЫ: missing_required | bad_number | unrecognized_bool | duplicate_id
    #     | empty_subcategory | empty_currency | unrecognized_currency | empty_is_active
    reason: str
    detail: str


class SchemaError(Exception):
    """Битая схема: rows непуст, но отсутствует обязательная колонка. parse() БРОСАЕТ это."""
```

- [ ] **Run & verify PASS** — `python -m pytest tests/data/test_models.py -q`
  Expected: все тесты этого файла зелёные.

- [ ] **Lint/type green** — `ruff check src/data/models.py tests/data/test_models.py && ruff format --check src/data/models.py tests/data/test_models.py && mypy --strict src/data/models.py tests/data/test_models.py`
  Expected: без ошибок (импорты `datetime`/`MappingProxyType`/`Iterable`/`Mapping` пока не используются — допустимо ТОЛЬКО если ruff не падает на F401; если падает — это сигнал перенести их добавление в подзадачи Catalog/Snapshot. См. примечание ниже.).
  Примечание: чтобы не держать неиспользуемые импорты на этом шаге, в impl выше оставлены лишь реально используемые (`dataclass`, `Decimal`). `datetime`, `MappingProxyType`, `Iterable`, `Mapping` добавляются ровно в той подзадаче, где появляется их потребитель (`Catalog`/`Snapshot`).

- [ ] **Commit** — `git add src/data/models.py tests/data/test_models.py && git commit -m "feat(models): add Product, RowIssue and SchemaError domain types"`

---

### `Catalog` + `Catalog.build` (MappingProxyType by_id, неизменяемость, без dedup)

**Files:**
- Modify: `src/data/models.py`
- Test: `tests/data/test_models.py`

- [ ] **Write failing test** — добавить в `tests/data/test_models.py`:

```python
from src.data.models import Catalog  # добавить к существующим импортам сверху файла


def test_catalog_build_indexes_by_id() -> None:
    a = _make_product(id="a")
    b = _make_product(id="b")
    catalog = Catalog.build([a, b])
    assert catalog.products == (a, b)  # порядок сохранён
    assert catalog.by_id["a"] is a
    assert catalog.by_id["b"] is b
    assert set(catalog.by_id) == {"a", "b"}


def test_catalog_by_id_is_read_only_mapping() -> None:
    """by_id — MappingProxyType: запись запрещена (атомарность/иммутабельность снимка)."""
    catalog = Catalog.build([_make_product(id="a")])
    with pytest.raises(TypeError):
        catalog.by_id["x"] = _make_product(id="x")  # type: ignore[index]


def test_catalog_build_does_not_dedup() -> None:
    """build НЕ дедупит — дедуп делает parse. Последний дубль id перетирает в by_id,
    но в products остаются оба (документированный контракт)."""
    first = _make_product(id="dup", name_ru="первый")
    second = _make_product(id="dup", name_ru="второй")
    catalog = Catalog.build([first, second])
    assert catalog.products == (first, second)  # оба товара сохранены
    assert catalog.by_id["dup"] is second  # by_id: последний wins (как обычный dict)


def test_catalog_build_empty() -> None:
    catalog = Catalog.build([])
    assert catalog.products == ()
    assert dict(catalog.by_id) == {}


def test_catalog_is_frozen() -> None:
    catalog = Catalog.build([_make_product(id="a")])
    with pytest.raises(FrozenInstanceError):
        catalog.products = ()  # type: ignore[misc]
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/data/test_models.py -q`
  Expected (collection error): `ImportError: cannot import name 'Catalog' from 'src.data.models'`
  (тип ещё не объявлен — честный Red на отсутствии нашей реализации).

- [ ] **Minimal CORRECT impl** — добавить в `src/data/models.py` (использует `MappingProxyType`, `Mapping`, `Iterable`):

```python
@dataclass(frozen=True, slots=True)
class Catalog:
    """Иммутабельный каталог: кортеж товаров + read-only индекс by_id.

    build НЕ выполняет дедупликацию — это ответственность parse(). При дублях id
    в by_id попадает последний товар (поведение dict), products сохраняет все.
    """

    products: tuple[Product, ...]
    by_id: Mapping[str, Product]  # MappingProxyType, неизменяемый

    @classmethod
    def build(cls, products: Iterable[Product]) -> "Catalog":
        items = tuple(products)
        index = MappingProxyType({p.id: p for p in items})
        return cls(products=items, by_id=index)
```

- [ ] **Run & verify PASS** — `python -m pytest tests/data/test_models.py -q`
  Expected: все тесты файла (включая прежние) зелёные.

- [ ] **Lint/type green** — `ruff check src/data/models.py tests/data/test_models.py && ruff format --check src/data/models.py tests/data/test_models.py && mypy --strict src/data/models.py tests/data/test_models.py`
  Expected: без ошибок (`Iterable`, `Mapping`, `MappingProxyType` теперь используются).

- [ ] **Commit** — `git add src/data/models.py tests/data/test_models.py && git commit -m "feat(models): add immutable Catalog with read-only by_id index"`

---

### `ParseResult` + `Snapshot` (зависят от Catalog; cold-start None)

**Files:**
- Modify: `src/data/models.py`
- Test: `tests/data/test_models.py`

- [ ] **Write failing test** — добавить в `tests/data/test_models.py`:

```python
from datetime import datetime, timezone  # добавить к импортам сверху файла

from src.data.models import ParseResult, Snapshot  # добавить к импортам


def test_parse_result_holds_catalog_and_counters() -> None:
    catalog = Catalog.build([_make_product(id="a")])
    issue = RowIssue(row_number=2, product_id=None, reason="missing_required", detail="empty id")
    result = ParseResult(catalog=catalog, issues=(issue,), valid_rows=1, skipped_rows=1)
    assert result.catalog is catalog
    assert result.issues == (issue,)
    assert result.valid_rows == 1
    assert result.skipped_rows == 1


def test_parse_result_is_frozen() -> None:
    result = ParseResult(catalog=Catalog.build([]), issues=(), valid_rows=0, skipped_rows=0)
    with pytest.raises(FrozenInstanceError):
        result.valid_rows = 5  # type: ignore[misc]


def test_snapshot_cold_start_allows_none_catalog() -> None:
    """До первого валидного снимка catalog и updated_at = None (cold-start)."""
    snap = Snapshot(catalog=None, updated_at=None, valid_rows=0, skipped_rows=0)
    assert snap.catalog is None
    assert snap.updated_at is None


def test_snapshot_with_catalog_and_timestamp() -> None:
    catalog = Catalog.build([_make_product(id="a")])
    ts = datetime(2026, 5, 31, tzinfo=timezone.utc)
    snap = Snapshot(catalog=catalog, updated_at=ts, valid_rows=1, skipped_rows=0)
    assert snap.catalog is catalog
    assert snap.updated_at == ts
    assert snap.valid_rows == 1


def test_snapshot_is_frozen() -> None:
    snap = Snapshot(catalog=None, updated_at=None, valid_rows=0, skipped_rows=0)
    with pytest.raises(FrozenInstanceError):
        snap.valid_rows = 1  # type: ignore[misc]
```

- [ ] **Run & verify FAIL** — `python -m pytest tests/data/test_models.py -q`
  Expected (collection error): `ImportError: cannot import name 'ParseResult' from 'src.data.models'`
  (оба типа ещё не объявлены — честный Red).

- [ ] **Minimal CORRECT impl** — добавить в `src/data/models.py` (использует `datetime`):

```python
@dataclass(frozen=True, slots=True)
class ParseResult:
    """Результат parse(): каталог (НЕ Optional, пустой при 0 валидных) + замечания + счётчики."""

    catalog: Catalog
    issues: tuple[RowIssue, ...]
    valid_rows: int
    skipped_rows: int


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Снимок в кэше. catalog/updated_at=None до первого валидного снимка (cold-start)."""

    catalog: Catalog | None
    updated_at: datetime | None
    valid_rows: int
    skipped_rows: int
```

- [ ] **Run & verify PASS** — `python -m pytest tests/data/test_models.py -q`
  Expected: все тесты файла зелёные.

- [ ] **Lint/type green** — `ruff check src/data/models.py tests/data/test_models.py && ruff format --check src/data/models.py tests/data/test_models.py && mypy --strict src/data/models.py tests/data/test_models.py`
  Expected: без ошибок (`datetime` теперь используется; неиспользуемых импортов в модуле не осталось).

- [ ] **Commit** — `git add src/data/models.py tests/data/test_models.py && git commit -m "feat(models): add ParseResult and Snapshot with cold-start support"`



---

# Группа задач 3: src/data/coerce.py

Модуль `src/data/coerce.py` — две чистые функции преобразования сырых строковых ячеек таблицы: `parse_number` (строка → `Decimal | None`) и `parse_bool` (строка → `bool | None`). Зависимостей от других модулей проекта нет (`consumes = []`). Импортируемые символы — `parse_number`, `parse_bool` из `src.data.coerce`. Обе фичи атомарны: одна задача = одна функция (все ветви сразу), дробление запрещено антидефектным чеклистом, т.к. каждая ветвь покрывается одним вызовом и поздняя ветвь не падает на «узкой» реализации — реализация структурная, не наращиваемая.

Предусловие (Task 0 scaffold готов): существуют git-репо, `pyproject.toml` с ruff+mypy --strict+pytest(asyncio strict), `src/__init__.py`, `src/data/__init__.py`, `tests/__init__.py`, `tests/data/__init__.py`, `tests/conftest.py`, `.gitignore`, установленные зависимости. Файла `src/data/coerce.py` ещё НЕТ — первый Red каждой задачи это `ImportError: cannot import name ... from src.data.coerce` (символ отсутствует в ТВОЁМ файле), а не `No module named src`.

Команды кроссплатформенны. Запускать из корня репо. Если в окружении `python` недоступен — заменить на `py` (Windows launcher); в CI используется `python`.

---

### Task A — `parse_number`: структурный разбор строки в `Decimal | None`

**Files:**
- Create: `src/data/coerce.py`
- Test: `tests/data/test_coerce.py`

Грамматика (контракт §ПРАВИЛА ПАРСИНГА): `strip` → `U+00A0`(неразрывный пробел) заменить на обычный пробел → удалить ВСЕ пробелы (трактуются как разделители тысяч) → проверки разделителей → `Decimal`. Правила запятой/точки: одновременно `,` и `.` ИЛИ более одной `,` → `None`; ровно одна `,` и `< 3` цифр после неё → десятичная (заменить `,` на `.`); ровно одна `,` и `>= 3` цифр после неё → `None`; `.` всегда десятичная (точка-как-тысячи НЕ поддерживается; несколько точек → `Decimal` бросит `InvalidOperation` → `None`); пустая строка / нечисловое / `InvalidOperation` → `None`. Разбор структурный (regex на финальную числовую форму), значение через `Decimal`, не `float`.

- [ ] **Write failing test.** Полный параметризованный тест на ВСЕ кейсы контракта (включая неразрывный пробел и отрицательное число). Записать в `tests/data/test_coerce.py`:

```python
"""Тесты чистых преобразователей строковых ячеек: parse_number, parse_bool."""
from __future__ import annotations

from decimal import Decimal

import pytest

from src.data.coerce import parse_number

NBSP = " "  # неразрывный пробел: трактуется как разделитель тысяч


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # пробелы = тысячи, удаляются
        ("120 000", Decimal("120000")),
        # одна запятая, < 3 цифр после → десятичная
        ("12,5", Decimal("12.5")),
        # одна запятая, ровно 3 цифры после → НЕ десятичная → None
        ("120,000", None),
        # пробел-тысячи + десятичная запятая
        ("1 200,50", Decimal("1200.50")),
        # точка = десятичная
        ("12.5", Decimal("12.5")),
        # точка-как-тысячи не поддерживается (несколько точек) → None
        ("1.234.567", None),
        # более одной запятой → None
        ("12,50,5", None),
        # нечисловое → None
        ("abc", None),
        # пустая строка → None
        ("", None),
        # неразрывный пробел тоже разделитель тысяч
        (f"120{NBSP}000", Decimal("120000")),
        # отрицательное число
        ("-5", Decimal("-5")),
    ],
)
def test_parse_number(raw: str, expected: Decimal | None) -> None:
    """Каждый кейс грамматики контракта даёт ожидаемый Decimal либо None."""
    assert parse_number(raw) == expected
```

- [ ] **Run & verify FAIL.** Команда: `python -m pytest tests/data/test_coerce.py -q`. Expected: сбор падает с `ImportError: cannot import name 'parse_number' from 'src.data.coerce'` (файл создаётся на следующем шаге, символа `parse_number` в нём ещё нет) — фактически Red на отсутствии ИМЕННО твоей реализации.

- [ ] **Minimal CORRECT impl.** Записать полный код в `src/data/coerce.py` (без заглушек, без TODO):

```python
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
    except InvalidOperation:
        return None
```

- [ ] **Run & verify PASS.** Команда: `python -m pytest tests/data/test_coerce.py -q`. Expected: все 11 кейсов `parse_number` зелёные.

- [ ] **Lint + types green.** Команды: `ruff check src/data/coerce.py tests/data/test_coerce.py` и `ruff format --check src/data/coerce.py tests/data/test_coerce.py` и `mypy --strict src/data/coerce.py tests/data/test_coerce.py`. Expected: без ошибок.

- [ ] **Commit.** `git add src/data/coerce.py tests/data/test_coerce.py` затем `git commit -m "feat(data): add parse_number string-to-Decimal coercion"`.

---

### Task B — `parse_bool`: нормализация апострофов + множества → `bool | None`

**Files:**
- Modify: `src/data/coerce.py`
- Test: `tests/data/test_coerce.py`

Правила (контракт): `strip` + `lower`; апострофы `[U+02BB, U+0027, U+2019, U+02BC]` свести к одному каноническому (`U+0027`); `true = {true, 1, да, ha, +, yes}`; `false = {false, 0, нет, yoq, yo'q, -, no}`; иначе `None`. Узбекское «нет» `yo'q` пишут с разными апострофами — после нормализации все варианты `yo<ap>q` попадают в `false`; голый `yoq` тоже в `false`.

- [ ] **Write failing test.** Дописать в существующий `tests/data/test_coerce.py` (НЕ перезаписывая Task A). Добавить импорт `parse_bool` и блок тестов:

```python
from src.data.coerce import parse_bool  # noqa: E402  (дополняет существующий импорт coerce)

# Три «не-ASCII» вида апострофа узбекского yo'q (канонический U+0027 проверяется отдельным кейсом).
_AP_VARIANTS = ["ʻ", "’", "ʼ"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # true-множество (в т.ч. регистр и пробелы вокруг)
        ("true", True),
        ("TRUE", True),
        (" True ", True),
        ("1", True),
        ("да", True),
        ("ha", True),
        ("+", True),
        ("yes", True),
        # false-множество
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("нет", False),
        ("yoq", False),
        ("yo'q", False),  # апостроф U+0027 (канонический)
        ("-", False),
        ("no", False),
        # нераспознанное → None
        ("maybe", None),
        ("", None),
        ("2", None),
    ],
)
def test_parse_bool(raw: str, expected: bool | None) -> None:
    """Каждый литерал true/false-множества (и мусор) даёт ожидаемый bool|None."""
    assert parse_bool(raw) is expected


@pytest.mark.parametrize("apostrophe", _AP_VARIANTS)
def test_parse_bool_uz_apostrophe_variants(apostrophe: str) -> None:
    """yo'q с любым из не-ASCII апострофов нормализуется и распознаётся как False."""
    assert parse_bool(f"yo{apostrophe}q") is False
```

- [ ] **Run & verify FAIL.** Команда: `python -m pytest tests/data/test_coerce.py -q`. Expected: сбор падает с `ImportError: cannot import name 'parse_bool' from 'src.data.coerce'` (символ `parse_bool` ещё не определён в твоём файле) — честный Red на отсутствии именно этой реализации; тесты Task A на `parse_number` при этом не запускаются, т.к. падает импорт всего модуля.

- [ ] **Minimal CORRECT impl.** Дописать в `src/data/coerce.py` (после `parse_number`, не трогая её):

```python
# Апострофы узбекской латиницы: разные кодовые точки сводятся к ASCII U+0027,
# чтобы yoʻq / yo’q / yoʼq / yo'q совпадали с каноническим литералом.
_CANONICAL_APOSTROPHE = "'"
_APOSTROPHES = ("ʻ", "'", "’", "ʼ")
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
```

- [ ] **Run & verify PASS.** Команда: `python -m pytest tests/data/test_coerce.py -q`. Expected: все кейсы `parse_number`, `parse_bool` и 3 апостроф-варианта зелёные.

- [ ] **Coverage 100% on coerce.** Команда: `python -m pytest tests/data/test_coerce.py --cov=src.data.coerce --cov-report=term-missing -q`. Expected: `src/data/coerce.py` — `100%`, столбец `Missing` пуст.

- [ ] **Lint + types green.** Команды: `ruff check src/data/coerce.py tests/data/test_coerce.py` и `ruff format --check src/data/coerce.py tests/data/test_coerce.py` и `mypy --strict src/data/coerce.py tests/data/test_coerce.py`. Expected: без ошибок.

- [ ] **Commit.** `git add src/data/coerce.py tests/data/test_coerce.py` затем `git commit -m "feat(data): add parse_bool with uzbek apostrophe normalization"`.


---

# Группа задач 4: src/data/fetch.py

> Модуль: `src/data/fetch.py` — грязный I/O поверх gspread. Чистое ядро (`parse`) его НЕ импортирует.
> Контракт (дословно из задания, не менять):
> - `class FetchError(Exception): def __init__(self, message, *, transient, retry_after=None)`
> - `fetch_rows(client: object, spreadsheet_id: str, worksheet_name: str) -> list[dict[str, str]]`
> Зависимости-предпосылки (создаёт Task 0 scaffold, я их НЕ создаю): git, дерево `src/data/`, `tests/data/`,
> окончательный `pyproject.toml`, все `__init__.py`, `conftest.py`, `.gitignore`, установленный `gspread`.
> Я НЕ создаю заглушки `models.py`/`refresh.py`/`parse.py` — мой модуль их не импортирует.
>
> Факты по gspread 6.2.1 (проверены по исходникам, не догадка):
> - `client.open_by_key(key: str) -> Spreadsheet`; `spreadsheet.worksheet(title: str) -> Worksheet`;
>   `worksheet.get_all_records() -> list[dict[str, int | float | str]]` (значения уже примитивы, но могут быть
>   int/float/bool/None в зависимости от данных листа — приводим КАЖДУЮ ячейку к str).
> - `gspread.exceptions.APIError(response)` — берёт `self.response`, `self.code` из `response.json()["error"]["code"]`.
>   Поэтому классификацию делаем по `exc.response.status_code` и `exc.response.headers` (атрибуты `requests.Response`),
>   а НЕ по `exc.code`. Фейк-исключение в тестах наследует реальный `APIError` и переопределяет `__init__`
>   (чтобы не лезть в `response.json()`), оставляя `.response` с `.status_code` и `.headers` — `except APIError` его ловит.
>
> Реализация дробится так: A — `FetchError` (атомарный класс, импортируется refresh); B — `fetch_rows` happy-path
> (приведение типов к str, без классификации ошибок); C — классификация `APIError` (НОВАЯ ветвь `except`,
> реально падает на impl из B); D — сетевые/таймаут-ошибки вне `APIError` (НОВАЯ ветвь, реально падает на impl из C).
> Каждая задача: failing test (полный код) → verify FAIL (точное сообщение) → корректная impl (полный код) →
> verify PASS → ruff+mypy зелёные → commit.

### A. `FetchError`: класс ошибки с флагом `transient` и `retry_after`

**Files**
- Create: `src/data/fetch.py`
- Test: `tests/data/test_fetch.py`

- [ ] Write failing test (первый Red моего файла — `ImportError` символа `FetchError` ИЗ моего файла, НЕ "No module named src"):

```python
# tests/data/test_fetch.py
"""Тесты грязного I/O-слоя fetch поверх gspread."""
from __future__ import annotations

from src.data.fetch import FetchError


def test_fetch_error_stores_transient_and_retry_after() -> None:
    """FetchError хранит message, transient-флаг и retry_after (kwargs-only)."""
    err = FetchError("rate limited", transient=True, retry_after=30.0)
    assert str(err) == "rate limited"
    assert err.transient is True
    assert err.retry_after == 30.0


def test_fetch_error_retry_after_defaults_to_none() -> None:
    """retry_after по умолчанию None; transient остаётся обязательным kwarg."""
    err = FetchError("forbidden", transient=False)
    assert err.transient is False
    assert err.retry_after is None
```

- [ ] Run & verify FAIL:
  - Команда: `python -m pytest tests/data/test_fetch.py -q`
  - Expected: collection-error `ImportError: cannot import name 'FetchError' from 'src.data.fetch'`
    (файла/символа нет — это честный Red ИЗ моего файла, не "No module named src").

- [ ] Minimal CORRECT impl (полный класс, без заглушек):

```python
# src/data/fetch.py
"""Грязный I/O-слой: чтение строк из Google Sheets через gspread.

Граница типов: всё, что приходит из gspread (Any), здесь приводится к str.
Чистое ядро (parse) этот модуль НЕ импортирует.
"""
from __future__ import annotations


class FetchError(Exception):
    """Ошибка чтения данных из Google Sheets.

    transient=True — временная (429/5xx/таймаут/сеть): refresh уходит в backoff
    или уважает retry_after. transient=False — фатальная (401/403/404/битый creds):
    refresh пробрасывает наружу, main завершает процесс с exit(1).
    """

    def __init__(
        self, message: str, *, transient: bool, retry_after: float | None = None
    ) -> None:
        super().__init__(message)
        self.transient = transient
        self.retry_after = retry_after
```

- [ ] Run & verify PASS: `python -m pytest tests/data/test_fetch.py -q` → 2 passed.
- [ ] Quality green: `python -m ruff check src/data/fetch.py tests/data/test_fetch.py` и
  `python -m mypy --strict src/data/fetch.py tests/data/test_fetch.py` → без ошибок.
- [ ] Commit: `feat: add FetchError with transient flag and retry_after`

---

### B. `fetch_rows` happy-path: каждая ячейка приводится к `str`

**Files**
- Modify: `src/data/fetch.py`
- Test: `tests/data/test_fetch.py`

- [ ] Write failing test (Red — `cannot import name 'fetch_rows'`; фейк-клиент, без сети и без реального gspread).
  Фейк-двойники моделируют цепочку `open_by_key -> worksheet -> get_all_records` и разнотипные ячейки:

```python
# tests/data/test_fetch.py  (добавить к существующему)
from src.data.fetch import FetchError, fetch_rows  # noqa: F401  (FetchError уже импортирован выше — оставить один импорт)


class _FakeWorksheet:
    """Двойник gspread Worksheet: возвращает заранее заданные записи."""

    def __init__(self, records: list[dict[str, object]]) -> None:
        self._records = records

    def get_all_records(self) -> list[dict[str, object]]:
        return self._records


class _FakeSpreadsheet:
    """Двойник gspread Spreadsheet: отдаёт лист по имени, проверяет имя."""

    def __init__(self, worksheet: _FakeWorksheet, expected_title: str) -> None:
        self._worksheet = worksheet
        self._expected_title = expected_title

    def worksheet(self, title: str) -> _FakeWorksheet:
        assert title == self._expected_title
        return self._worksheet


class _FakeClient:
    """Двойник gspread Client: отдаёт книгу по ключу, проверяет ключ."""

    def __init__(self, spreadsheet: _FakeSpreadsheet, expected_key: str) -> None:
        self._spreadsheet = spreadsheet
        self._expected_key = expected_key

    def open_by_key(self, key: str) -> _FakeSpreadsheet:
        assert key == self._expected_key
        return self._spreadsheet


def _make_client(records: list[dict[str, object]]) -> _FakeClient:
    ws = _FakeWorksheet(records)
    sheet = _FakeSpreadsheet(ws, expected_title="products")
    return _FakeClient(sheet, expected_key="SHEET_KEY")


def test_fetch_rows_coerces_every_cell_to_str() -> None:
    """int/float/bool/None приводятся к str; None -> пустая строка, не 'None'."""
    records: list[dict[str, object]] = [
        {"id": "A1", "price": 120000, "ratio": 12.5, "is_active": True, "desc": None},
    ]
    client = _make_client(records)

    rows = fetch_rows(client, "SHEET_KEY", "products")

    assert rows == [
        {"id": "A1", "price": "120000", "ratio": "12.5", "is_active": "True", "desc": ""},
    ]
    # Тип возврата — именно str по каждой ячейке.
    assert all(isinstance(v, str) for row in rows for v in row.values())


def test_fetch_rows_returns_empty_list_for_empty_sheet() -> None:
    """Лист с заголовком, но без строк данных -> пустой list (НЕ ошибка)."""
    client = _make_client([])
    assert fetch_rows(client, "SHEET_KEY", "products") == []
```

- [ ] Run & verify FAIL:
  - Команда: `python -m pytest tests/data/test_fetch.py -q`
  - Expected: `ImportError: cannot import name 'fetch_rows' from 'src.data.fetch'`
    (класс есть, функции нет — Red на отсутствии именно моей функции).

- [ ] Minimal CORRECT impl (полная функция; классификации ошибок ещё нет — добавится в C/D, где её тест реально падает):

```python
# src/data/fetch.py  (добавить импорты вверху и функцию)
from typing import Any


def _cell_to_str(value: Any) -> str:
    """Привести значение ячейки к str. None -> пустая строка (а не 'None')."""
    if value is None:
        return ""
    return str(value)


def fetch_rows(
    client: object, spreadsheet_id: str, worksheet_name: str
) -> list[dict[str, str]]:
    """Прочитать строки листа Google Sheets, приведя каждую ячейку к str.

    Граница типов: gspread отдаёт int/float/bool/None — здесь всё становится str,
    чтобы чистое ядро parse работало только со строками.
    """
    spreadsheet = client.open_by_key(spreadsheet_id)  # type: ignore[attr-defined]
    worksheet = spreadsheet.worksheet(worksheet_name)
    records: list[dict[str, Any]] = worksheet.get_all_records()
    return [{key: _cell_to_str(value) for key, value in record.items()} for record in records]
```

- [ ] Run & verify PASS: `python -m pytest tests/data/test_fetch.py -q` → 4 passed.
- [ ] Quality green: `python -m ruff check src/data/fetch.py tests/data/test_fetch.py` и
  `python -m mypy --strict src/data/fetch.py tests/data/test_fetch.py` → без ошибок.
  (`# type: ignore[attr-defined]` на `open_by_key` оправдан: параметр объявлен `object` по контракту,
  а реальный тип — gspread.Client; альтернатива — Protocol, но контракт фиксирует `client: object`.)
- [ ] Commit: `feat: read sheet rows via gspread, coercing every cell to str`

---

### C. Классификация `gspread.APIError` по HTTP-статусу

**Files**
- Modify: `src/data/fetch.py`
- Test: `tests/data/test_fetch.py`

- [ ] Write failing test (НОВАЯ ветвь `except APIError` — её нет в impl из B, поэтому APIError утечёт наружу как
  сам APIError, а тест ждёт FetchError → реальный Red, не искусственный). Фейк-исключение наследует реальный
  `gspread.exceptions.APIError`, переопределяя `__init__`, чтобы не парсить `response.json()`:

```python
# tests/data/test_fetch.py  (добавить)
import pytest
from gspread.exceptions import APIError


class _FakeResponse:
    """Двойник requests.Response: только то, что читает классификатор fetch."""

    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}


class _FakeAPIError(APIError):
    """Двойник gspread.APIError без парсинга JSON-тела (реальный __init__ лезет в response.json())."""

    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        # НЕ вызываем APIError.__init__ — он требует валидный JSON; нам нужен только .response.
        Exception.__init__(self, f"api error {status_code}")
        self.response = _FakeResponse(status_code, headers)  # type: ignore[assignment]


class _RaisingWorksheet:
    """Двойник Worksheet: get_all_records бросает заданное исключение."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def get_all_records(self) -> list[dict[str, object]]:
        raise self._exc


def _client_raising(exc: BaseException) -> _FakeClient:
    ws = _RaisingWorksheet(exc)
    sheet = _FakeSpreadsheet(ws, expected_title="products")  # type: ignore[arg-type]
    return _FakeClient(sheet, expected_key="SHEET_KEY")


def test_fetch_rows_429_is_transient_with_retry_after() -> None:
    """429 -> FetchError(transient=True, retry_after=float(Retry-After))."""
    client = _client_raising(_FakeAPIError(429, {"Retry-After": "30"}))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is True
    assert exc_info.value.retry_after == 30.0


def test_fetch_rows_429_without_retry_after_header() -> None:
    """429 без заголовка Retry-After -> transient=True, retry_after=None."""
    client = _client_raising(_FakeAPIError(429))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is True
    assert exc_info.value.retry_after is None


@pytest.mark.parametrize("status", [401, 403, 404])
def test_fetch_rows_auth_errors_are_non_transient(status: int) -> None:
    """401/403/404 -> FetchError(transient=False) (main завершит процесс)."""
    client = _client_raising(_FakeAPIError(status))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is False
    assert exc_info.value.retry_after is None


def test_fetch_rows_5xx_is_transient() -> None:
    """5xx (например 500) -> FetchError(transient=True) без retry_after."""
    client = _client_raising(_FakeAPIError(500))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is True
    assert exc_info.value.retry_after is None
```

- [ ] Run & verify FAIL:
  - Команда: `python -m pytest tests/data/test_fetch.py -q -k "429 or auth or 5xx"`
  - Expected: `Failed: DID NOT RAISE <class 'src.data.fetch.FetchError'>` — impl из B не ловит APIError,
    поэтому наружу летит `_FakeAPIError` (подкласс gspread APIError), а тест ждёт FetchError.

- [ ] Minimal CORRECT impl — добавить `except APIError` с классификацией по `status_code`:

```python
# src/data/fetch.py  (добавить импорт и helper, обернуть тело fetch_rows в try)
from gspread.exceptions import APIError


def _retry_after_seconds(headers: object) -> float | None:
    """Извлечь Retry-After (секунды) из заголовков ответа; нераспознанное -> None."""
    get = getattr(headers, "get", None)
    if get is None:
        return None
    raw = get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        # Retry-After может быть HTTP-датой, а не числом — тогда не уважаем конкретное значение.
        return None


def _classify_api_error(exc: APIError) -> FetchError:
    """Преобразовать gspread APIError в FetchError по HTTP-статусу.

    429 -> transient + retry_after из заголовка; 401/403/404 -> non-transient;
    прочее (5xx и т.п.) -> transient (временный сбой сервиса).
    """
    status = getattr(exc.response, "status_code", None)
    if status == 429:
        return FetchError(
            "rate limited",
            transient=True,
            retry_after=_retry_after_seconds(getattr(exc.response, "headers", None)),
        )
    if status in (401, 403, 404):
        return FetchError(f"non-transient API error: {status}", transient=False)
    return FetchError(f"transient API error: {status}", transient=True)
```

  И обернуть конвейер чтения:

```python
def fetch_rows(
    client: object, spreadsheet_id: str, worksheet_name: str
) -> list[dict[str, str]]:
    """Прочитать строки листа Google Sheets, приведя каждую ячейку к str."""
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)  # type: ignore[attr-defined]
        worksheet = spreadsheet.worksheet(worksheet_name)
        records: list[dict[str, Any]] = worksheet.get_all_records()
    except APIError as exc:
        raise _classify_api_error(exc) from exc
    return [{key: _cell_to_str(value) for key, value in record.items()} for record in records]
```

- [ ] Run & verify PASS: `python -m pytest tests/data/test_fetch.py -q` → все passed (happy-path B не сломан).
- [ ] Quality green: `python -m ruff check ...` и `python -m mypy --strict ...` → без ошибок.
- [ ] Commit: `feat: classify gspread APIError into transient/non-transient FetchError`

---

### D. Сетевые/таймаут-ошибки вне `APIError` -> `transient=True`

**Files**
- Modify: `src/data/fetch.py`
- Test: `tests/data/test_fetch.py`

- [ ] Write failing test (НОВАЯ ветвь: `requests` RequestException и `TimeoutError` — НЕ подклассы APIError,
  поэтому impl из C их не ловит и они летят наружу как есть → реальный Red):

```python
# tests/data/test_fetch.py  (добавить)
import requests


def test_fetch_rows_network_error_is_transient() -> None:
    """Сетевой сбой (requests.ConnectionError) -> FetchError(transient=True)."""
    client = _client_raising(requests.exceptions.ConnectionError("conn reset"))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is True
    assert exc_info.value.retry_after is None


def test_fetch_rows_timeout_is_transient() -> None:
    """Таймаут (requests.Timeout) -> FetchError(transient=True)."""
    client = _client_raising(requests.exceptions.Timeout("read timed out"))
    with pytest.raises(FetchError) as exc_info:
        fetch_rows(client, "SHEET_KEY", "products")
    assert exc_info.value.transient is True
```

- [ ] Run & verify FAIL:
  - Команда: `python -m pytest tests/data/test_fetch.py -q -k "network or timeout"`
  - Expected: тест падает с `requests.exceptions.ConnectionError: conn reset` /
    `requests.exceptions.Timeout: read timed out` (исключение пролетело мимо `except APIError`,
    `pytest.raises(FetchError)` его не поймал) — честный Red на отсутствии ветви.

- [ ] Minimal CORRECT impl — добавить `except requests.exceptions.RequestException` ПОСЛЕ `except APIError`
  (APIError — подкласс GSpreadException, не RequestException, порядок не конфликтует):

```python
# src/data/fetch.py  (добавить импорт requests вверху, расширить try в fetch_rows)
import requests

# ... внутри fetch_rows, после блока except APIError:
    except requests.exceptions.RequestException as exc:
        # Сеть/таймаут на стороне requests — всегда временный сбой: refresh уйдёт в backoff.
        raise FetchError(f"network error: {exc}", transient=True) from exc
```

  Итоговое тело fetch_rows:

```python
def fetch_rows(
    client: object, spreadsheet_id: str, worksheet_name: str
) -> list[dict[str, str]]:
    """Прочитать строки листа Google Sheets, приведя каждую ячейку к str."""
    try:
        spreadsheet = client.open_by_key(spreadsheet_id)  # type: ignore[attr-defined]
        worksheet = spreadsheet.worksheet(worksheet_name)
        records: list[dict[str, Any]] = worksheet.get_all_records()
    except APIError as exc:
        raise _classify_api_error(exc) from exc
    except requests.exceptions.RequestException as exc:
        raise FetchError(f"network error: {exc}", transient=True) from exc
    return [{key: _cell_to_str(value) for key, value in record.items()} for record in records]
```

- [ ] Run & verify PASS: `python -m pytest tests/data/test_fetch.py -q` → все passed.
- [ ] Quality green: `python -m ruff check src/data/fetch.py tests/data/test_fetch.py` и
  `python -m mypy --strict src/data/fetch.py tests/data/test_fetch.py` → без ошибок.
- [ ] Commit: `feat: treat requests network/timeout errors as transient FetchError`

---

### Финальная сверка модуля (без отдельного коммита)

- [ ] `python -m pytest tests/data/test_fetch.py -q` → все 12 тестов passed (A:2, B:2, C:6, D:2).
- [ ] `python -m mypy --strict src/data/fetch.py` → `Success`.
- [ ] `python -m ruff check src/data/fetch.py` → `All checks passed`.
- [ ] Публичный контракт совпадает дословно: `FetchError(message, *, transient, retry_after=None)` и
  `fetch_rows(client: object, spreadsheet_id: str, worksheet_name: str) -> list[dict[str, str]]`.
  Импортируется downstream-модулем `refresh` (через `main.py`-адаптер `lambda: asyncio.to_thread(fetch_rows, ...)`).


---

# Группа задач 5: src/config.py

## Модуль: `src/config.py`

> Зависимости: только внешние (`pydantic`, `pydantic-settings`). От `src/data/*` модуль НЕ зависит — `Settings` самодостаточен.
> Предполагается готовым: Task 0 (scaffold) уже создал `pyproject.toml` с `pydantic-settings`, `src/__init__.py`, `tests/conftest.py`, `.gitignore`, `.env.example`, установил зависимости. Этот модуль их НЕ создаёт и НЕ трогает.
> Первый Red — `ImportError: cannot import name 'Settings' from 'src.config'` (символ из ЭТОГО файла), а не `No module named src`.
>
> Меняю: создаю `src/config.py`, `tests/test_config.py`. Не трогаю: ничего другого.
>
> Контракт ENV дословно: `BOT_TOKEN: SecretStr(req)`; `SPREADSHEET_ID: str(req)`; `SHEET_NAME='products'`; `CACHE_TTL_SECONDS=300(gt=0)`; `DEFAULT_CURRENCY='UZS'`; `CURRENCIES='UZS'(csv)`; `MIN_VALID_ROWS=1(ge=0)`; `PAGE_SIZE=8(ge=1,le=10)`; `THROTTLE_RATE_PER_SEC=1.0(gt=0)`; `GOOGLE_APPLICATION_CREDENTIALS: str|None=None`; `GOOGLE_CREDENTIALS_B64: SecretStr|None=None`; `USE_WEBHOOK=False`; `LOG_LEVEL='INFO'`; `LOG_FORMAT='json'`; `COLD_START_BACKOFF_BASE_S=2.0`; `COLD_START_BACKOFF_MAX_S=60.0`; `SHUTDOWN_TIMEOUT_S=8.0`. `model_config=SettingsConfigDict(env_file='.env', extra='forbid', frozen=True)`. `model_validator(mode='after')`: РОВНО один из `GOOGLE_APPLICATION_CREDENTIALS` / `GOOGLE_CREDENTIALS_B64` непуст, иначе `ValueError`.

---

### Задача 1: `Settings` (поля + взаимоисключение creds) — атомарная, не дробится

Цельная фича: класс `Settings(BaseSettings)` со ВСЕМИ полями контракта дословно + `model_validator(mode='after')` взаимоисключения creds. Все тесты (валид / оба creds / ни одного / extra=forbid / дефолты / валидаторы границ) пишутся сразу одним блоком, до `Settings` падают на `ImportError`, затем ПОЛНАЯ корректная impl делает их зелёными. Дробить нельзя — взаимоисключение creds бессмысленно без полей creds, а поля без валидатора не проходят даже happy-path (нужен хотя бы один creds).

**Files:**
- Create: `src/config.py`
- Test: `tests/test_config.py`

**Шаги:**

- [ ] Написать падающий тест `tests/test_config.py` (ПОЛНЫЙ код):

```python
"""Тесты конфигурации приложения (pydantic-settings)."""

from __future__ import annotations

import pytest
from pydantic import SecretStr, ValidationError

from src.config import Settings

# Минимальный валидный набор: оба обязательных поля + РОВНО один способ creds.
_BASE_ENV = {
    "BOT_TOKEN": "123:abc",
    "SPREADSHEET_ID": "sheet-xyz",
    "GOOGLE_APPLICATION_CREDENTIALS": "/srv/sa.json",
}


def _make(**overrides: object) -> Settings:
    """Собрать Settings из чистого окружения (_env_file=None — игнор реального .env)."""
    env = {**_BASE_ENV, **overrides}
    return Settings(_env_file=None, **env)  # type: ignore[arg-type]


def test_valid_minimal_settings() -> None:
    """Обязательные поля + один способ creds -> объект собирается, секрет скрыт."""
    settings = _make()
    assert settings.SPREADSHEET_ID == "sheet-xyz"
    assert isinstance(settings.BOT_TOKEN, SecretStr)
    assert settings.BOT_TOKEN.get_secret_value() == "123:abc"
    assert settings.GOOGLE_APPLICATION_CREDENTIALS == "/srv/sa.json"
    assert settings.GOOGLE_CREDENTIALS_B64 is None


def test_defaults_applied() -> None:
    """Поля с дефолтами получают значения контракта без явной передачи."""
    settings = _make()
    assert settings.SHEET_NAME == "products"
    assert settings.CACHE_TTL_SECONDS == 300
    assert settings.DEFAULT_CURRENCY == "UZS"
    assert settings.CURRENCIES == "UZS"
    assert settings.MIN_VALID_ROWS == 1
    assert settings.PAGE_SIZE == 8
    assert settings.THROTTLE_RATE_PER_SEC == 1.0
    assert settings.USE_WEBHOOK is False
    assert settings.LOG_LEVEL == "INFO"
    assert settings.LOG_FORMAT == "json"
    assert settings.COLD_START_BACKOFF_BASE_S == 2.0
    assert settings.COLD_START_BACKOFF_MAX_S == 60.0
    assert settings.SHUTDOWN_TIMEOUT_S == 8.0


def test_b64_creds_branch() -> None:
    """Второй способ creds (b64) без файла-пути -> валидно, секрет скрыт."""
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        BOT_TOKEN="123:abc",
        SPREADSHEET_ID="sheet-xyz",
        GOOGLE_CREDENTIALS_B64="eyJrIjoidiJ9",
    )
    assert settings.GOOGLE_APPLICATION_CREDENTIALS is None
    assert isinstance(settings.GOOGLE_CREDENTIALS_B64, SecretStr)


def test_both_creds_rejected() -> None:
    """Оба способа creds одновременно -> ValidationError (взаимоисключение)."""
    with pytest.raises(ValidationError):
        _make(GOOGLE_CREDENTIALS_B64="eyJrIjoidiJ9")


def test_no_creds_rejected() -> None:
    """Ни одного способа creds -> ValidationError."""
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            BOT_TOKEN="123:abc",
            SPREADSHEET_ID="sheet-xyz",
        )


def test_empty_string_creds_treated_as_absent() -> None:
    """Пустая строка в GOOGLE_APPLICATION_CREDENTIALS = отсутствие -> при отсутствии b64 ошибка."""
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            BOT_TOKEN="123:abc",
            SPREADSHEET_ID="sheet-xyz",
            GOOGLE_APPLICATION_CREDENTIALS="",
        )


def test_extra_env_forbidden() -> None:
    """Неизвестная переменная окружения -> ValidationError (extra='forbid')."""
    with pytest.raises(ValidationError):
        _make(SOME_UNKNOWN_VAR="x")


def test_missing_required_rejected() -> None:
    """Отсутствие обязательного SPREADSHEET_ID -> ValidationError."""
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            BOT_TOKEN="123:abc",
            GOOGLE_APPLICATION_CREDENTIALS="/srv/sa.json",
        )


def test_ttl_must_be_positive() -> None:
    """CACHE_TTL_SECONDS gt=0 -> 0 отвергается."""
    with pytest.raises(ValidationError):
        _make(CACHE_TTL_SECONDS=0)


def test_page_size_upper_bound() -> None:
    """PAGE_SIZE le=10 -> 11 отвергается."""
    with pytest.raises(ValidationError):
        _make(PAGE_SIZE=11)


def test_min_valid_rows_allows_zero() -> None:
    """MIN_VALID_ROWS ge=0 -> 0 допустимо."""
    settings = _make(MIN_VALID_ROWS=0)
    assert settings.MIN_VALID_ROWS == 0


def test_frozen_immutable() -> None:
    """frozen=True -> присваивание поля после создания запрещено."""
    settings = _make()
    with pytest.raises(ValidationError):
        settings.SHEET_NAME = "other"  # type: ignore[misc]
```

- [ ] Run & verify FAIL: `python -m pytest tests/test_config.py -q`
  Expected: collection error — `ImportError: cannot import name 'Settings' from 'src.config'` (файл `src/config.py` ещё не содержит `Settings`).

- [ ] Minimal CORRECT impl — создать `src/config.py` (ПОЛНЫЙ код, без заглушек):

```python
"""Конфигурация приложения из переменных окружения (pydantic-settings)."""

from __future__ import annotations

from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Все настройки бота. Источник — окружение/.env. Иммутабельна (frozen)."""

    # Обязательные секреты и идентификаторы.
    BOT_TOKEN: SecretStr
    SPREADSHEET_ID: str

    # Google Sheets.
    SHEET_NAME: str = "products"

    # Кэш / парсинг.
    CACHE_TTL_SECONDS: int = 300
    DEFAULT_CURRENCY: str = "UZS"
    CURRENCIES: str = "UZS"  # csv-список разрешённых валют
    MIN_VALID_ROWS: int = 1

    # UI / троттлинг.
    PAGE_SIZE: int = 8
    THROTTLE_RATE_PER_SEC: float = 1.0

    # Доставка service-account: РОВНО один из двух способов (см. валидатор ниже).
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None
    GOOGLE_CREDENTIALS_B64: SecretStr | None = None

    # Транспорт / логирование.
    USE_WEBHOOK: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"

    # Cold-start backoff / shutdown.
    COLD_START_BACKOFF_BASE_S: float = 2.0
    COLD_START_BACKOFF_MAX_S: float = 60.0
    SHUTDOWN_TIMEOUT_S: float = 8.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="forbid",
        frozen=True,
    )

    # Ограничения значений вынесены в Field на самих полях.
    # (см. метод-валидаторы ниже для границ, заданных контрактом)

    @model_validator(mode="after")
    def _exactly_one_credentials_source(self) -> Self:
        """РОВНО один способ доставки creds: путь к файлу ИЛИ base64. Пустая строка = отсутствие."""
        path = self.GOOGLE_APPLICATION_CREDENTIALS
        has_path = bool(path and path.strip())
        b64 = self.GOOGLE_CREDENTIALS_B64
        has_b64 = b64 is not None and bool(b64.get_secret_value().strip())
        if has_path == has_b64:  # оба заданы ИЛИ оба пусты
            raise ValueError(
                "exactly one of GOOGLE_APPLICATION_CREDENTIALS / "
                "GOOGLE_CREDENTIALS_B64 must be set"
            )
        return self
```

  Затем добавить границы значений через `Field` на полях с ограничениями контракта. Заменить соответствующие объявления:

```python
from pydantic import Field, SecretStr, model_validator
```

```python
    CACHE_TTL_SECONDS: int = Field(default=300, gt=0)
    MIN_VALID_ROWS: int = Field(default=1, ge=0)
    PAGE_SIZE: int = Field(default=8, ge=1, le=10)
    THROTTLE_RATE_PER_SEC: float = Field(default=1.0, gt=0)
```

  (полный файл после правок: импорт `Field`, четыре поля через `Field` с границами `gt=0` / `ge=0` / `ge=1,le=10` / `gt=0`, остальное как выше).

- [ ] Run & verify PASS: `python -m pytest tests/test_config.py -q`
  Expected: все тесты зелёные (11 passed).

- [ ] Verify-команда (печатает [OK]/[FAIL], код выхода 0/≠0):
  `python -c "import sys; from pydantic import ValidationError; from src.config import Settings; s=Settings(_env_file=None, BOT_TOKEN='t', SPREADSHEET_ID='id', GOOGLE_APPLICATION_CREDENTIALS='/p'); assert s.PAGE_SIZE==8 and s.BOT_TOKEN.get_secret_value()=='t'; ok=False;\nimport contextlib\nwith contextlib.suppress(ValidationError):\n    Settings(_env_file=None, BOT_TOKEN='t', SPREADSHEET_ID='id'); ok=True\nsys.exit(print('[OK] Settings ok, no-creds rejected') or 0) if not ok else sys.exit(print('[FAIL] no-creds accepted') or 1)"`

- [ ] Ruff + mypy зелёные: `ruff check src/config.py tests/test_config.py && ruff format --check src/config.py tests/test_config.py && mypy --strict src/config.py`

- [ ] Commit: `feat: add Settings config with env validation and mutually exclusive credentials`

---

### Задача 2: `allowed_currencies()` — честный red на новом методе

Новая ветвь поведения: метод парсит CSV `CURRENCIES` -> `frozenset[str]`. Это РЕАЛЬНО новый символ — тест `settings.allowed_currencies()` падает `AttributeError` на impl Задачи 1 (метода ещё нет). Минимальная корректная impl добавляет метод.

**Files:**
- Modify: `src/config.py`
- Test: `tests/test_config.py` (дополнить)

**Шаги:**

- [ ] Дописать падающие тесты в `tests/test_config.py` (ПОЛНЫЙ добавляемый блок):

```python
def test_allowed_currencies_single() -> None:
    """Дефолтный CURRENCIES='UZS' -> frozenset из одного элемента."""
    settings = _make()
    assert settings.allowed_currencies() == frozenset({"UZS"})


def test_allowed_currencies_multi_with_spaces() -> None:
    """CSV с пробелами и регистром -> upper + strip, пустые элементы отброшены."""
    settings = _make(CURRENCIES=" uzs , USD ,eur, ")
    assert settings.allowed_currencies() == frozenset({"UZS", "USD", "EUR"})


def test_allowed_currencies_returns_frozenset() -> None:
    """Результат — frozenset (иммутабелен), не set/list."""
    settings = _make()
    assert isinstance(settings.allowed_currencies(), frozenset)


def test_allowed_currencies_dedup() -> None:
    """Повторяющиеся валюты схлопываются."""
    settings = _make(CURRENCIES="UZS,uzs,UZS")
    assert settings.allowed_currencies() == frozenset({"UZS"})
```

- [ ] Run & verify FAIL: `python -m pytest tests/test_config.py -q -k allowed_currencies`
  Expected: `AttributeError: 'Settings' object has no attribute 'allowed_currencies'` (метода нет в impl Задачи 1).

- [ ] Minimal CORRECT impl — добавить метод в класс `Settings` (ПОЛНЫЙ код метода):

```python
    def allowed_currencies(self) -> frozenset[str]:
        """Разрешённые валюты из CSV CURRENCIES (upper+strip, пустые отброшены)."""
        return frozenset(
            token.strip().upper()
            for token in self.CURRENCIES.split(",")
            if token.strip()
        )
```

- [ ] Run & verify PASS: `python -m pytest tests/test_config.py -q`
  Expected: все тесты зелёные (15 passed).

- [ ] Verify-команда (печатает [OK]/[FAIL], код 0/≠0):
  `python -c "import sys; from src.config import Settings; s=Settings(_env_file=None, BOT_TOKEN='t', SPREADSHEET_ID='id', GOOGLE_CREDENTIALS_B64='x', CURRENCIES=' uzs , USD ,uzs'); got=s.allowed_currencies(); ok = got==frozenset({'UZS','USD'}) and isinstance(got, frozenset); sys.exit(print('[OK] allowed_currencies parses csv:', sorted(got)) or 0) if ok else sys.exit(print('[FAIL] got', got) or 1)"`

- [ ] Ruff + mypy зелёные: `ruff check src/config.py tests/test_config.py && ruff format --check src/config.py tests/test_config.py && mypy --strict src/config.py`

- [ ] Commit: `feat: add allowed_currencies helper parsing CURRENCIES csv`


---

# Группа задач 6: src/data/parse.py

Модуль `src/data/parse.py` — чистая функция `parse(rows, *, default_currency, fallback_subcategory, allowed_currencies) -> ParseResult`, конвейер `normalize_headers -> resolve_required (SchemaError) -> per-row -> dedup -> Catalog.build`.

Предполагается готовым (Task 0 scaffold + предыдущие модули): git-репозиторий, дерево, окончательный `pyproject.toml` (с `[tool.coverage]`, `[tool.mypy] strict`, `[tool.ruff]`, `pytest-asyncio` strict), все `__init__.py` (включая `src/__init__.py`, `src/data/__init__.py`, `tests/__init__.py`, `tests/data/__init__.py`), `conftest.py`, `.gitignore`, `.env.example`, установленные зависимости. `src/data/models.py` реализован дословно по контракту (Product, RowIssue, Catalog, ParseResult, SchemaError, Snapshot). `src/data/coerce.py` реализован (`parse_number`, `parse_bool`).

Мой модуль НЕ создаёт `pyproject`/`__init__`/`conftest` и НЕ создаёт заглушки чужих модулей. Первый Red — `ImportError: cannot import name 'parse' from 'src.data.parse'` (файл существует пустым/отсутствует символ), НЕ `No module named 'src'`.

Контракт сигнатуры (соблюдать дословно):
```python
parse(rows: Sequence[Mapping[str, str]], *, default_currency: str, fallback_subcategory: str,
      allowed_currencies: frozenset[str]) -> ParseResult   # БРОСАЕТ SchemaError; пустой rows -> пустой ParseResult
```

Обязательные колонки (required): `id`, `category`, `subcategory`, `name_ru`, `name_uz`, `price_wholesale`, `price_retail`, `currency`, `is_active`. Опциональные (если колонки нет — поле `None`/пусто, без SchemaError): `desc_ru`, `desc_uz`, `packaging`, `photo`. Матчинг по нормализованному (strip+lower) имени заголовка; лишние колонки игнорируются. `row_number` — 1-based номер строки данных (без заголовка), т.е. индекс в `rows` + 1.

---

### Task P1: scaffold-файла нет в конвейере — фикстуры + skeleton-конвейер (headers / SchemaError / пустой rows / happy single valid)

Первая АТОМАРНАЯ ветвь конвейера: `normalize_headers -> resolve_required -> (per-row для полностью валидной строки) -> Catalog.build -> ParseResult`. Эти кейсы покрываются ОДНИМ корректным skeleton'ом (без missing/деградаций/dedup — они в следующих задачах с реальным red на новой ветви). Реализация СРАЗУ корректна для своих кейсов: для полностью валидной строки (все поля заполнены, валидны, currency в allowed, is_active явный) — корректный Product; SchemaError при отсутствии required колонки; пустой rows -> пустой ParseResult.

**Files:**
- Create: `tests/fixtures/__init__.py` (фабрики строковых фикстур, ВСЕ значения `str`)
- Create: `tests/data/test_parse_schema.py`
- Create: `tests/data/test_parse.py`
- Create: `src/data/parse.py`

- [ ] **Write fixtures** `tests/fixtures/__init__.py` — фабрики `dict[str, str]` (все значения str), чтобы тесты не повторяли литералы:
```python
"""Строковые фикстуры строк листа для тестов parse (все значения — str, как из fetch)."""
from __future__ import annotations

ALLOWED_CURRENCIES = frozenset({"UZS", "USD"})
DEFAULT_CURRENCY = "UZS"
FALLBACK_SUBCATEGORY = "Прочее"

# Полностью валидная строка: все required заполнены, цены валидны, currency в allowed, is_active явный.
_VALID_BASE: dict[str, str] = {
    "id": "p1",
    "category": "Напитки",
    "subcategory": "Соки",
    "name_ru": "Сок яблочный",
    "name_uz": "Olma sharbati",
    "desc_ru": "Натуральный",
    "desc_uz": "Tabiiy",
    "price_wholesale": "12000",
    "price_retail": "15000",
    "currency": "UZS",
    "packaging": "1 л",
    "photo": "https://example.com/p1.jpg",
    "is_active": "true",
}


def valid_row(**overrides: str) -> dict[str, str]:
    """Валидная строка с возможностью переопределить любые поля (значения — str)."""
    row = dict(_VALID_BASE)
    row.update(overrides)
    return row


def row_without_key(key: str, **overrides: str) -> dict[str, str]:
    """Валидная строка, но без указанной колонки (для эмуляции отсутствия колонки в схеме)."""
    row = valid_row(**overrides)
    row.pop(key, None)
    return row
```

- [ ] **Write failing test** `tests/data/test_parse_schema.py`:
```python
"""Тесты схемы: SchemaError при отсутствии required колонки; пустой rows — не ошибка."""
from __future__ import annotations

import pytest

from src.data.models import ParseResult, SchemaError
from src.data.parse import parse
from tests.fixtures import ALLOWED_CURRENCIES, DEFAULT_CURRENCY, FALLBACK_SUBCATEGORY, row_without_key, valid_row


def _parse(rows: list[dict[str, str]]) -> ParseResult:
    return parse(
        rows,
        default_currency=DEFAULT_CURRENCY,
        fallback_subcategory=FALLBACK_SUBCATEGORY,
        allowed_currencies=ALLOWED_CURRENCIES,
    )


def test_empty_rows_returns_empty_result_not_schema_error() -> None:
    """Пустой список строк -> валидный пустой ParseResult, НЕ SchemaError."""
    result = _parse([])
    assert result.valid_rows == 0
    assert result.skipped_rows == 0
    assert result.issues == ()
    assert result.catalog.products == ()
    assert dict(result.catalog.by_id) == {}


@pytest.mark.parametrize(
    "missing",
    ["id", "category", "subcategory", "name_ru", "name_uz",
     "price_wholesale", "price_retail", "currency", "is_active"],
)
def test_missing_required_column_raises_schema_error(missing: str) -> None:
    """Непустой rows без required колонки -> SchemaError."""
    rows = [row_without_key(missing)]
    with pytest.raises(SchemaError):
        _parse(rows)


def test_missing_optional_column_is_ok() -> None:
    """Отсутствие опциональной колонки (desc_ru) -> не ошибка, поле None."""
    rows = [valid_row()]
    del rows[0]["desc_ru"]
    result = _parse(rows)
    assert result.valid_rows == 1
    assert result.catalog.products[0].desc_ru is None


def test_headers_normalized_strip_lower() -> None:
    """Заголовки матчатся по strip+lower: ' ID ' и 'Name_RU' распознаются."""
    row = {
        "  ID  ": "p1", "Category": "C", "SubCategory": "S",
        "NAME_RU": "rn", "Name_Uz": "un",
        "Price_Wholesale": "10", "PRICE_RETAIL": "20",
        "Currency": "UZS", "Is_Active": "true",
    }
    result = _parse([row])
    assert result.valid_rows == 1
    assert result.catalog.products[0].id == "p1"
```

- [ ] **Write failing test** `tests/data/test_parse.py` (happy single valid):
```python
"""Тесты parse: happy-path одной полностью валидной строки."""
from __future__ import annotations

from decimal import Decimal

from src.data.models import ParseResult
from src.data.parse import parse
from tests.fixtures import ALLOWED_CURRENCIES, DEFAULT_CURRENCY, FALLBACK_SUBCATEGORY, valid_row


def _parse(rows: list[dict[str, str]]) -> ParseResult:
    return parse(
        rows,
        default_currency=DEFAULT_CURRENCY,
        fallback_subcategory=FALLBACK_SUBCATEGORY,
        allowed_currencies=ALLOWED_CURRENCIES,
    )


def test_single_valid_row_builds_product() -> None:
    """Полностью валидная строка -> один Product, counts корректны, нет issues."""
    result = _parse([valid_row()])
    assert result.valid_rows == 1
    assert result.skipped_rows == 0
    assert result.issues == ()
    assert len(result.catalog.products) == 1
    p = result.catalog.products[0]
    assert p.id == "p1"
    assert p.category == "Напитки"
    assert p.subcategory == "Соки"
    assert p.name_ru == "Сок яблочный"
    assert p.name_uz == "Olma sharbati"
    assert p.desc_ru == "Натуральный"
    assert p.desc_uz == "Tabiiy"
    assert p.price_wholesale == Decimal("12000")
    assert p.price_retail == Decimal("15000")
    assert p.currency == "UZS"
    assert p.packaging == "1 л"
    assert p.photo == "https://example.com/p1.jpg"
    assert p.is_active is True
    assert result.catalog.by_id["p1"] is p


def test_empty_optional_fields_become_none() -> None:
    """Пустые опциональные поля (desc/packaging/photo) -> None в Product."""
    result = _parse([valid_row(desc_ru="", desc_uz="  ", packaging="", photo="")])
    p = result.catalog.products[0]
    assert p.desc_ru is None
    assert p.desc_uz is None
    assert p.packaging is None
    assert p.photo is None
```

- [ ] **Run & verify FAIL**: `pytest tests/data/test_parse_schema.py tests/data/test_parse.py -q`
  Expected: collection/import error — `ImportError: cannot import name 'parse' from 'src.data.parse'` (символа `parse` ещё нет в файле). Это честный Red ИЗ ТВОЕГО файла.

- [ ] **Minimal CORRECT impl** `src/data/parse.py` (полная корректная реализация skeleton-конвейера, без заглушек):
```python
"""Чистый парсер строк листа в ParseResult. Без сети/env/gspread/aiogram."""
from __future__ import annotations

from decimal import Decimal
from typing import Final, Mapping, Sequence

from src.data.coerce import parse_bool, parse_number
from src.data.models import Catalog, ParseResult, Product, RowIssue, SchemaError

# Обязательные колонки: их отсутствие в непустой схеме -> SchemaError.
_REQUIRED_COLUMNS: Final[frozenset[str]] = frozenset(
    {"id", "category", "subcategory", "name_ru", "name_uz",
     "price_wholesale", "price_retail", "currency", "is_active"}
)
# Опциональные: если колонки нет -> поле None, без ошибки.
_OPTIONAL_COLUMNS: Final[frozenset[str]] = frozenset(
    {"desc_ru", "desc_uz", "packaging", "photo"}
)


def normalize_headers(row: Mapping[str, str]) -> dict[str, str]:
    """Нормализовать ключи (strip+lower). Значения не трогаем. Лишние колонки остаются (игнор позже)."""
    return {key.strip().lower(): value for key, value in row.items()}


def _resolve_required(first_row: Mapping[str, str]) -> None:
    """Проверить наличие всех required колонок в нормализованной первой строке. Иначе SchemaError."""
    present = set(first_row.keys())
    missing = _REQUIRED_COLUMNS - present
    if missing:
        raise SchemaError(f"missing required columns: {sorted(missing)}")


def _opt(row: Mapping[str, str], key: str) -> str | None:
    """Опциональное строковое поле: пусто/whitespace -> None, иначе strip-значение."""
    value = row.get(key, "").strip()
    return value or None


def _build_valid_product(row: Mapping[str, str]) -> Product:
    """Собрать Product из НОРМАЛИЗОВАННОЙ валидной строки (skeleton: поля заполнены и валидны).

    На этом этапе обрабатываются только полностью валидные строки. Деградации (пустая
    subcategory/currency, bad_number, is_active) добавляются отдельными ветвями в следующих задачах.
    """
    price_w = parse_number(row["price_wholesale"])
    price_r = parse_number(row["price_retail"])
    is_active = parse_bool(row["is_active"])
    return Product(
        id=row["id"].strip(),
        category=row["category"].strip(),
        subcategory=row["subcategory"].strip(),
        name_ru=row["name_ru"].strip(),
        name_uz=row["name_uz"].strip(),
        desc_ru=_opt(row, "desc_ru"),
        desc_uz=_opt(row, "desc_uz"),
        price_wholesale=price_w,
        price_retail=price_r,
        currency=row["currency"].strip(),
        packaging=_opt(row, "packaging"),
        photo=_opt(row, "photo"),
        is_active=bool(is_active),
    )


def parse(
    rows: Sequence[Mapping[str, str]],
    *,
    default_currency: str,
    fallback_subcategory: str,
    allowed_currencies: frozenset[str],
) -> ParseResult:
    """Распарсить строки листа в ParseResult. Чистая. БРОСАЕТ SchemaError при битой схеме."""
    if not rows:
        return ParseResult(catalog=Catalog.build(()), issues=(), valid_rows=0, skipped_rows=0)

    normalized = [normalize_headers(row) for row in rows]
    _resolve_required(normalized[0])

    products: list[Product] = []
    issues: list[RowIssue] = []
    for index, row in enumerate(normalized):
        product = _build_valid_product(row)
        products.append(product)

    catalog = Catalog.build(products)
    return ParseResult(
        catalog=catalog,
        issues=tuple(issues),
        valid_rows=len(products),
        skipped_rows=len(normalized) - len(products),
    )
```
  Примечание: `row_number`-логика, `index`, `Decimal` импорт пока заведены под будущие ветви; чтобы ruff не ругался на неиспользуемое — убери `Decimal` и `index` если линтер ругается на текущем шаге, верни на ветви где нужны. (На P1 `index`/`Decimal` НЕ используются — НЕ импортируй их здесь; добавь в задачах, где появится ветвь.)

- [ ] **Fix unused (ruff)**: на P1 убрать неиспользуемые `Decimal` и `index` (переписать цикл как `for row in normalized:`). Импорт `Decimal` не добавлять до задачи, где он реально нужен (он не нужен — `parse_number` возвращает Decimal сам).

- [ ] **Run & verify PASS**: `pytest tests/data/test_parse_schema.py tests/data/test_parse.py -q` -> все зелёные.
- [ ] **Quality green**: `ruff check src/data/parse.py tests/data/test_parse.py tests/data/test_parse_schema.py tests/fixtures/__init__.py` и `mypy --strict src/data/parse.py` -> 0 ошибок.
- [ ] **Commit**: `feat: add parse skeleton pipeline with header resolution and schema check`

---

### Task P2: новая ветвь — battered rows (missing_required отсев)

НОВАЯ ветвь: строка с пустым/whitespace `id|category|name_ru|name_uz` -> пропуск, `RowIssue(missing_required)`, НЕ в каталоге, `skipped_rows` растёт. Тест ПАДАЕТ на P1-реализации: P1 безусловно строит Product из каждой строки (нет отсева), поэтому битая строка попадёт в каталог и `skipped_rows` будет 0 -> assert провалится.

**Files:**
- Modify: `tests/data/test_parse.py`
- Modify: `src/data/parse.py`

- [ ] **Write failing test** (добавить в `tests/data/test_parse.py`):
```python
import pytest

from src.data.models import RowIssue
from tests.fixtures import valid_row as _vr  # уже импортирован valid_row; этот alias не нужен если есть


@pytest.mark.parametrize("field", ["id", "category", "name_ru", "name_uz"])
def test_empty_required_field_skips_row(field: str) -> None:
    """Пустое обязательное поле -> строка пропущена, RowIssue(missing_required), не в каталоге."""
    result = _parse([valid_row(**{field: ""})])
    assert result.valid_rows == 0
    assert result.skipped_rows == 1
    assert result.catalog.products == ()
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.reason == "missing_required"
    assert issue.row_number == 1


@pytest.mark.parametrize("field", ["id", "category", "name_ru", "name_uz"])
def test_whitespace_required_field_skips_row(field: str) -> None:
    """Whitespace-only обязательное поле трактуется как пустое -> пропуск."""
    result = _parse([valid_row(**{field: "   "})])
    assert result.skipped_rows == 1
    assert result.issues[0].reason == "missing_required"


def test_valid_and_broken_rows_mixed_counts() -> None:
    """Смесь: 1 валидная + 1 битая -> valid=1, skipped=1, row_number битой = её позиция."""
    rows = [valid_row(id="ok"), valid_row(id="", category="X")]
    result = _parse(rows)
    assert result.valid_rows == 1
    assert result.skipped_rows == 1
    assert result.catalog.products[0].id == "ok"
    assert result.issues[0].row_number == 2
    assert result.issues[0].reason == "missing_required"
```
  (Убери лишний alias `_vr`, если конфликтует — используй уже импортированный `valid_row` и добавь импорт `RowIssue`/`pytest` в шапку, если их там нет.)

- [ ] **Run & verify FAIL**: `pytest tests/data/test_parse.py -q -k "required or mixed"`
  Expected FAIL: `assert result.skipped_rows == 1` падает (`AssertionError: assert 0 == 1`) — P1-конвейер не отсеивает битые строки и не формирует issues.

- [ ] **Minimal CORRECT impl**: добавить отсев в `parse`. Заменить цикл per-row на проверку обязательных значений:
```python
_FATAL_FIELDS: Final[tuple[str, ...]] = ("id", "category", "name_ru", "name_uz")


def _is_battered(row: Mapping[str, str]) -> bool:
    """Строка фатально битая, если любое из id/category/name_ru/name_uz пусто/whitespace."""
    return any(not row.get(field, "").strip() for field in _FATAL_FIELDS)
```
  И в `parse` (тело цикла):
```python
    products: list[Product] = []
    issues: list[RowIssue] = []
    skipped = 0
    for index, row in enumerate(normalized):
        row_number = index + 1
        if _is_battered(row):
            skipped += 1
            issues.append(RowIssue(
                row_number=row_number,
                product_id=(row.get("id") or "").strip() or None,
                reason="missing_required",
                detail="empty id/category/name_ru/name_uz",
            ))
            continue
        products.append(_build_valid_product(row))

    catalog = Catalog.build(products)
    return ParseResult(
        catalog=catalog,
        issues=tuple(issues),
        valid_rows=len(products),
        skipped_rows=skipped,
    )
```

- [ ] **Run & verify PASS**: `pytest tests/data/test_parse.py tests/data/test_parse_schema.py -q` -> зелёные.
- [ ] **Quality green**: `ruff check` + `mypy --strict src/data/parse.py` -> 0.
- [ ] **Commit**: `feat: skip battered rows with missing required fields in parse`

---

### Task P3: новая ветвь — деградация цены (bad_number -> цена по запросу, товар жив)

НОВАЯ ветвь: невалидная цена (`parse_number -> None`) деградирует поле в `None` (цена по запросу), товар ОСТАЁТСЯ валидным, добавляется `RowIssue(bad_number)`. Тест падает на P2: P2 кладёт `None` в цену (т.к. `parse_number` уже вернёт None), но НЕ формирует `RowIssue(bad_number)` -> assert на issue провалится. (valid_row даёт валидные цены, поэтому P2 issues пуст.)

**Files:**
- Modify: `tests/data/test_parse.py`
- Modify: `src/data/parse.py`

- [ ] **Write failing test**:
```python
def test_bad_price_degrades_to_none_keeps_product() -> None:
    """Невалидная цена -> None (цена по запросу), товар жив, RowIssue(bad_number)."""
    result = _parse([valid_row(id="p", price_wholesale="abc")])
    assert result.valid_rows == 1
    assert result.skipped_rows == 0
    p = result.catalog.products[0]
    assert p.price_wholesale is None
    assert p.price_retail == Decimal("15000")
    reasons = [i.reason for i in result.issues]
    assert reasons.count("bad_number") == 1
    issue = next(i for i in result.issues if i.reason == "bad_number")
    assert issue.product_id == "p"
    assert issue.row_number == 1


def test_both_prices_bad_two_issues_product_alive() -> None:
    """Обе цены невалидны -> обе None, товар жив, два RowIssue(bad_number)."""
    result = _parse([valid_row(id="p", price_wholesale="", price_retail="xx")])
    p = result.catalog.products[0]
    assert p.price_wholesale is None
    assert p.price_retail is None
    assert [i.reason for i in result.issues].count("bad_number") == 2
    assert result.valid_rows == 1
```

- [ ] **Run & verify FAIL**: `pytest tests/data/test_parse.py -q -k "price"`
  Expected FAIL: `assert reasons.count("bad_number") == 1` падает (`AssertionError: assert 0 == 1`) — P2 не порождает issues для цен.

- [ ] **Minimal CORRECT impl**: ввести сбор per-row issues внутри сборки продукта. Изменить `_build_valid_product` -> возвращать `(Product, list[RowIssue])`. Сигнатура:
```python
def _build_product(row: Mapping[str, str], row_number: int) -> tuple[Product, list[RowIssue]]:
    """Собрать Product из валидной (не битой) строки + список деградационных RowIssue."""
    row_issues: list[RowIssue] = []
    product_id = row["id"].strip()

    price_w = parse_number(row["price_wholesale"])
    if price_w is None and row["price_wholesale"].strip():
        # непустая, но не распарсилась
        pass
    # bad_number фиксируется и для пустой, и для нераспознанной цены (поле обязательно по схеме)
    if price_w is None:
        row_issues.append(RowIssue(row_number=row_number, product_id=product_id,
                                   reason="bad_number", detail=f"price_wholesale={row['price_wholesale']!r}"))
    price_r = parse_number(row["price_retail"])
    if price_r is None:
        row_issues.append(RowIssue(row_number=row_number, product_id=product_id,
                                   reason="bad_number", detail=f"price_retail={row['price_retail']!r}"))

    product = Product(
        id=product_id,
        category=row["category"].strip(),
        subcategory=row["subcategory"].strip(),
        name_ru=row["name_ru"].strip(),
        name_uz=row["name_uz"].strip(),
        desc_ru=_opt(row, "desc_ru"),
        desc_uz=_opt(row, "desc_uz"),
        price_wholesale=price_w,
        price_retail=price_r,
        currency=row["currency"].strip(),
        packaging=_opt(row, "packaging"),
        photo=_opt(row, "photo"),
        is_active=bool(parse_bool(row["is_active"])),
    )
    return product, row_issues
```
  Удалить мёртвый `if price_w is None and ...: pass` (он не нужен — оставлен для иллюстрации; в финале НЕ коммитить bare `pass`). Корректная версия без мёртвого блока:
```python
def _build_product(row: Mapping[str, str], row_number: int) -> tuple[Product, list[RowIssue]]:
    """Собрать Product из не-битой строки + деградационные RowIssue (цены)."""
    row_issues: list[RowIssue] = []
    product_id = row["id"].strip()

    price_w = parse_number(row["price_wholesale"])
    if price_w is None:
        row_issues.append(RowIssue(row_number=row_number, product_id=product_id,
                                   reason="bad_number", detail=f"price_wholesale={row['price_wholesale']!r}"))
    price_r = parse_number(row["price_retail"])
    if price_r is None:
        row_issues.append(RowIssue(row_number=row_number, product_id=product_id,
                                   reason="bad_number", detail=f"price_retail={row['price_retail']!r}"))

    product = Product(
        id=product_id, category=row["category"].strip(), subcategory=row["subcategory"].strip(),
        name_ru=row["name_ru"].strip(), name_uz=row["name_uz"].strip(),
        desc_ru=_opt(row, "desc_ru"), desc_uz=_opt(row, "desc_uz"),
        price_wholesale=price_w, price_retail=price_r, currency=row["currency"].strip(),
        packaging=_opt(row, "packaging"), photo=_opt(row, "photo"),
        is_active=bool(parse_bool(row["is_active"])),
    )
    return product, row_issues
```
  И в `parse` заменить вызов:
```python
        product, row_issues = _build_product(row, row_number)
        products.append(product)
        issues.extend(row_issues)
```
  Удалить старую `_build_valid_product`.

- [ ] **Run & verify PASS**: `pytest tests/data/test_parse.py tests/data/test_parse_schema.py -q` -> зелёные (P1/P2 кейсы тоже: valid_row даёт валидные цены, issues пуст).
- [ ] **Quality green**: `ruff check` + `mypy --strict` -> 0.
- [ ] **Commit**: `feat: degrade invalid prices to price-on-request with bad_number issue`

---

### Task P4: новая ветвь — деградация currency (empty_currency / unrecognized_currency)

НОВАЯ ветвь: пустая currency -> `default_currency` + `RowIssue(empty_currency)`; непустая currency не из `allowed_currencies` -> `default_currency` + `RowIssue(unrecognized_currency)`; currency в allowed -> как есть, без issue. Тест падает на P3: P3 пишет `row["currency"].strip()` дословно (для пустой — `""`), issues по currency не порождает.

**Files:**
- Modify: `tests/data/test_parse.py`
- Modify: `src/data/parse.py`

- [ ] **Write failing test**:
```python
def test_empty_currency_uses_default_with_issue() -> None:
    """Пустая currency -> default_currency + RowIssue(empty_currency)."""
    result = _parse([valid_row(id="p", currency="")])
    p = result.catalog.products[0]
    assert p.currency == DEFAULT_CURRENCY
    assert [i.reason for i in result.issues] == ["empty_currency"]
    assert result.valid_rows == 1


def test_unrecognized_currency_uses_default_with_issue() -> None:
    """Непустая currency не из allowed -> default_currency + RowIssue(unrecognized_currency)."""
    result = _parse([valid_row(id="p", currency="EUR")])
    p = result.catalog.products[0]
    assert p.currency == DEFAULT_CURRENCY
    assert [i.reason for i in result.issues] == ["unrecognized_currency"]


def test_allowed_currency_kept_no_issue() -> None:
    """currency из allowed -> сохранена как есть, без issue."""
    result = _parse([valid_row(id="p", currency="USD")])
    assert result.catalog.products[0].currency == "USD"
    assert result.issues == ()
```
  (`DEFAULT_CURRENCY` уже импортирован из fixtures в шапке теста.)

- [ ] **Run & verify FAIL**: `pytest tests/data/test_parse.py -q -k "currency"`
  Expected FAIL: `test_empty_currency...` -> `assert '' == 'UZS'` (P3 кладёт пустую строку); `test_unrecognized...` -> `assert 'EUR' == 'UZS'`.

- [ ] **Minimal CORRECT impl**: `_build_product` принимает `default_currency` и `allowed_currencies`, добавляет резолв валюты:
```python
def _resolve_currency(
    raw: str, row_number: int, product_id: str,
    *, default_currency: str, allowed_currencies: frozenset[str],
) -> tuple[str, RowIssue | None]:
    """Разрешить валюту: пусто -> default+empty_currency; не из allowed -> default+unrecognized; иначе как есть."""
    value = raw.strip()
    if not value:
        return default_currency, RowIssue(
            row_number=row_number, product_id=product_id,
            reason="empty_currency", detail="empty currency -> default")
    if value not in allowed_currencies:
        return default_currency, RowIssue(
            row_number=row_number, product_id=product_id,
            reason="unrecognized_currency", detail=f"currency={value!r} not in allowed")
    return value, None
```
  В `_build_product` заменить `currency=row["currency"].strip()` на резолв и добавить issue в `row_issues`:
```python
    currency, currency_issue = _resolve_currency(
        row["currency"], row_number, product_id,
        default_currency=default_currency, allowed_currencies=allowed_currencies)
    if currency_issue is not None:
        row_issues.append(currency_issue)
```
  Прокинуть `default_currency`/`allowed_currencies` в сигнатуру `_build_product` и в вызов из `parse`.

- [ ] **Run & verify PASS**: `pytest tests/data/test_parse.py tests/data/test_parse_schema.py -q` -> зелёные.
- [ ] **Quality green**: `ruff check` + `mypy --strict` -> 0.
- [ ] **Commit**: `feat: degrade empty/unrecognized currency to default with issue`

---

### Task P5: новая ветвь — деградация subcategory (empty -> fallback)

НОВАЯ ветвь: пустая/whitespace `subcategory` -> `fallback_subcategory` + `RowIssue(empty_subcategory)`; непустая -> как есть. Тест падает на P4: P4 пишет `row["subcategory"].strip()` -> для пустой `""`, issue не порождает.

**Files:**
- Modify: `tests/data/test_parse.py`
- Modify: `src/data/parse.py`

- [ ] **Write failing test**:
```python
def test_empty_subcategory_uses_fallback_with_issue() -> None:
    """Пустая subcategory -> fallback_subcategory + RowIssue(empty_subcategory), товар жив."""
    result = _parse([valid_row(id="p", subcategory="")])
    p = result.catalog.products[0]
    assert p.subcategory == FALLBACK_SUBCATEGORY
    assert [i.reason for i in result.issues] == ["empty_subcategory"]
    assert result.valid_rows == 1


def test_whitespace_subcategory_uses_fallback() -> None:
    """Whitespace-only subcategory трактуется как пустая -> fallback."""
    result = _parse([valid_row(id="p", subcategory="   ")])
    assert result.catalog.products[0].subcategory == FALLBACK_SUBCATEGORY
    assert result.issues[0].reason == "empty_subcategory"


def test_nonempty_subcategory_kept() -> None:
    """Непустая subcategory -> как есть, без issue."""
    result = _parse([valid_row(id="p", subcategory="Соки")])
    assert result.catalog.products[0].subcategory == "Соки"
    assert result.issues == ()
```
  (`FALLBACK_SUBCATEGORY` уже импортирован из fixtures.)

- [ ] **Run & verify FAIL**: `pytest tests/data/test_parse.py -q -k "subcategory"`
  Expected FAIL: `assert '' == 'Прочее'` для пустой subcategory.

- [ ] **Minimal CORRECT impl**: в `_build_product` заменить `subcategory=row["subcategory"].strip()` на:
```python
    subcategory_raw = row["subcategory"].strip()
    if subcategory_raw:
        subcategory = subcategory_raw
    else:
        subcategory = fallback_subcategory
        row_issues.append(RowIssue(row_number=row_number, product_id=product_id,
                                   reason="empty_subcategory", detail="empty subcategory -> fallback"))
```
  Прокинуть `fallback_subcategory` в сигнатуру `_build_product` и вызов из `parse`.

- [ ] **Run & verify PASS**: `pytest tests/data/test_parse.py tests/data/test_parse_schema.py -q` -> зелёные.
- [ ] **Quality green**: `ruff check` + `mypy --strict` -> 0.
- [ ] **Commit**: `feat: fallback empty subcategory to default group with issue`

---

### Task P6: новая ветвь — деградация is_active (empty / unrecognized -> видим)

НОВАЯ ветвь: пустое `is_active` -> `True` (видим) + `RowIssue(empty_is_active)`; нераспознанное непустое (`parse_bool -> None`) -> `True` + `RowIssue(unrecognized_bool)`; явный bool -> его значение, без issue. Тест падает на P5: P5 делает `bool(parse_bool(...))` — для `None` даёт `False` (НЕ True!) и не порождает issue. Это реальный red на двух ветвях.

**Files:**
- Modify: `tests/data/test_parse.py`
- Modify: `src/data/parse.py`

- [ ] **Write failing test**:
```python
def test_empty_is_active_visible_with_issue() -> None:
    """Пустое is_active -> товар ВИДЕН (True) + RowIssue(empty_is_active)."""
    result = _parse([valid_row(id="p", is_active="")])
    p = result.catalog.products[0]
    assert p.is_active is True
    assert [i.reason for i in result.issues] == ["empty_is_active"]


def test_unrecognized_is_active_visible_with_issue() -> None:
    """Нераспознанное непустое is_active -> ВИДЕН (True) + RowIssue(unrecognized_bool)."""
    result = _parse([valid_row(id="p", is_active="maybe")])
    p = result.catalog.products[0]
    assert p.is_active is True
    assert [i.reason for i in result.issues] == ["unrecognized_bool"]


def test_explicit_false_is_active_hidden_no_issue() -> None:
    """Явный FALSE -> скрыт (is_active False), без issue."""
    result = _parse([valid_row(id="p", is_active="false")])
    assert result.catalog.products[0].is_active is False
    assert result.issues == ()


def test_explicit_true_is_active_visible_no_issue() -> None:
    """Явный TRUE -> видим, без issue."""
    result = _parse([valid_row(id="p", is_active="да")])
    assert result.catalog.products[0].is_active is True
    assert result.issues == ()
```

- [ ] **Run & verify FAIL**: `pytest tests/data/test_parse.py -q -k "is_active"`
  Expected FAIL: `test_empty_is_active...` и `test_unrecognized...` -> `assert False is True` (P5: `bool(None)` -> False) и `assert [...] == ['empty_is_active']` -> `assert [] == [...]`.

- [ ] **Minimal CORRECT impl**: вынести резолв is_active:
```python
def _resolve_is_active(raw: str, row_number: int, product_id: str) -> tuple[bool, RowIssue | None]:
    """Разрешить is_active: пусто -> True+empty_is_active; нераспозн -> True+unrecognized_bool; явный -> значение."""
    if not raw.strip():
        return True, RowIssue(row_number=row_number, product_id=product_id,
                              reason="empty_is_active", detail="empty is_active -> visible")
    parsed = parse_bool(raw)
    if parsed is None:
        return True, RowIssue(row_number=row_number, product_id=product_id,
                              reason="unrecognized_bool", detail=f"is_active={raw!r} -> visible")
    return parsed, None
```
  В `_build_product` заменить `is_active=bool(parse_bool(row["is_active"]))` на:
```python
    is_active, active_issue = _resolve_is_active(row["is_active"], row_number, product_id)
    if active_issue is not None:
        row_issues.append(active_issue)
```
  и `is_active=is_active` в конструкторе Product.

- [ ] **Run & verify PASS**: `pytest tests/data/test_parse.py tests/data/test_parse_schema.py -q` -> зелёные.
- [ ] **Quality green**: `ruff check` + `mypy --strict` -> 0.
- [ ] **Commit**: `feat: degrade empty/unrecognized is_active to visible with issue`

---

### Task P7: новая ветвь — dedup по id (первая ВАЛИДНАЯ wins; битые не участвуют)

НОВАЯ ветвь: среди ВАЛИДНЫХ (не битых) строк дубли по `id` -> первая валидная попадает в каталог, остальные -> `RowIssue(duplicate_id)`, не в каталоге. Битые дубликаты НЕ участвуют в dedup (они уже отсеяны как missing_required). Тест падает на P6: P6 кладёт все не-битые продукты в `products` (включая дубли) -> `Catalog.build` по контракту (`by_id` — Mapping) при дублях id перезатрёт/сломает, но `products` будет содержать 2 -> assert `valid_rows == 1` провалится (будет 2).

**Files:**
- Modify: `tests/data/test_parse.py`
- Modify: `src/data/parse.py`

- [ ] **Write failing test**:
```python
def test_duplicate_id_first_valid_wins() -> None:
    """Дубли по id среди валидных -> первая wins, остальные -> duplicate_id, не в каталоге."""
    rows = [valid_row(id="dup", name_ru="Первый"), valid_row(id="dup", name_ru="Второй")]
    result = _parse(rows)
    assert result.valid_rows == 1
    assert result.skipped_rows == 1
    assert len(result.catalog.products) == 1
    assert result.catalog.products[0].name_ru == "Первый"
    assert result.catalog.by_id["dup"].name_ru == "Первый"
    dup_issues = [i for i in result.issues if i.reason == "duplicate_id"]
    assert len(dup_issues) == 1
    assert dup_issues[0].row_number == 2
    assert dup_issues[0].product_id == "dup"


def test_battered_first_then_valid_dup_id_valid_wins() -> None:
    """Первая строка с этим id битая (пропущена), вторая валидна -> валидная wins, без duplicate_id."""
    rows = [valid_row(id="x", name_ru=""), valid_row(id="x", name_ru="Хороший")]
    result = _parse(rows)
    assert result.valid_rows == 1
    assert result.catalog.products[0].name_ru == "Хороший"
    reasons = sorted(i.reason for i in result.issues)
    assert "missing_required" in reasons
    assert "duplicate_id" not in reasons


def test_three_same_id_one_wins_two_dup() -> None:
    """Три валидные с одним id -> 1 wins, 2 duplicate_id."""
    rows = [valid_row(id="t"), valid_row(id="t"), valid_row(id="t")]
    result = _parse(rows)
    assert result.valid_rows == 1
    assert result.skipped_rows == 2
    assert [i.reason for i in result.issues].count("duplicate_id") == 2
```

- [ ] **Run & verify FAIL**: `pytest tests/data/test_parse.py -q -k "dup or wins"`
  Expected FAIL: `assert result.valid_rows == 1` падает (`AssertionError: assert 2 == 1`) — P6 не делает dedup, обе валидные строки попадают в products.

- [ ] **Minimal CORRECT impl**: в `parse` после сборки валидного продукта добавить dedup по `product.id`:
```python
    products: list[Product] = []
    issues: list[RowIssue] = []
    seen_ids: set[str] = set()
    skipped = 0
    for index, row in enumerate(normalized):
        row_number = index + 1
        if _is_battered(row):
            skipped += 1
            issues.append(RowIssue(
                row_number=row_number, product_id=(row.get("id") or "").strip() or None,
                reason="missing_required", detail="empty id/category/name_ru/name_uz"))
            continue
        product, row_issues = _build_product(
            row, row_number, default_currency=default_currency,
            fallback_subcategory=fallback_subcategory, allowed_currencies=allowed_currencies)
        if product.id in seen_ids:
            skipped += 1
            issues.append(RowIssue(
                row_number=row_number, product_id=product.id,
                reason="duplicate_id", detail=f"id={product.id!r} already seen"))
            continue
        seen_ids.add(product.id)
        products.append(product)
        issues.extend(row_issues)
```
  Важно: деградационные `row_issues` дубликата НЕ добавляются (товар не попал в каталог) — только `duplicate_id`. `skipped_rows = skipped` (битые + дубликаты).

- [ ] **Run & verify PASS**: `pytest tests/data/test_parse.py tests/data/test_parse_schema.py -q` -> зелёные.
- [ ] **Quality green**: `ruff check` + `mypy --strict` -> 0.
- [ ] **Commit**: `feat: dedup valid products by id keeping first occurrence`

---

### Task P8: интеграционный happy multi-row + порядок issues + финальный 100% coverage gate

Закрепляющий интеграционный тест (multi-row со смесью всех ветвей) + ВКЛЮЧЕНИЕ `--cov=src.data.parse --cov-fail-under=100` явным флагом команды (НЕ глобально в pyproject). Если coverage < 100 — дописать тесты недостающих ветвей (НЕ менять impl ради покрытия). Это не псевдо-red: цель — доказать, что все ветви конвейера покрыты и интеграция корректна.

**Files:**
- Modify: `tests/data/test_parse.py`

- [ ] **Write integration test**:
```python
def test_happy_multi_row_integration() -> None:
    """Смешанный лист: валидные + битая + bad_number + empty currency + dup -> корректные counts и каталог."""
    rows = [
        valid_row(id="a", category="C1", subcategory="S1"),
        valid_row(id="b", price_retail="abc"),                 # bad_number, жив
        valid_row(id="", category="C2"),                       # missing_required, пропуск
        valid_row(id="c", currency=""),                        # empty_currency, жив
        valid_row(id="a", name_ru="Дубль"),                    # duplicate_id, пропуск
        valid_row(id="d", subcategory="", is_active=""),       # empty_subcategory + empty_is_active, жив
    ]
    result = _parse(rows)
    assert result.valid_rows == 4
    assert result.skipped_rows == 2
    ids = [p.id for p in result.catalog.products]
    assert ids == ["a", "b", "c", "d"]
    reasons = sorted(i.reason for i in result.issues)
    assert "bad_number" in reasons
    assert "missing_required" in reasons
    assert "empty_currency" in reasons
    assert "duplicate_id" in reasons
    assert "empty_subcategory" in reasons
    assert "empty_is_active" in reasons
    # каталог иммутабелен и by_id согласован
    assert set(result.catalog.by_id.keys()) == {"a", "b", "c", "d"}
    assert result.catalog.by_id["a"].category == "C1"


def test_issue_row_numbers_are_1_based_data_index() -> None:
    """row_number == индекс строки данных + 1 (без заголовка)."""
    rows = [valid_row(id="ok"), valid_row(id="")]
    result = _parse(rows)
    assert result.issues[0].row_number == 2
```

- [ ] **Run & verify**: `pytest tests/data/test_parse.py tests/data/test_parse_schema.py -q` -> зелёные.
- [ ] **Run coverage gate (явным флагом)**: `pytest tests/data/test_parse.py tests/data/test_parse_schema.py --cov=src.data.parse --cov-report=term-missing --cov-fail-under=100 -q`
  Expected: `100%`, exit 0. Если есть Missing-строки -> дописать тест недостающей ветви (например, опциональная колонка отсутствует целиком, currency с пробелами, и т.п.), НЕ трогая impl. Повторить до 100%.
- [ ] **Quality green**: `ruff check src/data/parse.py tests/data/` + `mypy --strict src/data/parse.py tests/data/test_parse.py tests/data/test_parse_schema.py` -> 0.
- [ ] **Commit**: `test: cover parse pipeline branches to 100% with integration cases`


---

# Группа задач 7: src/data/cache.py

## Модуль: `src/data/cache.py` — CatalogCache (in-memory TTL-снимок, atomic swap, single-flight)

> **Для агентов:** ОБЯЗАТЕЛЬНЫЙ САБ-СКИЛЛ: используй superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans для реализации задача-за-задачей. Шаги — чекбоксы (`- [ ]`).

**Цель:** атомарный in-memory кэш каталога с порогом качества снимка и single-flight записью.

**Архитектура:** `CatalogCache` хранит одну ссылку на `Snapshot`. `get_snapshot()` синхронно возвращает текущую ссылку (без сети, без Lock — чтение хендлером). `try_swap(result)` под `asyncio.Lock` проверяет порог качества (доля битых ≤ 0.5 И valid ≥ `min_valid_rows`) и атомарно заменяет ссылку на новый `Snapshot`, иначе старый снимок остаётся жив.

**Стек:** Python 3.11+, `asyncio`, `datetime` (UTC), pytest + pytest-asyncio (strict), mypy --strict, ruff.

**Предусловия (scaffold Task 0 готов):** существуют `pyproject.toml`, `src/__init__.py`, `src/data/__init__.py`, `src/data/models.py` (с `Product`, `Catalog`, `ParseResult`, `Snapshot` — дословно по контракту), `tests/__init__.py`, `tests/data/__init__.py`, `tests/conftest.py`, установлены зависимости. Модуль НЕ создаёт инфраструктуру и НЕ трогает чужие файлы.

**Контракт типов (consumes из `src/data/models.py`):**
- `Product(id, category, subcategory, name_ru, name_uz, desc_ru, desc_uz, price_wholesale, price_retail, currency, packaging, photo, is_active)` — frozen.
- `Catalog(products: tuple[Product, ...], by_id: Mapping[str, Product])`; `Catalog.build(products) -> Catalog`.
- `ParseResult(catalog: Catalog, issues: tuple[RowIssue, ...], valid_rows: int, skipped_rows: int)`.
- `Snapshot(catalog: Catalog | None, updated_at: datetime | None, valid_rows: int, skipped_rows: int)` — frozen.

**Контракт (defines в `src/data/cache.py`):**
- `CatalogCache.__init__(self, *, min_valid_rows: int = 1) -> None` — старт `Snapshot(None, None, 0, 0)`.
- `CatalogCache.get_snapshot(self) -> Snapshot` — sync, без сети, без Lock.
- `async CatalogCache.try_swap(self, result: ParseResult, *, now: datetime | None = None) -> bool` — под `asyncio.Lock`. Порог: `skipped/(valid+skipped) > 0.5` ИЛИ `valid < min_valid_rows` → `False` (старый жив). Иначе атомарная замена ссылки на новый `Snapshot` (`now=None` → `datetime.now(timezone.utc)`) → `True`.

---

### Task 1: `CatalogCache.__init__` + `get_snapshot` (cold-start пустой снимок)

**Files:**
- Create: `src/data/cache.py`
- Test: `tests/data/test_cache.py`

- [ ] **Step 1: Написать падающий тест** (cold-start: кэш стартует с пустого `Snapshot(None, None, 0, 0)`)

```python
# tests/data/test_cache.py
"""Тесты CatalogCache: cold-start, atomic swap, порог качества, single-flight."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.data.cache import CatalogCache
from src.data.models import Catalog, ParseResult, Product


def _product(pid: str) -> Product:
    """Минимальный валидный Product для наполнения каталога в тестах."""
    return Product(
        id=pid,
        category="cat",
        subcategory="sub",
        name_ru="имя",
        name_uz="nom",
        desc_ru=None,
        desc_uz=None,
        price_wholesale=Decimal("100"),
        price_retail=Decimal("150"),
        currency="UZS",
        packaging=None,
        photo=None,
        is_active=True,
    )


def _result(*, valid: int, skipped: int) -> ParseResult:
    """ParseResult с `valid` валидными товарами и счётчиком `skipped` битых строк.

    issues для счётчиков несущественны — порог считается по valid_rows/skipped_rows.
    """
    products = tuple(_product(f"p{i}") for i in range(valid))
    return ParseResult(
        catalog=Catalog.build(products),
        issues=(),
        valid_rows=valid,
        skipped_rows=skipped,
    )


def test_cold_start_snapshot_is_empty() -> None:
    cache = CatalogCache()
    snap = cache.get_snapshot()
    assert snap.catalog is None
    assert snap.updated_at is None
    assert snap.valid_rows == 0
    assert snap.skipped_rows == 0


def test_get_snapshot_returns_same_reference_until_swap() -> None:
    cache = CatalogCache()
    assert cache.get_snapshot() is cache.get_snapshot()
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/data/test_cache.py::test_cold_start_snapshot_is_empty tests/data/test_cache.py::test_get_snapshot_returns_same_reference_until_swap -v`
Expected: FAIL с `ImportError: cannot import name 'CatalogCache' from 'src.data.cache'` (файл `src/data/cache.py` ещё пуст/без символа).

- [ ] **Step 3: Минимальная корректная реализация** (`__init__` + `get_snapshot`; пустой снимок — ровно по контракту)

```python
# src/data/cache.py
"""In-memory кэш каталога: атомарный снимок, порог качества, single-flight swap."""
from __future__ import annotations

from src.data.models import Snapshot

# Старт: cold-start пустой снимок (каталога ещё нет, см. контракт Snapshot).
_EMPTY_SNAPSHOT = Snapshot(catalog=None, updated_at=None, valid_rows=0, skipped_rows=0)


class CatalogCache:
    """Хранит единственную ссылку на актуальный Snapshot каталога.

    Чтение (get_snapshot) — синхронно, без сети и без Lock: хендлеры читают снимок
    напрямую. Запись (try_swap) — отдельная задача, появится в следующих шагах.
    """

    def __init__(self, *, min_valid_rows: int = 1) -> None:
        self._min_valid_rows = min_valid_rows
        self._snapshot: Snapshot = _EMPTY_SNAPSHOT

    def get_snapshot(self) -> Snapshot:
        """Текущий снимок. Без сети, без Lock — атомарное чтение ссылки."""
        return self._snapshot
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `pytest tests/data/test_cache.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: ruff + mypy зелёные**

Run: `ruff check src/data/cache.py tests/data/test_cache.py && ruff format --check src/data/cache.py tests/data/test_cache.py && mypy --strict src/data/cache.py tests/data/test_cache.py`
Expected: без ошибок (exit 0).

- [ ] **Step 6: Commit**

```bash
git add src/data/cache.py tests/data/test_cache.py
git commit -m "feat(cache): add CatalogCache cold-start snapshot and get_snapshot"
```

---

### Task 2: `try_swap` — atomic swap + порог качества (атомарная фича целиком)

> Порог — атомарная фича: реализуется ОДНОЙ задачей (happy swap + обе ветви reject). Lock здесь НЕ вводим — это ортогональная фича конкурентности (Task 3), её честный Red иначе исчезнет. Текущая реализация try_swap корректна для всех последовательных (неконкурентных) сценариев порога.

**Files:**
- Modify: `src/data/cache.py`
- Test: `tests/data/test_cache.py`

- [ ] **Step 1: Написать падающие тесты** (happy swap с переданным `now`; swap с `now=None` ставит UTC; reject по доле битых > 0.5; reject по `valid < min_valid_rows`, включая пустой каталог `valid=0`; граница доли ровно 0.5 — swap проходит)

```python
# tests/data/test_cache.py — ДОПИСАТЬ В КОНЕЦ ФАЙЛА (импорты datetime/timezone уже есть в шапке)


@pytest.mark.asyncio
async def test_try_swap_success_sets_snapshot_with_passed_now() -> None:
    cache = CatalogCache(min_valid_rows=1)
    now = datetime(2026, 5, 31, 12, 0, 0, tzinfo=timezone.utc)
    result = _result(valid=3, skipped=0)

    swapped = await cache.try_swap(result, now=now)

    assert swapped is True
    snap = cache.get_snapshot()
    assert snap.catalog is result.catalog
    assert snap.updated_at == now
    assert snap.valid_rows == 3
    assert snap.skipped_rows == 0


@pytest.mark.asyncio
async def test_try_swap_now_none_uses_utc() -> None:
    cache = CatalogCache(min_valid_rows=1)
    before = datetime.now(timezone.utc)

    swapped = await cache.try_swap(_result(valid=2, skipped=0))

    after = datetime.now(timezone.utc)
    assert swapped is True
    updated_at = cache.get_snapshot().updated_at
    assert updated_at is not None
    assert updated_at.tzinfo == timezone.utc
    assert before <= updated_at <= after


@pytest.mark.asyncio
async def test_try_swap_rejects_when_broken_ratio_above_half() -> None:
    cache = CatalogCache(min_valid_rows=1)
    # 2 валидных / 3 битых => 3/5 = 0.6 > 0.5 => reject, старый (пустой) снимок жив.
    swapped = await cache.try_swap(_result(valid=2, skipped=3))

    assert swapped is False
    snap = cache.get_snapshot()
    assert snap.catalog is None
    assert snap.updated_at is None


@pytest.mark.asyncio
async def test_try_swap_accepts_when_broken_ratio_exactly_half() -> None:
    cache = CatalogCache(min_valid_rows=1)
    # 2 валидных / 2 битых => 2/4 = 0.5, НЕ > 0.5 => swap проходит (граница включительно).
    swapped = await cache.try_swap(_result(valid=2, skipped=2))

    assert swapped is True
    assert cache.get_snapshot().valid_rows == 2


@pytest.mark.asyncio
async def test_try_swap_rejects_when_valid_below_min() -> None:
    cache = CatalogCache(min_valid_rows=5)
    # valid=4 < min=5 => reject даже при нулевой доле битых.
    swapped = await cache.try_swap(_result(valid=4, skipped=0))

    assert swapped is False
    assert cache.get_snapshot().catalog is None


@pytest.mark.asyncio
async def test_try_swap_rejects_empty_catalog() -> None:
    cache = CatalogCache(min_valid_rows=1)
    # valid=0 (пустой каталог) < min=1 => reject; деления на ноль нет.
    swapped = await cache.try_swap(_result(valid=0, skipped=0))

    assert swapped is False
    assert cache.get_snapshot().catalog is None


@pytest.mark.asyncio
async def test_try_swap_keeps_previous_snapshot_on_reject() -> None:
    cache = CatalogCache(min_valid_rows=1)
    good_now = datetime(2026, 5, 31, 10, 0, 0, tzinfo=timezone.utc)
    await cache.try_swap(_result(valid=5, skipped=0), now=good_now)

    # Плохой снимок: доля битых 0.75 => reject, прежний валидный снимок остаётся.
    swapped = await cache.try_swap(_result(valid=1, skipped=3))

    assert swapped is False
    snap = cache.get_snapshot()
    assert snap.valid_rows == 5
    assert snap.updated_at == good_now
```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

Run: `pytest tests/data/test_cache.py -v -k try_swap`
Expected: FAIL у всех try_swap-тестов с `AttributeError: 'CatalogCache' object has no attribute 'try_swap'` (метода ещё нет в `src/data/cache.py`).

- [ ] **Step 3: Минимальная корректная реализация** (полный порог обе ветви + atomic swap; без Lock — он в Task 3)

В `src/data/cache.py` дополнить импорты и добавить метод `try_swap`.

Заменить блок импортов:

```python
from __future__ import annotations

from src.data.models import Snapshot
```

на:

```python
from __future__ import annotations

from datetime import datetime, timezone

from src.data.models import ParseResult, Snapshot

# Максимальная доля битых строк, при которой снимок ещё принимается.
# Строго выше порога (доля битых > 0.5) — снимок отвергается целиком.
_MAX_BROKEN_RATIO = 0.5
```

Добавить метод в класс `CatalogCache` (после `get_snapshot`):

```python
    def _passes_threshold(self, result: ParseResult) -> bool:
        """Снимок принимается, если доля битых ≤ 0.5 И valid ≥ min_valid_rows.

        Пустой снимок (valid+skipped == 0, valid=0) не делится на ноль и
        отсекается условием valid < min_valid_rows (при min_valid_rows ≥ 1).
        """
        if result.valid_rows < self._min_valid_rows:
            return False
        total = result.valid_rows + result.skipped_rows
        if total == 0:
            # valid_rows == 0 при пустом снимке; прошёл проверку min выше только
            # если min_valid_rows == 0 — тогда пустой снимок допустим.
            return True
        broken_ratio = result.skipped_rows / total
        return broken_ratio <= _MAX_BROKEN_RATIO

    async def try_swap(
        self, result: ParseResult, *, now: datetime | None = None
    ) -> bool:
        """Поставить новый снимок, если он прошёл порог качества.

        Возвращает True при успешной замене, False — если порог не пройден
        (тогда прежний снимок остаётся в силе). Замена ссылки атомарна.
        """
        if not self._passes_threshold(result):
            return False
        stamp = now if now is not None else datetime.now(timezone.utc)
        self._snapshot = Snapshot(
            catalog=result.catalog,
            updated_at=stamp,
            valid_rows=result.valid_rows,
            skipped_rows=result.skipped_rows,
        )
        return True
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `pytest tests/data/test_cache.py -v`
Expected: PASS (все тесты, включая Task 1).

- [ ] **Step 5: ruff + mypy зелёные**

Run: `ruff check src/data/cache.py tests/data/test_cache.py && ruff format --check src/data/cache.py tests/data/test_cache.py && mypy --strict src/data/cache.py tests/data/test_cache.py`
Expected: без ошибок (exit 0).

- [ ] **Step 6: Commit**

```bash
git add src/data/cache.py tests/data/test_cache.py
git commit -m "feat(cache): add try_swap with quality threshold and atomic swap"
```

---

### Task 3: single-flight — сериализация конкурентных `try_swap` под `asyncio.Lock`

> Честный Red: `try_swap` из Task 2 НЕ держит Lock. Тест запускает N конкурентных `try_swap` через `asyncio.gather` с медленной критической секцией (через `asyncio.Event`/задержку внутри try_swap) и доказывает, что вторая корутина ждёт первую (сериализация). Без Lock параллельные входы перекрываются → тест падает. Затем добавляем Lock → PASS. Lock — ортогональная фича конкурентности, не дробление порога. Поломки кода ради Red нет: до фикса критсекция реально не сериализована.

**Files:**
- Modify: `src/data/cache.py`
- Test: `tests/data/test_cache.py`

- [ ] **Step 1: Написать падающий тест** (доказать сериализацию через наблюдаемое перекрытие критсекций)

Подход к доказательству без искусственной поломки: внедряем наблюдаемую задержку в критическую секцию через тестовый хук `_on_enter_critical` (async-callback, по умолчанию no-op), который вызывается ВНУТРИ критической секции `try_swap` после прохождения порога и до замены снимка. Хук считает «сколько корутин одновременно внутри секции». Под Lock максимум всегда 1; без Lock — больше 1, тест падает.

```python
# tests/data/test_cache.py — ДОПИСАТЬ В КОНЕЦ ФАЙЛА
import asyncio


@pytest.mark.asyncio
async def test_try_swap_is_single_flight_serialized() -> None:
    cache = CatalogCache(min_valid_rows=1)

    concurrent = 0
    max_concurrent = 0
    enter_gate = asyncio.Event()  # держит первую корутину внутри секции
    first_inside = asyncio.Event()  # сигнал, что кто-то уже в секции

    async def hook() -> None:
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        if not first_inside.is_set():
            # Первая вошедшая корутина застревает в секции, давая шанс второй
            # войти параллельно, ЕСЛИ сериализации (Lock) нет.
            first_inside.set()
            await enter_gate.wait()
        concurrent -= 1

    # Внедряем наблюдаемый хук в критическую секцию try_swap.
    cache._on_enter_critical = hook  # type: ignore[attr-defined]

    async def opener() -> bool:
        return await cache.try_swap(_result(valid=3, skipped=0))

    task_a = asyncio.create_task(opener())
    task_b = asyncio.create_task(opener())

    # Дать первой корутине войти в секцию и застрять на enter_gate.
    await first_inside.wait()
    # Дать второй корутине шанс войти (если Lock есть — она ждёт снаружи).
    await asyncio.sleep(0.05)
    # Отпустить первую — обе завершатся.
    enter_gate.set()

    results = await asyncio.gather(task_a, task_b)

    assert results == [True, True]
    # Под Lock одновременно внутри секции только одна корутина.
    assert max_concurrent == 1
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `pytest tests/data/test_cache.py::test_try_swap_is_single_flight_serialized -v`
Expected: FAIL с `AssertionError: assert 2 == 1` (без Lock обе корутины входят в критсекцию одновременно: `max_concurrent == 2`). Этот провал доказывает, что текущая `try_swap` не сериализована.

- [ ] **Step 3: Минимальная корректная реализация** (добавить `asyncio.Lock` + опциональный тестовый хук; критсекция — проверка порога + замена под Lock)

В `src/data/cache.py` обновить импорты, `__init__` и `try_swap`.

Заменить блок импортов на:

```python
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from src.data.models import ParseResult, Snapshot

# Максимальная доля битых строк, при которой снимок ещё принимается.
# Строго выше порога (доля битых > 0.5) — снимок отвергается целиком.
_MAX_BROKEN_RATIO = 0.5


async def _noop_critical() -> None:
    """Хук критической секции по умолчанию: ничего не делает.

    Подменяется в тестах для наблюдения за сериализацией single-flight.
    """
    return None
```

Заменить `__init__` на:

```python
    def __init__(self, *, min_valid_rows: int = 1) -> None:
        self._min_valid_rows = min_valid_rows
        self._snapshot: Snapshot = _EMPTY_SNAPSHOT
        # Single-flight: запись снимка сериализуется; чтение (get_snapshot) Lock не берёт.
        self._lock = asyncio.Lock()
        # Тестовый хук, вызываемый внутри критической секции. В проде — no-op.
        self._on_enter_critical: Callable[[], Awaitable[None]] = _noop_critical
```

Заменить `try_swap` на (тело теперь под `async with self._lock`, с вызовом хука внутри):

```python
    async def try_swap(
        self, result: ParseResult, *, now: datetime | None = None
    ) -> bool:
        """Поставить новый снимок, если он прошёл порог качества.

        Возвращает True при успешной замене, False — если порог не пройден
        (тогда прежний снимок остаётся в силе). Запись сериализована Lock
        (single-flight); замена ссылки атомарна.
        """
        async with self._lock:
            if not self._passes_threshold(result):
                return False
            await self._on_enter_critical()
            stamp = now if now is not None else datetime.now(timezone.utc)
            self._snapshot = Snapshot(
                catalog=result.catalog,
                updated_at=stamp,
                valid_rows=result.valid_rows,
                skipped_rows=result.skipped_rows,
            )
            return True
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `pytest tests/data/test_cache.py -v`
Expected: PASS (все тесты, включая single-flight: `max_concurrent == 1`).

- [ ] **Step 5: ruff + mypy зелёные**

Run: `ruff check src/data/cache.py tests/data/test_cache.py && ruff format --check src/data/cache.py tests/data/test_cache.py && mypy --strict src/data/cache.py tests/data/test_cache.py`
Expected: без ошибок (exit 0).

- [ ] **Step 6: Commit**

```bash
git add src/data/cache.py tests/data/test_cache.py
git commit -m "feat(cache): serialize try_swap under asyncio.Lock (single-flight)"
```

---

### Self-review (выполнено при составлении плана)

- **Покрытие контракта:** cold-start пустой снимок (Task 1); happy swap с переданным `now` и `now=None`→UTC, reject по доле битых > 0.5, граница 0.5 включительно, reject по `valid < min_valid_rows` включая пустой каталог `valid=0`, сохранение прежнего снимка при reject (Task 2); single-flight сериализация конкурентных `try_swap` без искусственной поломки Lock (Task 3). Все пункты контракта `cache.try_swap` из spec покрыты.
- **Честный Red:** Task 1 — `ImportError: cannot import name CatalogCache` из своего файла (scaffold готов). Task 2 — `AttributeError: try_swap` (метода нет). Task 3 — `AssertionError: 2 == 1` (без Lock секция не сериализована; поломки кода нет). Порог не раздроблён — реализован одной задачей.
- **Без плейсхолдеров:** весь код тестов и реализации показан целиком, без TBD/TODO/object-заглушек.
- **Согласованность типов:** `CatalogCache(min_valid_rows=...)`, `get_snapshot() -> Snapshot`, `try_swap(result, *, now=None) -> bool` совпадают между задачами и с контрактом. `ParseResult`/`Snapshot`/`Catalog`/`Product` импортируются из `src.data.models`.
- **mypy --strict / ruff:** каждый коммит зелёный; тестовый хук `_on_enter_critical` типизирован как `Callable[[], Awaitable[None]]`, подмена в тесте помечена `# type: ignore[attr-defined]` (доступ к приватному атрибуту через присваивание).


---

# Группа задач 8: src/data/refresh.py

Модуль `src/data/refresh.py` — фоновый refresh-loop. Зависимости (`FetchError`, `SchemaError`, `ParseResult`, `Snapshot`, `CatalogCache`) предполагаются готовыми (scaffold + предыдущие модули). Первый Red — `ImportError` конкретного символа `BackoffConfig` ИЗ `src/data/refresh.py`, а НЕ `No module named src`.

Импорты: `FetchError` из `src.data.fetch`; `SchemaError`, `ParseResult`, `Snapshot` из `src.data.models`; `CatalogCache` через `TYPE_CHECKING` (избегаем цикла импорта, runtime не нужен). `random.Random` и `Callable/Awaitable/Sequence/Mapping` из stdlib/typing.

Тестовые двойники (определяются в `tests/data/test_refresh.py`, переиспользуются между задачами):
- `MaxRng` — подкласс `random.Random` с `uniform(a, b) -> b` (детерминированный максимум джиттера: доказывает full-jitter cap без флака).
- `RecordingSleeper` — async-callable: пишет каждую переданную задержку в список `delays`, на N-м вызове бросает `asyncio.CancelledError` (выход из бесконечного цикла без реальных задержек).
- `FakeCache` — минимальный двойник: хранит `snapshot` (`Snapshot`), `swap_calls: list[ParseResult]`, `get_snapshot()` синхронный, `try_swap(result, *, now=None)` async, пишет в `swap_calls`, возвращает заранее заданный `bool` и при `True` обновляет `snapshot`.
- `make_parse_result(valid, skipped)` — фабрика `ParseResult` с пустым/непустым `Catalog` (через `Catalog.build([])`), нужными счётчиками `valid_rows`/`skipped_rows`, `issues=()`.

ВАЖНО (ЧЕКЛИСТ §2): каждая поздняя задача добавляет НОВУЮ ветвь, чей тест РЕАЛЬНО падает на узкой реализации предыдущей задачи. Задачи 1-2 — атомарные чистые функции/конфиг (один Red на отсутствие символа -> полная impl). Задачи 3+ — последовательное наращивание ветвей `run_refresh_loop`.

---

### Task R1: BackoffConfig + _compute_backoff_delay (full-jitter)

**Files:**
- Create: `src/data/refresh.py`
- Test: `tests/data/test_refresh.py`

Атомарная фича: frozen-конфиг + чистая функция джиттера. ОДНА задача (ЧЕКЛИСТ §2): все ветви (frozen, рост cap, потолок max_s, full-jitter через MaxRng) -> verify FAIL (символов нет) -> ПОЛНАЯ impl -> verify PASS.

- [ ] Write failing test — `tests/data/test_refresh.py`:
```python
"""Тесты refresh-loop: backoff-джиттер и фоновый цикл обновления."""
from __future__ import annotations

import asyncio
import dataclasses
import random

import pytest

from src.data.refresh import BackoffConfig, _compute_backoff_delay


def test_backoff_config_is_frozen() -> None:
    """BackoffConfig иммутабелен (frozen) — конфиг не мутируется в цикле."""
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)
    assert cfg.base_s == 2.0
    assert cfg.max_s == 60.0
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.base_s = 5.0  # type: ignore[misc]


def test_compute_delay_full_jitter_returns_cap_with_max_rng() -> None:
    """full-jitter: при rng.uniform->верхняя граница delay == cap = base*2**attempt."""

    class MaxRng(random.Random):
        def uniform(self, a: float, b: float) -> float:
            return b

    rng = MaxRng()
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)
    # attempt=0 -> cap=2*2**0=2.0; attempt=1 -> 4.0; attempt=2 -> 8.0
    assert _compute_backoff_delay(0, cfg, rng) == pytest.approx(2.0)
    assert _compute_backoff_delay(1, cfg, rng) == pytest.approx(4.0)
    assert _compute_backoff_delay(2, cfg, rng) == pytest.approx(8.0)


def test_compute_delay_grows_then_caps_at_max_s() -> None:
    """cap растёт экспоненциально, но не превышает max_s (потолок)."""

    class MaxRng(random.Random):
        def uniform(self, a: float, b: float) -> float:
            return b

    rng = MaxRng()
    cfg = BackoffConfig(base_s=2.0, max_s=10.0)
    # attempt=3 -> 2*8=16 > 10 -> потолок 10.0; attempt=10 -> тоже 10.0
    assert _compute_backoff_delay(3, cfg, rng) == pytest.approx(10.0)
    assert _compute_backoff_delay(10, cfg, rng) == pytest.approx(10.0)


def test_compute_delay_jitter_within_zero_and_cap() -> None:
    """full-jitter: реальный rng даёт значение в [0, cap]."""
    rng = random.Random(42)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)
    for attempt in range(5):
        cap = min(60.0, 2.0 * (2**attempt))
        delay = _compute_backoff_delay(attempt, cfg, rng)
        assert 0.0 <= delay <= cap
```

- [ ] Run & verify FAIL — `pytest tests/data/test_refresh.py -q`
  Expected: `ImportError: cannot import name 'BackoffConfig' from 'src.data.refresh'` (collection error — символов нет в твоём файле).

- [ ] Minimal CORRECT impl — `src/data/refresh.py` (полный, без заглушек):
```python
"""Фоновый refresh-loop: периодическое обновление каталога с backoff на cold-start."""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BackoffConfig:
    """Параметры экспоненциального backoff с full-jitter (cold-start)."""

    base_s: float
    max_s: float


def _compute_backoff_delay(
    attempt: int, backoff: BackoffConfig, rng: random.Random
) -> float:
    """Full-jitter задержка: равномерно в [0, cap], cap = min(max_s, base*2**attempt).

    attempt — 0-based номер попытки; rng инъектируется для детерминизма в тестах.
    """
    cap = min(backoff.max_s, backoff.base_s * (2**attempt))
    return rng.uniform(0.0, cap)
```

- [ ] Run & verify PASS — `pytest tests/data/test_refresh.py -q` (4 passed).
- [ ] ruff + mypy зелёные — `ruff check src/data/refresh.py tests/data/test_refresh.py && ruff format --check src/data/refresh.py tests/data/test_refresh.py && mypy --strict src/data/refresh.py`
- [ ] Commit — `git add src/data/refresh.py tests/data/test_refresh.py && git commit -m "feat: add BackoffConfig and full-jitter backoff delay"`

---

### Task R2: run_refresh_loop happy path (fetch -> parse -> swap -> sleep ttl)

**Files:**
- Modify: `src/data/refresh.py`
- Test: `tests/data/test_refresh.py`

Узкая корректная impl: только happy-ветвь (успешный fetch, успешный swap -> sleep на ttl). НЕ заглушка: реальный цикл, реальный вызов try_swap. Ветви ошибок добавят позже задачи R3+ (их тесты реально упадут на этой узкой версии).

- [ ] Write failing test — добавить в `tests/data/test_refresh.py` тестовые двойники + happy-тест:
```python
from collections.abc import Awaitable, Mapping, Sequence
from datetime import datetime, timezone

from src.data.fetch import FetchError
from src.data.models import Catalog, ParseResult, Snapshot
from src.data.refresh import run_refresh_loop


class RecordingSleeper:
    """async-sleeper: пишет задержки; на stop_after-м вызове бросает CancelledError."""

    def __init__(self, stop_after: int) -> None:
        self.delays: list[float] = []
        self._stop_after = stop_after

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
        if len(self.delays) >= self._stop_after:
            raise asyncio.CancelledError


class FakeCache:
    """Минимальный двойник CatalogCache: get_snapshot синхронно, try_swap пишет вызовы."""

    def __init__(self, snapshot: Snapshot, swap_returns: bool) -> None:
        self._snapshot = snapshot
        self._swap_returns = swap_returns
        self.swap_calls: list[ParseResult] = []

    def get_snapshot(self) -> Snapshot:
        return self._snapshot

    async def try_swap(
        self, result: ParseResult, *, now: datetime | None = None
    ) -> bool:
        self.swap_calls.append(result)
        if self._swap_returns:
            self._snapshot = Snapshot(
                catalog=result.catalog,
                updated_at=now or datetime.now(timezone.utc),
                valid_rows=result.valid_rows,
                skipped_rows=result.skipped_rows,
            )
        return self._swap_returns


def make_parse_result(valid: int, skipped: int) -> ParseResult:
    """Фабрика ParseResult с пустым Catalog и заданными счётчиками."""
    return ParseResult(
        catalog=Catalog.build([]),
        issues=(),
        valid_rows=valid,
        skipped_rows=skipped,
    )


def live_snapshot() -> Snapshot:
    """Снимок с непустым каталогом (live: catalog is not None)."""
    return Snapshot(
        catalog=Catalog.build([]),
        updated_at=datetime.now(timezone.utc),
        valid_rows=5,
        skipped_rows=0,
    )


def cold_snapshot() -> Snapshot:
    """Cold-start снимок: catalog is None."""
    return Snapshot(catalog=None, updated_at=None, valid_rows=0, skipped_rows=0)


@pytest.mark.asyncio
async def test_happy_fetch_parse_swap_then_sleep_ttl() -> None:
    """Happy: fetch -> parse -> try_swap(True) -> sleep(ttl). Цикл повторяется до cancel."""
    cache = FakeCache(live_snapshot(), swap_returns=True)
    fetch_calls = 0

    async def fetch_fn() -> list[dict[str, str]]:
        nonlocal fetch_calls
        fetch_calls += 1
        return [{"id": "1"}]

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        return make_parse_result(valid=3, skipped=0)

    sleeper = RecordingSleeper(stop_after=2)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache, fetch_fn, parse_fn,
            ttl_seconds=300.0, backoff=cfg, sleeper=sleeper,
        )

    assert len(cache.swap_calls) >= 1
    assert sleeper.delays[0] == pytest.approx(300.0)  # после успешного swap -> ttl
    assert fetch_calls >= 1
```

- [ ] Run & verify FAIL — `pytest tests/data/test_refresh.py::test_happy_fetch_parse_swap_then_sleep_ttl -q`
  Expected: `ImportError: cannot import name 'run_refresh_loop' from 'src.data.refresh'` (символа `run_refresh_loop` ещё нет).

- [ ] Minimal CORRECT impl — добавить в `src/data/refresh.py`. Импорты + узкий happy-цикл (только успешный путь; ошибки НЕ обрабатываются — добавится в R3+):
```python
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.data.fetch import FetchError
from src.data.models import ParseResult, SchemaError

if TYPE_CHECKING:
    from src.data.cache import CatalogCache

logger = logging.getLogger(__name__)


async def run_refresh_loop(
    cache: CatalogCache,
    fetch_fn: Callable[[], Awaitable[list[dict[str, str]]]],
    parse_fn: Callable[[Sequence[Mapping[str, str]]], ParseResult],
    ttl_seconds: float,
    backoff: BackoffConfig,
    *,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    rng: random.Random | None = None,
) -> None:
    """Фоновый цикл обновления каталога.

    happy: fetch -> parse -> try_swap -> sleep(ttl). На этом шаге обрабатывается
    только успешный путь; ветви ошибок добавляются в последующих задачах.
    """
    rng = rng if rng is not None else random.Random()
    while True:
        started = time.monotonic()
        rows = await fetch_fn()
        result = parse_fn(rows)
        swapped = await cache.try_swap(result)
        if swapped:
            duration_ms = (time.monotonic() - started) * 1000.0
            logger.info(
                "refresh_done",
                extra={
                    "rows_total": result.valid_rows + result.skipped_rows,
                    "valid": result.valid_rows,
                    "skipped": result.skipped_rows,
                    "duration_ms": duration_ms,
                    "snapshot_age_s": 0.0,
                    "schema_ok": True,
                },
            )
        await sleeper(ttl_seconds)
```
  Заметки по контракту: `FetchError`, `SchemaError`, `datetime`/`timezone` импортированы заранее (используются в R3+); чтобы ruff не ругался на неиспользуемые в R2, обработка ошибок добавляется в R3 в той же сессии — НО для зелёного ruff на ЭТОМ коммите временный неиспользуемый импорт недопустим (ЧЕКЛИСТ §3). Поэтому в R2 импортировать ТОЛЬКО фактически используемое: `asyncio, logging, time, Awaitable/Callable/Mapping/Sequence, datetime/timezone` (timezone/datetime пока не нужны в happy — НЕ импортировать), `TYPE_CHECKING`, `ParseResult`. `FetchError`/`SchemaError`/`datetime`/`timezone` добавляются в R3/R4, когда реально используются. Итоговый R2-импортный набор: `asyncio, logging, time`, `from collections.abc import Awaitable, Callable, Mapping, Sequence`, `from typing import TYPE_CHECKING`, `from src.data.models import ParseResult`, TYPE_CHECKING-блок с `CatalogCache`.

- [ ] Run & verify PASS — `pytest tests/data/test_refresh.py -q` (5 passed).
- [ ] ruff + mypy зелёные — `ruff check src/data/refresh.py tests/data/test_refresh.py && ruff format --check src/data/refresh.py tests/data/test_refresh.py && mypy --strict src/data/refresh.py`
- [ ] Commit — `git commit -am "feat: add run_refresh_loop happy path (fetch-parse-swap-ttl)"`

---

### Task R3: transient FetchError -> cold-start backoff растёт / live keeps ttl

**Files:**
- Modify: `src/data/refresh.py`
- Test: `tests/data/test_refresh.py`

НОВАЯ ветвь: `try/except FetchError`. Тест cold-start backoff РЕАЛЬНО падает на R2 (там нет except -> FetchError пробрасывается из первого же fetch, никакого роста задержек). Узкая impl R2 не умеет ловить transient.

- [ ] Write failing test — добавить:
```python
@pytest.mark.asyncio
async def test_transient_cold_start_backoff_grows() -> None:
    """Cold-start (catalog is None) + transient FetchError -> растущий backoff-джиттер."""

    class MaxRng(random.Random):
        def uniform(self, a: float, b: float) -> float:
            return b

    cache = FakeCache(cold_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        raise FetchError("503 transient", transient=True)

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise AssertionError("parse не должен вызываться при фейле fetch")

    sleeper = RecordingSleeper(stop_after=3)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache, fetch_fn, parse_fn,
            ttl_seconds=300.0, backoff=cfg, sleeper=sleeper, rng=MaxRng(),
        )

    # full-jitter cap при MaxRng: attempt 0,1,2 -> 2,4,8 (растёт)
    assert sleeper.delays == [pytest.approx(2.0), pytest.approx(4.0), pytest.approx(8.0)]
    assert cache.swap_calls == []  # swap не звали — fetch упал


@pytest.mark.asyncio
async def test_transient_live_keeps_ttl() -> None:
    """Live (catalog не None) + transient FetchError -> задержка == ttl (не backoff)."""
    cache = FakeCache(live_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        raise FetchError("503 transient", transient=True)

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise AssertionError("parse не должен вызываться")

    sleeper = RecordingSleeper(stop_after=2)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache, fetch_fn, parse_fn,
            ttl_seconds=300.0, backoff=cfg, sleeper=sleeper,
        )

    assert sleeper.delays == [pytest.approx(300.0), pytest.approx(300.0)]
```

- [ ] Run & verify FAIL — `pytest tests/data/test_refresh.py::test_transient_cold_start_backoff_grows tests/data/test_refresh.py::test_transient_live_keeps_ttl -q`
  Expected: `FetchError: 503 transient` пробрасывается из `run_refresh_loop` (нет except) -> тест падает не на ассерте, а на необработанном исключении.

- [ ] Minimal CORRECT impl — добавить импорт `FetchError` и `try/except FetchError` с веткой transient + счётчик `attempt` для cold-start:
```python
from src.data.fetch import FetchError  # добавить к импортам
```
  Тело цикла: обернуть fetch+parse+swap в `try`, после `except FetchError as exc:` — ветка transient (cold: `_compute_backoff_delay(attempt, backoff, rng)` + `attempt += 1`; live: `ttl_seconds`), затем `continue`/`sleeper`. `attempt` инициализировать перед `while True`, сбрасывать в 0 после успешного swap. Live-определение: `cache.get_snapshot().catalog is not None`. non-transient пока НЕ различается (упадёт в R4).
  Полный фрагмент тела:
```python
    rng = rng if rng is not None else random.Random()
    attempt = 0
    while True:
        started = time.monotonic()
        try:
            rows = await fetch_fn()
            result = parse_fn(rows)
        except FetchError:
            # transient: cold-start (нет снимка) -> backoff; live -> держим ttl
            if cache.get_snapshot().catalog is None:
                delay = _compute_backoff_delay(attempt, backoff, rng)
                attempt += 1
            else:
                delay = ttl_seconds
            await sleeper(delay)
            continue
        swapped = await cache.try_swap(result)
        if swapped:
            attempt = 0
            duration_ms = (time.monotonic() - started) * 1000.0
            logger.info("refresh_done", extra={...})  # как в R2
        await sleeper(ttl_seconds)
```

- [ ] Run & verify PASS — `pytest tests/data/test_refresh.py -q` (7 passed).
- [ ] ruff + mypy зелёные.
- [ ] Commit — `git commit -am "feat: handle transient FetchError with cold-start backoff and live ttl"`

---

### Task R4: non-transient FetchError пробрасывается + 429 retry_after уважается

**Files:**
- Modify: `src/data/refresh.py`
- Test: `tests/data/test_refresh.py`

Две НОВЫЕ ветви на `transient`/`retry_after`-флагах. R3 ловит ВСЕ FetchError одинаково -> non-transient НЕ пробрасывается (тест raises упадёт), а retry_after игнорируется (тест на delay==retry_after упадёт: R3 даёт джиттер/ttl). Обе ветви реально не покрыты R3.

- [ ] Write failing test — добавить:
```python
@pytest.mark.asyncio
async def test_non_transient_fetch_error_propagates() -> None:
    """non-transient FetchError (401/битый creds) -> НЕ ловится, поднимается наружу (main: exit 1)."""
    cache = FakeCache(cold_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        raise FetchError("401 unauthorized", transient=False)

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise AssertionError("не вызывается")

    sleeper = RecordingSleeper(stop_after=99)  # не должен сработать
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(FetchError) as ei:
        await run_refresh_loop(
            cache, fetch_fn, parse_fn,
            ttl_seconds=300.0, backoff=cfg, sleeper=sleeper,
        )
    assert ei.value.transient is False
    assert sleeper.delays == []  # ни одной задержки — сразу проброс


@pytest.mark.asyncio
async def test_429_retry_after_is_respected_over_jitter() -> None:
    """429: transient + retry_after задан -> delay == retry_after (НЕ джиттер-backoff)."""

    class MaxRng(random.Random):
        def uniform(self, a: float, b: float) -> float:
            return b  # если бы взяли джиттер — было бы != 7.5

    cache = FakeCache(cold_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        raise FetchError("429 rate limited", transient=True, retry_after=7.5)

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise AssertionError("не вызывается")

    sleeper = RecordingSleeper(stop_after=2)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache, fetch_fn, parse_fn,
            ttl_seconds=300.0, backoff=cfg, sleeper=sleeper, rng=MaxRng(),
        )

    assert sleeper.delays == [pytest.approx(7.5), pytest.approx(7.5)]
```

- [ ] Run & verify FAIL — `pytest tests/data/test_refresh.py::test_non_transient_fetch_error_propagates tests/data/test_refresh.py::test_429_retry_after_is_respected_over_jitter -q`
  Expected: первый — `Failed: DID NOT RAISE <class FetchError>` (R3 проглотил non-transient и ушёл в backoff/sleep -> CancelledError или зависание на ассерте delays); второй — `assert [2.0, 2.0] == [7.5, 7.5]` (R3 даёт джиттер cap=2.0, а не retry_after).

- [ ] Minimal CORRECT impl — расширить `except FetchError as exc:`:
```python
        except FetchError as exc:
            if not exc.transient:
                raise  # non-transient: main ловит -> error + exit(1)
            if cache.get_snapshot().catalog is None:
                if exc.retry_after is not None:
                    delay = exc.retry_after  # 429: уважаем заголовок Retry-After
                else:
                    delay = _compute_backoff_delay(attempt, backoff, rng)
                    attempt += 1
            else:
                delay = ttl_seconds
            await sleeper(delay)
            continue
```
  Уточнение ветвления retry_after: по контракту 429 -> уважать retry_after на cold-start (backoff-замена). На live transient -> ttl (retry_after не нужен, каталог жив). attempt инкрементируется только в джиттер-ветке (retry_after не «попытка backoff»).

- [ ] Run & verify PASS — `pytest tests/data/test_refresh.py -q` (9 passed).
- [ ] ruff + mypy зелёные.
- [ ] Commit — `git commit -am "feat: propagate non-transient FetchError and respect 429 retry_after"`

---

### Task R5: SchemaError -> live keep+ttl (swap не зван) / cold backoff

**Files:**
- Modify: `src/data/refresh.py`
- Test: `tests/data/test_refresh.py`

НОВАЯ ветвь `except SchemaError`. R4 не ловит SchemaError -> она пробрасывается из `parse_fn` -> тест (ожидающий keep+ttl, swap не зван) реально падает на необработанном SchemaError.

- [ ] Write failing test — добавить:
```python
@pytest.mark.asyncio
async def test_schema_error_live_keeps_snapshot_and_sleeps_ttl() -> None:
    """SchemaError при живом каталоге -> снимок держим, try_swap НЕ зван, sleep(ttl)."""
    cache = FakeCache(live_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        return [{"name_ru": "x"}]  # нет required колонки -> parse бросит SchemaError

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise SchemaError("missing required column: id")

    sleeper = RecordingSleeper(stop_after=2)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache, fetch_fn, parse_fn,
            ttl_seconds=300.0, backoff=cfg, sleeper=sleeper,
        )

    assert cache.swap_calls == []  # частичный/битый снимок в кэш не кладём
    assert sleeper.delays == [pytest.approx(300.0), pytest.approx(300.0)]


@pytest.mark.asyncio
async def test_schema_error_cold_uses_backoff() -> None:
    """SchemaError на cold-start (нет снимка) -> backoff (как transient cold)."""

    class MaxRng(random.Random):
        def uniform(self, a: float, b: float) -> float:
            return b

    cache = FakeCache(cold_snapshot(), swap_returns=False)

    async def fetch_fn() -> list[dict[str, str]]:
        return [{"name_ru": "x"}]

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise SchemaError("missing required column: id")

    sleeper = RecordingSleeper(stop_after=2)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache, fetch_fn, parse_fn,
            ttl_seconds=300.0, backoff=cfg, sleeper=sleeper, rng=MaxRng(),
        )

    assert cache.swap_calls == []
    assert sleeper.delays == [pytest.approx(2.0), pytest.approx(4.0)]
```

- [ ] Run & verify FAIL — `pytest tests/data/test_refresh.py::test_schema_error_live_keeps_snapshot_and_sleeps_ttl tests/data/test_refresh.py::test_schema_error_cold_uses_backoff -q`
  Expected: `SchemaError: missing required column: id` пробрасывается из `run_refresh_loop` (нет `except SchemaError`).

- [ ] Minimal CORRECT impl — добавить импорт `SchemaError` и отдельный `except SchemaError` ПОСЛЕ `except FetchError` (порядок: FetchError, SchemaError; CancelledError будет ВЫШЕ в R6):
```python
from src.data.models import ParseResult, SchemaError  # расширить импорт
```
  Ветка:
```python
        except SchemaError:
            # битая схема: частичный снимок не кладём. live -> keep+ttl; cold -> backoff
            if cache.get_snapshot().catalog is None:
                delay = _compute_backoff_delay(attempt, backoff, rng)
                attempt += 1
            else:
                delay = ttl_seconds
            await sleeper(delay)
            continue
```

- [ ] Run & verify PASS — `pytest tests/data/test_refresh.py -q` (11 passed).
- [ ] ruff + mypy зелёные.
- [ ] Commit — `git commit -am "feat: handle SchemaError with live keep-ttl and cold backoff"`

---

### Task R6: CancelledError пробрасывается (except ВЫШЕ FetchError)

**Files:**
- Modify: `src/data/refresh.py`
- Test: `tests/data/test_refresh.py`

Контракт: `asyncio.CancelledError` должен пробрасываться, его `except` стоит ВЫШЕ `except FetchError`. Риск регрессии: если `fetch_fn` бросит `CancelledError` (отмена во время I/O), а `except FetchError` стоит первым — CancelledError НЕ наследует FetchError, так что в R5 она и так пробрасывается из тела `try`. НО нужен явный тест-инвариант + явный `except asyncio.CancelledError: raise` ПЕРЕД `except FetchError`, чтобы будущие правки (расширение `except (FetchError, ...)`) не проглотили отмену. Тест РЕАЛЬНО проверяет, что отмена из fetch_fn не уходит в backoff.

Honesty note: на R5 этот тест может уже проходить (CancelledError не ловится FetchError-except). Это НЕ псевдо-red: задача добавляет ЯВНЫЙ guard `except asyncio.CancelledError: raise` как защиту инварианта порядка except + регресс-тест. Если на R5 тест зелёный — это фиксируется в шаге verify, и impl-шаг добавляет guard + комментарий-инвариант (защита от будущей регрессии), тест остаётся как контрактный. ЧЕКЛИСТ §2 допускает закрепляющий тест, ЕСЛИ он помечен честно и не выдаётся за red-green. Поэтому ниже — verify ожидает PASS уже до impl, и это указано прямо.

- [ ] Write contract test — добавить:
```python
@pytest.mark.asyncio
async def test_cancelled_error_from_fetch_propagates() -> None:
    """CancelledError (отмена во время fetch) пробрасывается, НЕ уходит в backoff."""
    cache = FakeCache(cold_snapshot(), swap_returns=False)
    fetch_calls = 0

    async def fetch_fn() -> list[dict[str, str]]:
        nonlocal fetch_calls
        fetch_calls += 1
        raise asyncio.CancelledError

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        raise AssertionError("не вызывается")

    sleeper = RecordingSleeper(stop_after=99)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with pytest.raises(asyncio.CancelledError):
        await run_refresh_loop(
            cache, fetch_fn, parse_fn,
            ttl_seconds=300.0, backoff=cfg, sleeper=sleeper,
        )

    assert fetch_calls == 1  # отмена на первом fetch, без повторов
    assert sleeper.delays == []  # backoff не сработал
```

- [ ] Run & verify — `pytest tests/data/test_refresh.py::test_cancelled_error_from_fetch_propagates -q`
  Expected на R5-коде: **PASS** (CancelledError не ловится FetchError-except, пробрасывается). Это контрактный/закрепляющий тест инварианта, помечен честно — НЕ выдаётся за red-green. Если бы был FAIL — баг в порядке except.

- [ ] Minimal impl — добавить ЯВНЫЙ guard ПЕРЕД `except FetchError` (защита инварианта порядка + читаемость намерения):
```python
        except asyncio.CancelledError:
            raise  # отмена refresh-task при shutdown — пробрасываем (except ВЫШЕ FetchError)
        except FetchError as exc:
            ...
```
  Комментарий фиксирует инвариант: CancelledError ловится первой и сразу re-raise, чтобы расширение нижних except не проглотило отмену.

- [ ] Run & verify PASS — `pytest tests/data/test_refresh.py -q` (12 passed).
- [ ] ruff + mypy зелёные.
- [ ] Commit — `git commit -am "feat: re-raise CancelledError above FetchError handler"`

---

### Task R7: refresh_done логируется в caplog с обязательными полями

**Files:**
- Modify: `src/data/refresh.py`
- Test: `tests/data/test_refresh.py`

Контракт: после УСПЕШНОГО swap — `logger.info("refresh_done", extra=...)` с полями `rows_total, valid, skipped, duration_ms, snapshot_age_s, schema_ok=True`. R2 уже пишет лог, но `snapshot_age_s` захардкожен 0.0 и поле НЕ проверялось тестом. НОВАЯ проверяемая ветвь: `snapshot_age_s` вычисляется из `updated_at` нового снимка (age = now - updated_at). Тест на корректный `snapshot_age_s` РЕАЛЬНО падает на R2 (там 0.0 жёстко) — это честный red для уточнённой логики.

Уточнение: чтобы `snapshot_age_s` был осмыслен и детерминирован, после успешного `try_swap` читаем `cache.get_snapshot()` и берём его `updated_at`; age = `(datetime.now(timezone.utc) - updated_at).total_seconds()`. FakeCache при swap=True выставляет `updated_at` (см. R2 двойник). Для детерминизма тест проверяет НАЛИЧИЕ всех полей и `schema_ok is True`, `snapshot_age_s >= 0.0` (а не точное значение — зависит от now).

- [ ] Write failing test — добавить:
```python
@pytest.mark.asyncio
async def test_refresh_done_logged_with_required_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """После успешного swap логируется refresh_done со всеми полями summary."""
    import logging as _logging

    cache = FakeCache(cold_snapshot(), swap_returns=True)

    async def fetch_fn() -> list[dict[str, str]]:
        return [{"id": "1"}]

    def parse_fn(rows: Sequence[Mapping[str, str]]) -> ParseResult:
        return make_parse_result(valid=7, skipped=2)

    sleeper = RecordingSleeper(stop_after=1)
    cfg = BackoffConfig(base_s=2.0, max_s=60.0)

    with caplog.at_level(_logging.INFO, logger="src.data.refresh"):
        with pytest.raises(asyncio.CancelledError):
            await run_refresh_loop(
                cache, fetch_fn, parse_fn,
                ttl_seconds=300.0, backoff=cfg, sleeper=sleeper,
            )

    recs = [r for r in caplog.records if r.message == "refresh_done"]
    assert len(recs) == 1
    rec = recs[0]
    assert rec.rows_total == 9
    assert rec.valid == 7
    assert rec.skipped == 2
    assert rec.schema_ok is True
    assert isinstance(rec.duration_ms, float)
    assert rec.snapshot_age_s >= 0.0
```

- [ ] Run & verify FAIL — `pytest tests/data/test_refresh.py::test_refresh_done_logged_with_required_fields -q`
  Expected на R6-коде: если `snapshot_age_s` вычисляется из `updated_at`, а R6/R2 пишет `0.0` без чтения снимка — тест на `snapshot_age_s >= 0.0` пройдёт случайно (0.0 >= 0.0). Чтобы red был ЧЕСТНЫМ: тест дополнительно проверяет `rec.rows_total == 9` (R2 уже даёт valid+skipped=9 -> может пройти). РИСК псевдо-green. РЕШЕНИЕ: на R7 убедиться, что R2-лог писал `snapshot_age_s: 0.0` БЕЗ опоры на снимок. Если все поля совпадают и тест зелёный на R6 — это закрепляющий тест (честно помечен), а impl-шаг УТОЧНЯЕТ `snapshot_age_s` на вычисление из `updated_at` нового снимка (поведенческое улучшение, ранее 0.0). Verify ниже фиксирует фактический результат запуска.
  Фактический Expected: тест проверяет точное `rows_total==9` (R2 даёт `result.valid_rows+result.skipped_rows` = 7+2 = 9 -> совпадает) и `snapshot_age_s>=0.0` (R2 даёт 0.0 -> совпадает) => **на R6 тест PASS**. Значит это контрактный тест полей лога, не red-green. Помечаю честно: если PASS — фиксируем как закрепление контракта полей; impl-шаг заменяет хардкод `0.0` на вычисление из `updated_at`.

- [ ] Minimal impl — заменить `snapshot_age_s: 0.0` на вычисление из нового снимка:
```python
        swapped = await cache.try_swap(result)
        if swapped:
            attempt = 0
            snap = cache.get_snapshot()
            now = datetime.now(timezone.utc)
            age_s = (
                (now - snap.updated_at).total_seconds()
                if snap.updated_at is not None
                else 0.0
            )
            duration_ms = (time.monotonic() - started) * 1000.0
            logger.info(
                "refresh_done",
                extra={
                    "rows_total": result.valid_rows + result.skipped_rows,
                    "valid": result.valid_rows,
                    "skipped": result.skipped_rows,
                    "duration_ms": duration_ms,
                    "snapshot_age_s": age_s,
                    "schema_ok": True,
                },
            )
```
  Добавить импорт `from datetime import datetime, timezone` (теперь реально используется -> ruff зелёный).
  Honesty (ЧЕКЛИСТ §2): этот тест — контрактная фиксация полей лога; impl-шаг улучшает `snapshot_age_s` с хардкода на вычисление. Помечено явно, не выдаётся за искусственный red.

- [ ] Run & verify PASS — `pytest tests/data/test_refresh.py -q` (13 passed).
- [ ] ruff + mypy зелёные — `ruff check src/data/refresh.py tests/data/test_refresh.py && ruff format --check src/data/refresh.py tests/data/test_refresh.py && mypy --strict src/data/refresh.py`
- [ ] Commit — `git commit -am "feat: compute snapshot_age_s from updated_at in refresh_done log"`

---

### Финальная сверка контракта (после R7)

- [ ] Полный прогон — `pytest tests/data/test_refresh.py -q` (13 passed) + `ruff check src tests && mypy --strict src`.
- [ ] Сверка с контрактом: `BackoffConfig(base_s, max_s)` frozen+slots; `_compute_backoff_delay` full-jitter; `run_refresh_loop` сигнатура дословно (`cache, fetch_fn, parse_fn, ttl_seconds, backoff, *, sleeper=asyncio.sleep, rng=None`); transient cold->backoff/429 retry_after, live->ttl; non-transient->raise; SchemaError live->keep+ttl/cold->backoff; CancelledError->raise (выше FetchError); refresh_done в логе с 6 полями. Заглушек чужих модулей нет; импорт `CatalogCache` под TYPE_CHECKING.