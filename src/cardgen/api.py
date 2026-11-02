"""FastAPI-приложение: JSON API и веб-форма для контент-менеджера."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from . import __version__
from .config import Settings, get_settings
from .errors import CardgenError, LLMError, ValidationFailedError
from .llm import build_provider
from .llm.base import LLMProvider
from .models import (
    BatchError,
    BatchGenerateRequest,
    BatchResponse,
    CardResult,
    ErrorDetail,
    ErrorResponse,
    GenerateOptions,
    GenerateRequest,
    HealthResponse,
    ProductInput,
)
from .pipeline import CardGenerator

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent
_TEMPLATES_DIR = _PACKAGE_DIR / "templates"
_STATIC_DIR = _PACKAGE_DIR / "static"
_DEMO_PATH = _PACKAGE_DIR / "data" / "demo_products.json"


@lru_cache
def load_examples() -> list[dict[str, Any]]:
    if not _DEMO_PATH.exists():
        return []
    payload = json.loads(_DEMO_PATH.read_text(encoding="utf-8"))
    products = payload.get("products", payload) if isinstance(payload, dict) else payload
    return [item for item in products if isinstance(item, dict)]


def _error_response(status_code: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=ErrorDetail(type=error_type, message=message)).model_dump(),
    )


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

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()[:5]
        )
        return _error_response(422, "validation_error", f"Некорректные входные данные: {details}")

    @app.exception_handler(ValidationFailedError)
    async def handle_validation_failed(
        request: Request, exc: ValidationFailedError
    ) -> JSONResponse:
        logger.warning(
            "Черновик не прошёл проверку (request_id=%s): %s",
            getattr(request.state, "request_id", "-"),
            exc.message,
        )
        return JSONResponse(
            status_code=502,
            content={
                "error": {
                    "type": "validation_failed",
                    "message": exc.message,
                    "violations": [
                        item.model_dump() if hasattr(item, "model_dump") else str(item)
                        for item in exc.violations
                    ],
                }
            },
        )

    @app.exception_handler(LLMError)
    async def handle_llm_error(request: Request, exc: LLMError) -> JSONResponse:
        logger.error(
            "Ошибка LLM (request_id=%s): %s",
            getattr(request.state, "request_id", "-"),
            exc.message,
        )
        return _error_response(502, "llm_error", exc.message)

    @app.exception_handler(CardgenError)
    async def handle_cardgen_error(_request: Request, exc: CardgenError) -> JSONResponse:
        return _error_response(500, "cardgen_error", str(exc))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, _exc: Exception) -> JSONResponse:
        logger.exception(
            "Необработанная ошибка (request_id=%s)",
            getattr(request.state, "request_id", "-"),
        )
        return _error_response(500, "internal_error", "Внутренняя ошибка сервиса")

    # --- служебные эндпоинты -------------------------------------------------

    @app.get("/health", response_model=HealthResponse, tags=["service"])
    async def health() -> HealthResponse:
        return HealthResponse(
            version=__version__,
            provider=active_provider.name,
            model=active_provider.model,
            provider_ready=active_provider.ready,
        )

    @app.get("/api/v1/examples", tags=["service"])
    async def examples() -> list[dict[str, Any]]:
        return load_examples()

    # --- JSON API ------------------------------------------------------------

    @app.post(
        "/api/v1/cards",
        response_model=CardResult,
        response_model_exclude_none=True,
        tags=["cards"],
    )
    async def generate_card(payload: GenerateRequest) -> CardResult:
        return await generator.generate(payload.product, payload.options)

    @app.post(
        "/api/v1/cards/batch",
        response_model=BatchResponse,
        response_model_exclude_none=True,
        tags=["cards"],
    )
    async def generate_cards(payload: BatchGenerateRequest) -> BatchResponse:
        response = BatchResponse()
        for index, product in enumerate(payload.products):
            try:
                response.items.append(await generator.generate(product, payload.options))
            except CardgenError as exc:
                message = getattr(exc, "message", str(exc))
                response.errors.append(
                    BatchError(
                        index=index,
                        product_name=product.name,
                        error_type=type(exc).__name__,
                        message=str(message),
                    )
                )
        return response

    # --- веб-форма -----------------------------------------------------------

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(request: Request, example: int | None = None) -> HTMLResponse:
        examples = load_examples()
        form: dict[str, Any] | None = None
        if example is not None and 0 <= example < len(examples):
            selected = examples[example]
            form = {
                "name": selected.get("name", ""),
                "manufacturer": selected.get("manufacturer", ""),
                "category": selected.get("category", ""),
                "description": selected.get("description", ""),
                "specs": [
                    {"key": key, "value": value}
                    for key, value in dict(selected.get("specs", {})).items()
                ],
                "allow_fallback": True,
            }
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "examples": examples,
                "provider": active_provider.name,
                "provider_ready": active_provider.ready,
                "model": active_provider.model,
                "error": None,
                "form": form,
            },
        )

    @app.post("/ui/generate", response_class=HTMLResponse, include_in_schema=False)
    async def generate_from_form(request: Request) -> HTMLResponse:
        form = await request.form()
        spec_keys = [str(item) for item in form.getlist("spec_key")]
        spec_values = [str(item) for item in form.getlist("spec_value")]
        specs = {
            key.strip(): value.strip()
            for key, value in zip(spec_keys, spec_values, strict=False)
            if key.strip() and value.strip()
        }
        raw_form: dict[str, Any] = {
            "name": str(form.get("name", "")),
            "manufacturer": str(form.get("manufacturer", "")),
            "category": str(form.get("category", "")),
            "description": str(form.get("description", "")),
            "specs": [
                {"key": key, "value": value}
                for key, value in zip(spec_keys, spec_values, strict=False)
                if key.strip() or value.strip()
            ],
            "allow_fallback": form.get("allow_fallback") is not None,
        }

        try:
            product = ProductInput(
                name=raw_form["name"],
                manufacturer=raw_form["manufacturer"],
                category=raw_form["category"] or None,
                specs=specs,
                description=raw_form["description"],
            )
        except ValidationError as exc:
            message = "; ".join(
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()[:3]
            )
            return templates.TemplateResponse(
                request=request,
                name="index.html",
                context={
                    "examples": load_examples(),
                    "provider": active_provider.name,
                    "provider_ready": active_provider.ready,
                    "model": active_provider.model,
                    "error": f"Проверьте форму: {message}",
                    "form": raw_form,
                },
                status_code=422,
            )

        try:
            result = await generator.generate(
                product,
                GenerateOptions(allow_fallback=bool(raw_form["allow_fallback"])),
            )
        except CardgenError as exc:
            return templates.TemplateResponse(
                request=request,
                name="index.html",
                context={
                    "examples": load_examples(),
                    "provider": active_provider.name,
                    "provider_ready": active_provider.ready,
                    "model": active_provider.model,
                    "error": getattr(exc, "message", str(exc)),
                    "form": raw_form,
                },
                status_code=502,
            )

        return templates.TemplateResponse(
            request=request,
            name="result.html",
            context={
                "result": result,
                "json_text": result.model_dump_json(indent=2, exclude_none=True),
                "markdown_text": result.markdown,
                "provider": active_provider.name,
                "provider_ready": active_provider.ready,
                "model": active_provider.model,
            },
        )

    return app


app = create_app()
