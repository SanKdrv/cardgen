from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from cardgen.domain.facts import build_facts
from cardgen.domain.guard import check_draft, summarize_violations
from cardgen.domain.models import CardDraft, GuardViolation, ProductInput


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


def _draft_with_description(
    good_draft: dict[str, Any], addition: str
) -> tuple[CardDraft, dict[str, Any]]:
    payload = copy.deepcopy(good_draft)
    payload["seo_description"] = f"{payload['seo_description']} {addition}"
    return CardDraft.model_validate(payload), payload


def test_invented_unit_is_rejected(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft, _ = _draft_with_description(good_draft, "Рабочее давление — 1,6 бар.")
    report = check_draft(product, build_facts(product), draft)
    assert "invented_quantity" in codes(report)


def test_number_from_other_attribute_is_rejected(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    for addition in ("Рабочее давление — 100 МПа.", "Диаметр корпуса — 1,5 мм."):
        draft, _ = _draft_with_description(good_draft, addition)
        report = check_draft(product, build_facts(product), draft)
        assert "invented_quantity" in codes(report)


def test_spaced_protection_code_is_rejected(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    draft, _ = _draft_with_description(good_draft, "Степень защиты IP 40.")
    report = check_draft(product, build_facts(product), draft)
    assert "invented_code" in codes(report)


def test_negation_and_new_materials_are_rejected(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    additions = (
        "Подходит для агрессивных сред.",
        "Мембрана из керамики.",
        "Сертификат соответствия прилагается.",
        "Межповерочный интервал — 2 года.",
        "Исполнение ATEX.",
    )
    for addition in additions:
        draft, _ = _draft_with_description(good_draft, addition)
        report = check_draft(product, build_facts(product), draft)
        assert "invented_claim" in codes(report), addition


def test_same_number_with_other_unit_on_partial_product(
    partial_product: ProductInput,
    fixture_drafts: dict[str, Any],
) -> None:
    payload = copy.deepcopy(fixture_drafts[partial_product.name])
    payload["seo_description"] += " Рабочий сигнал — 20 мА."
    report = check_draft(
        partial_product, build_facts(partial_product), CardDraft.model_validate(payload)
    )
    assert "invented_quantity" in codes(report)


def test_unitless_number_from_other_attribute_is_rejected(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    draft, _ = _draft_with_description(good_draft, "Класс точности — 100.")
    report = check_draft(product, build_facts(product), draft)
    assert "attribute_mismatch" in codes(report)


def test_attribute_swap_with_existing_number_is_rejected(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    draft, _ = _draft_with_description(good_draft, "Диапазон измерений — 1,5 МПа.")
    report = check_draft(product, build_facts(product), draft)
    assert "attribute_mismatch" in codes(report)


def test_equivalent_latin_unit_is_allowed(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    draft, _ = _draft_with_description(good_draft, "Диаметр корпуса — 100 mm.")
    report = check_draft(product, build_facts(product), draft)
    assert "invented_quantity" not in codes(report)


def test_changed_latin_unit_is_rejected(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft, _ = _draft_with_description(good_draft, "Рабочее давление — 1,6 bar.")
    report = check_draft(product, build_facts(product), draft)
    assert "invented_quantity" in codes(report)


def test_hyphenated_code_is_rejected(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft, _ = _draft_with_description(good_draft, "Степень защиты IP-40.")
    report = check_draft(product, build_facts(product), draft)
    assert "invented_code" in codes(report)


def test_duplicate_spec_under_different_name_is_rejected(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    payload = copy.deepcopy(good_draft)
    payload["key_specs"].append({"name": "класс точности прибора", "value": "1,5"})
    report = check_draft(product, build_facts(product), CardDraft.model_validate(payload))
    assert "duplicate_spec" in codes(report)


def test_unknown_pressure_units_are_rejected(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    for addition in (
        "Рабочее давление — 1,6 psi.",
        "Рабочее давление — 1,6 атм.",
        "Рабочее давление — 1,6 Па.",
        "Температура — 70 °F.",
    ):
        draft, _ = _draft_with_description(good_draft, addition)
        report = check_draft(product, build_facts(product), draft)
        assert "invented_quantity" in codes(report), addition


def test_completely_unknown_unit_is_rejected(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    draft, _ = _draft_with_description(good_draft, "Рабочее давление — 1,6 quux.")
    report = check_draft(product, build_facts(product), draft)
    assert "unknown_unit" in codes(report)


def test_attribute_aliases_and_codes_are_checked(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    for addition in (
        "Диаметр — 1,5.",
        "Точность — 2.",
        "Диапазон — 1,5.",
        "Присоединение — 1.",
    ):
        draft, _ = _draft_with_description(good_draft, addition)
        report = check_draft(product, build_facts(product), draft)
        assert "attribute_mismatch" in codes(report), addition


def test_negated_claim_in_source_is_not_a_permission(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    negative_product = product.model_copy(
        update={
            "description": ("Прибор не предназначен для агрессивных сред. " "Поверка не требуется.")
        }
    )
    payload = copy.deepcopy(good_draft)
    payload["seo_description"] = payload["seo_description"].replace("неагрессивных", "агрессивных")
    payload["seo_description"] += " Прибор проходит поверку."
    report = check_draft(
        negative_product,
        build_facts(negative_product),
        CardDraft.model_validate(payload),
    )
    assert "invented_claim" in codes(report)


def test_negative_claim_itself_is_allowed_when_present(
    product: ProductInput, good_draft: dict[str, Any]
) -> None:
    negative_product = product.model_copy(
        update={"description": "Прибор не предназначен для агрессивных сред."}
    )
    payload = copy.deepcopy(good_draft)
    payload["seo_description"] = payload["seo_description"].replace(
        "неагрессивных", "неагрессивных"
    )
    report = check_draft(
        negative_product,
        build_facts(negative_product),
        CardDraft.model_validate(payload),
    )
    assert "invented_negative_claim" not in codes(report)


def test_description_paragraph_count(product: ProductInput, good_draft: dict[str, Any]) -> None:
    paragraphs = good_draft["seo_description"].split("\n\n")

    two_paragraphs = copy.deepcopy(good_draft)
    two_paragraphs["seo_description"] = f"{paragraphs[0]}\n\n{' '.join(paragraphs[1:])}"
    report = check_draft(product, build_facts(product), CardDraft.model_validate(two_paragraphs))
    assert "description_paragraphs" not in codes(report)

    four_paragraphs = copy.deepcopy(good_draft)
    four_paragraphs["seo_description"] = (
        f"{paragraphs[0]}\n\n{paragraphs[1]}\n\n{paragraphs[2]}\n\nДополнительный абзац."
    )
    report = check_draft(product, build_facts(product), CardDraft.model_validate(four_paragraphs))
    assert "description_paragraphs" in codes(report)


def test_meta_phrase_is_rejected(product: ProductInput, good_draft: dict[str, Any]) -> None:
    draft, _ = _draft_with_description(
        good_draft, "В карточке указаны только характеристики из исходных данных."
    )
    report = check_draft(product, build_facts(product), draft)
    assert "meta_phrase" in codes(report)


def test_all_fixture_drafts_pass_guard(
    product: ProductInput,
    partial_product: ProductInput,
    fixture_drafts: dict[str, Any],
) -> None:
    for item in (product, partial_product):
        report = check_draft(
            item,
            build_facts(item),
            CardDraft.model_validate(fixture_drafts[item.name]),
        )
        assert report.ok, report.violations


def test_committed_examples_pass_guard(demo_products: list[dict[str, Any]]) -> None:
    root = Path(__file__).resolve().parents[2]
    names = [
        "01-manometr-pokazyvayuschiy-dm-02",
        "02-termometr-bimetallicheskiy-tb-1",
    ]
    for payload, name in zip(demo_products, names, strict=True):
        product = ProductInput.model_validate(payload)
        example = json.loads(
            (root / "examples" / "output" / f"{name}.json").read_text(encoding="utf-8")
        )
        report = check_draft(
            product,
            build_facts(product),
            CardDraft.model_validate(example["draft"]),
        )
        assert report.ok, (name, report.violations)
