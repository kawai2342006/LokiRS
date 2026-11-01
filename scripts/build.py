#!/usr/bin/env python3
"""Package only public static files. No framework, dependencies or API secrets."""
import json
import shutil
from pathlib import Path
from validate_snapshot import validate

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"
data = json.loads((ROOT / "data/latest.json").read_text())
validate(data)
assert data["meta"]["schemaVersion"] == 1 and len(data["rows"]) > 0, "Missing or invalid market snapshot"
assert data["asOf"] == data["benchmark"]["asOf"], "Benchmark date does not match snapshot"
OUT.mkdir(exist_ok=True)
for filename in ["index.html", ".nojekyll"]:
    shutil.copy2(ROOT / filename, OUT / filename)
for directory in ["assets", "data"]:
    shutil.copytree(ROOT / directory, OUT / directory, dirs_exist_ok=True)
print(f"Built {OUT}: {len(data['rows'])} stocks; {data['asOf']}")
