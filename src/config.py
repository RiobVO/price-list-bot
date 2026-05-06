"""Конфигурация приложения из переменных окружения (pydantic-settings)."""

from __future__ import annotations

from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Все настройки бота. Источник — окружение/.env. Иммутабельна (frozen)."""

    # Обязательные секреты и идентификаторы.
    BOT_TOKEN: SecretStr
    SPREADSHEET_ID: str

    # Google Sheets.
    SHEET_NAME: str = "products"

    # Кэш / парсинг.
    CACHE_TTL_SECONDS: int = Field(default=300, gt=0)
    DEFAULT_CURRENCY: str = "UZS"
    CURRENCIES: str = "UZS"  # csv-список разрешённых валют
    MIN_VALID_ROWS: int = Field(default=1, ge=0)

    # UI / троттлинг.
    PAGE_SIZE: int = Field(default=8, ge=1, le=10)
    THROTTLE_RATE_PER_SEC: float = Field(default=1.0, gt=0)

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

    @model_validator(mode="after")
    def _exactly_one_credentials_source(self) -> Self:
        """РОВНО один способ доставки creds: путь к файлу ИЛИ base64. Пустая строка = отсутствие."""
        path = self.GOOGLE_APPLICATION_CREDENTIALS
        has_path = bool(path and path.strip())
        b64 = self.GOOGLE_CREDENTIALS_B64
        has_b64 = b64 is not None and bool(b64.get_secret_value().strip())
        if has_path == has_b64:  # оба заданы ИЛИ оба пусты
            raise ValueError(
                "exactly one of GOOGLE_APPLICATION_CREDENTIALS / GOOGLE_CREDENTIALS_B64 must be set"
            )
        return self
