from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from cardgen.errors import (
    LLMAuthError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from cardgen.llm.openai_compat import OpenAICompatibleProvider


def make_provider(client: httpx.AsyncClient, **overrides: Any) -> OpenAICompatibleProvider:
    params: dict[str, Any] = {
        "base_url": "https://example.test/v1",
        "model": "test-model",
        "api_key": "test-key",
        "client": client,
        "max_retries": 3,
        "retry_backoff_s": 0,
        "session_header": None,
    }
    params.update(overrides)
    return OpenAICompatibleProvider(**params)


async def test_successful_request_payload_and_headers() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok": true}'}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client)
        assert await provider.complete(system="система", user="запрос") == '{"ok": true}'

    assert len(captured) == 1
    request = captured[0]
    assert str(request.url) == "https://example.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    payload = json.loads(request.content)
    assert payload["model"] == "test-model"
    assert payload["messages"][0] == {"role": "system", "content": "система"}
    assert payload["messages"][1] == {"role": "user", "content": "запрос"}
    assert payload["response_format"] == {"type": "json_object"}


async def test_session_header_is_generated() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client, session_header="x-opencode-session")
        await provider.complete(system="s", user="u")
        await provider.complete(system="s", user="u")

    first = captured[0].headers["x-opencode-session"]
    second = captured[1].headers["x-opencode-session"]
    assert first.startswith("ses_")
    assert first == second


async def test_content_as_list_of_parts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": [{"text": "часть1"}, {"text": "часть2"}]}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client)
        assert await provider.complete(system="s", user="u") == "часть1часть2"


async def test_rate_limit_is_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, text="slow down")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client)
        assert await provider.complete(system="s", user="u") == "ok"
    assert len(calls) == 2


async def test_rate_limit_exhausted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="slow down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client, max_retries=2)
        with pytest.raises(LLMRateLimitError):
            await provider.complete(system="s", user="u")


async def test_server_error_is_retried_and_raises() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503, text="unavailable")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client, max_retries=2)
        with pytest.raises(LLMUnavailableError):
            await provider.complete(system="s", user="u")
    assert len(calls) == 2


async def test_auth_error_is_not_retried() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, text="bad key")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client)
        with pytest.raises(LLMAuthError, match="ключ"):
            await provider.complete(system="s", user="u")
    assert len(calls) == 1


async def test_model_not_found() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="no model")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client)
        with pytest.raises(LLMResponseError, match="не найден"):
            await provider.complete(system="s", user="u")


async def test_timeout_is_retried() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client, max_retries=2, timeout_s=0.01)
        with pytest.raises(LLMTimeoutError):
            await provider.complete(system="s", user="u")


async def test_network_error_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client, max_retries=1)
        with pytest.raises(LLMUnavailableError, match="подключиться"):
            await provider.complete(system="s", user="u")


async def test_non_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json", headers={"content-type": "text/plain"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client)
        with pytest.raises(LLMResponseError, match="не-JSON"):
            await provider.complete(system="s", user="u")


async def test_missing_choices_and_empty_content() -> None:
    def no_choices(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]})

    for handler, message in ((no_choices, "choices"), (empty, "пустой")):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = make_provider(client)
            with pytest.raises(LLMResponseError, match=message):
                await provider.complete(system="s", user="u")


async def test_empty_content_with_reasoning_reports_token_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": "", "reasoning_content": "долго думал"},
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client, max_output_tokens=1234)
        with pytest.raises(LLMResponseError, match="reasoning") as error:
            await provider.complete(system="s", user="u")
    assert "1234" in str(error.value)


async def test_error_object_in_200_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"message": "quota"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client)
        with pytest.raises(LLMResponseError, match="quota"):
            await provider.complete(system="s", user="u")


async def test_unknown_client_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(418, text="teapot")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client)
        with pytest.raises(LLMResponseError, match="418"):
            await provider.complete(system="s", user="u")


async def test_missing_api_key_does_not_make_request() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client, api_key=None)
        assert provider.ready is False
        with pytest.raises(LLMAuthError, match="API-ключ"):
            await provider.complete(system="s", user="u")
    assert calls == []


async def test_extra_headers_and_json_mode_disabled() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = make_provider(client, json_mode=False, extra_headers={"X-Org": "souz"})
        await provider.complete(system="s", user="u")

    assert captured[0].headers["x-org"] == "souz"
    assert "response_format" not in json.loads(captured[0].content)
