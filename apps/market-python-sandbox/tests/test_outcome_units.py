"""S3 (P27) and S5 (M72), PLAN_FINAL_2026-10-04.md Fase 3: the outcome unit is checked by recomputing sampled rows
from the loaded prices (never by a scale rule alone), and a row whose condition cannot be evaluated is neither event
nor baseline. In-process over DuckDB views on Parquet files, the way a session reads its bundle."""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "runtime"
YTD = {"range_id": "r1", "start": "2024-01-01", "end": "2024-12-31", "extract_from": "2023-12-01",
       "extract_to": "2024-12-31"}


@pytest.fixture
def session(tmp_path):
    sys.path.insert(0, str(RUNTIME))
    import saniti_session as s

    saved = (dict(s.REQUESTS), s._CONNECTION, dict(s._FINDINGS_V1))

    def setup(frame: pd.DataFrame, entity_column="ticker", findings=None):
        path = tmp_path / "part.parquet"
        frame.to_parquet(path, index=False)
        request = {"data_request_id": "g_A", "logical_name": "prices", "source_table": "Price_Stock_Indonesia_IDX",
                   "columns": list(frame.columns), "entity_column": entity_column, "time_column": "date",
                   "files": [str(path)], "ranges": [YTD], "order_by": [], "quality": {}}
        s.REQUESTS.clear()
        s.REQUESTS["g_A"] = request
        con = duckdb.connect()
        con.execute(f"CREATE VIEW prices AS {s._view_sql(request)}")
        s._CONNECTION = con
        s._FINDINGS_V1.clear()
        s._FINDINGS_V1.update(findings or {})
        return s

    yield setup
    s.REQUESTS.clear()
    s.REQUESTS.update(saved[0])
    s._CONNECTION = saved[1]
    s._FINDINGS_V1.clear()
    s._FINDINGS_V1.update(saved[2])


def price_panel(tickers=("BBCA", "BBRI", "BMRI"), days=120, flat=()):
    rng = np.random.default_rng(7)
    rows = []
    for ticker in tickers:
        close = 1000.0
        for i in range(days):
            if ticker not in flat:
                close *= 1 + rng.normal(0, 0.02)
            rows.append({"ticker": ticker, "date": date(2024, 1, 1) + timedelta(days=i), "close": round(close, 4),
                         "volume": float(rng.integers(1, 10_000))})
    return pd.DataFrame(rows)


def outcomes(panel: pd.DataFrame, horizon: int, scale: float, name="ticker") -> pd.DataFrame:
    work = panel.sort_values(["ticker", "date"]).copy()
    work["fwd"] = (work.groupby("ticker")["close"].shift(-horizon) / work["close"] - 1) * scale
    return work.dropna(subset=["fwd"]).rename(columns={"ticker": name})[[name, "date", "fwd"]]


@pytest.mark.parametrize("horizon", [1, 5, 20])
def test_a_fraction_under_a_percent_plan_is_found(session, horizon) -> None:
    """g5.6: close.shift(-5)/close - 1 recorded under PERCENT."""
    panel = price_panel()
    s = session(panel)
    check = s.outcome_unit_check(outcomes(panel, horizon, 1.0), "fwd", "date", [horizon], "PERCENT")
    assert check["status"] == "MISMATCH" and check["observed_unit"] == "DECIMAL" and check["price_column"] == "close"
    assert "multiply it by 100" in check["message"]


@pytest.mark.parametrize("horizon", [1, 5, 20])
def test_a_percent_outcome_under_a_percent_plan_passes(session, horizon) -> None:
    panel = price_panel()
    s = session(panel)
    check = s.outcome_unit_check(outcomes(panel, horizon, 100.0), "fwd", "date", [horizon], "PERCENT")
    assert check["status"] == "CHECKED" and check["horizon"] == horizon


def test_a_percent_outcome_under_a_decimal_plan_is_found(session) -> None:
    panel = price_panel()
    s = session(panel)
    check = s.outcome_unit_check(outcomes(panel, 5, 100.0), "fwd", "date", [5], "DECIMAL")
    assert check["status"] == "MISMATCH" and "divide it by 100" in check["message"]


def test_a_dormant_stock_is_not_misjudged(session) -> None:
    """A stock whose price never moves has no usable rows; the others decide."""
    panel = price_panel(tickers=("BBCA", "BBRI", "SLEEP"), flat=("SLEEP",))
    s = session(panel)
    assert s.outcome_unit_check(outcomes(panel, 5, 100.0), "fwd", "date", [5], "PERCENT")["status"] == "CHECKED"
    only_flat = outcomes(panel[panel["ticker"] == "SLEEP"], 5, 100.0)
    assert s.outcome_unit_check(only_flat, "fwd", "date", [5], "PERCENT")["status"] == "NOT_CHECKED"


def test_the_entity_column_is_found_by_its_values_not_its_name(session) -> None:
    panel = price_panel()
    s = session(panel)
    check = s.outcome_unit_check(outcomes(panel, 5, 1.0, name="kode"), "fwd", "date", [5], "PERCENT")
    assert check["status"] == "MISMATCH"


def test_an_outcome_that_is_no_return_of_a_loaded_column_is_declared_not_checked(session) -> None:
    panel = price_panel()
    s = session(panel)
    other = outcomes(panel, 5, 100.0)
    other["fwd"] = np.random.default_rng(1).normal(0, 3, len(other))
    assert s.outcome_unit_check(other, "fwd", "date", [5], "PERCENT")["status"] == "NOT_CHECKED"


def test_a_log_return_still_reads_as_its_unit(session) -> None:
    panel = price_panel()
    s = session(panel)
    frame = outcomes(panel, 1, 1.0)
    frame["fwd"] = np.log1p(frame["fwd"]) * 100
    assert s.outcome_unit_check(frame, "fwd", "date", [1], "PERCENT")["status"] == "CHECKED"


def test_forward_return_uses_the_approved_unit(session) -> None:
    panel = price_panel()
    s = session(panel, findings={"outcome_unit": "PERCENT"})
    got = s.forward_return(panel, 5, value_column="close", entity_column="ticker", date_column="date")
    expected = outcomes(panel, 5, 100.0).set_index(["ticker", "date"])["fwd"]
    joined = panel.assign(got=got).dropna(subset=["got"]).set_index(["ticker", "date"])["got"]
    assert np.allclose(joined.loc[expected.index], expected)
    s = session(panel, findings={"outcome_unit": "DECIMAL"})
    assert s.forward_return(panel[panel["ticker"] == "BBCA"]["close"], 1).dropna().abs().max() < 1


def rsi_frames(panel: pd.DataFrame, negated_nan: bool):
    """The g6_revise pattern: the indicator is missing during its warm-up; the baseline is the negated condition."""
    work = outcomes(panel, 1, 100.0).merge(panel, on=["ticker", "date"])
    work["rsi14"] = work.groupby("ticker")["close"].transform(lambda c: c.rolling(14).mean())
    events = work[work["rsi14"] < work["rsi14"].median()]
    base = work[(work["rsi14"] >= work["rsi14"].median()) | work["rsi14"].isna()] if negated_nan \
        else work[work["rsi14"] >= work["rsi14"].median()]
    return events, base


def test_warm_up_rows_without_the_indicator_leave_the_baseline(session) -> None:
    panel = price_panel()
    s = session(panel)
    events, base = rsi_frames(panel, negated_nan=True)
    e2, b2, report = s._undefined_condition(events, base, "fwd", "date", None, {"fwd", "date"})
    assert report["columns"] == ["rsi14"] and report["BASELINE"] == 3 * 13 and report["CONDITION"] == 0
    clean_e, clean_b = rsi_frames(panel, negated_nan=False)
    assert len(b2) == len(clean_b) and len(e2) == len(clean_e)


def test_a_gap_in_the_middle_and_an_explicit_condition_column(session) -> None:
    panel = price_panel()
    s = session(panel)
    events, base = rsi_frames(panel, negated_nan=False)
    base = base.copy()
    base.loc[base.index[10:15], "rsi14"] = np.nan  # a gap inside the period
    _, b2, report = s._undefined_condition(events, base, "fwd", "date", ["rsi14"], {"fwd", "date"})
    assert report["BASELINE"] == 5 and len(b2) == len(base) - 5
    with pytest.raises(s.SanitiError):
        s._undefined_condition(events, base, "fwd", "date", ["missing_col"], {"fwd", "date"})


def test_a_column_missing_in_both_groups_is_not_taken_for_a_condition(session) -> None:
    """Data gaps unrelated to the condition (missing in both groups alike) are not dropped without being named."""
    panel = price_panel()
    s = session(panel)
    events, base = rsi_frames(panel, negated_nan=False)
    events, base = events.copy(), base.copy()
    events.loc[events.index[:3], "volume"] = np.nan
    base.loc[base.index[:3], "volume"] = np.nan
    _, _, report = s._undefined_condition(events, base, "fwd", "date", None, {"fwd", "date"})
    assert report["columns"] == [] and report["BASELINE"] == 0


def test_an_outcome_missing_at_the_end_of_the_period_is_not_a_row(session) -> None:
    """The last rows have no forward return; aggregate counts only rows with an outcome."""
    sys.path.insert(0, str(RUNTIME))
    import research_stats

    panel = price_panel()
    session(panel)
    work = panel.sort_values(["ticker", "date"]).copy()
    work["fwd"] = (work.groupby("ticker")["close"].shift(-5) / work["close"] - 1) * 100  # 5 missing per ticker
    events, base = work[work["volume"] > 5000], work[work["volume"] <= 5000]
    table = research_stats.aggregate(events, base, "fwd", "date")
    assert int(table["n"].sum()) == int(work["fwd"].notna().sum())
