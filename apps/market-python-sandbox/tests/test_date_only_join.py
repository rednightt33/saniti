"""EXEC-M216: relationships that meet on the date only (a stock and an index level, a stock and a monthly macro
series) and relationships that pair other keys but not the entity (a stock's market board and the market's).

The side a relationship declares "one" must give one row per date: its scope fixes every primary key column the
relationship leaves open (ONE_SIDE_NOT_UNIQUE otherwise), derived from the catalog's primary_key_columns. The
canonical key form of a date-only relationship is two empty key lists; saniti.join joins on the date alone."""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from app.data_need import validate
from dataneed_fixtures import data_need_catalog, prices, subset, ytd_spec
from conftest import _catalog_table, _columns, _contract

REF = date(2026, 9, 25)
BLANK = {"effective_from_column": None, "effective_to_column": None}


def catalog() -> dict:
    cat = data_need_catalog()
    cat["tables"]["Macro_Series_Monthly"]["primary_key_columns"] = ["series_id", "period"]
    board = _contract("Board_Flow_Daily", ["ticker", "market_board", "date"], "ticker", "date")
    market = _contract("Market_Board_Flow_Daily", ["ticker", "market_board", "date"], "ticker", "date", "INDEX", None)
    for contract in (board, market):
        cat["tables"][contract["table"]] = _catalog_table(contract, "Synthetic board flows.")
        cat["columns"][contract["table"]] = _columns({"ticker": ("text", True, True), "market_board": ("text", True, True),
                                                      "date": ("date", True, True), "net": ("numeric", True, False)})
        for column in cat["columns"][contract["table"]].values():
            column.setdefault("resample_aggregation", None)
    for column in cat["columns"]["Macro_Series_Monthly"].values():
        column.setdefault("resample_aggregation", None)
    cat["relationships"] += [
        {"relationship_id": 40, "left_table": "Price_Stock_Indonesia_IDX", "left_columns": ["date"],
         "right_table": "Index_Level_Daily", "right_columns": ["date"], "relationship_type": "MANY_TO_ONE",
         "temporal_rule": "Same trading date", "safe_output_grain": "date x ticker", "requires_preaggregation": False,
         "is_allowed": True, "version": "v1", **BLANK, "supported_join_semantics": ["EXACT_DATE"],
         "left_time_column": "date", "right_time_column": "date"},
        {"relationship_id": 41, "left_table": "Price_Stock_Indonesia_IDX", "left_columns": ["date"],
         "right_table": "Macro_Series_Monthly", "right_columns": ["period"], "relationship_type": "MANY_TO_ONE",
         "temporal_rule": "Latest value at or before the date", "safe_output_grain": "date x ticker",
         "requires_preaggregation": False, "is_allowed": True, "version": "v1", **BLANK,
         "supported_join_semantics": ["AS_OF"], "left_time_column": "date", "right_time_column": "period"},
        {"relationship_id": 42, "left_table": "Board_Flow_Daily", "left_columns": ["market_board", "date"],
         "right_table": "Market_Board_Flow_Daily", "right_columns": ["market_board", "date"],
         "relationship_type": "MANY_TO_ONE", "temporal_rule": "Same trading date and board",
         "safe_output_grain": "date x ticker x market_board", "requires_preaggregation": False, "is_allowed": True,
         "version": "v1", **BLANK, "supported_join_semantics": ["EXACT_DATE"], "left_time_column": "date",
         "right_time_column": "date"}]
    return cat


def run(spec: dict):
    return validate(spec, subset(catalog(), [r["source_table"] for r in spec["data_requests"]]), REF)


def pred(column: str, operator: str, value) -> dict:
    return {"type": "PREDICATE", "column": column, "operator": operator, "value": value}


def index_request(scope: dict) -> dict:
    return prices("data_request_1_B", logical_name="index_level", source_table="Index_Level_Daily",
                  entity_column="index_code", columns=["index_code", "date", "close"], scope=scope, ordering=[],
                  history_buffer=None)


def macro_request(scope: dict) -> dict:
    return prices("data_request_1_B", logical_name="bi_rate", source_table="Macro_Series_Monthly",
                  entity_column="series_id", time_column="period", columns=["series_id", "period", "value"],
                  scope=scope, ordering=[], history_buffer=None, source_frequency="1M", analysis_frequency="1M")


def relationship(rid: int, semantics: str, right_time: str, **overrides) -> dict:
    rel = {"relationship_id": rid, "left_request_id": "data_request_1_A", "right_request_id": "data_request_1_B",
           "left_columns": [], "right_columns": [], "join_type": "INNER", "join_semantics": semantics,
           "left_time_column": "date", "right_time_column": right_time,
           "as_of_direction": "BACKWARD" if semantics == "AS_OF" else None, **BLANK}
    rel.update(overrides)
    return rel


def spec_with(right: dict, rel: dict) -> dict:
    return ytd_spec(spec_version="data_need_spec/v2", data_requests=[prices(), right], relationships=[rel])


def codes(outcome) -> list[str]:
    return [i["code"] for i in outcome.issues]


# ---------------------------------------------------------------- the contract

def test_a_date_only_relationship_is_approved_with_two_empty_key_lists() -> None:
    scope = {"type": "AND", "children": [pred("index_code", "EQ", "IHSG"), pred("close", "GT", 7000)]}
    outcome = run(spec_with(index_request(scope), relationship(40, "EXACT_DATE", "date")))
    assert outcome.approved, outcome.issues
    rel = outcome.approved["relationships"][0]
    assert (rel["left_columns"], rel["right_columns"]) == ([], []) and "left_column" not in rel
    restriction = outcome.approved["requests"]["data_request_1_A"]["restrictions"][0]
    assert (restriction["left_columns"], restriction["right_columns"]) == ([], [])


@pytest.mark.parametrize("scope", [
    pred("close", "GT", 7000),                                                   # no series named
    pred("index_code", "IN", ["IHSG", "LQ45"]),                                  # two series on every date
    {"type": "OR", "children": [pred("index_code", "EQ", "IHSG"), pred("close", "GT", 1)]},  # not fixed by OR
])
def test_the_one_side_must_name_one_series(scope) -> None:
    outcome = run(spec_with(index_request(scope), relationship(40, "EXACT_DATE", "date")))
    issue = next(i for i in outcome.issues if i["code"] == "ONE_SIDE_NOT_UNIQUE")
    assert issue["data_request_id"] == "data_request_1_B" and issue["field_path"] == "data_requests[1].scope"
    assert "index_code" in issue["note"] and "EQ" in issue["note"] and "Wrong:" in issue["note"]


def test_in_with_one_value_names_one_series() -> None:
    outcome = run(spec_with(index_request(pred("index_code", "IN", ["IHSG"])), relationship(40, "EXACT_DATE", "date")))
    assert outcome.approved, outcome.issues


def test_a_monthly_macro_series_joins_as_of_once_its_series_is_fixed() -> None:
    loose = run(spec_with(macro_request(pred("value", "GTE", 6)), relationship(41, "AS_OF", "period")))
    assert "ONE_SIDE_NOT_UNIQUE" in codes(loose)
    fixed = run(spec_with(macro_request(pred("series_id", "EQ", "BI_RATE")), relationship(41, "AS_OF", "period")))
    assert fixed.approved, fixed.issues


def test_entity_keys_on_a_date_only_relationship_are_refused_with_the_expected_empty_pairs() -> None:
    rel = relationship(40, "EXACT_DATE", "date", left_columns=["ticker"], right_columns=["index_code"])
    outcome = run(spec_with(index_request(pred("index_code", "EQ", "IHSG")), rel))
    issue = next(i for i in outcome.issues if i["code"] == "RELATIONSHIP_KEY_MISMATCH")
    assert issue["expected_value"] == ""


def test_a_relationship_on_other_keys_still_needs_the_one_side_entity_fixed() -> None:
    board = prices(source_table="Board_Flow_Daily", columns=["ticker", "market_board", "date", "net"],
                   history_buffer=None, ordering=[])
    market = prices("data_request_1_B", logical_name="market_flows", source_table="Market_Board_Flow_Daily",
                    columns=["ticker", "market_board", "date", "net"], scope=pred("net", "GT", 0),
                    history_buffer=None, ordering=[])
    rel = relationship(42, "EXACT_DATE", "date", left_columns=["market_board"], right_columns=["market_board"])
    spec = ytd_spec(spec_version="data_need_spec/v2", data_requests=[board, market], relationships=[rel])
    assert "ONE_SIDE_NOT_UNIQUE" in codes(run(spec))
    market["scope"] = {"type": "AND", "children": [pred("ticker", "EQ", "IHSG"), pred("net", "GT", 0)]}
    assert run(spec).approved


def test_a_relationship_that_pairs_the_entity_keeps_its_old_behaviour() -> None:
    # the existing composite and single-key relationships pair the entity: the rule never applies to them
    outcome = run(ytd_spec())
    assert outcome.approved and "ONE_SIDE_NOT_UNIQUE" not in codes(outcome)


# ---------------------------------------------------------------- saniti.join on the date only

def runtime():
    path = Path(__file__).resolve().parents[1] / "runtime" / "saniti_session.py"
    spec = importlib.util.spec_from_file_location("saniti_session_date_only", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bundle(module, rel: dict):
    module._BUNDLE.clear()
    module._BUNDLE.update({"relationships": [rel]})
    module.REQUESTS.clear()
    module.REQUESTS.update({"p": {"data_request_id": "p", "logical_name": "prices", "time_column": "date"},
                            "i": {"data_request_id": "i", "logical_name": "index", "time_column": "date"}})
    return module


JOINED = {"relationship_id": 40, "left_request_id": "p", "right_request_id": "i", "join_type": "INNER",
          "join_semantics": "EXACT_DATE", "left_columns": [], "right_columns": [], "relationship_type": "MANY_TO_ONE",
          "requires_preaggregation": False, "left_time_column": "date", "right_time_column": "date",
          "as_of_direction": None, **BLANK}


def stock_prices() -> pd.DataFrame:
    return pd.DataFrame([{"ticker": t, "date": d, "close": c} for t in ("BBCA", "BBRI")
                         for d, c in (("2026-08-03", 10), ("2026-08-04", 11), ("2026-08-05", 12))])


def test_saniti_join_pairs_every_stock_row_with_the_index_row_of_its_date() -> None:
    saniti = bundle(runtime(), JOINED)
    index = pd.DataFrame([{"index_code": "IHSG", "date": "2026-08-03", "close": 7000},
                          {"index_code": "IHSG", "date": "2026-08-05", "close": 7100}])
    out = saniti.join(40, stock_prices(), index)
    assert len(out) == 4 and set(out["date"]) == {"2026-08-03", "2026-08-05"}
    assert saniti.join_report()["keys"] == [] and saniti.join_report()["rows_out"] == 4


def test_saniti_join_refuses_two_series_on_one_date() -> None:
    saniti = bundle(runtime(), JOINED)
    index = pd.DataFrame([{"index_code": c, "date": "2026-08-03", "close": 7000} for c in ("IHSG", "LQ45")])
    with pytest.raises(saniti.JoinCardinalityError, match="unique"):
        saniti.join(40, stock_prices(), index)


def test_saniti_join_as_of_takes_the_latest_value_of_one_series() -> None:
    saniti = bundle(runtime(), {**JOINED, "relationship_id": 41, "join_semantics": "AS_OF",
                                "right_time_column": "period", "as_of_direction": "BACKWARD"})
    macro = pd.DataFrame([{"series_id": "BI_RATE", "period": "2026-07-01", "value": 6.0},
                          {"series_id": "BI_RATE", "period": "2026-08-04", "value": 5.75}])
    out = saniti.join(41, stock_prices(), macro)
    by_date = dict(zip(out[out["ticker"] == "BBCA"]["date"], out[out["ticker"] == "BBCA"]["value"]))
    assert by_date == {"2026-08-03": 6.0, "2026-08-04": 5.75, "2026-08-05": 5.75}
