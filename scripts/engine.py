"""Transparent calculations, intentionally independent of the reference site's private formulas."""
from __future__ import annotations

import calendar
import math
from bisect import bisect_right
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def rnd(value, digits=4):
    return round(value, digits) if value is not None and math.isfinite(value) else None


def change(series: dict, start, end):
    a, b = series.get(start), series.get(end)
    return (b["close"] / a["close"] - 1) * 100 if a and b and a["close"] > 0 else None


def excess(asset: dict, benchmark: dict, start, end):
    a, b = change(asset, start, end), change(benchmark, start, end)
    return a - b if a is not None and b is not None else None


def weighted_score(asset, benchmark, sessions, at, weights):
    parts = []
    for period, weight in weights.items():
        period = int(period)
        if at < period:
            return None
        value = excess(asset, benchmark, sessions[at - period], sessions[at])
        if value is None:
            return None
        parts.append(value * weight)
    return sum(parts)


def month_before(value: str) -> str:
    current = date.fromisoformat(value)
    year, month = (current.year - 1, 12) if current.month == 1 else (current.year, current.month - 1)
    return date(year, month, min(current.day, calendar.monthrange(year, month)[1])).isoformat()


def rolling_excess(asset, benchmark, sessions, end, target):
    pos = bisect_right(sessions, target) - 1
    if pos < 0:
        return {"value": None, "from": None, "to": end, "target": target}
    start = sessions[pos]
    return {"value": rnd(excess(asset, benchmark, start, end)), "from": start, "to": end, "target": target}


def percentiles(values: dict) -> dict:
    """Average ranks for ties, 0..100 inclusive. Undefined when fewer than two valid observations."""
    items = sorted((value, key) for key, value in values.items() if value is not None)
    if len(items) < 2:
        return {key: None for _, key in items}
    result = {}
    i = 0
    while i < len(items):
        j = i + 1
        while j < len(items) and items[j][0] == items[i][0]:
            j += 1
        percentile = 100 * ((i + j - 1) / 2) / (len(items) - 1)
        for _, key in items[i:j]:
            result[key] = rnd(percentile, 1)
        i = j
    return result


def intraday_clock_excess(asset: dict, benchmark: dict):
    common = sorted(set(asset) & set(benchmark))
    if not common:
        return {"h1": None, "h4": None, "asOf": None}
    end = common[-1]
    result = {"asOf": datetime.fromtimestamp(end, timezone.utc).isoformat()}
    for hours, name in [(1, "h1"), (4, "h4")]:
        start = end - hours * 3600
        # Missing exact timestamps remain missing; never substitute 1 bar for 1 elapsed hour.
        same_session = datetime.fromtimestamp(start, timezone.utc).date() == datetime.fromtimestamp(end, timezone.utc).date()
        result[name] = rnd(excess(asset, benchmark, start, end)) if same_session else None
    return result


def intraday_excess(asset: dict, benchmark: dict):
    """Reference-style 1H candle steps, reconstructed from completed 30m closes.

    NY regular hours create hourly candle ends at 10:30..15:30 and 16:00.
    Consequently the final candle is 30 minutes. Return elapsed hours explicitly
    rather than pretending that N bars are always N clock hours.
    """
    tz = ZoneInfo("America/New_York")
    grid = sorted(t for t in benchmark if (lambda d: d.minute == 30 or (d.hour == 16 and d.minute == 0))(datetime.fromtimestamp(t, tz)))
    result = {"h1": None, "h4": None, "asOf": None, "basis": "completed 1H candle steps, reconstructed from 30m bars"}
    if not grid or grid[-1] not in asset:
        return result
    end = grid[-1]
    result["asOf"] = datetime.fromtimestamp(end, timezone.utc).isoformat()
    for n in [1, 4]:
        if len(grid) > n:
            start = grid[-1 - n]
            result[f"h{n}"] = rnd(excess(asset, benchmark, start, end))
            result[f"h{n}Start"] = datetime.fromtimestamp(start, timezone.utc).isoformat()
            result[f"h{n}ElapsedHours"] = (end - start) / 3600
    clock = intraday_clock_excess(asset, benchmark)
    result["clockH1"], result["clockH4"] = clock["h1"], clock["h4"]
    return result


def breadth(daily, sessions, stocks):
    history = []
    for at in range(max(50, len(sessions) - 43), len(sessions)):
        end = sessions[at]
        metrics = {k: [0, 0] for k in ["above20", "above50", "advancing", "positive20"]}
        for stock in stocks:
            bars = daily.get(stock["symbol"], {}).get("bars", {})
            if end not in bars:
                continue
            close = bars[end]["close"]
            for n, key in [(20, "above20"), (50, "above50")]:
                values = [bars.get(d, {}).get("close") for d in sessions[at - n + 1:at + 1]]
                if all(v is not None for v in values):
                    metrics[key][1] += 1
                    metrics[key][0] += close > sum(values) / n
            for n, key in [(1, "advancing"), (20, "positive20")]:
                if sessions[at - n] in bars:
                    metrics[key][1] += 1
                    metrics[key][0] += close > bars[sessions[at - n]]["close"]
        history.append({"date": end, **{k: {"value": rnd(100 * v[0] / v[1], 2) if v[1] else None,
                                           "count": v[0], "total": v[1]} for k, v in metrics.items()}})
    return history


def build_equities(universe, settings, daily, intra, prior=None):
    benchmark_symbol = settings["benchmark"]
    benchmark = daily[benchmark_symbol]["bars"]
    sessions = sorted(benchmark)
    if len(sessions) < 253:
        raise ValueError("Benchmark needs at least 253 completed sessions")
    end, at = sessions[-1], len(sessions) - 1
    stocks = universe["stocks"]
    weights = settings["scoreWeights"]
    scores, ranks = {}, {}
    # Reconstruct daily ranks with today's fixed universe; no claim of a point-in-time backtest.
    for ix in range(max(20, at - 64), at + 1):
        values = {s["symbol"]: weighted_score(daily.get(s["symbol"], {}).get("bars", {}), benchmark, sessions, ix, weights) for s in stocks}
        ordered = sorted(((-v, symbol) for symbol, v in values.items() if v is not None))
        scores[ix] = values
        ranks[ix] = {symbol: i + 1 for i, (_, symbol) in enumerate(ordered)}
    sector_values = {}
    for sector in universe["sectors"]:
        bars = daily.get(sector["symbol"], {}).get("bars", {})
        sector_values[sector["symbol"]] = weighted_score(bars, benchmark, sessions, at, weights)
    sector_ranks = {symbol: i + 1 for i, (_, symbol) in enumerate(sorted((-v, s) for s, v in sector_values.items() if v is not None))}
    long_values = {s["symbol"]: weighted_score(daily.get(s["symbol"], {}).get("bars", {}), benchmark, sessions, at, settings["longTermWeights"]) for s in stocks}
    long_percentiles = percentiles(long_values)
    old = {r["symbol"]: r for r in (prior or {}).get("rows", [])}
    rows = []
    for stock in stocks:
        symbol, sector = stock["symbol"], stock["sector"]
        bars = daily.get(symbol, {}).get("bars", {})
        latest = max(bars) if bars else old.get(symbol, {}).get("asOf")
        valid = end in bars
        score = scores[at].get(symbol)
        rank = ranks[at].get(symbol)
        previous = ranks[at - 1].get(symbol)
        streak = 0
        for ix in range(at, max(19, at - 65), -1):
            if ranks.get(ix, {}).get(symbol, math.inf) <= math.ceil(len(ranks.get(ix, {})) * settings["topFraction"]):
                streak += 1
            else:
                break
        sector_bars = daily.get(sector, {}).get("bars", {})
        week_target = (date.fromisoformat(end) - timedelta(days=7)).isoformat()
        week = rolling_excess(bars, benchmark, sessions, end, week_target)
        month = rolling_excess(bars, benchmark, sessions, end, month_before(end))
        intraday = intraday_excess(intra.get(symbol, {}).get("bars", {}), intra.get(benchmark_symbol, {}).get("bars", {}))
        history = [{"date": day, "close": rnd(bars[day]["close"]), "benchmark": rnd(benchmark[day]["close"])}
                   for day in sessions[-settings["historySessions"]:] if day in bars]
        ratios = [point["close"] / point["benchmark"] for point in history[-21:]]
        rs_line = [rnd(value / ratios[0] * 100) for value in ratios] if ratios else []
        sector_score = sector_values.get(sector)
        rows.append({**stock, "rank": rank, "rankDelta": previous - rank if previous and rank else None,
                     "price": rnd(bars[latest].get("price", bars[latest]["close"]) if bars and latest else old.get(symbol, {}).get("price")),
                     "currency": daily.get(symbol, {}).get("currency", "USD"), "asOf": latest,
                     "status": "ok" if valid else "stale" if latest else "unavailable", "score": rnd(score),
                     "d1": rnd(excess(bars, benchmark, sessions[at - 1], end)), "week": week, "month": month,
                     "intra": intraday, "longRS": long_percentiles.get(symbol), "streak": streak if score is not None else None,
                     "streakCapped": streak == 65, "sectorRank": sector_ranks.get(sector), "sectorScore": rnd(sector_score),
                     "vsSector": rnd(score - sector_score) if score is not None and sector_score is not None else None,
                     "vsSectorDay": rnd(excess(bars, sector_bars, sessions[at - 1], end)), "rsLine": rs_line,
                     "history": history})
    rows.sort(key=lambda row: (row["rank"] is None, row["rank"] or 99999, row["symbol"]))
    sectors = [{**s, "rank": sector_ranks.get(s["symbol"]), "score": rnd(sector_values[s["symbol"]])} for s in universe["sectors"]]
    return {"asOf": end, "rows": rows, "sectors": sectors, "breadth": breadth(daily, sessions, stocks),
            "benchmark": {"symbol": benchmark_symbol, "price": rnd(benchmark[end].get("price", benchmark[end]["close"])), "asOf": end,
                          "d1": rnd(change(benchmark, sessions[at - 1], end))}}


def macro_summary(series, today: date):
    specs = [("BAMLH0A0HYM2", "高收益債利差", "%", 3, -1), ("BAMLC0A0CM", "投資級債利差", "%", 3, -1),
             ("NFCI", "全國金融狀況指數", "", 5, -1), ("NET_LIQUIDITY", "Fed 淨流動性", "兆美元", 5, 1),
             ("DTWEXBGS", "廣義美元指數", "", 5, -1), ("DFII10", "10 年實質利率", "%", 5, -1)]
    cutoff = today.isoformat()
    series = {k: {d: v for d, v in values.items() if d <= cutoff} for k, values in series.items()}
    components = ["WALCL", "WTREGEN", "RRPONTSYD"]
    net, component_dates = {}, {}
    # Anchor on the Fed's weekly observation and use only already-observed components.
    for day, walcl in sorted(series.get("WALCL", {}).items()):
        values, dates = {}, {"WALCL": day}
        for key in components[1:]:
            eligible = [d for d in series.get(key, {}) if d <= day]
            if eligible:
                last = max(eligible)
                if (date.fromisoformat(day) - date.fromisoformat(last)).days <= 8:
                    values[key], dates[key] = series[key][last], last
        if len(values) == 2:
            # WALCL/WTREGEN are millions USD; RRPONTSYD is billions USD.
            net[day] = (walcl - values["WTREGEN"] - values["RRPONTSYD"] * 1000) / 1_000_000
            component_dates[day] = dates
    series["NET_LIQUIDITY"] = net
    result = []
    for key, name, unit, years, direction in specs:
        values = series.get(key, {})
        if not values:
            result.append({"id": key, "name": name, "unit": unit, "status": "unavailable", "value": None})
            continue
        end = max(values)
        prior = [d for d in values if d <= month_before(end)]
        delta = values[end] - values[max(prior)] if prior else None
        start = (date.fromisoformat(end) - timedelta(days=365 * years)).isoformat()
        history = [v for d, v in values.items() if start <= d <= end]
        # Ease percentile: high=looser for all six series, with each series' direction explicit.
        percentile = 100 * sum(direction * v <= direction * values[end] for v in history) / len(history)
        result.append({"id": key, "name": name, "unit": unit, "status": "ok", "value": rnd(values[end]),
                       "asOf": end, "ageDays": (today - date.fromisoformat(end)).days, "changeMonth": rnd(delta),
                       "easePercentile": rnd(percentile, 1), "windowYears": years, "direction": direction,
                       "componentDates": component_dates.get(end) if key == "NET_LIQUIDITY" else None,
                       "url": "https://fred.stlouisfed.org/series/" + ("WALCL" if key == "NET_LIQUIDITY" else key)})
    return result
