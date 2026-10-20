"""Explicit repair scope, recursive continuity, stale-plan and transaction rollback checks."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import psycopg
from psycopg import sql
import pytest

from test_engine import bars

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("selected_date_repair", ROOT / "scripts/repair_fixed_income_dates.py")
repair = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = repair
spec.loader.exec_module(repair)
NOW = datetime(2026, 10, 20, 9, tzinfo=timezone.utc)
DATES = [date(2026, 9, 30), date(2026, 10, 13), date(2026, 10, 19)]
ADMIN = os.environ.get("FEATURE04_REPAIR_TEST_POSTGRES_URL")


def history(ticker="ID10Y"):
    days, cursor = [], date(2026, 10, 19)
    while len(days) < 270:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return [{**row, "date": day, "ticker": ticker, "asset_type": "bonds",
             "source": "TradingView", "query_date": day, "volume": None,
             "tradingview_symbol": "TVC:" + ticker.removesuffix("Y")}
            for row, day in zip(bars(270), reversed(days))]


def test_repair_rebuilds_state_before_oldest_date_and_updates_dependent_dates():
    old = history()
    replacement = {**next(row for row in old if row["date"] == DATES[0]), "metric_type": "price"}
    for column in ("open", "high", "low", "close"):
        replacement[column] += 5
    merged = repair.merge_history(old, [replacement], DATES)
    calculated = repair.calculate_repair(merged, DATES[0], 7, NOW)
    assert calculated["bootstrap_rows"] > 200 and calculated["source_rows"] > 5
    assert calculated["checkpoint_date"] == "2026-09-29"
    assert calculated["chunk_limit"] == 5 and len(calculated["states"]) == 7
    assert min(row["trade_date"] for row in calculated["rows"]) == DATES[0]
    original = {row["trade_date"]: row for row in repair.calculate(old, calculated_at=NOW)}
    after = next(row for row in calculated["rows"] if row["trade_date"] == date(2026, 10, 1))
    assert after["ema_200"] != original[date(2026, 10, 1)]["ema_200"]


def test_merge_refuses_an_unrequested_source_date():
    source = history()
    with pytest.raises(ValueError, match="explicit cleansing dates"):
        repair.merge_history(source, [{**source[0], "metric_type": "price"}], DATES)


def test_policy_and_migration_hold_identical_verified_metadata():
    policy = json.loads(repair.POLICY.read_text())
    migration = (ROOT / "database/migrations/20261013_011_verify_fixed_income_sessions.sql").read_text()
    assert set(policy) == {"ID", "US"}
    for settings in policy.values():
        assert settings["source_date_mapping"] == "NEXT_BUSINESS_DAY"
        assert all(value in migration for value in settings.values())


TABLES = ["Universe_Fixed_income", "Fixed_Income_Market_Schedule", "Price_Fixed_Income",
          "Feature_04_Technical_Indicator", "Feature04_Calculation_Log", "Feature04_Calculation_Queue",
          "Feature04_Calculation_State", "Feature04_Column_Status"]
KEYS = {
    "Fixed_Income_Market_Schedule": ["market_code"],
    "Price_Fixed_Income": ["tradingview_symbol", "date", "metric_type", "Timeframe"],
    "Feature_04_Technical_Indicator": ["ticker", "trade_date", "timeframe", "asset_type"],
    "Feature04_Calculation_Log": ["id"],
    "Feature04_Calculation_Queue": ["asset_type", "ticker", "timeframe"],
    "Feature04_Calculation_State": ["asset_type", "ticker", "timeframe", "checkpoint_date"],
    "Feature04_Column_Status": ["asset_type", "ticker", "timeframe", "feature_column"],
}


def fixture_schema(connection):
    markdown = (ROOT / "DATABASE_SCHEMA.md").read_text()
    for table in TABLES:
        section = markdown.split("\n## " + table + "\n", 1)[1].split("\n## ", 1)[0]
        columns = []
        for line in section.split("### Constraints", 1)[0].splitlines():
            match = re.match(r"\| `([^`]+)` \| `([^`]+)` \| (Yes|No) \| (.*?) \|", line)
            if not match:
                continue
            name, kind, nullable, default = match.groups()
            if kind == "ARRAY":
                kind = "text[]"
            if name == "id" and table == "Feature04_Calculation_Log":
                definition = sql.SQL("{} bigint GENERATED ALWAYS AS IDENTITY").format(sql.Identifier(name))
            else:
                definition = sql.SQL("{} {}").format(sql.Identifier(name), sql.SQL(kind))
                if default.startswith("`") and default.endswith("`"):
                    definition += sql.SQL(" DEFAULT " + default[1:-1])
            if nullable == "No":
                definition += sql.SQL(" NOT NULL")
            columns.append(definition)
        if table in KEYS:
            columns.append(sql.SQL("PRIMARY KEY ({})").format(sql.SQL(",").join(map(sql.Identifier, KEYS[table]))))
        connection.execute(sql.SQL("CREATE TABLE public.{} ({})").format(
            sql.Identifier(table), sql.SQL(",").join(columns)))
    connection.execute('ALTER TABLE public."Fixed_Income_Market_Schedule" '
                       'ADD provider_timezone_name text, ADD provider_session text')
    connection.execute('''ALTER TABLE public."Feature04_Calculation_Queue" ADD CHECK
        ((status='PROCESSING')=(claimed_at IS NOT NULL AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL))''')
    connection.execute('''CREATE FUNCTION public.feature04_asset_type(text) RETURNS text LANGUAGE sql
        STABLE AS $$ SELECT 'bonds'::text $$''')
    for path, name in (("20261012_003_incremental_feature04_finality.sql", "enqueue_feature04_group"),
                       ("20261012_001_finalize_fixed_income_markets.sql", "enqueue_feature04_bond_price_row")):
        source = (ROOT / "database/migrations" / path).read_text()
        function = "CREATE OR REPLACE FUNCTION public." + name + "(" + source.split(
            "CREATE OR REPLACE FUNCTION public." + name + "(", 1)[1].split("$function$;", 1)[0] + "$function$;"
        connection.execute(function)
    connection.execute('''CREATE TRIGGER source_enqueue AFTER INSERT OR UPDATE OR DELETE
        ON public."Price_Fixed_Income" FOR EACH ROW EXECUTE FUNCTION public.enqueue_feature04_bond_price_row()''')


def seed(connection):
    policy = json.loads(repair.POLICY.read_text())
    sources = []
    for market, ticker, country, zone, clock in (("ID", "ID10Y", "Indonesia", "Asia/Jakarta", "16:00"),
                                                ("US", "US10Y", "United States", "America/New_York", "17:00")):
        connection.execute('''INSERT INTO public."Fixed_Income_Market_Schedule"(
            market_code,country,timezone_name,session_close_local,finality_delay_minutes,
            source_date_mapping,correction_lookback_sessions,provider_timezone_name,provider_session)
            VALUES(%s,%s,%s,%s,60,'NEXT_BUSINESS_DAY',5,%s,%s)''',
            (market, country, zone, clock, policy[market]["provider_timezone_name"], policy[market]["provider_session"]))
        for metric in ("price", "yield_to_maturity"):
            symbol = "TVC:" + ticker + ("P" if metric == "price" else "")
            connection.execute('''INSERT INTO public."Universe_Fixed_income"(
                region,country,instrument_name,ticker,tradingview_symbol,metric_type,value_unit,
                exchange,security_type,type_specs,is_common_stock,tradingview_country,tenor)
                VALUES('fixture',%s,%s,%s,%s,%s,'PCTPAR','TVC','bond','government',false,%s,'10Y')''',
                (country, ticker, ticker, symbol, metric, country))
            for row in history(ticker):
                sources.append({**row, "Country": country, "instrument_name": ticker,
                    "tradingview_symbol": symbol, "metric_type": metric, "value_unit": "PCTPAR", "Timeframe": "1D",
                    "source_bar_time": datetime.combine(row["date"] - timedelta(days=1), datetime.min.time(), timezone.utc),
                    "market_close_at": datetime.combine(row["date"], datetime.min.time(), timezone.utc),
                    "is_final": True, "finalized_at": NOW})
    repair.loader.bulk_upsert_prices(connection, sources)
    for ticker in ("ID10Y", "US10Y"):
        old = repair.source_history(connection, ticker)
        repair.upsert(connection, repair.calculate(old, calculated_at=NOW))
        _, _, _, states = repair.calculate_incremental(old, calculated_at=NOW, checkpoint_limit=7)
        for state in states:
            connection.execute('''INSERT INTO public."Feature04_Calculation_State"(
                asset_type,ticker,timeframe,checkpoint_date,state_version,calculation_version,
                source_position,source_chain_sha256,state_payload)
                VALUES('bonds',%s,'Daily',%s,%s,%s,%s,%s,%s)''',
                (ticker, date.fromisoformat(state["last_date"]), repair.STATE_VERSION, repair.VERSION,
                 state["position"], state["source_chain_sha256"], repair.Jsonb(state)))
        for column in repair.FEATURE_COLUMNS:
            connection.execute('''INSERT INTO public."Feature04_Column_Status"(
                asset_type,ticker,timeframe,feature_column,calculation_version,status)
                VALUES('bonds',%s,'Daily',%s,%s,'SUCCESS')''', (ticker, column, repair.VERSION))
    connection.execute('''UPDATE public."Feature04_Calculation_Queue" SET status='DONE',
        completed_generation=requested_generation''')
    # This equity sentinel and the older bonds prefix must survive the repair byte-for-byte.
    sentinel = repair.calculate(bars(1, ticker="BBCA"), calculated_at=NOW)
    repair.upsert(connection, sentinel)


@pytest.fixture
def database(monkeypatch):
    if not ADMIN:
        pytest.skip("FEATURE04_REPAIR_TEST_POSTGRES_URL is required for real transaction checks")
    database = "fi_repair_" + uuid.uuid4().hex[:12]
    with psycopg.connect(ADMIN, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    url = psycopg.conninfo.make_conninfo(ADMIN, dbname=database)
    try:
        with psycopg.connect(url, autocommit=True) as connection:
            fixture_schema(connection)
            with connection.transaction():
                seed(connection)
            def fetched(universe, schedules, dates, now, request_bars):
                rows = repair.selected_prices(connection, [item.country for item in schedules.values()], dates)
                for row in rows:
                    for key in ("open", "high", "low", "close"):
                        row[key] += Decimal("5")
                return rows
            monkeypatch.setattr(repair, "fetch_replacements", fetched)
            yield connection
    finally:
        with psycopg.connect(ADMIN, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))


def snapshot(connection):
    return {table: repair.records(connection, sql.SQL("SELECT * FROM public.{} ORDER BY to_jsonb({})::text")
        .format(sql.Identifier(table), sql.Identifier(table))) for table in TABLES}


def plan(connection):
    return repair.prepare(connection, ["ID", "US"], DATES, json.loads(repair.POLICY.read_text()), NOW, 60)


def test_atomic_cleansing_preserves_equity_and_unselected_prices_and_rebuilds_states(database, tmp_path):
    prepared = plan(database)
    before = snapshot(database)
    # Exercise the exact serialization boundary used by prepare/apply on different machines.
    prepared = repair.restore_types(json.loads(repair.encoded(prepared)))
    result = repair.apply(database, prepared, tmp_path / "backup.json", NOW)
    after = snapshot(database)
    assert result["status"] == "APPLIED" and result["removed_price_rows"] == 12
    assert result["removed_feature_rows"] == 6 and result["inserted_price_rows"] == 12
    prices = lambda data: [row for row in data["Price_Fixed_Income"] if row["date"] not in DATES]
    assert prices(before) == prices(after)
    preserved = lambda data: [row for row in data[repair.TABLE]
                             if row["asset_type"] == "equity" or row["trade_date"] < DATES[0]]
    assert preserved(before) == preserved(after)
    assert len(after["Feature04_Calculation_State"]) == 14
    assert all(row["status"] == "DONE" and row["requested_generation"] == row["completed_generation"]
               for row in after["Feature04_Calculation_Queue"])
    assert all(row["status"] == "SUCCESS" for row in after["Feature04_Column_Status"])
    assert len(after["Feature04_Calculation_Log"]) == 2
    assert (tmp_path / "backup.json").is_file()


def test_failure_after_source_cleansing_rolls_back_all_business_tables(database, tmp_path, monkeypatch):
    prepared, before = plan(database), snapshot(database)
    def broken(*args):
        raise RuntimeError("injected feature readback failure")
    monkeypatch.setattr(repair, "assert_feature_values", broken)
    with pytest.raises(RuntimeError, match="injected"):
        repair.apply(database, prepared, tmp_path / "backup.json", NOW)
    assert snapshot(database) == before


def test_stale_source_queue_or_checkpoint_aborts_without_cleansing(database, tmp_path):
    prepared = plan(database)
    database.execute('''UPDATE public."Price_Fixed_Income" SET high=high+1
        WHERE ticker='ID10Y' AND date=DATE '2026-10-01' AND metric_type='price' ''')
    before = snapshot(database)
    with pytest.raises(ValueError, match="idle and DONE|changed since preparation"):
        repair.apply(database, prepared, tmp_path / "backup.json", NOW)
    assert snapshot(database) == before


def test_unapplied_policy_migration_blocks_all_cleansing(database, tmp_path):
    prepared = plan(database)
    database.execute('''UPDATE public."Fixed_Income_Market_Schedule"
        SET source_date_mapping='CURRENT_OR_PREVIOUS_BUSINESS_DAY' WHERE market_code='ID' ''')
    before = snapshot(database)
    with pytest.raises(ValueError, match="provider-session migration"):
        repair.apply(database, prepared, tmp_path / "backup.json", NOW)
    assert snapshot(database) == before


def test_repeated_apply_cannot_delete_or_recalculate_a_second_time(database, tmp_path):
    prepared = plan(database)
    repair.apply(database, prepared, tmp_path / "backup.json", NOW)
    before = snapshot(database)
    with pytest.raises(ValueError, match="already applied"):
        repair.apply(database, prepared, tmp_path / "second-backup.json", NOW)
    assert snapshot(database) == before


def test_missing_provider_candle_keeps_source_and_feature_data(database, monkeypatch):
    before = snapshot(database)
    def missing(*args):
        raise ValueError("Replacement unavailable")
    monkeypatch.setattr(repair, "fetch_replacements", missing)
    with pytest.raises(ValueError, match="Replacement unavailable"):
        plan(database)
    assert snapshot(database) == before


def test_changed_economic_close_clock_aborts_without_cleansing(database, tmp_path):
    prepared = plan(database)
    database.execute('''UPDATE public."Fixed_Income_Market_Schedule"
        SET session_close_local='15:00' WHERE market_code='ID' ''')
    before = snapshot(database)
    with pytest.raises(ValueError, match="close/finality/correction policy changed"):
        repair.apply(database, prepared, tmp_path / "backup.json", NOW)
    assert snapshot(database) == before


def test_expired_plan_is_refused_before_backup_or_deletion(database, tmp_path):
    prepared, before = plan(database), snapshot(database)
    with pytest.raises(ValueError, match="expired"):
        repair.apply(database, prepared, tmp_path / "backup.json", NOW + timedelta(days=2))
    assert not (tmp_path / "backup.json").exists() and snapshot(database) == before


def test_cli_sha_mismatch_refuses_cleansing_before_creating_backup(database, tmp_path):
    prepared, before = plan(database), snapshot(database)
    path = tmp_path / "plan.json"
    path.write_bytes(repair.encoded(prepared))
    result = subprocess.run([sys.executable, str(ROOT / "scripts/repair_fixed_income_dates.py"),
        "apply", "--plan", str(path), "--expected-sha256", "0" * 64,
        "--backup", str(tmp_path / "backup.json"), "--confirm-apply"],
        env={**os.environ, "DATABASE_URL": database.info.dsn}, capture_output=True, text=True)
    assert result.returncode != 0 and "plan SHA256 differs" in result.stderr
    assert not (tmp_path / "backup.json").exists() and snapshot(database) == before


def test_forward_migration_rehearsal_and_repeat_guard(database):
    # Minimal catalog tables exercise the actual forward SQL, not a rewritten DDL.
    database.execute("""CREATE TABLE public."Table_Catalog" (
        table_schema text,table_name text,definition text,source_code_paths text[],updated_at timestamptz)""")
    database.execute("""INSERT INTO public."Table_Catalog" VALUES
        ('public','Fixed_Income_Market_Schedule','old','{}',CURRENT_TIMESTAMP)""")
    database.execute("""CREATE TABLE public."Column_Catalog" (
        table_schema text,table_name text,column_name text,ordinal_position integer,
        data_type text,is_nullable boolean,default_expression text,is_primary_key boolean,
        definition text,source_column_or_expression text,unit text,null_rule text,
        source_code_paths text[],documentation_status text,updated_at timestamptz DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(table_schema,table_name,column_name))""")
    database.execute("""ALTER TABLE public."Fixed_Income_Market_Schedule"
        DROP COLUMN provider_timezone_name,DROP COLUMN provider_session""")
    database.execute("""UPDATE public."Fixed_Income_Market_Schedule"
        SET source_date_mapping='CURRENT_OR_PREVIOUS_BUSINESS_DAY' WHERE market_code='ID'""")
    before = repair.records(database, 'SELECT market_code,timezone_name,session_close_local,finality_delay_minutes '
                            'FROM public."Fixed_Income_Market_Schedule" ORDER BY market_code')
    migration = (ROOT / 'database/migrations/20261013_011_verify_fixed_income_sessions.sql').read_text()
    database.execute(migration)
    after = repair.records(database, 'SELECT market_code,timezone_name,session_close_local,finality_delay_minutes '
                           'FROM public."Fixed_Income_Market_Schedule" ORDER BY market_code')
    assert before == after
    rows = repair.records(database, 'SELECT * FROM public."Fixed_Income_Market_Schedule"')
    policy = json.loads(repair.POLICY.read_text())
    assert all(all(row[key] == value for key,value in policy[row['market_code']].items()) for row in rows)
    assert database.execute('SELECT count(*) FROM public."Column_Catalog"').fetchone()[0] == 3
    with pytest.raises(psycopg.errors.RaiseException, match='Unexpected fixed-income source mapping'):
        database.execute(migration)
    database.execute('ROLLBACK')
