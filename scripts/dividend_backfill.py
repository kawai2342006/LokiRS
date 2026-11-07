"""Conservative corporate-action repair when a source has not yet adjusted history.

Amounts come from dated issuer/exchange records, never from target ranking scores.
Adjust only historical total-return closes; retain quoted prices and intraday bars.
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path


def load_verified(path: Path) -> dict[str, list[dict]]:
    payload = json.loads(path.read_text())
    actions = {}
    for item in payload["actions"]:
        symbol, day, amount, source = item["symbol"], item["exDate"], item["amountUSD"], item["source"]
        date.fromisoformat(day)
        if not symbol or not isinstance(amount, (int, float)) or isinstance(amount, bool) or not math.isfinite(amount) or amount <= 0:
            raise ValueError("Invalid verified dividend")
        if not source.startswith("https://"):
            raise ValueError("A verified dividend requires a public source")
        actions.setdefault(symbol, []).append(item)
    for symbol in actions:
        actions[symbol].sort(key=lambda item: item["exDate"])
        if len({item["exDate"] for item in actions[symbol]}) != len(actions[symbol]):
            raise ValueError(f"Duplicate dividend date for {symbol}")
    return actions


def backfill_verified(series: dict, actions: list[dict]) -> list[dict]:
    """Apply each cash distribution only if Adj Close has no ex-date factor yet."""
    bars = series.get("bars", {})
    applied = []
    for action in actions:
        day, amount = action["exDate"], action["amountUSD"]
        prior_days = [d for d in bars if d < day]
        if not prior_days or day not in bars:
            continue
        previous = max(prior_days)
        before, after = bars[previous], bars[day]
        old_quote, new_quote = before.get("price"), after.get("price")
        old_close, new_close = before.get("close"), after.get("close")
        if not all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in (old_quote, new_quote, old_close, new_close)):
            continue
        if not 0 < amount < old_quote * .3:
            continue
        factor = 1 - amount / old_quote
        existing_factor = (old_close / old_quote) / (new_close / new_quote)
        # A source that already reflects this action wins; a different existing
        # action/factor needs review rather than a guessed second adjustment.
        if abs(existing_factor - factor) < 1e-4:
            continue
        if abs(existing_factor - 1) > 1e-5:
            continue
        for date_key in prior_days:
            bars[date_key]["close"] *= factor
        mark = {"exDate": day, "amountUSD": amount, "source": action["source"],
                "basis": "verified cash distribution absent from source adjustment"}
        after["dividendBackfill"] = mark
        applied.append(mark)
    return applied
