#!/usr/bin/env python3
"""Refresh AI data coverage without reading any Feature table (Feature 01-06, their stock views and INDEX tables)."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg import sql


READ_TABLES = frozenset(
    {
        "AI_table_catalog",
        "AI_data_coverage",
        "Price_Stock_Indonesia_IDX",
        "IDX_Broker_Summary",
        "IDX_Stock_Universe",
        "IDX_Broker_Profile",
        "Feature_Status",
        "Price_Fixed_Income_Final",
        "Universe_Fixed_income",
        "idx_event_annotation",
    }
)
WRITE_TABLES = frozenset({"AI_data_coverage"})
FORBIDDEN_FEATURE_TABLES = frozenset(
    {
        "Feature_01_Stock_Daily",
        "Feature_02_Broker_Rolling",
        "Feature_03_Stock_Broker_Daily",
        "Feature_04_Technical_Indicator",
        "Feature_05_Foreign_Domestic_Broker_Detail",
        "Feature_06_Foreign_Domestic",
        "Feature_05_Foreign_Domestic_Broker_Detail_Stock",
        "Feature_06_Foreign_Domestic_Stock",
        "Feature_01_Stock_Daily_INDEX",
        "Feature_02_Broker_Rolling_INDEX",
        "Feature_03_Stock_Broker_Daily_INDEX",
        "Feature_04_Technical_Indicator_INDEX",
        "Feature_05_Foreign_Domestic_Broker_Detail_INDEX",
        "Feature_06_Foreign_Domestic_INDEX",
    }
)
# EXEC-M204 (2026-10-23): manual-refresh Features derived from IDX_Broker_Summary, with the entity filter of the object
# the AI reads. The Feature 05/06 views hold the current IDX stock universe only, so their expected coverage is the
# Broker Summary coverage of those stocks (the filter is the views' own, read from IDX_Stock_Universe, not a list).
STOCK_UNIVERSE_FILTER = (
    'AND source.entity_id IN (SELECT u."Ticker" FROM public."IDX_Stock_Universe" AS u WHERE u."Security Type" = \'stock\')'
)
# EXEC-INDEX-1 (2026-10-25): the index codes are the IDX_Stock_Universe rows of "Security Type" index, read at run
# time, not listed. Stock Features hold no index row (the INDEX tables do), so their expectations leave index codes out.
INDEX_CODES = 'SELECT u."Ticker" FROM public."IDX_Stock_Universe" AS u WHERE u."Security Type" = \'index\''
INDEX_FILTER = "AND source.entity_id IN (" + INDEX_CODES + ")"
NOT_INDEX_FILTER = "AND source.entity_id NOT IN (" + INDEX_CODES + ")"
# INDEX Features of the index price (one row per index and price date) and of market-wide broker flows (one row per
# index and Broker Summary date: every source symbol of the date, so the expected range is the Broker Summary range)
PRICE_INDEX_FEATURES = ("Feature_01_Stock_Daily_INDEX", "Feature_04_Technical_Indicator_INDEX")
MARKET_WIDE_INDEX_FEATURES = (
    "Feature_02_Broker_Rolling_INDEX",
    "Feature_03_Stock_Broker_Daily_INDEX",
    "Feature_05_Foreign_Domestic_Broker_Detail_INDEX",
    "Feature_06_Foreign_Domestic_INDEX",
)
BROKER_SUMMARY_FEATURES = {
    "Feature_02_Broker_Rolling": "",
    "Feature_03_Stock_Broker_Daily": "",
    "Feature_05_Foreign_Domestic_Broker_Detail_Stock": STOCK_UNIVERSE_FILTER,
    "Feature_06_Foreign_Domestic_Stock": STOCK_UNIVERSE_FILTER,
}

RAW_SOURCES = {
    "Price_Stock_Indonesia_IDX": {
        "entity_column": "ticker",
        "date_column": "date",
        "reference_for": ("Feature_01_Stock_Daily", "Feature_04_Technical_Indicator") + PRICE_INDEX_FEATURES,
    },
    "IDX_Broker_Summary": {
        "entity_column": "Symbol",
        "date_column": "Date",
        "reference_for": tuple(BROKER_SUMMARY_FEATURES) + MARKET_WIDE_INDEX_FEATURES,
    },
    # EXEC-ONBOARD-1: the final daily bond bars (both metric types per ticker); Feature 04's bond rows come from the
    # price series of this view
    "Price_Fixed_Income_Final": {
        "entity_column": "ticker",
        "date_column": "date",
        "reference_for": ("Feature_04_Technical_Indicator",),
    },
    # EXEC-GO-1025: Stockbit corporate actions and insider movements, one row per event (its own coverage); every pull
    # rebuilds the whole table, so the full range is always read (123,047 rows on 2026-10-25)
    "idx_event_annotation": {
        "entity_column": "ticker",
        "date_column": "annotation_date",
        "reference_for": (),
        "always_full": True,
    },
}
MARKET_TIMEZONE = ZoneInfo("Asia/Jakarta")
SNAPSHOTS = ("IDX_Stock_Universe", "IDX_Broker_Profile", "Universe_Fixed_income")
FEATURE_FOUR = "Feature_04_Technical_Indicator"
# Feature 04 is calculated by an event-driven worker after final price changes; no status table here confirms it,
# so its expected coverage stays UNVERIFIED (the expected range, not the stored one)
FEATURE_FOUR_PIPELINE = "EVENT_DRIVEN_NOT_CONFIRMED"


def validate_access_contract() -> None:
    forbidden_reads = READ_TABLES & FORBIDDEN_FEATURE_TABLES
    if forbidden_reads:
        raise RuntimeError(f"Coverage job cannot read Feature tables: {sorted(forbidden_reads)}")
    if WRITE_TABLES != {"AI_data_coverage"}:
        raise RuntimeError("Coverage job may write only AI_data_coverage")


def connection_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        raise RuntimeError("DATABASE_URL is required")
    return value


def enabled_datasets(connection: psycopg.Connection[Any]) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            """
            SELECT table_name
            FROM public."AI_table_catalog"
            WHERE is_active AND coverage_enabled
            """
        ).fetchall()
    }


def check_date() -> date:
    """EXEC-M224: the date coverage is measured against, in the market's timezone (the cron runs 07:30 and 17:30 WIB).
    A source row dated after it is an announced schedule, not data that has happened."""
    return datetime.now(MARKET_TIMEZONE).date()


def raw_coverage_rows(
    connection: psycopg.Connection[Any],
    dataset_name: str,
    mode: str,
    recent_days: int,
    as_of: date,
) -> list[tuple[Any, ...]]:
    """Per entity: (entity, first date, last date on or before as_of, row count, date count, rows after as_of, last
    date after as_of). Every raw source is read the same way from its RAW_SOURCES columns; the split at as_of is
    derived from the rows, so a source without future rows gives the same last date as the plain maximum (EXEC-M224).
    A nightly run reads the latest recent_days only; rows after as_of are always inside that window, so their count is
    complete in both modes."""
    if dataset_name not in RAW_SOURCES:
        raise ValueError(f"Unsupported raw dataset: {dataset_name}")
    source = RAW_SOURCES[dataset_name]
    table = sql.Identifier("public", dataset_name)
    entity = sql.Identifier(source["entity_column"])
    day = sql.Identifier(source["date_column"])
    windowed = mode != "full" and not source.get("always_full")
    where = sql.SQL("WHERE {} >= %(cutoff)s").format(day) if windowed else sql.SQL("")
    query = sql.SQL(
        """
        SELECT {entity}::text, min({day}), max({day}) FILTER (WHERE {day} <= %(as_of)s),
               count(*)::bigint, count(DISTINCT {day})::bigint,
               count(*) FILTER (WHERE {day} > %(as_of)s)::bigint, max({day}) FILTER (WHERE {day} > %(as_of)s)
        FROM {table}
        {where}
        GROUP BY {entity}
        ORDER BY {entity}
        """
    ).format(entity=entity, day=day, table=table, where=where)
    return connection.execute(
        query, {"cutoff": date.today() - timedelta(days=recent_days), "as_of": as_of}
    ).fetchall()


def upsert_raw_entities(
    connection: psycopg.Connection[Any],
    dataset_name: str,
    rows: list[tuple[Any, ...]],
    checked_at: datetime,
    mode: str,
    as_of: date,
) -> None:
    full_checked_at = checked_at if mode == "full" else None
    parameters = [
        (
            dataset_name,
            entity_id,
            min_date,
            max_date,
            row_count if mode == "full" else None,
            key_count if mode == "full" else None,
            scheduled_count,
            scheduled_max,
            checked_at,
            full_checked_at,
            as_of,
        )
        for entity_id, min_date, max_date, row_count, key_count, scheduled_count, scheduled_max in rows
    ]
    with connection.cursor() as cursor:
        cursor.executemany(
            """
        INSERT INTO public."AI_data_coverage" (
            dataset_name, coverage_scope, entity_id,
            reference_dataset_name, coverage_mode,
            actual_min_date, actual_max_date,
            expected_min_date, expected_max_date,
            source_row_count, source_key_count,
            scheduled_row_count, scheduled_max_date,
            pipeline_status, verification_status, quality_status,
            check_error, last_checked_at, last_full_checked_at
        )
        VALUES (
            %s, 'ENTITY', %s, NULL, 'ACTUAL_SOURCE',
            %s, %s, NULL, NULL, %s, %s, %s, %s,
            'SOURCE_OBSERVED', 'VERIFIED', 'HEALTHY', NULL, %s, %s
        )
        ON CONFLICT (dataset_name, coverage_scope, (COALESCE(entity_id, ''))) DO UPDATE SET
            actual_min_date = LEAST(
                public."AI_data_coverage".actual_min_date,
                EXCLUDED.actual_min_date
            ),
            -- EXEC-M224: a stored last date after the check date (written before the split) is not kept
            actual_max_date = GREATEST(
                CASE WHEN public."AI_data_coverage".actual_max_date <= %s::date
                     THEN public."AI_data_coverage".actual_max_date END,
                EXCLUDED.actual_max_date
            ),
            scheduled_row_count = EXCLUDED.scheduled_row_count,
            scheduled_max_date = EXCLUDED.scheduled_max_date,
            source_row_count = COALESCE(
                EXCLUDED.source_row_count,
                public."AI_data_coverage".source_row_count
            ),
            source_key_count = COALESCE(
                EXCLUDED.source_key_count,
                public."AI_data_coverage".source_key_count
            ),
            pipeline_status = EXCLUDED.pipeline_status,
            verification_status = EXCLUDED.verification_status,
            quality_status = EXCLUDED.quality_status,
            check_error = NULL,
            last_checked_at = EXCLUDED.last_checked_at,
            last_full_checked_at = COALESCE(
                EXCLUDED.last_full_checked_at,
                public."AI_data_coverage".last_full_checked_at
            )
            """,
            parameters,
        )
    if mode == "full":
        connection.execute(
            """
            DELETE FROM public."AI_data_coverage"
            WHERE dataset_name = %s
              AND coverage_scope = 'ENTITY'
              AND last_checked_at < %s
            """,
            (dataset_name, checked_at),
        )


def upsert_raw_dataset_summary(
    connection: psycopg.Connection[Any],
    dataset_name: str,
    checked_at: datetime,
    as_of: date,
) -> None:
    connection.execute(
        """
        INSERT INTO public."AI_data_coverage" (
            dataset_name, coverage_scope, entity_id,
            reference_dataset_name, coverage_mode,
            actual_min_date, actual_max_date,
            expected_min_date, expected_max_date,
            source_row_count, source_key_count,
            scheduled_row_count, scheduled_max_date,
            pipeline_status, verification_status, quality_status,
            check_error, last_checked_at, last_full_checked_at
        )
        SELECT
            %(dataset)s, 'DATASET', NULL, NULL, 'ACTUAL_SOURCE',
            min(actual_min_date), max(actual_max_date) FILTER (WHERE actual_max_date <= %(as_of)s), NULL, NULL,
            CASE WHEN bool_and(source_row_count IS NOT NULL)
                 THEN sum(source_row_count) END,
            CASE WHEN bool_and(source_key_count IS NOT NULL)
                 THEN sum(source_key_count) END,
            coalesce(sum(scheduled_row_count), 0), max(scheduled_max_date),
            'SOURCE_OBSERVED', 'VERIFIED', 'HEALTHY', NULL, %(checked_at)s,
            max(last_full_checked_at)
        FROM public."AI_data_coverage"
        WHERE dataset_name = %(dataset)s AND coverage_scope = 'ENTITY'
        HAVING count(*) > 0
        ON CONFLICT (dataset_name, coverage_scope, (COALESCE(entity_id, ''))) DO UPDATE SET
            actual_min_date = EXCLUDED.actual_min_date,
            actual_max_date = EXCLUDED.actual_max_date,
            source_row_count = EXCLUDED.source_row_count,
            source_key_count = EXCLUDED.source_key_count,
            scheduled_row_count = EXCLUDED.scheduled_row_count,
            scheduled_max_date = EXCLUDED.scheduled_max_date,
            pipeline_status = EXCLUDED.pipeline_status,
            verification_status = EXCLUDED.verification_status,
            quality_status = EXCLUDED.quality_status,
            check_error = NULL,
            last_checked_at = EXCLUDED.last_checked_at,
            last_full_checked_at = EXCLUDED.last_full_checked_at
        """,
        {"dataset": dataset_name, "checked_at": checked_at, "as_of": as_of},
    )


def upsert_snapshot(
    connection: psycopg.Connection[Any],
    dataset_name: str,
    checked_at: datetime,
) -> None:
    if dataset_name == "IDX_Stock_Universe":
        row_count = connection.execute(
            'SELECT count(*)::bigint FROM public."IDX_Stock_Universe"'
        ).fetchone()[0]
    elif dataset_name == "IDX_Broker_Profile":
        row_count = connection.execute(
            'SELECT count(*)::bigint FROM public."IDX_Broker_Profile"'
        ).fetchone()[0]
    elif dataset_name == "Universe_Fixed_income":
        row_count = connection.execute(
            'SELECT count(*)::bigint FROM public."Universe_Fixed_income"'
        ).fetchone()[0]
    else:
        raise ValueError(f"Unsupported snapshot dataset: {dataset_name}")
    connection.execute(
        """
        INSERT INTO public."AI_data_coverage" (
            dataset_name, coverage_scope, entity_id,
            reference_dataset_name, coverage_mode,
            actual_min_date, actual_max_date,
            expected_min_date, expected_max_date,
            source_row_count, source_key_count,
            pipeline_status, verification_status, quality_status,
            check_error, last_checked_at, last_full_checked_at
        )
        VALUES (
            %s, 'DATASET', NULL, NULL, 'SNAPSHOT',
            NULL, NULL, NULL, NULL, %s, %s,
            'SOURCE_OBSERVED', 'VERIFIED', 'HEALTHY', NULL, %s, %s
        )
        ON CONFLICT (dataset_name, coverage_scope, (COALESCE(entity_id, ''))) DO UPDATE SET
            source_row_count = EXCLUDED.source_row_count,
            source_key_count = EXCLUDED.source_key_count,
            pipeline_status = EXCLUDED.pipeline_status,
            verification_status = EXCLUDED.verification_status,
            quality_status = EXCLUDED.quality_status,
            check_error = NULL,
            last_checked_at = EXCLUDED.last_checked_at,
            last_full_checked_at = EXCLUDED.last_full_checked_at
        """,
        (dataset_name, row_count, row_count, checked_at, checked_at),
    )


def upsert_feature_one_expectations(
    connection: psycopg.Connection[Any],
    checked_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO public."AI_data_coverage" (
            dataset_name, coverage_scope, entity_id,
            reference_dataset_name, coverage_mode,
            actual_min_date, actual_max_date,
            expected_min_date, expected_max_date,
            source_row_count, source_key_count,
            pipeline_status, verification_status, quality_status,
            check_error, last_checked_at, last_full_checked_at
        )
        SELECT
            'Feature_01_Stock_Daily', 'ENTITY', source.entity_id,
            'Price_Stock_Indonesia_IDX', 'EXPECTED_DERIVED',
            NULL, NULL, source.actual_min_date, source.actual_max_date,
            source.source_row_count, source.source_key_count,
            COALESCE(status.status, 'NOT_TRACKED'),
            CASE
              WHEN status.status = 'SUCCESS'
               AND status.pending_count = 0
               AND status.processing_count = 0
               AND status.failed_count = 0
               AND status.last_successful_price_date >= source.actual_max_date
              THEN 'PIPELINE_CONFIRMED'
              ELSE 'UNVERIFIED'
            END,
            CASE
              WHEN status.status = 'FAILED' THEN 'FAILED'
              WHEN status.status = 'SUCCESS'
               AND status.pending_count = 0
               AND status.processing_count = 0
               AND status.failed_count = 0
               AND status.last_successful_price_date >= source.actual_max_date
              THEN 'HEALTHY'
              ELSE 'WARNING'
            END,
            status.last_error, %s, source.last_full_checked_at
        FROM public."AI_data_coverage" AS source
        LEFT JOIN public."Feature_Status" AS status
          ON status.feature_table = 'Feature_01_Stock_Daily'
         AND status.ticker = source.entity_id
        WHERE source.dataset_name = 'Price_Stock_Indonesia_IDX'
          AND source.coverage_scope = 'ENTITY'
        """ + NOT_INDEX_FILTER + """
        ON CONFLICT (dataset_name, coverage_scope, (COALESCE(entity_id, ''))) DO UPDATE SET
            reference_dataset_name = EXCLUDED.reference_dataset_name,
            coverage_mode = EXCLUDED.coverage_mode,
            actual_min_date = NULL,
            actual_max_date = NULL,
            expected_min_date = EXCLUDED.expected_min_date,
            expected_max_date = EXCLUDED.expected_max_date,
            source_row_count = EXCLUDED.source_row_count,
            source_key_count = EXCLUDED.source_key_count,
            pipeline_status = EXCLUDED.pipeline_status,
            verification_status = EXCLUDED.verification_status,
            quality_status = EXCLUDED.quality_status,
            check_error = EXCLUDED.check_error,
            last_checked_at = EXCLUDED.last_checked_at,
            last_full_checked_at = EXCLUDED.last_full_checked_at
        """,
        (checked_at,),
    )


def upsert_manual_feature_expectations(
    connection: psycopg.Connection[Any],
    feature_table: str,
    checked_at: datetime,
) -> None:
    entity_filter = BROKER_SUMMARY_FEATURES.get(feature_table, "")
    connection.execute(
        """
        INSERT INTO public."AI_data_coverage" (
            dataset_name, coverage_scope, entity_id,
            reference_dataset_name, coverage_mode,
            actual_min_date, actual_max_date,
            expected_min_date, expected_max_date,
            source_row_count, source_key_count,
            pipeline_status, verification_status, quality_status,
            check_error, last_checked_at, last_full_checked_at
        )
        SELECT
            %s, 'ENTITY', source.entity_id,
            'IDX_Broker_Summary', 'EXPECTED_DERIVED',
            NULL, NULL, source.actual_min_date, source.actual_max_date,
            source.source_row_count, source.source_key_count,
            'MANUAL_REFRESH_REQUIRED', 'UNVERIFIED', 'WARNING',
            NULL, %s, source.last_full_checked_at
        FROM public."AI_data_coverage" AS source
        WHERE source.dataset_name = 'IDX_Broker_Summary'
          AND source.coverage_scope = 'ENTITY'
        """ + entity_filter + """
        ON CONFLICT (dataset_name, coverage_scope, (COALESCE(entity_id, ''))) DO UPDATE SET
            reference_dataset_name = EXCLUDED.reference_dataset_name,
            coverage_mode = EXCLUDED.coverage_mode,
            actual_min_date = NULL,
            actual_max_date = NULL,
            expected_min_date = EXCLUDED.expected_min_date,
            expected_max_date = EXCLUDED.expected_max_date,
            source_row_count = EXCLUDED.source_row_count,
            source_key_count = EXCLUDED.source_key_count,
            pipeline_status = EXCLUDED.pipeline_status,
            verification_status = EXCLUDED.verification_status,
            quality_status = EXCLUDED.quality_status,
            check_error = NULL,
            last_checked_at = EXCLUDED.last_checked_at,
            last_full_checked_at = EXCLUDED.last_full_checked_at
        """,
        (feature_table, checked_at),
    )


def upsert_feature_four_expectations(
    connection: psycopg.Connection[Any],
    checked_at: datetime,
) -> None:
    """Feature 04 expected coverage from its two raw sources: equity tickers inherit the stock price range (already
    measured in AI_data_coverage), bond tickers the range of their price series in Price_Fixed_Income_Final (Feature
    04 reads only metric_type price). No stock ticker is also a bond ticker (live read 2026-10-20)."""
    connection.execute(
        """
        INSERT INTO public."AI_data_coverage" (
            dataset_name, coverage_scope, entity_id,
            reference_dataset_name, coverage_mode,
            actual_min_date, actual_max_date,
            expected_min_date, expected_max_date,
            source_row_count, source_key_count,
            pipeline_status, verification_status, quality_status,
            check_error, last_checked_at, last_full_checked_at
        )
        SELECT
            'Feature_04_Technical_Indicator', 'ENTITY', source.entity_id,
            source.reference_dataset_name, 'EXPECTED_DERIVED',
            NULL, NULL, source.expected_min_date, source.expected_max_date,
            source.source_row_count, source.source_key_count,
            %s, 'UNVERIFIED', 'WARNING', NULL, %s, source.last_full_checked_at
        FROM (
            SELECT entity_id, 'Price_Stock_Indonesia_IDX' AS reference_dataset_name,
                   actual_min_date AS expected_min_date, actual_max_date AS expected_max_date,
                   source_row_count, source_key_count, last_full_checked_at
            FROM public."AI_data_coverage" AS source
            WHERE dataset_name = 'Price_Stock_Indonesia_IDX' AND coverage_scope = 'ENTITY'
            """ + NOT_INDEX_FILTER + """
            UNION ALL
            SELECT ticker, 'Price_Fixed_Income_Final', min(date), max(date),
                   count(*)::bigint, count(DISTINCT date)::bigint, %s
            FROM public."Price_Fixed_Income_Final"
            WHERE metric_type = 'price'
            GROUP BY ticker
        ) AS source
        ON CONFLICT (dataset_name, coverage_scope, (COALESCE(entity_id, ''))) DO UPDATE SET
            reference_dataset_name = EXCLUDED.reference_dataset_name,
            coverage_mode = EXCLUDED.coverage_mode,
            actual_min_date = NULL,
            actual_max_date = NULL,
            expected_min_date = EXCLUDED.expected_min_date,
            expected_max_date = EXCLUDED.expected_max_date,
            source_row_count = EXCLUDED.source_row_count,
            source_key_count = EXCLUDED.source_key_count,
            pipeline_status = EXCLUDED.pipeline_status,
            verification_status = EXCLUDED.verification_status,
            quality_status = EXCLUDED.quality_status,
            check_error = NULL,
            last_checked_at = EXCLUDED.last_checked_at,
            last_full_checked_at = EXCLUDED.last_full_checked_at
        """,
        (FEATURE_FOUR_PIPELINE, checked_at, checked_at),
    )


def prune_feature_four_entities(connection: psycopg.Connection[Any]) -> None:
    """Every mode: a Feature 04 entity in neither raw source (index codes left out of the stock prices) is dropped."""
    connection.execute(
        """
        DELETE FROM public."AI_data_coverage" AS derived
        WHERE derived.dataset_name = 'Feature_04_Technical_Indicator'
          AND derived.coverage_scope = 'ENTITY'
          AND NOT EXISTS (
              SELECT 1 FROM public."AI_data_coverage" AS source
              WHERE source.dataset_name = 'Price_Stock_Indonesia_IDX'
                AND source.coverage_scope = 'ENTITY'
                AND source.entity_id = derived.entity_id
                """ + NOT_INDEX_FILTER + """
          )
          AND NOT EXISTS (
              SELECT 1 FROM public."Price_Fixed_Income_Final" AS bond
              WHERE bond.metric_type = 'price' AND bond.ticker = derived.entity_id
          )
        """
    )


def prune_derived_entities(
    connection: psycopg.Connection[Any],
    feature_table: str,
    source_table: str,
    entity_filter: str = "",
) -> None:
    """A derived entity whose source entity is gone, or no longer passes the Feature's entity filter, is dropped."""
    connection.execute(
        """
        DELETE FROM public."AI_data_coverage" AS derived
        WHERE derived.dataset_name = %s
          AND derived.coverage_scope = 'ENTITY'
          AND NOT EXISTS (
              SELECT 1
              FROM public."AI_data_coverage" AS source
              WHERE source.dataset_name = %s
                AND source.coverage_scope = 'ENTITY'
                AND source.entity_id = derived.entity_id
                """ + entity_filter + """
          )
        """,
        (feature_table, source_table),
    )


def upsert_price_index_expectations(
    connection: psycopg.Connection[Any],
    feature_table: str,
    checked_at: datetime,
) -> None:
    """An INDEX price Feature expects the price range of each index code; its refresh is manual (EXEC-INDEX-1)."""
    connection.execute(
        """
        INSERT INTO public."AI_data_coverage" (
            dataset_name, coverage_scope, entity_id,
            reference_dataset_name, coverage_mode,
            actual_min_date, actual_max_date,
            expected_min_date, expected_max_date,
            source_row_count, source_key_count,
            pipeline_status, verification_status, quality_status,
            check_error, last_checked_at, last_full_checked_at
        )
        SELECT
            %s, 'ENTITY', source.entity_id,
            'Price_Stock_Indonesia_IDX', 'EXPECTED_DERIVED',
            NULL, NULL, source.actual_min_date, source.actual_max_date,
            source.source_row_count, source.source_key_count,
            'MANUAL_REFRESH_REQUIRED', 'UNVERIFIED', 'WARNING',
            NULL, %s, source.last_full_checked_at
        FROM public."AI_data_coverage" AS source
        WHERE source.dataset_name = 'Price_Stock_Indonesia_IDX'
          AND source.coverage_scope = 'ENTITY'
        """ + INDEX_FILTER + """
        ON CONFLICT (dataset_name, coverage_scope, (COALESCE(entity_id, ''))) DO UPDATE SET
            reference_dataset_name = EXCLUDED.reference_dataset_name,
            coverage_mode = EXCLUDED.coverage_mode,
            actual_min_date = NULL,
            actual_max_date = NULL,
            expected_min_date = EXCLUDED.expected_min_date,
            expected_max_date = EXCLUDED.expected_max_date,
            source_row_count = EXCLUDED.source_row_count,
            source_key_count = EXCLUDED.source_key_count,
            pipeline_status = EXCLUDED.pipeline_status,
            verification_status = EXCLUDED.verification_status,
            quality_status = EXCLUDED.quality_status,
            check_error = NULL,
            last_checked_at = EXCLUDED.last_checked_at,
            last_full_checked_at = EXCLUDED.last_full_checked_at
        """,
        (feature_table, checked_at),
    )


def upsert_market_wide_index_expectations(
    connection: psycopg.Connection[Any],
    feature_table: str,
    checked_at: datetime,
) -> None:
    """A market-wide INDEX broker Feature aggregates every source symbol of a date, so each index code expects the
    whole Broker Summary range (its DATASET row); the refresh is manual (EXEC-INDEX-1). Index codes no longer in the
    universe are dropped."""
    connection.execute(
        """
        INSERT INTO public."AI_data_coverage" (
            dataset_name, coverage_scope, entity_id,
            reference_dataset_name, coverage_mode,
            actual_min_date, actual_max_date,
            expected_min_date, expected_max_date,
            source_row_count, source_key_count,
            pipeline_status, verification_status, quality_status,
            check_error, last_checked_at, last_full_checked_at
        )
        SELECT
            %s, 'ENTITY', codes."Ticker",
            'IDX_Broker_Summary', 'EXPECTED_DERIVED',
            NULL, NULL, source.actual_min_date, source.actual_max_date,
            source.source_row_count, source.source_key_count,
            'MANUAL_REFRESH_REQUIRED', 'UNVERIFIED', 'WARNING',
            NULL, %s, source.last_full_checked_at
        FROM public."AI_data_coverage" AS source
        CROSS JOIN (""" + INDEX_CODES + """) AS codes
        WHERE source.dataset_name = 'IDX_Broker_Summary'
          AND source.coverage_scope = 'DATASET'
        ON CONFLICT (dataset_name, coverage_scope, (COALESCE(entity_id, ''))) DO UPDATE SET
            reference_dataset_name = EXCLUDED.reference_dataset_name,
            coverage_mode = EXCLUDED.coverage_mode,
            actual_min_date = NULL,
            actual_max_date = NULL,
            expected_min_date = EXCLUDED.expected_min_date,
            expected_max_date = EXCLUDED.expected_max_date,
            source_row_count = EXCLUDED.source_row_count,
            source_key_count = EXCLUDED.source_key_count,
            pipeline_status = EXCLUDED.pipeline_status,
            verification_status = EXCLUDED.verification_status,
            quality_status = EXCLUDED.quality_status,
            check_error = NULL,
            last_checked_at = EXCLUDED.last_checked_at,
            last_full_checked_at = EXCLUDED.last_full_checked_at
        """,
        (feature_table, checked_at),
    )
    connection.execute(
        """
        DELETE FROM public."AI_data_coverage"
        WHERE dataset_name = %s AND coverage_scope = 'ENTITY'
          AND entity_id NOT IN (""" + INDEX_CODES + """)
        """,
        (feature_table,),
    )


def upsert_derived_dataset_summary(
    connection: psycopg.Connection[Any],
    dataset_name: str,
    reference_dataset_name: str | None,
    checked_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO public."AI_data_coverage" (
            dataset_name, coverage_scope, entity_id,
            reference_dataset_name, coverage_mode,
            actual_min_date, actual_max_date,
            expected_min_date, expected_max_date,
            source_row_count, source_key_count,
            pipeline_status, verification_status, quality_status,
            check_error, last_checked_at, last_full_checked_at
        )
        SELECT
            %s, 'DATASET', NULL, %s, 'EXPECTED_DERIVED',
            NULL, NULL, min(expected_min_date), max(expected_max_date),
            CASE WHEN bool_and(source_row_count IS NOT NULL)
                 THEN sum(source_row_count) END,
            CASE WHEN bool_and(source_key_count IS NOT NULL)
                 THEN sum(source_key_count) END,
            CASE
              WHEN bool_and(verification_status = 'PIPELINE_CONFIRMED')
                THEN 'ALL_PIPELINE_CONFIRMED'
              WHEN bool_or(pipeline_status = 'MANUAL_REFRESH_REQUIRED')
                THEN 'MANUAL_REFRESH_REQUIRED'
              ELSE 'NOT_FULLY_CONFIRMED'
            END,
            CASE WHEN bool_and(verification_status = 'PIPELINE_CONFIRMED')
                 THEN 'PIPELINE_CONFIRMED' ELSE 'UNVERIFIED' END,
            CASE
              WHEN bool_or(quality_status = 'FAILED') THEN 'FAILED'
              WHEN bool_and(quality_status = 'HEALTHY') THEN 'HEALTHY'
              ELSE 'WARNING'
            END,
            NULL, %s, max(last_full_checked_at)
        FROM public."AI_data_coverage"
        WHERE dataset_name = %s AND coverage_scope = 'ENTITY'
        HAVING count(*) > 0
        ON CONFLICT (dataset_name, coverage_scope, (COALESCE(entity_id, ''))) DO UPDATE SET
            reference_dataset_name = EXCLUDED.reference_dataset_name,
            coverage_mode = EXCLUDED.coverage_mode,
            actual_min_date = NULL,
            actual_max_date = NULL,
            expected_min_date = EXCLUDED.expected_min_date,
            expected_max_date = EXCLUDED.expected_max_date,
            source_row_count = EXCLUDED.source_row_count,
            source_key_count = EXCLUDED.source_key_count,
            pipeline_status = EXCLUDED.pipeline_status,
            verification_status = EXCLUDED.verification_status,
            quality_status = EXCLUDED.quality_status,
            check_error = NULL,
            last_checked_at = EXCLUDED.last_checked_at,
            last_full_checked_at = EXCLUDED.last_full_checked_at
        """,
        (dataset_name, reference_dataset_name, checked_at, dataset_name),
    )


def run(mode: str, recent_days: int) -> dict[str, Any]:
    validate_access_contract()
    checked_at = datetime.now(timezone.utc)
    as_of = check_date()
    with psycopg.connect(connection_url()) as connection:
        lock_acquired = connection.execute(
            "SELECT pg_try_advisory_xact_lock(hashtextextended('ai_data_coverage_job', 0))"
        ).fetchone()[0]
        if not lock_acquired:
            raise RuntimeError("Another AI data coverage run is active")
        enabled = enabled_datasets(connection)

        for raw_dataset in RAW_SOURCES:
            dependents = set(RAW_SOURCES[raw_dataset]["reference_for"])
            if raw_dataset not in enabled and not (dependents & enabled):
                continue
            rows = raw_coverage_rows(connection, raw_dataset, mode, recent_days, as_of)
            upsert_raw_entities(connection, raw_dataset, rows, checked_at, mode, as_of)
            upsert_raw_dataset_summary(connection, raw_dataset, checked_at, as_of)

        for snapshot in SNAPSHOTS:
            if snapshot in enabled:
                upsert_snapshot(connection, snapshot, checked_at)

        if "Feature_01_Stock_Daily" in enabled:
            upsert_feature_one_expectations(connection, checked_at)
            # every mode: an index code left in from before EXEC-INDEX-1 is dropped too
            prune_derived_entities(
                connection,
                "Feature_01_Stock_Daily",
                "Price_Stock_Indonesia_IDX",
                NOT_INDEX_FILTER,
            )
            upsert_derived_dataset_summary(
                connection,
                "Feature_01_Stock_Daily",
                "Price_Stock_Indonesia_IDX",
                checked_at,
            )

        for feature_table in BROKER_SUMMARY_FEATURES:
            if feature_table not in enabled:
                continue
            upsert_manual_feature_expectations(connection, feature_table, checked_at)
            if mode == "full":
                prune_derived_entities(
                    connection, feature_table, "IDX_Broker_Summary"
                )
            upsert_derived_dataset_summary(
                connection,
                feature_table,
                "IDX_Broker_Summary",
                checked_at,
            )

        if FEATURE_FOUR in enabled:
            upsert_feature_four_expectations(connection, checked_at)
            prune_feature_four_entities(connection)
            upsert_derived_dataset_summary(connection, FEATURE_FOUR, None, checked_at)

        for feature_table in PRICE_INDEX_FEATURES:
            if feature_table not in enabled:
                continue
            upsert_price_index_expectations(connection, feature_table, checked_at)
            prune_derived_entities(connection, feature_table, "Price_Stock_Indonesia_IDX", INDEX_FILTER)
            upsert_derived_dataset_summary(connection, feature_table, "Price_Stock_Indonesia_IDX", checked_at)

        for feature_table in MARKET_WIDE_INDEX_FEATURES:
            if feature_table not in enabled:
                continue
            upsert_market_wide_index_expectations(connection, feature_table, checked_at)
            upsert_derived_dataset_summary(connection, feature_table, "IDX_Broker_Summary", checked_at)

        summary_rows = connection.execute(
            """
            SELECT dataset_name, coverage_scope, count(*)::bigint,
                   count(*) FILTER (WHERE verification_status = 'PIPELINE_CONFIRMED')::bigint,
                   count(*) FILTER (WHERE verification_status = 'UNVERIFIED')::bigint
            FROM public."AI_data_coverage"
            GROUP BY dataset_name, coverage_scope
            ORDER BY dataset_name, coverage_scope
            """
        ).fetchall()
        connection.commit()
    return {
        "status": "SUCCESS",
        "mode": mode,
        "checked_at": checked_at.isoformat(),
        "as_of": as_of.isoformat(),
        "read_tables": sorted(READ_TABLES),
        "write_tables": sorted(WRITE_TABLES),
        "coverage_summary": [
            {
                "dataset_name": row[0],
                "coverage_scope": row[1],
                "rows": row[2],
                "pipeline_confirmed": row[3],
                "unverified": row[4],
            }
            for row in summary_rows
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("nightly", "full"), default="nightly")
    parser.add_argument("--recent-days", type=int, default=30)
    args = parser.parse_args()
    if args.recent_days < 1 or args.recent_days > 366:
        raise SystemExit("--recent-days must be between 1 and 366")
    try:
        result = run(args.mode, args.recent_days)
    except Exception as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}), flush=True)
        raise
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
