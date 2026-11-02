from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
ENV_FIXTURE = {
    "CARDGEN_PROVIDER": "fixture",
    "CARDGEN_MAX_RETRIES": "1",
    "CARDGEN_RETRY_BACKOFF_S": "0",
    "PYTHONIOENCODING": "utf-8",
}


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(ENV_FIXTURE)
    env.pop("CARDGEN_API_KEY", None)
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    return env


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(url: str, process: subprocess.Popen[str], timeout: float = 40.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            raise AssertionError(f"сервер завершился раньше времени:\n{stderr}")
        try:
            response = httpx.get(url, timeout=1.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.15)
    raise AssertionError("сервер не поднялся за отведённое время")


@pytest.mark.smoke
def test_uvicorn_end_to_end() -> None:
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "cardgen.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=ROOT,
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_for_health(f"{base_url}/health", process)
        product = json.loads((ROOT / "examples" / "products.json").read_text(encoding="utf-8"))[
            "products"
        ][0]
        with httpx.Client(timeout=20.0) as client:
            health = client.get(f"{base_url}/health").json()
            assert health["provider"] == "fixture"
            response = client.post(f"{base_url}/api/v1/cards", json={"product": product})
            assert response.status_code == 200
            body = response.json()
            assert body["meta"]["fallback_used"] is False
            assert body["draft"]["seo_title"]
            page = client.get(f"{base_url}/")
            assert page.status_code == 200
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.mark.smoke
def test_cli_generate_end_to_end(tmp_path: Path) -> None:
    output = tmp_path / "cards"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cardgen",
            "generate",
            "--provider",
            "fixture",
            "--input",
            str(ROOT / "examples" / "products.json"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    files = sorted(output.glob("*.json"))
    assert len(files) == 2
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["meta"]["provider"] == "fixture"
    assert payload["markdown"].startswith("# ")
    assert (output / files[0].name.replace(".json", ".md")).exists()

    second = subprocess.run(
        [
            sys.executable,
            "-m",
            "cardgen",
            "generate",
            "--provider",
            "fixture",
            "--input",
            str(ROOT / "examples" / "products.json"),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert second.returncode == 2
    assert "уже существуют" in second.stderr


@pytest.mark.smoke
def test_cli_check_config() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "cardgen", "check-config"],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "fixture" in result.stdout


@pytest.mark.smoke
def test_cli_invalid_input(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"products": [{"name": "П", "manufacturer": "З"}]}', encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cardgen",
            "generate",
            "--provider",
            "fixture",
            "--input",
            str(bad),
            "--output",
            str(tmp_path / "out"),
        ],
        cwd=ROOT,
        env=_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert result.returncode == 2
    assert "не прошёл валидацию" in result.stderr
