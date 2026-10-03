"""D1 (round 2026-10-03): per-column statistics of every governed dataset (nulls, min / median / max, distinct
counts, entities with gaps against the dataset's own calendar), shown compactly with the bundle and in full through
inspect_session(dataset=...), never with row values."""
from __future__ import annotations

from datetime import date

import duckdb
import pandas as pd

from app.bundles import VIEW_COLUMNS, column_stats
from conftest import requires_root
from runtime.profiler import Profiler
from test_dataneed_bundles import (HEADERS, TICKERS, approve, build, env, price_rows, window_of,  # noqa: F401
                                   ytd_parts)


def profile(tmp_path, frame: pd.DataFrame, columns: list[str], start: str, end: str, frequency: str) -> dict:
    path = tmp_path / "part.parquet"
    frame.to_parquet(path)
    request = {"data_request_id": "r1", "logical_name": "series", "entity_column": "entity", "time_column": "date",
               "columns": columns, "key_columns": ["entity", "date"], "source_frequency": frequency,
               "files": [{"path": str(path), "partition_id": "p1", "window": {"from": start, "to": end}}],
               "ranges": [{"range_id": "full", "start": start, "end": end, "extract_from": start, "extract_to": end}]}
    return Profiler(duckdb.connect(":memory:"), "2026-09-30").profile(request)


def test_numbers_dates_and_text_get_their_own_statistics(tmp_path) -> None:
    days = pd.bdate_range("2026-09-01", "2026-09-30")
    frame = pd.DataFrame([{"entity": e, "date": d.date(), "close": 100.0 + i, "board": "Regular"}
                          for e in ("BBCA", "BMRI") for i, d in enumerate(days) if not (e == "BMRI" and i == 3)])
    frame.loc[0, "close"] = None
    result = profile(tmp_path, frame, ["entity", "date", "close", "board"], "2026-09-01", "2026-09-30", "1D")
    stats = {c["name"]: c for c in result["columns"]}
    assert stats["close"]["nulls"] == 1 and stats["close"]["min"] == 100 and stats["close"]["max"] == 121
    assert stats["close"]["median"] is not None
    assert stats["date"] == {"name": "date", "type": "DATE", "nulls": 0, "min": "2026-09-01", "max": "2026-09-30"}
    assert stats["board"]["distinct"] == 1 and stats["entity"]["distinct"] == 2
    assert result["entities_with_gaps"] == 1  # BMRI misses a day of the dataset's own calendar


def test_a_monthly_series_is_not_a_series_with_gaps(tmp_path) -> None:
    """Another frequency than the observed case (macro or cross-asset data): month ends are its whole calendar."""
    months = pd.date_range("2025-01-31", "2026-08-31", freq="ME")
    frame = pd.DataFrame([{"entity": "CPI_ID", "date": d.date(), "value": 2.0 + i / 10}
                          for i, d in enumerate(months)])
    result = profile(tmp_path, frame, ["entity", "date", "value"], "2025-01-01", "2026-08-31", "1M")
    assert result["entities_with_gaps"] == 0
    assert {c["name"]: c for c in result["columns"]}["value"]["max"] == 3.9


def test_the_bundle_view_shows_at_most_thirty_columns() -> None:
    quality = {"columns": [{"name": f"c{i}", "type": "DOUBLE", "nulls": 0, "min": 0, "median": 1, "max": 2}
                           for i in range(40)], "entities_with_gaps": 2}
    shown = column_stats(quality)
    assert len(shown["column_stats"]) == VIEW_COLUMNS and shown["columns_not_shown"] == 10
    assert shown["entities_with_gaps"] == 2
    assert len(column_stats(quality, None)["column_stats"]) == 40 and "columns_not_shown" not in column_stats(
        quality, None)


@requires_root
def test_the_bundle_and_inspect_session_carry_the_statistics(env) -> None:  # noqa: F811
    need = approve(env)
    current = window_of(need, "data_request_1_A", "current_ytd")
    frame = price_rows(TICKERS, current["from"], current["to"], skip={"BBRI": {"2026-03-04"}})
    view = build(env, need, ytd_parts(env, need, current_frame=frame)).json()
    assert view["status"] == "READY", view
    prices_view = next(d for d in view["datasets"] if d["logical_name"] == "prices")
    stats = {c["name"]: c for c in prices_view["column_stats"]}
    assert stats["close"]["min"] <= stats["close"]["median"] <= stats["close"]["max"]
    assert prices_view["entities_with_gaps"] == 1
    session = env["api"].post("/v1/sessions", json={"request_id": "req_bundle_1",
                                                    "bundle_id": view["input_bundle_id"]}, headers=HEADERS).json()
    inspected = env["api"].post(f"/v1/sessions/{session['session_id']}/inspect", headers=HEADERS,
                                json={"request_id": "req_bundle_1", "dataset": "prices"}).json()
    assert inspected["dataset"] == "prices" and inspected["entities_with_gaps"] == 1
    assert {c["name"] for c in inspected["column_stats"]} >= {"ticker", "date", "close"}
    assert "rows" not in str(inspected.get("column_stats"))  # statistics only, no row values
    missing = env["api"].post(f"/v1/sessions/{session['session_id']}/inspect", headers=HEADERS,
                              json={"request_id": "req_bundle_1", "dataset": "nope"})
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "DATASET_NOT_FOUND"
    assert date.fromisoformat(stats["date"]["max"]) <= date(2026, 9, 25)


@requires_root
def test_a_bundle_records_its_governor_queries_and_shows_its_lineage(env) -> None:  # noqa: F811
    """D3: the lineage of a bundle for its own request, and nothing for another request without the conversation."""
    need = approve(env)
    view = build(env, need, ytd_parts(env, need)).json()
    bundle_id = view["input_bundle_id"]
    lineage = env["api"].get(f"/v1/bundles/{bundle_id}/lineage", params={"request_id": "req_bundle_1"},
                             headers=HEADERS)
    assert lineage.status_code == 200, lineage.text
    body = lineage.json()
    prices_lineage = next(d for d in body["datasets"] if d["logical_name"] == "prices")
    assert prices_lineage["source_table"] == "Price_Stock_Indonesia_IDX"
    assert prices_lineage["governor"][0]["query_id"] == "qry_test"
    assert prices_lineage["governor"][0]["query_hash"] == "q" * 64
    assert prices_lineage["ranges"][0]["actual_end"]
    assert body["relationships"] and "file" not in str(body)
    other = env["api"].get(f"/v1/bundles/{bundle_id}/lineage", params={"request_id": "req_other"}, headers=HEADERS)
    assert other.status_code == 404 and other.json()["error"]["code"] == "BUNDLE_NOT_FOUND"
