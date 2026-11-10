"""Independent regular-session snapshots at completed, full 60-minute candle ends.

Two observed consecutive 30m bars form each 60m candle. The closing 30m stub
is excluded. Daily history is rebased to the prior close's raw-price basis;
current-session corporate actions are excluded until their adjustment is known.
The canonical close snapshot is never written by this module.
"""
from __future__ import annotations

import concurrent.futures
import copy
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from engine import (additional_excess_periods, breadth, change, excess,
                    intraday_excess, month_before, rnd, rolling_excess, score_inputs)

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
CAP_FIELDS = ["marketCap", "marketCapCurrency", "marketCapAsOf", "marketCapFetchedAt", "marketCapSource", "marketCapStatus"]


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def full_hour_grid(series, now):
    """Expected regular-session hour ends, including missing source bars."""
    cutoff = now.timestamp()
    if series.get("observedThrough"):
        cutoff = min(cutoff, datetime.fromisoformat(series["observedThrough"]).timestamp())
    bars = series.get("bars", {})
    days = {datetime.fromtimestamp(stamp, NY).date().isoformat() for stamp in bars} | set(series.get("sessionEnds", {}))
    result = []
    for day in sorted(days):
        regular_open = int(datetime.fromisoformat(day + "T09:30:00").replace(tzinfo=NY).timestamp())
        regular_end = series.get("sessionEnds", {}).get(day)
        if regular_end is None:
            quoted_end = series.get("regularSessionEnd")
            if isinstance(quoted_end, (int, float)) and datetime.fromtimestamp(quoted_end, NY).date().isoformat() == day:
                regular_end = int(quoted_end)
            else:
                regular_end = int(datetime.fromisoformat(day + "T16:00:00").replace(tzinfo=NY).timestamp())
        for end in range(regular_open + 3600, int(regular_end) + 1, 3600):
            if end <= cutoff:
                result.append(end)
    return result


def full_hour_candles(series, now):
    """Require both constituent 30m closes; never turn a stub or gap into 60m."""
    bars, result = series.get("bars", {}), {}
    for end in full_hour_grid(series, now):
        components = [end - 1800, end]
        if all(positive(bars.get(stamp, {}).get("close")) for stamp in components):
            result[end] = {"close": bars[end]["close"], "price": bars[end]["close"],
                           "start": end - 3600, "components": components}
    return result


def current_endpoint(hourly, now):
    today = now.astimezone(NY).date().isoformat()
    candidates = [stamp for stamp in hourly if datetime.fromtimestamp(stamp, NY).date().isoformat() == today]
    if not candidates:
        raise ValueError("No completed full 60m SPY candle for the current New York session. Wait until after 10:30 New York time on a trading day, then retry.")
    return max(candidates)


def normalized_history(series, sessions, baseline, day, endpoint):
    """Keep the prior adjusted history but put it on the prior raw close's scale."""
    base = series.get("bars", {}).get(baseline, {})
    if not positive(base.get("close")) or not positive(base.get("price")):
        return {}, "缺少上一收市價格基準"
    factor = base["price"] / base["close"]
    history = {date: {"close": bar["close"] * factor, "price": bar.get("price")}
               for date, bar in series.get("bars", {}).items()
               if date in sessions and date < day and positive(bar.get("close"))}
    if not series.get("actionsChecked"):
        return history, "缺少當日除權息／拆股核對資料"
    if day in series.get("corporateActionDates", []):
        return history, "當日除權息／拆股，待調整核實後才計分"
    if endpoint is None:
        return history, "缺少相同時點的完整 60m K 線"
    history[day] = {"close": endpoint["close"], "price": endpoint["close"]}
    return history, None


def build_intraday_snapshot(universe, settings, daily, intra, closed, now, generated_at=None, errors=None):
    symbol = settings["benchmark"]
    hourly = {key: full_hour_candles(series, now) for key, series in intra.items()}
    benchmark_hours = hourly.get(symbol, {})
    end = current_endpoint(benchmark_hours, now)
    timestamp = datetime.fromtimestamp(end, UTC).isoformat()
    day = datetime.fromtimestamp(end, NY).date().isoformat()
    sessions = sorted(date for date in daily.get(symbol, {}).get("bars", {}) if date < day)
    if len(sessions) < 64:
        raise ValueError("Intraday snapshot needs at least 64 completed SPY sessions before the snapshot date")
    baseline = sessions[-1]
    prior_hour_days = {datetime.fromtimestamp(stamp, NY).date().isoformat() for stamp in benchmark_hours
                       if datetime.fromtimestamp(stamp, NY).date().isoformat() < day}
    if prior_hour_days and max(prior_hour_days) != baseline:
        raise ValueError("Daily SPY history lags the latest completed prior session; existing snapshots preserved")
    all_symbols = {row["symbol"] for row in universe["stocks"] + universe["sectors"]} | {symbol}
    normalized, notes = {}, {}
    for key in all_symbols:
        bars, note = normalized_history(daily.get(key, {}), sessions, baseline, day, hourly.get(key, {}).get(end))
        normalized[key] = {"bars": bars}
        notes[key] = note
    benchmark = normalized[symbol]["bars"]
    if day not in benchmark:
        raise ValueError("SPY snapshot price/adjustment basis is unavailable: " + str(notes[symbol]))
    periods = sessions + [day]
    at = len(periods) - 1
    weights = settings["scoreWeights"]
    grid = [stamp for stamp in full_hour_grid(intra.get(symbol, {}), now) if stamp <= end]
    parts, scores, hour_returns = {}, {}, {}
    for key in all_symbols:
        values = intraday_excess(hourly.get(key, {}), benchmark_hours, end, grid) if notes[key] is None else {"h1": None, "h4": None, "asOf": None}
        values["basis"] = "full 60m candle steps; both constituent 30m closes observed; closing stubs excluded"
        hour_returns[key] = values
        inputs = score_inputs(normalized[key]["bars"], benchmark, periods, at, weights, values)
        parts[key] = inputs
        scores[key] = sum(inputs[k] * weight for k, weight in weights.items()) if all(v is not None and math.isfinite(v) for v in inputs.values()) else None
    ordered = sorted((-scores[row["symbol"]], row["symbol"]) for row in universe["stocks"] if scores[row["symbol"]] is not None)
    ranks = {key: index + 1 for index, (_, key) in enumerate(ordered)}
    sector_order = sorted((-scores[row["symbol"]], row["symbol"]) for row in universe["sectors"] if scores[row["symbol"]] is not None)
    sector_ranks = {key: index + 1 for index, (_, key) in enumerate(sector_order)}
    # A close published after this candle must never supply future ranks/streaks.
    reference = closed if closed.get("asOf", day) < day else {}
    previous = {row["symbol"]: row for row in reference.get("rows", [])}
    capitalizations = {row["symbol"]: row for row in closed.get("rows", [])}
    rows = []
    for stock in universe["stocks"]:
        key, sector = stock["symbol"], stock["sector"]
        history_bars = normalized[key]["bars"]
        point = hourly.get(key, {}).get(end)
        old = previous.get(key, {})
        score, rank = scores[key], ranks.get(key)
        sector_score = scores.get(sector)
        history = [{"date": date, "close": rnd(history_bars[date]["close"]), "benchmark": rnd(benchmark[date]["close"])}
                   for date in periods[-settings.get("historySessions", 64):] if date in history_bars and date in benchmark]
        ratios = [item["close"] / item["benchmark"] for item in history[-21:]]
        row = {**stock, "rank": rank, "rankDelta": old.get("rank") - rank if old.get("rank") and rank else None,
               "price": rnd(point["close"]) if point else None, "currency": "USD", "asOf": day if point else None,
               "snapshotAt": timestamp if point else None,
               "snapshotBarStart": datetime.fromtimestamp(end - 3600, UTC).isoformat() if point else None,
               "snapshotComponents": point["components"] if point else [],
               "dailyCloseReconstructed": False, "dailyCloseSource": "complete-60m-candle", "dailyCloseSourceTime": timestamp if point else None,
               "dividendBackfill": old.get("dividendBackfill"),
               "status": "ok" if score is not None else "partial" if point else "unavailable",
               "score": rnd(score), "scoreInputs": parts[key],
               "d1": rnd(excess(history_bars, benchmark, baseline, day)), "d1From": baseline,
               **additional_excess_periods(history_bars, benchmark, periods, day),
               "week": rolling_excess(history_bars, benchmark, periods, day, (datetime.fromisoformat(day).date() - timedelta(days=7)).isoformat()),
               "month": rolling_excess(history_bars, benchmark, periods, day, month_before(day)),
               "intra": hour_returns[key], "longRS": old.get("longRS"), "streak": old.get("streak"), "streakCapped": old.get("streakCapped", False),
               "closedMetricsAsOf": reference.get("asOf"), "sectorRank": sector_ranks.get(sector), "sectorScore": rnd(sector_score),
               "vsSector": rnd(score - sector_score) if score is not None and sector_score is not None else None,
               "vsSectorDay": rnd(excess(history_bars, normalized.get(sector, {}).get("bars", {}), baseline, day)),
               "rsLine": [rnd(value / ratios[0] * 100) for value in ratios] if ratios else [], "history": history,
               "intradayNote": notes[key] or ("缺少同時點的期間數據，暫不計分" if score is None else None)}
        for field in CAP_FIELDS:
            row[field] = capitalizations.get(key, {}).get(field)
        if not positive(row.get("marketCap")):
            row.update(marketCap=None, marketCapStatus="unavailable")
        rows.append(row)
    rows.sort(key=lambda row: (row["rank"] is None, row["rank"] or 999999, row["symbol"]))
    valid = len(ordered)
    coverage = valid / len(rows) if rows else 0
    if coverage < settings["minimumCoverage"]:
        raise ValueError(f"Only {coverage:.1%} synchronized intraday scores; minimum is {settings['minimumCoverage']:.0%}. Existing snapshots preserved.")
    session_end = intra[symbol].get("sessionEnds", {}).get(day) or intra[symbol].get("regularSessionEnd")
    if session_end is None or datetime.fromtimestamp(session_end, NY).date().isoformat() != day:
        session_end = int(datetime.fromisoformat(day + "T16:00:00").replace(tzinfo=NY).timestamp())
    return {"asOf": day, "rows": rows,
            "sectors": [{**sector, "rank": sector_ranks.get(sector["symbol"]), "score": rnd(scores.get(sector["symbol"]))} for sector in universe["sectors"]],
            "breadth": breadth(normalized, periods, universe["stocks"]), "rankHistorySessions": reference.get("rankHistorySessions", 0),
            "benchmark": {"symbol": symbol, "price": rnd(benchmark_hours[end]["close"]), "asOf": day, "snapshotAt": timestamp,
                          "snapshotBarStart": datetime.fromtimestamp(end - 3600, UTC).isoformat(), "snapshotComponents": [end - 1800, end],
                          "d1": rnd(change(benchmark, baseline, day))},
            "macro": copy.deepcopy(closed.get("macro", [])), "sentiment": copy.deepcopy(closed.get("sentiment", {"status": "unavailable"})),
            "contracts": copy.deepcopy(closed.get("contracts", {"status": "unavailable", "symbols": []})),
            "meta": {"schemaVersion": 1, "snapshotMode": "intraday", "intervalMinutes": 60, "snapshotAt": timestamp,
                     "snapshotBarStart": datetime.fromtimestamp(end - 3600, UTC).isoformat(),
                     "sessionClose": datetime.fromtimestamp(session_end, UTC).isoformat(),
                     "generatedAt": (generated_at or now).isoformat(), "downloadStartedAt": now.isoformat(),
                     "referenceCloseDate": reference.get("asOf"), "dailyBaselineDate": baseline,
                     "closedMetricsAsOf": reference.get("asOf"), "universeDate": universe.get("capturedAt"),
                     "universeCount": len(rows), "currentCount": valid, "coverage": round(coverage, 4),
                     "intradayCount": sum(row["intra"]["h1"] is not None for row in rows), "approximation": True,
                     "scoreWeights": weights, "longTermWeights": settings.get("longTermWeights", {}),
                     "scoreFormula": " + ".join(f"{weight} × excess({period})" for period, weight in weights.items()),
                     "source": "Yahoo Finance completed regular-session chart bars", "errors": errors or [],
                     "macroUpdateStatus": "retained", "marketCapUpdateStatus": "retained",
                     "priceBasis": "Raw completed 60m close. Prior adjusted daily history rebased to the immediately prior raw close. Current-session corporate actions excluded. Long RS/streak retained from the dated canonical close snapshot.",
                     "notice": "Full 60m endpoints only. Daily returns include the current partial session; ranks compare with the reference close. This is a manually published intraday snapshot, not streaming quotes."}}


def validate_intraday(data):
    meta, rows = data["meta"], data["rows"]
    assert meta["schemaVersion"] == 1 and meta["snapshotMode"] == "intraday" and meta["intervalMinutes"] == 60
    stamp = datetime.fromisoformat(meta["snapshotAt"])
    assert stamp.tzinfo is not None
    end = int(stamp.timestamp())
    assert stamp <= datetime.fromisoformat(meta["downloadStartedAt"]) <= datetime.fromisoformat(meta["generatedAt"])
    assert data["asOf"] == stamp.astimezone(NY).date().isoformat() == data["benchmark"]["asOf"]
    assert stamp.astimezone(NY).minute == 30 and 10 <= stamp.astimezone(NY).hour <= 15
    assert (stamp - datetime.fromisoformat(meta["snapshotBarStart"])).total_seconds() == 3600
    assert stamp <= datetime.fromisoformat(meta["sessionClose"])
    assert meta["dailyBaselineDate"] < data["asOf"]
    assert meta["referenceCloseDate"] is None or meta["referenceCloseDate"] < data["asOf"]
    assert len({row["symbol"] for row in rows}) == len(rows) == meta["universeCount"]
    ranked = sorted((row for row in rows if row["rank"] is not None), key=lambda row: row["rank"])
    assert [row["rank"] for row in ranked] == list(range(1, len(ranked) + 1))
    assert len(ranked) == meta["currentCount"] and abs(meta["coverage"] - len(ranked) / len(rows)) <= .000051
    assert all(a["score"] >= b["score"] - .0001 for a, b in zip(ranked, ranked[1:]))
    for row in [data["benchmark"], *rows]:
        if row.get("price") is not None:
            assert positive(row["price"])
            assert row["snapshotAt"] == meta["snapshotAt"] and row["snapshotBarStart"] == meta["snapshotBarStart"]
            assert row["snapshotComponents"] == [end - 1800, end]
    for row in rows:
        for field in ["score", "d1", "d3", "longRS", "vsSector", "vsSectorDay"]:
            assert row[field] is None or math.isfinite(row[field])
        assert row["closedMetricsAsOf"] == meta["closedMetricsAsOf"]
        if row["rank"] is not None:
            assert row["status"] == "ok" and row["asOf"] == data["asOf"] and not row["intradayNote"]
            assert row["intra"]["asOf"] == meta["snapshotAt"]
            inputs = row["scoreInputs"]
            assert all(value is not None and math.isfinite(value) for value in inputs.values())
            assert abs(sum(inputs[key] * weight for key, weight in meta["scoreWeights"].items()) - row["score"]) <= .000051
        dates = [point["date"] for point in row["history"]]
        assert dates == sorted(set(dates)) and all(day <= data["asOf"] for day in dates)
        assert all(positive(point["close"]) and positive(point["benchmark"]) for point in row["history"])
        for period in ["week", "fortnight", "month"]:
            value = row[period]
            assert value["value"] is None or math.isfinite(value["value"])
            if value["value"] is not None:
                assert value["from"] <= value["target"] < value["to"] == data["asOf"]
        for period in ["h1", "h4"]:
            value = row["intra"].get(period)
            if value is not None:
                start = datetime.fromisoformat(row["intra"][period + "Start"])
                assert abs((stamp - start).total_seconds() / 3600 - row["intra"][period + "ElapsedHours"]) < .000001
    print(f"Intraday verified: {len(ranked)}/{len(rows)} scores, full 60m bar ending {meta['snapshotAt']}")


def write_intraday_snapshot(root, result):
    """Validate and atomically replace only the intraday publication."""
    validate_intraday(result)
    output = Path(root) / "data/intraday.json"
    if output.exists():
        previous = json.loads(output.read_text())
        old_time = previous.get("meta", {}).get("snapshotAt")
        if old_time and datetime.fromisoformat(old_time) > datetime.fromisoformat(result["meta"]["snapshotAt"]):
            raise ValueError("New intraday candle predates the published one; existing snapshot preserved")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    temporary.replace(output)
    return output


def publish_intraday(root, refresh=False, workers=4, now=None):
    from dividend_backfill import load_verified, backfill_verified
    from providers import cached_chart, parse_chart
    root = Path(root)
    now = now or datetime.now(UTC)
    settings = json.loads((root / "config/settings.json").read_text())
    universe = json.loads((root / "config/universe.json").read_text())
    closed = json.loads((root / "data/latest.json").read_text())
    cache = root / ".cache/openrs"
    symbol = settings["benchmark"]
    daily, intra, errors = {}, {}, []
    # Check SPY first, so a pre-open/weekend request does not download the whole universe.
    for interval, destination in [("1d", daily), ("30m", intra)]:
        raw, _ = cached_chart(symbol, interval, cache, refresh)
        destination[symbol] = parse_chart(raw, interval, now)
    current_endpoint(full_hour_candles(intra[symbol], now), now)
    symbols = sorted({row["symbol"] for row in universe["stocks"] + universe["sectors"]} - {symbol})
    tasks = [(key, interval) for interval in ["1d", "30m"] for key in symbols]
    def get(task):
        key, interval = task
        try:
            raw, _ = cached_chart(key, interval, cache, refresh)
            return key, interval, parse_chart(raw, interval, now), None
        except Exception as exc:
            return key, interval, None, str(exc)[:180]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(8, workers))) as executor:
        for count, (key, interval, series, error) in enumerate(executor.map(get, tasks), 1):
            if error:
                errors.append({"symbol": key, "interval": interval, "error": error})
            else:
                (daily if interval == "1d" else intra)[key] = series
            if count % 100 == 0 or count == len(tasks):
                print(f"Intraday downloads {count}/{len(tasks)}; failed {len(errors)}", flush=True)
    verified = load_verified(root / "config/verified_dividends.json")
    for key, series in daily.items():
        series["corporateActionDates"] = sorted(set(series.get("corporateActionDates", [])) | {item["exDate"] for item in verified.get(key, [])})
        backfill_verified(series, verified.get(key, []))
    result = build_intraday_snapshot(universe, settings, daily, intra, closed, now, datetime.now(UTC), errors)
    output = write_intraday_snapshot(root, result)
    print(f"Saved {output.name}: {result['meta']['currentCount']}/{len(result['rows'])}, 60m ending {result['meta']['snapshotAt']}", flush=True)
    return result
