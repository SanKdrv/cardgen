"""Извлечение JSON из ответа модели.

Модели иногда оборачивают JSON в ```json ... ```, добавляют пояснения до/после
или возвращают почти-JSON с висячими запятыми. Парсер это переживает, но
не пытается «додумать» структуру: итоговая валидация — за Pydantic.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from ..core.errors import DraftParseError
from ..domain.models import CardDraft

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _strip_fence(text: str) -> str:
    stripped = text.strip().lstrip("\ufeff")
    if stripped.startswith("```"):
        stripped = _FENCE_RE.sub("", stripped)
    return stripped.strip()


def _find_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _loads(candidate: str) -> dict[str, Any]:
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        repaired = _TRAILING_COMMA_RE.sub(r"\1", candidate)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise DraftParseError(f"ответ не является корректным JSON: {exc.msg}") from exc

    if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
        data = data[0]
    if not isinstance(data, dict):
        raise DraftParseError("ожидался JSON-объект с полями карточки")
    return data


def extract_json_object(raw: str) -> dict[str, Any]:
    text = _strip_fence(raw)
    if not text:
        raise DraftParseError("пустой ответ модели")

    try:
        return _loads(text)
    except DraftParseError as exc:
        if text.lstrip().startswith("["):
            raise exc

    candidate = _find_balanced_object(text)
    if candidate is None:
        raise DraftParseError("в ответе не найден JSON-объект")
    return _loads(candidate)


def parse_draft(raw: str) -> CardDraft:
    data = extract_json_object(raw)
    try:
        return CardDraft.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()[:3]
        )
        raise DraftParseError(f"структура ответа не соответствует схеме: {details}") from exc
