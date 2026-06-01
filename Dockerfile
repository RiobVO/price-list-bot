# Двуязычный Telegram прайс-лист бот. Транспорт по умолчанию — long-polling.
FROM python:3.11-slim

# Логи сразу в stdout, без .pyc.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Только runtime-зависимости (без dev): копируем метаданные и пакет, ставим проект.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Non-root: процесс не должен работать от root в контейнере.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# Корректная реакция на остановку: main.py ловит SIGTERM (graceful shutdown).
STOPSIGNAL SIGTERM

# exec-форма: python становится PID 1 и получает SIGTERM напрямую.
CMD ["python", "-m", "src.main"]
