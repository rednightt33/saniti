"""saniti.period_return: one boundary convention for named calendar-period returns.

base = the last valid value strictly before the range start; end = the last valid value on or before the range end,
observed inside the range; return = end / base - 1, never rounded. Boundary problems are statuses per entity, never a
silent substitution. The unit tests run the helper in-process over DuckDB views on Parquet files, the way a session
reads its bundle; the last test runs it in a real confined session."""
from __future__ import annotations

import math
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
YTD = {"range_id": "current_ytd", "start": "2026-01-01", "end": "2026-09-25", "extract_from": "2025-12-20",
       "extract_to": "2026-09-25"}


@pytest.fixture
def pr(tmp_path):
    """setup(frame, ranges=[YTD], quality=None, entity_column="ticker") -> the saniti_session module, configured with
    one data request "prices" (data_request_id g_A) whose only file holds frame."""
    sys.path.insert(0, str(RUNTIME))
    import saniti_session as s

    saved = (dict(s.REQUESTS), dict(s._BUNDLE), s._CONNECTION)
    counter = [0]

    def setup(frame: pd.DataFrame, ranges=None, quality=None, entity_column="ticker", time_column="date"):
        counter[0] += 1
        path = tmp_path / f"part_{counter[0]}.parquet"
        frame.to_parquet(path, index=False)
        request = {"data_request_id": "g_A", "logical_name": "prices", "source_table": "Price_Stock_Indonesia_IDX",
                   "columns": list(frame.columns), "entity_column": entity_column, "time_column": time_column,
                   "files": [str(path)], "ranges": ranges if ranges is not None else [YTD], "order_by": [],
                   "quality": quality or {}}
        s.REQUESTS.clear()
        s.REQUESTS["g_A"] = request
        s._ACCESS.clear()
        s._WARNINGS.clear()
        con = duckdb.connect()
        con.execute(f"CREATE VIEW prices AS {s._view_sql(request)}")
        s._CONNECTION = con
        return s

    yield setup
    s.REQUESTS.clear()
    s.REQUESTS.update(saved[0])
    s._BUNDLE.clear()
    s._BUNDLE.update(saved[1])
    s._CONNECTION = saved[2]


def prices(rows: list[tuple[str, str, float | None]]) -> pd.DataFrame:
    return pd.DataFrame([{"ticker": t, "date": date.fromisoformat(d), "close": c} for t, d, c in rows])


def row(table: pd.DataFrame, entity: str) -> dict:
    found = table[table["entity"] == entity]
    assert len(found) == 1, table
    return found.iloc[0].to_dict()


def test_a_normal_ytd_uses_the_last_close_before_the_start_and_keeps_full_precision(pr) -> None:
    s = pr(prices([("BBCA", "2025-12-30", 100.0), ("BBCA", "2025-12-31", 110.0), ("BBCA", "2026-01-02", 105.0),
                   ("BBCA", "2026-09-25", 121.0)]))
    table = s.period_return("prices", "current_ytd")
    assert list(table.columns) == ["entity", "base_date", "base_value", "end_date", "end_value", "return_decimal",
                                   "return_pct", "calculation_status", "range_id", "period_start", "period_end"]
    got = row(table, "BBCA")
    assert got["calculation_status"] == "COMPLETE"
    assert got["base_date"] == date(2025, 12, 31) and got["base_value"] == 110.0
    assert got["end_date"] == date(2026, 9, 25) and got["end_value"] == 121.0
    assert got["return_decimal"] == 121.0 / 110.0 - 1.0  # exactly, not rounded
    assert got["return_pct"] == (121.0 / 110.0 - 1.0) * 100.0
    assert got["period_start"] == date(2026, 1, 1) and got["period_end"] == date(2026, 9, 25)


def test_full_precision_is_retained(pr) -> None:
    s = pr(prices([("A", "2025-12-31", 3.0), ("A", "2026-03-02", 4.0)]))
    got = row(s.period_return("prices", "current_ytd"), "A")
    assert got["return_decimal"] == 4.0 / 3.0 - 1.0 and got["return_decimal"] != round(got["return_decimal"], 6)


def test_weekend_and_holiday_boundaries(pr) -> None:
    february = {"range_id": "feb", "start": "2026-02-01", "end": "2026-02-28", "extract_from": "2026-01-20",
                "extract_to": "2026-02-28"}  # starts on a Sunday, ends on a Saturday
    s = pr(prices([("A", "2026-01-29", 49.0), ("A", "2026-01-30", 50.0), ("A", "2026-02-02", 51.0),
                   ("A", "2026-02-27", 55.0)]), ranges=[february])
    got = row(s.period_return("prices", "feb"), "A")
    assert got["base_date"] == date(2026, 1, 30) and got["end_date"] == date(2026, 2, 27)
    assert got["return_decimal"] == 55.0 / 50.0 - 1.0


def test_an_observation_on_the_start_date_is_inside_the_period_not_the_base(pr) -> None:
    starts_on_a_trading_day = {**YTD, "range_id": "from_jan_2", "start": "2026-01-02", "extract_from": "2025-12-21"}
    s = pr(prices([("A", "2025-12-31", 100.0), ("A", "2026-01-02", 90.0), ("A", "2026-01-05", 99.0)]),
           ranges=[starts_on_a_trading_day])
    got = row(s.period_return("prices", "from_jan_2"), "A")
    assert got["base_date"] == date(2025, 12, 31) and got["base_value"] == 100.0
    assert got["end_value"] == 99.0


def test_the_end_is_the_last_valid_value_on_or_before_the_period_end(pr) -> None:
    with_future = {**YTD, "range_id": "q1", "start": "2026-01-01", "end": "2026-03-31", "extract_to": "2026-04-30"}
    s = pr(prices([("A", "2025-12-31", 100.0), ("A", "2026-03-30", 110.0), ("A", "2026-03-31", None),
                   ("A", "2026-04-01", 500.0)]), ranges=[with_future])
    got = row(s.period_return("prices", "q1"), "A")
    assert got["end_date"] == date(2026, 3, 30) and got["end_value"] == 110.0  # null on the end date skipped,
    assert got["return_decimal"] == 110.0 / 100.0 - 1.0                        # the row after the end ignored


def test_a_missing_previous_close_is_reported_and_never_replaced_by_the_first_value_in_the_period(pr) -> None:
    s = pr(prices([("NEWA", "2026-01-05", 200.0), ("NEWA", "2026-09-25", 260.0),
                   ("BBCA", "2025-12-31", 100.0), ("BBCA", "2026-09-25", 108.0)]))
    table = s.period_return("prices", "current_ytd")
    got = row(table, "NEWA")
    assert got["calculation_status"] == "NO_PRIOR_CLOSE"
    assert got["base_date"] is None and math.isnan(got["base_value"])
    assert math.isnan(got["return_decimal"]) and math.isnan(got["return_pct"])
    assert got["end_value"] == 260.0  # the end is still shown for diagnostics
    assert row(table, "BBCA")["calculation_status"] == "COMPLETE"
    warning = next(w for w in s._WARNINGS if w["code"] == "PERIOD_RETURN_EXCLUSIONS")
    assert "1 of 2" in warning["message"] and "NO_PRIOR_CLOSE" in warning["message"]


def test_a_missing_end_value_is_reported_and_the_base_is_not_reused_as_the_end(pr) -> None:
    s = pr(prices([("DLST", "2025-12-29", 70.0), ("DLST", "2025-12-30", 71.0)]))
    got = row(s.period_return("prices", "current_ytd"), "DLST")
    assert got["calculation_status"] == "NO_END_VALUE" and got["base_value"] == 71.0
    assert got["end_date"] is None and math.isnan(got["return_decimal"])


@pytest.mark.parametrize("base, status", [(0.0, "INVALID_BASE_VALUE"), (-5.0, "INVALID_BASE_VALUE")])
def test_a_zero_or_negative_base_is_invalid_and_never_divided(pr, base, status) -> None:
    s = pr(prices([("A", "2025-12-30", 10.0), ("A", "2025-12-31", base), ("A", "2026-02-02", 12.0)]))
    got = row(s.period_return("prices", "current_ytd"), "A")
    assert got["calculation_status"] == status and got["base_value"] == base  # the latest valid value, not skipped
    assert math.isnan(got["return_decimal"])


@pytest.mark.parametrize("latest", [None, float("inf"), float("nan")])
def test_a_null_or_non_finite_latest_value_is_not_a_base(pr, latest) -> None:
    s = pr(prices([("A", "2025-12-29", 80.0), ("A", "2025-12-31", latest), ("A", "2026-02-02", 88.0)]))
    got = row(s.period_return("prices", "current_ytd"), "A")
    assert got["calculation_status"] == "COMPLETE"
    assert got["base_date"] == date(2025, 12, 29) and got["base_value"] == 80.0
    assert got["return_decimal"] == 88.0 / 80.0 - 1.0


def test_an_entity_without_any_valid_value_is_insufficient(pr) -> None:
    s = pr(prices([("A", "2025-12-31", None), ("A", "2026-01-05", None), ("B", "2025-12-31", 1.0),
                   ("B", "2026-01-05", 2.0)]),
           quality={"empty_entities": ["ZZZZ"], "empty_entities_count": 1})
    table = s.period_return("prices", "current_ytd")
    assert row(table, "A")["calculation_status"] == "INSUFFICIENT_INPUT_DATA"
    assert row(table, "ZZZZ")["calculation_status"] == "INSUFFICIENT_INPUT_DATA"  # named by the scope, no data
    assert row(table, "B")["calculation_status"] == "COMPLETE"
    assert list(table["entity"]) == ["A", "B", "ZZZZ"]


def test_conflicting_duplicate_boundary_observations_are_never_picked(pr) -> None:
    s = pr(prices([("A", "2025-12-31", 100.0), ("A", "2025-12-31", 101.0), ("A", "2026-02-02", 110.0),
                   ("B", "2025-12-31", 100.0), ("B", "2026-02-02", 110.0), ("B", "2026-02-02", 111.0),
                   ("C", "2025-12-31", 100.0), ("C", "2025-12-31", 100.0), ("C", "2026-02-02", 110.0)]))
    table = s.period_return("prices", "current_ytd")
    a, b, c = row(table, "A"), row(table, "B"), row(table, "C")
    assert a["calculation_status"] == "DUPLICATE_BOUNDARY_OBSERVATION" and math.isnan(a["base_value"])
    assert b["calculation_status"] == "DUPLICATE_BOUNDARY_OBSERVATION" and math.isnan(b["end_value"])
    assert math.isnan(a["return_decimal"]) and math.isnan(b["return_decimal"])
    assert c["calculation_status"] == "COMPLETE" and c["return_decimal"] == 110.0 / 100.0 - 1.0  # identical: no conflict


def test_input_order_does_not_change_the_result_and_every_entity_gets_one_row(pr) -> None:
    rows = [("BBRI", "2025-12-30", 50.0), ("BBRI", "2025-12-31", 52.0), ("BBRI", "2026-09-25", 60.0),
            ("BBCA", "2025-12-31", 100.0), ("BBCA", "2026-04-01", 90.0), ("BBCA", "2026-09-24", 95.0),
            ("BMRI", "2026-03-01", 10.0)]
    ordered = pr(prices(rows)).period_return("prices", "current_ytd")
    shuffled = pr(prices(list(reversed(rows[3:])) + rows[:3])).period_return("prices", "current_ytd")
    pd.testing.assert_frame_equal(ordered, shuffled)
    assert list(ordered["entity"]) == ["BBCA", "BBRI", "BMRI"]
    assert list(ordered["calculation_status"]) == ["COMPLETE", "COMPLETE", "NO_PRIOR_CLOSE"]
    assert row(ordered, "BBCA")["end_date"] == date(2026, 9, 24)


def test_the_helper_reads_the_range_with_its_history_buffer_through_governed_access(pr) -> None:
    s = pr(prices([("A", "2025-12-31", 1.0), ("A", "2026-01-05", 2.0)]))
    s.period_return("prices", "current_ytd")
    assert s._ACCESS == [{"call": "range", "data_request_id": "g_A", "range_id": "current_ytd",
                          "include_buffers": True, "columns": ["ticker", "date", "close"], "rows": 2}]


@pytest.mark.parametrize("kwargs, message", [
    ({"range_id": "nope"}, "is not a range"),
    ({"value_column": "volume"}, "is not a column"),
    ({"date_column": "query_date"}, "must be the request's time column"),
    ({"value_column": "ticker"}, "three different columns"),
])
def test_arguments_are_validated(pr, kwargs, message) -> None:
    s = pr(prices([("A", "2025-12-31", 1.0), ("A", "2026-01-05", 2.0)]))
    arguments = {"range_id": "current_ytd", **kwargs}
    with pytest.raises(s.PeriodReturnError, match=message):
        s.period_return("prices", **arguments)


def test_a_non_numeric_value_column_and_missing_metadata_are_bounded_errors(pr) -> None:
    frame = prices([("A", "2025-12-31", 1.0), ("A", "2026-01-05", 2.0)]).assign(label=["x", "y"])
    s = pr(frame)
    with pytest.raises(s.PeriodReturnError, match="non-numeric"):
        s.period_return("prices", "current_ytd", value_column="label")
    s = pr(prices([("A", "2025-12-31", 1.0)]), entity_column=None)
    with pytest.raises(s.PeriodReturnError, match="no catalog entity column"):
        s.period_return("prices", "current_ytd")


def test_without_a_history_buffer_the_helper_refuses_instead_of_using_the_first_value_in_the_period(pr) -> None:
    no_buffer = {**YTD, "extract_from": "2026-01-01"}
    s = pr(prices([("A", "2026-01-02", 1.0), ("A", "2026-01-05", 2.0)]), ranges=[no_buffer])
    with pytest.raises(s.PeriodReturnError, match="history_buffer 1 TRADING_OBSERVATIONS"):
        s.period_return("prices", "current_ytd")
    assert s._ACCESS == []  # nothing was read


def test_decimal_values_are_read_as_numbers(pr) -> None:
    from decimal import Decimal

    frame = pd.DataFrame({"ticker": ["A", "A"], "date": [date(2025, 12, 31), date(2026, 1, 5)],
                          "close": [Decimal("6250.00"), Decimal("6500.00")]})
    got = row(pr(frame).period_return("prices", "current_ytd"), "A")
    assert got["calculation_status"] == "COMPLETE" and got["return_decimal"] == 6500.0 / 6250.0 - 1.0


# ---------------------------------------------------------------- in a real confined session

from conftest import requires_root  # noqa: E402
from test_dataneed_bundles import env  # noqa: E402,F401 - fixture
from test_dataneed_sessions import ok, session  # noqa: E402,F401 - fixture


@requires_root
def test_period_return_in_a_session_matches_an_independent_calculation(session) -> None:  # noqa: F811
    body = ok(session, "r = saniti.period_return('prices', 'current_ytd')\n"
                       "full = load('prices')\n"
                       "emit_table('period_return', r)\n"
                       "print(sorted(set(r['calculation_status'])), len(r))")
    assert "['COMPLETE'] 3" in body["stdout"], body
    check = ok(session, "import datetime as dt\n"
                        "rows = full.sort_values(['ticker', 'date'])\n"
                        "start, end = dt.date(2026, 1, 1), dt.date(2026, 9, 25)\n"
                        "for t, g in rows.groupby('ticker'):\n"
                        "    base = g[g['date'] < start].iloc[-1]['close']\n"
                        "    last = g[(g['date'] >= start) & (g['date'] <= end)].iloc[-1]['close']\n"
                        "    got = r[r['entity'] == t].iloc[0]['return_decimal']\n"
                        "    assert got == last / base - 1, (t, got, last / base - 1)\n"
                        "print('MATCH')")
    assert "MATCH" in check["stdout"]
    # the harness recorded the governed read of the range with its history buffer
    execution = session["dataneed"].store.executions_for(session["session_id"])[0]
    reads = [a for a in execution["access"] if a.get("call") == "range"]
    assert reads and reads[0]["range_id"] == "current_ytd" and reads[0]["include_buffers"] is True
