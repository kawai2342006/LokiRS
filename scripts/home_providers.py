"""Public source adapters for homepage context; no credentials or original-site market feed."""
from __future__ import annotations

import json
import math
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

HEADERS = {"User-Agent":"LokiRS/1.2 (public market research dashboard)"}


def public_payload(cache, name, url, ttl=21600):
    path = Path(cache)/name
    if path.exists() and time.time()-path.stat().st_mtime < ttl:
        return path.read_bytes()
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=25) as response:
        raw = response.read()
    Path(cache).mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)
    return raw


def parse_crypto_global(raw):
    data = json.loads(raw)["data"]
    total = float(data["total_market_cap"]["usd"])
    dominance = float(data["market_cap_percentage"]["btc"])
    change = float(data["market_cap_change_percentage_24h_usd"])
    if not all(math.isfinite(v) for v in [total, dominance, change]) or total <= 0 or not 0<=dominance<=100:
        raise ValueError("Invalid CoinGecko global market data")
    return {"status":"ok", "value":total, "btcDominance":dominance, "change24h":change,
            "asOf":datetime.fromtimestamp(int(data["updated_at"]),timezone.utc).isoformat(),
            "source":"CoinGecko", "url":"https://www.coingecko.com/en/global-charts"}


def parse_stablecoins(raw):
    records = json.loads(raw)
    values = []
    for row in records:
        value = row.get("totalCirculatingUSD", {}).get("peggedUSD")
        if isinstance(value,(int,float)) and math.isfinite(value) and value>0:
            values.append((int(row["date"]),float(value)))
    values.sort()
    if not values:
        raise ValueError("No USD-pegged stablecoin observations")
    stamp, current = values[-1]
    def delta(days):
        target = stamp-days*86400
        prior = [(d,v) for d,v in values if 0<=target-d<=3*86400]
        return current-prior[-1][1] if prior else None
    return {"status":"ok", "value":current, "change7d":delta(7), "change30d":delta(30),
            "asOf":datetime.fromtimestamp(stamp,timezone.utc).isoformat(), "scope":"USD-pegged stablecoins; totalCirculatingUSD.peggedUSD",
            "history":[{"date":datetime.fromtimestamp(d,timezone.utc).date().isoformat(),"value":v} for d,v in values[-90:]],
            "source":"DefiLlama", "url":"https://defillama.com/stablecoins"}


def parse_southbound(raw, expected_date):
    text = raw.decode("utf-8-sig").strip()
    # HKEX publishes a JSON array assigned to tabData, not executable code for our updater.
    if not text.startswith("tabData") or "=" not in text:
        raise ValueError("Invalid HKEX daily statistics wrapper")
    data = json.loads(text.split("=",1)[1].strip().rstrip(";"))
    parts = {}
    for record in data:
        market = record.get("market", "")
        if market not in ("SSE Southbound", "SZSE Southbound"):
            continue
        if record.get("date") != expected_date:
            raise ValueError("HKEX observation date mismatch")
        if record.get("tradingDay") != 1:
            return None
        table = next((c["table"] for c in record.get("content", []) if c.get("table", {}).get("classname")=="tradingTable"), None)
        if not table:
            raise ValueError("HKEX southbound turnover table missing")
        labels = table["schema"][0]
        rows = table["tr"]
        def amount(label):
            index = labels.index(label)
            return float(str(rows[index]["td"][0][0]).replace(",", ""))*1_000_000
        buy, sell = amount("Buy Turnover"), amount("Sell Turnover")
        if not all(math.isfinite(v) and v >= 0 for v in (buy,sell)):
            raise ValueError("Invalid HKEX turnover amount")
        parts[market] = {"buy":buy, "sell":sell, "net":buy-sell}
    if len(parts)!=2:
        raise ValueError("Both southbound routes are required")
    return {"date":expected_date, "net":sum(v["net"] for v in parts.values()), "parts":parts}


def fetch_southbound(cache, as_of):
    from concurrent.futures import ThreadPoolExecutor
    end = datetime.fromisoformat(as_of).date()
    dates = [(end-timedelta(days=i)).isoformat() for i in range(16) if (end-timedelta(days=i)).weekday()<5][:10]
    def get(day):
        url = "https://www.hkex.com.hk/eng/csm/DailyStat/data_tab_daily_"+day.replace("-", "")+"e.js"
        try:
            return parse_southbound(public_payload(cache,"home-southbound-"+day.replace("-", "")+".raw",url,21600),day)
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = sorted((r for r in pool.map(get, dates) if r is not None),key=lambda r:r["date"])
    if not records:
        raise ValueError("No complete HKEX southbound observations")
    recent = records[-5:]
    return {"status":"ok" if recent[-1]["date"]==as_of and len(recent)==5 else "stale",
            "asOf":recent[-1]["date"], "value":recent[-1]["net"], "sum5d":sum(r["net"] for r in recent) if len(recent)==5 else None,
            "sessionCount":len(recent), "history":recent, "source":"HKEX", "unit":"HKD",
            "url":"https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics/Historical-Daily?sc_lang=en"}


def parse_articles(raw):
    root = ET.fromstring(raw)
    if root.tag not in ("rss", "feed", "{http://www.w3.org/2005/Atom}feed"):
        raise ValueError("Publisher did not return an RSS feed")
    items = []
    for item in root.findall("./channel/item"):
        title, link, published = item.findtext("title"), item.findtext("link"), item.findtext("pubDate")
        parsed = urlparse(link or "")
        if not title or parsed.scheme!="https" or parsed.hostname!="lazybeanz.substack.com":
            continue
        try:
            date = parsedate_to_datetime(published).date().isoformat()
        except Exception:
            continue
        items.append({"title":title.strip(),"url":link,"date":date})
    if not items:
        raise ValueError("No valid article metadata in publisher feed")
    items.sort(key=lambda i:i["date"],reverse=True)
    return {"status":"ok", "items":items[:6], "asOf":datetime.now(timezone.utc).isoformat(),
            "source":"Lazybeanz / Substack", "url":"https://lazybeanz.substack.com/archive"}


def optional(prior, key, load):
    try:
        return load()
    except Exception as exc:
        old = prior.get(key, {})
        return {**old,"status":"stale" if old.get("value") is not None or old.get("items") else "unavailable",
                "error":str(exc)[:180]}
