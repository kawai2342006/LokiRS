#!/usr/bin/env python3
"""Refresh only CNN US-stock sentiment without downloading or replacing stock prices."""
import json
from pathlib import Path
from datetime import datetime, timezone
from providers import fetch_sentiment
from sentiment_sources import valid_previous

ROOT = Path(__file__).resolve().parents[1]


def update_sentiment_snapshot(root=ROOT, previous=None):
    root = Path(root)
    output = root/"data/sentiment.json"
    now = datetime.now(timezone.utc)
    prior = valid_previous(previous, now)
    if output.exists():
        try:
            candidate = valid_previous(json.loads(output.read_text()), now)
            if candidate and (not prior or candidate["observationDate"] >= prior["observationDate"]):
                prior = candidate
        except (ValueError, OSError):
            pass
    if prior is None and (root/"data/latest.json").exists():
        try:
            latest = json.loads((root/"data/latest.json").read_text())
            prior = valid_previous(latest.get("sentiment"), now) if isinstance(latest, dict) else None
        except (ValueError, OSError):
            pass
    result = fetch_sentiment(prior)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n")
    temporary.replace(output)
    print(f"Sentiment: {result['status']} / {result.get('source')} / {result.get('value')} / {result.get('observationDate')}",flush=True)
    return result


if __name__ == "__main__":
    update_sentiment_snapshot()
