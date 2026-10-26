#!/usr/bin/env python3
"""Fetch Stockbit market-wide broker activity with resumable 6-worker checkpoints.

The script writes two CSV datasets matching the user's Excel templates:
1) IDX_Net_Foreign_Summary: Date/Ticker/Investor Type totals.
2) IDX_Broker_Summary_Freq: Date/Symbol/Broker/Investor Type/Market Board frequencies.

Credentials are read only from STOCKBIT_TOKEN or a hidden interactive prompt.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import http.client
import json
import os
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo


HOST = "exodus.stockbit.com"
BOARDS = {"REGULER": "Regular", "NEGO": "Nego", "TUNAI": "Tunai"}
INVESTORS = {"FOREIGN": "Foreign", "DOMESTIC": "Domestic"}
EQUITY_SYMBOL = re.compile(r"^[A-Z]{4}$")


class StockbitError(RuntimeError):
    pass


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


def decimal_value(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise StockbitError(f"Missing numeric field: {label}")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise StockbitError(f"Invalid numeric field {label}: {value!r}") from exc
    if not number.is_finite():
        raise StockbitError(f"Invalid finite numeric field {label}: {value!r}")
    return number


def plain_decimal(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(int(value))
    return format(value.normalize(), "f")


class StockbitFetcher:
    def __init__(self, token: str, timeout: float, delay: float, page_limit: int) -> None:
        token = token.strip().replace("\\_", "_")
        if token.casefold().startswith("bearer "):
            token = token[7:].strip()
        if token.count(".") != 2:
            raise StockbitError("STOCKBIT_TOKEN is not a valid JWT shape")
        self.token = token
        self.timeout = timeout
        self.delay = delay
        self.page_limit = page_limit
        self.local = threading.local()

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
            "User-Agent": "stockbit-ihsg-daily/1.0",
        }
        for attempt in range(1, 5):
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
                if attempt == 4:
                    raise StockbitError(f"Network failure after {attempt} attempts: {exc}") from exc
                time.sleep(2 ** (attempt - 1))
                continue
            finally:
                self.local.last_finished = time.monotonic()

            elapsed_ms = round((time.monotonic() - started) * 1000)
            if response.status in (401, 403):
                raise StockbitError(f"Stockbit authentication failed with HTTP {response.status}")
            if response.status == 429 or 500 <= response.status < 600:
                self._reset_connection()
                if attempt == 4:
                    raise StockbitError(f"Stockbit returned HTTP {response.status} after retries")
                retry_after = response.getheader("Retry-After")
                time.sleep(float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt)
                continue
            if response.status != 200:
                preview = raw[:200].decode("utf-8", errors="replace")
                raise StockbitError(f"Stockbit returned HTTP {response.status}: {preview}")
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
        brokers = []
        for row in rows:
            if not isinstance(row, dict):
                raise StockbitError("Broker directory contains a non-object row")
            code = row.get("code")
            if not isinstance(code, str) or len(code) != 2 or not code.isalnum():
                raise StockbitError(f"Invalid broker code in directory: {code!r}")
            brokers.append({"code": code.upper(), "name": str(row.get("name") or ""), "group": str(row.get("group") or "")})
        if len(brokers) != len({row["code"] for row in brokers}):
            raise StockbitError("Broker directory contains duplicate codes")
        return brokers

    def activity(self, task: FilterTask) -> FilterResult:
        by_symbol: dict[str, dict[str, Any]] = {}
        page = 1
        total_requests = total_buy = total_sell = total_bytes = total_elapsed = 0
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
            if not isinstance(data, dict) or data.get("from") != task.trade_date or data.get("to") != task.trade_date:
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
                        "buy_value": Decimal(0), "sell_value": Decimal(0),
                        "buy_freq": Decimal(0), "sell_freq": Decimal(0),
                        "is_anomaly": False, "remarks": set(),
                    })
                    seen_key = f"{side}_seen"
                    value = decimal_value(item.get("value"), f"{task}.{symbol}.value")
                    frequency = decimal_value(item.get("freq"), f"{task}.{symbol}.freq")
                    if value < 0:
                        record["is_anomaly"] = True
                        record["remarks"].add(
                            f"NEGATIVE_{side.upper()}_VALUE_FROM_API: raw_value={plain_decimal(value)}"
                        )
                    if frequency < 0:
                        record["is_anomaly"] = True
                        record["remarks"].add(
                            f"NEGATIVE_{side.upper()}_FREQ_FROM_API: raw_value={plain_decimal(frequency)}"
                        )
                    if record[seen_key]:
                        if record[f"{side}_value"] != value or record[f"{side}_freq"] != frequency:
                            raise StockbitError(f"Conflicting duplicate {side} row for {task}: {symbol}")
                        continue
                    record[seen_key] = True
                    record[f"{side}_value"] = value
                    record[f"{side}_freq"] = frequency

            if len(buys) < self.page_limit and len(sells) < self.page_limit:
                break
            page += 1
            if page > 100:
                raise StockbitError(f"Pagination exceeded 100 pages for {task}")

        rows = [
            (
                task.trade_date, symbol, task.broker, INVESTORS[task.investor], BOARDS[task.board],
                plain_decimal(item["buy_value"]), plain_decimal(item["sell_value"]),
                plain_decimal(item["buy_freq"]), plain_decimal(item["sell_freq"]),
                1 if item["is_anomaly"] else 0,
                " | ".join(sorted(item["remarks"])) or None,
            )
            for symbol, item in by_symbol.items()
        ]
        return FilterResult(task, rows, page, total_requests, total_buy, total_sell, total_bytes, total_elapsed, hashes.hexdigest())


def open_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS brokers (
            code TEXT PRIMARY KEY, name TEXT NOT NULL, broker_group TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS activity (
            trade_date TEXT NOT NULL, symbol TEXT NOT NULL, broker TEXT NOT NULL,
            investor TEXT NOT NULL, board TEXT NOT NULL,
            buy_value TEXT NOT NULL, sell_value TEXT NOT NULL,
            buy_freq TEXT NOT NULL, sell_freq TEXT NOT NULL,
            is_anomaly INTEGER NOT NULL DEFAULT 0, remark TEXT,
            PRIMARY KEY (trade_date, symbol, broker, investor, board)
        );
        CREATE TABLE IF NOT EXISTS completed_filters (
            trade_date TEXT NOT NULL, broker TEXT NOT NULL, investor TEXT NOT NULL, board TEXT NOT NULL,
            pages INTEGER NOT NULL, requests INTEGER NOT NULL, buy_rows INTEGER NOT NULL,
            sell_rows INTEGER NOT NULL, response_bytes INTEGER NOT NULL, elapsed_ms INTEGER NOT NULL,
            response_sha256 TEXT NOT NULL, completed_at TEXT NOT NULL,
            PRIMARY KEY (trade_date, broker, investor, board)
        );
    """)
    activity_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(activity)")
    }
    if "is_anomaly" not in activity_columns:
        connection.execute(
            "ALTER TABLE activity ADD COLUMN is_anomaly INTEGER NOT NULL DEFAULT 0"
        )
    if "remark" not in activity_columns:
        connection.execute("ALTER TABLE activity ADD COLUMN remark TEXT")
    return connection


def save_result(connection: sqlite3.Connection, result: FilterResult) -> None:
    with connection:
        connection.executemany("""
            INSERT INTO activity (
                trade_date, symbol, broker, investor, board, buy_value, sell_value,
                buy_freq, sell_freq, is_anomaly, remark
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (trade_date, symbol, broker, investor, board) DO UPDATE SET
                buy_value=excluded.buy_value, sell_value=excluded.sell_value,
                buy_freq=excluded.buy_freq, sell_freq=excluded.sell_freq,
                is_anomaly=excluded.is_anomaly, remark=excluded.remark
        """, result.rows)
        task = result.task
        connection.execute("""
            INSERT OR REPLACE INTO completed_filters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task.trade_date, task.broker, task.investor, task.board,
            result.pages, result.requests, result.buy_rows, result.sell_rows,
            result.response_bytes, result.elapsed_ms, result.response_sha256,
            datetime.now(ZoneInfo("UTC")).isoformat(),
        ))


def write_outputs(connection: sqlite3.Connection, output_dir: Path, dates: list[str], equity_only: bool) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    date_marks = ",".join("?" for _ in dates)
    condition = "AND a.symbol GLOB '[A-Z][A-Z][A-Z][A-Z]' AND length(a.symbol)=4" if equity_only else ""

    detail_path = output_dir / "IDX_Broker_Summary_Freq.csv"
    detail_rows = symbols = 0
    symbol_set: set[str] = set()
    with detail_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("Date", "Symbol", "Broker", "Broker Name", "Investor Type", "Market Board", "Buy Freq", "Sell Freq"))
        query = f"""
            SELECT a.trade_date, a.symbol, a.broker, b.name, a.investor, a.board, a.buy_freq, a.sell_freq
            FROM activity a JOIN brokers b ON b.code=a.broker
            WHERE a.trade_date IN ({date_marks}) {condition}
            ORDER BY a.trade_date, a.symbol, a.broker, a.investor, a.board
        """
        for row in connection.execute(query, dates):
            writer.writerow(row)
            detail_rows += 1
            symbol_set.add(row[1])
    symbols = len(symbol_set)

    summary_path = output_dir / "IDX_Net_Foreign_Summary.csv"
    aggregates: dict[tuple[str, str, str], list[Decimal]] = {}
    query = f"""
        SELECT a.trade_date, a.symbol, a.investor, a.buy_value, a.sell_value, a.buy_freq, a.sell_freq
        FROM activity a
        WHERE a.trade_date IN ({date_marks}) {condition}
    """
    for trade_date, symbol, investor, buy_value, sell_value, buy_freq, sell_freq in connection.execute(query, dates):
        values = aggregates.setdefault((trade_date, symbol, investor), [Decimal(0), Decimal(0), Decimal(0), Decimal(0)])
        values[0] += Decimal(buy_value)
        values[1] += Decimal(sell_value)
        values[2] += Decimal(buy_freq)
        values[3] += Decimal(sell_freq)
    with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("Date", "Ticker", "Investor Type", "Buy Value", "Sell Value", "Net Value", "Buy Freq", "Sell Freq"))
        for key in sorted(aggregates):
            buy_value, sell_value, buy_freq, sell_freq = aggregates[key]
            writer.writerow((*key, plain_decimal(buy_value), plain_decimal(sell_value), plain_decimal(buy_value - sell_value), plain_decimal(buy_freq), plain_decimal(sell_freq)))

    reconciliation = 0
    by_market: dict[tuple[str, str], list[Decimal]] = {}
    for (trade_date, symbol, _investor), values in aggregates.items():
        totals = by_market.setdefault((trade_date, symbol), [Decimal(0), Decimal(0), Decimal(0), Decimal(0)])
        for index, value in enumerate(values):
            totals[index] += value
    for buy_value, sell_value, buy_freq, sell_freq in by_market.values():
        if buy_value != sell_value or buy_freq != sell_freq:
            reconciliation += 1

    return {
        "detail_csv": str(detail_path.resolve()),
        "summary_csv": str(summary_path.resolve()),
        "detail_rows": detail_rows,
        "summary_rows": len(aggregates),
        "symbols": symbols,
        "market_reconciliation_mismatches": reconciliation,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch IHSG-wide Stockbit broker data with resumable checkpoints")
    parser.add_argument("--dates", nargs="+", type=date.fromisoformat, required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--delay", type=float, default=0.1)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--page-limit", type=int, default=1000)
    parser.add_argument("--expected-brokers", type=int, default=112)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--all-symbols", action="store_true", help="Include warrants/rights/other non-4-letter symbols")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.workers <= 16:
        raise StockbitError("--workers must be between 1 and 16")
    if args.delay < 0:
        raise StockbitError("--delay cannot be negative")
    if not 1 <= args.page_limit <= 1000:
        raise StockbitError("--page-limit must be between 1 and 1000")
    dates = sorted({value.isoformat() for value in args.dates})
    if len(dates) != len(args.dates):
        raise StockbitError("--dates contains duplicates")
    token = os.environ.get("STOCKBIT_TOKEN", "").strip()
    if not token and sys.stdin.isatty():
        token = getpass.getpass("Stockbit JWT: ").strip()
    if not token:
        raise StockbitError("Set STOCKBIT_TOKEN or run interactively")

    fetcher = StockbitFetcher(token, args.timeout, args.delay, args.page_limit)
    brokers = fetcher.broker_directory()
    if args.expected_brokers and len(brokers) != args.expected_brokers:
        raise StockbitError(f"Expected {args.expected_brokers} brokers, received {len(brokers)}")

    connection = open_database(args.database)
    try:
        with connection:
            connection.executemany(
                "INSERT OR REPLACE INTO brokers (code, name, broker_group) VALUES (?, ?, ?)",
                [(row["code"], row["name"], row["group"]) for row in brokers],
            )
        completed = {tuple(row) for row in connection.execute("SELECT trade_date, broker, investor, board FROM completed_filters")}
        tasks = [
            FilterTask(trade_date, broker["code"], investor, board)
            for trade_date in dates for broker in brokers for investor in INVESTORS for board in BOARDS
            if (trade_date, broker["code"], investor, board) not in completed
        ]
        expected = len(dates) * len(brokers) * len(INVESTORS) * len(BOARDS)
        print(json.dumps({
            "brokers": len(brokers), "dates": dates, "workers": args.workers,
            "expected_filters": expected, "already_complete": expected - len(tasks), "remaining": len(tasks),
        }), file=sys.stderr, flush=True)

        completed_now = 0
        request_count = 1
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(fetcher.activity, task): task for task in tasks}
            try:
                for future in as_completed(futures):
                    result = future.result()
                    save_result(connection, result)
                    completed_now += 1
                    request_count += result.requests
                    if completed_now % 100 == 0 or completed_now == len(tasks):
                        print(json.dumps({
                            "filters_done": completed_now,
                            "filters_remaining": len(tasks) - completed_now,
                            "requests_this_run": request_count,
                            "rows_staged": connection.execute("SELECT COUNT(*) FROM activity").fetchone()[0],
                            "elapsed_seconds": round(time.monotonic() - started, 1),
                        }), file=sys.stderr, flush=True)
            except BaseException:
                for future in futures:
                    future.cancel()
                raise

        complete = connection.execute(
            f"SELECT COUNT(*) FROM completed_filters WHERE trade_date IN ({','.join('?' for _ in dates)})",
            dates,
        ).fetchone()[0]
        if complete != expected:
            raise StockbitError(f"Completeness check failed: {complete} of {expected} requested filters completed")
        outputs = write_outputs(connection, args.output_dir, dates, not args.all_symbols)
        summary = {
            **outputs,
            "database": str(args.database.resolve()),
            "dates": dates,
            "workers": args.workers,
            "brokers": len(brokers),
            "filters": complete,
            "requests_this_run": request_count,
            "elapsed_seconds": round(time.monotonic() - started, 1),
        }
        (args.output_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary))
    finally:
        connection.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StockbitError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
