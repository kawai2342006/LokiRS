#!/usr/bin/env python3
"""Report actual observation times and conservatively reuse closes on backup runs."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
HK = ZoneInfo("Asia/Hong_Kong")
# Keep the original 08:17 refresh: it also updates markets closing at UTC midnight.
BACKUP_SCHEDULES = {"11,31 22 * * 1-5"}
SCHEDULE_LABELS = {
    "56 5 * * 2-6": "05:56 HKT，星期二至六，收市主排程",
    "11,31 22 * * 1-5": "06:11／06:31 HKT，星期二至六，收市備用",
    "17 0 * * 2-6": "08:17 HKT，星期二至六，收市備用",
    "40 10-15 * * 1-5": "紐約 10:40 至 15:40，星期一至五，完整 60m 盤中",
}


def read_snapshot(path):
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def can_reuse_close(root, now=None, env=None):
    """Only near-close backups may reuse a validated close for today's NY date.

    This is duplicate-download suppression, not an exchange calendar or a claim
    that the live feed is current. On a holiday, an older date never qualifies.
    Before 16:00 NY (including a very late prior-day trigger), always fetch.
    Reused data is still built/deployed so a failed prior deployment can recover.
    """
    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    if (env.get("LOKIRS_EVENT_NAME") != "schedule"
            or env.get("SNAPSHOT_MODE") != "close"
            or env.get("LOKIRS_SCHEDULE_CRON") not in BACKUP_SCHEDULES):
        return False
    local = now.astimezone(NY)
    data = read_snapshot(root / "data/latest.json")
    if local.hour < 16 or data.get("asOf") != local.date().isoformat():
        return False
    try:
        meta = data["meta"]
        generated = datetime.fromisoformat(meta["generatedAt"])
        if generated.tzinfo is None or generated > now or meta.get("snapshotMode", "close") != "close":
            return False
        settings = json.loads((root / "config/settings.json").read_text())
        universe = json.loads((root / "config/universe.json").read_text())
        if (meta["coverage"] < settings["minimumCoverage"]
                or meta["scoreWeights"] != settings["scoreWeights"]
                or meta["longTermWeights"] != settings["longTermWeights"]
                or data["benchmark"]["symbol"] != settings["benchmark"]
                or {row["symbol"] for row in data["rows"]} != {row["symbol"] for row in universe["stocks"]}):
            return False
        from validate_snapshot import validate
        validate(data)
    except (AssertionError, KeyError, TypeError, ValueError, OSError, OverflowError):
        return False
    return True


def hkt(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is not None:
            return parsed.astimezone(HK).strftime("%Y-%m-%d %H:%M:%S HKT")
    except (TypeError, ValueError):
        pass
    return "—"


def summarize(root, before=False, now=None, env=None):
    env = os.environ if env is None else env
    now = now or datetime.now(timezone.utc)
    cron = env.get("LOKIRS_SCHEDULE_CRON", "")
    data = read_snapshot(root / "data/latest.json")
    meta = data.get("meta", {})
    lines = ["## LokiRS · " + ("資料處理前" if before else "資料處理後"), "",
             f"- 事件：{env.get('LOKIRS_EVENT_NAME', 'local')}；模式：{env.get('SNAPSHOT_MODE', 'close')}",
             f"- 觸發 cron：`{cron or '非排程'}`；{SCHEDULE_LABELS.get(cron, '手動／程式碼上傳')}",
             f"- 本步驟記錄時間：{hkt(now.isoformat())}；UTC {now.astimezone(timezone.utc).isoformat()}；紐約 {now.astimezone(NY).isoformat()}",
             "", "| 快照 | 行情日期 asOf | K 線完成時間 HKT | 開始抓取 HKT | 產生時間 HKT | 有效股票 |",
             "|---|---|---|---|---|---|"]
    for label, filename in [("收市 latest.json", "latest.json"), ("盤中 intraday.json", "intraday.json")]:
        snapshot = data if filename == "latest.json" else read_snapshot(root / "data" / filename)
        detail = snapshot.get("meta", {})
        count = f"{detail.get('currentCount', '—')} / {detail.get('universeCount', '—')}"
        lines.append(f"| {label} | {snapshot.get('asOf', '—')} | {hkt(detail.get('snapshotAt'))} | {hkt(detail.get('downloadStartedAt'))} | {hkt(detail.get('generatedAt'))} | {count} |")
    lines += ["", f"- 收市行情請求錯誤：{len(meta.get('errors', []))}"]
    home_path = root / "data/home.json"
    if home_path.exists():
        home = read_snapshot(home_path)
        lines.append(f"- 首頁股票行情日期：{home.get('stockAsOf', '—')}")
        if home.get("stockAsOf") != data.get("asOf"):
            lines.append("- 首頁與收市股票日期不同；請檢查獨立的首頁更新。")
    if meta.get("macroUpdateStatus") != "updated":
        lines.append("- 宏觀資料保留自己的觀測日期，與股票收市日期分開。")
    lines += ["", "上述為本次工作目錄內的資料；是否成功發布另看 deploy job。",
              "Actions 成功、產生時間改變或盤中更新，都不代表收市行情日期已前進。",
              "05:56 是預定開始時間；GitHub 觸發延誤、下載及部署另需時間，不能保證 06:00 完成。"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    now = datetime.now(timezone.utc)
    reuse = can_reuse_close(root, now) if args.before else False
    if args.before and os.environ.get("GITHUB_OUTPUT"):
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(f"reuse_close={str(reuse).lower()}\n")
    report = summarize(root, args.before, now)
    if args.before:
        report += ("\n備用重試：已有經驗證的本紐約日期收市檔，沿用資料並重新部署；本次不重新抓價。\n"
                   if reuse else "\n本次未符合備用資料重用條件；按原本所選模式及 refresh_data 選項執行。\n")
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as output:
            output.write(report)
