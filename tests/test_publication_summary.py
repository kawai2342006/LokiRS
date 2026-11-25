import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from publication_summary import HOME_BACKUP, can_reuse_close


class ScheduledCloseTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        (self.root / "config").mkdir()
        (self.root / "data").mkdir()
        self.snapshot = {
            "asOf": "2026-11-23",
            "benchmark": {"symbol": "SPY"},
            "rows": [{"symbol": "A"}],
            "meta": {
                "generatedAt": "2026-11-23T21:58:00+00:00",
                "coverage": 1,
                "scoreWeights": {"1": 1},
                "longTermWeights": {"20": 1},
                "benchmarkCloseReconstructed": False,
                "reconstructedDailyCount": 0,
                "errors": [],
            },
        }
        (self.root / "config/settings.json").write_text(json.dumps({
            "benchmark": "SPY", "minimumCoverage": 0.8,
            "scoreWeights": {"1": 1}, "longTermWeights": {"20": 1},
        }))
        (self.root / "config/universe.json").write_text(json.dumps({"stocks": [{"symbol": "A"}]}))
        validator = patch("validate_snapshot.validate")
        self.validate = validator.start()
        self.addCleanup(validator.stop)

    def reuse(self, stamp, cron=HOME_BACKUP, event="schedule"):
        (self.root / "data/latest.json").write_text(json.dumps(self.snapshot))
        env = {"LOKIRS_EVENT_NAME": event, "SNAPSHOT_MODE": "close", "LOKIRS_SCHEDULE_CRON": cron}
        return can_reuse_close(self.root, datetime.fromisoformat(stamp), env)

    def test_each_scheduled_close_can_reuse_after_new_york_midnight(self):
        for cron in ("56 5 * * 2-6", "11,31 22 * * 1-5", HOME_BACKUP):
            with self.subTest(cron=cron):
                self.assertTrue(self.reuse("2026-11-24T18:02:00+08:00", cron))
        self.assertEqual(self.validate.call_count, 3)

    def test_uses_hong_kong_session_date_in_daylight_saving_time(self):
        self.snapshot["asOf"] = "2026-07-06"
        self.snapshot["meta"]["generatedAt"] = "2026-07-06T21:58:00+00:00"
        self.assertTrue(self.reuse("2026-07-07T08:17:00+08:00"))

    def test_stale_early_and_manual_runs_fetch(self):
        self.assertFalse(self.reuse("2026-11-25T18:02:00+08:00"))
        self.assertFalse(self.reuse("2026-11-24T08:16:59+08:00"))
        self.assertFalse(self.reuse("2026-11-24T18:02:00+08:00", event="workflow_dispatch"))
        self.validate.assert_not_called()

    def test_later_backup_retries_provisional_or_failed_price_downloads(self):
        for key, value in (("benchmarkCloseReconstructed", True), ("reconstructedDailyCount", 1),
                           ("errors", [{"symbol": "A", "interval": "1d"}])):
            with self.subTest(field=key):
                with patch.dict(self.snapshot["meta"], {key: value}):
                    self.assertFalse(self.reuse("2026-11-24T18:02:00+08:00"))
                    self.assertTrue(self.reuse("2026-11-24T18:02:00+08:00", "11,31 22 * * 1-5"))

    def test_invalid_snapshot_still_needs_fetching(self):
        self.validate.side_effect = AssertionError("invalid snapshot")
        self.assertFalse(self.reuse("2026-11-24T18:02:00+08:00"))


if __name__ == "__main__":
    unittest.main()
