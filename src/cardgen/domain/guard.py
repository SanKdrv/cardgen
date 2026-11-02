"""Детерминированная проверка черновика: главный барьер против галлюцинаций."""

from __future__ import annotations

import re

from .facts import (
    BENIGN_CODES,
    KNOWN_UNITS,
    FactTable,
    canonical,
    claim_name,
    compact,
    find_claim_polarities,
)
from .models import CardDraft, GuardReport, GuardViolation, ProductInput

TITLE_MAX = 70
DESCRIPTION_MIN = 800
DESCRIPTION_MAX = 1200
DESCRIPTION_MIN_PARAGRAPHS = 2
DESCRIPTION_MAX_PARAGRAPHS = 3
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
_SPACED_CODE_RE = re.compile(r"\b(?:IP|RS|DN)\s?\d{2,4}[A-Za-zА-Яа-я0-9/-]*", re.IGNORECASE)
_META_PHRASES = (
    "в данных карточки",
    "в исходных данных",
    "параметры приведены",
    "описание составлено",
    "в карточке указаны",
)
_ATTRIBUTE_STOP_RE = re.compile(r"[,;]\s|\.\s|\n|\sи\s|\sили\s|\sпри\s|\sдля\s|\sс\s")
_ATTRIBUTE_WINDOW = 100
_LATIN_UNIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*([A-Za-z]{2,6})(?![A-Za-z0-9])")
_NON_UNIT_LATIN = frozenset({"max", "off", "on", "no", "ok", "ip", "rs", "dn", "dm"})
_ATTRIBUTE_ALIASES: dict[str, tuple[str, ...]] = {
    "диаметр корпуса": ("диаметр",),
    "класс точности": ("класс", "точность", "погрешность"),
    "диапазон измерений": ("диапазон", "давление"),
    "питание": ("питание", "напряжение"),
    "интерфейс": ("интерфейс", "протокол"),
    "выходной сигнал": ("выход", "сигнал"),
}


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

    paragraphs = [item for item in draft.seo_description.split("\n\n") if item.strip()]
    if not DESCRIPTION_MIN_PARAGRAPHS <= len(paragraphs) <= DESCRIPTION_MAX_PARAGRAPHS:
        _add(
            violations,
            "description_paragraphs",
            "seo_description",
            f"нужно {DESCRIPTION_MIN_PARAGRAPHS}–{DESCRIPTION_MAX_PARAGRAPHS} абзаца, "
            f"получено {len(paragraphs)}",
        )
    normalized_description = canonical(draft.seo_description)
    for phrase in _META_PHRASES:
        if phrase in normalized_description:
            _add(
                violations,
                "meta_phrase",
                "seo_description",
                f"фраза «{phrase}» комментирует источник данных, а не товар",
            )
            break

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
        if source_key in matched_sources:
            _add(
                violations,
                "duplicate_spec",
                "key_specs",
                f"характеристика «{source_key}» указана несколько раз под разными названиями",
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
    invented_quantities: dict[str, set[str]] = {}
    invented_units: dict[str, set[str]] = {}

    for field, text in texts.items():
        for number in facts.numbers_in(text):
            if number not in facts.numbers:
                invented_numbers.setdefault(number, set()).add(field)
        for code in facts.codes_in(text):
            if code and code not in BENIGN_CODES and code not in facts.compact_text:
                invented_codes.setdefault(code, set()).add(field)
        for spaced_code in _SPACED_CODE_RE.findall(text):
            normalized_code = compact(spaced_code)
            if normalized_code and normalized_code not in facts.compact_text:
                invented_codes.setdefault(normalized_code, set()).add(field)
        for number, unit in facts.quantities_in(text):
            if number in facts.numbers and (number, unit) not in facts.quantity_pairs:
                invented_quantities.setdefault(f"{number} {unit}", set()).add(field)
        for match in _LATIN_UNIT_RE.finditer(text):
            unit = canonical(match.group(2))
            if unit not in KNOWN_UNITS and unit not in _NON_UNIT_LATIN:
                invented_units.setdefault(unit, set()).add(field)

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
    for token, fields in list(invented_quantities.items()):
        if len(reported) >= MAX_TOKEN_VIOLATIONS:
            break
        if token in reported:
            continue
        reported.add(token)
        _add(
            violations,
            "invented_quantity",
            ", ".join(sorted(fields)),
            f"значение «{token}» не подтверждено исходной характеристикой",
        )
    for token, fields in list(invented_units.items()):
        if len(reported) >= MAX_TOKEN_VIOLATIONS:
            break
        if token in reported:
            continue
        reported.add(token)
        _add(
            violations,
            "unknown_unit",
            ", ".join(sorted(fields)),
            f"единица «{token}» отсутствует в исходных данных",
        )
    return reported


def _attribute_occurrences(normalized: str, source_keys: list[str]) -> list[tuple[int, int, str]]:
    """Находит названия характеристик и их короткие синонимы в тексте."""
    exact: list[tuple[int, int, str]] = []
    for key in source_keys:
        normalized_key = canonical(key)
        pattern = rf"(?<![а-яёa-z0-9]){re.escape(normalized_key)}(?![а-яёa-z0-9])"
        for match in re.finditer(pattern, normalized):
            exact.append((match.start(), match.end(), key))

    occurrences = list(exact)
    for key in source_keys:
        normalized_key = canonical(key)
        for target, aliases in _ATTRIBUTE_ALIASES.items():
            if target not in normalized_key:
                continue
            for alias in aliases:
                pattern = rf"(?<![а-яё]){re.escape(alias)}(?![а-яё])"
                for match in re.finditer(pattern, normalized):
                    if any(start <= match.start() < end for start, end, _ in exact):
                        continue
                    prefix = normalized[max(0, match.start() - 20) : match.start()]
                    tail = normalized[match.end() : match.end() + 20]
                    if alias == "диаметр" and tail.lstrip().startswith(("присоедин", "резьб")):
                        continue
                    if alias == "класс" and tail.lstrip().startswith(("защит", "точн", "изоляц")):
                        continue
                    if alias == "диапазон" and ("температур" in prefix or "рабоч" in prefix):
                        continue
                    occurrences.append((match.start(), match.end(), key))

    unique = set(occurrences)
    return sorted(unique)


def _check_attribute_numbers(
    product: ProductInput,
    facts: FactTable,
    draft: CardDraft,
    violations: list[GuardViolation],
    already_reported: set[str],
) -> None:
    """Проверяет числа рядом с названием характеристики.

    Без этого «класс точности — 20» проходил, если 20 встречалось в другом
    параметре: например, в резьбе M20×1,5. Синонимы («точность», «диаметр»)
    тоже учитываются.
    """
    source_keys = list(product.specs)
    if not source_keys:
        return

    texts = {
        "seo_title": draft.seo_title,
        "seo_description": draft.seo_description,
        "commercial_block": draft.commercial_block,
        "search_queries": " \n ".join(draft.search_queries),
    }

    for field, text in texts.items():
        normalized = canonical(text)
        occurrences = _attribute_occurrences(normalized, source_keys)
        for index, (start, end, key) in enumerate(occurrences):
            tail = normalized[end : end + _ATTRIBUTE_WINDOW]
            cut = len(tail)
            stop = _ATTRIBUTE_STOP_RE.search(tail)
            if stop:
                cut = min(cut, stop.start())
            for other_start, _, _ in occurrences[index + 1 :]:
                if other_start > end:
                    cut = min(cut, other_start - end)
                    break
            segment = tail[:cut]

            allowed = facts.numbers_in(product.specs[key])
            for number in facts.numbers_in(segment):
                token = f"{number}@{key}"
                if number in allowed or token in already_reported:
                    continue
                already_reported.add(token)
                _add(
                    violations,
                    "attribute_mismatch",
                    field,
                    f"число «{number}» рядом с «{key}» не встречается "
                    f"в значении этой характеристики",
                )

            source_codes = facts.codes_in(product.specs[key])
            segment_compact = compact(segment)
            segment_numbers = facts.numbers_in(segment)
            if (
                source_codes
                and segment_numbers
                and not any(code in segment_compact for code in source_codes)
            ):
                token = f"code@{key}@{start}"
                if token not in already_reported:
                    already_reported.add(token)
                    _add(
                        violations,
                        "attribute_mismatch",
                        field,
                        f"рядом с «{key}» не указан код из значения этой характеристики",
                    )


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
    fact_positive, fact_negative = find_claim_polarities(facts.text)
    for field, text in texts.items():
        positive, negative = find_claim_polarities(text)
        for stem in sorted(positive | negative):
            if stem in already_reported:
                continue
            if stem in positive and stem not in fact_positive:
                already_reported.add(stem)
                _add(
                    violations,
                    "invented_claim",
                    field,
                    f"упоминание «{claim_name(stem)}» отсутствует в исходных данных",
                )
                continue
            if stem in negative and stem not in fact_negative:
                already_reported.add(stem)
                _add(
                    violations,
                    "invented_negative_claim",
                    field,
                    f"отрицание «{claim_name(stem)}» не подтверждено исходными данными",
                )


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
    _check_attribute_numbers(product, facts, draft, violations, reported)
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
