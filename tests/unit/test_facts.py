from __future__ import annotations

from cardgen.domain.facts import (
    build_facts,
    canonical,
    compact,
    detect_missing_fields,
    find_claim_polarities,
    find_claim_stems,
    infer_category,
    required_fields_for,
)
from cardgen.domain.models import ProductInput


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


def test_build_facts_links_numbers_to_units(product: ProductInput) -> None:
    facts = build_facts(product)
    assert ("1.6", "мпа") in facts.quantity_pairs
    assert ("100", "мм") in facts.quantity_pairs
    assert ("40", "°c") in facts.quantity_pairs
    assert ("70", "°c") in facts.quantity_pairs
    assert facts.quantities_in("давление 1,6 бар") == {("1.6", "бар")}
    assert facts.quantities_in("диаметр 100 мм") == {("100", "мм")}


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


def test_claim_negation_is_respected() -> None:
    positive, negative = find_claim_polarities("неагрессивных жидкостей")
    assert "агрессивн" not in positive
    assert "агрессивн" in negative
    positive, negative = find_claim_polarities("не агрессивных сред")
    assert "агрессивн" in negative
    positive, _ = find_claim_polarities("для агрессивных сред")
    assert "агрессивн" in positive
    # «нержавеющая» начинается с «не», но это не отрицание стали.
    positive, _ = find_claim_polarities("нержавеющая сталь")
    assert "нержаве" in positive


def test_claim_negation_in_sentence_context() -> None:
    positive, negative = find_claim_polarities("Прибор не предназначен для агрессивных сред.")
    assert "агрессивн" in negative
    assert "агрессивн" not in positive
    positive, negative = find_claim_polarities("Поверка не требуется.")
    assert "поверк" in negative
    assert "поверк" not in positive
    positive, negative = find_claim_polarities("Поставляется без сертификата.")
    assert "сертифик" in negative
    assert "сертифик" not in positive


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


def test_placeholder_values_are_treated_as_missing() -> None:
    product = ProductInput(
        name="Манометр",
        manufacturer="Завод",
        specs={
            "диапазон измерений": "0–1,6 МПа",
            "класс точности": "н.д.",
            "присоединение": "нет",
            "диаметр корпуса": "не указан",
            "питание": "unknown",
            "интерфейс": "??",
            "материал корпуса": "xxx",
        },
    )
    assert product.specs == {"диапазон измерений": "0–1,6 МПа"}
    fields = {item.field for item in detect_missing_fields(product)}
    assert {"класс точности", "присоединение", "диаметр корпуса"} <= fields


def test_narrow_synonyms_do_not_cover_different_attribute() -> None:
    product = ProductInput(
        name="Манометр",
        manufacturer="Завод",
        specs={
            "диапазон измерений": "0–1,6 МПа",
            "диаметр присоединения": "G1/2",
        },
    )
    fields = {item.field for item in detect_missing_fields(product)}
    assert "диаметр корпуса" in fields
    assert "присоединение" not in fields

    thermometer = ProductInput(
        name="Термометр",
        manufacturer="Завод",
        specs={
            "диапазон измерений": "0…120 °C",
            "длина кабеля": "2 м",
            "присоединение": "M20×1,5",
        },
    )
    fields = {item.field for item in detect_missing_fields(thermometer)}
    assert "длина монтажной части" in fields
