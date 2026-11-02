from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest

from cardgen.config import Settings
from cardgen.errors import LLMUnavailableError, ValidationFailedError
from cardgen.facts import detect_missing_fields
from cardgen.fallback import build_template_draft
from cardgen.llm.fixture import FixtureProvider
from cardgen.llm.template import TemplateProvider
from cardgen.models import GenerateOptions, ProductInput
from cardgen.pipeline import CardGenerator

from ..conftest import ScriptedProvider


def raw(draft: dict[str, Any], **overrides: Any) -> str:
    payload = copy.deepcopy(draft)
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def make_generator(provider: Any, settings: Settings, max_attempts: int = 2) -> CardGenerator:
    return CardGenerator(provider, settings.model_copy(update={"max_attempts": max_attempts}))


async def test_successful_generation(
    product: ProductInput,
    good_draft: dict[str, Any],
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory([raw(good_draft)])
    result = await make_generator(provider, settings).generate(product)

    assert result.meta.attempts == 1
    assert result.meta.fallback_used is False
    assert result.meta.validation.ok
    assert result.warnings == []
    assert result.draft.seo_title == good_draft["seo_title"]
    assert result.markdown.startswith(f"# {product.name}")
    assert result.meta.latency_ms >= 0
    assert "Запрещено добавлять" in provider.calls[0][0]


async def test_validation_failure_is_corrected_on_retry(
    product: ProductInput,
    good_draft: dict[str, Any],
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    invalid = raw(good_draft, seo_description="слишком коротко")
    provider = scripted_factory([invalid, raw(good_draft)])
    result = await make_generator(provider, settings).generate(product)

    assert result.meta.attempts == 2
    assert result.meta.fallback_used is False
    assert len(provider.calls) == 2
    assert "РЕЗУЛЬТАТ АВТОМАТИЧЕСКОЙ ПРОВЕРКИ" in provider.calls[1][1]
    assert "description_too_short" in provider.calls[1][1]


async def test_invalid_json_is_corrected_on_retry(
    product: ProductInput,
    good_draft: dict[str, Any],
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory(["это не json", raw(good_draft)])
    result = await make_generator(provider, settings).generate(product)

    assert result.meta.attempts == 2
    assert result.meta.fallback_used is False
    assert "invalid_json" in provider.calls[1][1]


async def test_fallback_after_failed_validation(
    product: ProductInput,
    good_draft: dict[str, Any],
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    invalid = raw(good_draft, seo_title="x" * 100)
    provider = scripted_factory([invalid])
    result = await make_generator(provider, settings).generate(product)

    assert result.meta.attempts == 2
    assert result.meta.fallback_used is True
    assert result.meta.fallback_reason == "validation_failed"
    assert result.meta.validation.ok
    assert result.warnings
    expected = build_template_draft(product, detect_missing_fields(product))
    assert result.draft.seo_title == expected.seo_title


async def test_fallback_on_llm_error(
    product: ProductInput,
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory([LLMUnavailableError("нет сети")])
    result = await make_generator(provider, settings).generate(product)

    assert result.meta.fallback_used is True
    assert result.meta.fallback_reason == "llm_error:LLMUnavailableError"
    assert result.meta.attempts == 1
    assert any("нет сети" in warning for warning in result.warnings)
    assert result.meta.validation.ok


async def test_strict_mode_raises_validation_error(
    product: ProductInput,
    good_draft: dict[str, Any],
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    invalid = raw(good_draft, search_queries=["один"])
    provider = scripted_factory([invalid])
    generator = make_generator(provider, settings, max_attempts=1)

    with pytest.raises(ValidationFailedError) as error:
        await generator.generate(product, GenerateOptions(allow_fallback=False))
    assert any(getattr(item, "code", "") == "queries_count" for item in error.value.violations)


async def test_strict_mode_raises_llm_error(
    product: ProductInput,
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory([LLMUnavailableError("нет сети")])
    generator = make_generator(provider, settings)

    with pytest.raises(LLMUnavailableError):
        await generator.generate(product, GenerateOptions(allow_fallback=False))


async def test_strict_mode_with_invalid_json(
    product: ProductInput,
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory(["не json"])
    generator = make_generator(provider, settings, max_attempts=1)

    with pytest.raises(ValidationFailedError) as error:
        await generator.generate(product, GenerateOptions(allow_fallback=False))
    assert error.value.violations[0].code == "invalid_json"


async def test_template_provider_skips_llm(product: ProductInput, settings: Settings) -> None:
    result = await make_generator(TemplateProvider(), settings).generate(product)
    assert result.meta.attempts == 0
    assert result.meta.fallback_used is True
    assert result.meta.fallback_reason == "template_mode"
    assert result.meta.validation.ok
    assert result.warnings


async def test_fixture_provider_with_unknown_product_falls_back(
    product: ProductInput, settings: Settings
) -> None:
    unknown = product.model_copy(update={"name": "Неизвестный прибор"})
    result = await make_generator(FixtureProvider(), settings).generate(unknown)
    assert result.meta.fallback_used is True
    assert result.meta.fallback_reason.startswith("llm_error:")
    assert result.meta.validation.ok


async def test_partial_product_reports_missing_fields(
    partial_product: ProductInput,
    settings: Settings,
) -> None:
    result = await make_generator(FixtureProvider(), settings).generate(partial_product)
    assert result.meta.fallback_used is False
    assert [item.field for item in result.missing_fields] == ["класс точности"]


async def test_max_attempts_one_stops_after_first_failure(
    product: ProductInput,
    good_draft: dict[str, Any],
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory([raw(good_draft, commercial_block="мало")])
    result = await make_generator(provider, settings, max_attempts=1).generate(product)
    assert result.meta.attempts == 1
    assert result.meta.fallback_used is True
    assert len(provider.calls) == 1
