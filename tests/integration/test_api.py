from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient

from cardgen.api import create_app
from cardgen.config import Settings
from cardgen.errors import LLMUnavailableError
from cardgen.llm.fixture import FixtureProvider
from cardgen.llm.openai_compat import OpenAICompatibleProvider

from ..conftest import ScriptedProvider


def make_client(
    provider: Any | None = None,
    *,
    max_attempts: int = 2,
) -> TestClient:
    active_provider = provider or FixtureProvider()
    settings = Settings(
        _env_file=None,
        provider="fixture",
        api_key=None,
        max_attempts=max_attempts,
        max_retries=1,
        retry_backoff_s=0,
    )
    return TestClient(create_app(settings=settings, provider=active_provider))


def raw(draft: dict[str, Any], **overrides: Any) -> str:
    payload = copy.deepcopy(draft)
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def test_health() -> None:
    with make_client() as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["provider"] == "fixture"
    assert body["provider_ready"] is True
    assert body["version"]


def test_health_reports_missing_key() -> None:
    provider = OpenAICompatibleProvider(base_url="https://example.test/v1", model="m", api_key=None)
    with make_client(provider) as client:
        body = client.get("/health").json()
    assert body["provider_ready"] is False


def test_examples_endpoint(demo_products: list[dict[str, Any]]) -> None:
    with make_client() as client:
        response = client.get("/api/v1/examples")
    assert response.status_code == 200
    assert len(response.json()) == len(demo_products)
    assert response.json()[0]["name"] == demo_products[0]["name"]


def test_generate_card(demo_products: list[dict[str, Any]]) -> None:
    with make_client() as client:
        response = client.post("/api/v1/cards", json={"product": demo_products[0]})
    assert response.status_code == 200
    body = response.json()
    assert body["draft"]["seo_title"]
    assert body["meta"]["provider"] == "fixture"
    assert body["meta"]["fallback_used"] is False
    assert body["markdown"].startswith("# ")
    assert body["missing_fields"] == []


def test_generate_partial_product(demo_products: list[dict[str, Any]]) -> None:
    with make_client() as client:
        response = client.post("/api/v1/cards", json={"product": demo_products[1]})
    assert response.status_code == 200
    assert [item["field"] for item in response.json()["missing_fields"]] == ["класс точности"]


def test_invalid_input_returns_422(demo_products: list[dict[str, Any]]) -> None:
    bad = copy.deepcopy(demo_products[0])
    bad["name"] = "П"
    with make_client() as client:
        response = client.post("/api/v1/cards", json={"product": bad})
    assert response.status_code == 422
    assert response.json()["error"]["type"] == "validation_error"
    assert response.headers["x-request-id"]


def test_nested_specs_returns_422(demo_products: list[dict[str, Any]]) -> None:
    bad = copy.deepcopy(demo_products[0])
    bad["specs"] = {"давление": {"значение": "1,6"}}
    with make_client() as client:
        response = client.post("/api/v1/cards", json={"product": bad})
    assert response.status_code == 422
    assert "validation_error" in response.text


def test_non_json_body_returns_422() -> None:
    with make_client() as client:
        response = client.post(
            "/api/v1/cards",
            content="не json",
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 422


def test_strict_mode_validation_failure(
    demo_products: list[dict[str, Any]],
    good_draft: dict[str, Any],
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory([raw(good_draft, seo_description="коротко")])
    with make_client(provider, max_attempts=1) as client:
        response = client.post(
            "/api/v1/cards",
            json={
                "product": demo_products[0],
                "options": {"allow_fallback": False},
            },
        )
    assert response.status_code == 502
    error = response.json()["error"]
    assert error["type"] == "validation_failed"
    assert error["violations"]


def test_strict_mode_llm_failure(
    demo_products: list[dict[str, Any]],
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory([LLMUnavailableError("нет сети")])
    with make_client(provider) as client:
        response = client.post(
            "/api/v1/cards",
            json={
                "product": demo_products[0],
                "options": {"allow_fallback": False},
            },
        )
    assert response.status_code == 502
    assert response.json()["error"]["type"] == "llm_error"


def test_default_fallback_returns_200(
    demo_products: list[dict[str, Any]],
    good_draft: dict[str, Any],
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory([raw(good_draft, seo_title="x" * 100)])
    with make_client(provider) as client:
        response = client.post("/api/v1/cards", json={"product": demo_products[0]})
    assert response.status_code == 200
    assert response.json()["meta"]["fallback_used"] is True


def test_batch_generation(demo_products: list[dict[str, Any]]) -> None:
    with make_client() as client:
        response = client.post("/api/v1/cards/batch", json={"products": demo_products})
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    assert body["errors"] == []


def test_batch_reports_per_item_errors(
    demo_products: list[dict[str, Any]],
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory([LLMUnavailableError("нет сети")])
    with make_client(provider) as client:
        response = client.post(
            "/api/v1/cards/batch",
            json={
                "products": demo_products,
                "options": {"allow_fallback": False},
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert len(body["errors"]) == 2
    assert body["errors"][0]["index"] == 0
    assert body["errors"][0]["error_type"] == "LLMUnavailableError"


def test_batch_requires_products() -> None:
    with make_client() as client:
        assert client.post("/api/v1/cards/batch", json={"products": []}).status_code == 422


def test_index_page() -> None:
    with make_client() as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "Сгенерировать карточку" in response.text
    assert "Данные прибора" in response.text


def test_ui_generation(demo_products: list[dict[str, Any]]) -> None:
    product = demo_products[1]
    with make_client() as client:
        response = client.post(
            "/ui/generate",
            data={
                "name": product["name"],
                "manufacturer": product["manufacturer"],
                "category": product["category"],
                "description": product["description"],
                "spec_key": list(product["specs"].keys()),
                "spec_value": list(product["specs"].values()),
                "allow_fallback": "on",
            },
        )
    assert response.status_code == 200
    assert product["name"] in response.text
    assert "Не хватает данных" in response.text
    assert "SEO-описание" in response.text


def test_ui_validation_error() -> None:
    with make_client() as client:
        response = client.post(
            "/ui/generate",
            data={"name": "П", "manufacturer": "З"},
        )
    assert response.status_code == 422
    assert "Проверьте форму" in response.text


def test_ui_llm_error_without_fallback(
    demo_products: list[dict[str, Any]],
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory([LLMUnavailableError("нет сети")])
    product = demo_products[0]
    with make_client(provider) as client:
        response = client.post(
            "/ui/generate",
            data={
                "name": product["name"],
                "manufacturer": product["manufacturer"],
                "spec_key": list(product["specs"].keys()),
                "spec_value": list(product["specs"].values()),
            },
        )
    assert response.status_code == 502
    assert "нет сети" in response.text


def test_static_css() -> None:
    with make_client() as client:
        response = client.get("/static/styles.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
