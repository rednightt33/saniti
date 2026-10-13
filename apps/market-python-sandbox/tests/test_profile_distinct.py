"""M147 (2026-10-13): the session dataset profile counts a date column's distinct values exactly. DuckDB's
approx_count_distinct read 19 trading dates (17 and 25 August 2026 are holidays) as 21, the weekday count of the month,
and the model spent turns reconciling the profile with the rows it loaded."""
from __future__ import annotations

import datetime as dt

import duckdb
import pandas as pd

from app.carried import profile

TRADING_DAYS = [3, 4, 5, 6, 7, 10, 11, 12, 13, 14, 18, 19, 20, 21, 24, 26, 27, 28, 31]


def parquet(tmp_path, per_day: int = 40) -> str:
    rows = [{"date": dt.date(2026, 8, day), "ticker": f"T{i:03d}", "board": "Regular", "net": float(i * day)}
            for day in TRADING_DAYS for i in range(per_day)]
    path = tmp_path / "flows.parquet"
    pd.DataFrame(rows).to_parquet(path)
    return str(path)


def test_the_estimate_this_replaces_reads_nineteen_dates_as_twenty_one(tmp_path) -> None:
    path = parquet(tmp_path)
    estimate, exact = duckdb.connect().execute(
        f"SELECT approx_count_distinct(date), count(DISTINCT date) FROM read_parquet('{path}')").fetchone()
    assert (estimate, exact) == (21, 19)  # the M147 reading, DuckDB 1.5.5


def test_a_date_column_counts_its_distinct_dates_exactly(tmp_path) -> None:
    result = profile([parquet(tmp_path)], time_column="date", entity_column="ticker")
    assert result["columns"]["date"]["distinct"] == 19
    assert result["columns"]["date"]["min"] == "2026-08-03" and result["columns"]["date"]["max"] == "2026-08-31"
    assert result["entities"] == 40 and result["rows"] == 19 * 40
    assert result["columns"]["ticker"]["distinct"] > 0 and result["columns"]["board"]["distinct"] == 1
