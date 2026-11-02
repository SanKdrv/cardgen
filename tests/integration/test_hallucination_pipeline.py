from __future__ import annotations

import copy
import json
from collections.abc import Callable
from typing import Any

import pytest

from cardgen.application.fallback import build_template_draft
from cardgen.application.pipeline import CardGenerator
from cardgen.core.errors import ValidationFailedError
from cardgen.domain.facts import build_facts, detect_missing_fields
from cardgen.domain.guard import check_draft
from cardgen.domain.models import CardDraft, GenerateOptions, ProductInput
from cardgen.infrastructure.config import Settings

from ..conftest import ScriptedProvider

Draft = dict[str, Any]
Mutation = Callable[[Draft], Draft]


def _copy(draft: Draft) -> Draft:
    return copy.deepcopy(draft)


def _unit_swap(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] = payload["seo_description"].replace("1,6 МПа", "1,6 бар")
    return payload


def _number_swap(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_title"] = payload["seo_title"].replace("1,5", "2,5")
    return payload


def _unitless_attribute_swap(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += " Класс точности — 100."
    return payload


def _invented_claim(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += " Корпус из нержавеющей стали."
    return payload


def _invented_code(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += " Степень защиты IP65."
    return payload


def _spaced_code(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += " Степень защиты IP 40."
    return payload


def _latin_changed_unit(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += " Рабочее давление — 1,6 bar."
    return payload


def _unknown_unit(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += " Рабочее давление — 1,6 psi."
    return payload


def _completely_unknown_unit(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += " Рабочее давление — 1,6 quux."
    return payload


def _alias_attribute(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += " Диаметр — 1,5."
    return payload


def _code_fragment(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += " Присоединение — 1."
    return payload


def _semantic_claim(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += " Присоединение фланцевое."
    return payload


def _missing_spec(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["key_specs"].pop()
    return payload


def _changed_spec(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["key_specs"][0]["value"] = "0–2,5 МПа"
    return payload


def _extra_spec(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["key_specs"].append({"name": "степень защиты", "value": "IP65"})
    return payload


def _extra_paragraph(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += "\n\nДополнительный абзац без новых фактов."
    return payload


def _meta_phrase(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["seo_description"] += " В карточке указаны только характеристики."
    return payload


def _invented_query(draft: Draft) -> Draft:
    payload = _copy(draft)
    payload["search_queries"][0] = "манометр 2,5 МПа"
    return payload


MUTATIONS: tuple[tuple[str, Mutation, str], ...] = (
    ("unit_swap", _unit_swap, "invented_quantity"),
    ("number_swap", _number_swap, "invented_number"),
    ("unitless_attribute_swap", _unitless_attribute_swap, "attribute_mismatch"),
    ("invented_claim", _invented_claim, "invented_claim"),
    ("invented_code", _invented_code, "invented_code"),
    ("spaced_code", _spaced_code, "invented_code"),
    ("latin_changed_unit", _latin_changed_unit, "invented_quantity"),
    ("unknown_unit", _unknown_unit, "invented_quantity"),
    ("completely_unknown_unit", _completely_unknown_unit, "unknown_unit"),
    ("alias_attribute", _alias_attribute, "attribute_mismatch"),
    ("code_fragment", _code_fragment, "attribute_mismatch"),
    ("semantic_claim", _semantic_claim, "invented_claim"),
    ("missing_spec", _missing_spec, "missing_spec"),
    ("changed_spec", _changed_spec, "spec_value_changed"),
    ("extra_spec", _extra_spec, "unknown_spec"),
    ("extra_paragraph", _extra_paragraph, "description_paragraphs"),
    ("meta_phrase", _meta_phrase, "meta_phrase"),
    ("invented_query", _invented_query, "invented_number"),
)


def _raw(draft: Draft) -> str:
    return json.dumps(draft, ensure_ascii=False)


def _generator(
    provider: ScriptedProvider,
    settings: Settings,
    max_attempts: int = 1,
) -> CardGenerator:
    return CardGenerator(provider, settings.model_copy(update={"max_attempts": max_attempts}))


@pytest.mark.parametrize(
    ("name", "mutate", "expected_code"),
    MUTATIONS,
    ids=[item[0] for item in MUTATIONS],
)
def test_each_hallucination_is_rejected_by_guard(
    name: str,
    mutate: Mutation,
    expected_code: str,
    product: ProductInput,
    good_draft: Draft,
) -> None:
    del name
    payload = mutate(good_draft)
    report = check_draft(product, build_facts(product), CardDraft.model_validate(payload))
    assert not report.ok
    assert expected_code in {violation.code for violation in report.violations}


@pytest.mark.parametrize(
    ("name", "mutate", "expected_code"),
    MUTATIONS,
    ids=[item[0] for item in MUTATIONS],
)
async def test_pipeline_never_returns_hallucination(
    name: str,
    mutate: Mutation,
    expected_code: str,
    product: ProductInput,
    good_draft: Draft,
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    del name
    provider = scripted_factory([_raw(mutate(good_draft))])
    result = await _generator(provider, settings).generate(
        product, GenerateOptions(allow_fallback=True)
    )

    assert result.meta.fallback_used is True
    assert result.meta.fallback_reason == "validation_failed"
    assert result.meta.validation.ok is True
    assert result.meta.attempts == 1
    assert result.draft == build_template_draft(product, detect_missing_fields(product))
    assert any(expected_code in warning for warning in result.warnings), result.warnings


@pytest.mark.parametrize(
    ("name", "mutate", "expected_code"),
    MUTATIONS,
    ids=[item[0] for item in MUTATIONS],
)
async def test_strict_pipeline_raises_instead_of_falling_back(
    name: str,
    mutate: Mutation,
    expected_code: str,
    product: ProductInput,
    good_draft: Draft,
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    del name
    provider = scripted_factory([_raw(mutate(good_draft))])
    with pytest.raises(ValidationFailedError) as error:
        await _generator(provider, settings).generate(
            product, GenerateOptions(allow_fallback=False)
        )
    assert expected_code in {getattr(item, "code", "") for item in error.value.violations}


async def test_retry_receives_specific_violation_and_succeeds(
    product: ProductInput,
    good_draft: Draft,
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    provider = scripted_factory([_raw(_unit_swap(good_draft)), _raw(good_draft)])
    result = await _generator(provider, settings, max_attempts=2).generate(product)

    assert result.meta.fallback_used is False
    assert result.meta.attempts == 2
    assert len(provider.calls) == 2
    assert "invented_quantity" in provider.calls[1][1]
    assert "1.6 бар" in provider.calls[1][1]


async def test_partial_product_with_swapped_unit_never_leaks(
    partial_product: ProductInput,
    fixture_drafts: dict[str, Any],
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    payload = copy.deepcopy(fixture_drafts[partial_product.name])
    payload["seo_description"] += " Рабочий сигнал — 20 мА."
    provider = scripted_factory([_raw(payload)])
    result = await _generator(provider, settings).generate(partial_product)

    assert result.meta.fallback_used is True
    assert result.meta.validation.ok is True
    assert "20 мА" not in result.draft.seo_description
    assert "20 мА" not in result.draft.commercial_block


async def test_negative_source_cannot_be_turned_positive(
    product: ProductInput,
    good_draft: Draft,
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    negative_product = product.model_copy(
        update={
            "description": ("Прибор не предназначен для агрессивных сред. " "Поверка не требуется.")
        }
    )
    payload = _copy(good_draft)
    payload["seo_description"] = payload["seo_description"].replace("неагрессивных", "агрессивных")
    payload["seo_description"] += " Прибор проходит поверку."
    provider = scripted_factory([_raw(payload)])

    with pytest.raises(ValidationFailedError) as error:
        await _generator(provider, settings).generate(
            negative_product, GenerateOptions(allow_fallback=False)
        )
    assert "invented_claim" in {getattr(item, "code", "") for item in error.value.violations}


async def test_absent_field_hallucination_never_leaks(
    partial_product: ProductInput,
    fixture_drafts: dict[str, Any],
    settings: Settings,
    scripted_factory: Callable[[list[str | Exception]], ScriptedProvider],
) -> None:
    payload = _copy(fixture_drafts[partial_product.name])
    payload["seo_description"] += " Класс точности — 1,5."
    provider = scripted_factory([_raw(payload)])
    result = await _generator(provider, settings).generate(partial_product)

    assert result.meta.fallback_used is True
    assert result.meta.validation.ok is True
    assert "Класс точности — 1,5" not in result.draft.seo_description
    assert any("missing_field_mentioned" in warning for warning in result.warnings)


def test_equivalent_latin_unit_is_not_rejected(product: ProductInput, good_draft: Draft) -> None:
    payload = _copy(good_draft)
    payload["seo_description"] += " Диаметр корпуса — 100 mm."
    report = check_draft(product, build_facts(product), CardDraft.model_validate(payload))
    assert report.ok, report.violations
