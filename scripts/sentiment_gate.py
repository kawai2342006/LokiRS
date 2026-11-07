#!/usr/bin/env python3
"""Publish a separate sentiment deployment only when a new, current reading exists."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def should_publish(current: dict, previous: dict | None, market_day: str) -> bool:
    if (current.get("status") != "ok" or current.get("indexId") != "cnn-us-fear-greed"
            or not current.get("observationDate") or current["observationDate"] < market_day):
        return False
    return (not previous or previous.get("observationDate") < current["observationDate"]
            or previous.get("status") != "ok" or previous.get("value") != current.get("value")
            or previous.get("source") != current.get("source"))


def main() -> None:
    current = json.loads((ROOT / "data/sentiment.json").read_text())
    latest = json.loads((ROOT / "data/latest.json").read_text())
    try:
        previous = json.loads(subprocess.check_output(["git", "show", "HEAD:data/sentiment.json"], cwd=ROOT))
    except (subprocess.CalledProcessError, ValueError):
        previous = None
    publish = should_publish(current, previous, latest["asOf"])
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a") as stream:
            stream.write(f"publish={str(publish).lower()}\n")
    print(f"Sentiment deployment: {'new observation' if publish else 'skip; no new current observation'}; "
          f"sentiment {current.get('observationDate')}, market {latest['asOf']}")


if __name__ == "__main__":
    main()
