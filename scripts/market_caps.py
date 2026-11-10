"""Dated USD market caps from Nasdaq's public stock screener; never infer from price.

This is an independent observation, not historical market cap on the equity
snapshot's session. Retained observations keep their original dates and status.
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from providers import fetch_bytes

SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true"
SOURCE_URL = "https://www.nasdaq.com/market-activity/stocks/screener"


def normalize_symbol(value):
    return str(value).strip().upper().replace("/", "-").replace(".", "-")


def parse_cap(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) and value > 0 else None
    text = str(value).strip().replace(",", "").replace("$", "").upper()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([KMBT]?)", text)
    if not match:
        return None
    cap = float(match[1]) * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}[match[2]]
    return cap if math.isfinite(cap) and cap > 0 else None


def parse_screener(payload, fetched_at):
    if (payload.get("status") or {}).get("rCode", 200) != 200:
        raise ValueError("Nasdaq returned an unsuccessful screener response")
    data = payload.get("data") or {}
    rows = data.get("rows") or (data.get("table") or {}).get("rows") or []
    if not rows:
        raise ValueError("Nasdaq returned no stock screener rows")
    result = {}
    for row in rows:
        cap = parse_cap(row.get("marketCap"))
        if not row.get("symbol") or cap is None:
            continue
        result[normalize_symbol(row["symbol"])] = {
            "marketCap": cap, "marketCapCurrency": "USD",
            "marketCapAsOf": data.get("asOf"), "marketCapFetchedAt": fetched_at,
            "marketCapSource": SOURCE_URL,
        }
    if not result:
        raise ValueError("Nasdaq returned no valid positive market caps")
    return result


def fetch_market_caps(cache: Path, refresh=False):
    path = cache / "nasdaq-market-caps-v1.json"
    if path.exists() and not refresh and time.time() - path.stat().st_mtime < 6 * 3600:
        cached = json.loads(path.read_text())
        return parse_screener(cached["payload"], cached["fetchedAt"])
    payload = json.loads(fetch_bytes(SCREENER_URL, attempts=1))
    fetched_at = datetime.now(timezone.utc).isoformat()
    result = parse_screener(payload, fetched_at)
    cache.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"payload": payload, "fetchedAt": fetched_at}, separators=(",", ":")))
    temporary.replace(path)
    return result


def attach_market_caps(rows, observations, prior=None, error=None):
    old = {row["symbol"]: row for row in (prior or {}).get("rows", [])}
    fields = ["marketCap", "marketCapCurrency", "marketCapAsOf", "marketCapFetchedAt", "marketCapSource"]
    for row in rows:
        current = observations.get(normalize_symbol(row["symbol"]))
        previous = old.get(row["symbol"], {})
        if current and parse_cap(current.get("marketCap")) is not None:
            row.update({key: current.get(key) for key in fields}, marketCapStatus="ok")
        elif parse_cap(previous.get("marketCap")) is not None:
            row.update({key: previous.get(key) for key in fields}, marketCapStatus="stale")
        else:
            row.update({key: None for key in fields}, marketCapStatus="unavailable")
    available = sum(row["marketCapStatus"] != "unavailable" for row in rows)
    stale = sum(row["marketCapStatus"] == "stale" for row in rows)
    return {"source": SOURCE_URL, "currency": "USD", "availableCount": available,
            "currentCount": available - stale, "staleCount": stale,
            "missingCount": len(rows) - available, "error": error,
            "timing": "Independent source observation; fetchedAt is retrieval time, not the equity close or a historical valuation."}


def refresh_market_caps(rows, prior, cache, refresh=False):
    try:
        observations, error = fetch_market_caps(cache, refresh), None
    except Exception as exc:
        observations, error = {}, str(exc)[:180]
    return attach_market_caps(rows, observations, prior, error)
