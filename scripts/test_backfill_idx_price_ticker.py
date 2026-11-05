"""EXEC-UNIVERSE-BROKER P3 (go 2026-11-05): a BBCA session without a provider bar counts as proven no trade only when
IDX_Broker_Summary holds the session and shows no Regular-board buy for the ticker. Scratch database on
PRICE_TEST_POSTGRES_URL's server (or UPDATER_TEST_POSTGRES_URL)."""
import os
import unittest
from datetime import date

import psycopg

import backfill_idx_price_ticker as b

URL = os.environ.get('PRICE_TEST_POSTGRES_URL') or os.environ.get('UPDATER_TEST_POSTGRES_URL')
SCRATCH = 'p3_no_trade_test'


@unittest.skipUnless(URL, 'PRICE_TEST_POSTGRES_URL is not set')
class ProvenNoTradeTests(unittest.TestCase):
    def setUp(self):
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {SCRATCH}')
            admin.execute(f'CREATE DATABASE {SCRATCH}')
        self.db = psycopg.connect(psycopg.conninfo.make_conninfo(URL, dbname=SCRATCH), autocommit=True)
        self.db.execute('''CREATE TABLE public."IDX_Broker_Summary" ("Date" date, "Symbol" text, "Market Board" text,
            "Buy Value" numeric);
            INSERT INTO public."IDX_Broker_Summary" VALUES
             ('2026-10-01','BBCA','Regular',9), ('2026-10-01','XIJI','Nego',5),
             ('2026-10-02','BBCA','Regular',9), ('2026-10-02','XIJI','Regular',3)''')

    def tearDown(self):
        self.db.close()
        with psycopg.connect(URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS {SCRATCH}')

    def test_proof(self):
        days = [date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5)]
        # 10-01: only Nego -> proven; 10-02: Regular buy -> not proven; 10-05: broker summary lacks the session
        self.assertEqual(b.proven_no_trade(self.db, 'XIJI', days), {date(2026, 10, 1)})
        self.assertEqual(b.proven_no_trade(self.db, 'XIJI', []), set())


if __name__ == '__main__':
    unittest.main()
