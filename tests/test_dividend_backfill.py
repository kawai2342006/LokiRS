import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dividend_backfill import backfill_verified, load_verified

ROOT=Path(__file__).resolve().parents[1]
ACTION={'exDate':'2026-11-06','amountUSD':.43,'source':'https://www.pfizer.com/dividend'}


def series(prior=29.88):
    return {'bars':{'2026-11-04':{'close':30.00,'price':30.00},
                    '2026-11-05':{'close':prior,'price':29.88},
                    '2026-11-06':{'close':29.39,'price':29.39}}}


class VerifiedDividendTests(unittest.TestCase):
    def test_official_ex_date_repairs_returns_and_preserves_quoted_prices(self):
        data=series();applied=backfill_verified(data,[ACTION]);bars=data['bars']
        self.assertEqual(len(applied),1)
        self.assertAlmostEqual(bars['2026-11-05']['close'],29.45)
        self.assertAlmostEqual((29.39/bars['2026-11-05']['close']-1)*100,-.203735,places=5)
        self.assertEqual(bars['2026-11-04']['price'],30.00)
        self.assertEqual(bars['2026-11-05']['price'],29.88)
        self.assertEqual(bars['2026-11-06']['dividendBackfill']['source'],ACTION['source'])
        self.assertEqual(backfill_verified(data,[ACTION]),[])

    def test_source_adjustment_takes_precedence_without_double_count(self):
        data=series(prior=29.45)
        self.assertEqual(backfill_verified(data,[ACTION]),[])
        self.assertEqual(data['bars']['2026-11-05']['close'],29.45)

    def test_unexplained_factor_and_missing_ex_date_are_not_rewritten(self):
        data=series(prior=28.00)
        self.assertEqual(backfill_verified(data,[ACTION]),[])
        self.assertEqual(data['bars']['2026-11-05']['close'],28.00)
        data=series();del data['bars']['2026-11-06']
        self.assertEqual(backfill_verified(data,[ACTION]),[])

    def test_dated_sources_and_unique_events_are_declared(self):
        actions=load_verified(ROOT/'config/verified_dividends.json')
        self.assertEqual(len(actions),10)
        self.assertEqual(actions['PFE'][0]['amountUSD'],.43)
        self.assertTrue(all(item['source'].startswith('https://') for group in actions.values() for item in group))


if __name__=='__main__':unittest.main()
