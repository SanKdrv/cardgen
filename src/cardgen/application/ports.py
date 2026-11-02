"""Порты приложения: контракты, которые реализует инфраструктура."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """Минимальный контракт LLM-провайдера, достаточный пайплайну."""

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


class PipelineSettings(Protocol):
    """Настройки, которые реально нужны генератору."""

    @property
    def max_attempts(self) -> int: ...

    @property
    def max_concurrency(self) -> int: ...

    @property
    def concurrency_timeout_s(self) -> float: ...
