import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from intraday_update import BARS_PER_SESSION, MAX_BARS, requested_bars, rows_of, scale_check
from price_update import Symbol


def bar(day, hour, o, h, l, c, v=100.0):
    return {"date": date(2026, 10, day), "source_bar_time": datetime(2026, 10, day, hour, tzinfo=timezone.utc),
            "open": o, "high": h, "low": l, "close": c, "volume": v, "security_type": "stock"}


class IntradayTests(unittest.TestCase):
    def test_a_series_never_stored_is_asked_in_full_and_a_stored_one_for_its_gap_plus_the_overlap(self):
        self.assertEqual(requested_bars("5m", None), MAX_BARS)
        self.assertEqual(requested_bars("1h", 0), BARS_PER_SESSION["1h"] * 3)
        self.assertEqual(requested_bars("15m", 2), BARS_PER_SESSION["15m"] * 5)
        self.assertEqual(requested_bars("5m", 400), MAX_BARS)

    def test_only_completed_sessions_from_since_are_kept_and_a_broken_bar_is_skipped(self):
        stock = Symbol(1, "Bank", "BBCA", "IDX:BBCA", "IDX", "stock")
        bars = [bar(27, 2, 10, 11, 9, 10), bar(28, 2, 10, 11, 9, 12),   # close above high: skipped
                bar(29, 2, 10, 11, 9, 10.5), bar(30, 2, 10, 11, 9, 10)]
        rows, invalid = rows_of(stock, "1h", bars, date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 31))
        self.assertEqual(invalid, 1)
        self.assertEqual([r["session_date"] for r in rows], [date(2026, 10, 29)])
        self.assertEqual((rows[0]["adjustment"], rows[0]["timeframe"], rows[0]["close"]), ("splits", "1h", Decimal("10.5")))
        index = Symbol(2, "Composite", "IHSG", "IDX:COMPOSITE", "IDX", "index")
        rows, _ = rows_of(index, "4h", [dict(bar(29, 2, 10, 11, 9, 10), volume=None, security_type="index")],
                          date(2020, 1, 1), date(2026, 10, 30), date(2026, 10, 31))
        self.assertEqual((rows[0]["adjustment"], rows[0]["volume"]), ("none", None))

    def test_scale_check_tells_a_readjusted_history_from_revised_bars(self):
        t = [datetime(2026, 10, d, tzinfo=timezone.utc) for d in (27, 28, 29, 30)]
        stored = {t[0]: Decimal(700), t[1]: Decimal(690), t[2]: Decimal(680)}
        self.assertEqual(scale_check(stored, {t[0]: 700, t[1]: 690, t[2]: 680, t[3]: 670}), ("SAME", 1.0, 0))
        verdict, ratio, n = scale_check(stored, {t[0]: 350, t[1]: 345, t[2]: 340})
        self.assertEqual((verdict, ratio, n), ("SCALE_CHANGED", 2.0, 3))
        self.assertEqual(scale_check(stored, {t[0]: 700, t[1]: 695, t[2]: 680})[0], "REVISED")
        self.assertEqual(scale_check({}, {t[0]: 700}), ("SAME", 1.0, 0))


if __name__ == "__main__":
    unittest.main()
