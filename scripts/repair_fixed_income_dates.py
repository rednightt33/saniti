#!/usr/bin/env python3
"""Prepare, review and atomically apply an explicit fixed-income date repair.

`prepare` is READ ONLY and fetches replacement candles before any cleansing. It
also reconstructs the old recursive state once, then calculates affected outputs
in five-session chunks. `apply` accepts only a SHA256-pinned, unexpired plan;
all source/feature/queue/state guards are checked before deletion. Production
cron/worker limits and formula versions are not changed by this operator script.
"""
from __future__ import annotations

import argparse
from collections import deque
from dataclasses import fields
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from math import isclose
import os
from pathlib import Path
import sys
import uuid

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "features/feature04"))
sys.path.insert(0, str(ROOT / "apps/fixed-income-price-cron"))
import fixed_income_update as loader  # noqa: E402
from engine import COLUMNS, FEATURE_COLUMNS, TABLE, VERSION, calculate  # noqa: E402
from incremental import STATE_VERSION, calculate_incremental, validate_incremental_availability  # noqa: E402
from pipeline import upsert  # noqa: E402

SCHEMA = "fixed-income-selected-date-repair-v1"
POLICY = ROOT / "verification/fixed_income_session_repair/SESSION_POLICY.json"
MAX_DATES = 20
MAX_PLAN_AGE = timedelta(hours=24)


def encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False).encode()


def digest(value) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def records(connection, statement, params=()) -> list[dict]:
    with connection.cursor(row_factory=dict_row) as cursor:
        return list(cursor.execute(statement, params).fetchall())


def normalized_dates(values) -> list[date]:
    dates = sorted(set(date.fromisoformat(str(value)) for value in values))
    if not dates or len(dates) > MAX_DATES:
        raise ValueError(f"Specify 1–{MAX_DATES} distinct dates")
    return dates


def schedules(connection, markets: list[str], policy: dict) -> dict:
    rows = records(connection, 'SELECT * FROM public."Fixed_Income_Market_Schedule" '
                   'WHERE market_code=ANY(%s) AND enabled ORDER BY market_code', (markets,))
    if {row["market_code"] for row in rows} != set(markets):
        raise ValueError("Every requested market must have one enabled database schedule")
    names = {field.name for field in fields(loader.MarketSchedule)}
    result = {}
    for row in rows:
        requested = policy[row["market_code"]]
        base = {name: value for name, value in row.items() if name in names}
        base.update(requested)
        result[row["market_code"]] = loader.MarketSchedule(**base)
    return result


def source_history(connection, ticker: str) -> list[dict]:
    return records(connection, '''SELECT ticker,date,open,high,low,close,volume,
        'Daily'::text AS timeframe,tradingview_symbol,source,query_date,ingestion_time,
        'bonds'::text AS asset_type FROM public."Price_Fixed_Income"
        WHERE ticker=%s AND metric_type='price' AND "Timeframe"='1D' AND is_final
        ORDER BY date''', (ticker,))


def selected_prices(connection, countries, dates):
    return records(connection, '''SELECT * FROM public."Price_Fixed_Income"
        WHERE "Country"=ANY(%s) AND date=ANY(%s) AND "Timeframe"='1D'
        ORDER BY tradingview_symbol,date,metric_type''', (countries, dates))


def feature_suffix(connection, tickers, start):
    return records(connection, sql.SQL('''SELECT * FROM public.{} WHERE asset_type='bonds'
        AND ticker=ANY(%s) AND timeframe='Daily' AND trade_date>=%s
        ORDER BY ticker,trade_date''').format(sql.Identifier(TABLE)), (tickers, start))


def operational_snapshot(connection, tickers):
    result = {}
    for table, order in (("Feature04_Calculation_Queue", "ticker"),
                         ("Feature04_Calculation_State", "ticker,checkpoint_date"),
                         ("Feature04_Column_Status", "ticker,feature_column")):
        result[table] = records(connection, sql.SQL('''SELECT * FROM public.{}
            WHERE asset_type='bonds' AND ticker=ANY(%s) AND timeframe='Daily' ORDER BY {}''')
            .format(sql.Identifier(table), sql.SQL(order)), (tickers,))
    queues = result["Feature04_Calculation_Queue"]
    if len(queues) != len(tickers) or any(row["status"] != "DONE" or row["claim_token"] for row in queues):
        raise ValueError("Repair requires every selected ticker queue to be idle and DONE")
    return result


def fetch_replacements(universe, schedules_by_market, dates, now, request_bars):
    result = []
    for market, schedule in schedules_by_market.items():
        if max(dates) > loader.latest_completed_session(schedule, now):
            raise ValueError(f"Requested {market} date has not reached its final close")
        ws = loader.open_socket(45, False)
        try:
            session = loader.start_chart_session(ws)
            for item in (item for item in universe if item.country == schedule.country):
                candles, _ = loader.request_series(
                    ws, session, item, request_bars, 45, now.astimezone(schedule.timezone).date(),
                    max(dates), loader.market_close_at(schedule, max(dates)), now,
                    schedule.source_date_mapping, schedule.provider_timezone_name, schedule.provider_session)
                by_date = {}
                for candle in candles:
                    day = candle["date"]
                    if day in dates:
                        if day in by_date:
                            raise ValueError(f"Multiple provider anchors resolve to {item.ticker}/{day}")
                        candle["market_close_at"] = loader.market_close_at(schedule, day)
                        if now < candle["market_close_at"] + timedelta(minutes=schedule.finality_delay_minutes):
                            raise ValueError("A replacement candle is not final")
                        by_date[day] = loader.validate_price_row(candle)
                missing = sorted(set(dates) - set(by_date))
                if missing:
                    raise ValueError(f"Replacement unavailable for {item.ticker}/{item.metric_type}: {missing}")
                result.extend(by_date[day] for day in dates)
        finally:
            ws.close()
    expected = len(universe) * len(dates)
    if len(result) != expected:
        raise ValueError("Replacement candle coverage differs from the selected universe")
    return sorted(result, key=lambda row: (row["tradingview_symbol"], row["date"], row["metric_type"]))


def merge_history(history, replacements, dates):
    by_date = {row["date"]: dict(row) for row in history}
    if len(by_date) != len(history):
        raise ValueError("Duplicate source dates")
    for row in replacements:
        if row["metric_type"] != "price":
            continue
        if row["date"] not in dates:
            raise ValueError("Replacement escaped the explicit cleansing dates")
        by_date[row["date"]] = {**row, "asset_type": "bonds", "timeframe": "Daily"}
    return [by_date[day] for day in sorted(by_date)]


def equal_value(left, right):
    if left is None or right is None:
        return left is right
    if isinstance(right, (int, bool)):
        return left == right
    if isinstance(right, (float, Decimal)):
        return isclose(float(left), float(right), abs_tol=1e-10, rel_tol=1e-12)
    return left == right


def assert_feature_values(actual, expected):
    if len(actual) != len(expected):
        raise ValueError("Feature output row count differs")
    for got, want in zip(actual, expected):
        for column in ("ticker", "trade_date", "timeframe", "asset_type", *FEATURE_COLUMNS, "calculation_version"):
            if not equal_value(got[column], want[column]):
                raise ValueError(f"Feature mismatch: {want['ticker']}/{want['trade_date']}/{column}")


def calculate_repair(history, start, retention, now):
    chunk_limit = retention - 2
    if not 1 <= chunk_limit <= 20:
        raise ValueError("Invalid market correction-session policy")
    prefix = [row for row in history if row["date"] < start]
    suffix = [row for row in history if row["date"] >= start]
    if not prefix or not suffix or len(history) > 5000:
        raise ValueError("Repair needs a nonempty trusted prefix and bounded affected suffix")
    _, outcomes, state, prefix_states = calculate_incremental(
        prefix, state_only=True, checkpoint_limit=retention, calculated_at=now)
    if any(outcome["status"] != "SUCCESS" for outcome in outcomes.values()):
        raise ValueError("Prefix state bootstrap failed")
    checkpoint_date = state["last_date"]
    retained = deque(prefix_states, maxlen=retention)
    output = []
    for offset in range(0, len(suffix), chunk_limit):
        chunk = suffix[offset:offset + chunk_limit]
        rows, outcomes, state, checkpoints = calculate_incremental(chunk, checkpoint=state, calculated_at=now)
        if any(outcome["status"] != "SUCCESS" for outcome in outcomes.values()):
            raise ValueError("An affected formula group failed")
        if validate_incremental_availability(chunk, rows, checkpoints):
            raise ValueError("An affected indicator has an unexpected unavailable value")
        output.extend(rows)
        retained.extend(checkpoints)
    reference = [row for row in calculate(history, calculated_at=now) if row["trade_date"] >= start]
    assert_feature_values(output, reference)
    return {"rows": output, "states": list(retained), "source_rows": len(suffix),
            "bootstrap_rows": len(prefix), "checkpoint_date": checkpoint_date,
            "source_digest": state["source_chain_sha256"], "chunk_limit": chunk_limit}


def prepare(connection, markets, dates, policy, now, request_bars):
    schedules_by_market = schedules(connection, markets, policy)
    countries = sorted(schedule.country for schedule in schedules_by_market.values())
    universes = [item for schedule in schedules_by_market.values()
                 for item in loader.read_universe(connection, schedule)]
    # Provider data is fetched and validated before any destructive operation or long DB snapshot.
    replacements = fetch_replacements(universes, schedules_by_market, dates, now, request_bars)
    tickers = sorted({item.ticker for item in universes if item.metric_type == "price"})
    if not tickers or any({item.metric_type for item in universes if item.ticker == ticker}
                          != {"price", "yield_to_maturity"} for ticker in tickers):
        raise ValueError("Every selected ticker must resolve to a price/yield pair")
    with connection.transaction():
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        before = {"prices": selected_prices(connection, countries, dates),
                  "features": feature_suffix(connection, tickers, min(dates)),
                  "operations": operational_snapshot(connection, tickers)}
        replacement_keys = {(row["tradingview_symbol"], row["date"], row["metric_type"])
                            for row in replacements}
        if any((row["tradingview_symbol"], row["date"], row["metric_type"]) not in replacement_keys
               for row in before["prices"]):
            raise ValueError("Existing selected rows lack a validated replacement; no cleansing allowed")
        calculations, source_guards = {}, {}
        for ticker in tickers:
            history = source_history(connection, ticker)
            source_guards[ticker] = digest(history)
            updated = merge_history(history, [row for row in replacements if row["ticker"] == ticker], dates)
            schedule = next(s for s in schedules_by_market.values()
                            if any(item.ticker == ticker and item.country == s.country for item in universes))
            calculations[ticker] = calculate_repair(updated, min(dates), schedule.correction_lookback_sessions + 2, now)
    return {"schema": SCHEMA, "run_id": str(uuid.uuid4()), "created_at": now.isoformat(),
            "expires_at": (now + MAX_PLAN_AGE).isoformat(), "markets": markets, "countries": countries,
            "dates": dates, "tickers": tickers, "version": VERSION, "state_version": STATE_VERSION,
            "policy": {market: policy[market] for market in markets},
            "schedules": {market: schedule.__dict__ for market, schedule in schedules_by_market.items()},
            "universe": [item.__dict__ for item in universes], "source_guards": source_guards,
            "replacements": replacements, "calculations": calculations, "before": before}


def restore_types(plan):
    plan["dates"] = normalized_dates(plan["dates"])
    for row in plan["replacements"]:
        for name in ("date", "query_date"):
            row[name] = date.fromisoformat(row[name])
        for name in ("source_bar_time", "market_close_at", "finalized_at"):
            row[name] = datetime.fromisoformat(row[name])
        loader.validate_price_row(row)
    for calculation in plan["calculations"].values():
        for row in calculation["rows"]:
            row["trade_date"] = date.fromisoformat(row["trade_date"])
            row["calculated_at"] = datetime.fromisoformat(row["calculated_at"])
    return plan


def validate_plan(plan, now):
    if plan["schema"] != SCHEMA or plan["version"] != VERSION or plan["state_version"] != STATE_VERSION:
        raise ValueError("Repair plan/schema/formula version is incompatible")
    created, expires = (datetime.fromisoformat(plan[key]) for key in ("created_at", "expires_at"))
    if not created <= now <= expires or expires - created > MAX_PLAN_AGE:
        raise ValueError("Repair plan expired or has an invalid time window")
    dates = normalized_dates(plan["dates"])
    if plan["tickers"] != sorted(set(plan["tickers"])) or set(plan["calculations"]) != set(plan["tickers"]):
        raise ValueError("Repair ticker/calculation coverage differs")
    universe_keys = {(item["ticker"], item["metric_type"], item["tradingview_symbol"]) for item in plan["universe"]}
    expected = {(ticker, metric, symbol, day) for ticker, metric, symbol in universe_keys for day in dates}
    actual = [(row["ticker"], row["metric_type"], row["tradingview_symbol"], row["date"])
              for row in plan["replacements"]]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError("Plan replacements are duplicated, missing or outside the authorized dates")
    for ticker, computation in plan["calculations"].items():
        rows = computation["rows"]
        if not rows or any(row["ticker"] != ticker or row["asset_type"] != "bonds"
                           or row["timeframe"] != "Daily" or row["trade_date"] < min(dates) for row in rows):
            raise ValueError("Feature computation escaped the authorized bonds suffix")


def apply(connection, plan, backup_path, now):
    validate_plan(plan, now)
    if connection.execute("SHOW transaction_read_only").fetchone()[0] == "on":
        raise ValueError("Apply requires an explicitly supplied write-capable operator connection")
    tickers, dates = plan["tickers"], plan["dates"]
    marker = "selected-date-repair:" + plan["run_id"]
    if records(connection, 'SELECT id FROM public."Feature04_Calculation_Log" WHERE detail=%s LIMIT 1', (marker,)):
        raise ValueError("This plan was already applied; use its readback rather than replaying cleansing")
    backup_path = Path(backup_path)
    with backup_path.open("xb") as backup:
        backup.write(encoded({"run_id": plan["run_id"], "before": plan["before"], "policy": plan["policy"]}))
        backup.flush()
        os.fsync(backup.fileno())
    with connection.transaction():
        connection.execute("SET LOCAL lock_timeout='5s'")
        connection.execute("SET LOCAL statement_timeout='120s'")
        for market in sorted(plan["markets"]):
            if not connection.execute('SELECT pg_try_advisory_xact_lock(hashtext(%s))',
                                      (f"{loader.RUN_LOCK_NAMESPACE}.{market}",)).fetchone()[0]:
                raise ValueError(f"A {market} price writer is active; no cleansing performed")
        connection.execute('LOCK TABLE public."Price_Fixed_Income" IN SHARE ROW EXCLUSIVE MODE')
        connection.execute('SELECT ticker FROM public."Feature04_Calculation_Queue" '
                           "WHERE asset_type='bonds' AND ticker=ANY(%s) ORDER BY ticker FOR UPDATE", (tickers,))
        for market, expected_policy in plan["policy"].items():
            current = records(connection, 'SELECT * FROM public."Fixed_Income_Market_Schedule" '
                              'WHERE market_code=%s', (market,))[0]
            if any(current.get(key) != value for key, value in expected_policy.items()):
                raise ValueError("Apply and verify the tracked provider-session migration before cleansing")
            current_schedule = {key: current.get(key) for key in plan["schedules"][market]}
            if digest(current_schedule) != digest(plan["schedules"][market]):
                raise ValueError("Market close/finality/correction policy changed since preparation")
        universe = [item.__dict__ for schedule in schedules(connection, plan["markets"], plan["policy"]).values()
                    for item in loader.read_universe(connection, schedule)]
        if digest(universe) != digest(plan["universe"]):
            raise ValueError("Universe changed since preparation")
        guards = {"prices": selected_prices(connection, plan["countries"], dates),
                  "features": feature_suffix(connection, tickers, min(dates)),
                  "operations": operational_snapshot(connection, tickers)}
        if digest(guards) != digest(plan["before"]):
            raise ValueError("Source, output, queue or checkpoints changed since preparation")
        if any(digest(source_history(connection, ticker)) != plan["source_guards"][ticker] for ticker in tickers):
            raise ValueError("Price history changed since preparation")
        removed_prices = connection.execute('''DELETE FROM public."Price_Fixed_Income"
            WHERE "Country"=ANY(%s) AND date=ANY(%s) AND "Timeframe"='1D' ''',
            (plan["countries"], dates)).rowcount
        removed_features = connection.execute(sql.SQL('''DELETE FROM public.{}
            WHERE asset_type='bonds' AND ticker=ANY(%s) AND trade_date=ANY(%s) AND timeframe='Daily' ''')
            .format(sql.Identifier(TABLE)), (tickers, dates)).rowcount
        verified, _ = loader.bulk_upsert_prices(connection, plan["replacements"])
        if verified != len(plan["replacements"]):
            raise ValueError("Replacement source readback failed")
        output_changes = 0
        for ticker in tickers:
            computation = plan["calculations"][ticker]
            changed_for_ticker = upsert(connection, computation["rows"])
            output_changes += changed_for_ticker
            queue = records(connection, '''SELECT * FROM public."Feature04_Calculation_Queue"
                WHERE asset_type='bonds' AND ticker=%s AND timeframe='Daily' FOR UPDATE''', (ticker,))[0]
            attempt = connection.execute('''INSERT INTO public."Feature04_Calculation_Log"(
                asset_type,ticker,timeframe,source_generation,work_revision,requested_columns,
                successful_columns,failed_columns,group_outcomes,result,source_start,source_end,
                source_rows,source_sha256,changed_rows,calculation_version,started_at,detail,checkpoint_date,dirty_from_date)
                VALUES('bonds',%s,'Daily',%s,%s,%s,%s,'{}',%s,'SUCCESS',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',
                (ticker, queue["requested_generation"], queue["work_revision"], list(FEATURE_COLUMNS), list(FEATURE_COLUMNS),
                 Jsonb({"repair": {"dates": [str(day) for day in dates], "bootstrap_rows": computation["bootstrap_rows"],
                                    "chunk_limit": computation["chunk_limit"], "full_reference_matched": True}}),
                 computation["rows"][0]["trade_date"], computation["rows"][-1]["trade_date"],
                 computation["source_rows"], computation["source_digest"], changed_for_ticker, VERSION,
                 now, marker, date.fromisoformat(computation["checkpoint_date"]), min(dates))).fetchone()[0]
            for state in computation["states"]:
                connection.execute('''INSERT INTO public."Feature04_Calculation_State"(
                    asset_type,ticker,timeframe,checkpoint_date,state_version,calculation_version,
                    source_position,source_chain_sha256,state_payload)
                    VALUES('bonds',%s,'Daily',%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(asset_type,ticker,timeframe,checkpoint_date) DO UPDATE SET
                    state_version=EXCLUDED.state_version,calculation_version=EXCLUDED.calculation_version,
                    source_position=EXCLUDED.source_position,source_chain_sha256=EXCLUDED.source_chain_sha256,
                    state_payload=EXCLUDED.state_payload,updated_at=CURRENT_TIMESTAMP''',
                    (ticker, date.fromisoformat(state["last_date"]), STATE_VERSION, VERSION,
                     state["position"], state["source_chain_sha256"], Jsonb(state)))
            keep = [date.fromisoformat(state["last_date"]) for state in computation["states"]]
            connection.execute('''DELETE FROM public."Feature04_Calculation_State"
                WHERE asset_type='bonds' AND ticker=%s AND timeframe='Daily' AND NOT(checkpoint_date=ANY(%s))''',
                (ticker, keep))
            connection.execute('''UPDATE public."Feature04_Calculation_Queue" SET status='DONE',
                completed_generation=requested_generation,requested_columns=NULL,claimed_at=NULL,claim_token=NULL,
                claim_expires_at=NULL,completed_at=CURRENT_TIMESTAMP,source_attempt_count=0,
                last_error_code=NULL,last_error=NULL,updated_at=CURRENT_TIMESTAMP
                WHERE asset_type='bonds' AND ticker=%s AND timeframe='Daily' ''', (ticker,))
            latest = computation["rows"][-1]
            connection.execute('''UPDATE public."Feature04_Column_Status" SET status='SUCCESS',
                requested_generation=%s,completed_generation=%s,calculation_version=%s,dirty_from_date=NULL,
                validated_through=%s,last_attempt_id=%s,last_error_code=NULL,last_error=NULL,
                last_calculated_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                WHERE asset_type='bonds' AND ticker=%s AND timeframe='Daily' ''',
                (queue["requested_generation"], queue["requested_generation"], VERSION, latest["trade_date"], attempt, ticker))
            for column in FEATURE_COLUMNS:
                available = latest[column] is not None
                connection.execute('''UPDATE public."Feature04_Column_Status" SET latest_value_available=%s,
                    null_reason=CASE WHEN %s THEN NULL ELSE 'EXPECTED_FORMULA_NULL' END
                    WHERE asset_type='bonds' AND ticker=%s AND timeframe='Daily' AND feature_column=%s''',
                    (available, available, ticker, column))
            assert_feature_values(feature_suffix(connection, [ticker], min(dates)), computation["rows"])
        actual = selected_prices(connection, plan["countries"], dates)
        by_key = {(row["tradingview_symbol"], row["date"], row["metric_type"]): row for row in actual}
        if len(by_key) != len(plan["replacements"]):
            raise ValueError("Source replacement key count differs")
        for expected in plan["replacements"]:
            got = by_key[(expected["tradingview_symbol"], expected["date"], expected["metric_type"])]
            if any(got[column] != expected[column] for column in loader.PRICE_COLUMNS):
                raise ValueError("Stored source candle differs from the validated replacement")
    return {"status": "APPLIED", "run_id": plan["run_id"], "removed_price_rows": removed_prices,
            "removed_feature_rows": removed_features, "inserted_price_rows": verified,
            "feature_rows_inserted_or_updated": output_changes, "tickers": len(tickers),
            "backup_sha256": hashlib.sha256(backup_path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("prepare")
    stage.add_argument("--markets", nargs="+", required=True)
    stage.add_argument("--dates", nargs="+", type=date.fromisoformat, required=True)
    stage.add_argument("--policy", type=Path, default=POLICY)
    stage.add_argument("--request-bars", type=int, default=60)
    stage.add_argument("--plan", type=Path, required=True)
    run = commands.add_parser("apply")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--expected-sha256", required=True)
    run.add_argument("--backup", type=Path, required=True)
    run.add_argument("--confirm-apply", action="store_true", required=True)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
        if args.command == "prepare":
            policy = json.loads(args.policy.read_text())
            if len(set(args.markets)) != len(args.markets) or any(market not in policy for market in args.markets):
                raise ValueError("Specify distinct markets present in the reviewed session policy")
            plan = prepare(connection, sorted(args.markets), normalized_dates(args.dates), policy, now, args.request_bars)
            validate_plan(plan, now)
            with args.plan.open("xb") as target:
                target.write(encoded(plan))
            print(json.dumps({"status": "PREPARED_READ_ONLY", "run_id": plan["run_id"],
                "plan_sha256": hashlib.sha256(args.plan.read_bytes()).hexdigest(),
                "price_rows": len(plan["replacements"]), "tickers": len(plan["tickers"]),
                "existing_price_rows": len(plan["before"]["prices"]),
                "existing_feature_suffix_rows": len(plan["before"]["features"])}))
        else:
            content = args.plan.read_bytes()
            if hashlib.sha256(content).hexdigest() != args.expected_sha256:
                raise ValueError("Reviewed plan SHA256 differs; no cleansing performed")
            print(json.dumps(apply(connection, restore_types(json.loads(content)), args.backup, now)))


if __name__ == "__main__":
    main()
