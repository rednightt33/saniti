import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from intraday_update import (BARS_PER_SESSION, MAX_BARS, intraday_indexes, intraday_scope, requested_bars, rows_of,
                             scale_check, sessions_behind)
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


# EXEC-INDEX-GROUP-HISTORY stage 1: only the indexes that already have intraday bars are loaded and form the calendar
UNIVERSE = [Symbol(1, "Bank", "BBCA", "IDX:BBCA", "IDX", "stock"), Symbol(2, "Fund", "XIJI", "IDX:XIJI", "IDX", "fund"),
            Symbol(3, "Composite", "IHSG", "IDX:COMPOSITE", "IDX", "index"),
            Symbol(4, "LQ45", "LQ45", "IDX:LQ45", "IDX", "index"), Symbol(5, "Energy", "IDXENERGY", "IDX:IDXENERGY", "IDX", "index")]


class FakeConn:
    """Answers the two statements of intraday_indexes and sessions_behind from in-memory rows."""
    def __init__(self, intraday_tickers, daily):
        self.intraday, self.daily, self.calls = set(intraday_tickers), daily, []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        if "SELECT EXISTS" in sql:
            return FakeResult([(params[0] in self.intraday,)])
        if "max(session_date)" in sql:
            return FakeResult([(t, date(2026, 10, 27)) for t in sorted(self.intraday)])
        tickers, lo, hi = params
        return FakeResult(sorted({(d,) for t, d in self.daily if t in tickers and lo < d <= hi}))


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0]

    def fetchall(self):
        return self.rows


def test_a_new_index_is_not_loaded_and_the_stocks_and_funds_are():
    indexes = intraday_indexes(FakeConn({"IHSG", "BBCA"}, []), UNIVERSE)
    assert indexes == {"IHSG"}                                       # derived from the stored bars, not a list
    scope, refused = intraday_scope(UNIVERSE, indexes, set())
    assert [s.ticker for s in scope] == ["BBCA", "XIJI", "IHSG"] and refused == []


def test_naming_a_new_index_is_refused_and_naming_stocks_still_works():
    scope, refused = intraday_scope(UNIVERSE, {"IHSG"}, {"LQ45", "BBCA"})
    assert [s.ticker for s in scope] == ["BBCA"] and refused == ["LQ45"]
    scope, refused = intraday_scope(UNIVERSE, {"IHSG"}, {"IHSG", "BBCA"})     # the case where nothing is refused
    assert [s.ticker for s in scope] == ["BBCA", "IHSG"] and refused == []


def test_the_session_calendar_is_the_intraday_index_only():
    # LQ45 has a daily candle on 29 Oct that IHSG lacks: it must not count as a session behind
    daily = [("IHSG", date(2026, 10, 28)), ("IHSG", date(2026, 10, 30)), ("LQ45", date(2026, 10, 29)),
             ("LQ45", date(2026, 10, 30))]
    conn = FakeConn({"IHSG", "BBCA"}, daily)
    behind = sessions_behind(conn, UNIVERSE[:3], "1h", date(2026, 10, 31), {"IHSG"})
    assert behind == {"BBCA": 2, "XIJI": None, "IHSG": 2}
