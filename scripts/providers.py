"""Public, unauthenticated data adapters. Python 3.11+, standard library only."""
from __future__ import annotations

import csv
import io
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

UTC = timezone.utc
HEADERS = {"User-Agent": "OpenRS/1.0 (personal research dashboard)"}
FRED_IDS = ["WALCL", "WTREGEN", "RRPONTSYD", "BAMLH0A0HYM2", "BAMLC0A0CM", "NFCI", "DTWEXBGS", "DFII10"]


def fetch_bytes(url: str, attempts: int = 3) -> bytes:
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=25) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            # Never work around access denials, challenges, paywalls or regional blocks.
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
            delay = min(float(exc.headers.get("Retry-After", 2 ** (attempt + 2))), 30)
            time.sleep(delay)
        except (TimeoutError, urllib.error.URLError):
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("No response")


def cached_chart(symbol: str, interval: str, cache: Path, refresh: bool = False) -> tuple[dict, bool]:
    safe = urllib.parse.quote(symbol, safe="")
    path = cache / f"{safe}.{interval}.json"
    ttl = 6 * 3600 if interval == "1d" else 1800
    if path.exists() and not refresh and time.time() - path.stat().st_mtime < ttl:
        return json.loads(path.read_text()), True
    period = "2y" if interval == "1d" else "5d"
    query = urllib.parse.urlencode({"range": period, "interval": interval, "includePrePost": "false", "events": "splits"})
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{safe}?{query}"
    data = json.loads(fetch_bytes(url))
    if data.get("chart", {}).get("error") or not data.get("chart", {}).get("result"):
        raise ValueError(f"Yahoo returned no chart for {symbol}")
    # Validate before replacing a good cache. A failed refresh never masquerades as fresh data.
    result = data["chart"]["result"][0]
    if not result.get("timestamp"):
        raise ValueError(f"Empty timestamps for {symbol}")
    cache.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, separators=(",", ":")))
    temp.replace(path)
    return data, False


def parse_chart(data: dict, interval: str, now: datetime | None = None) -> dict:
    result = data["chart"]["result"][0]
    meta = result["meta"]
    tz = ZoneInfo(meta.get("exchangeTimezoneName", "America/New_York"))
    now = now or datetime.now(UTC)
    quote = result["indicators"]["quote"][0]
    raw_closes = quote.get("close", [])
    # The reference's public return columns match dividend-adjusted daily history.
    # Keep the quoted closing price separately; never silently mix the two bases.
    adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose", [])
    closes = adjusted if interval == "1d" else raw_closes
    if interval == "1d" and not adjusted:
        raise ValueError("Daily dividend-adjusted close history is missing")
    volumes = quote.get("volume", [])
    bars = {}
    for i, timestamp in enumerate(result.get("timestamp", [])):
        value = closes[i] if i < len(closes) else None
        if value is None or not math.isfinite(value) or value <= 0:
            continue
        stamp = datetime.fromtimestamp(timestamp, tz)
        # Yahoo daily candles are labelled by session start. Do not treat an open session as a close.
        session_end = stamp.replace(hour=16, minute=0, second=0, microsecond=0)
        if interval == "1d":
            if now < session_end:
                continue
            key = stamp.date().isoformat()
        else:
            # 30-minute closes permit exact 1h / 4h measurements, including the 16:00 close.
            if stamp.hour < 9 or (stamp.hour == 9 and stamp.minute < 30) or stamp >= session_end:
                continue
            end = min(stamp + timedelta(minutes=30), session_end)
            if now < end:
                continue
            key = int(end.timestamp())
        raw_price = raw_closes[i] if i < len(raw_closes) else None
        bars[key] = {"close": float(value), "price": float(raw_price) if raw_price is not None and math.isfinite(raw_price) else None,
                     "volume": volumes[i] if i < len(volumes) else None}
    return {"bars": dict(sorted(bars.items())), "currency": meta.get("currency", "USD"), "timezone": str(tz)}


def parse_fred(payload: bytes) -> dict[str, dict[str, float]]:
    """FRED returns a ZIP rather than one CSV for mixed-frequency requests."""
    tables = []
    if payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            tables = [archive.read(name).decode("utf-8-sig") for name in archive.namelist() if name.endswith(".csv")]
    else:
        tables = [payload.decode("utf-8-sig")]
    series = {key: {} for key in FRED_IDS}
    for table in tables:
        for row in csv.DictReader(io.StringIO(table)):
            date = row.get("observation_date", row.get("DATE", ""))
            for key in FRED_IDS:
                try:
                    value = float(row.get(key, ""))
                    if math.isfinite(value) and date:
                        series[key][date] = value
                except (TypeError, ValueError):
                    pass
    return series


def fetch_fred(cache: Path, refresh: bool = False) -> dict:
    path = cache / "fred.bin"
    if not path.exists() or refresh or time.time() - path.stat().st_mtime > 12 * 3600:
        since = (datetime.now(UTC).date() - timedelta(days=6 * 366)).isoformat()
        query = urllib.parse.urlencode({"id": ",".join(FRED_IDS), "cosd": since})
        payload = fetch_bytes("https://fred.stlouisfed.org/graph/fredgraph.csv?" + query)
        parsed = parse_fred(payload)
        if not any(parsed.values()):
            raise ValueError("No FRED observations in response")
        cache.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return parsed
    return parse_fred(path.read_bytes())


def fetch_sentiment() -> dict:
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    try:
        data = json.loads(fetch_bytes(url, attempts=1))
        fg = data["fear_and_greed"]
        value = float(fg["score"])
        if not 0 <= value <= 100:
            raise ValueError("Invalid CNN score")
        return {"status": "ok", "source": "CNN", "url": "https://www.cnn.com/markets/fear-and-greed", "value": value,
                "rating": fg.get("rating"), "asOf": fg.get("timestamp"), "previousClose": fg.get("previous_close"),
                "weekAgo": fg.get("previous_1_week"), "monthAgo": fg.get("previous_1_month"), "yearAgo": fg.get("previous_1_year")}
    except Exception as exc:
        return {"status": "unavailable", "source": "CNN", "value": None, "reason": str(exc)[:180],
                "url": "https://www.cnn.com/markets/fear-and-greed"}


def stock_contract_symbols(data: dict, symbols: set[str]) -> list[str]:
    active = set()
    for row in data.get("symbols", []):
        classification = " ".join([str(row.get("underlyingType", "")), str(row.get("underlyingSubType", "")), str(row.get("assetClass", ""))]).upper()
        # AI / CVX etc can denote both an equity and a cryptocurrency. Symbol equality alone is unsafe.
        if not any(word in classification for word in ["STOCK", "EQUITY", "EQUITIES"]):
            continue
        if row.get("status") == "TRADING" and row.get("quoteAsset") == "USDT" and row.get("contractType") == "PERPETUAL":
            active.add(row["baseAsset"])
    return sorted(symbols & active)


def fetch_contracts(symbols: set[str]) -> dict:
    """Display metadata only; no orders, authentication or trading endpoints."""
    try:
        data = json.loads(fetch_bytes("https://fapi.binance.com/fapi/v1/exchangeInfo", attempts=1))
        active = stock_contract_symbols(data, symbols)
        if not active:
            raise ValueError("No explicitly classified stock underlyings; filter disabled rather than matching crypto tickers")
        return {"status": "ok", "source": "Binance exchangeInfo (verified equity classifications)", "symbols": active}
    except Exception as exc:
        return {"status": "unavailable", "source": "Binance exchangeInfo", "symbols": [], "reason": str(exc)[:180]}
