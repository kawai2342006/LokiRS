#!/usr/bin/env python3
"""Download real market data and atomically publish a GitHub Pages JSON snapshot."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from engine import build_equities, macro_summary
from dividend_backfill import load_verified, backfill_verified
from market_caps import refresh_market_caps
from providers import cached_chart, fetch_contracts, fetch_fred, parse_chart, reconcile_latest_daily

ROOT = Path(__file__).resolve().parents[1]


def require_observed_close(benchmark, intraday, now, published_intraday=None, symbol="SPY"):
    """Reject daily history older than an observed, already completed session.

    Use source session timestamps and the independently published 60m snapshot.
    Never guess a trading day by subtracting a calendar day: holidays, weekends
    and early closes retain their real source dates. If every source is stale,
    this check cannot certify the newest exchange session without a calendar.
    """
    ny = ZoneInfo("America/New_York")
    evidence = {}

    def require(day, source):
        date.fromisoformat(day)
        evidence.setdefault(day, []).append(source)

    for label, series in [("daily", benchmark), ("30m", intraday)]:
        observed = now
        if series.get("observedThrough"):
            captured = datetime.fromisoformat(series["observedThrough"])
            if captured.tzinfo is None:
                raise ValueError("Benchmark capture time is missing its timezone")
            observed = min(now, captured)
        end = series.get("regularSessionEnd")
        if isinstance(end, (int, float)) and not isinstance(end, bool) and 0 < end <= observed.timestamp():
            require(datetime.fromtimestamp(end, ny).date().isoformat(), label + " regular-session metadata")
        for day, end in series.get("sessionEnds", {}).items():
            if end <= observed.timestamp() and datetime.fromtimestamp(end, ny).date().isoformat() == day:
                require(day, label + " completed-session metadata")
    # parse_chart records source daily dates only after that session has closed,
    # even when its adjusted price is missing. A missing final 30m bar must not
    # let a known, newer trading date disappear from the freshness check.
    for day in benchmark.get("dailySourceDates", []):
        require(day, "completed daily source date")
    if published_intraday:
        try:
            from intraday_snapshot import validate_intraday
            validate_intraday(published_intraday)
            meta = published_intraday["meta"]
            close = datetime.fromisoformat(meta["sessionClose"])
            generated = datetime.fromisoformat(meta["generatedAt"])
            if (close.tzinfo is not None and close <= now and generated <= now
                    and close.astimezone(ny).date().isoformat() == published_intraday["asOf"]
                    and published_intraday["benchmark"]["symbol"] == symbol):
                require(published_intraday["asOf"], "validated published 60m snapshot after its session close")
        except (AssertionError, KeyError, TypeError, ValueError, OverflowError):
            # Unverified optional evidence cannot assert a new trading session.
            pass
    latest = max(benchmark.get("bars", {}), default="")
    required = max(evidence, default=latest)
    if latest < required:
        sources = "; ".join(evidence[required])
        raise RuntimeError(f"Daily benchmark is stale: {latest or 'missing'}; observed completed session {required} ({sources}). Existing snapshot preserved.")
    print(f"Close freshness: daily {latest}; newest observed completed session {required}. This is source-based validation, not an exchange-calendar guarantee.", flush=True)
    return required


def retry_pending_daily(daily, intra, cache, now, workers=4):
    """Retry a missing latest completed daily bar once before reconstruction."""
    pending = []
    for symbol, series in daily.items():
        ends = intra.get(symbol, {}).get("sessionEnds", {})
        complete = [day for day,end in ends.items() if end <= now.timestamp()]
        if complete and max(complete) in series.get("pendingDailyDates", []) and max(complete) not in series.get("bars", {}):
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
    parser.add_argument("--snapshot", choices=["close", "intraday"], default="close", help="Publish the canonical close or a separate completed-60m intraday snapshot")
    parser.add_argument("--intraday-auto", action="store_true", help="Skip unchanged/non-session intraday candles and reuse cached completed daily history")
    parser.add_argument("--refresh", action="store_true", help="Ignore cache TTLs")
    parser.add_argument("--workers", type=int, help="Download concurrency, 1–8")
    parser.add_argument("--skip-optional", action="store_true", help="Skip sentiment sources and Binance")
    parser.add_argument("--rankings-only", action="store_true", help="Update equities and sectors; retain dated optional data and homepage")
    args = parser.parse_args()
    if args.intraday_auto and args.snapshot != "intraday":
        parser.error("--intraday-auto requires --snapshot intraday")
    if args.snapshot == "intraday":
        from intraday_snapshot import publish_intraday
        options = {"refresh": args.refresh, "workers": args.workers or 4}
        if args.intraday_auto:
            options["automatic"] = True
        publish_intraday(ROOT, **options)
        return
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
    verified_actions = load_verified(ROOT / "config/verified_dividends.json")
    # A market-wide delayed daily feed used to cause hundreds of redundant
    # retries even when a full, action-free 30m session was already available.
    # Reconstruct eligible observations first; retry only unresolved closes.
    for symbol, series in daily.items():
        known_dates = {item["exDate"] for item in verified_actions.get(symbol, [])}
        series["corporateActionDates"] = sorted(set(series.get("corporateActionDates", [])) | known_dates)
        reconcile_latest_daily(series, intra.get(symbol, {}), now, verified_cash_actions=verified_actions.get(symbol, []))
    errors.extend(retry_pending_daily(daily, intra, cache, now, workers))
    dividend_repairs = []
    for symbol in daily:
        # A missing daily bar on a known ex-date must not be reconstructed from
        # unadjusted intraday prices as if no corporate action happened.
        known_dates = {item["exDate"] for item in verified_actions.get(symbol, [])}
        daily[symbol]["corporateActionDates"] = sorted(set(daily[symbol].get("corporateActionDates", [])) | known_dates)
        reconcile_latest_daily(daily[symbol], intra.get(symbol, {}), now, verified_cash_actions=verified_actions.get(symbol, []))
        dividend_repairs.extend({"symbol":symbol, **item} for item in backfill_verified(daily[symbol], verified_actions.get(symbol, [])))
    published_intraday = None
    intraday_path = ROOT / "data/intraday.json"
    if intraday_path.exists():
        try:
            published_intraday = json.loads(intraday_path.read_text())
        except (OSError, ValueError):
            pass
    require_observed_close(daily[settings["benchmark"]], intra.get(settings["benchmark"], {}),
                           now, published_intraday, settings["benchmark"])
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
        result["sentiment"] = update_sentiment_snapshot(ROOT, previous=prior.get("sentiment"), market_date=result["asOf"])
    else:
        result["sentiment"] = prior.get("sentiment") or {"status":"unavailable","value":None,"reason":"Skipped by configuration"}
    result["contracts"] = prior.get("contracts", {"status":"unavailable","symbols":[]}) if args.rankings_only else fetch_contracts({s["symbol"] for s in universe["stocks"]}) if not args.skip_optional else {"status": "unavailable", "symbols": []}
    result["meta"] = {"schemaVersion": 1, "generatedAt": datetime.now(timezone.utc).isoformat(), "downloadStartedAt": now.isoformat(), "source": "Yahoo Finance public chart / FRED / CNN index via MacroMicro, CNN or public CNN mirror / Binance",
                      "universeDate": universe["capturedAt"], "universeCount": len(universe["stocks"]), "currentCount": valid,
                      "coverage": round(coverage, 4), "intradayCount": sum(r["intra"]["h1"] is not None for r in result["rows"]),
                      "scoreFormula": " + ".join(f"{w} × excess({p[1:]+'H' if p in ('h1','h4') else p+'D'})" for p,w in settings["scoreWeights"].items()),
                      "scoreModel": settings.get("scoreModel", "daily-three-period-v1"), "calibrationReferenceDates":settings.get("calibrationReferenceDates", []),
                      "scoreWeights": settings["scoreWeights"], "longTermWeights": settings["longTermWeights"],
                      "approximation": True, "priceBasis": "Yahoo Adj Close; independently verified cash distributions are backfilled only when the source lacks the ex-date adjustment. Raw quoted prices unchanged. Missing daily closes require a fully observed regular 30m session; prefer the timestamp-verified regular-session quote, otherwise its final 30m close. Only action-free or independently verified normal cash-dividend dates, explicitly flagged. Intraday: Yahoo Close.",
                      "errors": errors, "macroError": macro_error, "macroUpdateStatus":macro_status, "streakWindow": result["rankHistorySessions"],
                      "reconstructedDailyCount":sum(bool(r.get("dailyCloseReconstructed")) for r in result["rows"]),
                      "verifiedDividendBackfills": dividend_repairs,
                      "recoveredRegularQuoteCount":sum(r.get("dailyCloseSource")=="completed-regular-session-quote" for r in result["rows"]),
                      "provisionalDividendCount":sum((r.get("dividendBackfill") or {}).get("sourceStatus")=="provisional" for r in result["rows"]),
                      "benchmarkCloseReconstructed":bool(daily[settings["benchmark"]]["bars"][result["asOf"]].get("reconstructed")),
                      "dailyReconstructionPolicy":"Complete observed regular 30m session required. Prefer a same-session regular quote stamped from the close through +300 seconds and observed at capture. Action-free unit factor, or independently verified cash dividend with unit/known matching factor; non-cash actions excluded. Provisional provenance retained.",
                      "notice": f"Five-period weights inferred from public reference snapshots and rechecked through {max(settings.get('calibrationReferenceDates', ['unknown']))}; not an officially confirmed formula. Prices and runtime rankings are independently calculated from Yahoo. Long-term RS and historical ranks remain independent approximations."}
    # Valuation failures must not prevent publication of independently valid rankings.
    result["meta"]["marketCap"] = refresh_market_caps(result["rows"], prior, cache, args.refresh)
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
