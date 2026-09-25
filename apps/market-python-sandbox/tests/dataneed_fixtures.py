"""Catalog contract and DataNeedSpecs for the DataNeed tests.

The catalog has the shape of the Governor's POST /v1/catalog/contract after migration 20260925_003: relationships
carry supported_join_semantics and their time / effective-date columns, columns carry resample_aggregation. Two
synthetic point-in-time reference tables exercise AS_OF and EFFECTIVE_DATED, which no live table uses yet.
"""
from __future__ import annotations

import copy
from typing import Any

from conftest import CATALOG, SOURCE_CONTRACTS, _catalog_table, _columns, _contract

SOURCE_CONTRACTS.setdefault("Shares_Outstanding", _contract("Shares_Outstanding", ["ticker", "effective_date"],
                                                            "ticker", "effective_date"))
SOURCE_CONTRACTS.setdefault("Classification_History", _contract("Classification_History", ["Ticker", "valid_from"],
                                                                "Ticker", None))
SOURCE_CONTRACTS.setdefault("Index_Level_Daily", _contract("Index_Level_Daily", ["index_code", "date"], "index_code",
                                                           "date", "INDEX", None))


def data_need_catalog() -> dict[str, Any]:
    catalog = copy.deepcopy(CATALOG)
    for name in ("Shares_Outstanding", "Classification_History", "Index_Level_Daily", "Feature_02_Broker_Rolling"):
        catalog["tables"][name] = _catalog_table(SOURCE_CONTRACTS[name], "Synthetic point-in-time table.")
    catalog["columns"]["Feature_02_Broker_Rolling"] = _columns({
        "ticker": ("text", True, True), "market_board": ("text", True, True), "broker": ("text", True, True),
        "investor_type": ("text", True, True), "date": ("date", True, True), "net_value": ("numeric", True, False)})
    catalog["columns"]["IDX_Stock_Universe"].update(_columns({"Country": ("text", True, True),
                                                              "Status": ("text", True, True)}))
    catalog["columns"]["Shares_Outstanding"] = _columns({"ticker": ("text", True, True),
                                                         "effective_date": ("date", True, True),
                                                         "shares": ("bigint", True, False)})
    catalog["columns"]["Classification_History"] = _columns({"Ticker": ("text", True, True),
                                                             "Sector": ("text", True, True),
                                                             "valid_from": ("date", True, True),
                                                             "valid_to": ("date", True, True)})
    catalog["columns"]["Index_Level_Daily"] = _columns({"index_code": ("text", True, True), "date": ("date", True, True),
                                                        "close": ("numeric", True, False)})
    for info in catalog["columns"].values():
        for column in info.values():
            column.setdefault("resample_aggregation", None)
    for column, rule in (("open", "FIRST"), ("high", "MAX"), ("low", "MIN"), ("close", "LAST"), ("volume", "SUM")):
        catalog["columns"]["Price_Stock_Indonesia_IDX"][column]["resample_aggregation"] = rule
    blank = {"left_time_column": None, "right_time_column": None, "effective_from_column": None,
             "effective_to_column": None}
    catalog["relationships"][0].update({**blank, "supported_join_semantics": ["EXACT_DATE"],
                                        "left_time_column": "date", "right_time_column": "date"})
    catalog["relationships"][1].update({**blank, "supported_join_semantics": ["CURRENT_STATE"]})
    catalog["relationships"] += [
        {"relationship_id": 3, "left_table": "Price_Stock_Indonesia_IDX", "left_columns": ["ticker", "date"],
         "right_table": "Shares_Outstanding", "right_columns": ["ticker", "effective_date"],
         "relationship_type": "MANY_TO_ONE", "temporal_rule": "Latest shares at or before the trading date",
         "safe_output_grain": "date x ticker", "requires_preaggregation": False, "is_allowed": True, "version": "v1",
         **blank, "supported_join_semantics": ["AS_OF"], "left_time_column": "date",
         "right_time_column": "effective_date"},
        {"relationship_id": 4, "left_table": "Price_Stock_Indonesia_IDX", "left_columns": ["ticker"],
         "right_table": "Classification_History", "right_columns": ["Ticker"], "relationship_type": "MANY_TO_ONE",
         "temporal_rule": "Classification valid on the trading date", "safe_output_grain": "date x ticker",
         "requires_preaggregation": False, "is_allowed": True, "version": "v1", **blank,
         "supported_join_semantics": ["EFFECTIVE_DATED", "CURRENT_STATE"], "effective_from_column": "valid_from",
         "effective_to_column": "valid_to"},
        {"relationship_id": 5, "left_table": "Price_Stock_Indonesia_IDX", "left_columns": ["ticker"],
         "right_table": "IDX_Broker_Profile", "right_columns": ["broker_code"], "relationship_type": "MANY_TO_ONE",
         "temporal_rule": "Disallowed for testing", "safe_output_grain": "date x ticker",
         "requires_preaggregation": False, "is_allowed": False, "version": "v1", **blank,
         "supported_join_semantics": ["CURRENT_STATE"]},
    ]
    return catalog


def subset(catalog: dict[str, Any], tables: list[str]) -> dict[str, Any]:
    found = [t for t in tables if t in catalog["tables"]]
    return {**catalog, "tables": {t: catalog["tables"][t] for t in found},
            "columns": {t: catalog["columns"][t] for t in found},
            "relationships": [r for r in catalog["relationships"]
                              if r["left_table"] in found or r["right_table"] in found],
            "unknown_tables": [t for t in tables if t not in catalog["tables"]]}


def prices(rid: str = "data_request_1_A", **overrides: Any) -> dict[str, Any]:
    request = {
        "data_request_id": rid, "logical_name": "prices", "source_table": "Price_Stock_Indonesia_IDX",
        "entity_column": "ticker", "time_column": "date",
        "columns": ["ticker", "date", "open", "high", "low", "close", "volume"], "scope": {"type": "ALL"},
        "time_ranges": [{"range_id": "current_ytd", "start": "2026-01-01", "end": "2026-09-25"},
                        {"range_id": "previous_comparable", "start": "2025-01-01", "end": "2025-09-25"}],
        "source_frequency": "1D", "analysis_frequency": "1D", "resample": None,
        "history_buffer": {"value": 1, "unit": "TRADING_OBSERVATIONS"}, "future_buffer": None,
        "ordering": [{"column": "ticker", "direction": "ASC"}, {"column": "date", "direction": "ASC"}],
        "sampling_allowed": False}
    request.update(overrides)
    return request


def classification(rid: str = "data_request_1_B", **overrides: Any) -> dict[str, Any]:
    request = {
        "data_request_id": rid, "logical_name": "stock_classification", "source_table": "IDX_Stock_Universe",
        "entity_column": "Ticker", "time_column": None, "columns": ["Ticker", "Sector", "Industry"],
        "scope": {"type": "PREDICATE", "column": "Industry", "operator": "EQ", "value": "Banks"},
        "time_ranges": [], "source_frequency": "STATIC", "analysis_frequency": "STATIC", "resample": None,
        "history_buffer": None, "future_buffer": None, "ordering": [], "sampling_allowed": False}
    request.update(overrides)
    return request


def current_state(**overrides: Any) -> dict[str, Any]:
    relationship = {"relationship_id": 2, "left_request_id": "data_request_1_A", "left_column": "ticker",
                    "right_request_id": "data_request_1_B", "right_column": "Ticker", "join_type": "INNER",
                    "join_semantics": "CURRENT_STATE", "left_time_column": None, "right_time_column": None,
                    "as_of_direction": None, "effective_from_column": None, "effective_to_column": None}
    relationship.update(overrides)
    return relationship


def ytd_spec(**overrides: Any) -> dict[str, Any]:
    """The architecture document's YTD comparison (banks this year versus the same period last year)."""
    spec = {"spec_version": "data_need_spec/v1", "request_group_id": "data_request_1", "revision": 1,
            "mode": "ANALYSIS",
            "question": "Bandingkan performa YTD saham bank tahun ini dengan periode yang sama tahun lalu.",
            "subject": {"data_domain": "MARKET", "entity_type": "STOCK", "asset_type": "IDX_EQUITY"},
            "data_requests": [prices(), classification()], "relationships": [current_state()]}
    spec.update(overrides)
    return spec
