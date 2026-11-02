"""Pydantic-модели входа, выхода и служебных данных."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_SPECS = 40
MAX_SPEC_KEY = 80
MAX_SPEC_VALUE = 300


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


class ProductInput(BaseModel):
    """Данные о приборе, которые приходят из формы, JSON или CLI."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=200, examples=["Манометр показывающий DM 02"])
    manufacturer: str = Field(min_length=2, max_length=200, examples=["Манотомь"])
    category: str | None = Field(default=None, max_length=120, examples=["Манометры"])
    specs: dict[str, str] = Field(
        default_factory=dict,
        max_length=MAX_SPECS,
        description="Технические характеристики: название → значение.",
        examples=[{"диапазон измерений": "0–1,6 МПа", "класс точности": "1,5"}],
    )
    description: str = Field(
        default="",
        max_length=20_000,
        description="Фрагмент паспорта или маркетинговое описание.",
    )

    @field_validator("name", "manufacturer", "category")
    @classmethod
    def _normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _collapse_whitespace(value)
        if not normalized:
            raise ValueError("поле не может состоять из пробелов")
        return normalized

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str) -> str:
        return value.replace("\r\n", "\n").strip()

    @field_validator("specs", mode="before")
    @classmethod
    def _normalize_specs(cls, raw: Any) -> dict[str, str]:
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ValueError("specs должен быть объектом «характеристика → значение»")
        if len(raw) > MAX_SPECS:
            raise ValueError(f"поддерживается не больше {MAX_SPECS} характеристик")

        normalized: dict[str, str] = {}
        seen: set[str] = set()
        for raw_key, raw_value in raw.items():
            key = _collapse_whitespace(str(raw_key))
            if not key:
                raise ValueError("название характеристики не может быть пустым")
            if len(key) > MAX_SPEC_KEY:
                raise ValueError(f"название характеристики длиннее {MAX_SPEC_KEY} символов")
            if isinstance(raw_value, dict | list | tuple | set | bool):
                raise ValueError(f"значение характеристики «{key}» должно быть строкой или числом")
            if raw_value is None:
                continue
            value = _collapse_whitespace(str(raw_value))
            if not value:
                continue
            if len(value) > MAX_SPEC_VALUE:
                raise ValueError(
                    f"значение характеристики «{key}» длиннее {MAX_SPEC_VALUE} символов"
                )

            dedupe_key = key.casefold().replace("ё", "е")
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            normalized[key] = value
        return normalized


class KeySpecItem(BaseModel):
    """Одна характеристика в готовой карточке."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=MAX_SPEC_VALUE)


class CardDraft(BaseModel):
    """Черновик карточки, который вернула модель (до проверки guard-ом)."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    seo_title: str = Field(min_length=1, max_length=400)
    seo_description: str = Field(min_length=1, max_length=6000)
    key_specs: list[KeySpecItem] = Field(default_factory=list, max_length=MAX_SPECS)
    search_queries: list[str] = Field(default_factory=list, max_length=10)
    commercial_block: str = Field(min_length=1, max_length=3000)

    @field_validator("search_queries")
    @classmethod
    def _normalize_queries(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            query = _collapse_whitespace(value)
            if not query:
                continue
            key = query.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(query)
        return result


class MissingField(BaseModel):
    """Характеристика, которой не хватает для полноценной карточки."""

    field: str
    hint: str
    value: str = "данных нет"


class GuardViolation(BaseModel):
    code: str
    field: str
    message: str


class GuardReport(BaseModel):
    ok: bool
    violations: list[GuardViolation] = Field(default_factory=list)
    stats: dict[str, int | float | str] = Field(default_factory=dict)


class CardMeta(BaseModel):
    provider: str
    model: str
    attempts: int = 0
    fallback_used: bool = False
    fallback_reason: str | None = None
    latency_ms: int = 0
    prompt_version: str
    validation: GuardReport


class CardResult(BaseModel):
    product: ProductInput
    draft: CardDraft
    missing_fields: list[MissingField] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    meta: CardMeta
    markdown: str = ""


class GenerateOptions(BaseModel):
    allow_fallback: bool = Field(
        default=True,
        description="При ошибке LLM или провале проверки вернуть безопасный шаблон вместо 502.",
    )


class GenerateRequest(BaseModel):
    product: ProductInput
    options: GenerateOptions = Field(default_factory=GenerateOptions)


class BatchGenerateRequest(BaseModel):
    products: list[ProductInput] = Field(min_length=1, max_length=20)
    options: GenerateOptions = Field(default_factory=GenerateOptions)


class BatchError(BaseModel):
    index: int
    product_name: str | None = None
    error_type: str
    message: str


class BatchResponse(BaseModel):
    items: list[CardResult] = Field(default_factory=list)
    errors: list[BatchError] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    provider: str
    model: str
    provider_ready: bool


class ErrorDetail(BaseModel):
    type: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
