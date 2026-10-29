"""EXEC-LOADER-M217 (go 2026-10-29): migration 20261029_001 remarks every IDX_Broker_Summary date after any write and
never refuses a load. Runs the migration in a scratch database on UPDATER_TEST_POSTGRES_URL's server (or
ORC_TEST_POSTGRES_URL), with a minimal Table_Catalog/Column_Catalog and the live 15-column IDX_Broker_Summary."""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import psycopg
import pytest

URL = os.environ.get('UPDATER_TEST_POSTGRES_URL') or os.environ.get('ORC_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='UPDATER_TEST_POSTGRES_URL is not set')
MIGRATIONS = [Path(__file__).resolve().parents[2] / 'database/migrations' / name for name in
              ('20261029_001_broker_summary_date_quality.sql', '20261029_002_broker_summary_quality_checks.sql')]
SCRATCH = 'm217_quality_test'
BASE = '''
CREATE TABLE public."IDX_Broker_Summary" ("Date" date NOT NULL, "Symbol" varchar NOT NULL, "Broker" varchar NOT NULL,
 "Investor Type" varchar NOT NULL, "Market Board" varchar NOT NULL, "Buy Value" numeric NOT NULL,
 "Sell Value" numeric NOT NULL, "Net Value" numeric NOT NULL, "Buy Lots" numeric NOT NULL, "Sell Lots" numeric NOT NULL,
 "Net Lots" numeric NOT NULL, "Avg Buy" numeric, "Avg Sell" numeric, buy_freq bigint, sell_freq bigint,
 PRIMARY KEY ("Date", "Symbol", "Broker", "Investor Type", "Market Board"));
CREATE TABLE public."Table_Catalog" (table_schema text, table_name text, category text, definition text, grain text,
 primary_key_columns text[], source_system text, source_tables text[], source_code_paths text[], update_rule text,
 related_functions text[], documentation_status text, readiness_mode text, readiness_date_column text,
 observation_date_column text, availability_rule text, PRIMARY KEY (table_schema, table_name));
CREATE TABLE public."Column_Catalog" (table_schema text, table_name text, column_name text, ordinal_position int,
 data_type text, is_nullable boolean, default_expression text, is_primary_key boolean, definition text,
 source_column_or_expression text, unit text, null_rule text, source_code_paths text[], documentation_status text,
 PRIMARY KEY (table_schema, table_name, column_name));
'''
STOCKS = [f'S{chr(65 + i // 26)}{chr(65 + i % 26)}A' for i in range(30)]  # four-letter symbols
OTHERS = ['AAAA-W', 'BBBB-R', 'CCCC-W']
BROKERS = [f'B{i}' for i in range(8)]
DAY0 = date(2026, 9, 1)


@pytest.fixture()
def db():
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS {SCRATCH}')
        admin.execute(f'CREATE DATABASE {SCRATCH}')
    url = psycopg.conninfo.make_conninfo(URL, dbname=SCRATCH)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(BASE)
        for migration in MIGRATIONS:
            conn.execute(migration.read_text())
        yield conn
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS {SCRATCH}')


def rows(day: date, stocks=STOCKS, brokers=BROKERS, freq=True, others=OTHERS):
    out = [(day, s, b, 'Domestic', 'Regular', 100, 40, 60, 10, 4, 6, 10, 10, 3 if freq else None, 2 if freq else None)
           for s in stocks for b in brokers]
    out += [(day, s, b, 'Domestic', 'Regular', 5, 5, 0, 1, 1, 0, 5, 5, None, None) for s in others for b in brokers[:2]]
    return out


def load(conn, data, upsert=False):
    """One INSERT statement, like the updater's (INSERT ... ON CONFLICT DO UPDATE) when upsert is set."""
    with psycopg.ClientCursor(conn) as cur:
        conflict = (' ON CONFLICT ("Date","Symbol","Broker","Investor Type","Market Board") DO UPDATE SET '
                    'buy_freq = EXCLUDED.buy_freq, sell_freq = EXCLUDED.sell_freq '
                    'WHERE (t.buy_freq, t.sell_freq) IS DISTINCT FROM (EXCLUDED.buy_freq, EXCLUDED.sell_freq)'
                    if upsert else '')
        values = ','.join(cur.mogrify('(' + ','.join(['%s'] * 15) + ')', r) for r in data)
        cur.execute(f'INSERT INTO public."IDX_Broker_Summary" AS t VALUES {values}{conflict}')


def quality(conn, day):
    return conn.execute('SELECT status, remark, stock_complete, other_complete, findings FROM '
                        'public.broker_summary_date_quality WHERE trade_date = %s', (day,)).fetchone()


def history(conn, n=8):
    for i in range(n):
        load(conn, rows(DAY0 + timedelta(days=i)))


def test_early_dates_are_unchecked_then_complete(db) -> None:
    history(db, 8)
    assert [quality(db, DAY0 + timedelta(days=i))[0] for i in range(8)] == ['UNCHECKED'] * 5 + ['COMPLETE'] * 3
    assert 'perlu 5' in quality(db, DAY0)[1]


def test_reloading_the_same_rows_keeps_the_date_complete(db) -> None:
    history(db, 8)
    load(db, rows(DAY0 + timedelta(days=7)), upsert=True)  # (a) nothing differs: no row updated, status unchanged
    assert quality(db, DAY0 + timedelta(days=7))[0] == 'COMPLETE'


def test_a_date_without_frequency_is_loaded_and_remarked(db) -> None:
    history(db, 8)
    day = DAY0 + timedelta(days=8)
    load(db, rows(day, freq=False))  # (b) the load is not refused
    status, remark, stock_ok, _, findings = quality(db, day)
    assert status == 'INCOMPLETE' and not stock_ok and [f['check'] for f in findings] == ['stock_freq_share']
    assert 'frekuensi terisi pada 0.0% baris saham (biasanya 100.0%)' in remark and 'stockbit-updater' in remark
    assert db.execute('SELECT count(*) FROM public."IDX_Broker_Summary" WHERE "Date" = %s', (day,)).fetchone()[0] > 0
    load(db, rows(day), upsert=True)  # the reload with frequency clears it
    assert quality(db, day)[0] == 'COMPLETE'


def test_missing_brokers_are_remarked_and_the_bad_date_is_no_baseline(db) -> None:
    history(db, 8)
    bad = DAY0 + timedelta(days=8)
    load(db, rows(bad, brokers=BROKERS[:4]))  # (c) half the brokers
    status, remark, stock_ok, _, findings = quality(db, bad)
    assert status == 'INCOMPLETE' and not stock_ok and [f['check'] for f in findings] == ['stock_brokers']
    assert 'broker 4 (biasanya 8)' in remark
    load(db, rows(DAY0 + timedelta(days=9)))  # the next good date is compared with the good dates only
    assert quality(db, DAY0 + timedelta(days=9))[0] == 'COMPLETE'


def test_vanished_non_stock_symbols_name_m218_and_keep_the_stock_baseline(db) -> None:
    """The same mechanism on the other symbol group (M218 since 2026-09-01): remarked, but the stock checks passed."""
    history(db, 8)
    day = DAY0 + timedelta(days=8)
    load(db, rows(day, others=[]))
    status, remark, stock_ok, other_ok, _ = quality(db, day)
    assert status == 'INCOMPLETE' and stock_ok and not other_ok and 'M218' in remark and 'Muat ulang' not in remark


def test_other_symbols_without_frequency_are_not_a_finding(db) -> None:
    """Not applicable: the source gives warrants and rights no frequency, so their empty frequency is never flagged."""
    history(db, 8)
    assert quality(db, DAY0 + timedelta(days=7))[4] == []


def test_deleting_a_date_removes_its_row_and_a_partial_delete_is_remarked(db) -> None:
    history(db, 8)
    day = DAY0 + timedelta(days=7)
    db.execute('DELETE FROM public."IDX_Broker_Summary" WHERE "Date" = %s AND "Broker" IN (%s, %s, %s, %s, %s)',
               (day, *BROKERS[:5]))
    assert quality(db, day)[0] == 'INCOMPLETE'
    db.execute('DELETE FROM public."IDX_Broker_Summary" WHERE "Date" = %s', (day,))
    assert quality(db, day) is None


def test_a_quiet_day_with_every_stock_and_broker_is_complete(db) -> None:
    """20261029_002: fewer rows with the same stocks and brokers is less activity, not a partial load (2025-10-16 was
    flagged by the row check and matched the exchange volume like its neighbours)."""
    history(db, 8)
    day = DAY0 + timedelta(days=8)
    quiet = [r for r in rows(day) if not (r[1] in STOCKS[:20] and r[2] in BROKERS[4:])]  # 33% fewer stock rows
    load(db, quiet)
    assert quality(db, day)[:1] == ('COMPLETE',)
