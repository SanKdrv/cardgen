"""Нормализация исходных данных и поиск недостающих характеристик.

Модуль намеренно не использует LLM: это детерминированный слой, на который
опирается защита от выдуманных значений.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import MissingField, ProductInput

_TRANSLATION = str.maketrans(
    {
        "—": "-",
        "–": "-",
        "−": "-",
        "‑": "-",
        "×": "x",
        "ё": "е",
        "Ё": "Е",
    }
)

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
# Коды вида IP65, RS-485, G1/2, МП4, ТБ-1. Пробел внутри кода не допускаем,
# иначе под шаблон попали бы обычные фразы вроде «класс 1,5».
_CODE_RE = re.compile(
    r"[A-Za-zА-Яа-яЁё]{1,6}-?\d+(?:[.,]\d+)?(?:[/-]\d+(?:[.,]\d+)?)*(?![A-Za-zА-Яа-яЁё])"
)
_BENIGN_CODES = {"b2b", "b2c", "b2g"}
BENIGN_CODES = frozenset(_BENIGN_CODES)

# Слова-маркеры свойств, которые нельзя упоминать, если их нет во входных данных.
# Список сознательно узкий: только материалы, интерфейсы, защита и сервисные
# обещания, а не общеупотребительная лексика.
_CLAIM_STEMS: tuple[tuple[str, str], ...] = (
    ("нержаве", "нержавеющая сталь"),
    ("латун", "латунь"),
    ("бронз", "бронза"),
    ("алюмин", "алюминий"),
    ("стал", "сталь"),
    ("стекл", "стекло"),
    ("поликарбонат", "поликарбонат"),
    ("пластик", "пластик"),
    ("титан", "титан"),
    ("чугун", "чугун"),
    ("взрывозащищ", "взрывозащита"),
    ("пылевлагозащищ", "пылевлагозащита"),
    ("герметич", "герметичность"),
    ("поверк", "поверка"),
    ("калибров", "калибровка"),
    ("сертифиц", "сертификация"),
    ("гаранти", "гарантия"),
    ("агрессивн", "агрессивные среды"),
    ("пищев", "пищевая промышленность"),
    ("фармацевт", "фармацевтика"),
    ("hart", "HART"),
    ("modbus", "Modbus"),
    ("profibus", "Profibus"),
    ("profinet", "Profinet"),
    ("bluetooth", "Bluetooth"),
    ("wi-fi", "Wi-Fi"),
    ("gsm", "GSM"),
    ("usb", "USB"),
)


def canonical(text: str) -> str:
    """Приводит текст к виду, удобному для сравнения фактов."""
    lowered = text.translate(_TRANSLATION).lower()
    lowered = re.sub(r"(?<=\d),(?=\d)", ".", lowered)
    lowered = re.sub(r"(?<=\d)\s+(?=\d)", "", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def compact(text: str) -> str:
    """Убирает всё, кроме букв и цифр: нужно для сравнения кодов (G1/2, RS-485)."""
    return re.sub(r"[^0-9a-zа-я]+", "", canonical(text))


@dataclass(frozen=True)
class FactTable:
    """Все факты из входных данных + быстрые индексы для проверки текста."""

    text: str
    compact_text: str
    numbers: frozenset[str]

    def numbers_in(self, text: str) -> set[str]:
        return {_normalize_number(item) for item in _NUMBER_RE.findall(canonical(text))}

    def codes_in(self, text: str) -> set[str]:
        return {compact(item) for item in _CODE_RE.findall(text)}


def _normalize_number(value: str) -> str:
    normalized = value.replace(",", ".")
    if normalized.startswith("0") and len(normalized) > 1 and "." not in normalized:
        # «02» и «2» — одно и то же число, но код «DM 02» должен остаться узнаваемым.
        stripped = normalized.lstrip("0")
        return stripped or "0"
    return normalized


def build_facts(product: ProductInput) -> FactTable:
    """Собирает единый источник фактов из всех входных полей."""
    parts: list[str] = [product.name, product.manufacturer]
    if product.category:
        parts.append(product.category)
    for key, value in product.specs.items():
        parts.extend((key, value))
    if product.description:
        parts.append(product.description)

    text = canonical(" \n ".join(parts))
    numbers = frozenset(_normalize_number(item) for item in _NUMBER_RE.findall(text))
    return FactTable(text=text, compact_text=compact(text), numbers=numbers)


def find_claim_stems(text: str) -> set[str]:
    """Возвращает найденные в тексте маркеры свойств (в каноническом виде)."""
    normalized = canonical(text)
    return {stem for stem, _ in _CLAIM_STEMS if stem in normalized}


def claim_name(stem: str) -> str:
    for candidate, name in _CLAIM_STEMS:
        if candidate == stem:
            return name
    return stem


# --- Недостающие характеристики -------------------------------------------------

_REQUIRED_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    "манометр": (
        "диапазон измерений",
        "класс точности",
        "присоединение",
        "диаметр корпуса",
    ),
    "термометр": (
        "диапазон измерений",
        "класс точности",
        "присоединение",
        "длина монтажной части",
    ),
    "преобразователь": (
        "диапазон измерений",
        "класс точности",
        "выходной сигнал",
        "питание",
    ),
    "расходомер": (
        "диапазон измерений",
        "класс точности",
        "присоединение",
        "выходной сигнал",
    ),
    "уровнемер": (
        "диапазон измерений",
        "класс точности",
        "выходной сигнал",
        "питание",
    ),
    "калибратор": (
        "диапазон измерений",
        "класс точности",
        "интерфейс",
        "питание",
    ),
}

_DEFAULT_REQUIRED = ("диапазон измерений", "класс точности", "питание", "интерфейс")

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("манометр", ("манометр", "мановакуумметр", "вакуумметр")),
    ("термометр", ("термометр", "термопара", "термосопротивление")),
    ("преобразователь", ("преобразователь давления", "датчик давления")),
    ("расходомер", ("расходомер",)),
    ("уровнемер", ("уровнемер", "датчик уровня")),
    ("калибратор", ("калибратор",)),
)

_REQUIRED_SYNONYMS: dict[str, tuple[str, ...]] = {
    "диапазон измерений": ("диапазон", "пределы измерен", "шкала"),
    "класс точности": ("класс точности", "погрешн", "точн"),
    "присоединение": ("присоединен", "резьб", "штуцер", "разъем"),
    "диаметр корпуса": ("диаметр корпуса", "диаметр"),
    "питание": ("питани", "напряжение"),
    "интерфейс": ("интерфейс", "протокол"),
    "выходной сигнал": ("выходной сигнал", "выход", "сигнал"),
    "длина монтажной части": ("длина монтажн", "монтажн", "длина"),
}

_HINTS: dict[str, str] = {
    "диапазон измерений": "уточните пределы шкалы — без них нельзя подобрать модификацию",
    "класс точности": "уточните класс точности или предел допускаемой погрешности",
    "присоединение": "уточните тип и размер присоединения (резьба, штуцер, разъём)",
    "диаметр корпуса": "уточните диаметр корпуса — он влияет на монтаж и чтение шкалы",
    "длина монтажной части": "уточните длину монтажной части для выбора исполнения",
    "питание": "уточните напряжение и тип питания",
    "интерфейс": "уточните интерфейс или протокол обмена",
    "выходной сигнал": "уточните тип выходного сигнала",
}


def infer_category(product: ProductInput) -> str | None:
    haystack = f"{product.category or ''} {product.name}".lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return None


def required_fields_for(product: ProductInput) -> tuple[str, ...]:
    category = infer_category(product)
    if category is None:
        return _DEFAULT_REQUIRED
    return _REQUIRED_BY_CATEGORY[category]


def _spec_key_matches(spec_key: str, required: str) -> bool:
    normalized = canonical(spec_key)
    synonyms = _REQUIRED_SYNONYMS.get(required, (required,))
    return any(synonym in normalized for synonym in synonyms)


def detect_missing_fields(product: ProductInput) -> list[MissingField]:
    """Возвращает поля, которых не хватает для полноценной карточки.

    Результат вычисляется только по входным данным, а не по ответу модели,
    поэтому список пропусков невозможно «придумать».
    """
    missing: list[MissingField] = []
    spec_keys = list(product.specs)

    for required in required_fields_for(product):
        if not any(_spec_key_matches(key, required) for key in spec_keys):
            missing.append(
                MissingField(
                    field=required,
                    hint=_HINTS.get(required, "уточните значение у поставщика"),
                )
            )

    if len(spec_keys) < 2:
        missing.append(
            MissingField(
                field="технические характеристики",
                hint="добавьте минимум 2–3 параметра, иначе карточка получится неинформативной",
            )
        )

    if len(product.description.strip()) < 30:
        missing.append(
            MissingField(
                field="назначение и область применения",
                hint="добавьте 1–2 предложения из паспорта: для каких задач и сред подходит прибор",
            )
        )

    return missing
