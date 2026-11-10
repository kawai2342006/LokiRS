import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from providers import cached_chart, parse_chart, reconcile_latest_daily
from engine import build_equities
from dividend_backfill import backfill_verified
from test_calibrated_score import fixture
import update_data

NY = ZoneInfo('America/New_York')
NOW = datetime(2026,11,5,2,tzinfo=timezone.utc)


def inputs():
    start = int(datetime(2026,11,4,9,30,tzinfo=NY).timestamp())
    end = int(datetime(2026,11,4,16,tzinfo=NY).timestamp())
    daily = {'bars': {'2026-11-03': {'close':100,'price':100}}, 'timezone':str(NY),
             'actionsChecked':True,'corporateActionDates':[],'dailySourceDates':['2026-11-03','2026-11-04'],
             'pendingDailyDates':['2026-11-04'],'regularMarketTime':end,'observedThrough':NOW.isoformat()}
    hourly = {'bars':{t:{'close':110 if t==end else 100} for t in range(start+1800,end+1,1800)},
              'sessionStarts':{'2026-11-04':start},'sessionEnds':{'2026-11-04':end},'observedThrough':NOW.isoformat()}
    return daily,hourly


class FreshnessTests(unittest.TestCase):
    def test_missing_daily_close_uses_only_a_complete_observed_session_and_is_flagged(self):
        daily,hourly=inputs()
        actual=reconcile_latest_daily(daily,hourly,NOW)['bars']['2026-11-04']
        self.assertEqual(actual['close'],110)
        self.assertTrue(actual['reconstructed'])
        self.assertEqual(actual['basis'],'completed-intraday-close')
        self.assertEqual(actual['sourceTime'],'2026-11-04T21:00:00+00:00')

    def test_reconstruction_rejects_corporate_actions_unknown_adjustments_and_incomplete_sessions(self):
        for problem in ['action','unknown_actions','nonunit_factor','missing_bar','open','old_capture','multiple_missing_dates']:
            with self.subTest(problem=problem):
                daily,hourly=inputs();now=NOW
                if problem=='action':daily['corporateActionDates']=['2026-11-04']
                if problem=='unknown_actions':daily['actionsChecked']=False
                if problem=='nonunit_factor':daily['bars']['2026-11-03']['close']=99
                if problem=='missing_bar':del hourly['bars'][min(hourly['bars'])]
                if problem=='open':now=datetime(2026,11,4,20,59,tzinfo=timezone.utc)
                if problem=='old_capture':hourly['observedThrough']='2026-11-04T20:59:00+00:00'
                if problem=='multiple_missing_dates':
                    daily['bars']={'2026-11-02':{'close':100,'price':100}}
                    daily['dailySourceDates']=['2026-11-02','2026-11-03','2026-11-04']
                self.assertNotIn('2026-11-04',reconcile_latest_daily(daily,hourly,now)['bars'])

    def test_completed_regular_quote_captures_the_closing_auction(self):
        daily,hourly=inputs();end=hourly['sessionEnds']['2026-11-04']
        daily.update(regularMarketPrice=111,regularMarketTime=end+3,regularSessionEnd=end)
        bar=reconcile_latest_daily(daily,hourly,NOW)['bars']['2026-11-04']
        self.assertEqual(bar['price'],111)
        self.assertEqual(bar['basis'],'completed-regular-session-quote')

    def test_verified_cash_recovery_preserves_price_and_applies_distribution_once(self):
        action={'exDate':'2026-11-04','amountUSD':1,'source':'https://issuer.example/dividend'}
        for adjusted in [False,True]:
            with self.subTest(adjusted=adjusted):
                daily,hourly=inputs();daily['corporateActionDates']=['2026-11-04'];daily['nonCashActionDates']=[]
                if adjusted:daily['bars']['2026-11-03']['close']=99
                reconcile_latest_daily(daily,hourly,NOW,verified_cash_actions=[action])
                backfill_verified(daily,[action]);backfill_verified(daily,[action])
                self.assertEqual(daily['bars']['2026-11-03']['close'],99)
                self.assertEqual(daily['bars']['2026-11-04']['price'],110)
                self.assertEqual(daily['bars']['2026-11-04']['close'],110)
                self.assertEqual(daily['bars']['2026-11-04']['verifiedCashAction'],action)

    def test_verified_cash_does_not_override_split_unknown_action_or_unknown_factor(self):
        action={'exDate':'2026-11-04','amountUSD':1,'source':'https://issuer.example/dividend'}
        for problem in ['split','unknown_factor','missing_action_check','large_distribution']:
            with self.subTest(problem=problem):
                daily,hourly=inputs();daily['corporateActionDates']=['2026-11-04'];daily['nonCashActionDates']=[]
                event=dict(action)
                if problem=='split':daily['nonCashActionDates']=['2026-11-04']
                if problem=='unknown_factor':daily['bars']['2026-11-03']['close']=95
                if problem=='missing_action_check':daily['actionsChecked']=False
                if problem=='large_distribution':event['amountUSD']=26
                reconcile_latest_daily(daily,hourly,NOW,verified_cash_actions=[event])
                self.assertNotIn('2026-11-04',daily['bars'])

    def test_regular_quote_rejects_open_other_day_after_hours_and_invalid_values(self):
        for problem in ['preclose','afterhours','other_session','nonfinite','future_capture','missing_regular_end']:
            with self.subTest(problem=problem):
                daily,hourly=inputs();end=hourly['sessionEnds']['2026-11-04']
                daily.update(regularMarketPrice=999,regularMarketTime=end+3,regularSessionEnd=end)
                if problem=='preclose':daily['regularMarketTime']=end-1
                if problem=='afterhours':daily['regularMarketTime']=end+301
                if problem=='other_session':daily['regularSessionEnd']=end+86400
                if problem=='nonfinite':daily['regularMarketPrice']=float('nan')
                if problem=='future_capture':daily['regularMarketTime']=NOW.timestamp()+1
                if problem=='missing_regular_end':del daily['regularSessionEnd']
                bar=reconcile_latest_daily(daily,hourly,NOW)['bars']['2026-11-04']
                self.assertEqual(bar['price'],110)
                self.assertEqual(bar['basis'],'completed-intraday-close')

    def test_published_daily_value_always_takes_precedence(self):
        daily,hourly=inputs();daily['bars']['2026-11-04']={'close':111,'price':111}
        result=reconcile_latest_daily(daily,hourly,NOW)
        self.assertEqual(result['bars']['2026-11-04'],{'close':111,'price':111})

    def test_missing_daily_retry_prefers_native_values_and_preserves_data_on_failure(self):
        for failure in [False, True]:
            with self.subTest(failure=failure):
                series,hourly=inputs()
                daily={'A':series};intraday={'A':hourly}
                native={**series,'bars':{**series['bars'],'2026-11-04':{'close':111,'price':111}}}
                with patch.object(update_data,'cached_chart',side_effect=ValueError('unavailable') if failure else None,return_value=({},False)) as fetch, patch.object(update_data,'parse_chart',return_value=native):
                    errors=update_data.retry_pending_daily(daily,intraday,Path('/unused'),NOW,1)
                self.assertTrue(fetch.call_args.args[3])
                if failure:
                    self.assertIs(daily['A'],series)
                    self.assertEqual(errors[0]['interval'],'1d_retry')
                else:
                    self.assertEqual(daily['A']['bars']['2026-11-04']['close'],111)
                    self.assertFalse(errors)

    def test_already_reconstructed_completed_close_is_not_downloaded_again(self):
        series,hourly=inputs()
        reconcile_latest_daily(series,hourly,NOW)
        with patch.object(update_data,'cached_chart') as fetch:
            errors=update_data.retry_pending_daily({'A':series},{'A':hourly},Path('/unused'),NOW,1)
        fetch.assert_not_called()
        self.assertFalse(errors)
        self.assertTrue(series['bars']['2026-11-04']['reconstructed'])

    def test_cached_open_daily_bar_never_becomes_a_close_after_clock_advances(self):
        stamp=int(datetime(2026,11,4,9,30,tzinfo=NY).timestamp())
        raw={'_lokirsFetchedAt':datetime(2026,11,4,18,tzinfo=timezone.utc).timestamp(),
             'chart':{'result':[{'meta':{'exchangeTimezoneName':str(NY)},'timestamp':[stamp],
              'indicators':{'quote':[{'close':[110]}],'adjclose':[{'adjclose':[110]}]}}]}}
        self.assertEqual(parse_chart(raw,'1d',NOW)['bars'],{})

    def test_crossing_the_declared_market_close_invalidates_a_recent_cache(self):
        close=int(datetime(2026,11,4,16,tzinfo=NY).timestamp())
        raw={'_lokirsFetchedAt':close-3600,'chart':{'result':[{'timestamp':[100],
             'meta':{'currentTradingPeriod':{'regular':{'end':close}}}}]}}
        with tempfile.TemporaryDirectory() as folder, patch('providers.time.time',return_value=close+60), patch('providers.fetch_bytes',return_value=json.dumps(raw).encode()) as fetch:
            path=Path(folder)/'SPY.1d2y-v2.json';path.write_text(json.dumps(raw));os.utime(path,(close-3600,close-3600))
            _,used_cache=cached_chart('SPY','1d',Path(folder))
            self.assertFalse(used_cache);self.assertTrue(fetch.called)

    def test_newer_stock_day_does_not_change_the_benchmark_day_price_or_label(self):
        days,daily,hourly,universe,settings=fixture()
        future=(datetime.fromisoformat(days[-1])+timedelta(days=1)).date().isoformat()
        daily['A']['bars'][future]={'close':999,'price':999}
        result=build_equities(universe,settings,daily,hourly)
        row=next(r for r in result['rows'] if r['symbol']=='A')
        self.assertEqual(row['asOf'],result['asOf'])
        self.assertEqual(row['price'],100)

    def test_earlier_provisional_cash_adjustment_remains_visible_on_a_later_session(self):
        days,daily,hourly,universe,settings=fixture()
        mark={'exDate':days[-5],'amountUSD':.274815,'sourceStatus':'provisional','source':'https://issuer.example/adr'}
        daily['A']['bars'][days[-5]]['dividendBackfill']=mark
        result=build_equities(universe,settings,daily,hourly)
        row=next(r for r in result['rows'] if r['symbol']=='A')
        self.assertEqual(row['asOf'],days[-1])
        self.assertEqual(row['dividendBackfill'],mark)

    def test_validation_failure_preserves_the_existing_published_snapshot(self):
        days,daily,hourly,universe,settings=fixture()
        settings['minimumCoverage']=.8;settings['workers']=1
        universe['capturedAt']='2026-11-01'
        prior={'rows':[],'macro':[],'sentiment':{'status':'unavailable'},'contracts':{'status':'unavailable','symbols':[]},'meta':{}}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'config').mkdir();(root/'data').mkdir()
            (root/'config/settings.json').write_text(json.dumps(settings))
            (root/'config/universe.json').write_text(json.dumps(universe))
            (root/'config/verified_dividends.json').write_text(json.dumps({'actions':[]}))
            published=root/'data/latest.json';published.write_text(json.dumps(prior));original=published.read_bytes()
            def downloaded(symbol,interval,*args):return {'symbol':symbol,'interval':interval},False
            def parsed(raw,interval,*args):return (daily if interval=='1d' else hourly)[raw['symbol']]
            with patch.object(update_data,'ROOT',root), patch.object(update_data,'cached_chart',side_effect=downloaded), patch.object(update_data,'parse_chart',side_effect=parsed), patch.object(update_data,'refresh_market_caps',return_value={}), patch('sys.argv',['update_data','--rankings-only']), patch('validate_snapshot.validate',side_effect=ValueError('rejected snapshot')):
                with self.assertRaisesRegex(ValueError,'rejected snapshot'):update_data.run()
            self.assertEqual(published.read_bytes(),original)


if __name__=='__main__':unittest.main()
