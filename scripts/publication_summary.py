#!/usr/bin/env python3
"""Expose observation dates in Actions without treating a successful run as fresh prices."""
import json
import os
from pathlib import Path


def summarize(root):
    data = json.loads((root / "data/latest.json").read_text())
    meta = data["meta"]
    lines = ["## LokiRS publication", "",
             f"- US stock session: **{data['asOf']}**",
             f"- Snapshot generated (UTC): {meta['generatedAt']}",
             f"- Ranked stocks: {meta['currentCount']} / {meta['universeCount']}",
             f"- Failed market requests: {len(meta.get('errors', []))}"]
    home_path = root / "data/home.json"
    if home_path.exists():
        home = json.loads(home_path.read_text())
        lines.append(f"- Homepage stock session: {home.get('stockAsOf', 'unknown')}")
        if home.get("stockAsOf") != data["asOf"]:
            lines.append("- **Homepage has an older stock observation; check the optional homepage update.**")
    if meta.get("macroUpdateStatus") != "updated":
        lines.append("- Macro observations retained their own dates; the stock session above is independent.")
    lines += ["", "Page reload and 60-second checks read this deployed snapshot.",
              "To download prices again, run this workflow with refresh_data enabled."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    report = summarize(Path(__file__).resolve().parents[1])
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as output:
            output.write(report)
