"""EXEC-UNIVERSE-BROKER L3 (go 2026-11-05) against PostgreSQL: the real Feature 01 migrations in a scratch database,
then the worker. A claim of several items of one ticker refreshes the whole ticker once; the result must equal a
from-scratch refresh, every item must end DONE with its own SUCCESS log, and one item keeps the 121-row path.
Runs on FEATURE01_TEST_POSTGRES_URL's server (a scratch database is created and dropped)."""
from __future__ import annotations

import os
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

import psycopg

import worker as w

URL = os.environ.get('FEATURE01_TEST_POSTGRES_URL')
MIGRATIONS = Path(__file__).resolve().parents[2] / 'database/migrations'
SCRATCH = 'feature01_l3_test'
BASE = '''
CREATE TABLE public."IDX_Stock_Universe" ("Ticker" text PRIMARY KEY, "Sector" text, "Industry" text,
 "Security Type" text);
CREATE TABLE public."Price_Stock_Indonesia_IDX" (ticker text, date date, open numeric, high numeric, low numeric,
 close numeric, volume numeric, PRIMARY KEY (ticker, date));
''' + ''.join(f'CREATE TABLE public."{t}"(x int);' for t in (
    'IDX_Broker_Profile', 'IDX_Broker_Summary', 'Monitoring_Price_ALL', 'Telegram_Command_Log',
    'Telegram_Notification_Log', 'Universe_Equity_Description', 'stockbit_broker_summary_load_log'))
STEPS = ['20260912_001_create_feature_01_stock_daily.sql', '20260913_001_create_feature_catalog.sql',
         '20260913_002_add_price_ingestion_time.sql', '20260913_003_create_table_and_column_catalog.sql',
         '20260913_004_create_feature_calculation_control.sql', '20260913_006_activate_feature_01_queue.sql']


def live_enqueue() -> str:
    """is_universe_index and the enqueue trigger function as 20261025_011 left them (the rest needs the INDEX tables)."""
    text = (MIGRATIONS / '20261025_011_exclude_index_from_stock_features.sql').read_text()
    start = text.index('CREATE FUNCTION public.is_universe_index')
    end = text.index('$function$;', text.index('CREATE OR REPLACE FUNCTION public.enqueue_feature_01_price_row')) + 11
    return text[start:end]


DAYS = [date(2025, 1, 1) + timedelta(days=i) for i in range(400)]


def price_rows(ticker, scale):
    return [(ticker, d, 100 * scale + (i * 7919 % 37) - (i % 5), 1000 + (i * 104729 % 991)) for i, d in enumerate(DAYS)]


@unittest.skipUnless(URL, 'FEATURE01_TEST_POSTGRES_URL is not set')
class CoalescedQueueTests(unittest.TestCase):
    def setUp(self):
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {SCRATCH}')
            admin.execute(f'CREATE DATABASE {SCRATCH}')
        self.url = psycopg.conninfo.make_conninfo(URL, dbname=SCRATCH)
        self.c = psycopg.connect(self.url, autocommit=True)
        self.c.execute(BASE)
        for step in STEPS:
            self.c.execute((MIGRATIONS / step).read_text())
        self.c.execute(live_enqueue())
        self.c.execute('''INSERT INTO public."IDX_Stock_Universe" VALUES ('AAAA','S1','I1','stock'),
            ('BBBB','S1','I1','stock'), ('CCCC','S2','I2','fund')''')
        self.env = mock.patch.dict(os.environ, {'DATABASE_URL': self.url})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.c.close()
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {SCRATCH}')

    def load(self, rows):
        with self.c.cursor() as cur:
            cur.executemany('''INSERT INTO public."Price_Stock_Indonesia_IDX"(ticker, date, close, volume)
                VALUES (%s,%s,%s,%s) ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close,
                volume = EXCLUDED.volume, ingestion_time = statement_timestamp()''', rows)

    def drain(self):
        outcomes = []
        while (o := w.run_once()) != 'IDLE':
            outcomes.append(o)
        return outcomes

    def feature(self):
        return self.c.execute('SELECT * FROM public."Feature_01_Stock_Daily" ORDER BY ticker, date').fetchall()

    def reference(self):
        """A from-scratch refresh of every ticker in a rolled-back transaction."""
        with self.c.transaction(force_rollback=True):
            self.c.execute('DELETE FROM public."Feature_01_Stock_Daily"')
            self.c.execute('SELECT public.refresh_feature_01_stock_daily(NULL, NULL)')
            return self.feature()

    def queue(self):
        return dict(self.c.execute('''SELECT status, count(*) FROM public."Feature_Calculation_Queue"
            GROUP BY status''').fetchall())

    def test_coalesced_claims_equal_a_full_refresh(self):
        self.load(price_rows('AAAA', 1) + price_rows('BBBB', 3) + price_rows('CCCC', 2))
        self.assertEqual(self.queue(), {'PENDING': 1200})
        outcomes = self.drain()
        self.assertEqual(outcomes, ['SUCCESS'] * 3)                   # one claim per ticker
        self.assertEqual(self.queue(), {'DONE': 1200})
        self.assertEqual(self.feature(), self.reference())
        logs = self.c.execute('''SELECT result, count(*), count(rows_refreshed), sum(rows_refreshed)
            FROM public."Feature_Calculation_Log" GROUP BY result''').fetchall()
        self.assertEqual(logs, [('SUCCESS', 1200, 3, 1200)])
        status = self.c.execute('SELECT ticker, status FROM public."Feature_Status" ORDER BY ticker').fetchall()
        self.assertEqual(status, [('AAAA', 'SUCCESS'), ('BBBB', 'SUCCESS'), ('CCCC', 'SUCCESS')])

        # historical corrections on two dates of AAAA: one claim of two items, whole ticker
        rows = price_rows('AAAA', 1)
        self.load([(t, d, c + 11, v) for t, d, c, v in (rows[30], rows[250])])
        self.assertEqual(self.drain(), ['SUCCESS'])
        self.assertEqual(self.feature(), self.reference())
        self.assertEqual(self.queue(), {'DONE': 1200})

        # one correction of BBBB: the single-item path (its row and the 120 following)
        rows = price_rows('BBBB', 3)
        self.load([(t, d, c - 5, v) for t, d, c, v in (rows[100],)])
        self.assertEqual(self.drain(), ['SUCCESS'])
        last = self.c.execute('''SELECT rows_refreshed, detail FROM public."Feature_Calculation_Log"
            WHERE ticker='BBBB' AND price_date=%s ORDER BY attempt_no DESC LIMIT 1''', (DAYS[100],)).fetchone()
        self.assertEqual(last, (121, 'Feature 01 refresh and source coverage validated'))
        self.assertEqual(self.feature(), self.reference())

    def test_reingested_item_is_superseded_alone(self):
        self.load(price_rows('AAAA', 1)[:200])
        self.drain()
        rows = price_rows('AAAA', 1)
        self.load([(t, d, c + 3, v) for t, d, c, v in rows[10:13]])
        jobs = w.claim_one()
        self.assertEqual([j.price_date for j in jobs], DAYS[10:13])
        self.load([(t, d, c + 4, v) for t, d, c, v in rows[11:12]])   # re-ingested after the claim
        self.assertEqual(w.process_one(jobs), 'SUCCESS')
        state = dict(self.c.execute('''SELECT price_date, status FROM public."Feature_Calculation_Queue"
            WHERE price_date = ANY(%s)''', (DAYS[10:13],)).fetchall())
        self.assertEqual(state, {DAYS[10]: 'DONE', DAYS[11]: 'PENDING', DAYS[12]: 'DONE'})
        self.assertEqual(self.drain(), ['SUCCESS'])
        self.assertEqual(self.feature(), self.reference())

    def test_failure_fails_every_claimed_item(self):
        self.load(price_rows('AAAA', 1)[:50])
        with mock.patch.object(w, 'validate_affected_rows', side_effect=RuntimeError('boom')):
            self.assertEqual(w.run_once(), 'FAILED')
        self.assertEqual(self.queue(), {'FAILED': 50})
        self.assertEqual(self.c.execute('''SELECT count(*) FROM public."Feature_01_Stock_Daily"''').fetchone()[0], 0)
        status = self.c.execute('SELECT status FROM public."Feature_Status"').fetchone()[0]
        self.assertNotEqual(status, 'SUCCESS')
        self.c.execute('''UPDATE public."Feature_Calculation_Queue" SET next_attempt_at = now()''')
        self.assertEqual(self.drain(), ['SUCCESS'])
        self.assertEqual(self.queue(), {'DONE': 50})


if __name__ == '__main__':
    unittest.main()
