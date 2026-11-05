"""EXEC-UNIVERSE-BROKER P2 (go 2026-11-05) against PostgreSQL: migration 20261105_003 on a copy of the live
Monitoring_Price_ALL shape, then the run's writes, the recovery selection and the broker cross-check.
Runs in a scratch database on PRICE_TEST_POSTGRES_URL's server (or UPDATER_TEST_POSTGRES_URL)."""
from __future__ import annotations

import os
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import psycopg

import price_update as p

URL = os.environ.get('PRICE_TEST_POSTGRES_URL') or os.environ.get('UPDATER_TEST_POSTGRES_URL')
MIGRATION = Path(__file__).resolve().parents[2] / 'database/migrations/20261105_003_price_no_trade.sql'
SCRATCH = 'p2_no_trade_test'
BASE = '''
CREATE TABLE public."Monitoring_Price_ALL" (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, exchange text NOT NULL,
 asset_type text NOT NULL, timeframe text NOT NULL DEFAULT '1d' CHECK (timeframe = '1d'),
 run_type text NOT NULL CHECK (run_type IN ('DAILY','RECOVERY')), expected_symbols integer NOT NULL,
 queried_symbols integer NOT NULL, updated_symbols integer NOT NULL, missing_symbols integer NOT NULL,
 missing_symbol_list jsonb NOT NULL DEFAULT '[]', update_for_date date NOT NULL, run_time timestamptz NOT NULL,
 finished_at timestamptz NOT NULL, attempt_count smallint NOT NULL, status text NOT NULL, last_error text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 execution_id text NOT NULL, trigger_source text NOT NULL, query_time timestamptz NOT NULL,
 CONSTRAINT "Monitoring_Price_ALL_counts_check" CHECK (expected_symbols >= 0 AND queried_symbols >= 0
   AND updated_symbols >= 0 AND missing_symbols >= 0 AND queried_symbols <= expected_symbols
   AND updated_symbols <= queried_symbols AND missing_symbols = queried_symbols - updated_symbols),
 CONSTRAINT "Monitoring_Price_ALL_execution_key" UNIQUE (execution_id, exchange, asset_type, timeframe));
CREATE TABLE public."Price_Stock_Indonesia_IDX" (ticker text, date date, PRIMARY KEY (ticker, date));
CREATE TABLE public."IDX_Broker_Summary" ("Date" date, "Symbol" text, "Broker" text, "Investor Type" text,
 "Market Board" text, "Buy Value" numeric);
CREATE TABLE public."Column_Catalog" (table_schema text, table_name text, column_name text, ordinal_position int,
 data_type text, is_nullable boolean, default_expression text, is_primary_key boolean, definition text,
 source_column_or_expression text, unit text, null_rule text, source_code_paths text[], documentation_status text,
 PRIMARY KEY (table_schema, table_name, column_name));
'''
D3, D4 = date(2026, 11, 3), date(2026, 11, 4)


@unittest.skipUnless(URL, 'PRICE_TEST_POSTGRES_URL is not set')
class NoTradeDatabaseTests(unittest.TestCase):
    def setUp(self):
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {SCRATCH}')
            admin.execute(f'CREATE DATABASE {SCRATCH}')
        self.c = psycopg.connect(psycopg.conninfo.make_conninfo(URL, dbname=SCRATCH), autocommit=True)
        self.c.execute(BASE)
        # a row written by the code before P2 (no no_trade columns yet)
        self.c.execute('''INSERT INTO public."Monitoring_Price_ALL"(exchange, asset_type, run_type, expected_symbols,
            queried_symbols, updated_symbols, missing_symbols, missing_symbol_list, update_for_date, run_time,
            finished_at, attempt_count, status, execution_id, trigger_source, query_time)
            VALUES ('IDX','stock','DAILY',3,3,2,1,'["BBBB"]','2026-11-02',now(),now(),1,'PARTIAL','old','SCHEDULED',now())''')
        self.c.execute(MIGRATION.read_text())
        self.universe = [p.Symbol(1, 'A', 'AAAA', 'IDX:AAAA', 'IDX', 'stock'),
                         p.Symbol(2, 'B', 'BBBB', 'IDX:BBBB', 'IDX', 'stock'),
                         p.Symbol(3, 'C', 'CCCC', 'IDX:CCCC', 'IDX', 'stock')]

    def tearDown(self):
        self.c.close()
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {SCRATCH}')

    def write(self, target, outcomes, execution_id, run_type='DAILY', queried=None, **kw):
        now = datetime(2026, 11, 4, 10, tzinfo=timezone.utc)
        records = p.monitoring_records(self.universe, queried or self.universe, outcomes, run_type, target, now, now,
                                       execution_id, 'SCHEDULED', now, **kw)
        p.write_monitoring_rows(self.c, records)
        return records

    def test_old_rows_survive_and_no_trade_is_stored(self):
        u = self.universe
        self.c.execute("INSERT INTO public.\"Price_Stock_Indonesia_IDX\" VALUES ('AAAA','2026-11-03'),('CCCC','2026-11-03')")
        self.write(D3, [p.FetchOutcome(u[0], {'ticker': 'AAAA'}, None, None),
                        p.FetchOutcome(u[1], None, date(2026, 11, 2), 'No 1D candle', answered=True),
                        p.FetchOutcome(u[2], {'ticker': 'CCCC'}, None, None)], 'daily-3')
        row = self.c.execute('''SELECT status, missing_symbols, no_trade_symbols, no_trade_symbol_list
            FROM public."Monitoring_Price_ALL" WHERE execution_id='daily-3' ''').fetchone()
        self.assertEqual(row, ('SUCCESS', 0, 1, ['BBBB']))
        # the recovery asks the no-trade symbol once more
        self.assertEqual([s.ticker for s in p.get_recovery_symbols(self.c, self.universe, D3)], ['BBBB'])

    def test_contradiction_found_once(self):
        u = self.universe
        self.write(D3, [p.FetchOutcome(u[0], {'ticker': 'AAAA'}, None, None),
                        p.FetchOutcome(u[1], None, date(2026, 11, 2), 'No 1D candle', answered=True),
                        p.FetchOutcome(u[2], None, date(2026, 11, 2), 'No 1D candle', answered=True)], 'daily-3')
        # the broker round of the same evening: BBBB traded on the Regular board, CCCC only on Nego
        self.c.execute('''INSERT INTO public."IDX_Broker_Summary" VALUES ('2026-11-03','BBBB','YP','Domestic','Regular',5),
            ('2026-11-03','CCCC','YP','Domestic','Nego',9)''')
        gaps = p.no_trade_contradictions(self.c, D4)
        self.assertEqual(gaps, [{'date': '2026-11-03', 'ticker': 'BBBB'}])
        self.write(D4, [p.FetchOutcome(s, {'ticker': s.ticker}, None, None) for s in u], 'daily-4', contradicted=gaps)
        status = self.c.execute("SELECT status FROM public.\"Monitoring_Price_ALL\" WHERE execution_id='daily-4'").fetchone()
        self.assertEqual(status[0], 'PARTIAL')
        self.assertEqual(p.no_trade_contradictions(self.c, D4), [])          # reported once
        self.assertTrue(p.price_session_exists(self.c, D3) is False)

    def test_count_rule_enforced(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.c.execute('''INSERT INTO public."Monitoring_Price_ALL"(exchange, asset_type, run_type, expected_symbols,
                queried_symbols, updated_symbols, missing_symbols, no_trade_symbols, no_trade_symbol_list,
                update_for_date, run_time, finished_at, attempt_count, status, execution_id, trigger_source, query_time)
                VALUES ('IDX','stock','DAILY',3,3,1,1,0,'[]','2026-11-04',now(),now(),1,'PARTIAL','bad','SCHEDULED',now())''')


if __name__ == '__main__':
    unittest.main()
