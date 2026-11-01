import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from home_engine import build_cross_markets, cross_snapshot, parse_market_daily
from home_providers import optional, parse_southbound, parse_stablecoins, parse_articles


def market(symbol):
    return {'symbol':symbol,'name':symbol,'providerSymbol':symbol,'group':'equity','session':'exchange','tradingViewSymbol':symbol}


def chart(stamp, zone, price=100):
    return {'chart':{'result':[{'meta':{'exchangeTimezoneName':zone,'currency':'USD'},'timestamp':[stamp],
        'indicators':{'quote':[{'close':[price]}],'adjclose':[{'adjclose':[price]}]}}]}}


class HomeCalculationTests(unittest.TestCase):
    def test_median_is_per_period_and_excess_is_percentage_points(self):
        daily={s:{'bars':{'2026-01-01':{'close':100},'2026-01-02':{'close':v}}} for s,v in [('A',110),('B',105),('C',90)]}
        rows,medians,counts=cross_snapshot([market(s) for s in daily],daily,['2026-01-01','2026-01-02'],1,{'1':1})
        by={r['symbol']:r for r in rows}
        self.assertAlmostEqual(medians['1'],5)
        self.assertAlmostEqual(by['A']['excess']['1'],5)
        self.assertAlmostEqual(by['C']['excess']['1'],-15)
        self.assertEqual(counts['1'],3)
        self.assertEqual(by['A']['rank'],1)

    def test_missing_endpoint_is_not_filled_from_previous_day(self):
        daily={s:{'bars':{'a':{'close':100},'b':{'close':v}}} for s,v in [('A',110),('B',105),('C',90)]}
        del daily['B']['bars']['b']
        rows,_,_=cross_snapshot([market(s) for s in daily],daily,['a','b'],1,{'1':1},.6)
        row=next(r for r in rows if r['symbol']=='B')
        self.assertIsNone(row['rank']);self.assertIsNone(row['score']);self.assertIsNone(row['absolute']['1'])

    def test_five_session_rank_change_is_recalculated_on_the_old_date(self):
        dates=[];day=datetime(2026,1,1)
        while len(dates)<80:
            if day.weekday()<5:dates.append(day.date().isoformat())
            day+=timedelta(days=1)
        prices={'A':[100 if i<78 else 200 for i in range(80)],'B':[100*1.01**i for i in range(80)],
                'C':[100*1.005**i for i in range(80)],'SPY':[100]*80}
        daily={s:{'bars':{d:{'close':values[i],'price':values[i]} for i,d in enumerate(dates)},'currency':'USD','timezone':'UTC'} for s,values in prices.items()}
        result=build_cross_markets({'markets':[market(s) for s in prices],'scoreWeights':{'1':.5,'5':.3,'20':.2}},daily)
        row=next(r for r in result['rows'] if r['symbol']=='A')
        self.assertEqual(result['previousRankDate'],dates[-6])
        self.assertEqual(row['rank'],1);self.assertEqual(row['rankDelta5d'],2)
        self.assertEqual(result['periodFrom']['5'],dates[-6])

    def test_fx_keeps_london_session_date_across_summer_time(self):
        stamp=int(datetime(2026,10,22,23,tzinfo=timezone.utc).timestamp())
        result=parse_market_daily(chart(stamp,'Europe/London'),'fx',datetime(2026,10,24,tzinfo=timezone.utc))
        self.assertIn('2026-10-23',result['bars'])
        self.assertNotIn('2026-10-22',result['bars'])

    def test_crypto_open_utc_day_is_excluded(self):
        stamp=int(datetime(2026,11,1,tzinfo=timezone.utc).timestamp())
        result=parse_market_daily(chart(stamp,'UTC'),'utc24h',datetime(2026,11,1,12,tzinfo=timezone.utc))
        self.assertEqual(result['bars'],{})

    def test_hong_kong_open_session_is_excluded(self):
        stamp=int(datetime(2026,10,30,1,30,tzinfo=timezone.utc).timestamp())
        result=parse_market_daily(chart(stamp,'Asia/Hong_Kong'),'exchange',datetime(2026,10,30,7,59,tzinfo=timezone.utc))
        self.assertEqual(result['bars'],{})

    def test_stablecoin_supply_uses_usd_valued_dollar_peg_and_calendar_deltas(self):
        base=1790812800
        raw=[{'date':str(base+i*86400),'totalCirculating':{'peggedUSD':9999999,'peggedJPY':999999999},
              'totalCirculatingUSD':{'peggedUSD':100+i,'peggedJPY':999}} for i in range(31)]
        result=parse_stablecoins(json.dumps(raw).encode())
        self.assertEqual(result['value'],130);self.assertEqual(result['change7d'],7);self.assertEqual(result['change30d'],30)

    def test_hkex_combines_both_routes_and_converts_million_hkd(self):
        def record(name,buy,sell):
            return {'market':name,'date':'2026-10-30','tradingDay':1,'content':[{'table':{'classname':'tradingTable',
                'schema':[['Buy Turnover','Sell Turnover']],'tr':[{'td':[[str(buy)]]},{'td':[[str(sell)]]}]}}]}
        raw=('tabData = '+json.dumps([record('SSE Southbound',10,5),record('SZSE Southbound',4,10),record('SSE Northbound',999,1)])+';').encode()
        result=parse_southbound(raw,'2026-10-30')
        self.assertEqual(result['net'],-1_000_000)
        with self.assertRaises(ValueError):parse_southbound(raw,'2026-10-29')

    def test_optional_failure_preserves_original_asof(self):
        def fail():raise RuntimeError('provider unavailable')
        result=optional({'crypto':{'value':100,'asOf':'2026-10-20'}},'crypto',fail)
        self.assertEqual(result['asOf'],'2026-10-20');self.assertEqual(result['value'],100);self.assertEqual(result['status'],'stale')

    def test_non_feed_html_and_unsafe_publisher_links_are_rejected(self):
        with self.assertRaises(ValueError):parse_articles(b'<html><title>Site Unavailable</title></html>')
        bad=b'<rss><channel><item><title>x</title><link>javascript:alert(1)</link><pubDate>Sat, 31 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>'
        with self.assertRaises(ValueError):parse_articles(bad)


if __name__=='__main__':unittest.main()
