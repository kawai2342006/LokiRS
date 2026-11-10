#!/usr/bin/env python3
"""Add 3D/fortnight columns to an existing snapshot without fetching or reranking.

The embedded history contains adjusted closes rounded to four decimals. New
columns use those stored prices; a normal update uses full provider precision.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine import additional_excess_periods

ROOT = Path(__file__).resolve().parents[1]


def add_columns(snapshot):
    end = snapshot["asOf"]
    benchmark = {}
    for row in snapshot["rows"]:
        for point in row["history"]:
            day = point["date"]
            if day > end:
                continue
            value = point["benchmark"]
            if day in benchmark and benchmark[day]["close"] != value:
                raise ValueError(f"Conflicting benchmark closes on {day}")
            benchmark[day] = {"close": value}
    if end not in benchmark:
        raise ValueError("Snapshot has no benchmark close for its observation date")
    sessions = sorted(benchmark)
    for row in snapshot["rows"]:
        asset = {p["date"]: {"close": p["close"]} for p in row["history"] if p["date"] <= end}
        row.update(additional_excess_periods(asset, benchmark, sessions, end))
    return snapshot


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "data/latest.json")
    args = parser.parse_args()
    snapshot = add_columns(json.loads(args.snapshot.read_text()))
    from validate_snapshot import validate
    validate(snapshot)
    temp = args.snapshot.with_suffix(".tmp")
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    temp.replace(args.snapshot)
    print(f"Added return columns: {len(snapshot['rows'])} stocks; market date {snapshot['asOf']}")


if __name__ == "__main__":
    run()
