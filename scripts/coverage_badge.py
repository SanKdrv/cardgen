"""Формирует payload для shields.io endpoint по coverage.py JSON."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "coverage.json"
TARGET = ROOT / ".github" / "badges" / "coverage.json"


def color_for(percent: float) -> str:
    if percent >= 90:
        return "brightgreen"
    if percent >= 80:
        return "green"
    if percent >= 70:
        return "yellow"
    return "red"


def main() -> int:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    percent = round(float(data["totals"]["percent_covered"]), 1)
    payload = {
        "schemaVersion": 1,
        "label": "coverage",
        "message": f"{percent}%",
        "color": color_for(percent),
    }
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"coverage badge: {percent}% ({payload['color']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
