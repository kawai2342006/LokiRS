#!/usr/bin/env python3
"""Package only public static files. No framework, dependencies or API secrets."""
import json
import shutil
from pathlib import Path
from validate_snapshot import validate
from update_home import validate_home

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_site"
data = json.loads((ROOT / "data/latest.json").read_text())
validate(data)
assert data["meta"]["schemaVersion"] == 1 and len(data["rows"]) > 0, "Missing or invalid market snapshot"
assert data["asOf"] == data["benchmark"]["asOf"], "Benchmark date does not match snapshot"
home = json.loads((ROOT / "data/home.json").read_text())
validate_home(home)
OUT.mkdir(exist_ok=True)
for filename in ["index.html"]:
    shutil.copy2(ROOT / filename, OUT / filename)
(OUT / ".nojekyll").touch()
for directory in ["assets", "data"]:
    shutil.copytree(ROOT / directory, OUT / directory, dirs_exist_ok=True)
print(f"Built {OUT}: {len(data['rows'])} stocks; {home['meta']['currentCount']}/{home['meta']['universeCount']} cross-markets; {home['asOf']}")
