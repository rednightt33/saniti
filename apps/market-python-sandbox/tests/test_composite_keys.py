"""IP1 Stages B and C (golden tests on synthetic data): composite-key relationships through the DataNeed contract
(data_need_spec/v2 with left_columns / right_columns; v1 still read), the canonical key form, relationships that
need preaggregation, and the session helpers saniti.join (every key pair, cardinality checks, unmatched rows) and
saniti.preaggregate (catalog cross-entity rules, grain and totals)."""
from __future__ import annotations

import copy
import importlib.util
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.data_need import data_contract_sha256, validate
from conftest import _catalog_table, _columns, SOURCE_CONTRACTS
from dataneed_fixtures import current_state, data_need_catalog, prices, subset, ytd_spec

REF = date(2026, 9, 25)
BS_KEYS = ["Symbol", "Broker", "Investor Type", "Market Board"]
F02_KEYS = ["ticker", "broker", "investor_type", "market_board"]


def catalog() -> dict:
    cat = data_need_catalog()
    for name in ("IDX_Broker_Summary", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily"):
        cat["tables"][name] = _catalog_table(SOURCE_CONTRACTS[name], "Synthetic broker table.")
    cat["columns"]["IDX_Broker_Summary"] = _columns({
        "Date": ("date", True, True), "Symbol": ("text", True, True), "Broker": ("text", True, True),
        "Investor Type": ("text", True, True), "Market Board": ("text", True, True),
        "Buy Value": ("numeric", True, False)})
    cat["columns"]["Feature_02_Broker_Rolling"].update(_columns({"net_value_1d": ("numeric", True, False),
                                                                 "net_value_percentile_20d": ("double precision",
                                                                                              True, False)}))
    cat["columns"]["Feature_03_Stock_Broker_Daily"] = _columns({
        "ticker": ("text", True, True), "market_board": ("text", True, True), "date": ("date", True, True),
        "domestic_net_value": ("numeric", True, False)})
    for table in ("IDX_Broker_Summary", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily"):
        for column in cat["columns"][table].values():
            column.setdefault("resample_aggregation", None)
    cat["columns"]["Feature_02_Broker_Rolling"]["net_value_1d"]["cross_entity_aggregation"] = "SUM"
    blank = {"effective_from_column": None, "effective_to_column": None}
    cat["relationships"] += [
        {"relationship_id": 30, "left_table": "IDX_Broker_Summary",
         "left_columns": ["Date", "Symbol", "Broker", "Investor Type", "Market Board"],
         "right_table": "Feature_02_Broker_Rolling",
         "right_columns": ["date", "ticker", "broker", "investor_type", "market_board"],
         "relationship_type": "ONE_TO_ONE", "temporal_rule": "Exact source trading date",
         "safe_output_grain": "date x ticker x broker x investor_type x market_board",
         "requires_preaggregation": False, "is_allowed": True, "version": "v1", **blank,
         "supported_join_semantics": ["EXACT_DATE"], "left_time_column": "Date", "right_time_column": "date"},
        {"relationship_id": 31, "left_table": "Feature_02_Broker_Rolling",
         "left_columns": ["ticker", "date", "market_board"], "right_table": "Feature_03_Stock_Broker_Daily",
         "right_columns": ["ticker", "date", "market_board"], "relationship_type": "MANY_TO_ONE",
         "temporal_rule": "Exact trading date and market board", "safe_output_grain": "date x ticker x market_board",
         "requires_preaggregation": True, "is_allowed": True, "version": "v1", **blank,
         "supported_join_semantics": ["EXACT_DATE"], "left_time_column": "date", "right_time_column": "date"}]
    return cat


def run(spec: dict, cat: dict | None = None):
    cat = cat or catalog()
    tables = [r["source_table"] for r in spec["data_requests"]]
    return validate(spec, subset(cat, tables), REF)


def request(rid: str, name: str, table: str, entity: str, time: str, columns: list[str], **extra) -> dict:
    return {"data_request_id": rid, "logical_name": name, "source_table": table, "entity_column": entity,
            "time_column": time, "columns": columns, "scope": {"type": "ALL"},
            "time_ranges": [{"range_id": "window", "start": "2026-08-01", "end": "2026-08-31"}],
            "source_frequency": "1D", "analysis_frequency": "1D", "resample": None, "history_buffer": None,
            "future_buffer": None, "ordering": [], "sampling_allowed": False, **extra}


def broker_spec(relationship: dict, version: str = "data_need_spec/v2") -> dict:
    return ytd_spec(spec_version=version, data_requests=[
        request("data_request_1_A", "summary", "IDX_Broker_Summary", "Symbol", "Date",
                ["Date", "Symbol", "Broker", "Investor Type", "Market Board", "Buy Value"]),
        request("data_request_1_B", "flows", "Feature_02_Broker_Rolling", "ticker", "date",
                ["ticker", "date", "broker", "investor_type", "market_board", "net_value_1d"])],
        relationships=[relationship])


def five_keys(**overrides) -> dict:
    rel = {"relationship_id": 30, "left_request_id": "data_request_1_A", "right_request_id": "data_request_1_B",
           "left_columns": list(BS_KEYS), "right_columns": list(F02_KEYS), "join_type": "INNER",
           "join_semantics": "EXACT_DATE", "left_time_column": "Date", "right_time_column": "date",
           "as_of_direction": None, "effective_from_column": None, "effective_to_column": None}
    rel.update(overrides)
    return rel


def codes(outcome) -> list[str]:
    return [i["code"] for i in outcome.issues]


# ---------------------------------------------------------------- Stage B: the contract

def test_a_five_key_join_is_approved_with_every_key_in_catalog_order() -> None:
    shuffled = five_keys(left_columns=list(reversed(BS_KEYS)), right_columns=list(reversed(F02_KEYS)))
    outcome = run(broker_spec(shuffled))
    assert outcome.status == "APPROVED", outcome.issues
    rel = outcome.approved["relationships"][0]
    assert rel["left_columns"] == ["Symbol", "Broker", "Investor Type", "Market Board"]
    assert rel["right_columns"] == ["ticker", "broker", "investor_type", "market_board"]
    assert "left_column" not in rel and rel["relationship_type"] == "ONE_TO_ONE"
    restriction = outcome.approved["requests"]["data_request_1_A"]["restrictions"][0]
    assert restriction["left_columns"] == rel["left_columns"] and "left_column" not in restriction
    reverse = outcome.approved["requests"]["data_request_1_B"]["restrictions"][0]
    assert reverse["left_columns"] == rel["right_columns"] and reverse["right_columns"] == rel["left_columns"]


@pytest.mark.parametrize("drop", range(4))
def test_leaving_out_one_key_is_refused(drop: int) -> None:
    left = [c for i, c in enumerate(BS_KEYS) if i != drop]
    right = [c for i, c in enumerate(F02_KEYS) if i != drop]
    outcome = run(broker_spec(five_keys(left_columns=left, right_columns=right)))
    assert outcome.status == "REVISION_REQUIRED" and "RELATIONSHIP_KEY_MISMATCH" in codes(outcome)


def test_the_v1_single_key_cannot_express_a_composite_relationship() -> None:
    v1 = {k: v for k, v in five_keys().items() if k not in ("left_columns", "right_columns")}
    outcome = run(broker_spec({**v1, "left_column": "Symbol", "right_column": "ticker"}, "data_need_spec/v1"))
    assert "RELATIONSHIP_KEY_MISMATCH" in codes(outcome)


def test_old_and_new_key_forms_together_must_agree() -> None:
    agree = broker_spec(five_keys(), "data_need_spec/v2")
    single = ytd_spec(spec_version="data_need_spec/v2", relationships=[
        {**{k: v for k, v in current_state().items()}, "left_columns": ["ticker"], "right_columns": ["Ticker"]}])
    assert run(single).status == "APPROVED"
    conflict = ytd_spec(spec_version="data_need_spec/v2", relationships=[
        {**current_state(), "left_columns": ["ticker"], "right_columns": ["Sector"]}])
    assert "RELATIONSHIP_KEY_FORMAT_CONFLICT" in codes(run(conflict))
    assert run(agree).status == "APPROVED"
    # a v1 spec cannot use the v2 fields
    assert "UNKNOWN_FIELD" in codes(run(broker_spec(five_keys(), "data_need_spec/v1")))


def test_a_single_key_relationship_keeps_its_v1_canonical_form_and_hash() -> None:
    v1 = run(ytd_spec())
    v2 = run(ytd_spec(spec_version="data_need_spec/v2", relationships=[
        {**{k: v for k, v in current_state().items() if k not in ("left_column", "right_column")},
         "left_columns": ["ticker"], "right_columns": ["Ticker"]}]))
    assert v1.status == v2.status == "APPROVED"
    assert v1.approved["relationships"] == v2.approved["relationships"]
    assert "left_column" in v1.approved["relationships"][0] and "left_columns" not in v1.approved["relationships"][0]
    assert v1.approved["requests"] == v2.approved["requests"]
    assert data_contract_sha256(v1.approved) == data_contract_sha256(v2.approved)


# ---------------------------------------------------------------- Stage C: preaggregation in the contract

def f03_spec() -> dict:
    return ytd_spec(spec_version="data_need_spec/v2", data_requests=[
        request("data_request_1_A", "flows", "Feature_02_Broker_Rolling", "ticker", "date",
                ["ticker", "date", "broker", "investor_type", "market_board", "net_value_1d",
                 "net_value_percentile_20d"]),
        request("data_request_1_B", "stock_flows", "Feature_03_Stock_Broker_Daily", "ticker", "date",
                ["ticker", "date", "market_board", "domestic_net_value"])],
        relationships=[{"relationship_id": 31, "left_request_id": "data_request_1_A",
                        "right_request_id": "data_request_1_B", "left_columns": ["ticker", "market_board"],
                        "right_columns": ["ticker", "market_board"], "join_type": "INNER",
                        "join_semantics": "EXACT_DATE", "left_time_column": "date", "right_time_column": "date",
                        "as_of_direction": None, "effective_from_column": None, "effective_to_column": None}])


def test_a_relationship_that_needs_preaggregation_is_approved_and_marked() -> None:
    outcome = run(f03_spec())
    assert outcome.status == "APPROVED", outcome.issues
    rel = outcome.approved["relationships"][0]
    assert rel["requires_preaggregation"] is True and rel["relationship_type"] == "MANY_TO_ONE"
    flows = outcome.approved["requests"]["data_request_1_A"]
    assert flows["aggregation_rules"] == {"net_value_1d": "SUM"}  # the percentile has no rule
    # reversed orientation reads the cardinality the other way
    reverse = copy.deepcopy(f03_spec())
    reverse["relationships"][0].update(left_request_id="data_request_1_B", right_request_id="data_request_1_A")
    assert run(reverse).approved["relationships"][0]["relationship_type"] == "ONE_TO_MANY"


# ---------------------------------------------------------------- the session helpers

def runtime():
    path = Path(__file__).resolve().parents[1] / "runtime" / "saniti_session.py"
    spec = importlib.util.spec_from_file_location("saniti_session_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def with_bundle(module, relationships: list[dict], requests: dict[str, dict]):
    module._BUNDLE.clear()
    module._BUNDLE.update({"relationships": relationships})
    module.REQUESTS.clear()
    module.REQUESTS.update(requests)
    return module


def summary() -> pd.DataFrame:
    rows = []
    for board in ("RG", "NG"):
        for investor in ("D", "F"):
            rows.append({"Date": "2026-08-03", "Symbol": "BBCA", "Broker": "AK", "Investor Type": investor,
                         "Market Board": board, "Buy Value": {"RG": 10, "NG": 100}[board] + {"D": 1, "F": 2}[investor]})
    return pd.DataFrame(rows)


def flows() -> pd.DataFrame:
    rows = []
    for board in ("RG", "NG"):
        for investor in ("D", "F"):
            for broker, value in (("AK", 5.0), ("BK", -2.0)):
                rows.append({"date": "2026-08-03", "ticker": "BBCA", "broker": broker, "investor_type": investor,
                             "market_board": board, "net_value_1d": value * (10 if board == "NG" else 1),
                             "net_value_percentile_20d": 0.5})
    return pd.DataFrame(rows)


BS_F02 = {"relationship_id": 30, "left_request_id": "s", "right_request_id": "f", "join_type": "INNER",
          "join_semantics": "EXACT_DATE", "left_columns": BS_KEYS, "right_columns": F02_KEYS,
          "left_time_column": "Date", "right_time_column": "date", "relationship_type": "ONE_TO_ONE",
          "requires_preaggregation": False}
F02_F03 = {"relationship_id": 31, "left_request_id": "f", "right_request_id": "t", "join_type": "INNER",
           "join_semantics": "EXACT_DATE", "left_columns": ["ticker", "market_board"],
           "right_columns": ["ticker", "market_board"], "left_time_column": "date", "right_time_column": "date",
           "relationship_type": "MANY_TO_ONE", "requires_preaggregation": True}
REQS = {"s": {"data_request_id": "s", "logical_name": "summary", "time_column": "Date"},
        "f": {"data_request_id": "f", "logical_name": "flows", "time_column": "date",
              "aggregation_rules": {"net_value_1d": "SUM"}},
        "t": {"data_request_id": "t", "logical_name": "stock_flows", "time_column": "date"}}


def test_a_five_key_join_never_mixes_boards_or_investor_types() -> None:
    saniti = with_bundle(runtime(), [BS_F02], REQS)
    f02 = flows()[flows()["broker"] == "AK"]
    out = saniti.join(30, summary(), f02)
    assert len(out) == 4  # one row per board and investor type, no cross-match
    assert all((out["Market Board"] == out["market_board"]) & (out["Investor Type"] == out["investor_type"]))
    report = saniti.join_report()
    assert report["rows_out"] == 4 and report["keys"][0] == ("Symbol", "ticker") and report["left_unmatched"] == 0


def test_a_duplicate_on_a_one_side_is_refused() -> None:
    saniti = with_bundle(runtime(), [BS_F02], REQS)
    doubled = pd.concat([summary(), summary().head(1)], ignore_index=True)
    with pytest.raises(saniti.JoinCardinalityError, match="unique"):
        saniti.join(30, doubled, flows()[flows()["broker"] == "AK"])


def test_a_left_join_keeps_unmatched_rows_with_their_status() -> None:
    saniti = with_bundle(runtime(), [BS_F02], REQS)
    left = pd.concat([summary(), pd.DataFrame([{"Date": "2026-08-03", "Symbol": "TLKM", "Broker": "AK",
                                                "Investor Type": "D", "Market Board": "RG", "Buy Value": 7}])],
                     ignore_index=True)
    out = saniti.join(30, left, flows()[flows()["broker"] == "AK"], how="left")
    assert len(out) == 5 and list(out["_saniti_match"]).count("unmatched") == 1
    assert out.loc[out["_saniti_match"] == "unmatched", "Symbol"].tolist() == ["TLKM"]
    assert saniti.join_report()["left_unmatched"] == 1


def test_preaggregation_is_required_then_matches_the_reference_totals() -> None:
    saniti = with_bundle(runtime(), [F02_F03], REQS)
    stock = pd.DataFrame([{"ticker": "BBCA", "market_board": b, "date": "2026-08-03", "domestic_net_value": 0}
                          for b in ("RG", "NG")])
    with pytest.raises(saniti.JoinCardinalityError, match="preaggregate"):
        saniti.join(31, flows(), stock)
    with pytest.raises(saniti.AggregationRuleMissing, match="net_value_percentile_20d"):
        saniti.preaggregate(31, flows(), ["net_value_percentile_20d"])
    grouped = saniti.preaggregate(31, flows(), ["net_value_1d"])
    # one row per ticker, board and date; totals equal the SQL reference sum over brokers and investor types
    assert len(grouped) == 2 and grouped["source_rows"].tolist() == [4, 4]
    reference = flows().groupby(["ticker", "market_board", "date"])["net_value_1d"].sum().to_dict()
    assert {(r.ticker, r.market_board, r.date): r.net_value_1d for r in grouped.itertuples()} == reference
    joined = saniti.join(31, grouped, stock)
    assert len(joined) == 2 and joined["net_value_1d"].sum() == flows()["net_value_1d"].sum()
