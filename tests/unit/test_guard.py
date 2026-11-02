from __future__ import annotations

import copy
from typing import Any

from cardgen.facts import build_facts
from cardgen.guard import check_draft, summarize_violations
from cardgen.models import CardDraft, GuardViolation, ProductInput


def make_draft(good_draft: dict[str, Any]) -> CardDraft:
    return CardDraft.model_validate(good_draft)


def codes(report: Any) -> set[str]:
    return {violation.code for violation in report.violations}


def test_reference_draft_passes(product: ProductInput, good_draft: dict[str, Any]) -> None:
    report = check_draft(product, build_facts(product), make_draft(good_draft))
    assert report.ok, report.violations
    assert report.stats["title_chars"] == len(good_draft["seo_title"])


def test_title_too_long(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["seo_title"] = "Манометр " + "очень длинное название " * 4
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "title_too_long" in codes(report)


def test_title_trailing_dot(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["seo_title"] += "."
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "title_trailing_dot" in codes(report)


def test_title_exactly_limit_is_allowed(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["seo_title"] = "М" * 70
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "title_too_long" not in codes(report)


def test_description_length_bounds(product: ProductInput, good_draft: dict[str, Any]) -> None:
    facts = build_facts(product)
    short = copy.deepcopy(good_draft)
    short["seo_description"] = "коротко"
    assert "description_too_short" in codes(
        check_draft(product, facts, CardDraft.model_validate(short))
    )

    long = copy.deepcopy(good_draft)
    long["seo_description"] = "а" * 1201
    assert "description_too_long" in codes(
        check_draft(product, facts, CardDraft.model_validate(long))
    )


def test_queries_count(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["search_queries"] = draft["search_queries"][:2]
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "queries_count" in codes(report)


def test_commercial_length(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["commercial_block"] = "коротко"
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "commercial_length" in codes(report)


def test_invented_number(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["seo_description"] = draft["seo_description"].replace("1,6", "2,5")
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "invented_number" in codes(report)
    assert any("2.5" in violation.message for violation in report.violations)


def test_invented_code(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["seo_description"] += " Степень защиты IP65."
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "invented_code" in codes(report)


def test_invented_claim(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["seo_description"] += " Корпус из нержавеющей стали."
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "invented_claim" in codes(report)


def test_spec_value_changed(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["key_specs"][0]["value"] = "0–2,5 МПа"
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "spec_value_changed" in codes(report)


def test_unknown_spec(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["key_specs"].append({"name": "степень защиты", "value": "IP65"})
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "unknown_spec" in codes(report)


def test_missing_spec(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["key_specs"].pop()
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "missing_spec" in codes(report)


def test_duplicate_spec(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["key_specs"].append(copy.deepcopy(draft["key_specs"][0]))
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "duplicate_spec" in codes(report)


def test_markdown_artifacts(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["seo_title"] = f"**{draft['seo_title']}**"
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "markdown_artifacts" in codes(report)


def test_field_label_artifact(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft = copy.deepcopy(good_draft)
    draft["seo_title"] = f"SEO-заголовок: {draft['seo_title']}"
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert "field_label" in codes(report)


def test_numbers_from_description_are_allowed(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    draft = copy.deepcopy(good_draft)
    draft["seo_description"] += " Допустимая температура — от минус 40 до плюс 70 °C."
    report = check_draft(product, build_facts(product), CardDraft.model_validate(draft))
    assert report.ok, report.violations


def test_b2b_is_not_treated_as_invented_code(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    assert "B2B" in good_draft["seo_description"]
    report = check_draft(product, build_facts(product), make_draft(good_draft))
    assert not any("b2b" in violation.message.lower() for violation in report.violations)


def test_summarize_violations_limits_output() -> None:
    violations = [
        GuardViolation(code=f"code_{index}", field="field", message="сообщение")
        for index in range(7)
    ]
    summary = summarize_violations(violations, limit=5)
    assert len(summary.splitlines()) == 6
    assert "…и ещё 2" in summary
