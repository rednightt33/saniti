"""broker_import against a scratch PostgreSQL with the live IDX_Broker_Summary schema and a fake Stockbit. Needs
UPDATER_TEST_POSTGRES_URL (or ORC_TEST_POSTGRES_URL); the tables are created and dropped in a scratch schema-free
database, so point it at a throwaway database only."""
import json
import os
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

import broker_import as bi
import stockbit_ihsg_daily as source

URL = os.environ.get('UPDATER_TEST_POSTGRES_URL') or os.environ.get('ORC_TEST_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not URL, reason='UPDATER_TEST_POSTGRES_URL is not set')
SYMS = [f'{a}{b}{c}{d}' for a in 'AB' for b in 'ABCDEFGHIJ' for c in 'ABCDE' for d in 'ABCDEF'][:520]
TODAY = date.today()
D1, D2, OLD = TODAY - timedelta(days=3), TODAY - timedelta(days=2), TODAY - timedelta(days=5)
VARIANT = {'v': 0}


class FakeFetcher:
    def __init__(self, *a):
        pass

    def get_json(self, path):
        sym = path.split('/')[2].split('?')[0]
        q = dict(p.split('=') for p in path.split('?')[1].split('&'))
        day, board = q['from'], q['market_board']
        buys, sells = [], []
        if board.endswith('REGULER') and sym in SYMS[:200]:
            v = Decimal(1000 + VARIANT['v'])
            d = day.replace('-', '')
            buys = [{'netbs_broker_code': 'YP', 'netbs_stock_code': sym, 'netbs_date': d, 'bval': v,
                     'blot': Decimal('1.5'), 'netbs_buy_avg_price': Decimal(100), 'freq': Decimal(3)}]
            sells = [{'netbs_broker_code': 'CC', 'netbs_stock_code': sym, 'netbs_date': d, 'sval': v,
                      'slot': Decimal('1.5'), 'netbs_sell_avg_price': Decimal(100), 'freq': Decimal(3)}]
        body = {'data': {'from': day, 'to': day, 'broker_summary': {'brokers_buy': buys, 'brokers_sell': sells}}}
        return body, json.dumps(body, default=str).encode(), 1


@pytest.fixture()
def pg(monkeypatch):
    monkeypatch.setattr(source, 'StockbitFetcher', FakeFetcher)
    bi.STOP.clear()
    with psycopg.connect(URL, autocommit=True) as db:
        for t in ('"IDX_Broker_Summary"', '"Price_Stock_Indonesia_IDX"', '"IDX_Stock_Universe"',
                  'stockbit_full_broker_import_status'):
            db.execute(f'DROP TABLE IF EXISTS public.{t}')
        db.execute('''CREATE TABLE public."IDX_Broker_Summary" ("Date" date NOT NULL, "Symbol" varchar NOT NULL,
            "Broker" varchar NOT NULL, "Investor Type" varchar NOT NULL, "Market Board" varchar NOT NULL,
            "Buy Value" numeric NOT NULL, "Sell Value" numeric NOT NULL, "Net Value" numeric NOT NULL,
            "Buy Lots" numeric NOT NULL, "Sell Lots" numeric NOT NULL, "Net Lots" numeric NOT NULL,
            "Avg Buy" numeric, "Avg Sell" numeric, buy_freq bigint, sell_freq bigint,
            PRIMARY KEY ("Date","Symbol","Broker","Investor Type","Market Board"))''')
        db.execute('''CREATE TABLE public.stockbit_full_broker_import_status (trade_date date PRIMARY KEY,
            manifest_hash text NOT NULL, state text NOT NULL, expected_symbols integer NOT NULL,
            completed_symbols integer NOT NULL DEFAULT 0, row_count bigint NOT NULL DEFAULT 0,
            anomaly_symbols integer NOT NULL DEFAULT 0, heartbeat_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz, error_message text)''')
        db.execute('CREATE TABLE public."Price_Stock_Indonesia_IDX" (date date, ticker text, timeframe text)')
        db.execute('CREATE TABLE public."IDX_Stock_Universe" ("Ticker" text)')
        with db.cursor() as cur:
            cur.executemany('INSERT INTO public."IDX_Stock_Universe" VALUES (%s)', [(s,) for s in SYMS])
            cur.executemany('INSERT INTO public."Price_Stock_Indonesia_IDX" VALUES (%s,%s,%s)',
                            [(d, s, 'daily') for d in (OLD, D1, D2) for s in SYMS[:3]])
        # OLD is already loaded; a warrant row on D1 was loaded separately (decision K1) and must stay untouched
        db.execute('''INSERT INTO public."IDX_Broker_Summary" VALUES (%s,'AAAA','YP','Domestic','Regular',1,0,1,1,0,1,
                      1,NULL,1,0), (%s,'AAAA-W','YP','Domestic','Regular',10,0,10,1,0,1,100,NULL,NULL,NULL)''', (OLD, D1))
        yield db


def loader(db, events):
    return bi.BrokerImport(db, 'x.y.z', Path(tempfile.mkdtemp()), 4, lambda e, **k: events.append((e, k)), 3)


def test_dates_come_from_the_price_calendar_and_existing_rows_are_kept(pg):
    events = []
    # D1 holds a warrant row only: it is not "missing" as a date, but newer than the newest date is D2 only
    assert loader(pg, events).pending_dates() == [str(D2)]
    pg.execute('DELETE FROM public."IDX_Broker_Summary" WHERE "Symbol" = %s', ('AAAA-W',))
    assert loader(pg, events).pending_dates() == [str(D1), str(D2)]


def test_a_round_loads_the_missing_dates_once_and_leaves_other_symbols(pg):
    pg.execute('DELETE FROM public."IDX_Broker_Summary" WHERE "Symbol" = %s', ('AAAA-W',))
    pg.execute('''INSERT INTO public."IDX_Broker_Summary" VALUES (%s,'AAAA-W','YP','Domestic','Regular',10,0,10,1,0,1,
                  100,NULL,NULL,NULL)''', (OLD,))
    events = []
    result = loader(pg, events).run()
    assert result['dates'] == [str(D1), str(D2)] and result['rows'] == 2 * 800
    assert pg.execute('SELECT count(*) FROM public.stockbit_full_broker_import_status WHERE state = %s',
                      ('completed',)).fetchone()[0] == 2
    assert loader(pg, events).run()['dates'] == []  # nothing missing any more: the next round is a no-op
    assert pg.execute('''SELECT count(*) FROM public."IDX_Broker_Summary" WHERE "Symbol" = 'AAAA-W' ''').fetchone()[0] == 1


def test_verify_compares_a_stored_date_without_writing(pg):
    events = []
    loader(pg, events).run()
    clean = loader(pg, events).run(str(D2))['verify']
    assert (clean['different'], clean['missing_in_fetch'], clean['new_in_fetch']) == (0, 0, 0)
    VARIANT['v'] = 5
    try:
        changed = loader(pg, events).run(str(D2))['verify']
    finally:
        VARIANT['v'] = 0
    assert changed['different'] == 800 and {'Buy Value', 'Sell Value'} & set(changed['examples'][0]['columns'])
    assert pg.execute('''SELECT max("Buy Value") FROM public."IDX_Broker_Summary" WHERE "Date" = %s''',
                      (D2,)).fetchone()[0] == 1000  # VERIFY wrote nothing
