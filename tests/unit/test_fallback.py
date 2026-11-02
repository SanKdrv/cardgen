from __future__ import annotations

from cardgen.facts import build_facts, detect_missing_fields
from cardgen.fallback import build_template_draft
from cardgen.guard import (
    COMMERCIAL_MAX,
    COMMERCIAL_MIN,
    DESCRIPTION_MAX,
    DESCRIPTION_MIN,
    QUERIES_MAX,
    QUERIES_MIN,
    TITLE_MAX,
    check_draft,
)
from cardgen.models import ProductInput


def test_template_passes_guard_for_demo_products(
    product: ProductInput, partial_product: ProductInput
) -> None:
    for item in (product, partial_product):
        missing = detect_missing_fields(item)
        draft = build_template_draft(item, missing)
        report = check_draft(item, build_facts(item), draft)
        assert report.ok, report.violations
        assert DESCRIPTION_MIN <= len(draft.seo_description) <= DESCRIPTION_MAX
        assert len(draft.seo_title) <= TITLE_MAX
        assert COMMERCIAL_MIN <= len(draft.commercial_block) <= COMMERCIAL_MAX
        assert QUERIES_MIN <= len(draft.search_queries) <= QUERIES_MAX
        assert len(draft.key_specs) == len(item.specs)


def test_template_is_deterministic(product: ProductInput) -> None:
    missing = detect_missing_fields(product)
    first = build_template_draft(product, missing)
    second = build_template_draft(product, missing)
    assert first == second


def test_template_without_specs_and_description() -> None:
    product = ProductInput(name="Прибор", manufacturer="Завод", specs={}, description="")
    missing = detect_missing_fields(product)
    draft = build_template_draft(product, missing)
    report = check_draft(product, build_facts(product), draft)
    assert report.ok, report.violations
    assert draft.key_specs == []
    assert "уточните" in draft.seo_description


def test_template_with_very_long_name() -> None:
    product = ProductInput(
        name="Н" * 200,
        manufacturer="З" * 200,
        specs={"диапазон измерений": "0–1 МПа"},
        description="",
    )
    missing = detect_missing_fields(product)
    draft = build_template_draft(product, missing)
    report = check_draft(product, build_facts(product), draft)
    assert report.ok, report.violations
    assert len(draft.seo_title) <= TITLE_MAX
    assert all(len(query) <= 120 for query in draft.search_queries)


def test_template_queries_are_unique(product: ProductInput) -> None:
    draft = build_template_draft(product, detect_missing_fields(product))
    assert len(draft.search_queries) == len({query.casefold() for query in draft.search_queries})
