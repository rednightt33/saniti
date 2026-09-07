#!/usr/bin/env python3
"""Backfill Stockbit broker activity into Railway PostgreSQL, one date at a time."""

from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import http.client
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

try:
    import psycopg
    from psycopg import sql
except ModuleNotFoundError:  # Allows --help before dependencies are installed.
    psycopg = None
    sql = None


HOST = "exodus.stockbit.com"
BOARDS = {"REGULER": "Regular", "NEGO": "Nego", "TUNAI": "Tunai"}
INVESTORS = {"FOREIGN": "Foreign", "DOMESTIC": "Domestic"}
CSV_HEADERS = (
    "Date", "Symbol", "Broker", "Investor Type", "Market Board",
    "Buy Value", "Sell Value", "Net Value", "Buy Lots", "Sell Lots",
    "Net Lots", "Avg Buy", "Avg Sell",
)
CANONICAL_KEYS = (
    "date", "symbol", "broker", "investor_type", "market_board",
    "buy_value", "sell_value", "net_value", "buy_lots", "sell_lots",
    "net_lots", "avg_buy", "avg_sell",
)
COLUMN_ALIASES = {
    "date": ("Date", "trade_date", "date"),
    "symbol": ("Symbol", "symbol", "stock_code"),
    "broker": ("Broker", "broker", "broker_code"),
    "investor_type": ("Investor Type", "investor_type", "investor"),
    "market_board": ("Market Board", "market_board", "board"),
    "buy_value": ("Buy Value", "buy_value"),
    "sell_value": ("Sell Value", "sell_value"),
    "net_value": ("Net Value", "net_value"),
    "buy_lots": ("Buy Lots", "buy_lots"),
    "sell_lots": ("Sell Lots", "sell_lots"),
    "net_lots": ("Net Lots", "net_lots"),
    "avg_buy": ("Avg Buy", "avg_buy", "average_buy"),
    "avg_sell": ("Avg Sell", "avg_sell", "average_sell"),
}


class StockbitError(RuntimeError):
    pass


class StockbitAuthenticationLimitError(StockbitError):
    pass


class DatabaseError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(ZoneInfo("UTC"))


def write_status(path: Path | None, values: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(values)
    payload["updated_at"] = utc_now().isoformat()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


@dataclass(frozen=True)
class FilterTask:
    trade_date: str
    broker: str
    investor: str
    board: str


@dataclass
class FilterResult:
    task: FilterTask
    rows: list[tuple[Any, ...]]
    pages: int
    requests: int
    buy_rows: int
    sell_rows: int
    response_bytes: int
    elapsed_ms: int
    response_sha256: str
    duplicates_skipped: int


@dataclass(frozen=True)
class TargetTable:
    schema: str
    table: str
    columns: dict[str, str]
    data_types: dict[str, str]
    generated: frozenset[str]


@dataclass(frozen=True)
class DateResult:
    trade_date: date
    rows: list[tuple[Any, ...]]
    filters: int
    requests: int
    response_bytes: int
    elapsed_ms: int
    duplicates_skipped: int


def decimal_value(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise StockbitError(f"Missing numeric field: {label}")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise StockbitError(f"Invalid numeric field {label}: {value!r}") from exc
    if not number.is_finite() or number < 0:
        raise StockbitError(f"Invalid nonnegative field {label}: {value!r}")
    return number


def optional_decimal(value: Any, label: str) -> Decimal | None:
    return None if value is None else decimal_value(value, label)


def plain_decimal(value: Decimal | None) -> str:
    if value is None:
        return ""
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


class StockbitFetcher:
    def __init__(
        self, token: str, timeout: float, delay: float, page_limit: int,
        authentication_failure_limit: int,
    ) -> None:
        token = token.strip().replace("\\_", "_")
        if token.count(".") != 2:
            raise StockbitError("STOCKBIT_TOKEN is not a valid JWT shape")
        self.token = token
        self.timeout = timeout
        self.delay = delay
        self.page_limit = page_limit
        self.authentication_failure_limit = authentication_failure_limit
        self.authentication_failures = 0
        self.authentication_lock = threading.Lock()
        self.local = threading.local()

    def _register_authentication_failure(self) -> int:
        with self.authentication_lock:
            self.authentication_failures += 1
            return self.authentication_failures

    def _reset_authentication_failures(self) -> None:
        with self.authentication_lock:
            self.authentication_failures = 0

    def _connection(self) -> http.client.HTTPSConnection:
        connection = getattr(self.local, "connection", None)
        if connection is None:
            connection = http.client.HTTPSConnection(HOST, timeout=self.timeout)
            self.local.connection = connection
            self.local.last_finished = 0.0
        return connection

    def _reset_connection(self) -> None:
        connection = getattr(self.local, "connection", None)
        if connection is not None:
            connection.close()
        self.local.connection = None

    def get_json(self, path: str) -> tuple[dict[str, Any], bytes, int]:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Origin": "https://stockbit.com",
            "Referer": "https://stockbit.com/",
            "Accept": "application/json",
            "User-Agent": "stockbit-marketwide-broker-activity/2.0",
        }
        max_attempts = max(4, self.authentication_failure_limit)
        for attempt in range(1, max_attempts + 1):
            last_finished = getattr(self.local, "last_finished", 0.0)
            remaining = self.delay - (time.monotonic() - last_finished)
            if remaining > 0:
                time.sleep(remaining)
            started = time.monotonic()
            try:
                connection = self._connection()
                connection.request("GET", path, headers=headers)
                response = connection.getresponse()
                raw = response.read()
            except (OSError, TimeoutError, http.client.HTTPException) as exc:
                self._reset_connection()
                if attempt == max_attempts:
                    raise StockbitError(f"Network failure after {attempt} attempts: {exc}") from exc
                time.sleep(2 ** (attempt - 1))
                continue
            finally:
                self.local.last_finished = time.monotonic()

            elapsed_ms = round((time.monotonic() - started) * 1000)
            if response.status in (401, 403):
                self._reset_connection()
                failure_count = self._register_authentication_failure()
                if failure_count >= self.authentication_failure_limit:
                    raise StockbitAuthenticationLimitError(
                        f"Stockbit authentication failed {failure_count} consecutive times "
                        f"(last HTTP {response.status})"
                    )
                time.sleep(min(30.0, 2 ** (failure_count - 1)))
                continue
            if response.status == 429 or 500 <= response.status < 600:
                self._reset_connection()
                if attempt == max_attempts:
                    raise StockbitError(f"Stockbit returned HTTP {response.status} after retries")
                retry_after = response.getheader("Retry-After")
                time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt)
                continue
            if response.status != 200:
                preview = raw[:200].decode("utf-8", errors="replace")
                raise StockbitError(f"Stockbit returned HTTP {response.status}: {preview}")
            self._reset_authentication_failures()
            try:
                body = json.loads(raw, parse_float=Decimal, parse_int=Decimal)
            except json.JSONDecodeError as exc:
                raise StockbitError("Stockbit returned non-JSON content") from exc
            if not isinstance(body, dict):
                raise StockbitError("Stockbit returned a non-object JSON envelope")
            return body, raw, elapsed_ms
        raise AssertionError("retry loop exited unexpectedly")

    def broker_directory(self) -> list[dict[str, str]]:
        body, _, _ = self.get_json("/findata-view/marketdetectors/brokers?page=1&limit=200")
        rows = body.get("data")
        if not isinstance(rows, list):
            raise StockbitError("Broker directory is missing data array")
        brokers: list[dict[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise StockbitError("Broker directory contains a non-object row")
            code = row.get("code")
            if not isinstance(code, str) or len(code) != 2 or not code.isalnum():
                raise StockbitError(f"Invalid broker code in directory: {code!r}")
            brokers.append({
                "code": code.upper(),
                "name": str(row.get("name") or ""),
                "group": str(row.get("group") or ""),
            })
        if len(brokers) != len({row["code"] for row in brokers}):
            raise StockbitError("Broker directory contains duplicate codes")
        return brokers

    def activity(self, task: FilterTask) -> FilterResult:
        by_symbol: dict[str, dict[str, Any]] = {}
        page = 1
        total_requests = total_buy = total_sell = total_bytes = total_elapsed = 0
        duplicates_skipped = 0
        hashes = hashlib.sha256()
        while True:
            params = urlencode({
                "broker_code": task.broker,
                "from": task.trade_date,
                "to": task.trade_date,
                "market_board": f"MARKET_TYPE_{task.board}",
                "transaction_type": "TRANSACTION_TYPE_GROSS",
                "investor_type": f"INVESTOR_TYPE_{task.investor}",
                "limit": str(self.page_limit),
                "page": str(page),
            })
            body, raw, elapsed_ms = self.get_json(f"/order-trade/broker/activity?{params}")
            total_requests += 1
            total_bytes += len(raw)
            total_elapsed += elapsed_ms
            hashes.update(hashlib.sha256(raw).digest())

            data = body.get("data")
            if not isinstance(data, dict):
                raise StockbitError(f"Missing data object for {task}")
            if data.get("from") != task.trade_date or data.get("to") != task.trade_date:
                raise StockbitError(f"Unexpected response window for {task}")
            transaction = data.get("broker_activity_transaction")
            if not isinstance(transaction, dict):
                raise StockbitError(f"Missing broker activity transaction for {task}")
            buys = transaction.get("brokers_buy")
            sells = transaction.get("brokers_sell")
            if not isinstance(buys, list) or not isinstance(sells, list):
                raise StockbitError(f"Missing buy/sell arrays for {task}")
            total_buy += len(buys)
            total_sell += len(sells)

            for side, entries in (("buy", buys), ("sell", sells)):
                for item in entries:
                    if not isinstance(item, dict):
                        raise StockbitError(f"Non-object {side} row for {task}")
                    symbol = item.get("stock_code")
                    if not isinstance(symbol, str) or not symbol.strip() or len(symbol) > 32:
                        raise StockbitError(f"Invalid symbol in {side} row for {task}: {symbol!r}")
                    symbol = symbol.strip().upper()
                    if item.get("broker_code") != task.broker or item.get("date") != task.trade_date:
                        raise StockbitError(f"Unexpected identity in {side} row for {task}: {symbol}")
                    record = by_symbol.setdefault(symbol, {
                        "buy_seen": False, "sell_seen": False,
                        "buy_source": None, "sell_source": None,
                        "buy_value": Decimal(0), "sell_value": Decimal(0),
                        "buy_lots": Decimal(0), "sell_lots": Decimal(0),
                        "avg_buy": None, "avg_sell": None,
                    })
                    seen_key = f"{side}_seen"
                    source_key = f"{side}_source"
                    if record[seen_key]:
                        if record[source_key] == item:
                            duplicates_skipped += 1
                            continue
                        raise StockbitError(f"Conflicting duplicate {side} row for {task}: {symbol}")
                    record[seen_key] = True
                    record[source_key] = item
                    record[f"{side}_value"] = decimal_value(item.get("value"), f"{task}.{symbol}.value")
                    record[f"{side}_lots"] = decimal_value(item.get("lot"), f"{task}.{symbol}.lot")
                    record[f"avg_{side}"] = optional_decimal(item.get("avg_price"), f"{task}.{symbol}.avg_price")

            if len(buys) < self.page_limit and len(sells) < self.page_limit:
                break
            page += 1
            if page > 100:
                raise StockbitError(f"Pagination exceeded 100 pages for {task}")

        rows: list[tuple[Any, ...]] = []
        for symbol, item in by_symbol.items():
            buy_value, sell_value = item["buy_value"], item["sell_value"]
            buy_lots, sell_lots = item["buy_lots"], item["sell_lots"]
            rows.append((
                task.trade_date, symbol, task.broker,
                INVESTORS[task.investor], BOARDS[task.board],
                plain_decimal(buy_value), plain_decimal(sell_value),
                plain_decimal(buy_value - sell_value),
                plain_decimal(buy_lots), plain_decimal(sell_lots),
                plain_decimal(buy_lots - sell_lots),
                plain_decimal(item["avg_buy"]), plain_decimal(item["avg_sell"]),
            ))
        return FilterResult(
            task=task, rows=rows, pages=page, requests=total_requests,
            buy_rows=total_buy, sell_rows=total_sell,
            response_bytes=total_bytes, elapsed_ms=total_elapsed,
            response_sha256=hashes.hexdigest(),
            duplicates_skipped=duplicates_skipped,
        )


def normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def require_psycopg() -> None:
    if psycopg is None or sql is None:
        raise DatabaseError("Install dependencies with: python -m pip install -r requirements.txt")


def connect_database(database_url: str) -> Any:
    require_psycopg()
    try:
        return psycopg.connect(
            database_url,
            connect_timeout=30,
            application_name="stockbit_backfill",
            autocommit=True,
        )
    except Exception as exc:
        raise DatabaseError(f"Unable to connect to PostgreSQL: {exc}") from exc


def resolve_target_table(connection: Any, requested_schema: str, requested_table: str) -> TargetTable:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE lower(table_schema)=lower(%s) AND lower(table_name)=lower(%s) "
            "AND table_type='BASE TABLE'",
            (requested_schema, requested_table),
        )
        matches = cursor.fetchall()
    if len(matches) != 1:
        raise DatabaseError(
            f"Expected exactly one table named {requested_schema}.{requested_table}; found {len(matches)}"
        )
    actual_schema, actual_table = matches[0]
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT column_name, data_type, is_generated FROM information_schema.columns "
            "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
            (actual_schema, actual_table),
        )
        database_columns = cursor.fetchall()

    normalized_to_actual: dict[str, tuple[str, str, bool]] = {}
    for column_name, data_type, is_generated in database_columns:
        normalized = normalize_identifier(column_name)
        if normalized in normalized_to_actual:
            raise DatabaseError(f"Ambiguous normalized column name: {column_name}")
        normalized_to_actual[normalized] = (column_name, data_type, is_generated == "ALWAYS")

    resolved: dict[str, str] = {}
    data_types: dict[str, str] = {}
    generated: set[str] = set()
    missing: list[str] = []
    for key in CANONICAL_KEYS:
        match = next(
            (normalized_to_actual.get(normalize_identifier(alias)) for alias in COLUMN_ALIASES[key]
             if normalized_to_actual.get(normalize_identifier(alias)) is not None),
            None,
        )
        if match is None:
            missing.append(CSV_HEADERS[CANONICAL_KEYS.index(key)])
            continue
        column_name, data_type, is_generated = match
        resolved[key] = column_name
        data_types[key] = data_type
        if is_generated:
            generated.add(key)
    if missing:
        existing = ", ".join(row[0] for row in database_columns)
        raise DatabaseError(
            f"Target table is missing required columns: {', '.join(missing)}. Existing columns: {existing}"
        )
    return TargetTable(actual_schema, actual_table, resolved, data_types, frozenset(generated))


def create_load_log(connection: Any, target: TargetTable, log_table: str) -> None:
    statement = sql.SQL("""
        CREATE TABLE IF NOT EXISTS {}.{} (
            target_table text NOT NULL,
            trade_date date NOT NULL,
            status text NOT NULL,
            filter_count integer NOT NULL,
            request_count integer NOT NULL,
            row_count bigint NOT NULL,
            response_bytes bigint NOT NULL,
            fetch_elapsed_ms bigint NOT NULL,
            completed_at timestamptz,
            attempt_count integer NOT NULL DEFAULT 0,
            last_error text,
            last_attempt_at timestamptz,
            status_changed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (target_table, trade_date)
        )
    """).format(sql.Identifier(target.schema), sql.Identifier(log_table))
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(statement)
            qualified = sql.SQL("{}.{}").format(
                sql.Identifier(target.schema), sql.Identifier(log_table)
            )
            cursor.execute(sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS attempt_count integer NOT NULL DEFAULT 0").format(qualified))
            cursor.execute(sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS last_error text").format(qualified))
            cursor.execute(sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS last_attempt_at timestamptz").format(qualified))
            cursor.execute(sql.SQL("ALTER TABLE {} ADD COLUMN IF NOT EXISTS status_changed_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP").format(qualified))
            cursor.execute(sql.SQL("ALTER TABLE {} ALTER COLUMN completed_at DROP NOT NULL").format(qualified))


def create_supporting_indexes(connection: Any, target: TargetTable) -> None:
    base_name = normalize_identifier(target.table)[:32] or "broker_summary"
    date_index = f"stockbit_{base_name}_date_idx"
    natural_key_index = f"stockbit_{base_name}_natural_key_uidx"
    date_statement = sql.SQL(
        "CREATE INDEX IF NOT EXISTS {} ON {}.{} ((CAST({} AS date)))"
    ).format(
        sql.Identifier(date_index),
        sql.Identifier(target.schema),
        sql.Identifier(target.table),
        sql.Identifier(target.columns["date"]),
    )
    unique_statement = sql.SQL(
        "CREATE UNIQUE INDEX IF NOT EXISTS {} ON {}.{} ({})"
    ).format(
        sql.Identifier(natural_key_index),
        sql.Identifier(target.schema),
        sql.Identifier(target.table),
        sql.SQL(", ").join(
            sql.Identifier(target.columns[key])
            for key in ("date", "symbol", "broker", "investor_type", "market_board")
        ),
    )
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(date_statement)
            cursor.execute(unique_statement)


def target_key(target: TargetTable) -> str:
    return f"{target.schema}.{target.table}"


def completed_dates(connection: Any, target: TargetTable, log_table: str, start: date, end: date) -> set[date]:
    statement = sql.SQL(
        "SELECT trade_date FROM {}.{} WHERE target_table=%s AND status='COMPLETED' "
        "AND trade_date BETWEEN %s AND %s"
    ).format(sql.Identifier(target.schema), sql.Identifier(log_table))
    with connection.cursor() as cursor:
        cursor.execute(statement, (target_key(target), start, end))
        return {row[0] for row in cursor.fetchall()}


def replace_date(
    connection: Any,
    target: TargetTable,
    log_table: str,
    result: DateResult,
    attempt_count: int,
) -> None:
    delete_statement = sql.SQL("DELETE FROM {}.{} WHERE CAST({} AS date)=%s").format(
        sql.Identifier(target.schema), sql.Identifier(target.table),
        sql.Identifier(target.columns["date"]),
    )
    insert_keys = [key for key in CANONICAL_KEYS if key not in target.generated]
    insert_indices = [CANONICAL_KEYS.index(key) for key in insert_keys]
    copy_statement = sql.SQL("COPY {}.{} ({}) FROM STDIN").format(
        sql.Identifier(target.schema), sql.Identifier(target.table),
        sql.SQL(", ").join(sql.Identifier(target.columns[key]) for key in insert_keys),
    )
    log_statement = sql.SQL("""
        INSERT INTO {}.{} (
            target_table, trade_date, status, filter_count, request_count,
            row_count, response_bytes, fetch_elapsed_ms, completed_at,
            attempt_count, last_error, last_attempt_at, status_changed_at
        ) VALUES (%s,%s,'COMPLETED',%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s)
        ON CONFLICT (target_table, trade_date) DO UPDATE SET
            status=EXCLUDED.status, filter_count=EXCLUDED.filter_count,
            request_count=EXCLUDED.request_count, row_count=EXCLUDED.row_count,
            response_bytes=EXCLUDED.response_bytes,
            fetch_elapsed_ms=EXCLUDED.fetch_elapsed_ms,
            completed_at=EXCLUDED.completed_at,
            attempt_count={}.{}.attempt_count + EXCLUDED.attempt_count,
            last_error=NULL,
            last_attempt_at=EXCLUDED.last_attempt_at,
            status_changed_at=EXCLUDED.status_changed_at
    """).format(
        sql.Identifier(target.schema), sql.Identifier(log_table),
        sql.Identifier(target.schema), sql.Identifier(log_table),
    )
    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(delete_statement, (result.trade_date,))
                if result.rows:
                    with cursor.copy(copy_statement) as copy:
                        for row in result.rows:
                            copy.write_row(tuple(row[index] or None for index in insert_indices))
                finished_at = utc_now()
                cursor.execute(log_statement, (
                    target_key(target), result.trade_date, result.filters,
                    result.requests, len(result.rows), result.response_bytes,
                    result.elapsed_ms, finished_at, attempt_count, finished_at, finished_at,
                ))
    except Exception as exc:
        raise DatabaseError(f"Unable to save {result.trade_date.isoformat()}: {exc}") from exc


def record_needs_review(
    connection: Any,
    target: TargetTable,
    log_table: str,
    trade_date: date,
    attempt_count: int,
    error: str,
) -> None:
    statement = sql.SQL("""
        INSERT INTO {}.{} (
            target_table, trade_date, status, filter_count, request_count,
            row_count, response_bytes, fetch_elapsed_ms, completed_at,
            attempt_count, last_error, last_attempt_at, status_changed_at
        ) VALUES (%s,%s,'NEEDS_REVIEW',0,0,0,0,0,NULL,%s,%s,%s,%s)
        ON CONFLICT (target_table, trade_date) DO UPDATE SET
            status='NEEDS_REVIEW',
            completed_at=NULL,
            attempt_count={}.{}.attempt_count + EXCLUDED.attempt_count,
            last_error=EXCLUDED.last_error,
            last_attempt_at=EXCLUDED.last_attempt_at,
            status_changed_at=EXCLUDED.status_changed_at
    """).format(
        sql.Identifier(target.schema), sql.Identifier(log_table),
        sql.Identifier(target.schema), sql.Identifier(log_table),
    )
    attempted_at = utc_now()
    try:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(statement, (
                    target_key(target), trade_date, attempt_count,
                    error[-4000:], attempted_at, attempted_at,
                ))
    except Exception as exc:
        raise DatabaseError(f"Unable to mark {trade_date.isoformat()} NEEDS_REVIEW: {exc}") from exc


def export_date(connection: Any, target: TargetTable, output_directory: Path, trade_date: date) -> tuple[Path, int]:
    selected = sql.SQL(", ").join(sql.Identifier(target.columns[key]) for key in CANONICAL_KEYS)
    statement = sql.SQL(
        "SELECT {} FROM {}.{} WHERE CAST({} AS date) = %s "
        "ORDER BY {}, {}, {}, {}"
    ).format(
        selected, sql.Identifier(target.schema), sql.Identifier(target.table),
        sql.Identifier(target.columns["date"]),
        sql.Identifier(target.columns["symbol"]), sql.Identifier(target.columns["broker"]),
        sql.Identifier(target.columns["investor_type"]), sql.Identifier(target.columns["market_board"]),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / f"IDX_Broker_Summary_{trade_date.isoformat()}.csv"
    temporary_output = output.with_suffix(".csv.tmp")
    row_count = 0
    try:
        with temporary_output.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(CSV_HEADERS)
            with connection.cursor() as cursor:
                cursor.execute(statement, (trade_date,))
                while True:
                    rows = cursor.fetchmany(10_000)
                    if not rows:
                        break
                    writer.writerows(rows)
                    row_count += len(rows)
        temporary_output.replace(output)
    except BaseException:
        temporary_output.unlink(missing_ok=True)
        raise
    return output, row_count


def weekdays_between(start: date, end: date) -> list[date]:
    values: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            values.append(current)
        current += timedelta(days=1)
    return values


def fetch_date(
    executor: ThreadPoolExecutor,
    fetcher: StockbitFetcher,
    trade_date: date,
    brokers: Sequence[dict[str, str]],
    investors: Sequence[str],
    boards: Sequence[str],
) -> DateResult:
    date_text = trade_date.isoformat()
    tasks = [
        FilterTask(date_text, broker["code"], investor, board)
        for broker in brokers for investor in investors for board in boards
    ]
    futures: dict[Future[FilterResult], FilterTask] = {
        executor.submit(fetcher.activity, task): task for task in tasks
    }
    results: list[FilterResult] = []
    try:
        for future in as_completed(futures):
            results.append(future.result())
    except BaseException:
        for future in futures:
            future.cancel()
        raise
    if len(results) != len(tasks):
        raise StockbitError(
            f"Completeness check failed for {date_text}: {len(results)} of {len(tasks)} filters"
        )
    rows = [row for result in results for row in result.rows]
    keys = {(row[0], row[1], row[2], row[3], row[4]) for row in rows}
    if len(keys) != len(rows):
        raise StockbitError(f"Duplicate natural keys detected for {date_text}")
    return DateResult(
        trade_date=trade_date, rows=rows, filters=len(results),
        requests=sum(result.requests for result in results),
        response_bytes=sum(result.response_bytes for result in results),
        elapsed_ms=sum(result.elapsed_ms for result in results),
        duplicates_skipped=sum(result.duplicates_skipped for result in results),
    )


def database_schema_summary(target: TargetTable) -> dict[str, Any]:
    return {
        "target": target_key(target),
        "columns": {
            key: {"database_name": target.columns[key], "data_type": target.data_types[key], "generated": key in target.generated}
            for key in CANONICAL_KEYS
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Stockbit broker activity into Railway PostgreSQL")
    parser.add_argument("--from-date", type=date.fromisoformat, default=date(2025, 9, 1))
    parser.add_argument("--to-date", type=date.fromisoformat, default=date(2026, 8, 31))
    parser.add_argument("--date-order", choices=("ascending", "descending"), default="ascending")
    parser.add_argument("--boards", nargs="+", choices=tuple(BOARDS), default=tuple(BOARDS))
    parser.add_argument("--investors", nargs="+", choices=tuple(INVESTORS), default=tuple(INVESTORS))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--delay", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--page-limit", type=int, default=1000)
    parser.add_argument("--expected-brokers", type=int, default=112)
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--schema", default="public")
    parser.add_argument("--table", default="IDX_Broker_Summary")
    parser.add_argument("--log-table", default="stockbit_broker_summary_load_log")
    parser.add_argument(
        "--daily-output-dir", "--monthly-output-dir", dest="daily_output_dir", type=Path,
        default=Path("outputs/IDX_Broker_Summary_daily"),
    )
    parser.add_argument("--no-daily-export", action="store_true")
    parser.add_argument("--refresh-completed-dates", action="store_true")
    parser.add_argument("--check-database-only", action="store_true")
    parser.add_argument("--token-stdin", action="store_true")
    parser.add_argument("--date-retries", type=int, default=3)
    parser.add_argument("--authentication-failure-limit", type=int, default=5)
    parser.add_argument("--retry-base-seconds", type=float, default=30.0)
    parser.add_argument("--status-file", type=Path)
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.from_date > args.to_date:
        raise StockbitError("--from-date cannot be later than --to-date")
    if not 1 <= args.workers <= 16:
        raise StockbitError("--workers must be between 1 and 16")
    if args.delay < 0:
        raise StockbitError("--delay cannot be negative")
    if not 1 <= args.page_limit <= 1000:
        raise StockbitError("--page-limit must be between 1 and 1000")
    if args.expected_brokers < 0:
        raise StockbitError("--expected-brokers cannot be negative")
    if not 1 <= args.date_retries <= 20:
        raise StockbitError("--date-retries must be between 1 and 20")
    if not 1 <= args.authentication_failure_limit <= 20:
        raise StockbitError("--authentication-failure-limit must be between 1 and 20")
    if args.retry_base_seconds < 0:
        raise StockbitError("--retry-base-seconds cannot be negative")


def main() -> int:
    args = parse_args()
    validate_args(args)
    requested_dates = weekdays_between(args.from_date, args.to_date)
    if args.date_order == "descending":
        requested_dates.reverse()
    status: dict[str, Any] = {
        "state": "STARTING",
        "from_date": args.from_date.isoformat(),
        "to_date": args.to_date.isoformat(),
        "date_order": args.date_order,
        "daily_export_enabled": not args.no_daily_export,
        "current_date": None,
        "last_completed_date": None,
        "latest_failed_date": None,
        "current_attempt": 0,
        "date_retry_limit": args.date_retries,
        "authentication_failure_limit": args.authentication_failure_limit,
        "completed_count": 0,
        "total_dates": len(requested_dates),
        "rows_loaded_this_run": 0,
        "needs_review_count": 0,
        "last_error": None,
    }
    write_status(args.status_file, status)
    connection = None
    try:
        database_url = os.environ.get(args.database_url_env, "").strip()
        if not database_url:
            raise DatabaseError(f"Set the {args.database_url_env} environment variable")
        connection = connect_database(database_url)
        target = resolve_target_table(connection, args.schema, args.table)
        print(json.dumps(database_schema_summary(target), default=str), file=sys.stderr)
        if args.check_database_only:
            print(json.dumps({"status": "database_schema_valid", "target": target_key(target)}))
            return 0

        create_load_log(connection, target, args.log_table)
        # The Railway target table already has a primary key on the complete
        # natural key, beginning with Date, so extra date/unique indexes would
        # duplicate existing coverage.

        token = sys.stdin.readline().strip() if args.token_stdin else os.environ.get("STOCKBIT_TOKEN", "").strip()
        if not token and sys.stdin.isatty():
            token = getpass.getpass("Stockbit JWT: ").strip()
        if not token:
            raise StockbitError("Set STOCKBIT_TOKEN, use --token-stdin, or run interactively")
        fetcher = StockbitFetcher(
            token, args.timeout, args.delay, args.page_limit,
            args.authentication_failure_limit,
        )
        brokers = fetcher.broker_directory()
        if args.expected_brokers and len(brokers) != args.expected_brokers:
            raise StockbitError(f"Expected {args.expected_brokers} brokers, received {len(brokers)}")

        complete = completed_dates(connection, target, args.log_table, args.from_date, args.to_date)
        run_started = time.monotonic()
        totals = {"dates_loaded": 0, "rows_loaded": 0, "requests": 1, "duplicates_skipped": 0}
        needs_review: set[date] = set()
        status["state"] = "RUNNING"
        status["completed_count"] = len(set(requested_dates) & complete)
        write_status(args.status_file, status)
        print(json.dumps({
            "status": "starting", "from_date": args.from_date.isoformat(),
            "to_date": args.to_date.isoformat(), "weekday_dates": len(requested_dates),
            "date_order": args.date_order,
            "dates_already_complete": len(set(requested_dates) & complete),
            "brokers": len(brokers),
            "filters_per_date": len(brokers) * len(args.investors) * len(args.boards),
        }), file=sys.stderr)

        for trade_date in requested_dates:
            date_succeeded = False
            status["current_date"] = trade_date.isoformat()
            status["current_attempt"] = 0
            status["last_error"] = None
            write_status(args.status_file, status)
            if trade_date in complete and not args.refresh_completed_dates:
                status["last_completed_date"] = trade_date.isoformat()
                print(json.dumps({"status": "skipped_complete_date", "date": trade_date.isoformat()}), file=sys.stderr)
            else:
                for attempt in range(1, args.date_retries + 1):
                    status["current_attempt"] = attempt
                    status["state"] = "FETCHING"
                    write_status(args.status_file, status)
                    date_started = time.monotonic()
                    try:
                        # A fresh executor per attempt prevents failed work from
                        # overlapping the next retry.
                        with ThreadPoolExecutor(max_workers=args.workers) as executor:
                            result = fetch_date(executor, fetcher, trade_date, brokers, args.investors, args.boards)
                        replace_date(connection, target, args.log_table, result, attempt)
                    except StockbitAuthenticationLimitError:
                        # Authentication exhaustion is process-wide. Let the
                        # outer handler stop the runner instead of retrying the
                        # date or incorrectly recording it as NEEDS_REVIEW.
                        raise
                    except StockbitError as exc:
                        status["latest_failed_date"] = trade_date.isoformat()
                        status["last_error"] = str(exc)
                        print(json.dumps({
                            "status": "date_attempt_failed", "date": trade_date.isoformat(),
                            "attempt": attempt, "attempt_limit": args.date_retries,
                            "error": str(exc),
                        }), file=sys.stderr)
                        write_status(args.status_file, status)
                        if attempt < args.date_retries:
                            time.sleep(args.retry_base_seconds * (2 ** (attempt - 1)))
                        continue

                    complete.add(trade_date)
                    date_succeeded = True
                    totals["dates_loaded"] += 1
                    totals["rows_loaded"] += len(result.rows)
                    totals["requests"] += result.requests
                    totals["duplicates_skipped"] += result.duplicates_skipped
                    status["state"] = "RUNNING"
                    status["last_completed_date"] = trade_date.isoformat()
                    status["completed_count"] = len(set(requested_dates) & complete)
                    status["rows_loaded_this_run"] = totals["rows_loaded"]
                    status["last_error"] = None
                    write_status(args.status_file, status)
                    print(json.dumps({
                        "status": "date_complete", "date": trade_date.isoformat(),
                        "rows": len(result.rows), "filters": result.filters,
                        "requests": result.requests,
                        "duplicates_skipped": result.duplicates_skipped,
                        "attempt": attempt,
                        "elapsed_seconds": round(time.monotonic() - date_started, 1),
                    }), file=sys.stderr)
                    break

                if not date_succeeded:
                    error = str(status["last_error"] or "Unknown Stockbit error")
                    record_needs_review(connection, target, args.log_table, trade_date, args.date_retries, error)
                    needs_review.add(trade_date)
                    status["state"] = "NEEDS_REVIEW"
                    status["needs_review_count"] = len(needs_review)
                    write_status(args.status_file, status)
                    print(json.dumps({
                        "status": "needs_review", "date": trade_date.isoformat(),
                        "attempts": args.date_retries, "error": error,
                    }), file=sys.stderr)
                    continue

            if not args.no_daily_export:
                output_path = args.daily_output_dir / f"IDX_Broker_Summary_{trade_date.isoformat()}.csv"
                if not output_path.exists() or date_succeeded:
                    output, output_rows = export_date(connection, target, args.daily_output_dir, trade_date)
                    print(json.dumps({
                        "status": "daily_export_complete", "date": trade_date.isoformat(),
                        "output": str(output.resolve()), "rows": output_rows,
                    }), file=sys.stderr)

        final_state = "COMPLETED_WITH_NEEDS_REVIEW" if needs_review else "COMPLETED"
        status["state"] = final_state
        status["current_date"] = None
        status["current_attempt"] = 0
        status["needs_review_count"] = len(needs_review)
        write_status(args.status_file, status)
        print(json.dumps({
            "status": final_state.lower(), "target": target_key(target),
            "from_date": args.from_date.isoformat(), "to_date": args.to_date.isoformat(),
            "date_order": args.date_order,
            "dates_loaded_this_run": totals["dates_loaded"],
            "rows_loaded_this_run": totals["rows_loaded"],
            "requests_this_run": totals["requests"],
            "duplicates_skipped_this_run": totals["duplicates_skipped"],
            "daily_output_directory": None if args.no_daily_export else str(args.daily_output_dir.resolve()),
            "elapsed_seconds": round(time.monotonic() - run_started, 1),
            "needs_review_dates": [value.isoformat() for value in sorted(needs_review)],
        }))
        return 2 if needs_review else 0
    except StockbitAuthenticationLimitError as exc:
        status["state"] = "STOPPED_INVALID_TOKEN"
        status["last_error"] = str(exc)
        write_status(args.status_file, status)
        print(f"STOPPED_INVALID_TOKEN: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        status["state"] = "FAILED"
        status["last_error"] = str(exc)
        write_status(args.status_file, status)
        raise
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
