"""Детерминированный шаблонный генератор.

Используется, когда LLM недоступна или её ответ не прошёл проверку. Не
обращается к модели и не может выдумать факт: все значения берутся из входа.
"""

from __future__ import annotations

import re

from ..domain.guard import (
    COMMERCIAL_MAX,
    COMMERCIAL_MIN,
    DESCRIPTION_MAX,
    DESCRIPTION_MIN,
    TITLE_MAX,
)
from ..domain.models import CardDraft, KeySpecItem, MissingField, ProductInput

_SAFE_SENTENCES = (
    "Информация в карточке опирается только на переданные технические данные.",
    "Перед публикацией рекомендуется сверить формулировки с техническим специалистом.",
    "Для подбора модификации уточните условия эксплуатации и требования к монтажу.",
    "Описание не заменяет официальную документацию производителя.",
    "При подготовке коммерческого предложения уточните доступность позиции и условия поставки.",
    "Карточка может быть дополнена после получения недостающих характеристик.",
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_MARKDOWN_CLEAN_RE = re.compile(r"[*_`#>]+")
_CATEGORY_SINGULAR = {
    "манометры": "манометр",
    "термометры": "термометр",
    "преобразователи давления": "преобразователь давления",
    "расходомеры": "расходомер",
    "уровнемеры": "уровнемер",
    "калибраторы": "калибратор",
}


def _plain_text(value: str) -> str:
    """Убирает Markdown, чтобы шаблон не копировал разметку в карточку."""
    return _MARKDOWN_CLEAN_RE.sub("", value).strip()


def _clean_phrase(value: str) -> str:
    return _plain_text(value).strip(" .,;:-—–")


def _truncate(text: str, limit: int) -> str:
    """Аккуратно обрезает текст по границе предложения или слова."""
    if len(text) <= limit:
        return text.strip()
    cut = text[:limit]
    for separator in (". ", "! ", "? ", "; ", ", ", " "):
        index = cut.rfind(separator)
        if index >= limit // 2:
            return cut[: index + len(separator)].rstrip()
    return cut.rstrip()


def _build_title(product: ProductInput) -> str:
    name = _clean_phrase(product.name)
    manufacturer = _clean_phrase(product.manufacturer)
    with_manufacturer = _clean_phrase(f"{name} — {manufacturer}")
    if len(with_manufacturer) <= TITLE_MAX:
        return with_manufacturer
    if len(name) <= TITLE_MAX:
        return name
    return _clean_phrase(_truncate(name, TITLE_MAX))


def _first_sentences(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if not text:
        return ""
    sentences = _SENTENCE_SPLIT_RE.split(text)
    collected: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*collected, sentence]).strip()
        if len(candidate) > limit and collected:
            break
        collected.append(sentence)
        if len(candidate) >= limit:
            break
    return " ".join(collected).strip()


def _build_description(product: ProductInput, missing: list[MissingField]) -> str:
    name = _clean_phrase(product.name)
    manufacturer = _clean_phrase(product.manufacturer)
    category = _clean_phrase(product.category or "контрольно-измерительный прибор").lower()
    category = _CATEGORY_SINGULAR.get(category, category)
    intro = f"{name} — {category} производства {manufacturer}."
    purpose = _first_sentences(_plain_text(product.description), 420)
    if purpose and purpose.lower() not in intro.lower():
        intro = f"{intro} {purpose}"
    intro = _truncate(intro, 500)

    paragraphs = [intro]

    if product.specs:
        lines = "\n".join(
            f"— {_plain_text(key)}: {_plain_text(value)}." for key, value in product.specs.items()
        )
        paragraphs.append(f"Ключевые характеристики:\n{lines}")

    closing = (
        "Прибор предназначен для задач, где требуется контролировать параметры "
        "технологического процесса и подбирать оборудование по техническим "
        "характеристикам. Карточка помогает сравнить исполнение с другими приборами "
        "и подготовить коммерческое предложение."
    )
    if missing:
        fields = ", ".join(item.field for item in missing)
        closing = (
            f"{closing} Для полной карточки уточните: {fields}. После уточнения описание "
            "можно расширить и дополнить характеристиками, которых не хватает."
        )
    paragraphs.append(closing)

    text = "\n\n".join(paragraphs)
    if len(text) > DESCRIPTION_MAX:
        text = _truncate(text, DESCRIPTION_MAX)
        if len([item for item in text.split("\n\n") if item.strip()]) < 2:
            text = f"{text}\n\n{_SAFE_SENTENCES[0]}"
    if len(text) > DESCRIPTION_MAX:
        text = text[:DESCRIPTION_MAX]

    index = 0
    while len(text) < DESCRIPTION_MIN:
        text = f"{text} {_SAFE_SENTENCES[index % len(_SAFE_SENTENCES)]}"
        index += 1
    return text


def _build_commercial_block(product: ProductInput, missing: list[MissingField]) -> str:
    name = _clean_phrase(product.name)
    manufacturer = _clean_phrase(product.manufacturer)
    highlighted = list(product.specs.items())[:3]
    if highlighted:
        specs_phrase = "; ".join(
            f"{_plain_text(key)} — {_plain_text(value)}" for key, value in highlighted
        )
        block = f"{name} от {manufacturer}: {specs_phrase}."
    else:
        block = f"{name} от {manufacturer}."

    block += (
        " Прибор стоит предложить предприятиям, которым нужно подобрать оборудование "
        "по техническим характеристикам и условиям эксплуатации."
    )
    if missing:
        block += f" Перед отправкой предложения уточните: {', '.join(m.field for m in missing)}."
    else:
        block += " Перед отправкой предложения проверьте комплектацию и условия поставки."

    if len(block) > COMMERCIAL_MAX:
        block = _truncate(block, COMMERCIAL_MAX)
    while len(block) < COMMERCIAL_MIN:
        block = f"{block} {_SAFE_SENTENCES[0]}"
    return block


def _build_queries(product: ProductInput) -> list[str]:
    category = _clean_phrase(product.category or "прибор")
    name = _clean_phrase(product.name)
    manufacturer = _clean_phrase(product.manufacturer)
    base = _clean_phrase(_truncate(name, 90))
    candidates = [
        base,
        f"{base} купить",
        f"{base} характеристики",
        f"{base} {manufacturer}",
        f"{category} {manufacturer}",
    ]
    result: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        query = _truncate(" ".join(candidate.split()), 120)
        key = query.casefold()
        if query and key not in seen:
            seen.add(key)
            result.append(query)
    return result[:5]


def build_template_draft(product: ProductInput, missing: list[MissingField]) -> CardDraft:
    """Собирает валидный по построению черновик без обращения к LLM."""
    return CardDraft(
        seo_title=_build_title(product),
        seo_description=_build_description(product, missing),
        key_specs=[KeySpecItem(name=key, value=value) for key, value in product.specs.items()],
        search_queries=_build_queries(product),
        commercial_block=_build_commercial_block(product, missing),
    )
