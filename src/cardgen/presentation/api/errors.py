"""Обработчики ошибок HTTP-слоя."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ...core.errors import CardgenError, LLMError, ValidationFailedError
from ...domain.models import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _error_response(status_code: int, error_type: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=ErrorDetail(type=error_type, message=message)).model_dump(),
    )


async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    details = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()[:5]
    )
    return _error_response(422, "validation_error", f"Некорректные входные данные: {details}")


async def handle_validation_failed(request: Request, exc: ValidationFailedError) -> JSONResponse:
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


async def handle_llm_error(request: Request, exc: LLMError) -> JSONResponse:
    logger.error(
        "Ошибка LLM (request_id=%s): %s",
        getattr(request.state, "request_id", "-"),
        exc.message,
    )
    return _error_response(502, "llm_error", exc.message)


async def handle_cardgen_error(_request: Request, exc: CardgenError) -> JSONResponse:
    return _error_response(500, "cardgen_error", str(exc))


async def handle_unexpected(request: Request, _exc: Exception) -> JSONResponse:
    logger.exception(
        "Необработанная ошибка (request_id=%s)",
        getattr(request.state, "request_id", "-"),
    )
    return _error_response(500, "internal_error", "Внутренняя ошибка сервиса")


def register_exception_handlers(app: FastAPI) -> None:
    """Регистрирует обработчики в одном месте, а не в фабрике приложения."""
    handlers: list[tuple[type[Exception], Any]] = [
        (RequestValidationError, handle_validation_error),
        (ValidationFailedError, handle_validation_failed),
        (LLMError, handle_llm_error),
        (CardgenError, handle_cardgen_error),
        (Exception, handle_unexpected),
    ]
    for error_type, handler in handlers:
        app.add_exception_handler(error_type, handler)
