"""Запуск быстрых тестов из pre-commit/pre-push.

Если тестов ещё нет (ранние коммиты), шаг считается успешным: иначе хук
блокировал бы коммиты до появления тестового каталога.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tool import run

TARGETS = {
    "unit": ["tests/unit"],
    "all": ["tests/unit", "tests/integration"],
}


def _has_tests(paths: list[str]) -> bool:
    for raw_path in paths:
        path = Path(raw_path)
        if path.exists() and any(path.rglob("test_*.py")):
            return True
    return False


def main(argv: list[str]) -> int:
    target = argv[1] if len(argv) > 1 else "unit"
    paths = TARGETS.get(target)
    if paths is None:
        print(f"неизвестный набор тестов: {target}", file=sys.stderr)
        return 2
    if not _has_tests(paths):
        print("тестов пока нет — проверка пропущена")
        return 0
    return run(["-m", "pytest", "-q", "-m", "not smoke", *paths])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
