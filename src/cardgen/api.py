"""Совместимый вход для uvicorn: `cardgen.api:app`.

Канонический код приложения лежит в `cardgen.presentation.api.app`.
"""

from __future__ import annotations

from .presentation.api.app import app, create_app

__all__ = ["app", "create_app"]
