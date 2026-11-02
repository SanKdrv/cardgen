"""Детерминированный шаблонный генератор.

Используется, когда LLM недоступна или её ответ не прошёл проверку. Не
обращается к модели и не может выдумать факт: все значения берутся из входа.
"""

from __future__ import annotations

import re

from .guard import COMMERCIAL_MAX, COMMERCIAL_MIN, DESCRIPTION_MAX, DESCRIPTION_MIN, TITLE_MAX
from .models import CardDraft, KeySpecItem, MissingField, ProductInput

_SAFE_SENTENCES = (
    "Информация в карточке опирается только на переданные технические данные.",
    "Перед публикацией рекомендуется сверить формулировки с техническим специалистом.",
    "Для подбора модификации уточните условия эксплуатации и требования к монтажу.",
    "Описание не заменяет официальную документацию производителя.",
    "При подготовке коммерческого предложения уточните доступность позиции и условия поставки.",
    "Карточка может быть дополнена после получения недостающих характеристик.",
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


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
    with_manufacturer = f"{product.name} — {product.manufacturer}"
    if len(with_manufacturer) <= TITLE_MAX:
        return with_manufacturer
    if len(product.name) <= TITLE_MAX:
        return product.name
    return _truncate(product.name, TITLE_MAX)


def _first_sentences(text: str, limit: int) -> str:
    text = text.strip()
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
    category = (product.category or "контрольно-измерительный прибор").lower()
    intro = f"{product.name} — {category} производства {product.manufacturer}."
    purpose = _first_sentences(product.description, 420)
    if purpose and purpose.lower() not in intro.lower():
        intro = f"{intro} {purpose}"

    paragraphs = [intro]

    if product.specs:
        lines = "\n".join(f"— {key}: {value}." for key, value in product.specs.items())
        paragraphs.append(f"Ключевые характеристики:\n{lines}")

    paragraphs.append(
        "Прибор предназначен для задач, где требуется контролировать параметры "
        "технологического процесса и подбирать оборудование по техническим "
        "характеристикам. Карточка помогает сравнить исполнение с другими приборами "
        "и подготовить коммерческое предложение."
    )

    if missing:
        fields = ", ".join(item.field for item in missing)
        paragraphs.append(
            f"Для полной карточки уточните: {fields}. После уточнения описание можно "
            "расширить и дополнить характеристиками, которых сейчас нет в исходных данных."
        )

    text = "\n\n".join(paragraphs)
    index = 0
    while len(text) < DESCRIPTION_MIN:
        text = f"{text}\n\n{_SAFE_SENTENCES[index % len(_SAFE_SENTENCES)]}"
        index += 1

    if len(text) > DESCRIPTION_MAX:
        paragraphs = text.split("\n\n")
        while len(paragraphs) > 1 and len("\n\n".join(paragraphs)) > DESCRIPTION_MAX:
            paragraphs.pop()
        text = "\n\n".join(paragraphs)
        if len(text) > DESCRIPTION_MAX:
            text = _truncate(text, DESCRIPTION_MAX)
    return text


def _build_commercial_block(product: ProductInput, missing: list[MissingField]) -> str:
    highlighted = list(product.specs.items())[:3]
    if highlighted:
        specs_phrase = "; ".join(f"{key} — {value}" for key, value in highlighted)
        block = f"{product.name} от {product.manufacturer}: {specs_phrase}."
    else:
        block = f"{product.name} от {product.manufacturer}."

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
    category = product.category or "прибор"
    base = _truncate(product.name, 90)
    candidates = [
        base,
        f"{base} купить",
        f"{base} характеристики",
        f"{base} {product.manufacturer}",
        f"{category} {product.manufacturer}",
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
