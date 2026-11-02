from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from cardgen.domain.models import ProductInput
from cardgen.infrastructure.config import Settings
from cardgen.infrastructure.llm.fixture import FixtureProvider

ROOT = Path(__file__).resolve().parents[1]
DEMO_PATH = ROOT / "src" / "cardgen" / "data" / "demo_products.json"
FIXTURES_PATH = ROOT / "src" / "cardgen" / "data" / "fixtures.json"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def demo_products() -> list[dict[str, Any]]:
    return list(_read(DEMO_PATH)["products"])


@pytest.fixture
def product(demo_products: list[dict[str, Any]]) -> ProductInput:
    return ProductInput.model_validate(demo_products[0])


@pytest.fixture
def partial_product(demo_products: list[dict[str, Any]]) -> ProductInput:
    return ProductInput.model_validate(demo_products[1])


@pytest.fixture(scope="session")
def fixture_drafts() -> dict[str, Any]:
    return dict(_read(FIXTURES_PATH)["drafts"])


@pytest.fixture
def good_draft(product: ProductInput, fixture_drafts: dict[str, Any]) -> dict[str, Any]:
    return dict(fixture_drafts[product.name])


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        provider="fixture",
        api_key=None,
        max_attempts=2,
        max_retries=1,
        retry_backoff_s=0,
    )


@pytest.fixture
def fixture_provider() -> FixtureProvider:
    return FixtureProvider()


class ScriptedProvider:
    """Провайдер, который отдаёт заранее заданные ответы и записывает вызовы."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, responses: list[str | Exception]) -> None:
        if not responses:
            raise ValueError("нужен хотя бы один ответ")
        self.responses = list(responses)
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    @property
    def ready(self) -> bool:
        return True

    async def complete(self, *, system: str, user: str) -> str:
        self.calls.append((system, user))
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def scripted_factory() -> Callable[[list[str | Exception]], ScriptedProvider]:
    return ScriptedProvider
