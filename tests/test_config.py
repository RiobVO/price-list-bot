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
    return Settings(_env_file=None, **env)  # type: ignore[call-arg, arg-type]


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
        BOT_TOKEN="123:abc",  # type: ignore[arg-type]
        SPREADSHEET_ID="sheet-xyz",
        GOOGLE_CREDENTIALS_B64="eyJrIjoidiJ9",  # type: ignore[arg-type]
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
            BOT_TOKEN="123:abc",  # type: ignore[arg-type]
            SPREADSHEET_ID="sheet-xyz",
        )


def test_empty_string_creds_treated_as_absent() -> None:
    """Пустая строка в GOOGLE_APPLICATION_CREDENTIALS = отсутствие -> при отсутствии b64 ошибка."""
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            BOT_TOKEN="123:abc",  # type: ignore[arg-type]
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
            BOT_TOKEN="123:abc",  # type: ignore[arg-type]
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
        settings.SHEET_NAME = "other"


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
