"""Конфигурация из переменных окружения и .env."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки сервиса. Все переменные имеют префикс CARDGEN_."""

    model_config = SettingsConfigDict(
        env_prefix="CARDGEN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    provider: Literal["openai", "fixture", "template"] = Field(
        default="openai",
        description=(
            "openai — любой OpenAI-совместимый API; fixture — офлайн-демо; " "template — без LLM."
        ),
    )
    base_url: str = "https://opencode.ai/zen/go/v1"
    model: str = "deepseek-v4.1-flash"
    api_key: SecretStr | None = None

    session_header: str | None = "x-opencode-session"
    session_prefix: str = "ses_"
    extra_headers: dict[str, str] = Field(default_factory=dict)

    timeout_s: float = Field(default=60.0, gt=0, le=600)
    max_attempts: int = Field(default=2, ge=1, le=5)
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_backoff_s: float = Field(default=0.5, ge=0, le=30)
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_output_tokens: int = Field(default=2000, ge=200, le=32_000)
    json_mode: bool = True
    log_level: str = "INFO"

    @field_validator("base_url")
    @classmethod
    def _validate_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("base_url должен начинаться с http:// или https://")
        return normalized

    @field_validator("api_key", mode="before")
    @classmethod
    def _empty_key_to_none(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            return value if value.get_secret_value().strip() else None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("session_header", mode="before")
    @classmethod
    def _empty_header_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def api_key_value(self) -> str | None:
        return self.api_key.get_secret_value() if self.api_key else None

    @property
    def provider_ready(self) -> bool:
        """Готов ли провайдер отвечать без гарантированной ошибки авторизации."""
        return self.provider != "openai" or bool(self.api_key_value)


@lru_cache
def get_settings() -> Settings:
    return Settings()
