"""Провайдер-заглушка для полностью детерминированного режима."""

from __future__ import annotations

from ...core.errors import LLMUnavailableError


class TemplateProvider:
    """Не вызывает LLM: пайплайн сразу собирает карточку по шаблону."""

    name = "template"
    model = "deterministic-template"

    @property
    def ready(self) -> bool:
        return True

    async def complete(self, *, system: str, user: str) -> str:
        del system, user
        raise LLMUnavailableError("шаблонный провайдер не обращается к LLM")

    async def aclose(self) -> None:
        return None
