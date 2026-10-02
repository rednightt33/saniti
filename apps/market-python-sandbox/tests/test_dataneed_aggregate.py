"""G18 phase 1 (WAREHOUSE_AGGREGATION_PLAN.md, user decision 2026-10-02): a DataNeed request may ask the warehouse to
summarise across entities. What may be summed comes from the catalog's direction rule (cross_entity_aggregation),
never from allowed_aggregations; a dated table keeps its time column; the approved contract carries the summary's grain.

The catalog here is synthetic but has the live shapes (Feature 02's grain and rules as read from dev on 2026-10-02):
net_value_1d and net_value_5d add up across entities, a ratio does not, and identifiers may be counted."""
from __future__ import annotations

import copy
from datetime import date

import pytest

from app.data_need import contract_covers, data_contract_sha256, validate
from conftest import SOURCE_CONTRACTS, _catalog_table, _columns
from dataneed_fixtures import classification, data_need_catalog, subset, ytd_spec

REF = date(2026, 9, 25)
F2 = "Feature_02_Broker_Rolling"


def catalog() -> dict:
    found = data_need_catalog()
    found["tables"][F2] = _catalog_table(SOURCE_CONTRACTS[F2], "Broker flows per stock, board, broker and day.")
    columns = _columns({"ticker": ("text", True, True), "market_board": ("text", True, True),
                        "broker": ("text", True, True), "investor_type": ("text", True, True),
                        "date": ("date", True, True), "net_value_1d": ("numeric", True, False),
                        "net_value_5d": ("numeric", True, False), "buy_avg_price": ("numeric", True, False)})
    for name in ("ticker", "market_board", "broker", "date"):
        columns[name]["semantic_type"] = "IDENTIFIER"
    for name, rule in (("net_value_1d", "SUM"), ("net_value_5d", "SUM"), ("buy_avg_price", None)):
        columns[name]["cross_entity_aggregation"] = rule
        columns[name]["allowed_aggregations"] = ["AVG", "MAX", "MIN", "SUM"]  # the old list: no direction
    found["columns"][F2] = columns
    found["relationships"].append({
        "relationship_id": 6, "left_table": F2, "left_columns": ["ticker"], "right_table": "IDX_Stock_Universe",
        "right_columns": ["Ticker"], "relationship_type": "MANY_TO_ONE", "temporal_rule": "Current state",
        "safe_output_grain": "date x ticker x board x broker x investor type", "requires_preaggregation": False,
        "is_allowed": True, "version": "v1", "supported_join_semantics": ["CURRENT_STATE"], "left_time_column": None,
        "right_time_column": None, "effective_from_column": None, "effective_to_column": None})
    return found


CATALOG = catalog()


def flows(group_by=("date", "broker"), measures=None, **overrides) -> dict:
    measures = measures if measures is not None else [
        {"column": "net_value_1d", "function": "SUM", "as": "net_value_1d_sum"},
        {"column": None, "function": "COUNT", "as": "row_count"}]
    measured = [m["column"] for m in measures if m["column"]]
    request = {"data_request_id": "data_request_1_A", "logical_name": "broker_flows", "source_table": F2,
               "entity_column": "ticker", "time_column": "date",
               "columns": list(dict.fromkeys([*group_by, *measured])), "scope": {"type": "ALL"},
               "time_ranges": [{"range_id": "crash_days", "start": "2022-01-03", "end": "2026-08-31"}],
               "source_frequency": "1D", "analysis_frequency": "1D", "resample": None, "history_buffer": None,
               "future_buffer": None, "ordering": [], "sampling_allowed": False,
               "aggregate": {"group_by": list(group_by), "measures": measures}}
    request.update(overrides)
    return request


def banks_relationship(**overrides) -> dict:
    relationship = {"relationship_id": 6, "left_request_id": "data_request_1_A", "left_column": "ticker",
                    "right_request_id": "data_request_1_B", "right_column": "Ticker", "join_type": "INNER",
                    "join_semantics": "CURRENT_STATE", "left_time_column": None, "right_time_column": None,
                    "as_of_direction": None, "effective_from_column": None, "effective_to_column": None}
    relationship.update(overrides)
    return relationship


def spec(*requests, relationships=(), mode="ANALYSIS") -> dict:
    return ytd_spec(question="Broker mana yang paling sering net beli saham bank di hari crash?", mode=mode,
                    data_requests=list(requests), relationships=list(relationships))


def run(raw):
    tables = sorted({r["source_table"] for r in raw["data_requests"]})
    return validate(raw, subset(CATALOG, tables), REF)


def codes(outcome) -> list[str]:
    return [i["code"] for i in outcome.issues]


def test_question_5s_summary_across_tickers_is_approved_with_its_own_grain() -> None:
    outcome = run(spec(flows()))
    assert outcome.status == "APPROVED", outcome.issues
    request = outcome.approved["requests"]["data_request_1_A"]
    assert request["aggregate"]["group_by"] == ["date", "broker"]
    assert request["extract_columns"] == ["date", "broker", "net_value_1d_sum", "row_count"]
    assert request["key_columns"] == ["date", "broker"] and request["entity_column"] is None
    assert request["time_column"] == "date" and request["primary_key_columns"] == ["broker", "date"]
    assert request["column_types"]["row_count"] == "bigint" and request["column_types"]["net_value_1d_sum"] == "numeric"
    assert request["resample_rules"] == {} and request["aggregation_rules"] == {}
    # a summary never serves raw rows (or the reverse), and a raw request's contract carries no summary at all
    raw = run(spec(flows(columns=["net_value_1d"], aggregate=None)))
    assert raw.status == "APPROVED", raw.issues
    assert "aggregate" not in raw.approved["requests"]["data_request_1_A"]
    assert contract_covers(raw.approved, outcome.approved) is not None
    assert data_contract_sha256(raw.approved) != data_contract_sha256(outcome.approved)


def test_a_rolling_total_adds_up_across_entities_but_a_ratio_does_not() -> None:
    """The direction is what matters: net_value_5d is summed across tickers on one date (allowed); an average price is
    not additive in any direction although the old allowed_aggregations listed SUM for it."""
    ok = run(spec(flows(measures=[{"column": "net_value_5d", "function": "SUM", "as": "net_5d"},
                                  {"column": "buy_avg_price", "function": "MAX", "as": "max_price"},
                                  {"column": "ticker", "function": "COUNT_DISTINCT", "as": "tickers"}])))
    assert ok.status == "APPROVED", ok.issues
    refused = run(spec(flows(measures=[{"column": "buy_avg_price", "function": "SUM", "as": "price_sum"}])))
    assert codes(refused) == ["AGGREGATION_NOT_ADDITIVE"]
    assert "no SUM across ticker, market_board, investor_type" in refused.issues[0]["rejected_value"]
    for measure in ({"column": "broker", "function": "MAX", "as": "m"},
                    {"column": "net_value_1d", "function": "COUNT_DISTINCT", "as": "m"}):
        assert codes(run(spec(flows(measures=[measure])))) == ["AGGREGATION_NOT_ALLOWED"], measure


@pytest.mark.parametrize("group_by, code", [
    (("broker",), "AGGREGATE_TIME_REQUIRED"),                                   # phase 1: dates stay
    (("ticker", "market_board", "broker", "investor_type", "date"), "AGGREGATE_NOT_NEEDED"),
    (("date", "net_value_5d"), "AGGREGATE_GROUP_BY_NOT_ALLOWED"),               # a measure is not a group
])
def test_group_by_rules(group_by, code) -> None:
    assert code in codes(run(spec(flows(group_by=group_by))))


def test_research_and_resample_are_refused_and_columns_must_match() -> None:
    assert "AGGREGATE_MODE_UNSUPPORTED" in codes(run(spec(flows(), mode="RESEARCH")))
    resampled = run(spec(flows(analysis_frequency="1W", resample="WEEKLY")))
    assert "AGGREGATE_WITH_RESAMPLE" in codes(resampled)
    assert codes(run(spec(flows(columns=["date", "broker", "net_value_1d", "net_value_5d"])))) == [
        "AGGREGATE_COLUMNS_MISMATCH"]
    ordered = run(spec(flows(ordering=[{"column": "ticker", "direction": "ASC"}])))
    assert "ORDERING_COLUMN_INVALID" in codes(ordered)


@pytest.mark.parametrize("aggregate", [
    {"group_by": ["date"], "measures": [{"column": "net_value_1d", "function": "COUNT", "as": "n"}]},
    {"group_by": ["date"], "measures": [{"column": None, "function": "SUM", "as": "n"}]},
    {"group_by": ["date"], "measures": [{"column": None, "function": "COUNT", "as": "n"},
                                        {"column": None, "function": "COUNT", "as": "n"}]},
    {"group_by": ["date"], "measures": [{"column": "net_value_1d", "function": "AVG", "as": "n"}]},
    {"group_by": [], "measures": [{"column": None, "function": "COUNT", "as": "n"}]},
    {"group_by": ["date"], "measures": []},
])
def test_schema_of_the_summary(aggregate) -> None:
    outcome = run(spec(flows(aggregate=aggregate, columns=["date"])))
    assert outcome.status == "REVISION_REQUIRED"
    assert {"AGGREGATE_INVALID", "AGGREGATE_FUNCTION_INVALID"} & set(codes(outcome)), outcome.issues


def test_a_join_key_stays_in_group_by() -> None:
    """Summing over the bank universe's tickers is a restriction (EXISTS on the raw rows), but a relationship of the
    summary needs its key in the delivered rows."""
    universe = classification(columns=["Ticker", "Industry"])
    dropped = run(spec(flows(), universe, relationships=[banks_relationship()]))
    assert codes(dropped) == ["AGGREGATE_DROPS_JOIN_KEY"]
    kept = run(spec(flows(group_by=("date", "ticker")), universe, relationships=[banks_relationship()]))
    assert kept.status == "APPROVED", kept.issues
    request = kept.approved["requests"]["data_request_1_A"]
    assert request["entity_column"] == "ticker" and request["restrictions"][0]["relationship_id"] == 6
    assert copy.deepcopy(request["aggregate"]["measures"])[0]["as"] == "net_value_1d_sum"


# ---------------------------------------------------------------- the bundle path (Governor dataset -> coverage)

from conftest import requires_root  # noqa: E402
from dataneed_fixtures import prices  # noqa: E402
from test_dataneed_bundles import HEADERS, approve, build, env, extract_part, price_rows, window_of  # noqa: E402,F401


def summed_prices_spec() -> dict:
    """Total traded volume per date over every ticker (a synthetic SUM rule on volume for the test)."""
    request = prices(columns=["date", "volume"], ordering=[{"column": "date", "direction": "ASC"}],
                     time_ranges=[{"range_id": "q1", "start": "2026-01-02", "end": "2026-03-31"}],
                     history_buffer=None,
                     aggregate={"group_by": ["date"], "measures": [
                         {"column": "volume", "function": "SUM", "as": "volume_sum"},
                         {"column": None, "function": "COUNT", "as": "row_count"}]})
    return ytd_spec(data_requests=[request], relationships=[])


@pytest.fixture
def summing(env):
    columns = env["governor"].catalog["columns"]["Price_Stock_Indonesia_IDX"]
    columns["volume"]["cross_entity_aggregation"] = "SUM"
    columns["date"]["semantic_type"] = "TIME"
    columns["ticker"]["semantic_type"] = "IDENTIFIER"
    return env


@requires_root
def test_a_summary_dataset_is_bundled_profiled_and_covered_at_its_own_grain(summing) -> None:
    env = summing
    need = approve(env, summed_prices_spec())
    rid = "data_request_1_A"
    request = need["requests"][rid]
    window = window_of(need, rid, "q1")
    raw = price_rows(["BBCA", "BBRI", "BMRI"], window["from"], window["to"])
    frame = raw.groupby("date", as_index=False).agg(volume_sum=("volume", "sum"), row_count=("ticker", "size"))
    good = extract_part(env, need, rid, frame, f"{rid}__q1__part_001", window=window,
                        executed={"aggregate": request["aggregate"]})
    view = build(env, need, [{"data_request_id": rid, "envelopes": [], "parts": [good]}]).json()
    assert view["status"] == "READY" and view["coverage_status"] == "PASS", view
    dataset = view["datasets"][0]
    assert dataset["columns"] == ["date", "volume_sum", "row_count"] and dataset["entities"] in (None, 0)
    manifest = env["api"].get(f"/v1/bundles/{view['input_bundle_id']}", headers=HEADERS).json()
    quality = manifest["datasets"][0]["quality"]
    assert quality["duplicate_keys"]["key_columns"] == ["date"] and quality["duplicate_keys"]["groups"] == 0


@requires_root
def test_a_dataset_without_the_approved_summary_fails_coverage(summing) -> None:
    env = summing
    need = approve(env, summed_prices_spec(), request_id="req_bundle_2")
    rid = "data_request_1_A"
    window = window_of(need, rid, "q1")
    raw = price_rows(["BBCA", "BBRI"], window["from"], window["to"])
    frame = raw.groupby("date", as_index=False).agg(volume_sum=("volume", "sum"), row_count=("ticker", "size"))
    unsummarised = extract_part(env, need, rid, frame, f"{rid}__q1__part_001", window=window)  # no aggregate
    view = build(env, need, [{"data_request_id": rid, "envelopes": [], "parts": [unsummarised]}],
                 request_id="req_bundle_2").json()
    assert view.get("coverage_status") == "FAIL" or view.get("status") != "READY", view
    assert "EXECUTED_SCOPE_MISMATCH" in str(view)
