from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_commit_msg.py"
_spec = importlib.util.spec_from_file_location("check_commit_msg", SCRIPT)
assert _spec is not None
assert _spec.loader is not None
commit_msg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(commit_msg)


def test_valid_message_passes() -> None:
    message = (
        "feat(api): добавить пакетную генерацию\n"
        "\n"
        "Зачем:\n"
        "Контент-менеджеру нужно обрабатывать несколько товаров за раз.\n"
        "\n"
        "Что сделано:\n"
        "- добавлен эндпоинт batch."
    )
    assert commit_msg.check(message) == []


def test_subject_requires_conventional_type() -> None:
    errors = commit_msg.check("добавить пакетную генерацию\n\nТело на русском достаточно длинное.")
    assert errors
    assert any("type" in error for error in errors)


def test_body_requires_cyrillic() -> None:
    errors = commit_msg.check("feat: add batch generation\n\nThis body is written in English only.")
    assert any("русском" in error for error in errors)


def test_body_too_short() -> None:
    errors = commit_msg.check("feat: добавить пакет\n\nКоротко.")
    assert any("короче" in error for error in errors)


def test_merge_commit_is_allowed() -> None:
    assert commit_msg.check("Merge branch 'feature/x' into main") == []


def test_trailing_dot_is_rejected() -> None:
    errors = commit_msg.check(
        "feat: добавить пакетную генерацию.\n\n"
        "Зачем: нужно обрабатывать несколько товаров за один запрос."
    )
    assert any("точкой" in error for error in errors)


def test_long_subject_is_rejected() -> None:
    subject = "feat: " + "очень длинное описание " * 5
    errors = commit_msg.check(subject + "\n\nТело коммита на русском языке достаточно длинное.")
    assert errors


def test_empty_message_is_rejected() -> None:
    assert commit_msg.check("# только комментарий") == ["сообщение коммита пустое"]


def test_main_reports_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert commit_msg.main(["script", str(tmp_path / "missing")]) == 1
    assert "не найден" in capsys.readouterr().err
