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


def test_the_publish_request_names_the_loader_and_what_changed(monkeypatch):
    """EXEC-PUBLISH-FLOW: a clean intraday run sends its own completion signal (source Terminal_Publish_Request)."""
    import json as _json
    import urllib.request as ur
    import intraday_update as iu
    sent = []

    class Answer:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"status": "triggered"}'

    monkeypatch.setenv("TELEGRAM_NOTIFY_URL", "http://monitor/notify")
    monkeypatch.setenv("TELEGRAM_NOTIFY_SECRET", "s" * 32)
    monkeypatch.setattr(ur, "urlopen", lambda request, timeout: sent.append(request) or Answer())
    assert iu.request_publication("intraday-2026-11-05-2026-11-05-7", 38505)
    body = _json.loads(sent[0].data)
    assert body == {"source_table": "Terminal_Publish_Request", "execution_id": "intraday-2026-11-05-2026-11-05-7",
                    "details": {"loader": "idx-intraday-cron", "changed": 38505}}
    monkeypatch.delenv("TELEGRAM_NOTIFY_URL")
    assert not iu.request_publication("x", 1)


def test_the_loaders_hold_and_release_the_publisher_write_lock():
    import price_update as pu
    seen = []

    class Conn:
        def execute(self, sql, params=()):
            seen.append((sql, params))
    pu.hold_publish_write_lock(Conn())
    pu.release_publish_write_lock(Conn())
    assert seen == [("SELECT pg_advisory_lock_shared(hashtext(%s))", ("terminal_publish_write",)),
                    ("SELECT pg_advisory_unlock_shared(hashtext(%s))", ("terminal_publish_write",))]
