#!/usr/bin/env python3
"""Continuously refresh Feature 01 for committed price-candle queue items."""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime

import psycopg
from psycopg.rows import dict_row


FEATURE_TABLE = "Feature_01_Stock_Daily"
MAX_SOURCE_ATTEMPTS = 5
LEASE_MINUTES = 10
POLL_SECONDS = 5
RETRY_BASE_SECONDS = 30
RETRY_CAP_SECONDS = 30 * 60


@dataclass(frozen=True)
class Job:
    ticker: str
    price_date: date
    source_ingestion_time: datetime
    attempt_no: int
    source_attempt_count: int
    claim_token: uuid.UUID
    started_at: datetime


def connect() -> psycopg.Connection:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        autocommit=True,
        application_name="feature-01-worker",
    )


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)


def error_detail(error: Exception) -> str:
    if isinstance(error, psycopg.Error):
        message = error.diag.message_primary or type(error).__name__
    else:
        message = str(error) or type(error).__name__
    return f"{type(error).__name__}: {message}"[:500]


def record_attempt(
    connection: psycopg.Connection,
    *,
    ticker: str,
    price_date: date,
    source_ingestion_time: datetime,
    attempt_no: int,
    result: str,
    started_at: datetime,
    rows_refreshed: int | None = None,
    detail: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO public."Feature_Calculation_Log" (
            feature_table, ticker, price_date, source_ingestion_time,
            attempt_no, result, started_at, finished_at, rows_refreshed, detail
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, clock_timestamp(), %s, %s
        )
        ON CONFLICT (feature_table, ticker, price_date, attempt_no) DO NOTHING
        """,
        (
            FEATURE_TABLE, ticker, price_date, source_ingestion_time,
            attempt_no, result, started_at, rows_refreshed, detail,
        ),
    )


def claim_one() -> Job | str | None:
    """Claim a due item, or finalize an exhausted expired claim, in a short transaction."""
    with connect() as connection, connection.transaction():
        connection.execute("SET LOCAL statement_timeout = '15s'")
        candidate = connection.execute(
            """
            SELECT feature_table, ticker, price_date, source_ingestion_time,
                   status, attempt_count, source_attempt_count, claimed_at
            FROM public."Feature_Calculation_Queue"
            WHERE feature_table = %s
              AND (
                  (status IN ('PENDING', 'FAILED')
                   AND next_attempt_at <= CURRENT_TIMESTAMP
                   AND source_attempt_count < %s)
                  OR (status = 'PROCESSING'
                      AND claim_expires_at <= CURRENT_TIMESTAMP)
              )
            ORDER BY next_attempt_at, created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
            """,
            (FEATURE_TABLE, MAX_SOURCE_ATTEMPTS),
        ).fetchone()
        if candidate is None:
            return None

        ticker = candidate["ticker"]
        price_date = candidate["price_date"]
        version = candidate["source_ingestion_time"]
        if candidate["status"] == "PROCESSING":
            record_attempt(
                connection,
                ticker=ticker,
                price_date=price_date,
                source_ingestion_time=version,
                attempt_no=candidate["attempt_count"],
                result="FAILED",
                started_at=candidate["claimed_at"],
                detail="Claim lease expired before validated completion",
            )
            if candidate["source_attempt_count"] >= MAX_SOURCE_ATTEMPTS:
                connection.execute(
                    """
                    UPDATE public."Feature_Calculation_Queue"
                    SET status = 'FAILED', claimed_at = NULL, claim_token = NULL,
                        claim_expires_at = NULL, completed_at = NULL,
                        next_attempt_at = 'infinity'::timestamptz,
                        last_error = 'Maximum attempts exhausted after lease expiry',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE feature_table = %s AND ticker = %s AND price_date = %s
                    """,
                    (FEATURE_TABLE, ticker, price_date),
                )
                connection.execute(
                    "SELECT public.refresh_feature_01_control_status(%s, false)",
                    (ticker,),
                )
                return "EXHAUSTED"

        token = uuid.uuid4()
        claim = connection.execute(
            """
            UPDATE public."Feature_Calculation_Queue"
            SET status = 'PROCESSING', attempt_count = attempt_count + 1,
                source_attempt_count = source_attempt_count + 1,
                claimed_at = clock_timestamp(), claim_token = %s,
                claim_expires_at = clock_timestamp() + make_interval(mins => %s),
                completed_at = NULL,
                last_error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE feature_table = %s AND ticker = %s AND price_date = %s
            RETURNING claimed_at
            """,
            (token, LEASE_MINUTES, FEATURE_TABLE, ticker, price_date),
        ).fetchone()
        connection.execute(
            "SELECT public.refresh_feature_01_control_status(%s, false)",
            (ticker,),
        )
        return Job(
            ticker=ticker,
            price_date=price_date,
            source_ingestion_time=version,
            attempt_no=candidate["attempt_count"] + 1,
            source_attempt_count=candidate["source_attempt_count"] + 1,
            claim_token=token,
            started_at=claim["claimed_at"],
        )


def current_claim(connection: psycopg.Connection, job: Job) -> bool:
    row = connection.execute(
        """
        SELECT status, claim_token, source_ingestion_time
        FROM public."Feature_Calculation_Queue"
        WHERE feature_table = %s AND ticker = %s AND price_date = %s
        FOR UPDATE
        """,
        (FEATURE_TABLE, job.ticker, job.price_date),
    ).fetchone()
    return bool(
        row is not None
        and row["status"] == "PROCESSING"
        and row["claim_token"] == job.claim_token
        and row["source_ingestion_time"] == job.source_ingestion_time
    )


def validate_affected_rows(connection: psycopg.Connection, job: Job, expected: int) -> None:
    result = connection.execute(
        """
        WITH affected AS (
            SELECT ticker, date, close, volume
            FROM public."Price_Stock_Indonesia_IDX"
            WHERE ticker = %s AND date >= %s
            ORDER BY date
            LIMIT 121
        )
        SELECT count(*) AS source_rows,
               count(*) FILTER (
                   WHERE feature.ticker IS NULL
                      OR feature.close IS DISTINCT FROM affected.close
                      OR feature.volume IS DISTINCT FROM affected.volume
                      OR feature.sector IS DISTINCT FROM universe."Sector"
                      OR feature.industry IS DISTINCT FROM universe."Industry"
               ) AS mismatches
        FROM affected
        JOIN public."IDX_Stock_Universe" AS universe
          ON universe."Ticker" = affected.ticker
        LEFT JOIN public."Feature_01_Stock_Daily" AS feature
          ON feature.ticker = affected.ticker AND feature.date = affected.date
        """,
        (job.ticker, job.price_date),
    ).fetchone()
    if (
        result["source_rows"] < 1
        or result["source_rows"] != expected
        or result["mismatches"] != 0
    ):
        raise RuntimeError(
            "Feature 01 coverage/source validation failed: "
            f"expected={expected}, source={result['source_rows']}, "
            f"mismatches={result['mismatches']}"
        )


def process_one(job: Job) -> str:
    """Lock the queue key across refresh and completion to fence price re-ingestion."""
    with connect() as connection, connection.transaction():
        connection.execute("SET LOCAL statement_timeout = '120s'")
        if not current_claim(connection, job):
            record_attempt(
                connection, ticker=job.ticker, price_date=job.price_date,
                source_ingestion_time=job.source_ingestion_time,
                attempt_no=job.attempt_no, result="SUPERSEDED",
                started_at=job.started_at,
                detail="Claim or source version changed before refresh",
            )
            return "SUPERSEDED"

        refreshed = connection.execute(
            "SELECT public.refresh_feature_01_stock_daily(%s, ARRAY[%s]::text[]) AS refreshed_rows",
            (job.price_date, job.ticker),
        ).fetchone()["refreshed_rows"]
        validate_affected_rows(connection, job, refreshed)
        connection.execute(
            """
            UPDATE public."Feature_Calculation_Queue"
            SET status = 'DONE', claimed_at = NULL, claim_token = NULL,
                claim_expires_at = NULL, completed_at = clock_timestamp(),
                last_error = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE feature_table = %s AND ticker = %s AND price_date = %s
            """,
            (FEATURE_TABLE, job.ticker, job.price_date),
        )
        record_attempt(
            connection, ticker=job.ticker, price_date=job.price_date,
            source_ingestion_time=job.source_ingestion_time,
            attempt_no=job.attempt_no, result="SUCCESS",
            started_at=job.started_at, rows_refreshed=refreshed,
            detail="Feature 01 refresh and source coverage validated",
        )
        connection.execute(
            "SELECT public.refresh_feature_01_control_status(%s, true)",
            (job.ticker,),
        )
        return "SUCCESS"


def fail_one(job: Job, error: Exception) -> str:
    detail = error_detail(error)
    with connect() as connection, connection.transaction():
        connection.execute("SET LOCAL statement_timeout = '15s'")
        if not current_claim(connection, job):
            record_attempt(
                connection, ticker=job.ticker, price_date=job.price_date,
                source_ingestion_time=job.source_ingestion_time,
                attempt_no=job.attempt_no, result="SUPERSEDED",
                started_at=job.started_at,
                detail="Claim changed while handling a failed refresh",
            )
            return "SUPERSEDED"

        if job.source_attempt_count >= MAX_SOURCE_ATTEMPTS:
            next_attempt_at = None
        else:
            seconds = min(
                RETRY_CAP_SECONDS,
                RETRY_BASE_SECONDS * (2 ** (job.source_attempt_count - 1)),
            )
            next_attempt_at = seconds
        connection.execute(
            """
            UPDATE public."Feature_Calculation_Queue"
            SET status = 'FAILED', claimed_at = NULL, claim_token = NULL,
                claim_expires_at = NULL, completed_at = NULL,
                next_attempt_at = CASE
                    WHEN %s::integer IS NULL THEN 'infinity'::timestamptz
                    ELSE clock_timestamp() + (%s::integer * interval '1 second')
                END,
                last_error = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE feature_table = %s AND ticker = %s AND price_date = %s
            """,
            (next_attempt_at, next_attempt_at, detail,
             FEATURE_TABLE, job.ticker, job.price_date),
        )
        record_attempt(
            connection, ticker=job.ticker, price_date=job.price_date,
            source_ingestion_time=job.source_ingestion_time,
            attempt_no=job.attempt_no, result="FAILED",
            started_at=job.started_at, detail=detail,
        )
        connection.execute(
            "SELECT public.refresh_feature_01_control_status(%s, false)",
            (job.ticker,),
        )
        return "FAILED"


def run_once() -> str:
    job = claim_one()
    if job is None:
        return "IDLE"
    if job == "EXHAUSTED":
        emit("claim_exhausted")
        return "EXHAUSTED"
    emit("claim_started", ticker=job.ticker, price_date=job.price_date,
         attempt=job.source_attempt_count)
    try:
        outcome = process_one(job)
    except Exception as error:
        outcome = fail_one(job, error)
        emit("calculation_failed", ticker=job.ticker, price_date=job.price_date,
             attempt=job.source_attempt_count, error=error_detail(error))
    else:
        emit("calculation_completed", ticker=job.ticker,
             price_date=job.price_date, outcome=outcome)
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Process at most one item and exit")
    args = parser.parse_args()
    if args.once:
        emit("worker_once", outcome=run_once())
        return

    emit("worker_started", poll_seconds=POLL_SECONDS,
         max_source_attempts=MAX_SOURCE_ATTEMPTS)
    while True:
        try:
            outcome = run_once()
        except Exception as error:
            emit("worker_error", error=error_detail(error))
            time.sleep(10)
            continue
        if outcome == "IDLE":
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
