from __future__ import annotations

import pytest
from pydantic import ValidationError

from cardgen.domain.models import CardDraft, ProductInput


def test_product_input_normalizes_text_and_specs() -> None:
    product = ProductInput(
        name="  Манометр   DM 02 ",
        manufacturer=" Манотомь ",
        specs={"  Класс   точности ": " 1,5 ", "пустое": "   "},
        description="  текст  ",
    )
    assert product.name == "Манометр DM 02"
    assert product.manufacturer == "Манотомь"
    assert product.specs == {"Класс точности": "1,5"}
    assert product.description == "текст"


def test_specs_accept_numbers_and_drop_none() -> None:
    product = ProductInput(
        name="Прибор",
        manufacturer="Завод",
        specs={"диаметр": 100, "давление": 1.6, "пусто": None},
    )
    assert product.specs == {"диаметр": "100", "давление": "1.6"}


def test_specs_deduplicate_case_insensitive() -> None:
    product = ProductInput(
        name="Прибор",
        manufacturer="Завод",
        specs={"Класс": "1", "класс": "2"},
    )
    assert product.specs == {"Класс": "1"}


def test_specs_must_be_object() -> None:
    with pytest.raises(ValidationError, match="объектом"):
        ProductInput(name="Прибор", manufacturer="Завод", specs=["a"])  # type: ignore[arg-type]


def test_specs_reject_nested_values() -> None:
    with pytest.raises(ValidationError, match="строкой или числом"):
        ProductInput(name="Прибор", manufacturer="Завод", specs={"a": {"b": "c"}})  # type: ignore[dict-item]


def test_specs_reject_empty_key() -> None:
    with pytest.raises(ValidationError, match="название характеристики"):
        ProductInput(name="Прибор", manufacturer="Завод", specs={"  ": "1"})


def test_specs_reject_too_many_items() -> None:
    specs = {f"характеристика {index}": str(index) for index in range(41)}
    with pytest.raises(ValidationError, match="не больше 40"):
        ProductInput(name="Прибор", manufacturer="Завод", specs=specs)


def test_specs_reject_long_key_and_value() -> None:
    with pytest.raises(ValidationError, match="название характеристики длиннее"):
        ProductInput(name="Прибор", manufacturer="Завод", specs={"x" * 81: "1"})
    with pytest.raises(ValidationError, match="длиннее 300"):
        ProductInput(name="Прибор", manufacturer="Завод", specs={"ключ": "x" * 301})


def test_name_and_manufacturer_required() -> None:
    with pytest.raises(ValidationError):
        ProductInput(name="П", manufacturer="Завод")
    with pytest.raises(ValidationError):
        ProductInput(name="Прибор", manufacturer="")


def test_description_normalizes_line_endings() -> None:
    product = ProductInput(name="Прибор", manufacturer="Завод", description="первая\r\nвторая\r\n")
    assert product.description == "первая\nвторая"


def test_extra_fields_are_ignored() -> None:
    product = ProductInput.model_validate(
        {"name": "Прибор", "manufacturer": "Завод", "unknown": "значение"}
    )
    assert product.name == "Прибор"


def test_card_draft_normalizes_queries() -> None:
    draft = CardDraft(
        seo_title="Заголовок",
        seo_description="Описание",
        search_queries=["  манометр  ", "манометр", "", "манометр купить"],
        commercial_block="Блок",
    )
    assert draft.search_queries == ["манометр", "манометр купить"]


def test_card_draft_ignores_extra_and_requires_fields() -> None:
    with pytest.raises(ValidationError):
        CardDraft.model_validate({"seo_title": "Только заголовок"})
    draft = CardDraft.model_validate(
        {
            "seo_title": "Заголовок",
            "seo_description": "Описание",
            "commercial_block": "Блок",
            "extra": True,
        }
    )
    assert draft.seo_description == "Описание"
