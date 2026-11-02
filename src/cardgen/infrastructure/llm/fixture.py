"""Офлайн-провайдер с заранее подготовленными ответами для демо и тестов."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ...core.errors import LLMResponseError

logger = logging.getLogger(__name__)

DEFAULT_FIXTURE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures.json"


class FixtureProvider:
    """Ищет ответ по названию товара в промпте.

    Нужен, чтобы демо и smoke-тесты работали без сети и без платного ключа.
    Если товара нет в наборе, пайплайн переходит на безопасный шаблон.
    """

    name = "fixture"
    model = "offline-fixtures"

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_FIXTURE_PATH
        self._drafts: dict[str, dict[str, Any]] = {}
        self._load()

    @property
    def ready(self) -> bool:
        return True

    def _load(self) -> None:
        if not self._path.exists():
            logger.warning("Набор офлайн-ответов не найден: %s", self._path)
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Не удалось прочитать офлайн-ответы: %s", exc)
            return
        drafts = payload.get("drafts", payload) if isinstance(payload, dict) else {}
        if isinstance(drafts, dict):
            self._drafts = {
                str(key): value for key, value in drafts.items() if isinstance(value, dict)
            }

    async def complete(self, *, system: str, user: str) -> str:
        del system
        haystack = user.lower()
        matches = [
            (name, payload) for name, payload in self._drafts.items() if name.lower() in haystack
        ]
        if not matches:
            raise LLMResponseError(
                "в офлайн-наборе нет ответа для этого товара; используйте openai-провайдер "
                "или добавьте фикстуру"
            )
        _, payload = max(matches, key=lambda item: len(item[0]))
        return json.dumps(payload, ensure_ascii=False)

    async def aclose(self) -> None:
        return None
