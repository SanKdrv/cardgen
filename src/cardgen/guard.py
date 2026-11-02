"""Детерминированная проверка черновика: главный барьер против галлюцинаций."""

from __future__ import annotations

import re

from .facts import BENIGN_CODES, FactTable, canonical, claim_name, find_claim_stems
from .models import CardDraft, GuardReport, GuardViolation, ProductInput

TITLE_MAX = 70
DESCRIPTION_MIN = 800
DESCRIPTION_MAX = 1200
QUERIES_MIN = 3
QUERIES_MAX = 5
QUERY_MAX_CHARS = 120
COMMERCIAL_MIN = 80
COMMERCIAL_MAX = 900
MAX_TOKEN_VIOLATIONS = 15

_MARKDOWN_RE = re.compile(r"\*\*|__|```|^\s*#{1,6}\s", re.MULTILINE)
_LABEL_RE = re.compile(
    r"^\s*(seo[- ]?заголовок|seo[- ]?описание|заголовок|описание)\s*:",
    re.IGNORECASE,
)


def _add(violations: list[GuardViolation], code: str, field: str, message: str) -> None:
    violations.append(GuardViolation(code=code, field=field, message=message))


def _normalize_value(value: str) -> str:
    """Сравнение значений характеристик без учёта регистра, пробелов и пунктуации."""
    normalized = canonical(value)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.strip(".,;")


def _match_source_key(draft_key: str, source_keys: list[str]) -> str | None:
    wanted = canonical(draft_key)
    for source in source_keys:
        if canonical(source) == wanted:
            return source
    candidates = [
        source
        for source in source_keys
        if canonical(source) in wanted or wanted in canonical(source)
    ]
    return candidates[0] if len(candidates) == 1 else None


def _check_text_shape(draft: CardDraft, violations: list[GuardViolation]) -> None:
    if len(draft.seo_title) > TITLE_MAX:
        _add(
            violations,
            "title_too_long",
            "seo_title",
            f"заголовок длиной {len(draft.seo_title)} символов, максимум {TITLE_MAX}",
        )
    if draft.seo_title.endswith("."):
        _add(
            violations,
            "title_trailing_dot",
            "seo_title",
            "заголовок не должен заканчиваться точкой",
        )

    if len(draft.seo_description) < DESCRIPTION_MIN:
        _add(
            violations,
            "description_too_short",
            "seo_description",
            f"описание длиной {len(draft.seo_description)} символов, нужно от {DESCRIPTION_MIN}",
        )
    if len(draft.seo_description) > DESCRIPTION_MAX:
        _add(
            violations,
            "description_too_long",
            "seo_description",
            f"описание длиной {len(draft.seo_description)} символов, максимум {DESCRIPTION_MAX}",
        )

    if not QUERIES_MIN <= len(draft.search_queries) <= QUERIES_MAX:
        _add(
            violations,
            "queries_count",
            "search_queries",
            f"нужно от {QUERIES_MIN} до {QUERIES_MAX} запросов, "
            f"получено {len(draft.search_queries)}",
        )
    for query in draft.search_queries:
        if len(query) > QUERY_MAX_CHARS:
            _add(
                violations,
                "query_too_long",
                "search_queries",
                f"запрос «{query[:40]}…» длиннее {QUERY_MAX_CHARS} символов",
            )

    if not COMMERCIAL_MIN <= len(draft.commercial_block) <= COMMERCIAL_MAX:
        _add(
            violations,
            "commercial_length",
            "commercial_block",
            f"коммерческий блок должен быть {COMMERCIAL_MIN}–{COMMERCIAL_MAX} символов, "
            f"получено {len(draft.commercial_block)}",
        )


def _check_specs(
    product: ProductInput,
    draft: CardDraft,
    violations: list[GuardViolation],
) -> None:
    source_keys = list(product.specs)
    seen_draft_keys: set[str] = set()
    matched_sources: set[str] = set()

    for item in draft.key_specs:
        normalized_key = canonical(item.name)
        if normalized_key in seen_draft_keys:
            _add(
                violations,
                "duplicate_spec",
                "key_specs",
                f"характеристика «{item.name}» указана несколько раз",
            )
            continue
        seen_draft_keys.add(normalized_key)

        source_key = _match_source_key(item.name, source_keys)
        if source_key is None:
            _add(
                violations,
                "unknown_spec",
                "key_specs",
                f"характеристика «{item.name}» отсутствует во входных данных",
            )
            continue
        matched_sources.add(source_key)

        if _normalize_value(item.value) != _normalize_value(product.specs[source_key]):
            _add(
                violations,
                "spec_value_changed",
                "key_specs",
                f"значение «{item.name}» изменено: было «{product.specs[source_key]}», "
                f"стало «{item.value}»",
            )

    for source_key in source_keys:
        if source_key not in matched_sources:
            _add(
                violations,
                "missing_spec",
                "key_specs",
                f"характеристика «{source_key}» не попала в список key_specs",
            )


def _check_invented_tokens(
    facts: FactTable,
    draft: CardDraft,
    violations: list[GuardViolation],
) -> set[str]:
    texts = {
        "seo_title": draft.seo_title,
        "seo_description": draft.seo_description,
        "commercial_block": draft.commercial_block,
        "search_queries": " \n ".join(draft.search_queries),
    }
    invented_numbers: dict[str, set[str]] = {}
    invented_codes: dict[str, set[str]] = {}

    for field, text in texts.items():
        for number in facts.numbers_in(text):
            if number not in facts.numbers:
                invented_numbers.setdefault(number, set()).add(field)
        for code in facts.codes_in(text):
            if code and code not in BENIGN_CODES and code not in facts.compact_text:
                invented_codes.setdefault(code, set()).add(field)

    reported: set[str] = set()
    for token, fields in list(invented_numbers.items()):
        if len(reported) >= MAX_TOKEN_VIOLATIONS:
            break
        reported.add(token)
        _add(
            violations,
            "invented_number",
            ", ".join(sorted(fields)),
            f"число «{token}» отсутствует в исходных данных",
        )
    for token, fields in list(invented_codes.items()):
        if len(reported) >= MAX_TOKEN_VIOLATIONS:
            break
        if token in reported:
            continue
        reported.add(token)
        _add(
            violations,
            "invented_code",
            ", ".join(sorted(fields)),
            f"обозначение «{token}» отсутствует в исходных данных",
        )
    return reported


def _check_claims(
    facts: FactTable,
    draft: CardDraft,
    violations: list[GuardViolation],
    already_reported: set[str],
) -> None:
    texts = {
        "seo_title": draft.seo_title,
        "seo_description": draft.seo_description,
        "commercial_block": draft.commercial_block,
        "search_queries": " \n ".join(draft.search_queries),
    }
    for field, text in texts.items():
        for stem in find_claim_stems(text):
            if stem in already_reported:
                continue
            if stem in facts.text:
                continue
            already_reported.add(stem)
            _add(
                violations,
                "invented_claim",
                field,
                f"упоминание «{claim_name(stem)}» отсутствует в исходных данных",
            )
            break


def _check_markdown(draft: CardDraft, violations: list[GuardViolation]) -> None:
    fields = {
        "seo_title": draft.seo_title,
        "seo_description": draft.seo_description,
        "commercial_block": draft.commercial_block,
    }
    for field, text in fields.items():
        if _MARKDOWN_RE.search(text):
            _add(
                violations,
                "markdown_artifacts",
                field,
                "в тексте есть Markdown-разметка, нужен чистый текст",
            )
        if _LABEL_RE.match(text):
            _add(
                violations,
                "field_label",
                field,
                "в тексте остался служебный ярлык поля («SEO-заголовок:» и т.п.)",
            )


def check_draft(product: ProductInput, facts: FactTable, draft: CardDraft) -> GuardReport:
    """Проверяет черновик и возвращает отчёт со всеми найденными нарушениями."""
    violations: list[GuardViolation] = []

    _check_text_shape(draft, violations)
    _check_specs(product, draft, violations)
    reported = _check_invented_tokens(facts, draft, violations)
    _check_claims(facts, draft, violations, reported)
    _check_markdown(draft, violations)

    stats: dict[str, int | float | str] = {
        "title_chars": len(draft.seo_title),
        "description_chars": len(draft.seo_description),
        "queries_count": len(draft.search_queries),
        "commercial_chars": len(draft.commercial_block),
        "specs_count": len(draft.key_specs),
        "violations_count": len(violations),
    }
    return GuardReport(ok=not violations, violations=violations, stats=stats)


def summarize_violations(violations: list[GuardViolation], limit: int = 5) -> str:
    """Короткая сводка для письма об ошибке и корректирующего промпта."""
    parts = [f"[{item.code}] {item.field}: {item.message}" for item in violations[:limit]]
    if len(violations) > limit:
        parts.append(f"…и ещё {len(violations) - limit}")
    return "\n".join(parts)
