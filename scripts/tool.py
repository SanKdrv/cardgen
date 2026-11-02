"""Запускает инструмент интерпретатором из .venv проекта.

Локальные pre-commit-хуки вызываются системным `python`, который может не
знать о зависимостях проекта. Этот враппер находит виртуальное окружение и
передаёт управление ему. Если .venv нет — используется текущий интерпретатор.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def project_python() -> str:
    candidates = [
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def run(arguments: list[str]) -> int:
    return subprocess.call([project_python(), *arguments])


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
