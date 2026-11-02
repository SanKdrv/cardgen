"""Схемы HTTP-слоя, дополняющие доменные модели."""

from __future__ import annotations

from pydantic import Field

from ...domain.models import GenerateOptions, ProductInput


class BareGenerateRequest(ProductInput):
    """Товар без обёртки `product`, но с необязательными опциями.

    ТЗ показывает именно «голый» JSON товара; если клиент добавит
    `options.allow_fallback=false`, настройка не должна теряться.
    """

    options: GenerateOptions = Field(default_factory=GenerateOptions)
