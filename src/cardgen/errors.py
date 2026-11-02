"""Доменные исключения сервиса."""

from __future__ import annotations

from collections.abc import Sequence


class CardgenError(Exception):
    """Базовая ошибка приложения."""


class ConfigurationError(CardgenError):
    """Некорректная или неполная конфигурация."""


class LLMError(CardgenError):
    """Ошибка при обращении к LLM."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


class LLMAuthError(LLMError):
    """Неверный ключ или нет доступа к модели."""


class LLMUnavailableError(LLMError):
    """Провайдер недоступен по сети."""


class LLMTimeoutError(LLMUnavailableError):
    """Провайдер не ответил за отведённое время."""


class LLMRateLimitError(LLMError):
    """Превышен лимит запросов."""


class LLMResponseError(LLMError):
    """Провайдер вернул некорректный или пустой ответ."""


class DraftParseError(CardgenError):
    """Ответ модели не удалось разобрать как JSON нужной структуры."""


class ValidationFailedError(CardgenError):
    """Черновик не прошёл детерминированную проверку, а fallback запрещён."""

    def __init__(self, message: str, violations: Sequence[object]) -> None:
        super().__init__(message)
        self.message = message
        self.violations = violations
