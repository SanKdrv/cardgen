from __future__ import annotations

from cardgen.application.fallback import build_template_draft
from cardgen.application.render import to_markdown
from cardgen.domain.facts import build_facts, detect_missing_fields
from cardgen.domain.guard import check_draft
from cardgen.domain.models import (
    CardDraft,
    CardMeta,
    CardResult,
    KeySpecItem,
    MissingField,
    ProductInput,
)


def build_result(product: ProductInput) -> CardResult:
    missing = detect_missing_fields(product)
    draft = build_template_draft(product, missing)
    report = check_draft(product, build_facts(product), draft)
    meta = CardMeta(
        provider="template",
        model="deterministic-template",
        attempts=0,
        fallback_used=True,
        fallback_reason="template_mode",
        latency_ms=12,
        prompt_version="test",
        validation=report,
    )
    return CardResult(
        product=product,
        draft=draft,
        missing_fields=missing,
        warnings=["тестовое предупреждение"],
        meta=meta,
    )


def test_markdown_contains_all_sections(product: ProductInput) -> None:
    markdown = to_markdown(build_result(product))
    assert markdown.startswith(f"# {product.name}")
    assert "## SEO-заголовок" in markdown
    assert "## SEO-описание" in markdown
    assert "## Ключевые характеристики" in markdown
    assert "| Характеристика | Значение |" in markdown
    assert "## Поисковые запросы" in markdown
    assert "## Коммерческий блок" in markdown
    assert "## Предупреждения" in markdown
    assert "Fallback: да (template_mode)" in markdown
    assert "тестовое предупреждение" in markdown


def test_markdown_shows_missing_fields(partial_product: ProductInput) -> None:
    markdown = to_markdown(build_result(partial_product))
    assert "## Недостающие данные" in markdown
    assert "класс точности" in markdown
    assert "данных нет" in markdown


def test_markdown_escapes_pipes(product: ProductInput) -> None:
    draft = CardDraft(
        seo_title="Заголовок",
        seo_description="Описание",
        key_specs=[KeySpecItem(name="труба", value="1|2")],
        search_queries=["запрос"],
        commercial_block="Блок",
    )
    result = build_result(product).model_copy(update={"draft": draft})
    markdown = to_markdown(result)
    assert r"| труба | 1\|2 |" in markdown


def test_markdown_without_missing_and_warnings(product: ProductInput) -> None:
    result = build_result(product).model_copy(update={"missing_fields": [], "warnings": []})
    markdown = to_markdown(result)
    assert "## Недостающие данные" not in markdown
    assert "## Предупреждения" not in markdown


def test_markdown_lists_missing_hint() -> None:
    result = build_result(ProductInput(name="Прибор", manufacturer="Завод"))
    markdown = to_markdown(result)
    assert "**диапазон измерений**" in markdown
    assert "уточните пределы шкалы" in markdown
    assert isinstance(result.missing_fields[0], MissingField)
