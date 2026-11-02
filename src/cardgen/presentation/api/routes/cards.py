"""JSON API генерации карточек."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ....application.pipeline import CardGenerator
from ....core.errors import CardgenError
from ....domain.models import (
    BatchError,
    BatchGenerateRequest,
    BatchResponse,
    CardResult,
    GenerateRequest,
)
from ..dependencies import get_generator
from ..schemas import BareGenerateRequest

router = APIRouter(prefix="/api/v1", tags=["cards"])


@router.post(
    "/cards",
    response_model=CardResult,
    response_model_exclude_none=True,
)
async def generate_card(
    payload: GenerateRequest | BareGenerateRequest,
    generator: Annotated[CardGenerator, Depends(get_generator)],
) -> CardResult:
    if isinstance(payload, GenerateRequest):
        return await generator.generate(payload.product, payload.options)
    return await generator.generate(payload, payload.options)


@router.post(
    "/cards/batch",
    response_model=BatchResponse,
    response_model_exclude_none=True,
)
async def generate_cards(
    payload: BatchGenerateRequest,
    generator: Annotated[CardGenerator, Depends(get_generator)],
) -> BatchResponse:
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
