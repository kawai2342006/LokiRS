import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from market_caps import parse_cap, parse_screener, attach_market_caps, refresh_market_caps, fetch_market_caps


class MarketCapTests(unittest.TestCase):
    def fixture(self):
        return {"status": {"rCode": 200}, "data": {"asOf": None, "rows": [
            {"symbol": "BRK/B", "marketCap": "1,234,567,890,123.00"},
            {"symbol": "A", "marketCap": "1200000.00"},
            {"symbol": "ZERO", "marketCap": "0.00"},
            {"symbol": "MISSING", "marketCap": ""}]}}

    def test_values_and_units(self):
        for value in (None, "", "N/A", "--", "0.00", 0, -1, True, math.nan, math.inf):
            self.assertIsNone(parse_cap(value))
        self.assertEqual(parse_cap("$1,250.5M"), 1250500000)
        self.assertEqual(parse_cap("2B"), 2e9)
        self.assertEqual(parse_cap(1e17), 1e17)

    def test_class_symbol_mapping_and_independent_date(self):
        records = parse_screener(self.fixture(), "2026-11-10T08:00:00+00:00")
        self.assertEqual(set(records), {"BRK-B", "A"})
        self.assertIsNone(records["A"]["marketCapAsOf"])
        self.assertEqual(records["BRK-B"]["marketCapCurrency"], "USD")
        rows = [{"symbol": "BRK-B"}, {"symbol": "A"}, {"symbol": "MISSING"}]
        summary = attach_market_caps(rows, records)
        self.assertEqual(rows[0]["marketCap"], 1234567890123)
        self.assertEqual(summary["availableCount"], 2)
        self.assertEqual(summary["missingCount"], 1)
        self.assertEqual(rows[2]["marketCapStatus"], "unavailable")

    def test_failed_refresh_retains_value_and_original_timestamp_with_stale_status(self):
        old = [{"symbol": "A"}]
        attach_market_caps(old, parse_screener(self.fixture(), "2026-11-09T08:00:00+00:00"))
        rows = [{"symbol": "A"}, {"symbol": "NEW"}]
        with tempfile.TemporaryDirectory() as directory, patch("market_caps.fetch_market_caps", side_effect=RuntimeError("offline")):
            summary = refresh_market_caps(rows, {"rows": old}, Path(directory), True)
        self.assertEqual(rows[0]["marketCap"], 1200000)
        self.assertEqual(rows[0]["marketCapFetchedAt"], "2026-11-09T08:00:00+00:00")
        self.assertEqual(rows[0]["marketCapStatus"], "stale")
        self.assertIsNone(rows[1]["marketCap"])
        self.assertEqual(summary["currentCount"], 0)
        self.assertEqual(summary["staleCount"], 1)
        self.assertEqual(summary["error"], "offline")

    def test_a_partial_response_does_not_erase_prior_observations(self):
        prior = [{"symbol": "A"}, {"symbol": "BRK-B"}]
        records = parse_screener(self.fixture(), "2026-11-09T08:00:00+00:00")
        attach_market_caps(prior, records)
        rows = [{"symbol": "A"}, {"symbol": "BRK-B"}]
        stats = attach_market_caps(rows, {"A": {**records["A"], "marketCap": 1300000}}, {"rows": prior})
        self.assertEqual(rows[0]["marketCapStatus"], "ok")
        self.assertEqual(rows[1]["marketCapStatus"], "stale")
        self.assertEqual(stats["availableCount"], 2)

    def test_cache_preserves_actual_fetch_timestamp_and_invalid_refresh_does_not_replace_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            with patch("market_caps.fetch_bytes", return_value=json.dumps(self.fixture()).encode()) as request:
                first = fetch_market_caps(cache)
                second = fetch_market_caps(cache)
                self.assertEqual(request.call_count, 1)
                self.assertEqual(first, second)
            cache_bytes = (cache / "nasdaq-market-caps-v1.json").read_bytes()
            with patch("market_caps.fetch_bytes", return_value=b'{"data":null}'):
                with self.assertRaises(ValueError):
                    fetch_market_caps(cache, refresh=True)
            self.assertEqual((cache / "nasdaq-market-caps-v1.json").read_bytes(), cache_bytes)


if __name__ == "__main__":
    unittest.main()
