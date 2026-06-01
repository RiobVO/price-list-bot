.PHONY: install lint format format-check typecheck test cov check run

# Установка проекта с dev-зависимостями в текущее окружение.
install:
	pip install -e ".[dev]"

# Линт (ruff): стиль, импорты, баги.
lint:
	ruff check .

# Автоформат (ruff).
format:
	ruff format .

# Проверка форматирования без правок (для гейта/CI).
format-check:
	ruff format --check .

# Строгая проверка типов.
typecheck:
	mypy --strict src

# Тесты.
test:
	pytest -q

# Тесты с покрытием.
cov:
	pytest --cov=src --cov-report=term-missing

# Единый гейт качества (§10 дизайна): lint -> format -> typecheck -> test.
check: lint format-check typecheck test

# Запуск бота.
run:
	python -m src.main
