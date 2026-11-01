import io
import sys
import unittest
import zipfile
from datetime import datetime, timezone, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from engine import change, excess, weighted_score, rolling_excess, month_before, percentiles, intraday_excess, intraday_clock_excess, macro_summary
from providers import parse_chart, parse_fred, stock_contract_symbols


def bars(**values):
    return {day: {"close": value} for day, value in values.items()}


class ReturnTests(unittest.TestCase):
    def test_excess_is_percentage_point_difference(self):
        asset, benchmark = bars(a=100, b=110), bars(a=100, b=105)
        self.assertAlmostEqual(excess(asset, benchmark, "a", "b"), 5)
        self.assertIsNone(excess(asset, benchmark, "missing", "b"))

    def test_weighted_score_requires_all_periods(self):
        asset, benchmark = bars(a=100, b=110, c=121), bars(a=100, b=100, c=100)
        self.assertAlmostEqual(weighted_score(asset, benchmark, ["a", "b", "c"], 2, {"1": .5, "2": .5}), 15.5)
        self.assertIsNone(weighted_score(asset, benchmark, ["a", "b", "c"], 1, {"1": .5, "2": .5}))

    def test_calendar_month_and_holiday_anchor(self):
        self.assertEqual(month_before("2024-03-31"), "2024-02-29")
        self.assertEqual(month_before("2025-03-31"), "2025-02-28")
        self.assertEqual(month_before("2026-01-31"), "2025-12-31")
        a, b = bars(**{"2026-10-23": 100, "2026-10-30": 110}), bars(**{"2026-10-23": 100, "2026-10-30": 105})
        result = rolling_excess(a, b, sorted(b), "2026-10-30", "2026-10-25")
        self.assertEqual(result["from"], "2026-10-23")
        self.assertAlmostEqual(result["value"], 5)

    def test_no_forward_fill_for_missing_stock_session(self):
        a, b = bars(**{"2026-10-22": 100, "2026-10-30": 110}), bars(**{"2026-10-23": 100, "2026-10-30": 105})
        self.assertIsNone(rolling_excess(a, b, sorted(b), "2026-10-30", "2026-10-25")["value"])

    def test_percentile_ties_and_insufficient_history(self):
        result=percentiles({"a": 1, "b": 2, "c": 2, "d": 4, "new": None})
        self.assertEqual(result, {"a": 0, "b": 50, "c": 50, "d": 100})
        self.assertEqual(percentiles({"only": 1}), {"only": None})

    def test_hourly_requires_exact_elapsed_time(self):
        end=int(datetime(2026,10,30,20,tzinfo=timezone.utc).timestamp())
        a={end: {"close": 110}, end-1800: {"close": 100}}
        b={end: {"close": 100}, end-1800: {"close": 100}}
        self.assertIsNone(intraday_clock_excess(a,b)["h1"])
        a[end-3600]={"close":100};b[end-3600]={"close":105}
        self.assertAlmostEqual(intraday_clock_excess(a,b)["h1"],14.7619,places=4)

    def test_hourly_candle_steps_disclose_short_final_candle(self):
        end=int(datetime(2026,10,30,20,tzinfo=timezone.utc).timestamp())
        ends=[end-12600,end-10800,end-9000,end-7200,end-5400,end-3600,end-1800,end]
        a={t:{"close":100 if t<end else 110} for t in ends}
        b={t:{"close":100} for t in ends}
        result=intraday_excess(a,b)
        self.assertAlmostEqual(result["h1"],10)
        self.assertEqual(result["h1ElapsedHours"],.5)
        self.assertEqual(result["h4ElapsedHours"],3.5)

    def test_missing_latest_benchmark_candle_does_not_use_old_stock_candle(self):
        end=int(datetime(2026,10,30,20,tzinfo=timezone.utc).timestamp())
        self.assertIsNone(intraday_excess({end-1800:{"close":100}},{end:{"close":101},end-1800:{"close":100}})["h1"])


class ProviderTests(unittest.TestCase):
    def test_crypto_ticker_collision_does_not_imply_stock_contract(self):
        base={"status":"TRADING","quoteAsset":"USDT","contractType":"PERPETUAL"}
        data={"symbols":[{**base,"baseAsset":"AI","underlyingType":"COIN"},
                         {**base,"baseAsset":"AAPL","underlyingType":"EQUITY"}]}
        self.assertEqual(stock_contract_symbols(data,{"AI","AAPL"}),["AAPL"])

    def chart(self, stamps, prices):
        return {"chart":{"result":[{"meta":{"exchangeTimezoneName":"America/New_York","currency":"USD"},"timestamp":stamps,"indicators":{"quote":[{"close":prices}],"adjclose":[{"adjclose":prices}]}}]}}

    def test_dividend_adjusted_return_price_is_separate_from_quoted_price(self):
        stamp=int(datetime(2026,10,30,13,30,tzinfo=timezone.utc).timestamp())
        data=self.chart([stamp],[100])
        data["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"]=[99]
        parsed=parse_chart(data,"1d",datetime(2026,10,30,21,tzinfo=timezone.utc))
        self.assertEqual(parsed["bars"]["2026-10-30"]["close"],99)
        self.assertEqual(parsed["bars"]["2026-10-30"]["price"],100)

    def test_partial_daily_candle_is_excluded(self):
        stamp=int(datetime(2026,10,30,13,30,tzinfo=timezone.utc).timestamp())
        data=self.chart([stamp],[100])
        self.assertEqual(parse_chart(data,"1d",datetime(2026,10,30,19,tzinfo=timezone.utc))["bars"],{})
        self.assertIn("2026-10-30",parse_chart(data,"1d",datetime(2026,10,30,21,tzinfo=timezone.utc))["bars"])

    def test_partial_intraday_and_missing_values_excluded(self):
        stamp=int(datetime(2026,10,30,19,30,tzinfo=timezone.utc).timestamp())
        self.assertEqual(parse_chart(self.chart([stamp],[100]),"30m",datetime(2026,10,30,19,45,tzinfo=timezone.utc))["bars"],{})
        values=parse_chart(self.chart([stamp,stamp-1800],[100,None]),"30m",datetime(2026,10,30,20,1,tzinfo=timezone.utc))["bars"]
        self.assertEqual(list(values),[stamp+1800])

    def test_fred_mixed_frequency_zip(self):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,"w") as archive:
            archive.writestr("weekly.csv","observation_date,WALCL\n2026-10-28,7000000\n")
            archive.writestr("daily.csv","observation_date,RRPONTSYD\n2026-10-28,100\n2026-10-29,.\n")
        series=parse_fred(stream.getvalue())
        self.assertEqual(series["WALCL"]["2026-10-28"],7000000)
        self.assertEqual(len(series["RRPONTSYD"]),1)

    def test_net_liquidity_units_and_no_future_component(self):
        series={"WALCL":{"2026-10-28":7000000},"WTREGEN":{"2026-10-28":700000},"RRPONTSYD":{"2026-10-28":100,"2026-10-29":900}}
        result=next(r for r in macro_summary(series,date(2026,10,30)) if r["id"]=="NET_LIQUIDITY")
        self.assertEqual(result["value"],6.2)
        self.assertEqual(result["componentDates"]["RRPONTSYD"],"2026-10-28")

    def test_old_net_liquidity_component_is_rejected(self):
        series={"WALCL":{"2026-10-28":7000000},"WTREGEN":{"2026-10-01":700000},"RRPONTSYD":{"2026-10-28":100}}
        result=next(r for r in macro_summary(series,date(2026,10,30)) if r["id"]=="NET_LIQUIDITY")
        self.assertIsNone(result["value"])


if __name__ == "__main__":
    unittest.main()
