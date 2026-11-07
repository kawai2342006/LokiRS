#!/usr/bin/env python3
"""Download real market data and atomically publish a GitHub Pages JSON snapshot."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from engine import build_equities, macro_summary
from dividend_backfill import load_verified, backfill_verified
from providers import cached_chart, fetch_contracts, fetch_fred, parse_chart, reconcile_latest_daily

ROOT = Path(__file__).resolve().parents[1]


def retry_pending_daily(daily, intra, cache, now, workers=4):
    """Retry a missing latest completed daily bar once before reconstruction."""
    pending = []
    for symbol, series in daily.items():
        ends = intra.get(symbol, {}).get("sessionEnds", {})
        complete = [day for day,end in ends.items() if end <= now.timestamp()]
        if complete and max(complete) in series.get("pendingDailyDates", []):
            pending.append(symbol)
    def get(symbol):
        try:
            raw,_ = cached_chart(symbol, "1d", cache, True)
            result = parse_chart(raw, "1d", now)
            if max(result["bars"], default="") < max(daily[symbol]["bars"], default=""):
                raise ValueError("Retry returned an older observation; retained prior daily data")
            return symbol,result,None
        except Exception as exc:
            return symbol,None,str(exc)[:180]
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(8,workers))) as pool:
        for symbol,result,error in pool.map(get,pending):
            if result is not None:
                daily[symbol] = result
            else:
                failures.append({"symbol":symbol,"interval":"1d_retry","error":error})
    if pending:
        print(f"Retried latest missing daily closes: {len(pending)}; failed {len(failures)}",flush=True)
    return failures


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Ignore cache TTLs")
    parser.add_argument("--workers", type=int, help="Download concurrency, 1–8")
    parser.add_argument("--skip-optional", action="store_true", help="Skip sentiment sources and Binance")
    parser.add_argument("--rankings-only", action="store_true", help="Update equities and sectors; retain dated optional data and homepage")
    args = parser.parse_args()
    settings = json.loads((ROOT / "config/settings.json").read_text())
    universe = json.loads((ROOT / "config/universe.json").read_text())
    output = ROOT / "data/latest.json"
    prior = json.loads(output.read_text()) if output.exists() else {}
    cache = ROOT / ".cache/openrs"
    symbols = sorted({r["symbol"] for r in universe["stocks"] + universe["sectors"]} | {settings["benchmark"]})
    daily, intra, errors = {}, {}, []
    now = datetime.now(timezone.utc)
    start = time.monotonic()

    def get(task):
        symbol, interval = task
        try:
            data, cached = cached_chart(symbol, interval, cache, args.refresh)
            return symbol, interval, parse_chart(data, interval, now), None
        except Exception as exc:
            return symbol, interval, None, str(exc)[:180]

    tasks = [(s, interval) for interval in ["1d", "30m"] for s in symbols]
    workers = max(1, min(8, args.workers or settings["workers"]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for count, (symbol, interval, data, error) in enumerate(executor.map(get, tasks), 1):
            if data is not None:
                (daily if interval == "1d" else intra)[symbol] = data
            else:
                errors.append({"symbol": symbol, "interval": interval, "error": error})
            if count % 100 == 0 or count == len(tasks):
                print(f"Downloaded {count}/{len(tasks)}; failed requests {len(errors)}; {time.monotonic()-start:.0f}s", flush=True)
    if settings["benchmark"] not in daily:
        raise RuntimeError("Benchmark fetch failed. Existing snapshot preserved.")
    errors.extend(retry_pending_daily(daily, intra, cache, now, workers))
    verified_actions = load_verified(ROOT / "config/verified_dividends.json")
    dividend_repairs = []
    for symbol in daily:
        # A missing daily bar on a known ex-date must not be reconstructed from
        # unadjusted intraday prices as if no corporate action happened.
        known_dates = {item["exDate"] for item in verified_actions.get(symbol, [])}
        daily[symbol]["corporateActionDates"] = sorted(set(daily[symbol].get("corporateActionDates", [])) | known_dates)
        reconcile_latest_daily(daily[symbol], intra.get(symbol, {}), now)
        dividend_repairs.extend({"symbol":symbol, **item} for item in backfill_verified(daily[symbol], verified_actions.get(symbol, [])))
    benchmark_daily_day = max(daily[settings["benchmark"]]["bars"], default="")
    benchmark_intra = intra.get(settings["benchmark"], {})
    observed_closes = [day for day,end in benchmark_intra.get("sessionEnds", {}).items()
                       if end <= now.timestamp() and end in benchmark_intra.get("bars", {})]
    if observed_closes and benchmark_daily_day < max(observed_closes):
        raise RuntimeError(f"Daily benchmark lags completed intraday session: daily {benchmark_daily_day}, intraday {max(observed_closes)}. Existing snapshot preserved.")
    result = build_equities(universe, settings, daily, intra, prior)
    if prior.get("asOf") and result["asOf"] < prior["asOf"]:
        raise RuntimeError("New market date predates published snapshot. Existing snapshot preserved.")
    valid = sum(row["status"] == "ok" and row["score"] is not None for row in result["rows"])
    coverage = valid / len(universe["stocks"])
    if coverage < settings["minimumCoverage"]:
        raise RuntimeError(f"Only {coverage:.1%} current coverage, below safety threshold. Existing snapshot preserved.")
    if args.rankings_only:
        result["macro"] = [{**row, "status": "stale"} for row in prior.get("macro", [])]
        macro_error = prior.get("meta", {}).get("macroError")
        macro_status = "retained"
    else:
        try:
            result["macro"] = macro_summary(fetch_fred(cache, args.refresh), now.astimezone(ZoneInfo("Asia/Hong_Kong")).date())
            macro_error, macro_status = None, "updated"
        except Exception as exc:
            result["macro"] = [{**row, "status": "stale"} for row in prior.get("macro", [])]
            macro_error, macro_status = str(exc)[:180], "stale"
    if not args.skip_optional and not args.rankings_only:
        from update_sentiment import update_sentiment_snapshot
        result["sentiment"] = update_sentiment_snapshot(ROOT, previous=prior.get("sentiment"))
    else:
        result["sentiment"] = prior.get("sentiment") or {"status":"unavailable","value":None,"reason":"Skipped by configuration"}
    result["contracts"] = prior.get("contracts", {"status":"unavailable","symbols":[]}) if args.rankings_only else fetch_contracts({s["symbol"] for s in universe["stocks"]}) if not args.skip_optional else {"status": "unavailable", "symbols": []}
    result["meta"] = {"schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat(), "downloadStartedAt": now.isoformat(), "source": "Yahoo Finance public chart / FRED / CNN index via MacroMicro or CNN / Binance",
                      "universeDate": universe["capturedAt"], "universeCount": len(universe["stocks"]), "currentCount": valid,
                      "coverage": round(coverage, 4), "intradayCount": sum(r["intra"]["h1"] is not None for r in result["rows"]),
                      "scoreFormula": " + ".join(f"{w} × excess({p[1:]+'H' if p in ('h1','h4') else p+'D'})" for p,w in settings["scoreWeights"].items()),
                      "scoreModel": settings.get("scoreModel", "daily-three-period-v1"), "calibrationReferenceDates":settings.get("calibrationReferenceDates", []),
                      "scoreWeights": settings["scoreWeights"], "longTermWeights": settings["longTermWeights"],
                      "approximation": True, "priceBasis": "Yahoo Adj Close; independently verified cash distributions are backfilled only when the source lacks the ex-date adjustment. Raw quoted prices unchanged. Missing latest daily closes may use a complete observed regular-session 30m close only on action-free days, explicitly flagged. Intraday: Yahoo Close.",
                      "errors": errors, "macroError": macro_error, "macroUpdateStatus":macro_status, "streakWindow": result["rankHistorySessions"],
                      "reconstructedDailyCount":sum(bool(r.get("dailyCloseReconstructed")) for r in result["rows"]),
                      "verifiedDividendBackfills": dividend_repairs,
                      "benchmarkCloseReconstructed":bool(daily[settings["benchmark"]]["bars"][result["asOf"]].get("reconstructed")),
                      "dailyReconstructionPolicy":"Only a complete regular session's observed 30m close; latest daily missing; unit prior adjustment factor; corporate-action dates excluded; provisional provenance retained.",
                      "notice": "Five-period weights inferred from public reference snapshots and rechecked through 2026-11-06; not an officially confirmed formula. Prices and runtime rankings are independently calculated from Yahoo. Long-term RS and historical ranks remain independent approximations."}
    from validate_snapshot import validate
    validate(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    temp.replace(output)
    print(f"Saved {output.name}: {valid}/{len(universe['stocks'])}, market date {result['asOf']}", flush=True)
    if args.rankings_only:
        return
    # The homepage is independently atomic: a failed optional refresh preserves its prior file.
    from update_home import refresh_home
    try:
        refresh_home(ROOT, equities=result, workers=workers, refresh=False, daily_overrides=daily)
    except Exception as exc:
        print(f"Homepage update failed; prior home.json preserved: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"Update failed: {exc}", file=sys.stderr)
        sys.exit(1)
