#!/usr/bin/env python3
"""Exercise Release 1B tools live under market_ai_reader, without OpenAI calls."""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "market-ai-backend"
sys.path.insert(0, str(APP))

from app.config import Settings  # noqa: E402
from app.compaction import compact_result  # noqa: E402
from app.db import Database  # noqa: E402
from app.tools import ToolError, ToolRegistry  # noqa: E402


def with_reader_role(url: str) -> str:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("options", "-c role=market_ai_reader"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, quote_via=quote), parts.fragment))


def main() -> None:
    source_url = os.environ.get("DATABASE_URL", "")
    if not source_url:
        raise RuntimeError("DATABASE_URL is required")
    os.environ["DATABASE_URL"] = with_reader_role(source_url)
    settings = Settings.from_env(require_runtime_secrets=False)
    db = Database(settings.database_url, settings.query_timeout_seconds)
    db.open()
    try:
        tools = ToolRegistry(db, settings)
        definitions = tools.definitions({"META", "DISCOVERY", "QUALITY", "QUERY", "SCREENING"})
        core_definitions = tools.definitions(ToolRegistry.CORE_FAMILIES)
        core_names = {item["name"] for item in core_definitions}
        assert "record_evidence" in core_names
        assert "get_analysis_history" not in core_names
        table_result = tools.execute("list_feature_tables", {"include_columns": False}, "test")
        tables = [row["table_name"] for row in table_result.payload["rows"]]
        expected = {"Feature_01_Stock_Daily", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily"}
        assert expected <= set(tables), tables

        freshness = tools.execute("check_data_freshness", {"tables": sorted(expected)}, "test")
        ready = date.fromisoformat(freshness.payload["analysis_ready_date"])
        start = ready - timedelta(days=30)
        discovery = tools.execute("find_features", {"search_text": "return", "tables": ["Feature_01_Stock_Daily"], "limit": 20}, "test")
        assert discovery.payload["total_rows"] > 0
        multi_discovery = tools.execute("find_features", {
            "search_text": "close return", "tables": ["Feature_01_Stock_Daily"], "limit": 40,
        }, "test")
        multi_columns = {row["feature_column"] for row in multi_discovery.payload["rows"]}
        assert {"close", "return_20d_pct"} <= multi_columns
        assert multi_discovery.payload["search_mode"] == "whitespace_keywords_or"
        compact_discovery, _, was_compacted = compact_result(
            multi_discovery.payload,
            max_rows=settings.llm_tool_result_max_rows,
            max_bytes=settings.llm_tool_result_max_bytes,
            max_tokens=settings.ai_max_tool_result_tokens_per_call,
        )
        assert not was_compacted, compact_discovery.get("selection")
        assert len(compact_discovery["rows"]) == multi_discovery.payload["total_rows"]

        quality = tools.execute("check_data_quality", {
            "table": "Feature_01_Stock_Daily", "tickers": ["BBCA"],
            "start_date": start.isoformat(), "end_date": ready.isoformat(),
        }, "test")
        assert quality.payload["classification"] in {"PASS", "WARNING"}
        assert quality.payload["policy"].startswith("Source-valid extremes")

        query = {
            "table": "Feature_01_Stock_Daily", "columns": ["date", "ticker", "close", "return_1d_pct"],
            "tickers": ["BBCA"], "start_date": start.isoformat(), "end_date": ready.isoformat(),
            "filters": None, "order_by": [{"column": "date", "direction": "asc"}], "limit": 100,
        }
        estimate = tools.execute("estimate_query_size", query, "test")
        rows = tools.execute("query_features", query, "test")
        assert estimate.payload["valid"] and rows.payload["rows"]
        assert rows.query_hash == estimate.query_hash

        rejected = False
        try:
            tools.execute("query_features", {**query, "columns": ["raw_price"]}, "test")
        except ToolError:
            rejected = True
        assert rejected, "Unregistered columns must be rejected"

        market_board = tools.execute("get_feature_definition", {
            "features": [{"table": "Feature_03_Stock_Broker_Daily", "column": "market_board"}],
        }, "test")
        market_board_meta = market_board.payload["rows"][0]
        assert market_board_meta["semantic_role"] == "IDENTITY"
        assert market_board_meta["is_filterable"] is True
        assert market_board_meta["is_groupable"] is True
        assert set(market_board_meta["allowed_aggregations"]) == {"COUNT", "COUNT_DISTINCT"}
        assert market_board_meta["analytical_interpretation"]
        assert market_board_meta["recommended_use"]
        assert market_board_meta["misuse_warning"]
        assert market_board_meta["semantic_review_status"] == "CALCULATION_VERIFIED"
        assert len(market_board_meta["validation_evidence"]) >= 3

        aggregation = tools.execute("aggregate_features", {
            "table": "Feature_03_Stock_Broker_Daily", "group_by": ["market_board"],
            "metrics": [{"column": "total_buy_value", "aggregation": "SUM"}],
            "tickers": ["BBCA"], "start_date": start.isoformat(), "end_date": ready.isoformat(), "limit": 10,
        }, "test")
        assert aggregation.payload["rows"]
        boards = {row["market_board"] for row in aggregation.payload["rows"]}
        assert boards == {"Regular", "Nego", "Tunai"}, boards
        print(json.dumps({
            "status": "PASS", "active_tool_definitions": len(definitions),
            "feature_tables": tables, "analysis_ready_date": ready.isoformat(),
            "quality": quality.payload["classification"], "query_rows": rows.payload["total_rows"],
            "aggregate_groups": aggregation.payload["total_rows"],
            "market_board_catalog_audit": "PASS", "semantic_contract_audit": "PASS",
            "multi_keyword_discovery": "PASS", "discovery_identifier_preservation": "PASS",
            "always_exposed_evidence": "PASS", "history_not_core": True,
            "market_boards": sorted(boards),
            "raw_column_rejected": rejected,
        }))
    finally:
        db.close()


if __name__ == "__main__":
    main()
