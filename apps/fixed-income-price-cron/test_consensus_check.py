"""EXEC-FI-DATE B (ERRORS M324, user go 2026-11-01): the weekly consensus check reports, never writes."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("consensus_check", HERE / "consensus_check.py")
cc = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cc
SPEC.loader.exec_module(cc)

D = lambda day: date(2026, 10, day)
A, B = (7.0, 7.1, 6.9, 7.0), (7.2, 7.3, 7.1, 7.2)


def test_a_stored_bar_equal_to_any_version_is_kept():
    # US10Y yield answers two histories by turn: the stored one is a source value even when two pulls give the other
    found = cc.compare_series({D(5): A}, [{D(5): B}, {D(5): A}, {D(5): B}], D(30))
    assert all(not days for days in found.values())


def test_revised_missing_extra_and_unstable():
    stored = {D(5): A, D(6): A, D(7): A, D(9): A}
    pulls = [{D(5): A, D(6): B, D(8): B, D(9): A}, {D(5): A, D(6): B, D(8): B, D(9): B}, {D(5): A, D(6): B, D(8): B}]
    found = cc.compare_series(stored, pulls, D(30))
    assert found == {"revised": [D(6)], "missing": [D(8)], "extra": [D(7)], "unstable": []}
    pulls[2][D(9)] = B                                   # D9 stored A, pulls A/B/B: kept (A is one of the versions)
    assert cc.compare_series(stored, pulls, D(30))["unstable"] == []
    stored[D(9)] = (1, 1, 1, 1)                           # unlike every version and the pulls disagree
    assert cc.compare_series(stored, pulls, D(30))["unstable"] == [D(9)]


def test_dates_outside_the_stored_history_and_after_the_last_session_are_not_checked():
    stored = {D(6): A}
    pulls = [{D(5): A, D(6): A, D(30): A}] * 3
    assert all(not days for days in cc.compare_series(stored, pulls, D(29)).values())


def test_a_stored_date_older_than_every_pull_is_not_called_extra():
    stored = {D(1): A, D(6): A}
    pulls = [{D(5): A, D(6): A}, {D(6): A}, {D(5): A, D(6): A}]
    assert cc.compare_series(stored, pulls, D(30))["extra"] == []


def test_summary_counts_and_lines_put_corrections_before_unstable():
    results = {"US10Y/yield_to_maturity": {"revised": [], "missing": [], "extra": [], "unstable": [D(5), D(6)]},
               "ID01Y/price": {"revised": [D(5)], "missing": [D(12)], "extra": [], "unstable": []}}
    report = cc.summarize("ID", results, ["ID30Y/price"], 22)
    assert (report["revised"], report["missing"], report["extra"], report["unstable"]) == (1, 1, 0, 2)
    assert [i["kind"] for i in report["items"]] == ["revised", "missing", "unstable"]
    assert report["items"][-1] == {"series": "US10Y/yield_to_maturity", "kind": "unstable", "count": 2,
                                   "first": "2026-10-05", "last": "2026-10-06"}
    assert report["failed_series"] == ["ID30Y/price"] and report["more_items"] == 0


def test_due_on_the_market_s_local_saturday():
    assert cc.due(ZoneInfo("America/New_York"), datetime(2026, 11, 8, 0, 0, tzinfo=timezone.utc))      # Sat 19:00 NY
    assert not cc.due(ZoneInfo("Asia/Jakarta"), datetime(2026, 11, 8, 0, 0, tzinfo=timezone.utc))      # Sun 07:00 WIB
    assert cc.due(ZoneInfo("Asia/Jakarta"), datetime(2026, 11, 7, 11, 0, tzinfo=timezone.utc))         # Sat 18:00 WIB


class FakeLoader:
    PRICE_TABLE = "public.\"Price_Fixed_Income\""
    TIMEFRAME = "1D"
    ZoneInfo = ZoneInfo

    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    def notify_telegram_monitor(self, execution_id, *, source_table, details):
        self.sent.append((execution_id, source_table, details))


def test_a_failed_check_is_reported_with_its_error_class():
    loader = FakeLoader()

    def connect(_url):
        raise ConnectionError("database down")

    now = datetime(2026, 11, 7, 11, 0, tzinfo=timezone.utc)
    details = cc.run(loader, "postgresql://x", "ID", now, manual=False, connect=connect)
    assert details["error"] == "ConnectionError" and details["market"] == "ID"
    [(run_id, table, sent)] = loader.sent
    assert run_id == "fi-consensus-ID-2026-11-07-1100" and table == "Fixed_Income_Consensus_Check"
    assert sent["run_time"] == "2026-11-07 18:00" and sent["pulls"] == 3
