"""Фабрика провайдеров по настройкам."""

from __future__ import annotations

from ...application.ports import LLMProvider
from ...core.errors import ConfigurationError
from ..config import Settings
from .fixture import FixtureProvider
from .openai_compat import OpenAICompatibleProvider
from .template import TemplateProvider


def build_provider(settings: Settings) -> LLMProvider:
    if settings.provider == "openai":
        return OpenAICompatibleProvider(
            base_url=settings.base_url,
            model=settings.model,
            api_key=settings.api_key_value,
            timeout_s=settings.timeout_s,
            temperature=settings.temperature,
            max_output_tokens=settings.max_output_tokens,
            json_mode=settings.json_mode,
            session_header=settings.session_header,
            session_prefix=settings.session_prefix,
            extra_headers=settings.extra_headers,
            max_retries=settings.max_retries,
            retry_backoff_s=settings.retry_backoff_s,
        )
    if settings.provider == "fixture":
        return FixtureProvider()
    if settings.provider == "template":
        return TemplateProvider()
    raise ConfigurationError(f"неизвестный провайдер: {settings.provider}")
