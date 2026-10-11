#!/usr/bin/env python3
"""Continuously calculate Feature04 for durable per-ticker queue items."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

sys.path.insert(0, str(Path(__file__).resolve().parent / "features" / "feature04"))
from engine import (  # noqa: E402
    COLUMNS,
    FEATURE_COLUMNS,
    VERSION,
    calculate_with_diagnostics,
    dependency_closure,
)


MAX_SOURCE_ATTEMPTS = 5
LEASE_MINUTES = 15
POLL_SECONDS = 5
RETRY_BASE_SECONDS = 30
RETRY_CAP_SECONDS = 30 * 60
PRICE_COLUMNS = (
    "ticker", "date", "open", "high", "low", "close", "volume", "timeframe",
    "tradingview_symbol", "source", "query_date", "ingestion_time",
)
LATEST_REQUIRED_AFTER = {
    "sma_20": 20, "sma_50": 50, "ema_12": 12, "ema_26": 26,
    "rsi_14": 15, "macd": 26, "macd_signal": 34, "macd_histogram": 34,
    "atr_14": 15, "bb_upper_20": 20, "bb_middle_20": 20, "bb_lower_20": 20,
    "adx_14": 28, "ema_50": 50, "ema_200": 200, "inside_bar": 2,
}


@dataclass(frozen=True)
class Job:
    ticker: str
    dirty_from_date: date
    requested_generation: int
    work_revision: int
    requested_columns: tuple[str, ...] | None
    origin_execution_id: str | None
    attempt_no: int
    source_attempt_count: int
    claim_token: uuid.UUID
    started_at: datetime


def connect() -> psycopg.Connection:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    return psycopg.connect(
        database_url,
        row_factory=dict_row,
        autocommit=True,
        application_name="feature-04-worker",
    )


def emit(event: str, **fields: object) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)


def error_detail(error: BaseException) -> str:
    if isinstance(error, psycopg.Error):
        message = error.diag.message_primary or type(error).__name__
    else:
        message = str(error) or type(error).__name__
    return f"{type(error).__name__}: {message}"[:1000]


def claim_one() -> Job | str | None:
    with connect() as connection, connection.transaction():
        connection.execute("SET LOCAL statement_timeout = '15s'")
        candidate = connection.execute(
            """
            SELECT * FROM public."Feature04_Calculation_Queue"
            WHERE (status IN ('PENDING','FAILED') AND next_attempt_at <= CURRENT_TIMESTAMP
                   AND source_attempt_count < %s)
               OR (status='PROCESSING' AND claim_expires_at <= CURRENT_TIMESTAMP)
            ORDER BY next_attempt_at,updated_at FOR UPDATE SKIP LOCKED LIMIT 1
            """,
            (MAX_SOURCE_ATTEMPTS,),
        ).fetchone()
        if candidate is None:
            return None
        if candidate["status"] == "PROCESSING" and candidate["source_attempt_count"] >= MAX_SOURCE_ATTEMPTS:
            connection.execute(
                """
                INSERT INTO public."Feature04_Calculation_Log"(
                  ticker,timeframe,source_generation,work_revision,requested_columns,
                  failed_columns,group_outcomes,result,calculation_version,started_at,error_code,detail)
                VALUES(%s,'Daily',%s,%s,%s,%s,%s::jsonb,'FAILED',%s,%s,
                       'LEASE_EXPIRED','Claim lease expired on the final allowed attempt')
                """,
                (
                    candidate["ticker"], candidate["requested_generation"], candidate["work_revision"],
                    candidate["requested_columns"], list(dependency_closure(candidate["requested_columns"])),
                    json.dumps({"worker": {"status": "FAILED", "error": "lease expired"}}),
                    VERSION, candidate["claimed_at"],
                ),
            )
            terminal_failure(
                connection, candidate["ticker"], int(candidate["requested_generation"]),
                int(candidate["work_revision"]), "LEASE_EXPIRED",
                "Maximum attempts exhausted after claim lease expiry",
            )
            return "EXHAUSTED"
        if candidate["status"] == "PROCESSING":
            connection.execute(
                """
                INSERT INTO public."Feature04_Calculation_Log"(
                  ticker,timeframe,source_generation,work_revision,requested_columns,
                  failed_columns,group_outcomes,result,calculation_version,started_at,
                  error_code,detail)
                VALUES(%s,'Daily',%s,%s,%s,%s,%s::jsonb,'FAILED',%s,%s,
                       'LEASE_EXPIRED','Claim lease expired before validated completion')
                """,
                (
                    candidate["ticker"], candidate["requested_generation"], candidate["work_revision"],
                    candidate["requested_columns"],
                    list(dependency_closure(candidate["requested_columns"])),
                    json.dumps({"worker": {"status": "FAILED", "error": "lease expired"}}),
                    VERSION, candidate["claimed_at"],
                ),
            )
        token = uuid.uuid4()
        claimed = connection.execute(
            """
            UPDATE public."Feature04_Calculation_Queue"
            SET status='PROCESSING',attempt_count=attempt_count+1,
                source_attempt_count=source_attempt_count+1,claimed_at=clock_timestamp(),
                claim_token=%s,claim_expires_at=clock_timestamp()+make_interval(mins=>%s),
                completed_at=NULL,last_error_code=NULL,last_error=NULL,updated_at=CURRENT_TIMESTAMP
            WHERE ticker=%s AND timeframe='Daily' RETURNING claimed_at,attempt_count,source_attempt_count
            """,
            (token, LEASE_MINUTES, candidate["ticker"]),
        ).fetchone()
        selected_columns = list(dependency_closure(candidate["requested_columns"]))
        connection.execute(
            """
            INSERT INTO public."Feature04_Column_Status"(
              ticker,timeframe,feature_column,requested_generation,completed_generation,
              calculation_version,status,dirty_from_date,updated_at)
            SELECT %s,'Daily',column_name,%s,0,%s,'PROCESSING',%s,CURRENT_TIMESTAMP
            FROM unnest(%s::text[]) column_name
            ON CONFLICT(ticker,timeframe,feature_column) DO UPDATE SET
              status='PROCESSING',requested_generation=EXCLUDED.requested_generation,
              calculation_version=EXCLUDED.calculation_version,
              dirty_from_date=EXCLUDED.dirty_from_date,updated_at=CURRENT_TIMESTAMP
            """,
            (
                candidate["ticker"], candidate["requested_generation"], VERSION,
                candidate["dirty_from_date"], selected_columns,
            ),
        )
        connection.execute(
            """
            UPDATE public."Feature04_Retry_Request" SET status='PROCESSING',
              started_at=coalesce(started_at,CURRENT_TIMESTAMP)
            WHERE ticker=%s AND source_generation=%s AND work_revision=%s AND status='PENDING'
            """,
            (candidate["ticker"], candidate["requested_generation"], candidate["work_revision"]),
        )
        connection.execute(
            """
            UPDATE public."Monitoring_Feature04_Ticker"
            SET status='PROCESSING',started_at=coalesce(started_at,CURRENT_TIMESTAMP),updated_at=CURRENT_TIMESTAMP
            WHERE ticker=%s AND timeframe='Daily' AND status='PENDING' AND required_generation<=%s
            """,
            (candidate["ticker"], candidate["requested_generation"]),
        )
        return Job(
            ticker=candidate["ticker"], dirty_from_date=candidate["dirty_from_date"],
            requested_generation=int(candidate["requested_generation"]),
            work_revision=int(candidate["work_revision"]),
            requested_columns=tuple(candidate["requested_columns"]) if candidate["requested_columns"] else None,
            origin_execution_id=candidate["origin_execution_id"],
            attempt_no=int(claimed["attempt_count"]),
            source_attempt_count=int(claimed["source_attempt_count"]),
            claim_token=token, started_at=claimed["claimed_at"],
        )


def load_history(connection: psycopg.Connection, ticker: str) -> list[dict]:
    rows = connection.execute(
        sql.SQL("SELECT {} FROM public.{} WHERE ticker=%s AND timeframe='Daily' ORDER BY date").format(
            sql.SQL(",").join(map(sql.Identifier, PRICE_COLUMNS)),
            sql.Identifier("Price_Stock_Indonesia_IDX"),
        ),
        (ticker,),
    ).fetchall()
    if not rows:
        raise RuntimeError(f"No Daily price history for {ticker}")
    if len(rows) > 5000:
        raise RuntimeError(f"Price history exceeds 5000-row controlled limit for {ticker}")
    return [dict(row) for row in rows]


def source_digest(rows: list[dict]) -> str:
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def unexpected_latest_nulls(rows: list[dict], selected: tuple[str, ...]) -> tuple[str, ...]:
    """Flag NULLs only where the formula contract requires a latest value."""
    if not rows:
        return ()
    latest = rows[-1]
    return tuple(
        column for column in selected
        if column in LATEST_REQUIRED_AFTER
        and len(rows) >= LATEST_REQUIRED_AFTER[column]
        and latest[column] is None
    )


def upsert_columns(
    connection: psycopg.Connection, rows: list[dict], feature_columns: tuple[str, ...]
) -> int:
    if not rows or not feature_columns:
        return 0
    insert_columns = ("ticker", "trade_date", "timeframe") + feature_columns + (
        "calculation_version", "calculated_at",
    )
    updated = feature_columns + ("calculation_version", "calculated_at")
    compared = feature_columns + ("calculation_version",)
    statement = sql.SQL(
        """INSERT INTO public.{} AS target ({}) VALUES ({})
        ON CONFLICT (ticker,trade_date,timeframe) DO UPDATE SET {}
        WHERE ROW({}) IS DISTINCT FROM ROW({})"""
    ).format(
        sql.Identifier("Feature04_Technical_Indicator"),
        sql.SQL(",").join(map(sql.Identifier, insert_columns)),
        sql.SQL(",").join(sql.Placeholder() for _ in insert_columns),
        sql.SQL(",").join(
            sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c)) for c in updated
        ),
        sql.SQL(",").join(sql.SQL("target.{}").format(sql.Identifier(c)) for c in compared),
        sql.SQL(",").join(sql.SQL("EXCLUDED.{}").format(sql.Identifier(c)) for c in compared),
    )
    changed = 0
    for row in rows:
        changed += connection.execute(statement, [row[c] for c in insert_columns]).rowcount
    return changed


def current_claim(connection: psycopg.Connection, job: Job) -> bool:
    row = connection.execute(
        """
        SELECT status,claim_token,requested_generation,work_revision
        FROM public."Feature04_Calculation_Queue"
        WHERE ticker=%s AND timeframe='Daily' FOR UPDATE
        """,
        (job.ticker,),
    ).fetchone()
    return bool(
        row and row["status"] == "PROCESSING" and row["claim_token"] == job.claim_token
        and row["requested_generation"] == job.requested_generation
        and row["work_revision"] == job.work_revision
    )


def finalize_runs(connection: psycopg.Connection) -> None:
    terminal = connection.execute(
        """
        WITH candidates AS (
          SELECT m.execution_id,
                 count(*) FILTER(WHERE t.status='SUCCESS')::int completed,
                 count(*) FILTER(WHERE t.status='FAILED')::int failed,
                 count(*) FILTER(WHERE t.status='BLOCKED')::int blocked,
                 count(*) FILTER(WHERE t.status IN ('PENDING','PROCESSING'))::int active
          FROM public."Monitoring_Feature04" m
          JOIN public."Monitoring_Feature04_Ticker" t USING(execution_id)
          WHERE m.status IN ('READY','PROCESSING') GROUP BY m.execution_id
        )
        UPDATE public."Monitoring_Feature04" m SET
          completed_tickers=c.completed,failed_tickers=c.failed,blocked_tickers=c.blocked,
          status=CASE WHEN c.active>0 THEN 'PROCESSING'
                      WHEN c.failed+c.blocked=0 THEN 'SUCCESS'
                      WHEN c.completed>0 THEN 'PARTIAL' ELSE 'FAILED' END,
          finished_at=CASE WHEN c.active=0 THEN CURRENT_TIMESTAMP ELSE NULL END,
          updated_at=CURRENT_TIMESTAMP
        FROM candidates c WHERE m.execution_id=c.execution_id
        RETURNING m.execution_id,m.status
        """
    ).fetchall()
    for row in terminal:
        if row["status"] not in ("SUCCESS", "PARTIAL", "FAILED"):
            continue
        connection.execute(
            """
            INSERT INTO public."Feature04_Notification_Outbox"(event_id,execution_id)
            VALUES(%s,%s) ON CONFLICT(execution_id,notification_type) DO NOTHING
            """,
            (uuid.uuid4(), row["execution_id"]),
        )
        connection.execute(
            """
            UPDATE public."Feature04_Retry_Request" r SET status=m.status,
              finished_at=m.finished_at,last_error=m.last_error
            FROM public."Monitoring_Feature04" m
            WHERE r.child_execution_id=m.execution_id AND r.status IN ('PENDING','PROCESSING')
            """
        )


def write_attempt(
    connection: psycopg.Connection, job: Job, *, requested: tuple[str, ...],
    successful: tuple[str, ...], failed: tuple[str, ...], outcomes: dict,
    result: str, history: list[dict], digest: str, changed: int,
    error_code: str | None = None, detail: str | None = None,
) -> int:
    retry = connection.execute(
        """SELECT request_id FROM public."Feature04_Retry_Request"
           WHERE ticker=%s AND source_generation=%s AND work_revision=%s
           ORDER BY created_at DESC LIMIT 1""",
        (job.ticker, job.requested_generation, job.work_revision),
    ).fetchone()
    return connection.execute(
        """
        INSERT INTO public."Feature04_Calculation_Log"(
          ticker,timeframe,source_generation,work_revision,retry_request_id,requested_columns,
          successful_columns,failed_columns,group_outcomes,result,source_start,source_end,
          source_rows,source_sha256,changed_rows,calculation_version,started_at,error_code,detail)
        VALUES(%s,'Daily',%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (
            job.ticker, job.requested_generation, job.work_revision,
            retry["request_id"] if retry else None, list(requested), list(successful), list(failed),
            json.dumps(outcomes), result, history[0]["date"], history[-1]["date"], len(history),
            digest, changed, VERSION, job.started_at, error_code, detail,
        ),
    ).fetchone()["id"]


def terminal_failure(
    connection: psycopg.Connection, ticker: str, generation: int, revision: int,
    error_code: str, detail: str,
) -> None:
    connection.execute(
        """
        UPDATE public."Feature04_Calculation_Queue" SET status='FAILED',claimed_at=NULL,
          claim_token=NULL,claim_expires_at=NULL,next_attempt_at='infinity'::timestamptz,
          last_error_code=%s,last_error=%s,updated_at=CURRENT_TIMESTAMP
        WHERE ticker=%s AND timeframe='Daily' AND requested_generation=%s AND work_revision=%s
        """,
        (error_code, detail, ticker, generation, revision),
    )
    connection.execute(
        """
        UPDATE public."Feature04_Column_Status" SET status='FAILED',last_error_code=%s,
          last_error=%s,updated_at=CURRENT_TIMESTAMP
        WHERE ticker=%s AND timeframe='Daily' AND requested_generation=%s AND status='PROCESSING'
        """,
        (error_code, detail, ticker, generation),
    )
    connection.execute(
        """
        UPDATE public."Monitoring_Feature04_Ticker" SET status='FAILED',last_error_code=%s,
          last_error=%s,finished_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
        WHERE ticker=%s AND timeframe='Daily' AND required_generation<=%s
          AND status IN ('PENDING','PROCESSING')
        """,
        (error_code, detail, ticker, generation),
    )
    finalize_runs(connection)


def process_one(job: Job) -> str:
    try:
        with connect() as read_connection:
            history = load_history(read_connection, job.ticker)
        digest = source_digest(history)
        requested = dependency_closure(job.requested_columns)
        rows, outcomes = calculate_with_diagnostics(history, requested_columns=requested)
        failed_set = {
            column for outcome in outcomes.values() if outcome["status"] == "FAILED"
            for column in outcome["columns"] if column in requested
        }
        unexpected_nulls = unexpected_latest_nulls(rows, requested)
        failed_set.update(unexpected_nulls)
        for column in unexpected_nulls:
            outcomes[f"validation:{column}"] = {
                "status": "FAILED", "columns": [column],
                "error": "Unexpected NULL on latest valid candle after required history",
            }
        successful = tuple(column for column in requested if column not in failed_set)
        failed = tuple(column for column in requested if column in failed_set)
        with connect() as connection, connection.transaction():
            connection.execute("SET LOCAL statement_timeout = '180s'")
            if not current_claim(connection, job):
                write_attempt(
                    connection, job, requested=requested, successful=(), failed=(),
                    outcomes={"worker": {"status": "SUPERSEDED"}}, result="SUPERSEDED",
                    history=history, digest=digest, changed=0,
                    error_code="SUPERSEDED", detail="Queue generation or work revision changed",
                )
                emit("feature04_superseded", ticker=job.ticker)
                return "SUPERSEDED"
            changed = upsert_columns(connection, rows, successful)
            result = "SUCCESS" if not failed else ("PARTIAL" if successful else "FAILED")
            attempt_id = write_attempt(
                connection, job, requested=requested, successful=successful, failed=failed,
                outcomes=outcomes, result=result, history=history, digest=digest, changed=changed,
                error_code="FORMULA_GROUP_FAILED" if failed else None,
                detail=json.dumps({k: v for k, v in outcomes.items() if v["status"] == "FAILED"})[:1000] or None,
            )
            if successful:
                connection.execute(
                    """
                    UPDATE public."Feature04_Column_Status" SET status='SUCCESS',
                      completed_generation=%s,calculation_version=%s,dirty_from_date=NULL,
                      validated_through=%s,last_attempt_id=%s,last_error_code=NULL,last_error=NULL,
                      last_calculated_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                    WHERE ticker=%s AND timeframe='Daily' AND feature_column=ANY(%s)
                    """,
                    (job.requested_generation, VERSION, history[-1]["date"], attempt_id, job.ticker, list(successful)),
                )
                for column in successful:
                    value_available = rows[-1][column] is not None
                    connection.execute(
                        """
                        UPDATE public."Feature04_Column_Status"
                        SET latest_value_available=%s,
                            null_reason=CASE WHEN %s THEN NULL ELSE 'EXPECTED_FORMULA_NULL' END
                        WHERE ticker=%s AND timeframe='Daily' AND feature_column=%s
                        """,
                        (value_available, value_available, job.ticker, column),
                    )
            if failed:
                connection.execute(
                    """
                    UPDATE public."Feature04_Column_Status" SET status='FAILED',last_attempt_id=%s,
                      last_error_code='FORMULA_GROUP_FAILED',last_error='See Feature04_Calculation_Log',
                      updated_at=CURRENT_TIMESTAMP
                    WHERE ticker=%s AND timeframe='Daily' AND feature_column=ANY(%s)
                    """,
                    (attempt_id, job.ticker, list(failed)),
                )
            if failed and job.source_attempt_count < MAX_SOURCE_ATTEMPTS:
                delay = min(RETRY_CAP_SECONDS, RETRY_BASE_SECONDS * (2 ** (job.source_attempt_count - 1)))
                connection.execute(
                    """
                    UPDATE public."Feature04_Calculation_Queue" SET status='FAILED',claimed_at=NULL,
                      claim_token=NULL,claim_expires_at=NULL,next_attempt_at=CURRENT_TIMESTAMP+make_interval(secs=>%s),
                      last_error_code='FORMULA_GROUP_FAILED',last_error='One or more formula groups failed',
                      updated_at=CURRENT_TIMESTAMP WHERE ticker=%s AND timeframe='Daily'
                    """,
                    (delay, job.ticker),
                )
                return result
            if failed:
                terminal_failure(
                    connection, job.ticker, job.requested_generation, job.work_revision,
                    "FORMULA_GROUP_FAILED", "Maximum attempts exhausted for failed formula groups",
                )
                return result
            connection.execute(
                """
                UPDATE public."Feature04_Calculation_Queue" SET status='DONE',
                  completed_generation=requested_generation,claimed_at=NULL,claim_token=NULL,
                  claim_expires_at=NULL,completed_at=CURRENT_TIMESTAMP,last_error_code=NULL,last_error=NULL,
                  updated_at=CURRENT_TIMESTAMP WHERE ticker=%s AND timeframe='Daily'
                """,
                (job.ticker,),
            )
            connection.execute(
                """
                UPDATE public."Monitoring_Feature04_Ticker" SET status='SUCCESS',
                  completed_generation=%s,finished_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                WHERE ticker=%s AND timeframe='Daily' AND required_generation<=%s
                  AND status IN ('PENDING','PROCESSING')
                """,
                (job.requested_generation, job.ticker, job.requested_generation),
            )
            finalize_runs(connection)
        emit("feature04_completed", ticker=job.ticker, changed_rows=changed, columns=len(successful))
        return "SUCCESS"
    except Exception as error:
        detail = error_detail(error)
        emit("feature04_failed", ticker=job.ticker, error=detail)
        with connect() as connection, connection.transaction():
            row = connection.execute(
                """SELECT claim_token,source_attempt_count FROM public."Feature04_Calculation_Queue"
                   WHERE ticker=%s AND timeframe='Daily' FOR UPDATE""",
                (job.ticker,),
            ).fetchone()
            if not row or row["claim_token"] != job.claim_token:
                return "SUPERSEDED"
            requested = dependency_closure(job.requested_columns)
            attempt_id = connection.execute(
                """
                INSERT INTO public."Feature04_Calculation_Log"(
                  ticker,timeframe,source_generation,work_revision,requested_columns,
                  failed_columns,group_outcomes,result,calculation_version,started_at,
                  error_code,detail)
                VALUES(%s,'Daily',%s,%s,%s,%s,%s::jsonb,'FAILED',%s,%s,
                       'WORKER_EXCEPTION',%s) RETURNING id
                """,
                (
                    job.ticker, job.requested_generation, job.work_revision, list(requested),
                    list(requested), json.dumps({"worker": {"status": "FAILED", "error": detail}}),
                    VERSION, job.started_at, detail,
                ),
            ).fetchone()["id"]
            connection.execute(
                """
                UPDATE public."Feature04_Column_Status" SET last_attempt_id=%s,
                  last_error_code='WORKER_EXCEPTION',last_error=%s,updated_at=CURRENT_TIMESTAMP
                WHERE ticker=%s AND timeframe='Daily' AND feature_column=ANY(%s)
                """,
                (attempt_id, detail, job.ticker, list(requested)),
            )
            if row["source_attempt_count"] >= MAX_SOURCE_ATTEMPTS:
                terminal_failure(
                    connection, job.ticker, job.requested_generation, job.work_revision,
                    "WORKER_EXCEPTION", detail,
                )
            else:
                delay = min(RETRY_CAP_SECONDS, RETRY_BASE_SECONDS * (2 ** (int(row["source_attempt_count"]) - 1)))
                connection.execute(
                    """
                    UPDATE public."Feature04_Calculation_Queue" SET status='FAILED',claimed_at=NULL,
                      claim_token=NULL,claim_expires_at=NULL,next_attempt_at=CURRENT_TIMESTAMP+make_interval(secs=>%s),
                      last_error_code='WORKER_EXCEPTION',last_error=%s,updated_at=CURRENT_TIMESTAMP
                    WHERE ticker=%s AND timeframe='Daily'
                    """,
                    (delay, detail, job.ticker),
                )
        return "FAILED"


def claim_outbox(connection: psycopg.Connection) -> dict | None:
    with connection.transaction():
        row = connection.execute(
            """
            SELECT o.event_id,o.execution_id FROM public."Feature04_Notification_Outbox" o
            JOIN public."Monitoring_Feature04" m USING(execution_id)
            WHERE o.status IN ('PENDING','FAILED') AND o.next_attempt_at<=CURRENT_TIMESTAMP
              AND (NOT m.price_notification_required OR m.price_notification_sent_at IS NOT NULL)
            ORDER BY o.created_at FOR UPDATE OF o SKIP LOCKED LIMIT 1
            """
        ).fetchone()
        if not row:
            return None
        token = uuid.uuid4()
        connection.execute(
            """
            UPDATE public."Feature04_Notification_Outbox" SET status='SENDING',attempt_count=attempt_count+1,
              claim_token=%s,claimed_at=CURRENT_TIMESTAMP,claim_expires_at=CURRENT_TIMESTAMP+interval '2 minutes',
              updated_at=CURRENT_TIMESTAMP WHERE event_id=%s
            """,
            (token, row["event_id"]),
        )
        return {**row, "claim_token": token}


def dispatch_one() -> bool:
    notify_url = os.environ.get("TELEGRAM_NOTIFY_URL", "").strip()
    notify_secret = os.environ.get("TELEGRAM_NOTIFY_SECRET", "").strip()
    if not notify_url or not notify_secret:
        return False
    with connect() as connection:
        event = claim_outbox(connection)
    if not event:
        return False
    payload = json.dumps({
        "source_table": "Monitoring_Feature04", "execution_id": event["execution_id"]
    }).encode()
    try:
        request = Request(
            notify_url, data=payload,
            headers={"Content-Type": "application/json", "X-Notify-Secret": notify_secret},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            response.read()
            if not 200 <= response.status < 300:
                raise RuntimeError(f"HTTP {response.status}")
        with connect() as connection:
            connection.execute(
                """
                UPDATE public."Feature04_Notification_Outbox" SET status='SENT',sent_at=CURRENT_TIMESTAMP,
                  claim_token=NULL,claimed_at=NULL,claim_expires_at=NULL,last_error=NULL,updated_at=CURRENT_TIMESTAMP
                WHERE event_id=%s AND claim_token=%s
                """,
                (event["event_id"], event["claim_token"]),
            )
        return True
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as error:
        with connect() as connection:
            connection.execute(
                """
                UPDATE public."Feature04_Notification_Outbox" SET status='FAILED',
                  next_attempt_at=CURRENT_TIMESTAMP+interval '2 minutes',claim_token=NULL,claimed_at=NULL,
                  claim_expires_at=NULL,last_error=%s,updated_at=CURRENT_TIMESTAMP
                WHERE event_id=%s AND claim_token=%s
                """,
                (error_detail(error), event["event_id"], event["claim_token"]),
            )
        return True


def main() -> None:
    emit("feature04_worker_started", calculation_version=VERSION)
    while True:
        try:
            job = claim_one()
            if isinstance(job, Job):
                process_one(job)
                continue
            if dispatch_one():
                continue
        except Exception as error:
            emit("feature04_worker_loop_error", error=error_detail(error))
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
