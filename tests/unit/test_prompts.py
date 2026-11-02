from __future__ import annotations

from cardgen.models import GuardViolation, MissingField, ProductInput
from cardgen.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_correction_prompt,
    build_user_prompt,
)


def test_system_prompt_contains_hard_rules() -> None:
    assert "Запрещено добавлять" in SYSTEM_PROMPT
    assert "копируй дословно" in SYSTEM_PROMPT
    assert "800" in SYSTEM_PROMPT
    assert "1200" in SYSTEM_PROMPT
    assert "JSON-объект и ничего больше" in SYSTEM_PROMPT


def test_user_prompt_contains_facts(product: ProductInput) -> None:
    prompt = build_user_prompt(product, [])
    assert product.name in prompt
    assert product.manufacturer in prompt
    assert '"диапазон измерений": "0–1,6 МПа"' in prompt
    assert "характеристик во входных данных: 4" in prompt
    assert "ЧЕГО НЕТ В ДАННЫХ" not in prompt
    assert product.description[:40] in prompt


def test_user_prompt_lists_missing_fields(product: ProductInput) -> None:
    missing = [MissingField(field="класс точности", hint="уточните погрешность")]
    prompt = build_user_prompt(product, missing)
    assert "ЧЕГО НЕТ В ДАННЫХ" in prompt
    assert "класс точности" in prompt


def test_user_prompt_works_without_description(product: ProductInput) -> None:
    prompt = build_user_prompt(product.model_copy(update={"description": ""}), [])
    assert "(описание не передано)" in prompt


def test_correction_prompt_contains_violations(product: ProductInput) -> None:
    original = build_user_prompt(product, [])
    violations = [
        GuardViolation(code="invented_number", field="seo_title", message="число «2.5» лишнее")
    ]
    prompt = build_correction_prompt(original, '{"seo_title": "..."}', violations)
    assert "РЕЗУЛЬТАТ АВТОМАТИЧЕСКОЙ ПРОВЕРКИ" in prompt
    assert "invented_number" in prompt
    assert "2.5" in prompt
    assert "Верни ПОЛНЫЙ исправленный JSON" in prompt


def test_correction_prompt_truncates_long_response(product: ProductInput) -> None:
    prompt = build_correction_prompt(build_user_prompt(product, []), "x" * 5000, [])
    assert "фрагмент обрезан" in prompt
    assert len(prompt) < 8000


def test_prompt_version_is_set() -> None:
    assert PROMPT_VERSION.count(".") >= 1
