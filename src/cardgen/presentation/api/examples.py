"""Загрузка демо-товаров для API и веб-формы."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "demo_products.json"


@lru_cache
def load_examples() -> list[dict[str, Any]]:
    if not _DATA_PATH.exists():
        return []
    payload = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    products = payload.get("products", payload) if isinstance(payload, dict) else payload
    return [item for item in products if isinstance(item, dict)]
