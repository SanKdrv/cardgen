from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from cardgen.application.pipeline import CardGenerator
from cardgen.core.errors import ConcurrencyLimitError
from cardgen.domain.models import ProductInput
from cardgen.infrastructure.config import Settings


class BlockingProvider:
    name = "blocking"
    model = "blocking-1"

    def __init__(self, response: str) -> None:
        self.response = response
        self.active = 0
        self.max_active = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    @property
    def ready(self) -> bool:
        return True

    async def complete(self, *, system: str, user: str) -> str:
        del system, user
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.started.set()
        await self.release.wait()
        self.active -= 1
        return self.response

    async def aclose(self) -> None:
        return None


def _settings(**overrides: Any) -> Settings:
    values = {
        "_env_file": None,
        "provider": "fixture",
        "api_key": None,
        "max_attempts": 1,
        "max_retries": 1,
        "retry_backoff_s": 0,
        "max_concurrency": 1,
        "concurrency_timeout_s": 5.0,
    }
    values.update(overrides)
    return Settings(**values)


def _raw(draft: dict[str, Any]) -> str:
    return json.dumps(draft, ensure_ascii=False)


async def test_only_one_generation_enters_provider(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    provider = BlockingProvider(_raw(good_draft))
    generator = CardGenerator(provider, _settings())
    first = asyncio.create_task(generator.generate(product))
    await provider.started.wait()
    second = asyncio.create_task(generator.generate(product))
    await asyncio.sleep(0.05)

    assert provider.max_active == 1
    provider.release.set()
    results = await asyncio.gather(first, second)
    assert len(results) == 2
    assert provider.max_active == 1


async def test_concurrency_timeout_is_503_error(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    provider = BlockingProvider(_raw(good_draft))
    generator = CardGenerator(provider, _settings(concurrency_timeout_s=0.01))
    await generator._semaphore.acquire()
    try:
        with pytest.raises(ConcurrencyLimitError):
            await generator.generate(product)
    finally:
        generator._semaphore.release()


async def test_slow_generation_is_not_killed_by_slot_timeout(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    provider = BlockingProvider(_raw(good_draft))
    generator = CardGenerator(provider, _settings(concurrency_timeout_s=0.01))
    task = asyncio.create_task(generator.generate(product))
    await provider.started.wait()
    await asyncio.sleep(0.05)
    provider.release.set()
    result = await task
    assert result.meta.fallback_used is False


async def test_concurrency_handler_returns_503() -> None:
    from cardgen.presentation.api.errors import handle_concurrency_limit

    response = await handle_concurrency_limit(
        None,  # type: ignore[arg-type]
        ConcurrencyLimitError("сервис занят", 30),
    )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"
    assert b"service_busy" in response.body


async def test_rate_limiter_allows_burst_then_blocks() -> None:
    from cardgen.presentation.api.rate_limit import RateLimiter

    now = [0.0]
    limiter = RateLimiter(2, window_s=60, clock=lambda: now[0])
    assert await limiter.acquire("127.0.0.1") == (True, None)
    assert await limiter.acquire("127.0.0.1") == (True, None)
    allowed, retry_after = await limiter.acquire("127.0.0.1")
    assert allowed is False
    assert retry_after is not None
    assert retry_after >= 1

    now[0] = 61.0
    assert await limiter.acquire("127.0.0.1") == (True, None)
