"""Environment-based application configuration.

Settings are read from environment variables (prefix ``APP_``) or a local
``.env`` file, and validated at import time so a misconfigured deployment fails
loudly at startup rather than on the first request that happens to need the bad
value.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    CI = "ci"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ACME Pay Insights"
    environment: Environment = Environment.LOCAL
    debug: bool = False
    log_level: str = "INFO"

    api_v1_prefix: str = "/api/v1"

    # SQLite locally; PostgreSQL in staging/production. The schema is written to
    # the intersection of both dialects so the URL is the only thing that changes.
    database_url: str = "sqlite:///./acme_pay_insights.db"
    database_echo: bool = False

    default_reporting_currency: str = "USD"

    default_page_size: int = Field(default=50, ge=1, le=200)
    max_page_size: int = Field(default=200, ge=1, le=1000)

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @field_validator("default_reporting_currency")
    @classmethod
    def _validate_reporting_currency(cls, value: str) -> str:
        # Imported here to keep the domain layer free of a settings dependency.
        from app.domain.currencies import is_supported_currency

        code = value.strip().upper()
        if not is_supported_currency(code):
            raise ValueError(f"Unsupported default reporting currency: {value!r}")
        return code

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings singleton.

    Cached so that configuration is parsed once per process. Tests that need to
    vary configuration should call ``get_settings.cache_clear()``.
    """
    return Settings()
