#!/usr/bin/env python3
"""Refresh AI data coverage without reading Feature 01, 02, or 03 tables."""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg


READ_TABLES = frozenset(
    {
        "AI_table_catalog",
        "AI_data_coverage",
        "Price_Stock_Indonesia_IDX",
        "IDX_Broker_Summary",
        "IDX_Stock_Universe",
        "IDX_Broker_Profile",
        "Feature_Status",
    }
)
WRITE_TABLES = frozenset({"AI_data_coverage"})
FORBIDDEN_FEATURE_TABLES = frozenset(
    {
        "Feature_01_Stock_Daily",
        "Feature_02_Broker_Rolling",
        "Feature_03_Stock_Broker_Daily",
    }
)

RAW_SOURCES = {
    "Price_Stock_Indonesia_IDX": {
        "entity_column": "ticker",
        "date_column": "date",
        "reference_for": ("Feature_01_Stock_Daily",),
    },
    "IDX_Broker_Summary": {
        "entity_column": "Symbol",
        "date_column": "Date",
        "reference_for": (
            "Feature_02_Broker_Rolling",
            "Feature_03_Stock_Broker_Daily",
        ),
    },
}


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


def raw_coverage_rows(
    connection: psycopg.Connection[Any],
    dataset_name: str,
    mode: str,
    recent_days: int,
) -> list[tuple[Any, ...]]:
    cutoff = date.today() - timedelta(days=recent_days)
    if dataset_name == "Price_Stock_Indonesia_IDX":
        where_clause = "" if mode == "full" else "WHERE date >= %s"
        parameters: tuple[Any, ...] = () if mode == "full" else (cutoff,)
        return connection.execute(
            f"""
            SELECT ticker::text, min(date), max(date),
                   count(*)::bigint, count(DISTINCT date)::bigint
            FROM public."Price_Stock_Indonesia_IDX"
            {where_clause}
            GROUP BY ticker
            ORDER BY ticker
            """,
            parameters,
        ).fetchall()
    if dataset_name == "IDX_Broker_Summary":
        where_clause = "" if mode == "full" else "WHERE \"Date\" >= %s"
        parameters = () if mode == "full" else (cutoff,)
        return connection.execute(
            f"""
            SELECT "Symbol"::text, min("Date"), max("Date"),
                   count(*)::bigint, count(DISTINCT "Date")::bigint
            FROM public."IDX_Broker_Summary"
            {where_clause}
            GROUP BY "Symbol"
            ORDER BY "Symbol"
            """,
            parameters,
        ).fetchall()
    raise ValueError(f"Unsupported raw dataset: {dataset_name}")


def upsert_raw_entities(
    connection: psycopg.Connection[Any],
    dataset_name: str,
    rows: list[tuple[Any, ...]],
    checked_at: datetime,
    mode: str,
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
            checked_at,
            full_checked_at,
        )
        for entity_id, min_date, max_date, row_count, key_count in rows
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
            pipeline_status, verification_status, quality_status,
            check_error, last_checked_at, last_full_checked_at
        )
        VALUES (
            %s, 'ENTITY', %s, NULL, 'ACTUAL_SOURCE',
            %s, %s, NULL, NULL, %s, %s,
            'SOURCE_OBSERVED', 'VERIFIED', 'HEALTHY', NULL, %s, %s
        )
        ON CONFLICT (dataset_name, coverage_scope, (COALESCE(entity_id, ''))) DO UPDATE SET
            actual_min_date = LEAST(
                public."AI_data_coverage".actual_min_date,
                EXCLUDED.actual_min_date
            ),
            actual_max_date = GREATEST(
                public."AI_data_coverage".actual_max_date,
                EXCLUDED.actual_max_date
            ),
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
            %s, 'DATASET', NULL, NULL, 'ACTUAL_SOURCE',
            min(actual_min_date), max(actual_max_date), NULL, NULL,
            CASE WHEN bool_and(source_row_count IS NOT NULL)
                 THEN sum(source_row_count) END,
            CASE WHEN bool_and(source_key_count IS NOT NULL)
                 THEN sum(source_key_count) END,
            'SOURCE_OBSERVED', 'VERIFIED', 'HEALTHY', NULL, %s,
            max(last_full_checked_at)
        FROM public."AI_data_coverage"
        WHERE dataset_name = %s AND coverage_scope = 'ENTITY'
        HAVING count(*) > 0
        ON CONFLICT (dataset_name, coverage_scope, (COALESCE(entity_id, ''))) DO UPDATE SET
            actual_min_date = EXCLUDED.actual_min_date,
            actual_max_date = EXCLUDED.actual_max_date,
            source_row_count = EXCLUDED.source_row_count,
            source_key_count = EXCLUDED.source_key_count,
            pipeline_status = EXCLUDED.pipeline_status,
            verification_status = EXCLUDED.verification_status,
            quality_status = EXCLUDED.quality_status,
            check_error = NULL,
            last_checked_at = EXCLUDED.last_checked_at,
            last_full_checked_at = EXCLUDED.last_full_checked_at
        """,
        (dataset_name, checked_at, dataset_name),
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


def prune_derived_entities(
    connection: psycopg.Connection[Any],
    feature_table: str,
    source_table: str,
) -> None:
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
          )
        """,
        (feature_table, source_table),
    )


def upsert_derived_dataset_summary(
    connection: psycopg.Connection[Any],
    dataset_name: str,
    reference_dataset_name: str,
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
            rows = raw_coverage_rows(connection, raw_dataset, mode, recent_days)
            upsert_raw_entities(connection, raw_dataset, rows, checked_at, mode)
            upsert_raw_dataset_summary(connection, raw_dataset, checked_at)

        for snapshot in ("IDX_Stock_Universe", "IDX_Broker_Profile"):
            if snapshot in enabled:
                upsert_snapshot(connection, snapshot, checked_at)

        if "Feature_01_Stock_Daily" in enabled:
            upsert_feature_one_expectations(connection, checked_at)
            if mode == "full":
                prune_derived_entities(
                    connection,
                    "Feature_01_Stock_Daily",
                    "Price_Stock_Indonesia_IDX",
                )
            upsert_derived_dataset_summary(
                connection,
                "Feature_01_Stock_Daily",
                "Price_Stock_Indonesia_IDX",
                checked_at,
            )

        for feature_table in (
            "Feature_02_Broker_Rolling",
            "Feature_03_Stock_Broker_Daily",
        ):
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
