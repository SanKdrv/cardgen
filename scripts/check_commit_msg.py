"""Проверка сообщения коммита: Conventional Commits + русскоязычное тело.

Запускается pre-commit-хуком commit-msg, но может использоваться и вручную:

    python scripts/check_commit_msg.py .git/COMMIT_EDITMSG
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TYPES = (
    "feat",
    "fix",
    "docs",
    "test",
    "refactor",
    "perf",
    "build",
    "ci",
    "chore",
    "style",
    "revert",
)
SUBJECT_RE = re.compile(
    r"^(?P<type>" + "|".join(TYPES) + r")"
    r"(?:\((?P<scope>[a-z0-9][a-z0-9-]*)\))?!?: "
    r"(?P<description>\S.{2,71})$"
)
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
MAX_LINE = 100
MIN_BODY = 30


def _content_lines(text: str) -> list[str]:
    """Убирает комментарии git и хвостовые пустые строки."""
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def check(message: str) -> list[str]:
    """Возвращает список ошибок; пустой список означает, что сообщение корректно."""
    lines = _content_lines(message)
    if not lines:
        return ["сообщение коммита пустое"]

    subject = lines[0].rstrip()
    if subject.startswith(("Merge ", "Revert ", "fixup! ", "squash! ")):
        return []

    errors: list[str] = []
    match = SUBJECT_RE.match(subject)
    if not match:
        errors.append(
            "заголовок должен иметь вид '<type>(<scope>): <описание>' "
            f"с типом из {', '.join(TYPES)} и длиной до 72 символов"
        )
    elif subject.endswith("."):
        errors.append("заголовок не должен заканчиваться точкой")

    if len(lines) < 3 or lines[1].strip():
        errors.append("после заголовка нужна пустая строка и тело коммита на русском")
    else:
        body = "\n".join(lines[2:]).strip()
        if len(body) < MIN_BODY:
            errors.append(f"тело коммита короче {MIN_BODY} символов")
        if not CYRILLIC_RE.search(body):
            errors.append("тело коммита должно быть на русском языке")

    for number, line in enumerate(lines, start=1):
        if len(line) > MAX_LINE:
            errors.append(f"строка {number} длиннее {MAX_LINE} символов")
            break

    return errors


def main(argv: list[str]) -> int:
    path = Path(argv[1] if len(argv) > 1 else ".git/COMMIT_EDITMSG")
    if not path.exists():
        print(f"файл сообщения не найден: {path}", file=sys.stderr)
        return 1

    errors = check(path.read_text(encoding="utf-8"))
    if errors:
        print("Сообщение коммита не прошло проверку:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(
            "\nШаблон: .gitmessage. Пример:\n"
            "  feat(api): добавить пакетную генерацию карточек\n"
            "\n"
            "  Зачем:\n"
            "  Контент-менеджеру нужно обрабатывать несколько товаров за раз.\n"
            "\n"
            "  Что сделано:\n"
            "  - добавлен эндпоинт /api/v1/cards/batch;\n"
            "  - ошибки по товарам возвращаются отдельно.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
