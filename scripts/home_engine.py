"""Transparent cross-market calculations for the LokiRS home page."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo

PERIODS = (1, 5, 20, 60)


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse_market_daily(payload, session="exchange", now=None):
    result = payload["chart"]["result"][0]
    meta = result["meta"]
    tz = ZoneInfo(meta.get("exchangeTimezoneName", "America/New_York"))
    now = now or datetime.now(timezone.utc)
    captured = payload.get("_lokirsFetchedAt")
    if isinstance(captured, (int,float)) and not isinstance(captured, bool):
        now = min(now, datetime.fromtimestamp(captured, timezone.utc))
    quote = result["indicators"]["quote"][0]
    raw = quote.get("close", [])
    adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose", [])
    bars, pending, source_dates = {}, [], []
    for i, stamp in enumerate(result.get("timestamp", [])):
        local = datetime.fromtimestamp(stamp, tz)
        # Preserve FX exchange-date labels across London DST; crypto uses UTC calendar days.
        if session in ("utc24h", "fx"):
            label = datetime.fromtimestamp(stamp, timezone.utc) if session == "utc24h" else local
            end = label.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        else:
            label = local
            end = local.replace(hour=16, minute=0, second=0, microsecond=0)
        if now < end:
            continue
        day = label.date().isoformat()
        source_dates.append(day)
        price = raw[i] if i < len(raw) else None
        close = adjusted[i] if i < len(adjusted) else None
        # Some FX sources omit Adj Close; FX has no distributions to adjust.
        if not finite(close) and session in ("utc24h", "fx"):
            close = price
        if not finite(close) or close <= 0 or not finite(price) or price <= 0:
            pending.append(day)
            continue
        bars[day] = {"close": float(close), "price": float(price)}
    return {"bars": dict(sorted(bars.items())), "currency": meta.get("currency", "USD"), "timezone": str(tz),
            "pendingDailyDates": sorted(set(pending)), "dailySourceDates": sorted(set(source_dates)),
            "observedThrough": now.isoformat()}


def absolute_return(bars, start, end):
    first, last = bars.get(start, {}).get("close"), bars.get(end, {}).get("close")
    return (last / first - 1) * 100 if finite(first) and first > 0 and finite(last) else None


def cross_snapshot(markets, daily, calendar, index, weights, minimum_coverage=.8):
    end = calendar[index]
    absolute = {}
    for market in markets:
        bars = daily.get(market["symbol"], {}).get("bars", {})
        absolute[market["symbol"]] = {
            str(p): absolute_return(bars, calendar[index-p], end) if index >= p else None for p in PERIODS
        }
    required = math.ceil(len(markets) * minimum_coverage)
    medians = {}
    counts = {}
    for period in PERIODS:
        values = [returns[str(period)] for returns in absolute.values() if finite(returns[str(period)])]
        counts[str(period)] = len(values)
        medians[str(period)] = median(values) if len(values) >= required else None
    rows = []
    for market in markets:
        symbol = market["symbol"]
        excess = {p: value - medians[p] if finite(value) and finite(medians[p]) else None for p, value in absolute[symbol].items()}
        score = sum(excess[p] * weight for p, weight in weights.items()) if all(finite(excess.get(p)) for p in weights) else None
        rows.append({**market, "absolute": absolute[symbol], "excess": excess, "score": score, "rank": None})
    valid = sorted((r for r in rows if finite(r["score"])), key=lambda r: (-r["score"], r["symbol"]))
    for rank, row in enumerate(valid, 1):
        row["rank"] = rank
    return rows, medians, counts


def build_cross_markets(config, daily):
    benchmark = config.get("benchmark", "SPY")
    calendar = sorted(daily.get(benchmark, {}).get("bars", {}))
    if len(calendar) < 66:
        raise ValueError("Insufficient completed SPY sessions for cross-market calculations")
    markets, weights = config["markets"], config["scoreWeights"]
    end = len(calendar)-1
    minimum = config.get("minimumCoverage", .8)
    rows, medians, counts = cross_snapshot(markets, daily, calendar, end, weights, minimum)
    previous, _, _ = cross_snapshot(markets, daily, calendar, end-5, weights, minimum)
    previous_ranks = {r["symbol"]: r["rank"] for r in previous}
    # A separate median-return index provides the 21-session relative-strength line.
    daily_medians = {}
    for index in range(max(1, end-63), end+1):
        values = [absolute_return(daily.get(m["symbol"], {}).get("bars", {}), calendar[index-1], calendar[index]) for m in markets]
        values = [v for v in values if finite(v)]
        daily_medians[calendar[index]] = median(values) if len(values) >= math.ceil(len(markets)*minimum) else None
    for row in rows:
        series = daily.get(row["symbol"], {})
        bars = series.get("bars", {})
        observed = [d for d in bars if d <= calendar[end]]
        as_of = max(observed) if observed else None
        row.update({"asOf": as_of, "status": "ok" if as_of == calendar[end] and finite(row["score"]) else "stale" if as_of else "unavailable",
                    "dailyCloseReconstructed":bool(bars.get(as_of, {}).get("reconstructed")),
                    "dailyCloseSourceTime":bars.get(as_of, {}).get("sourceTime"),
                    "currency": series.get("currency"), "timezone": series.get("timezone"),
                    "price": bars.get(as_of, {}).get("price"), "rankDelta5d": previous_ranks.get(row["symbol"])-row["rank"] if previous_ranks.get(row["symbol"]) is not None and row["rank"] is not None else None})
        row["history"] = [{"date": day, **bars[day]} for day in calendar[-64:] if day in bars]
        dates = calendar[-21:]
        row["rsLine"] = []
        if all(day in bars and finite(daily_medians.get(day)) for day in dates):
            index_value = 1
            relative = []
            for day in dates:
                index_value *= 1 + daily_medians[day]/100
                relative.append(bars[day]["close"] / index_value)
            row["rsLine"] = [v / relative[0] * 100 for v in relative]
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] or 0, r["symbol"]))
    valid = sum(r["rank"] is not None for r in rows)
    if valid < math.ceil(len(markets)*minimum):
        raise ValueError(f"Cross-market coverage too low: {valid}/{len(markets)}; prior snapshot preserved")
    return {"asOf": calendar[end], "rows": rows, "medians": medians, "sampleCounts": counts,
            "periodFrom": {str(p): calendar[end-p] for p in PERIODS}, "previousRankDate": calendar[end-5], "coverage": valid/len(markets)}


def build_pulse(equities):
    rows = [r for r in equities.get("rows", []) if r.get("status") == "ok" and finite(r.get("rank"))]
    jump = math.ceil(len(equities.get("rows", []))*.5)
    cutoff = math.ceil(len(equities.get("rows", []))*.25)
    sudden = sorted((r for r in rows if (r.get("rankDelta") or 0) >= jump and r["rank"] <= cutoff and (r.get("d1") or 0)>0 and (r.get("intra", {}).get("h4") or 0)>0), key=lambda r: (-r["rankDelta"], r["rank"]))[:8]
    leaders = sorted((r for r in rows if (r.get("streak") or 0)>=7), key=lambda r: (-r["streak"], r["rank"]))[:5]
    weak = sorted((r for r in rows if (r.get("rankDelta") or 0)<=-jump and (r.get("d1") or 0)<0), key=lambda r: (r["rankDelta"], r["rank"]))[:5]
    def compact(r):
        return {k:r.get(k) for k in ["symbol", "name", "rank", "rankDelta", "score", "d1", "streak", "streakCapped"]} | {"h4":r.get("intra", {}).get("h4")}
    return {"asOf": equities.get("asOf"), "scope": "existing US equity universe", "universeCount":len(equities.get("rows", [])),
            "sudden":[compact(r) for r in sudden], "leaders":[compact(r) for r in leaders], "weak":[compact(r) for r in weak],
            "rules":{"minimumRankJump":jump, "suddenRankCutoff":cutoff, "minimumStreak":7}}


def vix_summary(daily, as_of):
    bars = daily.get("bars", {})
    dates = sorted(d for d in bars if d <= as_of)
    if not dates:
        return {"status":"unavailable", "value":None, "asOf":None}
    values = [bars[d]["price"] for d in dates[-20:]]
    value = values[-1]
    return {"status":"ok" if dates[-1] == as_of else "stale", "value":value, "asOf":dates[-1],
            "changeDay":value-bars[dates[-2]]["price"] if len(dates)>1 else None,
            "low20":min(values), "high20":max(values), "history":[bars[d]["price"] for d in dates[-21:]],
            "source":"Yahoo Finance / CBOE VIX", "url":"https://www.cboe.com/tradable_products/vix/"}
