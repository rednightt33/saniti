#!/usr/bin/env python3
"""Synchronize the database table catalog and generate DATABASE_SCHEMA.md."""

from __future__ import annotations

import argparse
import os
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg import sql


STATUS_TABLE = "Database_Table_Status"
TABLE_STATUS_RULES = {
    "Database_Table_Status": ("System", "Automatic / daily documentation refresh"),
    "Table_Catalog": ("Reference", "After approved table metadata changes"),
    "Column_Catalog": ("Reference", "After approved column metadata changes"),
    "Feature_Relationship_Catalog": ("Reference", "After a validated Feature join contract changes"),
    "Tool_Catalog": ("Reference", "With each approved backend or analytics tool release"),
    "Analysis_Request": ("System", "One lifecycle per submitted AI analysis"),
    "Analysis_Model_Call": ("System", "One row after every provider model response; retained reasoning is purged by policy"),
    "Analysis_Step_Log": ("System", "After each AI analysis tool or compaction step"),
    "Analysis_Evidence": ("System", "When compact evidence is recorded for an analysis"),
    "Golden_Analysis_Test": ("System", "After a versioned golden analytical expectation changes"),
    "Golden_Analysis_Test_Run": ("System", "Before major releases and material model, prompt, Feature, or tool changes"),
    "Golden_Analysis_Test_Result": ("System", "After each test in a golden-suite run"),
    "Feature_01_Stock_Daily": ("Feature", "After validated daily-price changes"),
    "Feature_02_Broker_Rolling": ("Feature", "After validated broker-summary changes; manual backfill in v1"),
    "Feature_02_Broker_Rolling_v2": ("Feature", "Unreleased shadow rebuild; no production refresh or AI cutover"),
    "Feature_03_Stock_Broker_Daily": ("Feature", "After Feature 02 refresh; manual refresh in v1"),
    "Feature_Calculation_Queue": ("System", "After committed price inserts/updates and worker transitions"),
    "Feature_Status": ("System", "After enqueue and worker state transitions"),
    "Feature_Calculation_Log": ("System", "After completed worker attempts"),
    "Feature_Catalog": ("Reference", "After each validated Feature schema change"),
    "IDX_Broker_Profile": ("Reference", "Periodic / approximately annual"),
    "IDX_Broker_Summary": ("Transactional", "Continuous / each loaded trading day"),
    "IDX_Stock_Universe": ("Reference", "Periodic / when the listed universe changes"),
    "Monitoring_Price_ALL": ("System", "Twice daily alongside IDX price automation"),
    "Telegram_Command_Log": ("System", "Event-driven / when an authorized Telegram command is received"),
    "Telegram_Notification_Log": ("System", "Event-driven / after a monitored job completes"),
    "Universe_Equity_Description": ("Reference", "Periodic / when equity descriptions change"),
    "Price_Stock_Indonesia_IDX": ("Transactional", "Periodic / when daily IDX prices are refreshed"),
    "stockbit_broker_summary_load_log": ("System", "Continuous / alongside broker-summary loads"),
}
TRACKED_CHANGE_TABLES = (
    "Table_Catalog",
    "Column_Catalog",
    "Feature_01_Stock_Daily",
    "Feature_02_Broker_Rolling",
    "Feature_03_Stock_Broker_Daily",
    "Feature_Catalog",
    "IDX_Broker_Profile",
    "IDX_Stock_Universe",
    "Universe_Equity_Description",
    "Price_Stock_Indonesia_IDX",
    "Telegram_Command_Log",
    "Telegram_Notification_Log",
)
TABLE_DESCRIPTIONS = {
    "Database_Table_Status": "Tracks the data freshness, change time, and update pattern of each table.",
    "Table_Catalog": "Curated meanings, grain, provenance, and update contracts for approved public data tables.",
    "Column_Catalog": "Physical column inventory and evidence-graded semantic definitions for approved tables.",
    "Feature_Relationship_Catalog": "Versioned safe-join and grain contracts between verified Feature tables.",
    "Tool_Catalog": "Versioned generic AI tool registry, schemas, activation state, and advertised operational ceilings.",
    "Analysis_Request": "Durable AI analysis lifecycle, compact result, version snapshot, methodology metadata, and token usage.",
    "Analysis_Model_Call": "Per-provider-call usage, tool exposure, decision summary, and temporarily retained provider-returned reasoning audit.",
    "Analysis_Step_Log": "Audit record for each AI query, tool, compaction, or analytical step.",
    "Analysis_Evidence": "Compact reproducible evidence supporting material AI analysis claims.",
    "Golden_Analysis_Test": "Versioned analytical correctness, methodology, and safety expectations.",
    "Golden_Analysis_Test_Run": "Historical execution record for one complete golden analytical suite.",
    "Golden_Analysis_Test_Result": "Per-test observed metrics, warnings, evidence, latency, and token outcome.",
    "Feature_01_Stock_Daily": "Daily ticker-level price, return, volatility, volume, and price-position features.",
    "Feature_02_Broker_Rolling": "Broker flow, persistence, abnormality, and accumulation by source ticker, broker, board, and transaction date.",
    "Feature_02_Broker_Rolling_v2": "Unreleased Investor-Type-preserving Feature 02 shadow used only for staged rebuild and validation.",
    "Feature_03_Stock_Broker_Daily": "Stock-level daily broker breadth, classified flow, dominant-broker, and concentration features separated by market board.",
    "Feature_Calculation_Queue": "Durable work item per changed Feature 01 source candle.",
    "Feature_Status": "Current price-driven Feature 01 calculation state per ticker.",
    "Feature_Calculation_Log": "Completed Feature 01 worker attempt and retry history.",
    "Feature_Catalog": "Machine-readable semantic, availability, and usage contract for validated Feature columns.",
    "IDX_Broker_Profile": "Reference list of IDX broker codes, names, and domestic/foreign classification.",
    "IDX_Broker_Summary": "Daily broker buy/sell activity by symbol, broker, investor type, and market board.",
    "IDX_Stock_Universe": "Reference universe of Indonesian listed securities and TradingView fundamentals.",
    "Monitoring_Price_ALL": "Operational results for daily and recovery IDX price-update runs.",
    "Telegram_Command_Log": "Inbound Telegram command audit and duplicate-prevention ledger for telegram-trigger.",
    "Telegram_Notification_Log": "Delivery ledger used by telegram-monitor to prevent duplicate notifications.",
    "Universe_Equity_Description": "Reference descriptions and sector classifications for the Indonesian equity universe.",
    "Price_Stock_Indonesia_IDX": "Daily Indonesian stock OHLCV prices sourced from TradingView.",
    "stockbit_broker_summary_load_log": "Audit log used to resume and verify Stockbit broker-summary loads by date.",
}
COLUMN_DESCRIPTIONS = {
    "Table_Catalog": {
        "table_schema": "Physical PostgreSQL schema containing the cataloged table.",
        "table_name": "Exact case-sensitive physical table name.",
        "category": "Operational role: Reference, Transactional, Feature, or System.",
        "definition": "Human-readable purpose and meaning of the table.",
        "grain": "Business entity represented by one table row.",
        "primary_key_columns": "Ordered physical columns in the table primary key.",
        "source_system": "External system or internal process supplying the data, when known.",
        "source_tables": "Physical upstream tables used to populate or derive the table.",
        "source_code_paths": "Repository paths of relevant scripts and migrations.",
        "update_rule": "Event or process that changes table data.",
        "related_functions": "PostgreSQL routines directly related to this table.",
        "documentation_status": "Semantic confidence: VERIFIED, PARTIAL, or NEEDS_REVIEW.",
        "created_at": "Timestamp when the catalog row was created.",
        "updated_at": "Timestamp when the catalog row was last changed.",
        "readiness_mode": "Whether readiness is derived from a data date, reference state, or is not applicable.",
        "readiness_date_column": "Physical column used to derive the latest data date.",
        "observation_date_column": "Physical column representing the market or source observation date.",
        "data_available_at_column": "Physical timestamp proving when an observation became decision-available, when retained.",
        "availability_rule": "Conservative decision-time rule for historical use.",
        "point_in_time_status": "Availability status of point-in-time universe and metadata.",
        "historical_metadata_method": "Historical metadata method or explicitly disclosed current-state fallback.",
    },
    "Column_Catalog": {
        "table_schema": "Physical PostgreSQL schema containing the cataloged column.",
        "table_name": "Exact case-sensitive physical table name.",
        "column_name": "Exact case-sensitive physical column name.",
        "ordinal_position": "Column position in the physical table.",
        "data_type": "Physical PostgreSQL information_schema data type.",
        "is_nullable": "Whether PostgreSQL permits a NULL value in this column.",
        "default_expression": "Physical PostgreSQL default expression, when present.",
        "is_primary_key": "Whether the column participates in the primary key.",
        "definition": "Human-readable meaning of values stored in this column.",
        "source_column_or_expression": "Source reference or concise derivation; Feature_Catalog owns detailed Feature formulas.",
        "unit": "Semantic unit, when applicable.",
        "null_rule": "Meaning or rule for a NULL value, when documented.",
        "source_code_paths": "Repository paths supporting the column definition.",
        "documentation_status": "Semantic confidence: VERIFIED, PARTIAL, or NEEDS_REVIEW.",
        "created_at": "Timestamp when the catalog row was created.",
        "updated_at": "Timestamp when the catalog row was last changed.",
    },
    "Database_Table_Status": {
        "Table Name": "Exact PostgreSQL table name in the public schema.",
        "Table Category": "Operational role: Reference, Transactional, or System.",
        "Update Pattern": "Expected frequency or event that updates the table.",
        "Latest Data Date": "Latest business or trading date represented by the table, when applicable.",
        "Last Changed At": "UTC timestamp of the latest tracked data load or table change.",
        "Last Checked At": "UTC timestamp when the catalog last inspected the table.",
        "Tracking Status": "Explains whether freshness is derived, tracked, or only a baseline.",
        "Last Operation": "Last tracked operation, such as LOAD, INSERT, UPDATE, DELETE, or TRUNCATE.",
    },
    "Feature_01_Stock_Daily": {
        "date": "Trading observation date from Price_Stock_Indonesia_IDX.",
        "ticker": "IDX ticker; the table grain is one row per ticker and trading date.",
        "close": "Source closing price.",
        "volume": "Source trading volume.",
        "sector": "Current Sector inherited from IDX_Stock_Universe.",
        "industry": "Current Industry inherited from IDX_Stock_Universe.",
        "close_1d_ago": "Closing price one prior trading observation ago.",
        "close_5d_ago": "Closing price five prior trading observations ago.",
        "close_20d_ago": "Closing price twenty prior trading observations ago.",
        "close_60d_ago": "Closing price sixty prior trading observations ago.",
        "return_1d_pct": "Percent close return versus one prior trading observation.",
        "return_5d_pct": "Percent close return versus five prior trading observations.",
        "return_20d_pct": "Percent close return versus twenty prior trading observations.",
        "return_60d_pct": "Percent close return versus sixty prior trading observations.",
        "abs_return_1d_pct": "Absolute one-observation percent return.",
        "volatility_5d_ann_pct": "Annualized sample standard deviation of five daily decimal returns, in percent.",
        "volatility_20d_ann_pct": "Annualized sample standard deviation of twenty daily decimal returns, in percent.",
        "volatility_60d_ann_pct": "Annualized sample standard deviation of sixty daily decimal returns, in percent.",
        "volatility_5d_change_pct": "Percent change versus the five-day volatility from five observations ago.",
        "volatility_20d_change_pct": "Percent change versus the twenty-day volatility from twenty observations ago.",
        "volatility_60d_change_pct": "Percent change versus the sixty-day volatility from sixty observations ago.",
        "volume_avg_20d": "Average volume over a complete twenty-observation window.",
        "volume_std_20d": "Sample standard deviation of volume over a complete twenty-observation window.",
        "volume_ratio_20d": "Current volume divided by the complete twenty-observation average.",
        "volume_zscore_20d": "Current volume deviation from the twenty-observation average in standard deviations.",
        "high_20d": "Maximum close over a complete twenty-observation window.",
        "high_60d": "Maximum close over a complete sixty-observation window.",
        "drawdown_20d_pct": "Percent close position below the complete twenty-observation maximum close.",
        "drawdown_60d_pct": "Percent close position below the complete sixty-observation maximum close.",
    },
    "Feature_Catalog": {
        "feature_table": "Exact physical name of a verified table registered as category Feature.",
        "feature_column": "Exact physical PostgreSQL column name.",
        "grain": "Business grain represented by one row in the Feature table.",
        "feature_category": "Controlled semantic category for the feature.",
        "definition": "Human-readable meaning of the feature value.",
        "calculation": "Exact formula or ordered calculation logic used by the implementation.",
        "source_tables": "Pipe-delimited exact source-table names required by the calculation.",
        "source_columns": "Pipe-delimited exact source-column references used by the calculation.",
        "lookback_window": "Effective observation-based historical window.",
        "minimum_history": "Minimum valid observation history required for a usable value.",
        "unit": "Semantic unit of the feature value.",
        "null_rule": "Conditions under which the feature is NULL.",
        "refresh_trigger": "Upstream event that requires the feature to be recalculated.",
        "dependency_rule": "Upstream availability conditions required before the feature is valid.",
        "version": "Semantic-definition version; material formula changes require a new version.",
        "is_active": "Whether AI analytics may use this catalog definition.",
        "created_at": "Timestamp when this semantic version was created.",
        "updated_at": "Timestamp of the latest metadata change, maintained by trigger.",
        "semantic_role": "Generic query role: IDENTITY, DIMENSION, or MEASURE.",
        "allowed_aggregations": "Allow-list of valid generic aggregations for this column.",
        "ranking_interpretation": "Default ranking direction or requirement for request-specific context.",
        "is_filterable": "Whether generic tools may use this column in a structured filter.",
        "is_groupable": "Whether generic tools may use this column as a grouping dimension.",
        "availability_rule": "Earliest decision-time rule used by historical validation.",
        "point_in_time_safe": "Whether the value is time-indexed and safe under its documented availability rule.",
        "historical_metadata_warning": "Required disclosure for current-state or incomplete historical metadata.",
    },
    "IDX_Broker_Profile": {
        "broker_code": "Two-character IDX broker code.",
        "broker_name": "Registered broker or securities-company name.",
        "broker_type": "Broker classification: Domestic or Foreign.",
        "broker_classification": "Observed broker usage profile: Institutional-heavy, Retail-heavy, Mixed, or Niche; this is distinct from domestic/foreign broker_type.",
    },
    "IDX_Broker_Summary": {
        "Date": "Exchange trading date.",
        "Symbol": "IDX security ticker.",
        "Broker": "Two-character broker code.",
        "Investor Type": "Investor classification: Domestic or Foreign.",
        "Market Board": "IDX market board: Regular, Nego, or Tunai.",
        "Buy Value": "Gross purchase value for the key combination.",
        "Sell Value": "Gross sale value for the key combination.",
        "Net Value": "Buy Value minus Sell Value.",
        "Buy Lots": "Number of lots purchased.",
        "Sell Lots": "Number of lots sold.",
        "Net Lots": "Buy Lots minus Sell Lots.",
        "Avg Buy": "Average purchase price when supplied by Stockbit.",
        "Avg Sell": "Average sale price when supplied by Stockbit.",
    },
    "IDX_Stock_Universe": {
        "Region": "Geographic market region.",
        "Country": "Country represented by the listing.",
        "Company Name": "Issuer or company name.",
        "Ticker": "IDX ticker and primary identifier for this table.",
        "Exchange": "Exchange on which the security is listed.",
        "TradingView Symbol": "Symbol used by TradingView.",
        "TradingView URL": "TradingView instrument page URL.",
        "Security Type": "Broad security classification.",
        "Type Specs": "More specific security-type detail.",
        "Is Common Stock": "Source flag indicating whether the security is common stock.",
        "Sector": "Source sector classification.",
        "Sector Translated": "Translated sector classification.",
        "Industry": "Source industry classification.",
        "Industry Translated": "Translated industry classification.",
        "TradingView Country": "Country value used by TradingView.",
        "Currency": "Trading currency.",
        "Fundamental Currency": "Currency used for fundamental figures.",
        "Average Volume 10D": "Average trading volume over the latest 10-day source window.",
        "Market Cap": "Market capitalization when available.",
        "Number of Shareholders": "Reported shareholder count when available.",
        "Number of Employees": "Reported employee count when available.",
        "ISIN": "International Securities Identification Number.",
    },
    "Monitoring_Price_ALL": {
        "id": "Generated monitoring-row identifier.",
        "execution_id": "Identifier shared by all grouped monitoring rows from one service execution.",
        "trigger_source": "Execution origin inferred from the service schedule window: SCHEDULED or MANUAL.",
        "query_time": "UTC timestamp immediately before TradingView requests began.",
        "exchange": "Exchange copied from IDX_Stock_Universe for the monitored group.",
        "asset_type": "Security Type copied from IDX_Stock_Universe for the monitored group.",
        "timeframe": "TradingView interval; fixed to 1d.",
        "run_type": "Scheduled phase: DAILY at 17:00 WIB or RECOVERY at 06:00 WIB.",
        "expected_symbols": "Distinct universe tickers in the exchange and asset-type group at run time.",
        "queried_symbols": "Symbols sent to TradingView during this run.",
        "updated_symbols": "Symbols verified in the price table after bulk upsert.",
        "missing_symbols": "Queried symbols still missing after this run.",
        "missing_symbol_list": "JSON array of tickers still missing after this run.",
        "update_for_date": "Trading date targeted by the run.",
        "run_time": "UTC timestamp when the run started; display in Asia/Jakarta when needed.",
        "finished_at": "UTC timestamp when the run completed.",
        "attempt_count": "Automation attempt number: 1 for DAILY and 2 for RECOVERY.",
        "status": "Run result: SUCCESS, PARTIAL, FAILED, SKIPPED, or NEEDS_REVIEW.",
        "last_error": "Condensed failure detail when a run did not fully succeed.",
        "created_at": "UTC timestamp when the monitoring row was first created.",
        "updated_at": "UTC timestamp when the monitoring row was last refreshed.",
    },
    "Telegram_Command_Log": {
        "id": "Generated inbound-command identifier.",
        "telegram_update_id": "Unique Telegram update identifier used to reject webhook retries.",
        "chat_id": "Telegram chat that requested the action; only the configured owner is accepted.",
        "command": "Allowlisted action requested from the bot.",
        "target_service": "Fixed Railway service selected by the allowlisted command.",
        "requested_at": "UTC timestamp when telegram-trigger accepted the update.",
        "triggered_at": "UTC timestamp when Railway accepted the Run Now request.",
        "finished_at": "UTC timestamp when a trigger request failed before Railway accepted it.",
        "status": "Trigger state: RECEIVED, TRIGGERED, BLOCKED, or FAILED.",
        "railway_reference": "Allowlisted Railway service-instance identifier used for Run Now.",
        "last_error": "Cooldown reason or condensed trigger failure detail.",
        "created_at": "UTC timestamp when the command row was created.",
        "updated_at": "UTC timestamp when the command row was last changed.",
    },
    "Telegram_Notification_Log": {
        "id": "Generated Telegram delivery-log identifier.",
        "source_table": "Monitoring table from which notification details are read.",
        "source_execution_id": "Execution identifier in the source monitoring table.",
        "notification_type": "Notification event type; currently COMPLETED.",
        "send_status": "Delivery state: PENDING, SENDING, SENT, or FAILED.",
        "attempt_count": "Number of claimed Telegram delivery attempts.",
        "telegram_message_ids": "JSON array of Telegram message IDs returned after delivery.",
        "sent_at": "UTC timestamp when all Telegram message parts were sent.",
        "last_error": "Most recent Telegram delivery error; cleared after success.",
        "created_at": "UTC timestamp when the delivery record was created.",
        "updated_at": "UTC timestamp when the delivery record last changed.",
    },
    "Universe_Equity_Description": {
        "Region": "Geographic market region.",
        "Market": "Market-development classification.",
        "Country": "Country represented by the listing.",
        "Exchange": "Exchange on which the security is listed.",
        "Ticker": "Four-character IDX ticker and primary identifier for this table.",
        "Company_Name": "Issuer or security name.",
        "TV_Sector": "TradingView sector classification.",
        "TV_Industry": "TradingView industry classification.",
        "ISIN": "Unique International Securities Identification Number.",
        "Sector": "IDX or curated sector classification.",
        "Industry": "IDX or curated industry classification.",
    },
    "Price_Stock_Indonesia_IDX": {
        "company_name": "Listed company name.",
        "ticker": "Four-character IDX ticker.",
        "tradingview_symbol": "TradingView exchange-qualified symbol.",
        "date": "Trading date represented by the price row.",
        "open": "Opening price.",
        "high": "Highest price.",
        "low": "Lowest price.",
        "close": "Closing price.",
        "volume": "Trading volume reported by the source.",
        "source": "Price data source.",
        "query_date": "Date the source data was queried.",
        "timeframe": "Price-series interval.",
        "ingestion_time": "Timezone-aware database statement time of the latest successful insert or upsert for this price row; null for historical rows whose exact ingestion time is unknown.",
    },
    "stockbit_broker_summary_load_log": {
        "target_table": "Schema-qualified table populated by the load.",
        "trade_date": "Trading date covered by this load record.",
        "status": "Per-date state: COMPLETED or NEEDS_REVIEW.",
        "filter_count": "Number of broker/investor/board combinations processed.",
        "request_count": "Number of Stockbit API requests made.",
        "row_count": "Number of summary rows stored for the trading date.",
        "response_bytes": "Total Stockbit response payload size in bytes.",
        "fetch_elapsed_ms": "Cumulative API request duration in milliseconds.",
        "completed_at": "UTC timestamp when the date completed successfully; null while NEEDS_REVIEW.",
        "attempt_count": "Cumulative number of date-level attempts across supervisor restarts.",
        "last_error": "Most recent error for a date; cleared after a successful load.",
        "last_attempt_at": "UTC timestamp of the latest attempt.",
        "status_changed_at": "UTC timestamp when this date's status was last changed.",
    },
}
LOGICAL_RELATIONSHIPS = [
    (
        'Table_Catalog.(table_schema, table_name)',
        'Approved physical public tables',
        "Governed semantic reference",
        "Exactly the approved table set is registered; Database_Table_Status remains a separate freshness monitor.",
    ),
    (
        'Column_Catalog.(table_schema, table_name)',
        'Table_Catalog.(table_schema, table_name)',
        "Enforced foreign key",
        "Each cataloged physical column belongs to a registered table; physical facts are reconciled from PostgreSQL.",
    ),
    (
        'IDX_Broker_Summary."Broker"',
        'IDX_Broker_Profile.broker_code',
        "Logical",
        "Broker activity uses the broker-code reference. No database foreign key is enforced.",
    ),
    (
        'IDX_Broker_Summary."Symbol"',
        'IDX_Stock_Universe."Ticker"',
        "Logical",
        "Broker activity symbols map to the stock universe when a matching ticker exists. No database foreign key is enforced.",
    ),
    (
        'Universe_Equity_Description."Ticker"',
        'IDX_Stock_Universe."Ticker"',
        "Logical one-to-one by ticker",
        "Both reference tables describe the same listed security when a matching ticker exists. No database foreign key is enforced.",
    ),
    (
        'Price_Stock_Indonesia_IDX.ticker',
        'IDX_Stock_Universe."Ticker"',
        "Logical many-to-one by ticker",
        "Daily price rows map to the stock universe when a matching ticker exists. No database foreign key is enforced.",
    ),
    (
        'Feature_01_Stock_Daily.(ticker, date)',
        'Price_Stock_Indonesia_IDX.(ticker, date)',
        "Logical one-to-one by ticker and trading date",
        "Each feature row is derived from exactly one available price candle. No database foreign key is enforced.",
    ),
    (
        'Feature_01_Stock_Daily.ticker',
        'IDX_Stock_Universe."Ticker"',
        "Logical many-to-one by ticker",
        "Feature classifications use the current Sector and Industry values from the stock universe. No database foreign key is enforced.",
    ),
    (
        'Feature_Catalog.(feature_table, feature_column)',
        'Locked Feature table physical columns',
        "Governed semantic reference",
        "Active catalog rows are validated by trigger against exact physical columns in the public schema.",
    ),
    (
        'Monitoring_Price_ALL.asset_type',
        'IDX_Stock_Universe."Security Type"',
        "Logical grouped snapshot",
        "Monitoring rows group expected and missing ticker counts by the universe Security Type value.",
    ),
    (
        'Monitoring_Price_ALL.update_for_date',
        'Price_Stock_Indonesia_IDX.date',
        "Logical",
        "A monitoring date describes the daily-price date targeted by an automation run.",
    ),
    (
        'Telegram_Notification_Log.source_execution_id',
        'Monitoring_Price_ALL.execution_id',
        "Logical many-to-one by execution",
        "The notifier reads all monitoring rows for one execution before sending and recording delivery. No database foreign key is enforced.",
    ),
]


def markdown(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def code(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return f"`{str(value).replace('`', '``')}`"


def table_names(connection: psycopg.Connection[Any], schema: str) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (schema,),
        ).fetchall()
    ]


def ensure_status_table(connection: psycopg.Connection[Any], schema: str) -> None:
    create_statement = sql.SQL(
        """
        CREATE TABLE IF NOT EXISTS {}.{} (
            "Table Name" text PRIMARY KEY,
            "Table Category" text NOT NULL,
            "Update Pattern" text NOT NULL,
            "Latest Data Date" date,
            "Last Changed At" timestamptz,
            "Last Checked At" timestamptz NOT NULL,
            "Tracking Status" text NOT NULL,
            "Last Operation" text
        )
        """
    ).format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    connection.execute(create_statement)

    existing_columns = {
        row[0]
        for row in connection.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (schema, STATUS_TABLE),
        ).fetchall()
    }
    target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    if "Last Updated" in existing_columns and "Last Checked At" not in existing_columns:
        connection.execute(
            sql.SQL('ALTER TABLE {} RENAME COLUMN "Last Updated" TO "Last Checked At"').format(target)
        )

    additions = (
        ('"Table Category"', "text NOT NULL DEFAULT 'Unclassified'"),
        ('"Update Pattern"', "text NOT NULL DEFAULT 'Unknown'"),
        ('"Latest Data Date"', "date"),
        ('"Last Changed At"', "timestamptz"),
        ('"Last Checked At"', "timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP"),
        ('"Tracking Status"', "text NOT NULL DEFAULT 'Baseline'"),
        ('"Last Operation"', "text"),
    )
    for column_name, definition in additions:
        connection.execute(
            sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} {}").format(
                target, sql.SQL(column_name), sql.SQL(definition)
            )
        )


def existing_status(connection: psycopg.Connection[Any], schema: str) -> dict[str, dict[str, Any]]:
    target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    rows = connection.execute(
        sql.SQL(
            'SELECT "Table Name", "Last Changed At", "Tracking Status", "Last Operation" FROM {}'
        ).format(target)
    ).fetchall()
    return {
        name: {"last_changed_at": changed_at, "tracking_status": tracking, "last_operation": operation}
        for name, changed_at, tracking, operation in rows
    }


def derive_status_rows(
    connection: psycopg.Connection[Any], schema: str, names: list[str], refreshed_at: datetime
) -> list[tuple[Any, ...]]:
    previous = existing_status(connection, schema)
    rows: list[tuple[Any, ...]] = []
    for name in names:
        category, pattern = TABLE_STATUS_RULES.get(name, ("Unclassified", "Unknown"))
        latest_data_date = None
        last_changed_at = previous.get(name, {}).get("last_changed_at")
        tracking_status = previous.get(name, {}).get("tracking_status") or "Baseline"
        last_operation = previous.get(name, {}).get("last_operation")

        if name in {"Feature_01_Stock_Daily", "Feature_02_Broker_Rolling", "Feature_03_Stock_Broker_Daily"}:
            latest_data_date = connection.execute(
                sql.SQL('SELECT max("date") FROM {}.{}').format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            ).fetchone()[0]
            if last_changed_at is None:
                last_changed_at = refreshed_at
                last_operation = "BACKFILL"
            if name == "Feature_01_Stock_Daily":
                tracking_status = "Derived from Price_Stock_Indonesia_IDX"
            elif name == "Feature_02_Broker_Rolling":
                tracking_status = "Derived from IDX_Broker_Summary; Feature 02 refresh is manual"
            else:
                tracking_status = "Derived from Feature_02_Broker_Rolling; Feature 03 refresh is manual"
        elif name == "Feature_Calculation_Queue":
            latest_data_date, changed = connection.execute(
                sql.SQL("SELECT max(price_date), max(updated_at) FROM {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            ).fetchone()
            last_changed_at = changed or last_changed_at
            tracking_status = "Derived from queue rows"
            last_operation = "ENQUEUE_OR_WORKER_UPDATE"
        elif name == "Feature_Status":
            latest_data_date, changed = connection.execute(
                sql.SQL("SELECT max(latest_price_date), max(updated_at) FROM {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            ).fetchone()
            last_changed_at = changed or last_changed_at
            tracking_status = "Derived from per-ticker status rows"
            last_operation = "STATUS_RECONCILE"
        elif name == "Feature_Calculation_Log":
            latest_data_date, changed = connection.execute(
                sql.SQL("SELECT max(price_date), max(finished_at) FROM {}.{}").format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            ).fetchone()
            last_changed_at = changed or last_changed_at
            tracking_status = "Derived from attempt log rows"
            last_operation = "ATTEMPT_RESULT"
        elif name == "IDX_Broker_Summary":
            latest_data_date = connection.execute(
                sql.SQL('SELECT max("Date") FROM {}.{}').format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            ).fetchone()[0]
            if "stockbit_broker_summary_load_log" in names:
                last_changed_at = connection.execute(
                    sql.SQL("SELECT max(completed_at) FROM {}.{} WHERE status = 'COMPLETED'").format(
                        sql.Identifier(schema), sql.Identifier("stockbit_broker_summary_load_log")
                    )
                ).fetchone()[0]
            tracking_status = "Derived from table data and load log"
            last_operation = "LOAD"
        elif name == "Price_Stock_Indonesia_IDX":
            latest_data_date = connection.execute(
                sql.SQL('SELECT max("date") FROM {}.{}').format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            ).fetchone()[0]
            if last_changed_at is None:
                last_changed_at = refreshed_at
                last_operation = "BASELINE"
            tracking_status = "Latest date derived; future changes tracked automatically"
        elif name == "Monitoring_Price_ALL":
            latest_data_date, last_changed_at = connection.execute(
                sql.SQL(
                    'SELECT max(update_for_date), max(updated_at) FROM {}.{}'
                ).format(sql.Identifier(schema), sql.Identifier(name))
            ).fetchone()
            tracking_status = "Derived from monitoring rows"
            last_operation = "UPSERT"
        elif name == "stockbit_broker_summary_load_log":
            latest_data_date, last_changed_at = connection.execute(
                sql.SQL(
                    "SELECT max(trade_date) FILTER (WHERE status = 'COMPLETED'), "
                    "max(status_changed_at) FROM {}.{}"
                ).format(
                    sql.Identifier(schema), sql.Identifier(name)
                )
            ).fetchone()
            tracking_status = "Derived from load log"
            last_operation = "LOAD"
        elif name == STATUS_TABLE:
            last_changed_at = refreshed_at
            tracking_status = "System-managed"
            last_operation = "CATALOG_REFRESH"
        elif name in TRACKED_CHANGE_TABLES:
            if last_changed_at is None:
                last_changed_at = refreshed_at
                last_operation = "BASELINE"
            if tracking_status in {"Baseline", "Baseline only"}:
                tracking_status = "Baseline; exact changes tracked from this time forward"
        elif last_changed_at is None:
            last_changed_at = refreshed_at
            tracking_status = "Baseline only"
            last_operation = "BASELINE"

        rows.append(
            (
                name,
                category,
                pattern,
                latest_data_date,
                last_changed_at,
                refreshed_at,
                tracking_status,
                last_operation,
            )
        )
    return rows


def refresh_status(
    connection: psycopg.Connection[Any], schema: str, names: list[str], refreshed_at: datetime
) -> None:
    target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    status_rows = derive_status_rows(connection, schema, names, refreshed_at)
    upsert = sql.SQL(
        """
        INSERT INTO {} (
            "Table Name", "Table Category", "Update Pattern", "Latest Data Date",
            "Last Changed At", "Last Checked At", "Tracking Status", "Last Operation"
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT ("Table Name") DO UPDATE
        SET "Table Category" = EXCLUDED."Table Category",
            "Update Pattern" = EXCLUDED."Update Pattern",
            "Latest Data Date" = EXCLUDED."Latest Data Date",
            "Last Changed At" = EXCLUDED."Last Changed At",
            "Last Checked At" = EXCLUDED."Last Checked At",
            "Tracking Status" = EXCLUDED."Tracking Status",
            "Last Operation" = EXCLUDED."Last Operation"
        """
    ).format(target)
    with connection.cursor() as cursor:
        cursor.executemany(upsert, status_rows)
    connection.execute(
        sql.SQL('DELETE FROM {} WHERE NOT ("Table Name" = ANY(%s))').format(target),
        (names,),
    )


def trigger_exists(
    connection: psycopg.Connection[Any], schema: str, table_name: str, trigger_name: str
) -> bool:
    return connection.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_trigger AS trigger
            JOIN pg_catalog.pg_class AS class ON class.oid = trigger.tgrelid
            JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = class.relnamespace
            WHERE namespace.nspname = %s
              AND class.relname = %s
              AND trigger.tgname = %s
              AND NOT trigger.tgisinternal
        )
        """,
        (schema, table_name, trigger_name),
    ).fetchone()[0]


def function_exists(connection: psycopg.Connection[Any], schema: str, function_name: str) -> bool:
    return connection.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM pg_catalog.pg_proc AS function
            JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = function.pronamespace
            WHERE namespace.nspname = %s AND function.proname = %s
        )
        """,
        (schema, function_name),
    ).fetchone()[0]


def ensure_reference_tracking(connection: psycopg.Connection[Any], schema: str, names: list[str]) -> None:
    status_target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    function_statement = sql.SQL(
        """
        CREATE OR REPLACE FUNCTION {}.track_database_table_change()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
            UPDATE {}
            SET "Last Changed At" = clock_timestamp(),
                "Tracking Status" = 'Tracked automatically',
                "Last Operation" = TG_OP
            WHERE "Table Name" = TG_TABLE_NAME;
            RETURN NULL;
        END;
        $function$
        """
    ).format(sql.Identifier(schema), status_target)
    if not function_exists(connection, schema, "track_database_table_change"):
        connection.execute(function_statement)

    for table_name in TRACKED_CHANGE_TABLES:
        if table_name not in names:
            continue
        trigger_name = "database_table_status_change_tracker"
        if trigger_exists(connection, schema, table_name, trigger_name):
            continue
        connection.execute(
            sql.SQL(
                "CREATE TRIGGER {} AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON {}.{} "
                "FOR EACH STATEMENT EXECUTE FUNCTION {}.track_database_table_change()"
            ).format(
                sql.Identifier(trigger_name),
                sql.Identifier(schema),
                sql.Identifier(table_name),
                sql.Identifier(schema),
            )
        )


def ensure_broker_load_tracking(connection: psycopg.Connection[Any], schema: str, names: list[str]) -> None:
    log_table = "stockbit_broker_summary_load_log"
    if log_table not in names or "IDX_Broker_Summary" not in names:
        return

    status_target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    log_target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(log_table))
    function_statement = sql.SQL(
        """
        CREATE OR REPLACE FUNCTION {}.track_broker_summary_load()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $function$
        BEGIN
            UPDATE {} AS table_status
            SET "Latest Data Date" = newest.latest_data_date,
                "Last Changed At" = newest.last_changed_at,
                "Last Operation" = 'LOAD'
            FROM (
                SELECT max(trade_date) AS latest_data_date,
                       max(completed_at) AS last_changed_at
                FROM {}
                WHERE status = 'COMPLETED'
            ) AS newest
            WHERE table_status."Table Name" IN (
                'IDX_Broker_Summary', 'stockbit_broker_summary_load_log'
            );
            RETURN NULL;
        END;
        $function$
        """
    ).format(sql.Identifier(schema), status_target, log_target)
    if not function_exists(connection, schema, "track_broker_summary_load"):
        connection.execute(function_statement)

    trigger_name = "database_table_status_load_tracker"
    if trigger_exists(connection, schema, log_table, trigger_name):
        return
    connection.execute(
        sql.SQL(
            "CREATE TRIGGER {} AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON {} "
            "FOR EACH STATEMENT EXECUTE FUNCTION {}.track_broker_summary_load()"
        ).format(sql.Identifier(trigger_name), log_target, sql.Identifier(schema))
    )


def fetch_status_rows(connection: psycopg.Connection[Any], schema: str) -> list[dict[str, Any]]:
    target = sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(STATUS_TABLE))
    rows = connection.execute(
        sql.SQL(
            """
            SELECT "Table Name", "Table Category", "Update Pattern", "Latest Data Date",
                   "Last Changed At", "Last Checked At", "Tracking Status", "Last Operation"
            FROM {}
            ORDER BY "Table Name"
            """
        ).format(target)
    ).fetchall()
    keys = (
        "table_name", "category", "pattern", "latest_data_date",
        "last_changed_at", "last_checked_at", "tracking_status", "last_operation",
    )
    return [dict(zip(keys, row)) for row in rows]


def fetch_columns(connection: psycopg.Connection[Any], schema: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = connection.execute(
        """
        SELECT
            columns.table_name,
            columns.column_name,
            columns.data_type,
            columns.udt_name,
            columns.is_nullable,
            columns.column_default,
            columns.ordinal_position,
            pg_catalog.col_description(class.oid, attributes.attnum) AS description
        FROM information_schema.columns AS columns
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.nspname = columns.table_schema
        JOIN pg_catalog.pg_class AS class
          ON class.relnamespace = namespace.oid
         AND class.relname = columns.table_name
        JOIN pg_catalog.pg_attribute AS attributes
          ON attributes.attrelid = class.oid
         AND attributes.attname = columns.column_name
        WHERE columns.table_schema = %s
        ORDER BY columns.table_name, columns.ordinal_position
        """,
        (schema,),
    ).fetchall()
    for table_name, column_name, data_type, udt_name, nullable, default, position, description in rows:
        result[table_name].append(
            {
                "name": column_name,
                "type": data_type if data_type != "USER-DEFINED" else udt_name,
                "nullable": nullable,
                "default": default,
                "position": position,
                "description": description,
            }
        )
    return result


def fetch_constraints(connection: psycopg.Connection[Any], schema: str) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    type_names = {"p": "Primary key", "f": "Foreign key", "u": "Unique", "c": "Check"}
    rows = connection.execute(
        """
        SELECT
            class.relname,
            constraint_definition.conname,
            constraint_definition.contype,
            pg_catalog.pg_get_constraintdef(constraint_definition.oid, true)
        FROM pg_catalog.pg_constraint AS constraint_definition
        JOIN pg_catalog.pg_class AS class
          ON class.oid = constraint_definition.conrelid
        JOIN pg_catalog.pg_namespace AS namespace
          ON namespace.oid = class.relnamespace
        WHERE namespace.nspname = %s
          AND constraint_definition.contype IN ('p', 'f', 'u', 'c')
        ORDER BY class.relname, constraint_definition.contype, constraint_definition.conname
        """,
        (schema,),
    ).fetchall()
    for table_name, name, constraint_type, definition in rows:
        result[table_name].append(
            {"name": name, "type": type_names[constraint_type], "definition": definition}
        )
    return result


def fetch_indexes(connection: psycopg.Connection[Any], schema: str) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    rows = connection.execute(
        """
        SELECT tablename, indexname, indexdef
        FROM pg_catalog.pg_indexes
        WHERE schemaname = %s
        ORDER BY tablename, indexname
        """,
        (schema,),
    ).fetchall()
    for table_name, name, definition in rows:
        result[table_name].append({"name": name, "definition": definition})
    return result


def fetch_table_comments(connection: psycopg.Connection[Any], schema: str) -> dict[str, str | None]:
    return {
        table_name: description
        for table_name, description in connection.execute(
            """
            SELECT class.relname, pg_catalog.obj_description(class.oid, 'pg_class')
            FROM pg_catalog.pg_class AS class
            JOIN pg_catalog.pg_namespace AS namespace ON namespace.oid = class.relnamespace
            WHERE namespace.nspname = %s AND class.relkind = 'r'
            ORDER BY class.relname
            """,
            (schema,),
        ).fetchall()
    }


def apply_catalog_definitions(
    connection: psycopg.Connection[Any],
    schema: str,
    names: list[str],
    comments: dict[str, str | None],
    columns: dict[str, list[dict[str, Any]]],
) -> None:
    if "Table_Catalog" not in names or "Column_Catalog" not in names:
        return
    for table_name, definition in connection.execute(
        """
        SELECT table_name, definition
        FROM public."Table_Catalog"
        WHERE table_schema = %s AND definition IS NOT NULL
        """,
        (schema,),
    ).fetchall():
        comments[table_name] = definition
    definitions = {
        (table_name, column_name): definition
        for table_name, column_name, definition in connection.execute(
            """
            SELECT table_name, column_name, definition
            FROM public."Column_Catalog"
            WHERE table_schema = %s AND definition IS NOT NULL
            """,
            (schema,),
        ).fetchall()
    }
    for table_name, table_columns in columns.items():
        for column in table_columns:
            definition = definitions.get((table_name, column["name"]))
            if definition is not None:
                column["description"] = definition


def generate_document(
    schema: str,
    refreshed_at: datetime,
    names: list[str],
    columns: dict[str, list[dict[str, Any]]],
    constraints: dict[str, list[dict[str, str]]],
    indexes: dict[str, list[dict[str, str]]],
    comments: dict[str, str | None],
    statuses: list[dict[str, Any]],
) -> str:
    lines = [
        "# Database schema",
        "",
        f"Generated from PostgreSQL schema `{schema}` at `{refreshed_at.isoformat()}`.",
        "",
        "`Latest Data Date` is the newest business date represented in a table. `Last Changed At` is the latest tracked database change or completed load. `Last Checked At` is only the time this catalog inspected the table.",
        "",
        "## Tables",
        "",
        "| Table Name | Category | Update Pattern | Latest Data Date | Last Changed At | Tracking | Definition |",
        "|---|---|---|---|---|---|---|",
    ]
    status_by_name = {item["table_name"]: item for item in statuses}
    for name in names:
        status = status_by_name[name]
        description = comments.get(name) or TABLE_DESCRIPTIONS.get(name) or "No description has been recorded."
        lines.append(
            "| "
            + " | ".join(
                [
                    code(name),
                    markdown(status["category"]),
                    markdown(status["pattern"]),
                    code(status["latest_data_date"]),
                    code(status["last_changed_at"]),
                    markdown(status["tracking_status"]),
                    markdown(description),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Logical relationships",
            "",
            "These relationships are documented for analysis but are not enforced as PostgreSQL foreign keys.",
            "",
            "| From | To | Relationship | Notes |",
            "|---|---|---|---|",
        ]
    )
    for source, destination, relationship_type, notes in LOGICAL_RELATIONSHIPS:
        lines.append(
            f"| {code(source)} | {code(destination)} | {markdown(relationship_type)} | {markdown(notes)} |"
        )

    for name in names:
        description = comments.get(name) or TABLE_DESCRIPTIONS.get(name) or "No description has been recorded."
        lines.extend(["", f"## {name}", "", description, "", "### Columns", ""])
        lines.extend(
            [
                "| Column | Type | Nullable | Default | Definition |",
                "|---|---|---|---|---|",
            ]
        )
        for column in columns.get(name, []):
            description = (
                column["description"]
                or COLUMN_DESCRIPTIONS.get(name, {}).get(column["name"])
                or "No column description has been recorded."
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        code(column["name"]),
                        code(column["type"]),
                        "Yes" if column["nullable"] == "YES" else "No",
                        code(column["default"]),
                        markdown(description),
                    ]
                )
                + " |"
            )

        lines.extend(["", "### Constraints", ""])
        if constraints.get(name):
            lines.extend(["| Name | Type | Definition |", "|---|---|---|"])
            for item in constraints[name]:
                lines.append(
                    f"| {code(item['name'])} | {markdown(item['type'])} | {code(item['definition'])} |"
                )
        else:
            lines.append("No primary-key, foreign-key, unique, or check constraints were found.")

        lines.extend(["", "### Indexes", ""])
        if indexes.get(name):
            lines.extend(["| Name | Definition |", "|---|---|"])
            for item in indexes[name]:
                lines.append(f"| {code(item['name'])} | {code(item['definition'])} |")
        else:
            lines.append("No indexes were found.")

    return "\n".join(lines) + "\n"


def write_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        Path(temporary_name).replace(path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", default="public")
    parser.add_argument("--output", type=Path, default=Path("DATABASE_SCHEMA.md"))
    parser.add_argument("--host", help="Optional public database host override")
    parser.add_argument("--port", type=int, help="Port used with --host")
    args = parser.parse_args()

    if args.host:
        connection_args = {
            "host": args.host,
            "port": args.port or 5432,
            "dbname": os.environ["PGDATABASE"],
            "user": os.environ["PGUSER"],
            "password": os.environ["PGPASSWORD"],
            "sslmode": "require",
        }
    else:
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        connection_args = {"conninfo": database_url}

    refreshed_at = datetime.now(timezone.utc).replace(microsecond=0)
    with psycopg.connect(**connection_args) as connection:
        ensure_status_table(connection, args.schema)
        names = table_names(connection, args.schema)
        refresh_status(connection, args.schema, names, refreshed_at)
        ensure_reference_tracking(connection, args.schema, names)
        ensure_broker_load_tracking(connection, args.schema, names)
        statuses = fetch_status_rows(connection, args.schema)
        columns = fetch_columns(connection, args.schema)
        constraints = fetch_constraints(connection, args.schema)
        indexes = fetch_indexes(connection, args.schema)
        comments = fetch_table_comments(connection, args.schema)
        apply_catalog_definitions(connection, args.schema, names, comments, columns)
        document = generate_document(
            args.schema, refreshed_at, names, columns, constraints, indexes, comments, statuses
        )

    write_atomically(args.output, document)
    print(
        f"Synchronized {len(names)} tables into {args.schema}.{STATUS_TABLE} "
        f"and wrote {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
