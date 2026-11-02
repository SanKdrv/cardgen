from __future__ import annotations

import pytest
from pydantic import ValidationError

from cardgen.infrastructure.config import Settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.provider == "openai"
    assert settings.model == "deepseek-v4.1-flash"
    assert settings.base_url == "https://opencode.ai/zen/go/v1"
    assert settings.max_attempts == 2
    assert settings.timeout_s == 180
    assert settings.max_output_tokens == 16000
    assert settings.max_concurrency == 4
    assert settings.rate_limit_per_minute == 60
    assert settings.session_header == "x-opencode-session"


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARDGEN_PROVIDER", "fixture")
    monkeypatch.setenv("CARDGEN_MODEL", "test-model")
    monkeypatch.setenv("CARDGEN_MAX_ATTEMPTS", "3")
    settings = Settings(_env_file=None)
    assert settings.provider == "fixture"
    assert settings.model == "test-model"
    assert settings.max_attempts == 3


def test_empty_api_key_becomes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARDGEN_API_KEY", "  ")
    settings = Settings(_env_file=None)
    assert settings.api_key is None
    assert settings.api_key_value is None


def test_api_key_is_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARDGEN_API_KEY", "secret-value")
    settings = Settings(_env_file=None)
    assert settings.api_key_value == "secret-value"
    assert "secret-value" not in repr(settings)


def test_provider_ready_flags() -> None:
    assert Settings(_env_file=None, provider="fixture").provider_ready is True
    assert Settings(_env_file=None, provider="template").provider_ready is True
    assert Settings(_env_file=None, provider="openai", api_key=None).provider_ready is False
    assert Settings(_env_file=None, provider="openai", api_key="key").provider_ready is True


def test_base_url_is_normalized_and_validated() -> None:
    assert Settings(_env_file=None, base_url="https://example.com/v1/").base_url == (
        "https://example.com/v1"
    )
    with pytest.raises(ValidationError, match="http"):
        Settings(_env_file=None, base_url="example.com")


def test_empty_session_header_becomes_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARDGEN_SESSION_HEADER", "")
    assert Settings(_env_file=None).session_header is None


def test_extra_headers_from_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CARDGEN_EXTRA_HEADERS", '{"X-Org": "souz"}')
    assert Settings(_env_file=None).extra_headers == {"X-Org": "souz"}


def test_attempts_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_attempts=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_attempts=6)
