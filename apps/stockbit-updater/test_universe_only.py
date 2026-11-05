"""EXEC-UNIVERSE-BROKER S2 (go 2026-11-05): Feature 05 holds only IDX_Stock_Universe tickers; rows already stored for
other codes stay; the refresh compares universe rows; the IHSG INDEX is due when the all-symbol totals change.
Runs migration 20261105_002 in a scratch database on UPDATER_TEST_POSTGRES_URL's server (or ORC_TEST_POSTGRES_URL)."""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import psycopg
import pytest

import refresh

URL = os.environ.get('UPDATER_TEST_POSTGRES_URL') or os.environ.get('ORC_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='UPDATER_TEST_POSTGRES_URL is not set')
MIGRATION = Path(__file__).resolve().parents[2] / 'database/migrations/20261105_002_broker_features_universe_only.sql'
SCRATCH = 's2_universe_test'
D0, D1 = date(2026, 8, 31), date(2026, 9, 1)
BASE = '''
CREATE TABLE public."IDX_Stock_Universe" ("Ticker" text PRIMARY KEY, "Security Type" text NOT NULL);
CREATE TABLE public."IDX_Broker_Summary" ("Date" date NOT NULL, "Symbol" varchar NOT NULL, "Broker" varchar NOT NULL,
 "Investor Type" varchar NOT NULL, "Market Board" varchar NOT NULL, "Buy Value" numeric NOT NULL,
 "Sell Value" numeric NOT NULL, "Net Value" numeric NOT NULL, "Buy Lots" numeric NOT NULL, "Sell Lots" numeric NOT NULL,
 "Net Lots" numeric NOT NULL, "Avg Buy" numeric, "Avg Sell" numeric, buy_freq bigint, sell_freq bigint,
 PRIMARY KEY ("Date", "Symbol", "Broker", "Investor Type", "Market Board"));
CREATE TABLE public."Feature_05_Foreign_Domestic_Broker_Detail" (trade_date date, ticker text, broker text,
 market_board text, investor_type text, buy_value numeric, sell_value numeric, net_value numeric, buy_lots numeric,
 sell_lots numeric, net_lots numeric, buy_freq bigint, sell_freq bigint, source_balance_gap boolean,
 PRIMARY KEY (ticker, trade_date, broker, investor_type, market_board));
CREATE TABLE public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX" (trade_date date, ticker text, broker text,
 market_board text, investor_type text, buy_value numeric, sell_value numeric, buy_lots numeric, sell_lots numeric,
 buy_freq bigint, sell_freq bigint);
CREATE TABLE public."Table_Catalog" (table_schema text, table_name text, update_rule text,
 PRIMARY KEY (table_schema, table_name));
INSERT INTO public."Table_Catalog" VALUES ('public', 'Feature_05_Foreign_Domestic_Broker_Detail', 'Refreshed daily.'),
 ('public', 'Feature_02_Broker_Rolling', NULL), ('public', 'Feature_03_Stock_Broker_Daily', 'x'),
 ('public', 'Feature_06_Foreign_Domestic', 'y');
INSERT INTO public."IDX_Stock_Universe" VALUES ('AAAA', 'stock'), ('IHSG', 'index');
'''


def row(d, symbol, broker='YP', buy=100, sell=100):
    return (d, symbol, broker, 'Domestic', 'Regular', buy, sell, buy - sell, buy, sell, buy - sell, 1, 1, 2, 3)


@pytest.fixture()
def db():
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS {SCRATCH}')
        admin.execute(f'CREATE DATABASE {SCRATCH}')
    url = psycopg.conninfo.make_conninfo(URL, dbname=SCRATCH)
    with psycopg.connect(url, autocommit=True) as c:
        c.execute(BASE)
        c.execute(MIGRATION.read_text())
        yield c
    with psycopg.connect(URL, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS {SCRATCH}')


def load(c, rows):
    c.cursor().executemany('INSERT INTO public."IDX_Broker_Summary" VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                           rows)


def plan(c):
    return refresh.plan(c.execute(refresh.PER_DATE).fetchall())


def f05(c):
    return sorted(c.execute('SELECT trade_date, ticker FROM public."Feature_05_Foreign_Domestic_Broker_Detail"').fetchall())


def build_index(c):
    c.execute('DELETE FROM public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX"')
    c.execute('''INSERT INTO public."Feature_05_Foreign_Domestic_Broker_Detail_INDEX"
        SELECT "Date", 'IHSG', "Broker", "Market Board", "Investor Type", sum("Buy Value"), sum("Sell Value"),
               sum("Buy Lots"), sum("Sell Lots"), sum(buy_freq), sum(sell_freq)
        FROM public."IDX_Broker_Summary" GROUP BY 1, 3, 4, 5''')


def test_only_universe_written_and_old_rows_kept(db):
    # an old row of a code outside the universe, stored before S2
    db.execute('''INSERT INTO public."Feature_05_Foreign_Domestic_Broker_Detail" VALUES
        ('2026-08-31', 'BBBB-W', 'YP', 'Regular', 'Domestic', 5, 5, 0, 5, 5, 0, 1, 1, false)''')
    load(db, [row(D0, 'AAAA'), row(D0, 'BBBB-W', buy=5, sell=5), row(D1, 'AAAA'), row(D1, 'CCCC'), row(D1, 'DDDDXYZ7A')])
    for d in (D0, D1):
        db.execute('SELECT public.refresh_feature_05(%s, %s)', (d, d + timedelta(days=1)))
    assert f05(db) == [(D0, 'AAAA'), (D0, 'BBBB-W'), (D1, 'AAAA')]   # CCCC and the long code not computed; BBBB-W kept
    assert db.execute('SELECT public.refresh_feature_05(%s, %s)', (D1, D1 + timedelta(days=1))).fetchone()[0] == 1


def test_plan_compares_universe_rows_and_index_all_symbols(db):
    load(db, [row(D0, 'AAAA'), row(D1, 'AAAA'), row(D1, 'CCCC')])
    dates, index_dates = plan(db)
    assert dates == [D0, D1] and index_dates == [D0, D1]
    for d in (D0, D1):
        db.execute('SELECT public.refresh_feature_05(%s, %s)', (d, d + timedelta(days=1)))
    build_index(db)
    assert plan(db) == ([], [])                                     # CCCC is outside the universe: nothing due
    src, stored, differing = db.execute(refresh.ROW_DIFF, {'d': D1}).fetchone()
    assert (src, stored, differing) == (1, 1, 0)
    load(db, [row(D1, 'EEEEXYZ7A', buy=7, sell=7)])                 # an upload of a code outside the universe
    assert plan(db) == ([], [D1])                                   # only the IHSG INDEX is due
    db.execute('''INSERT INTO public."IDX_Stock_Universe" VALUES ('CCCC', 'stock')''')
    assert plan(db)[0] == [D1]                                      # a ticker added to the universe is computed
    db.execute('SELECT public.refresh_feature_05(%s, %s)', (D1, D1 + timedelta(days=1)))
    assert plan(db)[0] == []


def test_index_needed_follows_index_dates(monkeypatch):
    monkeypatch.setattr(refresh, 'INDEX_DUE', [D1])
    assert refresh.index_needed(False) is True


def test_orphan_universe_date_stops(db):
    db.execute('''INSERT INTO public."Feature_05_Foreign_Domestic_Broker_Detail" VALUES
        ('2026-08-31', 'AAAA', 'YP', 'Regular', 'Domestic', 5, 5, 0, 5, 5, 0, 1, 1, false)''')
    with pytest.raises(refresh.RefreshFailed):
        plan(db)


def test_catalog_rule_appended_once(db):
    rules = dict(db.execute('SELECT table_name, update_rule FROM public."Table_Catalog"').fetchall())
    assert all('EXEC-UNIVERSE-BROKER S2' in r for r in rules.values())
    assert rules['Feature_05_Foreign_Domestic_Broker_Detail'].startswith('Refreshed daily. From 2026-11-05')
    db.execute(MIGRATION.read_text())
    again = dict(db.execute('SELECT table_name, update_rule FROM public."Table_Catalog"').fetchall())
    assert again == rules
