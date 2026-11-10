import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from engine import build_equities, intraday_excess, weighted_score
from providers import cached_chart, parse_chart
from compare_rankings import compare, read_public_reference

WEIGHTS = {'h1': .25, 'h4': .25, '1': .25, '5': .15, '20': .10}


def fixture():
    sessions = []
    day = datetime(2025, 1, 1)
    while len(sessions) < 300:
        if day.weekday() < 5:
            sessions.append(day.date().isoformat())
        day += timedelta(days=1)
    prices = {'SPY': [100]*300, 'A': [100]*300, 'B': [100]*298+[101, 102]}
    daily = {s: {'bars': {d: {'close': values[i], 'price': values[i]} for i, d in enumerate(sessions)}} for s, values in prices.items()}
    intra = {s: {'bars': {}} for s in prices}
    for day in sessions[-3:]:
        end = int(datetime.fromisoformat(day+'T16:00:00').replace(tzinfo=ZoneInfo('America/New_York')).timestamp())
        for offset in [19800, 16200, 12600, 9000, 5400, 1800, 0]:
            for s in prices:
                value = 110 if s == 'A' and day == sessions[-1] and offset == 0 else 100
                intra[s]['bars'][end-offset] = {'close': value}
    universe = {'stocks': [{'symbol': s, 'name': s, 'sector': 'SPY', 'sectorName': 'Test'} for s in ['A', 'B']], 'sectors': [{'symbol': 'SPY'}]}
    settings = {'benchmark': 'SPY', 'scoreWeights': WEIGHTS, 'longTermWeights': {'252': 1}, 'topFraction': .2, 'historySessions': 64}
    return sessions, daily, intra, universe, settings


class CalibratedScoreTests(unittest.TestCase):
    def test_real_public_examples_on_both_dates_match_at_published_precision(self):
        data = json.loads((Path(__file__).parent/'fixtures/public_calibration_examples.json').read_text())
        for r in data['observations']:
            with self.subTest(date=r['date'], symbol=r['symbol']):
                # Each daily endpoint independently encodes the published excess return.
                sessions = list(range(21))
                benchmark = {t: {'close': 100} for t in sessions}
                asset = {20: {'close': 100}}
                for n in [1, 5, 20]:
                    asset[20-n] = {'close': 100/(1+r[f'd{n}']/100)}
                value = weighted_score(asset, benchmark, sessions, 20, WEIGHTS, {'h1': r['h1'], 'h4': r['h4']})
                self.assertLessEqual(abs(value-r['referenceScore']), .000101)

    def test_missing_hourly_input_excludes_score_without_daily_fallback(self):
        sessions, daily, _, _, _ = fixture()
        for hourly in [None, {'h1': 1}, {'h1': 1, 'h4': None}]:
            self.assertIsNone(weighted_score(daily['A']['bars'], daily['SPY']['bars'], sessions, 299, WEIGHTS, hourly))

    def test_historical_cutoff_does_not_include_a_future_hourly_move(self):
        _, _, intra, _, _ = fixture()
        ends = sorted(intra['SPY']['bars'])
        previous = ends[-8]
        self.assertEqual(intraday_excess(intra['A']['bars'], intra['SPY']['bars'], previous)['h1'], 0)
        self.assertEqual(intraday_excess(intra['A']['bars'], intra['SPY']['bars'])['h1'], 10)

    def test_rank_delta_is_recomputed_with_same_formula_on_both_days(self):
        _, daily, intra, universe, settings = fixture()
        result = build_equities(universe, settings, daily, intra, {'rows': [{'symbol': 'A', 'rank': 1}]})
        rows = {r['symbol']: r for r in result['rows']}
        self.assertEqual(rows['A']['rank'], 1)
        self.assertEqual(rows['A']['rankDelta'], 1)
        self.assertEqual(rows['A']['score'], 5)
        self.assertEqual(rows['A']['streak'], 1)
        self.assertFalse(rows['A']['streakCapped'])
        self.assertEqual(result['rankHistorySessions'], 3)
        self.assertEqual(result['sectors'][0]['score'], 0)

    def test_missing_latest_stock_candle_is_not_replaced_by_an_older_candle(self):
        _, daily, intra, universe, settings = fixture()
        del intra['A']['bars'][max(intra['A']['bars'])]
        rows = {r['symbol']: r for r in build_equities(universe, settings, daily, intra)['rows']}
        self.assertIsNone(rows['A']['score'])
        self.assertIsNone(rows['A']['rank'])
        self.assertEqual(rows['A']['status'], 'partial')

    def test_streak_at_intraday_history_boundary_is_a_lower_bound(self):
        _, daily, intra, universe, settings = fixture()
        for t in intra['A']['bars']:
            intra['A']['bars'][t]['close'] = 100
        for t in sorted(intra['A']['bars'])[6::7]:
            intra['A']['bars'][t]['close'] = 120
        row = next(r for r in build_equities(universe, settings, daily, intra)['rows'] if r['symbol'] == 'A')
        self.assertEqual(row['streak'], 3)
        self.assertTrue(row['streakCapped'])

    def test_snapshot_inputs_explain_the_new_score(self):
        _, daily, intra, universe, settings = fixture()
        result = build_equities(universe, settings, daily, intra)
        for row in result['rows']:
            self.assertAlmostEqual(row['score'], sum(WEIGHTS[k]*v for k, v in row['scoreInputs'].items()), places=4)

    def test_intraday_cache_uses_explicit_58_day_window_and_new_cache_key(self):
        raw = json.dumps({'chart': {'result': [{'timestamp': [100]}]}}).encode()
        with tempfile.TemporaryDirectory() as folder, patch('providers.time.time', return_value=2_000_000_000), patch('providers.fetch_bytes', return_value=raw) as fetch:
            cache = Path(folder)
            (cache/'SPY.30m.json').write_bytes(raw)
            cached_chart('SPY', '30m', cache)
            query = parse_qs(urlparse(fetch.call_args.args[0]).query)
            self.assertEqual(int(query['period2'][0])-int(query['period1'][0]), 58*86400)
            self.assertTrue((cache/'SPY.30m58d-v2.json').exists())

    def test_source_session_end_metadata_handles_an_early_close(self):
        ny = ZoneInfo('America/New_York')
        opened = int(datetime(2026, 11, 27, 9, 30, tzinfo=ny).timestamp())
        closed = int(datetime(2026, 11, 27, 13, tzinfo=ny).timestamp())
        raw = {'chart': {'result': [{'meta': {'exchangeTimezoneName': str(ny), 'tradingPeriods': [[{'start': opened, 'end': closed}]]}, 'timestamp': [closed-1800, closed], 'indicators': {'quote': [{'close': [100, 999]}]}}]}}
        data = parse_chart(raw, '30m', datetime(2026, 11, 27, 18, 1, tzinfo=ZoneInfo('UTC')))
        self.assertEqual(data['sessionEnds']['2026-11-27'], closed)
        self.assertEqual(data['bars'], {closed: {'close': 100.0, 'price': 100.0, 'volume': None}})


class ComparisonTests(unittest.TestCase):
    def reference(self):
        return {'tab': 'stocks', 'premium': False, 'volMode': False, 'rows': [
            {'symbol': 'LB:A.US', 'score': 3, 'dailyRank': 99, 'rollingExcess': {'w1': {'to': '2026-11-02'}}},
            {'symbol': 'LB:C.US', 'score': 2, 'dailyRank': 1, 'rollingExcess': {'w1': {'to': '2026-11-02'}}},
            {'symbol': 'LB:B.US', 'score': 1, 'dailyRank': 2, 'rollingExcess': {'w1': {'to': '2026-11-02'}}},
        ]}

    def test_comparison_uses_visible_order_and_same_symbol_cohort(self):
        snapshot = {'asOf': '2026-11-02', 'rows': [{'symbol': 'B', 'rank': 1, 'score': 4}, {'symbol': 'A', 'rank': 2, 'score': 1}]}
        result = compare(snapshot, self.reference())
        self.assertEqual(result['commonRanked'], 2)
        self.assertEqual(result['referenceOnly'], ['C'])
        self.assertEqual(result['meanAbsoluteRankDifference'], 1)
        self.assertEqual(result['rows'][0]['referenceRankCommon'], 1)
        self.assertEqual(result['rows'][0]['referenceDisplayRank'], 1)
        snapshot['asOf'] = '2026-10-30'
        with self.assertRaises(ValueError):
            compare(snapshot, self.reference())

    def test_parser_reads_literal_public_props_without_executing_javascript(self):
        props = self.reference()
        flight = '2f:'+json.dumps(['$', '$L30', None, props])+'\n'
        page = '<script>self.__next_f.push('+json.dumps([1, flight])+')</script>'
        self.assertEqual(read_public_reference(page), props)
        props['volMode'] = True
        page = '<script>self.__next_f.push('+json.dumps([1, '2f:'+json.dumps(['$', '$L30', None, props])+'\n'])+')</script>'
        with self.assertRaises(ValueError):
            read_public_reference(page)

    def test_cross_date_diagnostic_requires_opt_in_and_cannot_claim_formula_accuracy(self):
        snapshot={'asOf':'2026-10-30','rows':[{'symbol':'A','rank':1,'score':3},{'symbol':'B','rank':2,'score':1}]}
        with self.assertRaises(ValueError):compare(snapshot,self.reference())
        result=compare(snapshot,self.reference(),allow_date_mismatch=True)
        self.assertEqual(result['referenceAsOf'],'2026-11-02')
        self.assertEqual(result['lokiAsOf'],'2026-10-30')
        self.assertFalse(result['formulaAccuracyComparable'])
        self.assertEqual(result['comparisonType'],'cross-date-published-snapshots')
        mixed=self.reference();mixed['rows'][0]['rollingExcess']['w1']['to']='2026-11-01'
        with self.assertRaisesRegex(ValueError,'mixed'):compare(snapshot,mixed,allow_date_mismatch=True)

    def test_duplicate_normalized_symbols_are_rejected_instead_of_silently_overwritten(self):
        snapshot={'asOf':'2026-11-02','rows':[{'symbol':'A','rank':1,'score':3},{'symbol':'B','rank':2,'score':1}]}
        reference=self.reference();reference['rows'][1]['symbol']='LB:A.US'
        with self.assertRaisesRegex(ValueError,'duplicate'):compare(snapshot,reference)


if __name__ == '__main__':
    unittest.main()
