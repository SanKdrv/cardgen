"""Провайдер LLM: протокол и общие типы."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Минимальный контракт, которого достаточно пайплайну."""

    name: str
    model: str

    @property
    def ready(self) -> bool:
        """Готов ли провайдер к запросам (например, задан ли ключ)."""
        ...

    async def complete(self, *, system: str, user: str) -> str:
        """Возвращает сырой текст ответа модели."""
        ...

    async def aclose(self) -> None:
        """Освобождает сетевые ресурсы."""
        ...
