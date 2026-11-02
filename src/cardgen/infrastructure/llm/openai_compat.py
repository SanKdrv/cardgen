"""Клиент для любого OpenAI-совместимого Chat Completions API.

Подходит для OpenCode Go, OpenAI, DeepSeek, Ollama, vLLM и других серверов,
которые реализуют POST /chat/completions.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from typing import Any

import httpx

from ... import __version__
from ...core.errors import (
    LLMAuthError,
    LLMError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)

logger = logging.getLogger(__name__)

_MAX_RETRY_DELAY_S = 10.0


class OpenAICompatibleProvider:
    """Тонкий клиент без SDK: меньше зависимостей и полный контроль над ошибками."""

    name = "openai"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None,
        timeout_s: float = 60.0,
        temperature: float = 0.2,
        max_output_tokens: int = 2000,
        json_mode: bool = True,
        session_header: str | None = None,
        session_prefix: str = "ses_",
        extra_headers: dict[str, str] | None = None,
        max_retries: int = 3,
        retry_backoff_s: float = 0.5,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._json_mode = json_mode
        self._session_header = session_header
        self._session_id = f"{session_prefix}{uuid.uuid4().hex}" if session_header else None
        self._extra_headers = extra_headers or {}
        self._max_retries = max_retries
        self._retry_backoff_s = retry_backoff_s
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    @property
    def ready(self) -> bool:
        return bool(self._api_key)

    async def aclose(self) -> None:
        if self._owns_client and not self._client.is_closed:
            await self._client.aclose()

    async def complete(self, *, system: str, user: str) -> str:
        if not self._api_key:
            raise LLMAuthError(
                "не задан API-ключ: заполните CARDGEN_API_KEY в .env или включите "
                "офлайн-режим CARDGEN_PROVIDER=fixture"
            )

        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_output_tokens,
        }
        if self._json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error: LLMError | None = None
        for attempt in range(1, self._max_retries + 1):
            response: httpx.Response | None = None
            started = time.perf_counter()
            try:
                response = await self._client.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                    timeout=self._timeout_s,
                )
            except httpx.TimeoutException:
                last_error = LLMTimeoutError(
                    f"провайдер не ответил за {self._timeout_s:.0f} с", retryable=True
                )
                logger.warning("Таймаут LLM (попытка %s/%s)", attempt, self._max_retries)
            except httpx.HTTPError as exc:
                last_error = LLMUnavailableError(
                    f"не удалось подключиться к провайдеру: {exc}", retryable=True
                )
                logger.warning(
                    "Сетевая ошибка LLM (попытка %s/%s): %s",
                    attempt,
                    self._max_retries,
                    exc,
                )
            else:
                elapsed_ms = (time.perf_counter() - started) * 1000
                if response.status_code == 200:
                    logger.debug("LLM ответила за %.0f мс", elapsed_ms)
                    return self._extract_content(response)

                error = self._map_error(response)
                if not error.retryable:
                    raise error
                last_error = error
                logger.warning(
                    "Провайдер вернул HTTP %s (попытка %s/%s)",
                    response.status_code,
                    attempt,
                    self._max_retries,
                )

            if attempt >= self._max_retries:
                break
            await asyncio.sleep(self._retry_delay(attempt, response))

        if last_error is None:  # pragma: no cover - защита от неполной ветки
            raise LLMResponseError("не удалось получить ответ провайдера")
        raise last_error

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"cardgen/{__version__}",
        }
        if self._session_header and self._session_id:
            headers[self._session_header] = self._session_id
        headers.update(self._extra_headers)
        return headers

    def _retry_delay(self, attempt: int, response: httpx.Response | None) -> float:
        delay: float = self._retry_backoff_s * (2 ** (attempt - 1))
        if response is not None:
            header = response.headers.get("retry-after")
            if header:
                with contextlib.suppress(ValueError):
                    delay = max(delay, float(header))
        return min(delay, _MAX_RETRY_DELAY_S)

    @staticmethod
    def _map_error(response: httpx.Response) -> LLMError:
        status = response.status_code
        body = response.text.strip().replace("\n", " ")[:300]
        if status in (401, 403):
            return LLMAuthError(
                f"провайдер отклонил ключ (HTTP {status}). Проверьте CARDGEN_API_KEY.",
                status_code=status,
            )
        if status == 404:
            return LLMResponseError(
                "модель или эндпоинт не найдены (HTTP 404). Проверьте CARDGEN_MODEL "
                "и CARDGEN_BASE_URL.",
                status_code=status,
            )
        if status == 429:
            return LLMRateLimitError(
                "превышен лимит запросов провайдера (HTTP 429)", retryable=True, status_code=status
            )
        if status >= 500 or status == 408:
            return LLMUnavailableError(
                f"провайдер временно недоступен (HTTP {status}): {body}",
                retryable=True,
                status_code=status,
            )
        return LLMResponseError(f"провайдер вернул HTTP {status}: {body}", status_code=status)

    def _extract_content(self, response: httpx.Response) -> str:
        try:
            data: Any = response.json()
        except ValueError as exc:
            raise LLMResponseError("провайдер вернул не-JSON ответ") from exc

        if isinstance(data, dict) and data.get("error"):
            error = data["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise LLMResponseError(f"провайдер сообщил об ошибке: {message}")

        choices = data.get("choices") if isinstance(data, dict) else None
        if not isinstance(choices, list) or not choices:
            raise LLMResponseError("в ответе нет поля choices")

        first = choices[0]
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item, str):
                    parts.append(item)
            content = "".join(parts)

        if not isinstance(content, str) or not content.strip():
            reasoning = message.get("reasoning_content") if isinstance(message, dict) else None
            if reasoning or first.get("finish_reason") == "length":
                raise LLMResponseError(
                    "модель израсходовала лимит токенов на reasoning и не вернула ответ. "
                    f"Увеличьте CARDGEN_MAX_OUTPUT_TOKENS (сейчас {self._max_output_tokens})."
                )
            raise LLMResponseError("провайдер вернул пустой ответ")
        return content
