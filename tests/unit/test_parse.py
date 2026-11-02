from __future__ import annotations

import json
from typing import Any

import pytest

from cardgen.application.parsing import extract_json_object, parse_draft
from cardgen.core.errors import DraftParseError


def minimal_payload() -> dict[str, Any]:
    return {
        "seo_title": "Манометр DM 02",
        "seo_description": "Описание",
        "key_specs": [{"name": "класс точности", "value": "1,5"}],
        "search_queries": ["манометр купить"],
        "commercial_block": "Блок",
    }


def test_plain_json() -> None:
    draft = parse_draft(json.dumps(minimal_payload(), ensure_ascii=False))
    assert draft.seo_title == "Манометр DM 02"
    assert draft.key_specs[0].value == "1,5"


def test_fenced_json() -> None:
    raw = "```json\n" + json.dumps(minimal_payload(), ensure_ascii=False) + "\n```"
    assert parse_draft(raw).seo_title == "Манометр DM 02"


def test_json_with_prose_around() -> None:
    raw = "Вот результат:\n" + json.dumps(minimal_payload(), ensure_ascii=False) + "\nГотово."
    assert parse_draft(raw).seo_description == "Описание"


def test_json_with_trailing_comma() -> None:
    raw = json.dumps(minimal_payload(), ensure_ascii=False).replace('"Блок"', '"Блок",')
    assert parse_draft(raw).commercial_block == "Блок"


def test_single_item_list() -> None:
    raw = json.dumps([minimal_payload()], ensure_ascii=False)
    assert parse_draft(raw).seo_title == "Манометр DM 02"


def test_empty_response() -> None:
    with pytest.raises(DraftParseError, match="пустой"):
        extract_json_object("   ")


def test_no_json_object() -> None:
    with pytest.raises(DraftParseError, match="не найден"):
        extract_json_object("просто текст без структуры")


def test_array_of_many_items_is_rejected() -> None:
    with pytest.raises(DraftParseError, match="JSON-объект"):
        extract_json_object("[{}, {}]")


def test_schema_mismatch() -> None:
    with pytest.raises(DraftParseError, match="схеме"):
        parse_draft('{"seo_title": "без остальных полей"}')


def test_invalid_json_reports_position() -> None:
    with pytest.raises(DraftParseError):
        extract_json_object('{"seo_title": , }')
