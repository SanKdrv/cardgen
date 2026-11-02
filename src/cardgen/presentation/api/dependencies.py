"""Зависимости FastAPI-приложения.

Состояние создаётся в `create_app` и живёт в `app.state`, поэтому роутеры
не создают провайдера и генератор повторно и легко подменяются в тестах.
"""

from __future__ import annotations

from typing import cast

from fastapi import Request
from fastapi.templating import Jinja2Templates

from ...application.pipeline import CardGenerator
from ...application.ports import LLMProvider
from ...infrastructure.config import Settings


def get_generator(request: Request) -> CardGenerator:
    return cast(CardGenerator, request.app.state.generator)


def get_provider(request: Request) -> LLMProvider:
    return cast(LLMProvider, request.app.state.provider)


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_templates(request: Request) -> Jinja2Templates:
    return cast(Jinja2Templates, request.app.state.templates)
