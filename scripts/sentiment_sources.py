"""CNN's US-stock Fear & Greed index from public MacroMicro HTML, then CNN.

Reads only data embedded in the provided public page. No login, chart-data API,
subscription download, proxy, or browser fingerprint spoofing is used.
"""
from __future__ import annotations

import calendar
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

INDEX_ID = "cnn-us-fear-greed"
MACROMICRO_URL = "https://en.macromicro.me/charts/50108/cnn-fear-and-greed"
CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
MAX_AGE_DAYS = 7


def score(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not an index value")
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError("Fear & Greed score must be between 0 and 100")
    return value


def observed_day(value, now):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("A source observation date is required")
    day = date.fromisoformat(value)
    if day > now.astimezone(timezone.utc).date():
        raise ValueError("Source observation date is in the future")
    return day.isoformat()


def rating(value):
    return "extreme fear" if value <= 25 else "fear" if value < 45 else "neutral" if value <= 55 else "greed" if value <= 75 else "extreme greed"


def previous_month(day):
    year, month = (day.year-1, 12) if day.month == 1 else (day.year, day.month-1)
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def parse_macromicro(payload, now=None, previous=None):
    now = now or datetime.now(timezone.utc)
    text = payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload
    match = re.search(r"\b(?:let|const|var)\s+chart\s*=\s*(\{)", text)
    if not match:
        raise ValueError("MacroMicro public chart metadata missing")
    chart, _ = json.JSONDecoder().raw_decode(text, match.start(1))
    if chart.get("id") != 50108 or chart.get("is_membersonly") not in (0, False, None, "0"):
        raise ValueError("Not the expected public CNN chart")
    configs = chart.get("settings", {}).get("seriesConfigs", [])
    indices = [i for i, config in enumerate(configs) if any(
        str(stat.get("stat_id")) == "22748" and "CNN" in str(stat.get("name_en", "")).upper()
        for stat in config.get("stats", []))]
    if len(indices) != 1:
        raise ValueError("CNN series identity not found; other sentiment indices are not substitutes")
    rows = chart.get("series_last_rows")
    rows = json.loads(rows) if isinstance(rows, str) else rows
    points = {}
    if isinstance(previous, dict) and previous.get("indexId") == INDEX_ID and previous.get("source") == "MacroMicro":
        for point in previous.get("history", []):
            if isinstance(point, dict) and point.get("provider") == "MacroMicro":
                try:
                    points[observed_day(point["date"], now)] = score(point["value"])
                except (KeyError, TypeError, ValueError):
                    continue
    current = {}
    for item in rows[indices[0]]:
        if not isinstance(item, list) or len(item) < 2:
            raise ValueError("Malformed public CNN observation")
        current[observed_day(item[0], now)] = score(item[1])
    if not current:
        raise ValueError("No public CNN observations")
    # Retained history must not invent a newer current value than this source page actually serves.
    latest = max(current)
    points = {d:v for d,v in points.items() if d <= latest}
    points.update(current)
    days = sorted(points)
    earlier = [d for d in days if d < latest]
    def historical(target):
        eligible = [d for d in days if 0 <= (target-date.fromisoformat(d)).days <= 3]
        return (points[eligible[-1]], eligible[-1]) if eligible else (None, None)
    week, week_day = historical(date.fromisoformat(latest)-timedelta(days=7))
    month, month_day = historical(previous_month(date.fromisoformat(latest)))
    value = points[latest]
    return {"schemaVersion":1, "indexId":INDEX_ID, "status":"ok", "source":"MacroMicro", "upstream":"CNN",
            "url":MACROMICRO_URL, "value":value, "rating":rating(value), "asOf":latest,
            "observationDate":latest, "asOfPrecision":"date", "previousLabel":"上一筆",
            "previousClose":points[earlier[-1]] if earlier else None, "previousAsOf":earlier[-1] if earlier else None,
            "weekAgo":week, "weekAgoAsOf":week_day, "monthAgo":month, "monthAgoAsOf":month_day, "yearAgo":None,
            "history":[{"date":d,"value":points[d],"provider":"MacroMicro"} for d in days[-400:]],
            "historyNote":"Public latest observations plus previously retained observations from the same provider; missing dates are not synthesized."}


def parse_cnn(payload, now=None):
    now = now or datetime.now(timezone.utc)
    data = json.loads(payload)
    fg = data["fear_and_greed"]
    value = score(fg["score"])
    raw_time = fg.get("timestamp")
    if not isinstance(raw_time, str):
        raise ValueError("CNN observation timestamp missing")
    instant = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    if instant.tzinfo is None or instant > now + timedelta(minutes=5):
        raise ValueError("Invalid CNN observation timestamp")
    day = observed_day(instant.astimezone(ZoneInfo("America/New_York")).date().isoformat(), now)
    def optional(field):
        value = fg.get(field)
        return score(value) if value is not None else None
    return {"schemaVersion":1, "indexId":INDEX_ID, "status":"ok", "source":"CNN", "upstream":"CNN",
            "url":"https://www.cnn.com/markets/fear-and-greed", "value":value, "rating":fg.get("rating") or rating(value),
            "asOf":instant.isoformat(), "observationDate":day, "asOfPrecision":"timestamp", "previousLabel":"前收",
            "previousClose":optional("previous_close"), "weekAgo":optional("previous_1_week"),
            "monthAgo":optional("previous_1_month"), "yearAgo":optional("previous_1_year")}


def valid_previous(previous, now):
    if not isinstance(previous, dict) or previous.get("source") not in ("MacroMicro", "CNN"):
        return None
    if previous.get("indexId", INDEX_ID) != INDEX_ID or previous.get("status") not in ("ok", "stale"):
        return None
    try:
        score(previous["value"])
        day = previous.get("observationDate")
        if not day and previous.get("asOf"):
            stamp = previous["asOf"]
            day = stamp if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp) else datetime.fromisoformat(stamp.replace("Z","+00:00")).astimezone(ZoneInfo("America/New_York")).date().isoformat()
        observed_day(day, now)
        return {**previous,"indexId":INDEX_ID,"schemaVersion":1,"observationDate":day}
    except (TypeError, ValueError, KeyError):
        return None


def fetch_index(loader, previous=None, now=None):
    now = now or datetime.now(timezone.utc)
    prior = valid_previous(previous, now)
    candidates, errors = [], []
    for source, url in [("MacroMicro", MACROMICRO_URL), ("CNN", CNN_URL)]:
        try:
            raw = loader(url)
            result = parse_macromicro(raw, now, prior) if source == "MacroMicro" else parse_cnn(raw, now)
            if prior and result["observationDate"] < prior["observationDate"]:
                errors.append({"source":source,"error":"Source observation predates retained snapshot"})
                continue
            age = (now.date()-date.fromisoformat(result["observationDate"])).days
            result["status"] = "stale" if age > MAX_AGE_DAYS else "ok"
            result["fetchedAt"] = now.isoformat()
            result["attempts"] = list(errors)
            if result["status"] == "ok":
                return result
            candidates.append(result)
        except Exception as exc:
            errors.append({"source":source,"error":str(exc)[:180]})
    if prior:
        candidates.append(prior)
    if candidates:
        result = dict(max(candidates, key=lambda r:r["observationDate"]))
        # Observation date and value stay intact when all fresh sources fail.
        result.update({"status":"stale","lastCheckedAt":now.isoformat(),"attempts":errors})
        return result
    return {"schemaVersion":1,"indexId":INDEX_ID,"status":"unavailable","source":None,"upstream":"CNN",
            "value":None,"asOf":None,"observationDate":None,"attempts":errors,"lastCheckedAt":now.isoformat(),"url":MACROMICRO_URL}
