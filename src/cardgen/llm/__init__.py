"""Провайдеры LLM."""

from __future__ import annotations

from .base import LLMProvider
from .factory import build_provider
from .fixture import FixtureProvider
from .openai_compat import OpenAICompatibleProvider
from .template import TemplateProvider

__all__ = [
    "FixtureProvider",
    "LLMProvider",
    "OpenAICompatibleProvider",
    "TemplateProvider",
    "build_provider",
]
