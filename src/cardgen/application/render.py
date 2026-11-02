"""Markdown-представление результата для копирования и ревью."""

from __future__ import annotations

from ..domain.guard import DESCRIPTION_MAX, DESCRIPTION_MIN, TITLE_MAX
from ..domain.models import CardResult


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def to_markdown(result: CardResult) -> str:
    draft = result.draft
    product = result.product
    lines: list[str] = [
        f"# {product.name}",
        "",
        f"- **Производитель:** {product.manufacturer}",
    ]
    if product.category:
        lines.append(f"- **Категория:** {product.category}")
    lines.extend(
        [
            "",
            f"## SEO-заголовок ({len(draft.seo_title)}/{TITLE_MAX})",
            "",
            draft.seo_title,
            "",
            f"## SEO-описание ({len(draft.seo_description)} символов)",
            "",
            draft.seo_description,
            "",
            "## Ключевые характеристики",
            "",
            "| Характеристика | Значение |",
            "| --- | --- |",
        ]
    )
    lines.extend(
        f"| {_escape_cell(item.name)} | {_escape_cell(item.value)} |" for item in draft.key_specs
    )

    lines.extend(["", "## Поисковые запросы", ""])
    lines.extend(f"{number}. {query}" for number, query in enumerate(draft.search_queries, start=1))

    lines.extend(["", "## Коммерческий блок", "", draft.commercial_block, ""])

    if result.missing_fields:
        lines.extend(["## Недостающие данные", ""])
        lines.extend(
            f"- **{item.field}** — {item.value}: {item.hint}" for item in result.missing_fields
        )
        lines.append("")

    if result.warnings:
        lines.extend(["## Предупреждения", ""])
        lines.extend(f"- {warning}" for warning in result.warnings)
        lines.append("")

    meta = result.meta
    lines.extend(
        [
            "---",
            "",
            "## Служебная информация",
            "",
            f"- Провайдер: `{meta.provider}`",
            f"- Модель: `{meta.model}`",
            f"- Попыток обращения к LLM: {meta.attempts}",
            f"- Версия промпта: `{meta.prompt_version}`",
            f"- Проверка: {'пройдена' if meta.validation.ok else 'не пройдена'}",
            f"- Fallback: {'да' if meta.fallback_used else 'нет'}"
            + (f" ({meta.fallback_reason})" if meta.fallback_reason else ""),
            f"- Длина описания: {len(draft.seo_description)} "
            f"(норма {DESCRIPTION_MIN}–{DESCRIPTION_MAX})",
            "",
        ]
    )
    return "\n".join(lines)
