import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from add_return_columns import add_columns
from engine import additional_excess_periods, build_equities, excess, rnd
from test_calibrated_score import fixture


class ReturnColumnTests(unittest.TestCase):
    def series(self):
        sessions = ['2026-10-23', '2026-10-27', '2026-10-28', '2026-10-29',
                    '2026-10-30', '2026-11-02', '2026-11-03', '2026-11-04',
                    '2026-11-05', '2026-11-06', '2026-11-09']
        benchmark = {d: {'close': 100} for d in sessions}
        asset = {d: {'close': 100} for d in sessions}
        asset['2026-11-04']['close'] = 80
        asset['2026-11-09']['close'] = 120
        benchmark['2026-11-09']['close'] = 105
        return sessions, asset, benchmark

    def test_three_days_use_benchmark_sessions_and_endpoint_returns(self):
        sessions, asset, benchmark = self.series()
        result = additional_excess_periods(asset, benchmark, sessions, sessions[-1])
        self.assertEqual(result['d3From'], '2026-11-04')
        self.assertAlmostEqual(result['d3'], 45)
        self.assertNotEqual(result['d3'], rnd(excess(asset, benchmark, '2026-11-06', sessions[-1])))

    def test_fortnight_anchors_on_or_before_fourteen_calendar_days(self):
        sessions, asset, benchmark = self.series()
        result = additional_excess_periods(asset, benchmark, sessions, sessions[-1])['fortnight']
        self.assertEqual(result['target'], '2026-10-26')
        self.assertEqual(result['from'], '2026-10-23')
        self.assertEqual(result['to'], '2026-11-09')
        self.assertAlmostEqual(result['value'], 15)

    def test_missing_asset_endpoints_never_shift_the_benchmark_anchor(self):
        for missing, field in [('2026-11-04', 'd3'), ('2026-10-23', 'fortnight'), ('2026-11-09', 'both')]:
            with self.subTest(missing=missing):
                sessions, asset, benchmark = self.series()
                del asset[missing]
                result = additional_excess_periods(asset, benchmark, sessions, sessions[-1])
                if field in ('d3', 'both'):
                    self.assertIsNone(result['d3'])
                    self.assertEqual(result['d3From'], '2026-11-04')
                if field in ('fortnight', 'both'):
                    self.assertIsNone(result['fortnight']['value'])
                    self.assertEqual(result['fortnight']['from'], '2026-10-23')

    def test_insufficient_benchmark_history_is_explicitly_missing(self):
        sessions, asset, benchmark = self.series()
        result = additional_excess_periods(asset, benchmark, sessions[:2], sessions[1])
        self.assertIsNone(result['d3'])
        self.assertIsNone(result['d3From'])
        self.assertIsNone(result['fortnight']['value'])
        self.assertIsNone(result['fortnight']['from'])

    def test_future_updates_and_offline_backfill_use_the_same_formula(self):
        sessions, daily, intra, universe, settings = fixture()
        result = build_equities(universe, settings, daily, intra)
        for row in result['rows']:
            self.assertEqual(row['d3From'], sessions[-4])
            self.assertEqual(row['d3'], rnd(excess(daily[row['symbol']]['bars'], daily['SPY']['bars'], sessions[-4], sessions[-1])))
            self.assertIn('fortnight', row)
        original = copy.deepcopy(result)
        for row in original['rows']:
            for field in ('d3', 'd3From', 'fortnight'):
                row.pop(field)
        updated = add_columns(copy.deepcopy(original))
        self.assertEqual(updated, result)
        self.assertEqual(add_columns(copy.deepcopy(updated)), updated)
        for old, new in zip(original['rows'], updated['rows']):
            self.assertEqual(old, {k: v for k, v in new.items() if k not in ('d3', 'd3From', 'fortnight')})

    def test_backfill_uses_shared_spy_calendar_even_when_a_stock_date_is_missing(self):
        _, daily, intra, universe, settings = fixture()
        snapshot = build_equities(universe, settings, daily, intra)
        row = snapshot['rows'][0]
        start = row['d3From']
        row['history'] = [p for p in row['history'] if p['date'] != start]
        add_columns(snapshot)
        self.assertEqual(row['d3From'], start)
        self.assertIsNone(row['d3'])


if __name__ == '__main__':
    unittest.main()
