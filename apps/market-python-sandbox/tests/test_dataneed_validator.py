"""DataNeedSpec schema and DataNeedValidator: four layers, stable codes, no catalog candidates."""
from __future__ import annotations

import copy
import importlib.util
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from app.data_need import Limits, canonical_scope, canonical_value, validate
from dataneed_fixtures import classification, current_state, data_need_catalog, prices, subset, ytd_spec

REF = date(2026, 9, 25)
CATALOG = data_need_catalog()


def run(spec, catalog=CATALOG, ref=REF, limits=Limits()):
    tables = sorted({r["source_table"] for r in spec.get("data_requests", []) if isinstance(r, dict)
                     and isinstance(r.get("source_table"), str)})
    return validate(spec, subset(catalog, tables) if catalog is not None else None, ref, limits)


def codes(outcome) -> list[str]:
    return [issue["code"] for issue in outcome.issues]


def issue(outcome, code):
    return next(i for i in outcome.issues if i["code"] == code)


def test_the_documented_ytd_spec_is_approved_with_two_requests_and_two_ranges() -> None:
    outcome = run(ytd_spec())
    assert outcome.status == "APPROVED", outcome.issues
    approved = outcome.approved
    assert set(approved["requests"]) == {"data_request_1_A", "data_request_1_B"}
    windows = approved["requests"]["data_request_1_A"]["windows"]
    assert [w["range_id"] for w in windows] == ["current_ytd", "previous_comparable"]
    # one trading observation of history buffer widens each range backwards; the future is capped at the reference
    assert windows[0]["extract_from"] < "2026-01-01" and windows[0]["extract_to"] == "2026-09-25"
    assert approved["requests"]["data_request_1_B"]["windows"] == []
    restriction = approved["requests"]["data_request_1_A"]["restrictions"][0]
    assert restriction["relationship_id"] == 2 and restriction["join_semantics"] == "CURRENT_STATE"
    assert restriction["right_scope"] == {"type": "PREDICATE", "column": "Industry", "operator": "EQ",
                                          "values": ["Banks"]}
    assert [w["code"] for w in outcome.warnings] == ["HISTORICAL_REFERENCE_USES_CURRENT_STATE"]
    assert approved["requests"]["data_request_1_A"]["extract_columns"][:2] == ["ticker", "date"]


def test_an_inner_relationship_restricts_both_requests_whichever_side_is_left() -> None:
    """INNER keeps only matching rows on both sides; the model may write the relationship in either direction."""
    forward = run(ytd_spec()).approved["requests"]
    reversed_spec = ytd_spec(data_requests=[classification("data_request_1_A"), prices("data_request_1_B")],
                             relationships=[current_state(left_column="Ticker", right_column="ticker")])
    outcome = run(reversed_spec)
    assert outcome.status == "APPROVED", outcome.issues
    requests = outcome.approved["requests"]
    [on_prices] = requests["data_request_1_B"]["restrictions"]
    assert on_prices == forward["data_request_1_A"]["restrictions"][0]  # the same pushdown in either direction
    assert on_prices["left_column"] == "ticker" and on_prices["right_table"] == "IDX_Stock_Universe"
    assert on_prices["right_scope"] == {"type": "PREDICATE", "column": "Industry", "operator": "EQ",
                                        "values": ["Banks"]}
    [on_universe] = requests["data_request_1_A"]["restrictions"]
    assert on_universe["left_column"] == "Ticker" and on_universe["right_table"] == "Price_Stock_Indonesia_IDX"
    assert on_universe["right_scope"] == {"type": "ALL"}
    # the prices side holds the historical observations, whichever side of the relationship it is
    assert [(w["code"], w["data_request_id"]) for w in outcome.warnings] == [
        ("HISTORICAL_REFERENCE_USES_CURRENT_STATE", "data_request_1_B")]
    assert forward["data_request_1_B"]["restrictions"][0]["right_table"] == "Price_Stock_Indonesia_IDX"


def test_issues_carry_request_code_path_and_rejected_value_and_never_candidates() -> None:
    spec = ytd_spec()
    spec["data_requests"][0]["columns"].append("adj_clsoe")
    spec["relationships"][0]["join_semantics"] = "AS_OF"
    spec["relationships"][0].update(left_time_column="date", right_time_column="date", as_of_direction="BACKWARD")
    outcome = run(spec)
    assert outcome.status == "REVISION_REQUIRED"
    unknown = issue(outcome, "UNKNOWN_COLUMN")
    assert unknown == {"data_request_id": "data_request_1_A", "code": "UNKNOWN_COLUMN",
                       "field_path": "data_requests[0].columns[7]", "rejected_value": "adj_clsoe"}
    semantics = issue(outcome, "JOIN_SEMANTICS_UNAVAILABLE")
    assert semantics["field_path"] == "relationships[0].join_semantics" and semantics["rejected_value"] == "AS_OF"
    for entry in outcome.issues:
        assert set(entry) == {"data_request_id", "code", "field_path", "rejected_value"}
    text = json.dumps(outcome.body()).lower()
    assert "candidate" not in text and "did you mean" not in text and "close" not in unknown["rejected_value"][:4]


@pytest.mark.parametrize("mutate, code", [
    (lambda s: s["data_requests"].append(copy.deepcopy(s["data_requests"][0]) | {"logical_name": "prices_2"}),
     "DUPLICATE_REQUEST_ID"),
    (lambda s: s["data_requests"][0].update(data_request_id="other_group_A"), "INVALID_REQUEST_ID"),
    (lambda s: s["data_requests"][0]["time_ranges"].append({"range_id": "current_ytd", "start": "2024-01-01",
                                                            "end": "2024-02-01"}), "DUPLICATE_RANGE_ID"),
    (lambda s: s["data_requests"][0].pop("columns"), "MISSING_REQUIRED_FIELD"),
    (lambda s: s["data_requests"][0].update(columns=[]), "MISSING_REQUIRED_FIELD"),
    (lambda s: s["data_requests"][0].update(formula="rsi(close, 14)"), "UNKNOWN_FIELD"),
    (lambda s: s.update(spec_version="analysis_spec/v2"), "UNSUPPORTED_SPEC_VERSION"),
    (lambda s: s.update(revision=0), "INVALID_FIELD_VALUE"),
    (lambda s: s["data_requests"][0].update(time_ranges=[{"range_id": "x", "start": "2026-13-01",
                                                          "end": "2026-12-31"}]), "INVALID_TIME_RANGE"),
    (lambda s: s["data_requests"][0].update(history_buffer={"value": -1, "unit": "TRADING_OBSERVATIONS"}),
     "BUFFER_INVALID"),
    (lambda s: s["data_requests"][0].update(history_buffer={"value": 5, "unit": "WEEKS"}), "BUFFER_INVALID"),
    (lambda s: s["data_requests"][0].update(ordering=[{"column": "date", "direction": "UP"}]),
     "ORDERING_COLUMN_INVALID"),
])
def test_schema_layer(mutate, code) -> None:
    spec = ytd_spec()
    mutate(spec)
    outcome = run(spec)
    assert outcome.status == "REVISION_REQUIRED" and code in codes(outcome), outcome.issues


def test_revision_and_group_are_part_of_the_contract() -> None:
    spec = ytd_spec(revision=3)
    outcome = run(spec)
    assert outcome.status == "APPROVED" and outcome.approved["revision"] == 3
    assert outcome.approved["request_group_id"] == "data_request_1"


@pytest.mark.parametrize("mutate, code, path", [
    (lambda s: s["data_requests"][0].update(source_table="Price_Stok"), "UNKNOWN_TABLE",
     "data_requests[0].source_table"),
    (lambda s: s["data_requests"][0].update(entity_column="Ticker"), "ENTITY_COLUMN_MISMATCH",
     "data_requests[0].entity_column"),
    (lambda s: s["data_requests"][0].update(time_column=None), "TIME_COLUMN_MISMATCH",
     "data_requests[0].time_column"),
    (lambda s: s["data_requests"][0].update(source_frequency="1W", analysis_frequency="1W"),
     "SOURCE_FREQUENCY_UNAVAILABLE", "data_requests[0].source_frequency"),
    (lambda s: s.update(subject={"data_domain": "MACRO", "entity_type": "SERIES", "asset_type": None}),
     "SUBJECT_TABLE_MISMATCH", "subject"),
    (lambda s: s["data_requests"][0].update(scope={"type": "PREDICATE", "column": "query_date", "operator": "EQ",
                                                   "value": "2026-01-01"}), "INVALID_FILTER_COLUMN",
     "data_requests[0].scope.column"),
    (lambda s: s["data_requests"][1].update(scope={"type": "PREDICATE", "column": "Sector", "operator": "GT",
                                                   "value": "Energy"}), "INVALID_FILTER_OPERATOR",
     "data_requests[1].scope.operator"),
    (lambda s: s["data_requests"][1].update(scope={"type": "PREDICATE", "column": "Shares", "operator": "GTE",
                                                   "value": "many"}), "INVALID_FILTER_VALUE",
     "data_requests[1].scope.value"),
    (lambda s: s["data_requests"][1].update(scope={"type": "PREDICATE", "column": "Sector", "operator": "LIKE",
                                                   "value": "Ener%"}), "INVALID_SCOPE_OPERATOR",
     "data_requests[1].scope.operator"),
    (lambda s: s["data_requests"][0].update(ordering=[{"column": "volume_rank", "direction": "ASC"}]),
     "ORDERING_COLUMN_INVALID", "data_requests[0].ordering[0].column"),
])
def test_catalog_binding(mutate, code, path) -> None:
    spec = ytd_spec()
    mutate(spec)
    outcome = run(spec)
    assert outcome.status == "REVISION_REQUIRED"
    found = issue(outcome, code)
    assert found["field_path"] == path, outcome.issues


def test_the_documented_nested_scope_is_approved_and_canonical_regardless_of_child_order() -> None:
    tree = {"type": "AND", "children": [
        {"type": "PREDICATE", "column": "Country", "operator": "EQ", "value": "Indonesia"},
        {"type": "OR", "children": [
            {"type": "PREDICATE", "column": "Sector", "operator": "EQ", "value": "Energy"},
            {"type": "PREDICATE", "column": "Industry", "operator": "EQ", "value": "Banks"}]},
        {"type": "NOT", "child": {"type": "PREDICATE", "column": "Status", "operator": "EQ", "value": "Delisted"}}]}
    reordered = copy.deepcopy(tree)
    reordered["children"].reverse()
    reordered["children"][1]["children"].reverse()
    a = run(ytd_spec(data_requests=[prices(), classification(scope=tree)]))
    b = run(ytd_spec(data_requests=[prices(), classification(scope=reordered)]))
    assert a.status == b.status == "APPROVED", (a.issues, b.issues)
    ra, rb = a.approved["requests"]["data_request_1_B"], b.approved["requests"]["data_request_1_B"]
    assert ra["scope"] == rb["scope"] and ra["scope_sha256"] == rb["scope_sha256"]
    assert ra["scope"]["children"][-1]["type"] in ("NOT", "OR", "PREDICATE")


def test_in_lists_are_sorted_unique_and_typed_in_the_canonical_scope() -> None:
    types = {"Shares": "bigint", "Sector": "text"}
    node = {"type": "OR", "children": [
        {"type": "PREDICATE", "column": "Sector", "operator": "IN", "value": ["Energy", "Banks", "Energy"]},
        {"type": "PREDICATE", "column": "Shares", "operator": "BETWEEN", "value": [1000, 2000.0]}]}
    canonical = canonical_scope(node, types)
    assert {"type": "PREDICATE", "column": "Sector", "operator": "IN", "values": ["Banks", "Energy"]} \
        in canonical["children"]
    assert {"type": "PREDICATE", "column": "Shares", "operator": "BETWEEN", "values": ["1000", "2000"]} \
        in canonical["children"]


@pytest.mark.parametrize("scope", [
    {"type": "AND", "children": [{"type": "PREDICATE", "column": "Sector", "operator": "EQ", "value": "Energy"}]},
    {"type": "XOR", "children": []},
    {"type": "NOT", "children": [{"type": "ALL"}]},
    {"type": "AND", "children": [{"type": "ALL"}, {"type": "PREDICATE", "column": "Sector", "operator": "EQ",
                                                  "value": "Energy"}]},
    {"type": "PREDICATE", "column": "Sector", "operator": "IN", "value": []},
    {"type": "PREDICATE", "column": "Sector", "operator": "BETWEEN", "value": ["a"]},
])
def test_invalid_scope_trees_are_refused(scope) -> None:
    outcome = run(ytd_spec(data_requests=[prices(), classification(scope=scope)]))
    assert outcome.status == "REVISION_REQUIRED"
    assert set(codes(outcome)) & {"INVALID_SCOPE", "INVALID_FILTER_VALUE"}, outcome.issues


def test_scope_depth_and_node_limits() -> None:
    leaf = {"type": "PREDICATE", "column": "Sector", "operator": "EQ", "value": "Energy"}
    deep = leaf
    for kind in ("AND", "OR", "AND", "OR"):
        deep = {"type": kind, "children": [deep, dict(leaf, value="Banks")]}
    outcome = run(ytd_spec(data_requests=[prices(), classification(scope=deep)]))
    assert "INVALID_SCOPE" in codes(outcome) and "depth" in str(issue(outcome, "INVALID_SCOPE")["rejected_value"])
    wide = {"type": "OR", "children": [dict(leaf, value=f"S{i}") for i in range(45)]}
    outcome = run(ytd_spec(data_requests=[prices(), classification(scope=wide)]))
    assert "INVALID_SCOPE" in codes(outcome)


@pytest.mark.parametrize("relationship, code", [
    (current_state(relationship_id=99), "UNKNOWN_RELATIONSHIP"),
    (current_state(relationship_id=1), "RELATIONSHIP_KEY_MISMATCH"),
    (current_state(right_request_id="data_request_1_Z"), "INVALID_REQUEST_ID"),
    (current_state(join_semantics="EXACT_DATE", left_time_column="date", right_time_column="date"),
     "JOIN_SEMANTICS_UNAVAILABLE"),
    (current_state(left_column="date"), "RELATIONSHIP_KEY_MISMATCH"),
    (current_state(left_time_column="date"), "TIME_COLUMN_MISMATCH"),
    (current_state(effective_from_column="valid_from"), "EFFECTIVE_DATE_COLUMNS_REQUIRED"),
    (current_state(join_type="OUTER"), "INVALID_FIELD_VALUE"),
])
def test_cross_request_relationships(relationship, code) -> None:
    outcome = run(ytd_spec(relationships=[relationship]))
    assert outcome.status == "REVISION_REQUIRED" and code in codes(outcome), outcome.issues


def test_a_disallowed_catalog_relationship_is_refused() -> None:
    broker = {"data_request_id": "data_request_1_C", "logical_name": "brokers", "source_table": "IDX_Broker_Profile",
              "entity_column": "broker_code", "time_column": None, "columns": ["broker_code"], "scope": {"type": "ALL"},
              "time_ranges": [], "source_frequency": "STATIC", "analysis_frequency": "STATIC", "resample": None,
              "history_buffer": None, "future_buffer": None, "ordering": [], "sampling_allowed": False}
    rel = current_state(relationship_id=5, right_request_id="data_request_1_C", right_column="broker_code")
    outcome = run(ytd_spec(data_requests=[prices(), classification(), broker], relationships=[rel]))
    assert "RELATIONSHIP_NOT_ALLOWED" in codes(outcome)


def shares(**overrides):
    request = {"data_request_id": "data_request_1_C", "logical_name": "shares", "source_table": "Shares_Outstanding",
               "entity_column": "ticker", "time_column": "effective_date", "columns": ["ticker", "effective_date",
                                                                                        "shares"],
               "scope": {"type": "ALL"}, "time_ranges": [{"range_id": "all", "start": "2024-01-01",
                                                          "end": "2026-09-25"}],
               "source_frequency": "1D", "analysis_frequency": "1D", "resample": None, "history_buffer": None,
               "future_buffer": None, "ordering": [], "sampling_allowed": False}
    request.update(overrides)
    return request


def history(**overrides):
    request = {"data_request_id": "data_request_1_D", "logical_name": "classification_history",
               "source_table": "Classification_History", "entity_column": "Ticker", "time_column": None,
               "columns": ["Ticker", "Sector", "valid_from", "valid_to"],
               "scope": {"type": "PREDICATE", "column": "Sector", "operator": "EQ", "value": "Financials"},
               "time_ranges": [], "source_frequency": "STATIC", "analysis_frequency": "STATIC", "resample": None,
               "history_buffer": None, "future_buffer": None, "ordering": [], "sampling_allowed": False}
    request.update(overrides)
    return request


def test_as_of_relationships_need_their_catalog_time_columns_and_direction() -> None:
    good = current_state(relationship_id=3, right_request_id="data_request_1_C", right_column="ticker",
                         join_type="LEFT", join_semantics="AS_OF", left_time_column="date",
                         right_time_column="effective_date", as_of_direction="BACKWARD")
    ok = run(ytd_spec(data_requests=[prices(), shares()], relationships=[good]))
    assert ok.status == "APPROVED", ok.issues
    assert ok.approved["relationships"][0]["as_of_direction"] == "BACKWARD"
    missing = dict(good, right_time_column=None, as_of_direction=None)
    outcome = run(ytd_spec(data_requests=[prices(), shares()], relationships=[missing]))
    assert codes(outcome).count("AS_OF_COLUMN_REQUIRED") == 2
    wrong = dict(good, right_time_column="date")
    assert "TIME_COLUMN_MISMATCH" in codes(run(ytd_spec(data_requests=[prices(), shares()], relationships=[wrong])))


def test_effective_dated_relationships_need_their_catalog_effective_columns() -> None:
    good = current_state(relationship_id=4, right_request_id="data_request_1_D", right_column="Ticker",
                         join_semantics="EFFECTIVE_DATED", effective_from_column="valid_from",
                         effective_to_column="valid_to")
    ok = run(ytd_spec(data_requests=[prices(), history()], relationships=[good]))
    assert ok.status == "APPROVED", ok.issues
    restriction = ok.approved["requests"]["data_request_1_A"]["restrictions"][0]
    assert restriction["join_semantics"] == "EFFECTIVE_DATED" and restriction["left_time_column"] == "date"
    assert not ok.warnings  # point-in-time: no current-state warning
    missing = dict(good, effective_to_column=None)
    outcome = run(ytd_spec(data_requests=[prices(), history()], relationships=[missing]))
    assert "EFFECTIVE_DATE_COLUMNS_REQUIRED" in codes(outcome)


def test_restrictions_are_one_level_deep() -> None:
    chained = [current_state(), current_state(relationship_id=4, left_request_id="data_request_1_B",
                                              left_column="Ticker", right_request_id="data_request_1_D",
                                              right_column="Ticker", join_semantics="CURRENT_STATE")]
    outcome = run(ytd_spec(data_requests=[prices(), classification(), history()], relationships=chained))
    assert "RELATIONSHIP_KEY_MISMATCH" in codes(outcome) or "RELATIONSHIP_NOT_ALLOWED" in codes(outcome)


@pytest.mark.parametrize("overrides, code", [
    ({"analysis_frequency": "1W"}, "RESAMPLE_REQUIRED"),
    ({"analysis_frequency": "1W", "resample": "MONTHLY"}, "RESAMPLE_INVALID"),
    ({"resample": "WEEKLY"}, "RESAMPLE_INVALID"),
    ({"analysis_frequency": "1H"}, "ANALYSIS_FREQUENCY_INVALID"),
    ({"analysis_frequency": "2W", "resample": "WEEKLY"}, "ANALYSIS_FREQUENCY_INVALID"),
    ({"time_ranges": []}, "TIME_RANGE_REQUIRED"),
    ({"time_ranges": [{"range_id": "later", "start": "2026-10-01", "end": "2026-12-31"}]}, "INVALID_TIME_RANGE"),
    ({"time_ranges": [{"range_id": "backwards", "start": "2026-05-01", "end": "2026-04-01"}]}, "INVALID_TIME_RANGE"),
    ({"sampling_allowed": True}, "SAMPLING_NOT_ALLOWED"),
    ({"history_buffer": {"value": 9000, "unit": "TRADING_OBSERVATIONS"}}, "BUFFER_INVALID"),
])
def test_planning_feasibility(overrides, code) -> None:
    outcome = run(ytd_spec(data_requests=[prices(**overrides), classification()]))
    assert outcome.status == "REVISION_REQUIRED" and code in codes(outcome), outcome.issues


def test_weekly_analysis_of_daily_source_keeps_frequencies_distinct() -> None:
    outcome = run(ytd_spec(data_requests=[prices(analysis_frequency="1W", resample="WEEKLY"), classification()]))
    assert outcome.status == "APPROVED", outcome.issues
    entry = outcome.approved["requests"]["data_request_1_A"]
    assert (entry["source_frequency"], entry["analysis_frequency"], entry["resample"]) == ("1D", "1W", "WEEKLY")
    assert entry["resample_rules"]["close"] == "LAST"


def test_static_requests_take_no_ranges_buffers_or_dated_frequency() -> None:
    bad = classification(time_ranges=[{"range_id": "r", "start": "2026-01-01", "end": "2026-02-01"}],
                         history_buffer={"value": 5, "unit": "CALENDAR_DAYS"}, source_frequency="1D")
    outcome = run(ytd_spec(data_requests=[prices(), bad]))
    assert {"INVALID_TIME_RANGE", "BUFFER_INVALID", "SOURCE_FREQUENCY_UNAVAILABLE"} <= set(codes(outcome))


def test_catalog_unavailable_is_its_own_status() -> None:
    outcome = run(ytd_spec(), catalog=None)
    assert outcome.status == "CATALOG_UNAVAILABLE" and outcome.approved is None


def test_the_validator_has_no_hardcoded_tables_or_dimensions() -> None:
    """A request against any catalog table with any dimensions validates the same way (catalog-driven)."""
    macro = {"data_request_id": "g_1", "logical_name": "series", "source_table": "Macro_Series_Monthly",
             "entity_column": "series_id", "time_column": "period", "columns": ["series_id", "period", "value"],
             "scope": {"type": "PREDICATE", "column": "series_id", "operator": "IN", "value": ["CPI", "M2"]},
             "time_ranges": [{"range_id": "decade", "start": "2016-01-01", "end": "2026-08-31"}],
             "source_frequency": "1M", "analysis_frequency": "1Q", "resample": "QUARTERLY", "history_buffer": None,
             "future_buffer": None, "ordering": [{"column": "period", "direction": "ASC"}], "sampling_allowed": False}
    spec = {"spec_version": "data_need_spec/v1", "request_group_id": "g", "revision": 1, "mode": "ANALYSIS",
            "question": "Quarterly macro series.", "subject": {"data_domain": "MACRO", "entity_type": "SERIES",
                                                               "asset_type": None},
            "data_requests": [macro], "relationships": []}
    outcome = run(spec)
    assert outcome.status == "APPROVED", outcome.issues


def test_the_contract_has_no_calculation_or_output_fields() -> None:
    from app.data_need import REQUEST_FIELDS, TOP_FIELDS

    forbidden = {"calculations", "calculation", "formula", "formula_refs", "method", "indicator", "outputs",
                 "output_grain", "ranking", "event_study", "python_code", "expected_outputs"}
    assert not forbidden & (REQUEST_FIELDS | TOP_FIELDS)


def test_canonical_values_equal_the_governor_implementation() -> None:
    """The approved scope hash and the Governor's executed scope must render every typed value identically."""
    path = Path(__file__).resolve().parents[2] / "market-sql-governor" / "app" / "catalog_contract.py"
    module_spec = importlib.util.spec_from_file_location("governor_catalog_contract_dataneed", path)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    for value in ("Banks", "", 5, 5.0, 0.1, 1e-7, -0.0, 12345678901234, Decimal("1.500"), True, False,
                  date(2026, 9, 1), datetime(2026, 9, 1, 9, 30)):
        assert canonical_value(value) == module.canonical_value(value)


def test_every_catalog_key_column_is_extracted_so_rows_stay_identifiable() -> None:
    """A request for one measure of a table with a five-column grain still receives the whole grain."""
    rolling = prices(source_table="Feature_02_Broker_Rolling", columns=["net_value"], ordering=[],
                     history_buffer=None)
    outcome = run(ytd_spec(data_requests=[rolling], relationships=[]))
    assert outcome.status == "APPROVED", outcome.issues
    entry = outcome.approved["requests"]["data_request_1_A"]
    assert entry["key_columns"] == ["ticker", "date", "market_board", "broker", "investor_type"]
    assert entry["extract_columns"] == entry["key_columns"] + ["net_value"]
