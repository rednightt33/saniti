"""IP1 Stages D and E (golden tests on synthetic data): time_basis in data_need_spec/v2 (HISTORICAL_DESCRIPTIVE by
default, POINT_IN_TIME opt-in and refused where history is insufficient), the CURRENT_STATE disclosure, the history
coverage of EFFECTIVE_DATED relationships, and saniti.join's point-in-time version choice on a bitemporal history
(pit_valid_from <= date < pit_valid_to, the same rule as the SQL Governor's restriction)."""
from __future__ import annotations

import copy
import importlib.util
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.data_need import data_contract_sha256, validate
from conftest import SOURCE_CONTRACTS, _catalog_table, _columns, _contract
from dataneed_fixtures import classification, current_state, data_need_catalog, prices, subset, ytd_spec

REF = date(2026, 10, 30)
HISTORY_FROM = "2026-09-29"
SOURCE_CONTRACTS.setdefault("IDX_Stock_Universe_History", _contract("IDX_Stock_Universe_History", ["history_id"],
                                                                    "Ticker", None))


def catalog(history_from: str | None = HISTORY_FROM, metadata: bool = True) -> dict:
    cat = data_need_catalog()
    cat["tables"]["IDX_Stock_Universe_History"] = _catalog_table(SOURCE_CONTRACTS["IDX_Stock_Universe_History"],
                                                                 "Synthetic reference history.")
    cat["columns"]["IDX_Stock_Universe_History"] = _columns({
        "history_id": ("bigint", True, True), "Ticker": ("text", True, True), "Sector": ("text", True, True),
        "pit_valid_from": ("date", True, True), "pit_valid_to": ("date", True, True)})
    cat["columns"]["Feature_01_Stock_Daily"]["sector"] = _columns({"sector": ("text", True, True)})["sector"]
    for table, info in cat["columns"].items():
        for name, column in info.items():
            column.setdefault("resample_aggregation", None)
            column["value_time_basis"] = "CURRENT_STATE" if table in ("IDX_Stock_Universe", "IDX_Broker_Profile") \
                or (table, name) == ("Feature_01_Stock_Daily", "sector") else "HISTORICAL"
    status = {"IDX_Stock_Universe": "UNAVAILABLE", "IDX_Broker_Profile": "UNAVAILABLE"}
    for name, meta in cat["tables"].items():
        meta["availability"] = {"observation_date_column": meta.get("time_column"), "data_available_at_column": None,
                                "availability_rule": "x", "point_in_time_status": status.get(name, "PARTIAL"),
                                "historical_metadata_method": "x"}
    cat["relationships"].append(
        {"relationship_id": 40, "left_table": "Price_Stock_Indonesia_IDX", "left_columns": ["ticker"],
         "right_table": "IDX_Stock_Universe_History", "right_columns": ["Ticker"], "relationship_type": "MANY_TO_ONE",
         "temporal_rule": "Point in time", "safe_output_grain": "date x ticker", "requires_preaggregation": False,
         "is_allowed": True, "version": "v1", "supported_join_semantics": ["EFFECTIVE_DATED"],
         "left_time_column": None, "right_time_column": None, "effective_from_column": "pit_valid_from",
         "effective_to_column": "pit_valid_to", "history_available_from": history_from})
    if metadata:
        cat["point_in_time_metadata"] = True
    else:
        for meta in cat["tables"].values():
            meta.pop("availability")
    return cat


def run(spec: dict, cat: dict | None = None):
    cat = cat or catalog()
    return validate(spec, subset(cat, [r["source_table"] for r in spec["data_requests"]]), REF)


def codes(outcome) -> list[str]:
    return [i["code"] for i in outcome.issues]


def window(start: str, end: str, buffer=None) -> dict:
    return {"time_ranges": [{"range_id": "window", "start": start, "end": end}], "history_buffer": buffer}


def history(rid: str = "data_request_1_B", **overrides) -> dict:
    return classification(rid, source_table="IDX_Stock_Universe_History", logical_name="sector_history",
                          columns=["Ticker", "Sector", "pit_valid_from", "pit_valid_to"],
                          scope={"type": "PREDICATE", "column": "Sector", "operator": "EQ",
                                 "value": "Non-Energy Minerals"}, **overrides)


def v2(rel: dict) -> dict:
    """The data_need_spec/v2 key form of a single-key relationship."""
    rel = dict(rel)
    rel["left_columns"], rel["right_columns"] = [rel.pop("left_column")], [rel.pop("right_column")]
    return rel


def effective(**overrides) -> dict:
    rel = v2(current_state(relationship_id=40, left_column="ticker", right_column="Ticker",
                           join_semantics="EFFECTIVE_DATED", effective_from_column="pit_valid_from",
                           effective_to_column="pit_valid_to"))
    rel.update(overrides)
    return rel


def pit_spec(time_basis: str | None = "POINT_IN_TIME", start: str = "2026-10-01", **overrides) -> dict:
    spec = ytd_spec(spec_version="data_need_spec/v2",
                    data_requests=[prices(**window(start, "2026-10-20")), history()], relationships=[effective()])
    if time_basis is not None:
        spec["time_basis"] = time_basis
    spec.update(overrides)
    return spec


# ------------------------------------------------------------------------------------------ the contract

def test_time_basis_is_a_v2_field_with_two_values() -> None:
    v1 = ytd_spec(time_basis="POINT_IN_TIME")
    assert "UNKNOWN_FIELD" in codes(run(v1))
    assert "INVALID_FIELD_VALUE" in codes(run(pit_spec("AS_KNOWN")))


def test_point_in_time_is_approved_on_history_it_covers_and_travels_with_the_need() -> None:
    outcome = run(pit_spec())
    assert outcome.status == "APPROVED", outcome.issues
    assert outcome.approved["time_basis"] == "POINT_IN_TIME"
    request = outcome.approved["requests"]["data_request_1_A"]
    assert request["availability"]["point_in_time_status"] == "PARTIAL"
    descriptive = run(pit_spec(None))
    assert descriptive.status == "APPROVED" and descriptive.approved["time_basis"] == "HISTORICAL_DESCRIPTIVE"
    # a point-in-time need never reuses descriptive data; the descriptive hash is the one before Stage D
    assert data_contract_sha256(outcome.approved) != data_contract_sha256(descriptive.approved)
    legacy = {k: v for k, v in descriptive.approved.items() if k != "time_basis"}
    assert data_contract_sha256(legacy) == data_contract_sha256(descriptive.approved)


def test_history_not_available_is_never_a_silent_fallback() -> None:
    # the window reads dates before the first recorded version: refused in both modes (never an empty join)
    for basis in ("POINT_IN_TIME", None):
        outcome = run(pit_spec(basis, start="2026-09-01"))
        assert outcome.status == "REVISION_REQUIRED" and codes(outcome) == ["POINT_IN_TIME_UNAVAILABLE"]
        assert "2026-09-29" in outcome.issues[0]["rejected_value"]
    # a history buffer that reaches before the history is refused too
    buffered = pit_spec(data_requests=[prices(**window("2026-10-01", "2026-10-20",
                                                       {"value": 20, "unit": "TRADING_OBSERVATIONS"})), history()])
    assert codes(run(buffered)) == ["POINT_IN_TIME_UNAVAILABLE"]
    empty = run(pit_spec(), catalog(history_from=None))
    assert codes(empty) == ["POINT_IN_TIME_UNAVAILABLE"] and "no date yet" in empty.issues[0]["rejected_value"]


def test_point_in_time_refuses_current_state_relationships_tables_and_columns() -> None:
    universe = ytd_spec(spec_version="data_need_spec/v2", time_basis="POINT_IN_TIME",
                        data_requests=[prices(**window("2026-10-01", "2026-10-20")), classification()],
                        relationships=[v2(current_state())])
    outcome = run(universe)
    assert outcome.status == "REVISION_REQUIRED"
    paths = {(i["code"], i["field_path"]) for i in outcome.issues}
    assert ("POINT_IN_TIME_UNAVAILABLE", "relationships[0].join_semantics") in paths
    assert ("POINT_IN_TIME_UNAVAILABLE", "data_requests[1].source_table") in paths
    # descriptive mode keeps the current-state join, with the disclosure warning
    descriptive = run({**universe, "time_basis": "HISTORICAL_DESCRIPTIVE"})
    assert descriptive.status == "APPROVED"
    assert "HISTORICAL_REFERENCE_USES_CURRENT_STATE" in [w["code"] for w in descriptive.warnings]


def test_a_current_state_column_is_refused_point_in_time_and_disclosed_otherwise() -> None:
    f01 = {**prices(**window("2026-10-01", "2026-10-20")), "source_table": "Feature_01_Stock_Daily",
           "logical_name": "features", "columns": ["ticker", "date", "return_20d_pct", "sector"],
           "ordering": []}
    spec = ytd_spec(spec_version="data_need_spec/v2", time_basis="POINT_IN_TIME", data_requests=[f01],
                    relationships=[], subject={"data_domain": "MARKET", "entity_type": "STOCK",
                                               "asset_type": "IDX_EQUITY"})
    outcome = run(spec)
    assert [(i["code"], i["field_path"]) for i in outcome.issues] == [
        ("POINT_IN_TIME_UNAVAILABLE", "data_requests[0].columns[3]")]
    filtered = copy.deepcopy(spec)
    filtered["data_requests"][0].update(columns=["ticker", "date", "return_20d_pct"],
                                        scope={"type": "PREDICATE", "column": "sector", "operator": "EQ",
                                               "value": "Finance"})
    assert [i["field_path"] for i in run(filtered).issues] == ["data_requests[0].scope.column"]
    described = run({**spec, "time_basis": "HISTORICAL_DESCRIPTIVE"})
    assert described.status == "APPROVED"
    warning = [w for w in described.warnings if w["code"] == "CURRENT_STATE_COLUMN"]
    assert warning and warning[0]["columns"] == ["sector"]


def test_point_in_time_fails_closed_without_catalog_metadata() -> None:
    outcome = run(pit_spec(), catalog(metadata=False))
    assert codes(outcome) == ["POINT_IN_TIME_UNAVAILABLE"] and outcome.issues[0]["field_path"] == "time_basis"


# --------------------------------------------------------------------------- saniti.join (golden, IP1 E)

def runtime():
    path = Path(__file__).resolve().parents[1] / "runtime" / "saniti_session.py"
    spec = importlib.util.spec_from_file_location("saniti_session_pit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._BUNDLE.clear()
    module._BUNDLE.update({"relationships": [
        {"relationship_id": 40, "left_request_id": "p", "right_request_id": "h", "join_type": "INNER",
         "join_semantics": "EFFECTIVE_DATED", "left_column": "ticker", "right_column": "Ticker",
         "left_time_column": "date", "right_time_column": None, "relationship_type": "MANY_TO_ONE",
         "effective_from_column": "pit_valid_from", "effective_to_column": "pit_valid_to",
         "requires_preaggregation": False}]})
    module.REQUESTS.clear()
    module.REQUESTS.update({"p": {"data_request_id": "p", "logical_name": "prices", "time_column": "date"},
                            "h": {"data_request_id": "h", "logical_name": "sector_history", "time_column": None}})
    return module


def sector_history() -> pd.DataFrame:
    """ANTM: Mining from the first capture (2026-10-01, used from 10-02), recorded as Finance on 10-10 (used from
    10-11). The superseded open-ended Mining knowledge row applies to no date after the change (empty interval), and a
    same-day revision left an inverted row; BBCA: Finance throughout."""
    rows = [
        (1, "ANTM", "Non-Energy Minerals", "2026-10-02", "2026-10-11"),  # superseded knowledge, closed by recording
        (2, "ANTM", "Non-Energy Minerals", "2026-10-11", "2026-10-11"),  # closed copy recorded 10-10: empty
        (3, "ANTM", "Finance", "2026-10-11", None),
        (4, "ANTM", "Energy Minerals X", "2026-10-02", "2026-10-02"),    # same-day revision on the first day
        (5, "BBCA", "Finance", "2026-10-02", None)]
    frame = pd.DataFrame(rows, columns=["history_id", "Ticker", "Sector", "pit_valid_from", "pit_valid_to"])
    for column in ("pit_valid_from", "pit_valid_to"):
        frame[column] = pd.to_datetime(frame[column]).dt.date
    return frame


def daily_prices() -> pd.DataFrame:
    days = pd.date_range("2026-10-01", "2026-10-15", freq="D").date
    return pd.DataFrame([{"ticker": t, "date": d, "close": 1.0} for t in ("ANTM", "BBCA") for d in days])


def sql_rule(left: pd.DataFrame, right: pd.DataFrame) -> set[tuple[str, date]]:
    """The SQL Governor's EFFECTIVE_DATED restriction (pit_valid_from <= date AND (to IS NULL OR date < to))."""
    kept = set()
    for row in left.itertuples():
        versions = right[(right["Ticker"] == row.ticker) & (right["pit_valid_from"] <= row.date)
                         & (right["pit_valid_to"].isna() | (row.date < right["pit_valid_to"].fillna(date.max)))]
        if len(versions):
            kept.add((row.ticker, row.date))
    return kept


def test_a_sector_move_does_not_carry_the_old_mining_version() -> None:
    saniti = runtime()
    mining = sector_history()[sector_history()["Sector"] == "Non-Energy Minerals"]  # the reference scope, first
    out = saniti.join(40, daily_prices(), mining)
    assert set(out["ticker"]) == {"ANTM"}
    assert min(out["date"]) == date(2026, 10, 2) and max(out["date"]) == date(2026, 10, 10)
    # the same entities and dates as the Governor's SQL restriction
    assert {(t, d) for t, d in zip(out["ticker"], out["date"])} == sql_rule(daily_prices(), mining)


def test_each_date_gets_the_version_recorded_before_it() -> None:
    saniti = runtime()
    out = saniti.join(40, daily_prices(), sector_history(), how="left")
    by_date = {(r["ticker"], r["date"]): (r["Sector"] if r["_saniti_match"] == "matched" else None)
               for r in out.to_dict("records")}
    assert by_date[("ANTM", date(2026, 10, 1))] is None  # before the first recorded version: nothing is known
    assert by_date[("ANTM", date(2026, 10, 10))] == "Non-Energy Minerals"  # recorded 10-10, used from 10-11
    assert by_date[("ANTM", date(2026, 10, 11))] == "Finance"
    assert len(out) == len(daily_prices())  # one version per ticker and date, no duplicate from empty rows
    matched = {k for k, v in by_date.items() if v is not None}
    assert matched == sql_rule(daily_prices(), sector_history())


def test_a_version_that_started_before_the_window_is_still_used() -> None:
    saniti = runtime()
    window_prices = daily_prices()[daily_prices()["date"] >= date(2026, 10, 12)]
    out = saniti.join(40, window_prices, sector_history())
    assert set(out.loc[out["ticker"] == "BBCA", "Sector"]) == {"Finance"}  # BBCA's version began 10-02


def test_overlapping_versions_are_refused() -> None:
    saniti = runtime()
    broken = pd.concat([sector_history(), pd.DataFrame([{"history_id": 9, "Ticker": "BBCA", "Sector": "Banks",
                                                         "pit_valid_from": date(2026, 10, 5),
                                                         "pit_valid_to": date(2026, 10, 7)}])])
    with pytest.raises(saniti.JoinCardinalityError, match="non-overlapping"):
        saniti.join(40, daily_prices(), broken)
