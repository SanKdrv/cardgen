"""Служебные эндпоинты: здоровье и демо-товары."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from .... import __version__
from ....application.ports import LLMProvider
from ....domain.models import HealthResponse
from ..dependencies import get_provider
from ..examples import load_examples

router = APIRouter(tags=["service"])


@router.get("/health", response_model=HealthResponse)
async def health(
    provider: Annotated[LLMProvider, Depends(get_provider)],
) -> HealthResponse:
    return HealthResponse(
        version=__version__,
        provider=provider.name,
        model=provider.model,
        provider_ready=provider.ready,
    )


@router.get("/api/v1/examples")
async def examples() -> list[dict[str, Any]]:
    return load_examples()
