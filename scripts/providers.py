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
HEADERS = {"User-Agent": "LokiRS/1.3.1 (public market research dashboard)"}
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
    # A new cache key prevents an older 5-day intraday cache limiting calibrated history.
    suffix = "30m58d-v2" if interval == "30m" else "1d2y-v2"
    path = cache / f"{safe}.{suffix}.json"
    ttl = 6 * 3600 if interval == "1d" else 1800
    if path.exists() and not refresh and time.time() - path.stat().st_mtime < ttl:
        cached = json.loads(path.read_text())
        captured = cached.get("_lokirsFetchedAt", path.stat().st_mtime)
        end = cached.get("chart", {}).get("result", [{}])[0].get("meta", {}).get("currentTradingPeriod", {}).get("regular", {}).get("end")
        crossed_close = isinstance(end, (int,float)) and captured < end <= time.time()
        if not crossed_close:
            return cached, True
    requested_at = time.time()
    lookback = 2 * 366 if interval == "1d" else 58
    params = {"interval": interval, "includePrePost": "false", "events": "div,splits,capitalGains",
              "period1":int(requested_at-lookback*86400), "period2":int(requested_at)}
    query = urllib.parse.urlencode(params)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{safe}?{query}"
    data = json.loads(fetch_bytes(url))
    if data.get("chart", {}).get("error") or not data.get("chart", {}).get("result"):
        raise ValueError(f"Yahoo returned no chart for {symbol}")
    # Validate before replacing a good cache. A failed refresh never masquerades as fresh data.
    result = data["chart"]["result"][0]
    if not result.get("timestamp"):
        raise ValueError(f"Empty timestamps for {symbol}")
    data["_lokirsFetchedAt"] = time.time()
    data["_lokirsRequestedEvents"] = ["div", "splits", "capitalGains"]
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
    captured = data.get("_lokirsFetchedAt")
    if isinstance(captured, (int, float)) and not isinstance(captured, bool):
        # A bar captured while open never becomes a completed close just because
        # a later process reads the cache after the market has closed.
        now = min(now, datetime.fromtimestamp(captured, UTC))
    quote = result["indicators"]["quote"][0]
    raw_closes = quote.get("close", [])
    # The reference's public return columns match dividend-adjusted daily history.
    # Keep the quoted closing price separately; never silently mix the two bases.
    adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose", [])
    closes = adjusted if interval == "1d" else raw_closes
    if interval == "1d" and not adjusted:
        raise ValueError("Daily dividend-adjusted close history is missing")
    volumes = quote.get("volume", [])
    session_ends, session_starts = {}, {}
    def collect_sessions(periods):
        if isinstance(periods, list):
            for item in periods:
                collect_sessions(item)
        elif isinstance(periods, dict):
            if "start" in periods and "end" in periods:
                day = datetime.fromtimestamp(periods["start"], tz).date().isoformat()
                session_ends[day] = int(periods["end"])
                session_starts[day] = int(periods["start"])
            elif "regular" in periods:
                collect_sessions(periods["regular"])
    collect_sessions(meta.get("tradingPeriods", []))
    bars, pending, source_dates = {}, [], []
    for i, timestamp in enumerate(result.get("timestamp", [])):
        value = closes[i] if i < len(closes) else None
        stamp = datetime.fromtimestamp(timestamp, tz)
        # Yahoo daily candles are labelled by session start. Do not treat an open session as a close.
        session_end = datetime.fromtimestamp(session_ends[stamp.date().isoformat()], tz) if stamp.date().isoformat() in session_ends else stamp.replace(hour=16, minute=0, second=0, microsecond=0)
        if interval == "1d":
            if now < session_end:
                continue
            key = stamp.date().isoformat()
            source_dates.append(key)
            if value is None or not math.isfinite(value) or value <= 0:
                pending.append(key)
                continue
        else:
            if value is None or not math.isfinite(value) or value <= 0:
                continue
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
    action_dates = []
    for events in result.get("events", {}).values():
        for item in events.values() if isinstance(events, dict) else []:
            if isinstance(item, dict) and isinstance(item.get("date"), (int,float)):
                action_dates.append(datetime.fromtimestamp(item["date"], tz).date().isoformat())
    return {"bars": dict(sorted(bars.items())), "currency": meta.get("currency", "USD"), "timezone": str(tz),
            "sessionEnds":session_ends, "sessionStarts":session_starts, "pendingDailyDates":sorted(set(pending)),
            "dailySourceDates":sorted(set(source_dates)), "corporateActionDates":sorted(set(action_dates)),
            "actionsChecked":set(data.get("_lokirsRequestedEvents", [])) >= {"div","splits","capitalGains"},
            "regularMarketTime":meta.get("regularMarketTime"), "observedThrough":now.isoformat()}


def reconcile_latest_daily(daily: dict, intraday: dict, now=None) -> dict:
    """Reconstruct only a missing latest daily close from complete observed 30m bars.

    Never fill an open session, stale intraday data, missing adjustment metadata,
    non-unit last adjustment factors, or dates with a corporate action. The
    reconstructed close is provisional and carries explicit provenance.
    """
    now = now or datetime.now(UTC)
    if not daily.get("actionsChecked") or not intraday.get("bars") or not daily.get("bars"):
        return daily
    tz = ZoneInfo(daily.get("timezone", "America/New_York"))
    if tz.key not in ("America/New_York", "US/Eastern"):
        return daily
    observed = min(now, datetime.fromisoformat(daily.get("observedThrough", now.isoformat())),
                   datetime.fromisoformat(intraday.get("observedThrough", now.isoformat())))
    closes = intraday.get("sessionEnds", {})
    completed = [d for d,t in closes.items() if t <= observed.timestamp()]
    if not completed:
        return daily
    day = max(completed)
    if day in daily["bars"]:
        return daily
    before = [d for d in daily["bars"] if d < day]
    if not before:
        return daily
    previous = max(before)
    gap = (datetime.fromisoformat(day)-datetime.fromisoformat(previous)).days
    if not 0 < gap <= 4 or any(previous < d <= day for d in daily.get("corporateActionDates", [])):
        return daily
    missing = [d for d in daily.get("dailySourceDates", []) if previous < d <= day]
    market_time = daily.get("regularMarketTime")
    missing_latest = missing == [day] or (not missing and isinstance(market_time, (int,float)) and market_time >= closes[day]
                                         and datetime.fromtimestamp(market_time,tz).date().isoformat() == day)
    if not missing_latest:
        return daily
    prior = daily["bars"][previous]
    if not prior.get("price") or abs(prior["close"]/prior["price"]-1) > 1e-8:
        return daily
    start, end = intraday.get("sessionStarts", {}).get(day), closes[day]
    if start is None or (end-start) % 1800:
        return daily
    required = list(range(start+1800, end+1, 1800))
    bars = intraday["bars"]
    if not required or not all(t in bars and math.isfinite(bars[t]["close"]) and bars[t]["close"] > 0 for t in required):
        return daily
    value = bars[end]["close"]
    daily["bars"][day] = {"close":value,"price":value,"volume":None,"reconstructed":True,
                           "basis":"completed-intraday-close","sourceTime":datetime.fromtimestamp(end,UTC).isoformat()}
    daily["bars"] = dict(sorted(daily["bars"].items()))
    daily.setdefault("reconstructedDates", []).append(day)
    return daily


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


def fetch_sentiment(previous=None) -> dict:
    from sentiment_sources import fetch_index
    return fetch_index(lambda url: fetch_bytes(url, attempts=1), previous=previous)


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
