# План реализации: слой `infra` (деплой + единый гейт качества)

> Четвёртый, заключительный план серии: data → services → bot → **infra**.
> Цель — выполнить DoD брифа §8: «бот запускается одной командой (`docker compose up` / `python -m src.main`)»,
> README с инструкциями, `.env.example` со всеми переменными, единый гейт качества и CI.

**Goal:** Превратить готовое приложение (`src/main.py`) в разворачиваемый и поддерживаемый продукт:
Dockerfile (non-root, реакция на SIGTERM), docker-compose (read-only mount секрета), README (получение SA,
расшаривание таблицы, шаблон колонок 1-в-1, запуск), финализация `.env.example`, единый гейт `Makefile`
(lint → format → typecheck → test), pre-commit и CI (GitHub Actions). Полная реализация webhook — НЕ в
охвате (polling — дефолт деплоя; webhook остаётся каркасом с `NotImplementedError`, см. ADR 0008).

**Контекст:** Python ≥3.11, единый гейт §10 дизайна = `ruff check` → `ruff format --check` →
`mypy --strict src` → `pytest`. Секреты: `.env` и `*service-account*.json` уже в `.gitignore`. `main.py`
ловит SIGTERM/SIGINT и гасит refresh-task + сессию. polling — строго одна реплика (иначе 409).

---

# Группа 1: Makefile (единый гейт)

Цель: одна команда `make check` = весь гейт; отдельные таргеты для разработки.

- [ ] **Create `Makefile`** с таргетами (`.PHONY`): `install` (`pip install -e ".[dev]"`),
  `lint` (`ruff check .`), `format` (`ruff format .`), `format-check` (`ruff format --check .`),
  `typecheck` (`mypy --strict src`), `test` (`pytest -q`), `cov` (`pytest --cov=src --cov-report=term-missing`),
  `check` (зависит от `lint format-check typecheck test`), `run` (`python -m src.main`).
- [ ] **Verify** — `make check` зелёный на текущем дереве.
- [ ] **Commit** — `chore(infra): add Makefile quality gate`

---

# Группа 2: `.env.example` (финализация)

- [ ] **Modify `.env.example`** — добавить `FALLBACK_SUBCATEGORY=Прочее` (новое поле конфига) в секцию
  «Каталог / валюты»; проверить, что присутствуют ВСЕ поля `Settings` с комментариями.
- [ ] **Verify** — сверить ключи `.env.example` с полями `src/config.py` (нет пропусков/лишних).
- [ ] **Commit** — `docs(infra): finalize .env.example with all settings`

---

# Группа 3: Dockerfile + .dockerignore

- [ ] **Create `.dockerignore`** — исключить `.git`, `.venv`, кэши, `tests`, `docs`, `*.md`, `.env`,
  `*service-account*.json`, `__pycache__`.
- [ ] **Create `Dockerfile`** — `python:3.11-slim`; non-root user; `pip install --no-cache-dir .`
  (только runtime-зависимости, без dev); copy `src/`; `STOPSIGNAL SIGTERM`; **exec-form**
  `CMD ["python","-m","src.main"]` (python = PID 1, получает SIGTERM → graceful shutdown в `main.py`).
- [ ] **Verify** — `docker build -t price-list-bot .` собирается (если доступен daemon/сеть; иначе пометить
  «собран локально оператором», Dockerfile проверен ревью).
- [ ] **Commit** — `chore(infra): add Dockerfile and .dockerignore`

---

# Группа 4: docker-compose.yml

- [ ] **Create `docker-compose.yml`** — сервис `bot`: `build: .`, `env_file: .env`,
  `volumes: ["./service-account.json:/secrets/sa.json:ro"]` (read-only mount; путь = дефолт
  `GOOGLE_APPLICATION_CREDENTIALS`), `init: true` (reaper зомби-процессов / форвард сигналов),
  `restart: unless-stopped`. Комментарий: polling — ровно одна реплика (не масштабировать).
- [ ] **Verify** — `docker compose config` валиден (парсится).
- [ ] **Commit** — `chore(infra): add docker-compose with read-only SA mount`

---

# Группа 5: README.md

- [ ] **Create `README.md`** — разделы:
  1. Что это (двуязычный прайс-лист из Google Sheets; заказов нет).
  2. Быстрый старт: `cp .env.example .env`, заполнить, положить `service-account.json`, `docker compose up`.
  3. Получение service-account: создать проект/SA в Google Cloud, включить Sheets API, скачать JSON-ключ,
     **расшарить таблицу на email сервис-аккаунта** (Reader).
  4. Шаблон таблицы — заголовки колонок 1-в-1 с моделью (`id, category, subcategory, name_ru, name_uz,
     desc_ru, desc_uz, price_wholesale, price_retail, currency, packaging, photo, is_active`); правила
     заполнения (толерантный bool/number, пустая subcategory → «Прочее», пустое name_* → строка
     пропускается, фото = публичный URL).
  5. Переменные окружения (таблица: имя, дефолт, назначение).
  6. Разработка: `make install`, `make check` (единый гейт), TDD-серия планов в `docs/superpowers/plans/`.
  7. Транспорт: polling (дефолт, одна реплика); webhook — каркас (ADR 0008).
- [ ] **Commit** — `docs(infra): add README (SA setup, sheet template, run, dev)`

---

# Группа 6: pre-commit + CI (GitHub Actions)

- [ ] **Create `.pre-commit-config.yaml`** — локальные хуки на гейт: `ruff check`, `ruff format`,
  `mypy --strict src` (через `language: system`, чтобы использовать окружение проекта).
- [ ] **Create `.github/workflows/ci.yml`** — на push/PR: `python 3.11`, `pip install -e ".[dev]"`,
  затем `ruff check .`, `ruff format --check .`, `mypy --strict src`, `pytest -q --cov=src`.
- [ ] **Verify** — `make check` локально зелёный (CI повторяет тот же гейт).
- [ ] **Commit** — `chore(infra): add pre-commit hooks and CI workflow`

---

# Финальный гейт

- [ ] `make check` зелёный; `git status --porcelain` пуст.
- [ ] DoD §8: `docker compose up` (или `python -m src.main`) поднимает бота; README покрывает SA/таблицу/запуск;
  `.env.example` полон; ADR на месте (0001–0013, актуальные).

# Вне охвата (отдельная задача при необходимости)

Полная реализация webhook (aiohttp-сервер, `set_webhook`, secret-token, healthcheck-эндпоинт);
persist языка/состояния (SQLite/Redis); форс-рефреш по whitelist user_id.
