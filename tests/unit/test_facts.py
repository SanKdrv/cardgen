from __future__ import annotations

from cardgen.facts import (
    build_facts,
    canonical,
    compact,
    detect_missing_fields,
    find_claim_stems,
    infer_category,
    required_fields_for,
)
from cardgen.models import ProductInput


def test_canonical_normalizes_dashes_commas_and_yo() -> None:
    assert canonical("0–1,6 МПа, Ёмкость") == "0-1.6 мпа, емкость"
    assert canonical("1000   мм") == "1000 мм"
    assert canonical("1 000 мм") == "1000 мм"


def test_compact_removes_separators() -> None:
    assert compact("G1/2") == "g12"
    assert compact("M20×1,5") == "m20x15"


def test_build_facts_collects_numbers_and_text(product: ProductInput) -> None:
    facts = build_facts(product)
    assert "манотомь" in facts.text
    assert "0-1.6" in facts.text
    assert {"0", "1.6", "1.5", "100", "40", "70"} <= facts.numbers
    assert facts.numbers_in("давление 1,6 МПа") == {"1.6"}
    assert facts.numbers_in("давление 2,5 МПа") == {"2.5"}


def test_numbers_from_code_are_extracted(product: ProductInput) -> None:
    facts = build_facts(product)
    assert {"1", "2"} <= facts.numbers


def test_codes_are_extracted_and_b2b_is_not_a_code(product: ProductInput) -> None:
    facts = build_facts(product)
    codes = facts.codes_in("G1/2 и IP65, поставка B2B")
    assert "g12" in codes
    assert "ip65" in codes
    assert "b2b" not in codes


def test_claim_stems_and_names(product: ProductInput) -> None:
    stems = find_claim_stems("Корпус из нержавеющей стали")
    assert "нержаве" in stems
    assert "стал" in stems
    assert find_claim_stems("Обычный текст без обещаний") == set()


def test_detect_missing_fields_for_complete_product(product: ProductInput) -> None:
    assert detect_missing_fields(product) == []


def test_detect_missing_accuracy_for_partial_product(partial_product: ProductInput) -> None:
    missing = detect_missing_fields(partial_product)
    assert [item.field for item in missing] == ["класс точности"]
    assert "погрешности" in missing[0].hint


def test_detect_missing_fields_for_unknown_category() -> None:
    product = ProductInput(
        name="Прибор",
        manufacturer="Завод",
        specs={},
        description="",
    )
    fields = {item.field for item in detect_missing_fields(product)}
    assert {"диапазон измерений", "класс точности", "питание", "интерфейс"} <= fields
    assert "технические характеристики" in fields
    assert "назначение и область применения" in fields


def test_short_description_adds_missing_purpose(product: ProductInput) -> None:
    product = product.model_copy(update={"description": "Коротко"})
    fields = {item.field for item in detect_missing_fields(product)}
    assert "назначение и область применения" in fields


def test_infer_category_and_required_fields(product: ProductInput) -> None:
    assert infer_category(product) == "манометр"
    assert "диаметр корпуса" in required_fields_for(product)
    assert infer_category(ProductInput(name="Клапан", manufacturer="Завод")) is None


def test_spec_key_synonyms() -> None:
    with_accuracy = ProductInput(
        name="Манометр",
        manufacturer="Завод",
        specs={"предел допускаемой погрешности": "1,5"},
    )
    assert all(item.field != "класс точности" for item in detect_missing_fields(with_accuracy))

    with_protection = ProductInput(
        name="Манометр",
        manufacturer="Завод",
        specs={"класс защиты": "IP65"},
    )
    assert any(item.field == "класс точности" for item in detect_missing_fields(with_protection))
