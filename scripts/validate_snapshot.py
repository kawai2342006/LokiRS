"""Check a published snapshot's internal dates, coverage and cross-series consistency."""
import math
from datetime import datetime
from pathlib import Path
import json
from zoneinfo import ZoneInfo


def validate(data):
    meta, rows = data["meta"], data["rows"]
    assert meta["schemaVersion"] == 1 and meta["approximation"] is True
    assert len({r["symbol"] for r in rows}) == len(rows) == meta["universeCount"]
    assert data["asOf"] == data["benchmark"]["asOf"]
    assert data["benchmark"]["price"] > 0
    ranked = sorted((r for r in rows if r["rank"] is not None), key=lambda r: r["rank"])
    assert [r["rank"] for r in ranked] == list(range(1, len(ranked) + 1))
    assert all(a["score"] >= b["score"] - 0.0001 for a, b in zip(ranked, ranked[1:]))
    assert len(ranked) == meta["currentCount"]
    assert abs(meta["coverage"] - len(ranked) / len(rows)) < 0.0001
    calibrated = meta.get("scoreModel") == "five-period-public-calibration-v1"
    if calibrated:
        assert 0 < meta["streakWindow"] <= 65
        assert set(meta["scoreWeights"]) == {"h1", "h4", "1", "5", "20"}
    benchmark_prices = {}
    for row in rows:
        if row["rank"] is not None:
            assert row["asOf"] == data["asOf"] and row["status"] == "ok", (row["symbol"], "ranked observation date/status", row["asOf"], data["asOf"], row["status"])
            if calibrated:
                parts = row["scoreInputs"]
                assert all(v is not None and math.isfinite(v) for v in parts.values())
                expected = sum(parts[k]*w for k,w in meta["scoreWeights"].items())
                assert abs(expected-row["score"]) <= .000051, (row["symbol"], "score components")
                assert datetime.fromisoformat(row["intra"]["asOf"]).astimezone(ZoneInfo("America/New_York")).date().isoformat() == data["asOf"]
                assert parts["h1"] == row["intra"]["h1"] and parts["h4"] == row["intra"]["h4"]
                if row.get("dailyCloseReconstructed"):
                    assert datetime.fromisoformat(row["dailyCloseSourceTime"]).astimezone(ZoneInfo("America/New_York")).date().isoformat() == data["asOf"]
                    assert row["dailyCloseSourceTime"] == row["intra"]["asOf"]
        for field in ["price", "score", "d1", "longRS", "vsSector", "vsSectorDay"]:
            assert row[field] is None or math.isfinite(row[field]), (row["symbol"], field)
        if row["longRS"] is not None:
            assert 0 <= row["longRS"] <= 100
        dates = [point["date"] for point in row["history"]]
        assert dates == sorted(set(dates))
        for point in row["history"]:
            assert point["close"] > 0 and point["benchmark"] > 0
            assert point["date"] <= data["asOf"]
            if point["date"] in benchmark_prices:
                assert abs(benchmark_prices[point["date"]] - point["benchmark"]) < 0.0002
            benchmark_prices[point["date"]] = point["benchmark"]
        if row["rsLine"]:
            assert len(row["rsLine"]) <= 21 and abs(row["rsLine"][0] - 100) < 0.0001
        for period in ["week", "month"]:
            value = row[period]
            if value["value"] is not None:
                assert value["from"] <= value["target"] <= value["to"] == data["asOf"]
        intra = row["intra"]
        for n in [1, 4]:
            if intra[f"h{n}"] is not None:
                assert intra["asOf"] and intra.get(f"h{n}Start")
                duration = (datetime.fromisoformat(intra["asOf"]) - datetime.fromisoformat(intra[f"h{n}Start"])).total_seconds() / 3600
                assert abs(duration - intra[f"h{n}ElapsedHours"]) < 0.00001
    assert len({row["id"] for row in data["macro"]}) == len(data["macro"])
    if "reconstructedDailyCount" in meta:
        assert meta["reconstructedDailyCount"] == sum(bool(r.get("dailyCloseReconstructed")) for r in rows)
    if "verifiedDividendBackfills" in meta:
        for event in meta["verifiedDividendBackfills"]:
            assert event["exDate"] <= data["asOf"] and event["amountUSD"] > 0
            assert event["source"].startswith("https://")
    for item in data["macro"]:
        if item.get("asOf"):
            assert item["asOf"] <= meta["generatedAt"][:10]
    print(f"Snapshot verified: {len(rows)} unique stocks, {len(ranked)} ranked, dates/coverage/benchmark/RS consistent")


if __name__ == "__main__":
    validate(json.loads((Path(__file__).resolve().parents[1] / "data/latest.json").read_text()))
