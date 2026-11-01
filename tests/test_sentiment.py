import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sentiment_sources import INDEX_ID, MACROMICRO_URL, CNN_URL, fetch_index, parse_macromicro, parse_cnn
from update_sentiment import update_sentiment_snapshot

NOW = datetime(2026, 11, 1, 16, tzinfo=timezone.utc)


def public_page(points=None, reverse=False, chart_id=50108, stat_id=22748, name='US - CNN Fear and Greed Index'):
    configs = [{'stats': [{'stat_id': stat_id, 'name_en': name}]}, {'stats': [{'stat_id': 2, 'name_en': 'US - S&P 500'}]}]
    rows = [points if points is not None else [['2026-10-29', '30.7672'], ['2026-10-30', '26.2387']], [['2026-10-30', '7580.0698']]]
    if reverse:
        configs.reverse()
        rows.reverse()
    chart = {'id': chart_id, 'is_membersonly': 0, 'settings': {'seriesConfigs': configs}, 'series_last_rows': json.dumps(rows)}
    return ('<script>let collection=null; let chart = ' + json.dumps(chart) + '; otherCode();</script>').encode()


def cnn_page(**fields):
    return json.dumps({'fear_and_greed': {'score': 26.2, 'timestamp': '2026-10-30T20:00:00Z', 'previous_close': 31.0, **fields}}).encode()


class SentimentSourceTests(unittest.TestCase):
    def test_public_page_keeps_precision_observation_day_and_missing_history(self):
        result = parse_macromicro(public_page(), NOW)
        self.assertEqual(result['value'], 26.2387)
        self.assertEqual(result['previousClose'], 30.7672)
        self.assertEqual(result['previousLabel'], '上一筆')
        self.assertEqual(result['previousAsOf'], '2026-10-29')
        self.assertEqual(result['observationDate'], '2026-10-30')
        self.assertEqual(result['asOfPrecision'], 'date')
        self.assertEqual(result['asOf'], '2026-10-30')
        self.assertIsNone(result['weekAgo'])
        self.assertIsNone(result['monthAgo'])
        self.assertEqual(result['rating'], 'fear')

    def test_series_identity_follows_cnn_metadata_after_reordering(self):
        result = parse_macromicro(public_page(reverse=True), NOW)
        self.assertEqual(result['value'], 26.2387)

    def test_other_indices_cannot_replace_cnn(self):
        for change in [{'chart_id': 99999}, {'stat_id': 99999}, {'name': 'Crypto Fear and Greed Index'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_macromicro(public_page(**change), NOW)

    def test_missing_or_nonliteral_metadata_is_rejected(self):
        for raw in [b'<html>Sign in</html>', b'let chart = fetchPrivateData();']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_macromicro(raw, NOW)

    def test_invalid_score_or_future_date_is_not_published(self):
        for value in [True, 'NaN', 'Infinity', -1, 101, None]:
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                parse_macromicro(public_page([['2026-10-30', value]]), NOW)
        for day in ['2026-02-30', '2026-11-03', '2026-10-30T20:00:00Z']:
            with self.subTest(day=day), self.assertRaises(ValueError):
                parse_macromicro(public_page([[day, 26]]), NOW)

    def test_only_same_provider_recorded_history_populates_week_and_month(self):
        prior = parse_macromicro(public_page(), NOW)
        prior['history'] += [
            {'date': '2026-10-23', 'value': 32.5, 'provider': 'MacroMicro'},
            {'date': '2026-09-30', 'value': 41.5, 'provider': 'MacroMicro'},
            {'date': '2026-10-22', 'value': 99, 'provider': 'CNN'},
            {'date': 'bad', 'value': 10, 'provider': 'MacroMicro'},
        ]
        result = parse_macromicro(public_page(), NOW, prior)
        self.assertEqual((result['weekAgo'], result['weekAgoAsOf']), (32.5, '2026-10-23'))
        self.assertEqual((result['monthAgo'], result['monthAgoAsOf']), (41.5, '2026-09-30'))
        self.assertTrue(all(p['value'] != 99 for p in result['history']))

    def test_old_record_is_not_filled_into_a_missing_week(self):
        prior = parse_macromicro(public_page(), NOW)
        prior['history'].append({'date': '2026-10-15', 'value': 20, 'provider': 'MacroMicro'})
        self.assertIsNone(parse_macromicro(public_page(), NOW, prior)['weekAgo'])

    def test_working_macromicro_does_not_call_cnn(self):
        calls = []
        def load(url):
            calls.append(url)
            return public_page()
        result = fetch_index(load, now=NOW)
        self.assertEqual(calls, [MACROMICRO_URL])
        self.assertEqual(result['source'], 'MacroMicro')
        self.assertEqual(result['status'], 'ok')

    def test_cnn_is_used_only_after_public_page_failure(self):
        calls = []
        def load(url):
            calls.append(url)
            if url == MACROMICRO_URL:
                raise RuntimeError('Public page unavailable')
            return cnn_page(previous_1_week=40.2)
        result = fetch_index(load, now=NOW)
        self.assertEqual(calls, [MACROMICRO_URL, CNN_URL])
        self.assertEqual(result['source'], 'CNN')
        self.assertEqual(result['previousLabel'], '前收')
        self.assertEqual(result['weekAgo'], 40.2)
        self.assertEqual(result['observationDate'], '2026-10-30')

    def test_cnn_timestamp_is_observation_time_with_new_york_session_day(self):
        result = parse_cnn(cnn_page(timestamp='2026-10-31T00:30:00Z'), NOW)
        self.assertEqual(result['observationDate'], '2026-10-30')
        self.assertEqual(result['asOf'], '2026-10-31T00:30:00+00:00')
        for stamp in ['2026-11-03T00:00:00Z', '2026-10-30T20:00:00']:
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                parse_cnn(cnn_page(timestamp=stamp), NOW)

    def test_both_sources_failing_preserves_original_value_date_and_fetch_time(self):
        prior = {**parse_macromicro(public_page(), NOW), 'fetchedAt': '2026-10-31T10:00:00Z'}
        def fail(url):
            raise RuntimeError('Provider unavailable')
        result = fetch_index(fail, prior, NOW)
        for key in ['value', 'asOf', 'observationDate', 'source', 'fetchedAt']:
            self.assertEqual(result[key], prior[key])
        self.assertEqual(result['status'], 'stale')
        self.assertEqual(len(result['attempts']), 2)

    def test_older_provider_result_does_not_regress_the_retained_day(self):
        prior = parse_macromicro(public_page([['2026-10-31', '28']]), NOW)
        result = fetch_index(lambda url: public_page() if url == MACROMICRO_URL else cnn_page(), prior, NOW)
        self.assertEqual(result['value'], 28)
        self.assertEqual(result['asOf'], '2026-10-31')
        self.assertEqual(result['status'], 'stale')

    def test_all_missing_returns_unavailable_instead_of_zero(self):
        result = fetch_index(lambda url: b'<html>unavailable</html>', previous=['invalid'], now=NOW)
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['value'])

    def test_old_public_value_is_preserved_and_explicitly_stale(self):
        result = fetch_index(lambda url: public_page([['2026-10-01', '20']]) if url == MACROMICRO_URL else cnn_page(timestamp='2026-10-01T20:00:00Z'), now=NOW)
        self.assertEqual(result['status'], 'stale')
        self.assertEqual(result['observationDate'], '2026-10-01')


class SentimentSnapshotTests(unittest.TestCase):
    def test_standalone_refresh_does_not_touch_market_prices(self):
        result = parse_macromicro(public_page(), NOW)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'data').mkdir()
            latest = root/'data/latest.json'
            original = b'{"rows":[{"price":123}],"sentiment":{"status":"unavailable"}}\n'
            latest.write_bytes(original)
            with patch('update_sentiment.fetch_sentiment', return_value=result):
                update_sentiment_snapshot(root)
            self.assertEqual(latest.read_bytes(), original)
            self.assertEqual(json.loads((root/'data/sentiment.json').read_text())['value'], 26.2387)
            self.assertFalse((root/'data/sentiment.tmp').exists())

    def test_bad_independent_cache_still_uses_valid_embedded_snapshot(self):
        prior = parse_macromicro(public_page(), NOW)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'data').mkdir()
            (root/'data/latest.json').write_text(json.dumps({'sentiment': prior}))
            (root/'data/sentiment.json').write_text('[]')
            with patch('update_sentiment.fetch_sentiment', return_value=prior) as fetch:
                update_sentiment_snapshot(root)
                self.assertEqual(fetch.call_args.args[0]['observationDate'], '2026-10-30')


if __name__ == '__main__':
    unittest.main()
