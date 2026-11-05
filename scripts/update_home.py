#!/usr/bin/env python3
"""Refresh LokiRS homepage data from free public sources without altering equity calculations."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
from datetime import datetime, timezone
from pathlib import Path

from home_engine import build_cross_markets, build_pulse, parse_market_daily, vix_summary
from home_providers import fetch_southbound, optional, parse_articles, parse_crypto_global, parse_stablecoins, public_payload
from providers import cached_chart, parse_chart, reconcile_latest_daily

ROOT = Path(__file__).resolve().parents[1]


def refresh_home(root=ROOT, equities=None, workers=4, refresh=False, daily_overrides=None):
    root = Path(root)
    config = json.loads((root/"config/home_markets.json").read_text())
    output = root/"data/home.json"
    prior = json.loads(output.read_text()) if output.exists() else {}
    equities = equities if equities is not None else json.loads((root/"data/latest.json").read_text())
    cache = root/".cache/openrs"
    now = datetime.now(timezone.utc)
    daily, errors = {}, []
    tasks = config["markets"] + [{"symbol":"VIX", "providerSymbol":"^VIX", "session":"exchange"}]
    def get(market):
        try:
            symbol = market["providerSymbol"]
            if daily_overrides and symbol in daily_overrides and market["session"] == "exchange":
                return market["symbol"], daily_overrides[symbol], None
            payload,_ = cached_chart(market["providerSymbol"], "1d", cache, refresh)
            zone = payload["chart"]["result"][0]["meta"].get("exchangeTimezoneName")
            us_exchange = market["session"] == "exchange" and zone in ("America/New_York", "US/Eastern")
            def parse(raw):
                return parse_chart(raw, "1d", now) if us_exchange else parse_market_daily(raw, market["session"], now)
            parsed = parse(payload)
            warning = None
            latest_source = max(parsed.get("dailySourceDates", []), default="")
            if latest_source and latest_source in parsed.get("pendingDailyDates", []):
                try:
                    native,_ = cached_chart(symbol, "1d", cache, True)
                    retry = parse(native)
                    if max(retry["bars"], default="") < max(parsed["bars"], default=""):
                        raise ValueError("Retry returned an older observation")
                    parsed = retry
                except Exception as exc:
                    warning = "Latest daily retry failed; retained dated source: " + str(exc)[:130]
            if us_exchange:
                if parsed.get("pendingDailyDates"):
                    hourly,_ = cached_chart(symbol, "30m", cache, refresh)
                    reconcile_latest_daily(parsed, parse_chart(hourly, "30m", now), now)
            return market["symbol"], parsed, warning
        except Exception as exc:
            return market["symbol"], None, str(exc)[:180]
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(8,workers))) as pool:
        for symbol,series,error in pool.map(get,tasks):
            if series is not None:
                daily[symbol] = series
            if error:
                errors.append({"symbol":symbol,"error":error})
    result = build_cross_markets(config,daily)
    if prior.get("asOf") and result["asOf"] < prior["asOf"]:
        raise ValueError("Homepage source date regressed; existing snapshot preserved")
    market_by_symbol = {m["symbol"]:m for m in config["markets"]}
    result["tiles"] = []
    for symbol in ["SPY","QQQ","BTC","UUP","GLD","USO"]:
        series = daily.get(symbol,{}); bars = series.get("bars",{}); dates = sorted(bars)
        latest = dates[-1] if dates else None
        returns = {}
        for period in [1,5]:
            returns[str(period)] = (bars[latest]["close"]/bars[dates[-1-period]]["close"]-1)*100 if len(dates)>period else None
        result["tiles"].append({"symbol":symbol,"name":market_by_symbol[symbol]["name"],"asOf":latest,
            "dailyCloseReconstructed":bool(bars.get(latest,{}).get("reconstructed")),
            "price":bars.get(latest,{}).get("price"),"currency":series.get("currency"),"returns":returns,
            "history":[bars[date]["close"] for date in dates[-21:]],"session":market_by_symbol[symbol]["session"]})
    result["stockAsOf"] = equities.get("asOf")
    result["breadth"] = equities.get("breadth", [])[-2:]
    result["pulse"] = build_pulse(equities)
    result["vix"] = vix_summary(daily.get("VIX",{}),result["asOf"])
    # All optional providers retain the original observation time when an update fails.
    jobs = {
        "crypto":lambda:parse_crypto_global(public_payload(cache,"home-coingecko.raw","https://api.coingecko.com/api/v3/global")),
        "stablecoins":lambda:parse_stablecoins(public_payload(cache,"home-stablecoins.raw","https://stablecoins.llama.fi/stablecoincharts/all")),
        "southbound":lambda:fetch_southbound(cache,result["asOf"]),
        "articles":lambda:parse_articles(public_payload(cache,"home-articles.raw","https://lazybeanz.substack.com/feed")),
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for key,value in zip(jobs,pool.map(lambda key:optional(prior,key,jobs[key]),jobs)):
            result[key] = value
    result["meta"] = {
        "schemaVersion":1, "generatedAt":datetime.now(timezone.utc).isoformat(),
        "universeCount":len(config["markets"]), "currentCount":sum(r["rank"] is not None for r in result["rows"]),
        "scoreWeights":config["scoreWeights"], "approximation":True, "source":"Yahoo Finance / CoinGecko / DefiLlama / HKEX / publisher RSS",
        "errors":errors, "calendar":"SPY completed trading sessions; exact dates without forward fill",
        "priceBasis":"Adjusted daily close for returns; unit-factor/no-action missing latest US closes may be reconstructed from complete regular-session 30m observations, explicitly flagged. Native currency; no FX conversion.",
        "stockGeneratedAt":equities.get("meta",{}).get("generatedAt"),
        "reconstructedDailyCount":sum(bool(r.get("dailyCloseReconstructed")) for r in result["rows"]),
        "notice":"Independent open formula; original LazyRS score weights and home-pulse selection are not verified. No original-site numerical feed is used.",
    }
    validate_home(result)
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n")
    temporary.replace(output)
    print(f"Saved home.json: {result['meta']['currentCount']}/{len(config['markets'])} markets; {result['asOf']}; optional "+", ".join(k+"="+result[k]["status"] for k in jobs),flush=True)
    return result


def validate_home(data):
    from home_engine import finite
    assert data["meta"]["schemaVersion"]==1
    rows = data["rows"]
    assert len({r["symbol"] for r in rows})==len(rows)==data["meta"]["universeCount"]
    valid = [r for r in rows if r["rank"] is not None]
    assert sorted(r["rank"] for r in valid)==list(range(1,len(valid)+1))
    assert data["meta"]["currentCount"]==len(valid)
    for row in valid:
        assert row["asOf"]==data["asOf"] and row["status"]=="ok"
        for period in ("1","5","20"):
            assert finite(row["absolute"][period]) and finite(row["excess"][period])
            assert abs(row["absolute"][period]-data["medians"][period]-row["excess"][period])<1e-8
        expected = sum(row["excess"][p]*w for p,w in data["meta"]["scoreWeights"].items())
        assert abs(expected-row["score"])<1e-8
    return True


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh",action="store_true")
    parser.add_argument("--workers",type=int,default=4)
    args=parser.parse_args()
    refresh_home(workers=args.workers,refresh=args.refresh)
