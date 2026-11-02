"""Сборка FastAPI-приложения из независимых роутеров."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ... import __version__
from ...application.pipeline import CardGenerator
from ...infrastructure.config import Settings, get_settings
from ...infrastructure.llm import build_provider
from ...infrastructure.llm.base import LLMProvider
from .errors import register_exception_handlers
from .routes import cards, health, ui

_APP_DIR = Path(__file__).resolve().parent
_PRESENTATION_DIR = _APP_DIR.parent
_TEMPLATES_DIR = _PRESENTATION_DIR / "templates"
_STATIC_DIR = _PRESENTATION_DIR / "static"


def create_app(
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
) -> FastAPI:
    """Собирает приложение. Провайдер и настройки можно подменить в тестах."""
    active_settings = settings or get_settings()
    logging.getLogger("cardgen").setLevel(active_settings.log_level.upper())

    owns_provider = provider is None
    active_provider = provider or build_provider(active_settings)
    generator = CardGenerator(active_provider, active_settings)
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_provider:
            await active_provider.aclose()

    app = FastAPI(
        title="cardgen — AI-карточки КИП",
        description=(
            "Генератор черновиков B2B-карточек контрольно-измерительных приборов. "
            "Не выдумывает характеристики: все факты проверяются детерминированно."
        ),
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = active_settings
    app.state.provider = active_provider
    app.state.generator = generator
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(cards.router)
    app.include_router(ui.router)
    return app


app = create_app()
