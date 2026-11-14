import datetime as dt
import gzip
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publisher as pub  # noqa: E402


class FakeBucket:
    def __init__(self):
        self.objects, self.modified, self.deleted = {}, {}, []
        self.puts = []                                     # every put, in order (the objects dict keeps first order)
        self.clock = dt.datetime(2026, 10, 25, 0, 0, tzinfo=dt.timezone.utc)   # the bucket's LastModified clock

    def put(self, key, body, content_type):
        self.objects[key] = body
        self.modified[key] = self.clock
        self.puts.append(key)

    def list(self, deadline=None, prefix=''):
        return {k: (self.modified.get(k, self.clock), len(v)) for k, v in self.objects.items() if k.startswith(prefix)}

    def delete(self, keys):
        for k in keys:
            self.objects.pop(k, None)
            self.modified.pop(k, None)
        self.deleted += list(keys)
        return []

    def get_raw(self, key):
        return self.objects.get(key)

    def get_json(self, key):
        body = self.objects.get(key)
        if body is None:
            return None
        return json.loads(gzip.decompress(body) if key.endswith('.gz') else body)


class Result(list):
    """A statement's rows, read as a psycopg cursor reads them: fetchall, fetchone or iteration."""
    def fetchall(self):
        return list(self)

    def fetchone(self):
        return self[0] if self else None


class FakeConn:
    """Answers the publisher's statements from small in-memory tables."""
    def __init__(self, prices, brokers, universe, events=None, actions=None, intraday=None, timeframes=None,
                 changes=None, now=None, fixed=None, fixed_universe=None, index_brokers=None):
        self.prices, self.brokers, self.universe = prices, brokers, universe
        # EXEC-IHSG-FLOW: rows of Feature_05_..._INDEX (an index's market aggregate), the same shape as `brokers`
        self.index_brokers = list(index_brokers or [])
        # EXEC-FI-TERMINAL: bond rows (ticker, metric_type, date, o, h, l, c, ingested) and Universe_Fixed_income
        self.fixed, self.fixed_universe = list(fixed or []), list(fixed_universe or [])
        self.events = list(EVENTS if events is None else events)
        self.actions = list(ACTIONS if actions is None else actions)
        # EXEC-INTRADAY-FEATURES C1: bars (ticker, tf, bar_time, o, h, l, c, v), timeframes (tf, bars_per_year),
        # change records (ticker, tf, changed_from, changed_at) and the database clock
        self.intraday = list(intraday or [])
        self.timeframes = list(timeframes or [])
        self.changes = list(changes or [])
        self.now = now or dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.timezone.utc)
        self.statements = []
        # EXEC-PUBLISH-FLOW: advisory locks held by others (names), RUNNING broker rounds, loader signal times
        self.held, self.rounds, self.signals = set(), 0, []
        # EXEC-SCREENER-FLOW-CANDLES P4: Monitoring_Stockbit_Update rows (finished_at, mode, status, changed_dates), and
        # every statement with its parameters
        self.broker_rounds, self.calls = [], []
        # EXEC-SCREENER-STOCK-LISTS: Stock_List rows as STOCK_LISTS_SQL answers them (None: the tables are missing)
        self.stock_lists = list(STOCK_LISTS)

    def execute(self, sql, params=()):
        self.statements.append(sql)
        self.calls.append((sql, params))
        return Result(self._rows(sql, params))

    def cursor(self):
        """A cursor for stream() (publisher.stream_rows): the same rows as execute."""
        conn = self
        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def stream(self, sql, params=(), size=1):
                return iter(conn.execute(sql, params))
        return Cursor()

    def _bars(self, t, tf, lo=pub.EPOCH, hi=pub.END_OF_TIME):
        return sorted(b for b in self.intraday if b[0] == t and b[1] == tf and lo <= b[2] < hi)

    def _fi(self, ticker, metric, lo, hi):
        return sorted(r for r in self.fixed if r[0] == ticker and r[1] == metric and lo <= r[2] <= hi)

    def _rows(self, sql, params):
        # EXEC-SCREENER-FLOW-CANDLES P4: the broker day statements (before the broader matches below)
        if sql == pub.BROKER_DAYS_WINDOW_SQL:              # the skip scan: the newest n distinct dates, oldest first
            return [(d,) for d in sorted({r[1] for r in self.brokers})[-params[0]:]]
        if sql == pub.BROKER_DAY_SQL:                      # no ORDER BY: newest rows first, the publisher orders them
            d, tickers = params
            return [(r[0], *r[2:]) for r in reversed(self.brokers) if r[1] == d and r[0] in tickers]
        if sql == pub.BROKER_DAY_STAMPS_SQL:
            dates, tickers = params
            out = {}
            for r in self.brokers:
                if r[1] in dates and r[0] in tickers:
                    out.setdefault(r[1], []).append(r)
            # the row hash: any deterministic 64-bit hash over every column but the date does (the database's is
            # hashtextextended); a changed column changes it
            h = lambda x: int.from_bytes(hashlib.sha256(repr((x[0], *x[2:])).encode()).digest()[:8], 'big', signed=True)
            return [(d, len(v), str(sum(x[5] for x in v)), str(sum(x[6] for x in v)), str(sum(h(x) for x in v)))
                    for d, v in out.items()]
        if sql == pub.BROKER_ROUNDS_SQL:
            since = dt.datetime.fromisoformat(params[0]) if params[0] else None
            return [(at, dates) for at, mode, status, dates in sorted(self.broker_rounds, key=lambda r: r[0])
                    if mode == 'APPLY' and status == 'SUCCESS' and (since is None or at > since)]
        if sql.startswith('SELECT pg_try_advisory_lock('):
            return [(params[0] not in self.held,)]
        if sql.startswith('SELECT pg_advisory_unlock('):
            return [(True,)]
        if 'Monitoring_Stockbit_Update' in sql:
            return [(self.rounds,)]
        if sql.startswith('SELECT max(created_at) FROM ' + pub.SIGNAL_TABLE):
            return [(max(self.signals, default=None),)]
        if pub.BROKER_TABLES['index'] in sql:             # the INDEX table: the same statements on its own rows
            saved, self.brokers = self.brokers, self.index_brokers
            try:
                return self._rows(sql.replace(pub.BROKER_TABLES['index'], pub.BROKER_TABLES['stock']), params)
            finally:
                self.brokers = saved
        if sql == pub.FI_UNIVERSE_SQL:
            return self.fixed_universe
        if sql == pub.FI_STAMPS_SQL:
            out = {}
            for t, metric, d, _o, _h, _l, c, ing in self.fixed:
                out.setdefault((t, metric, int(d[:4])), []).append((d, c, ing))
            return [(t, m, y, len(v), max(x[0] for x in v), max(x[2] for x in v), str(sum(x[1] for x in v)))
                    for (t, m, y), v in out.items()]
        if sql == pub.FI_SQL:
            return [(r[2], *r[3:7], None) for r in self._fi(*params)]
        if sql == pub.FI_VERIFY_SQL:
            r = self._fi(*params)
            return [(len(r), r[0][2] if r else None, r[-1][2] if r else None, float(sum(x[6] for x in r)))]
        if sql == pub.INTRADAY_TIMEFRAMES_SQL:
            return sorted(self.timeframes)
        if sql == pub.MARKET_TZ_SQL:
            return [('Asia/Jakarta',)] if params == ('IDX',) else []
        if sql == pub.DB_NOW_SQL:
            return [(self.now,)]
        if sql == pub.INTRADAY_LAST_SQL:
            bars = self._bars(*params)
            return [(bars[-1][2] if bars else None,)]
        if sql == pub.INTRADAY_SQL:
            return [(int(b[2].timestamp()), *b[3:]) for b in self._bars(*params)]
        if sql == pub.INTRADAY_VERIFY_SQL:
            bars = self._bars(*params)
            return [(len(bars), int(bars[0][2].timestamp()) if bars else None, int(bars[-1][2].timestamp()) if bars else None,
                     float(sum(b[6] for b in bars)))]
        if sql == pub.INTRADAY_CHANGES_SQL:
            return [c for c in self.changes if c[3] > params[0]]
        if sql == pub.XSECTION_PRICE_SQL:
            lo, hi = params
            # date-major, newest first, as no ORDER BY promises nothing: the publisher groups and orders the rows itself
            return [r for r in sorted(self.prices, key=lambda r: (r[1], r[0]), reverse=True) if lo <= r[1] <= hi]
        if sql == pub.XSECTION_PRICE_CHECK_SQL:
            lo, hi = params
            out = {}
            for t, d, *_o, c, _v in self.prices:
                if lo <= d <= hi:
                    out.setdefault(t, []).append((d, c))
            return [(t, len(v), min(x[0] for x in v), max(x[0] for x in v), sum(x[1] for x in v)) for t, v in out.items()]
        if sql == pub.XSECTION_ACTIONS_SQL:
            types, since = params
            return [a for a in reversed(self.actions) if a[2] in types and a[1] >= since]
        if sql == pub.UNIVERSE_SQL:
            return self.universe
        # EXEC-RADAR R5: the Feature 07 tables are absent here (tests/test_radar.py answers them)
        if sql == pub.radar.PROBE_SQL:
            return [(False,)]
        if sql == pub.STOCK_LISTS_SQL:
            if self.stock_lists is None:
                raise RuntimeError('relation "Stock_List" does not exist')
            return self.stock_lists
        if sql == pub.PRICE_SQL:                           # ORDER BY date
            t, lo, hi = params
            return sorted((r[1:] for r in self.prices if r[0] == t and lo <= r[1] <= hi), key=lambda r: r[0])
        if sql == pub.BROKER_SQL:                          # ORDER BY trade_date, broker, investor_type, market_board
            t, lo, hi = params
            return sorted((r[1:] for r in self.brokers if r[0] == t and lo <= r[1] <= hi), key=lambda r: r[:4])
        if sql == pub.PRICE_STAMPS_SQL:
            out = {}
            for t, d, *_rest in self.prices:
                key = (t, int(d[:4]))
                out.setdefault(key, []).append((d, _rest[3]))
            return [(t, y, len(v), max(x[0] for x in v), '', str(sum(x[1] for x in v))) for (t, y), v in out.items()]
        if sql == pub.EVENTS_SQL:
            return [e[1:] for e in sorted(self.events, key=lambda e: e[1]) if e[0] == params[0]]
        if sql == pub.EVENT_STAMPS_SQL:
            out = {}
            for e in self.events:
                out.setdefault(e[0], []).append(e)
            return [(t, len(v), max(x[1] for x in v), 'ing') for t, v in out.items()]
        if 'max(ingestion_time)' in sql and 'idx_event_annotation' in sql:
            return [('2026-10-25 17:04:28+00',)]
        if sql == pub.BEHIND_SQL:
            return [(len({r[1] for r in self.prices if r[1] > params[0]}),)]
        if sql.startswith('SELECT count(*), min(annotation_date)'):
            r = [e for e in self.events if e[0] == params[0]]
            return [(len(r), min(e[1] for e in r), max(e[1] for e in r), sum(e[16] or 0 for e in r))]
        if sql.startswith('SELECT count(*), min(date)'):
            t, lo, hi = params
            r = [x for x in self.prices if x[0] == t and lo <= x[1] <= hi]
            return [(len(r), min(x[1] for x in r), max(x[1] for x in r), sum(x[5] for x in r))]
        if sql.startswith('SELECT count(*), min(trade_date)'):
            t, lo, hi = params
            r = [x for x in self.brokers if x[0] == t and lo <= x[1] <= hi]
            return [(len(r), min(x[1] for x in r), max(x[1] for x in r), sum(x[5] + x[6] for x in r),
                     sum((x[10] or 0) + (x[11] or 0) for x in r))]
        if 'min(trade_date)' in sql:
            return [(min(r[1] for r in self.brokers),)]
        if 'IDX_Broker_Profile' in sql:
            return [('AK', 'UBS', 'Foreign', 'Institutional-heavy'), ('YP', 'Mirae', 'Domestic', 'Retail-heavy')]
        if 'min(date)' in sql:
            return [(min(r[1] for r in self.prices),)]
        if 'max(date)' in sql:
            return [(max(r[1] for r in self.prices),)]
        if 'max(trade_date)' in sql:
            return [(max((r[1] for r in self.brokers), default=None),)]
        if 'DISTINCT ticker' in sql:
            return sorted({(r[0], int(r[1][:4])) for r in self.brokers if r[1] > params[0]})
        raise AssertionError(sql)


PRICES = [('BBCA', '2025-12-30', 100.0, 110.0, 95.0, 105.0, 1000.0),
          ('BBCA', '2026-01-02', 105.0, 106.0, 101.0, 102.0, 900.0),
          ('IHSG', '2026-01-02', 7000.0, 7100.0, 6950.0, 7050.0, None)]
# ticker, date, broker, investor, board, buy and sell value, buy and sell lots, source_balance_gap, buy and sell transactions
BROKERS = [('BBCA', '2026-01-02', 'AK', 'Foreign', 'Regular', 500.0, 0.0, 5.0, 0.0, False, 3, 0),
           ('BBCA', '2026-01-02', 'YP', 'Domestic', 'Regular', 0.0, 500.0, 0.0, 4.5, True, 0, 2)]
# the 17 display columns, then source_payload and the two closes of EVENTS_SQL
EVENTS = [('BBCA', '2026-03-10', 'EX_DATE', 'CORPORATE_ACTION', 'DIVIDEND', None, None, None, None, None, None, None,
           None, None, 250.0, None, None, None, {'dividend_value': '250', 'dividend_currency': 'CURRENCY_IDR', 'dividend_cumdate': '2026-03-09', 'dividend_exdate': '2026-03-10', 'dividend_recdate': '2026-03-11', 'dividend_paydate': ''}, 10000.0, None),
          ('BBCA', '2026-05-02', 'TRANSACTION_DATE', 'INSIDER', 'INSIDER_TRANSACTION', 'BUY', 'A. Holder', 'Director',
           'YP', None, 10000.0, 1.25, 0.01, 'OK', 9000.0, False, 90000000.0, 'KSEI', None, None, None),
          ('GONE', '2026-01-02', 'EX_DATE', 'CORPORATE_ACTION', 'DIVIDEND', None, None, None, None, None, None, None,
           None, None, 10.0, None, None, None, {}, None, None)]
UNIVERSE = [('BBCA', 'Bank Central Asia', 'stock', 'Finance', 'Banks', 'common'), ('IHSG', 'Composite', 'index', None, None, 'Undefined')]
# EXEC-SCREENER-STOCK-LISTS: Stock_List rows as STOCK_LISTS_SQL returns them (list_key, kind, code, name, definition,
# last_seen_at, members); a list before its first round has no member
SEEN = dt.datetime(2026, 11, 9, 13, 31, 48, tzinfo=dt.timezone.utc)
STOCK_LISTS = [('INDEX:550', 'INDEX', 'LQ45', 'LQ45', 'The 45 most liquid stocks.', SEEN, ['BBCA', 'BBRI']),
               ('KONGLO:1', 'KONGLO', 'DJARUM', 'Djarum', 'Companies of the Djarum group.', SEEN, ['BBCA']),
               ('KONGLO:2', 'KONGLO', 'NEW', 'New group', 'Not loaded yet.', None, [])]
# XSECTION_ACTIONS_SQL rows: ticker, ex date, type, ratio_old, ratio_new, amount_per_share, currency, event_key
ACTIONS = [('BBCA', '2026-03-10', 'DIVIDEND', None, None, 250.0, 'IDR', 'k1'),
           ('BBCA', '2026-10-14', 'STOCK_SPLIT', 1.0, 5.0, None, None, 'k2'),
           ('BBCA', '2026-11-03', 'DIVIDEND', None, None, 0.0, 'IDR', 'k3'),        # future; 0 is the source's unknown
           ('GONE', '2026-01-02', 'DIVIDEND', None, None, 10.0, 'IDR', 'k4'),       # not a published ticker
           ('BBCA', '2012-05-02', 'STOCK_SPLIT', 1.0, 2.0, None, None, 'k5')]       # before the first published year
TODAY = dt.date(2026, 10, 25)


def key_of(bucket, ticker, dataset, name):
    """The key (without v1/) the ticker's manifest names, as every reader finds it."""
    m = bucket.get_json(f'manifest/{ticker}.json')
    entry = m['packs'][name] if dataset == 'pack' else m['datasets'][dataset]['files'][str(name)]
    return entry['key'][len(pub.PREFIX) + 1:]


def doc_of(bucket, ticker, dataset, name):
    return bucket.get_json(key_of(bucket, ticker, dataset, name))


def run(mode, conn=None, bucket=None):
    conn = conn or FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = bucket or FakeBucket()
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run(mode)
    return p, conn, bucket


def test_window_is_current_year_and_five_before():
    assert pub.window(TODAY, 5) == (2021, 2026)


def test_backfill_writes_files_then_manifests_and_index_has_no_broker_file():
    p, _, bucket = run('backfill')
    keys = list(bucket.objects)
    assert key_of(bucket, 'BBCA', 'price', 2025) in keys and key_of(bucket, 'BBCA', 'price', 2026) in keys
    assert key_of(bucket, 'BBCA', 'broker', 2026) in keys and not any(k.startswith('broker/IHSG') for k in keys)
    assert keys.index(key_of(bucket, 'BBCA', 'broker', 2026)) < keys.index('manifest/BBCA.json')
    m = bucket.get_json('manifest/BBCA.json')
    assert m['datasets']['broker']['data_through'] == '2026-01-02'
    assert m['datasets']['price']['files']['2026']['rows'] == 1
    assert 'broker' not in bucket.get_json('manifest/IHSG.json')['datasets']


def test_broker_file_keeps_decimal_lots_investor_type_and_gaps():
    _, _, bucket = run('backfill')
    doc = doc_of(bucket, 'BBCA', 'broker', 2026)
    assert doc['sl'] == [0.0, 4.5]
    assert doc['i'] == ['Foreign', 'Domestic']
    assert doc['gap'] == [['2026-01-02', 'Regular']]


def test_broker_files_carry_the_transaction_counts_after_the_eight_columns():
    # EXEC-TERMINAL-FLOW-IND (user go 2026-10-30): bf, sf after d..sl, integers, None when the source has none
    conn = FakeConn(PRICES, BROKERS + [('BBCA', '2021-03-01', 'YU', 'Domestic', 'Nego', 5.0, 1.0, 0.5, 0.1, False, None, None)], UNIVERSE)
    _, _, bucket = run('backfill', conn=conn)
    doc = doc_of(bucket, 'BBCA', 'broker', 2026)
    assert doc['columns'] == ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf']
    assert (doc['bf'], doc['sf']) == ([3, 0], [0, 2]) and all(type(v) is int for v in doc['bf'] + doc['sf'])
    assert doc['units']['bf'] == 'buy transactions' and doc['gap'] == [['2026-01-02', 'Regular']]
    old = doc_of(bucket, 'BBCA', 'broker', 2021)
    assert (old['bf'], old['sf']) == ([None], [None])
    m = bucket.get_json('manifest/BBCA.json')
    arch = json.loads(gzip.decompress(bucket.objects[m['packs']['broker-archive']['key'][3:]]))
    assert arch['columns'][-2:] == ['bf', 'sf'] and arch['bf'] == [None]


def test_ref_brokers_carries_the_classification():
    _, _, bucket = run('backfill')
    doc = bucket.get_json('ref/brokers.json.gz')
    assert doc['columns'] == ['code', 'name', 'type', 'classification']
    assert doc['classification'] == ['Institutional-heavy', 'Retail-heavy']


def test_verify_compares_the_transaction_counts():
    _, conn, bucket = run('backfill')
    assert pub.verify(conn, bucket) == 0
    conn.brokers = [r[:10] + (r[10] + 1, r[11]) if r[1] == '2026-01-02' and r[2] == 'AK' else r for r in conn.brokers]
    # the yearly broker file and (EXEC-SCREENER-FLOW-CANDLES P4) the Screener's broker day file of that date
    assert pub.verify(conn, bucket) == 2


def test_index_price_file_keeps_null_volume():
    _, _, bucket = run('backfill')
    assert doc_of(bucket, 'IHSG', 'price', 2026)['v'] == [None]


def test_daily_after_backfill_writes_nothing_when_nothing_changed():
    p, conn, bucket = run('backfill')
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('daily')
    assert p2.written == 0


def test_daily_republishes_only_the_changed_price_year_and_new_broker_dates():
    _, conn, bucket = run('backfill')
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    conn.brokers = BROKERS + [('BBCA', '2026-01-05', 'AK', 'Foreign', 'Regular', 10.0, 0.0, 0.1, 0.0, False, 1, 0)]
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('daily')
    assert p2.written == 4  # price/BBCA/2026, broker/BBCA/2026, BBCA's price pack, the xsection price; 2025, IHSG untouched
    assert ('pack', 'BBCA', 'broker-archive') not in p2.changed   # a current-year broker change leaves the archive
    assert bucket.get_json('manifest/BBCA.json')['datasets']['broker']['data_through'] == '2026-01-05'


def test_encoding_is_deterministic():
    doc = pub.price_doc('BBCA', 2026, [r[1:] for r in PRICES[:1]])
    assert pub.encode(doc)[1] == pub.encode(doc)[1]


def test_verify_detects_a_changed_object():
    _, conn, bucket = run('backfill')
    assert pub.verify(conn, bucket) == 0
    bucket.objects[key_of(bucket, 'BBCA', 'price', 2026)] = gzip.compress(b'{}')
    assert pub.verify(conn, bucket) == 1


def test_price_and_broker_are_published_from_their_own_first_year():
    # T8 (user 2026-10-26): broker no longer keeps the 5-year window; each dataset starts at its first stored year
    prices = PRICES + [('BBCA', '2019-06-03', 50.0, 51.0, 49.0, 50.5, 10.0)]
    brokers = BROKERS + [('BBCA', '2020-06-03', 'AK', 'Foreign', 'Regular', 1.0, 0.0, 0.01, 0.0, False, 1, 0)]
    p, _, bucket = run('backfill', conn=FakeConn(prices, brokers, UNIVERSE))
    assert (p.price_first_year, p.broker_first_year) == (2019, 2020)
    assert key_of(bucket, 'BBCA', 'price', 2019) in bucket.objects and key_of(bucket, 'BBCA', 'broker', 2020) in bucket.objects
    m = bucket.get_json('manifest/BBCA.json')
    assert m['datasets']['price']['first_year'] == 2019 and m['datasets']['broker']['first_year'] == 2020
    assert '2019' in m['datasets']['price']['files'] and '2020' in m['datasets']['broker']['files']
    assert m['window']['broker_first_year'] == 2020


def test_daily_adds_missing_early_price_years():
    _, conn, bucket = run('backfill')
    conn.prices = PRICES + [('BBCA', '2019-06-03', 50.0, 51.0, 49.0, 50.5, 10.0)]
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('daily')
    # the year, the price pack and the xsection price
    assert key_of(bucket, 'BBCA', 'price', 2019) in bucket.objects and p2.written == 3


def test_events_are_one_file_per_listed_ticker_with_display_columns_only():
    _, _, bucket = run('backfill')
    doc = doc_of(bucket, 'BBCA', 'events', 'all')
    assert doc['columns'] == pub.EVENT_COLUMNS and doc['d'] == ['2026-03-10', '2026-05-02']
    assert doc['holder'] == [None, 'A. Holder'] and doc['pct_flag'] == [None, 'OK']
    assert 'source_payload' not in doc and not any(k.startswith('events/GONE/') for k in bucket.objects)  # delisted: not served
    m = bucket.get_json('manifest/BBCA.json')
    assert m['datasets']['events']['files']['all']['rows'] == 2 and 'events' not in bucket.get_json('manifest/IHSG.json')['datasets']


def test_daily_republishes_events_only_when_the_ticker_changed():
    _, conn, bucket = run('backfill')
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('daily')
    assert p2.written == 0
    conn.events.append(('BBCA', '2026-09-01', 'MEETING_DATE', 'CORPORATE_ACTION', 'RUPS', None, None, None, None,
                        None, None, None, None, None, None, None, None, None, {'rups_date': '2026-09-01'}, None, None))
    p3 = pub.Publisher(conn, bucket, today=TODAY)
    p3.run('daily')
    assert p3.written == 1 and len(doc_of(bucket, 'BBCA', 'events', 'all')['d']) == 3


def test_ticker_reference_carries_the_sector_and_industry_for_search_and_portfolio_filters():
    _, _, bucket = run('backfill')
    doc = bucket.get_json('ref/tickers.json.gz')
    assert doc['columns'] == ['ticker', 'name', 'type', 'sector', 'industry', 'instrument']
    assert doc['sector'] == ['Finance', None] and doc['industry'] == ['Banks', None]
    assert doc['instrument'] == ['common', 'Undefined']


def test_a_fund_is_published_like_a_stock():
    """EXEC-UNIVERSE-BROKER S1.4: an ETF (Security Type fund) gets price and broker files from Feature 05, as a stock."""
    universe = UNIVERSE + [('XIJI', 'Premier ETF JII', 'fund', 'Undefined', 'Undefined', 'etf')]
    prices = PRICES + [(r[0].replace('BBCA', 'XIJI'),) + tuple(r[1:]) for r in PRICES if r[0] == 'BBCA']
    brokers = BROKERS + [('XIJI',) + tuple(r[1:]) for r in BROKERS if r[0] == 'BBCA']
    _, _, bucket = run('backfill', FakeConn(prices, brokers, universe))
    m = bucket.get_json('manifest/XIJI.json')
    assert set(m['datasets']) >= {'price', 'broker'}
    assert doc_of(bucket, 'XIJI', 'broker', 2026)['bv'] == doc_of(bucket, 'BBCA', 'broker', 2026)['bv']
    ref = bucket.get_json('ref/tickers.json.gz')
    assert ref['type'][ref['ticker'].index('XIJI')] == 'fund' and ref['instrument'][ref['ticker'].index('XIJI')] == 'etf'


def test_corporate_action_detail_comes_from_the_payload_and_blank_is_none():
    _, _, bucket = run('backfill')
    doc = doc_of(bucket, 'BBCA', 'events', 'all')
    assert doc['title'] == ['Cash dividend', None] and doc['detail'][1] is None   # insider rows have no detail
    rows = {label: value for label, value, _ in doc['detail'][0]}
    assert rows['Dividend'] == 250 and rows['Cum date'] == '2026-03-09' and rows['Payment'] is None   # '' -> None
    assert abs(rows['Yield (on cum-date close)'] - 2.5) < 1e-12                                    # 250 / 10,000


def test_derived_values_need_their_close_and_zero_means_unknown():
    title, rows = pub.corporate_action('STOCK_SPLIT', {'stocksplit_old': '1', 'stocksplit_new': '5',
                                                       'stocksplit_new_price': 0}, 7320.0, None)
    assert title == 'Stock split 1 : 5' and dict((a, b) for a, b, _ in rows)['Price after (from cum-date close)'] == 1464
    title, rows = pub.corporate_action('STOCK_SPLIT', {'stocksplit_old': '1', 'stocksplit_new': '5'}, None, None)
    assert dict((a, b) for a, b, _ in rows)['Price after (from cum-date close)'] is None    # cum date not traded yet
    _, rows = pub.corporate_action('TENDER_OFFER', {'tender_price': '3600', 'tender_shares': '0'}, None, 3380.0)
    d = dict((a, b) for a, b, _ in rows)
    assert abs(d['Premium (vs close before start)'] - (3600 / 3380 - 1) * 100) < 1e-9 and d['Shares sought'] is None
    assert pub.corporate_action('PUBLIC_EXPOSE', {}, None, None) == (None, None)


def test_a_new_events_format_republishes_every_events_file_once():
    _, conn, bucket = run('backfill')
    m = bucket.get_json('manifest/BBCA.json')
    m['datasets']['events']['files']['all']['stamp'] = 'rows=1;last=2026-03-10;ing=ing'   # a stamp from format 1
    bucket.put('manifest/BBCA.json', json.dumps(m).encode(), 'application/json')
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    assert [t for _, t, _, _ in p2.changed_events({'BBCA': 'stock'})] == ['BBCA']


def test_broker_is_published_from_its_first_stored_year():
    conn = FakeConn(PRICES, BROKERS + [('BBCA', '2016-01-04', 'AK', 'Foreign', 'Regular', 1.0, 0.0, 0.01, 0.0, False, 1, 0)],
                    UNIVERSE)
    _, _, bucket = run('backfill', conn)
    assert key_of(bucket, 'BBCA', 'broker', 2016) in bucket.objects
    ds = bucket.get_json('manifest/BBCA.json')['datasets']['broker']
    assert ds['first_year'] == 2016 and '2016' in ds['files']


def test_run_times_skip_only_the_unlisted_cron_ticks():
    times = pub.run_times('07:30,19:00')
    # 00:30 and 12:00 UTC are 07:30 and 19:00 WIB; 01:00 and 12:30 UTC (08:00 and 19:30 WIB) are their check times
    # (EXEC-PUBLISHER-SPEED, ERRORS M303), so hour 1 joins the product
    assert pub.check_times(times) == [(8, 0), (19, 30)]
    assert pub.cron_for(times) == '0,30 0,1,12 * * *'
    at = lambda h, m: dt.datetime(2026, 10, 26, h, m, tzinfo=dt.timezone.utc)
    assert pub.should_run(times, at(0, 31)) and pub.should_run(times, at(12, 2))      # listed times
    assert not pub.should_run(times, at(0, 1)) and not pub.should_run(times, at(12, 31))  # 07:00 and 19:30 WIB
    assert not pub.should_run(times, at(1, 1)) and not pub.should_run(times, at(1, 31))   # 08:00 and 08:30 WIB
    assert pub.should_run(times, at(5, 0))                             # a deploy or manual run away from every tick
    assert pub.should_run([], at(0, 1))                                # no list: always runs


# ---- EXEC-TERMINAL-LOGO ------------------------------------------------------------------------------------------
PNG = b'\x89PNG\r\n\x1a\n' + b'x' * 50
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="4"/></svg>'


def fake_get(stockbit=('BBCA',), tradingview=None, scan=None):
    """Stockbit has the tickers in `stockbit`; TradingView's scanner gives `scan` logoids and serves their SVG."""
    def get(url, data=None, timeout=30):
        if url == pub.TRADINGVIEW_SCAN:
            return 'application/json', json.dumps({'data': [{'s': f'IDX:{t}', 'd': [t, i]} for t, i in (scan or {}).items()]}).encode()
        if 'stockbit' in url:
            t = url.rsplit('/', 1)[1].split('.')[0]
            if t in stockbit:
                return 'image/png', PNG + t.encode()
            raise pub.urllib.error.HTTPError(url, 404, 'nf', {}, None)
        if 'tradingview' in url and tradingview:
            return 'image/svg+xml', SVG
        raise pub.urllib.error.URLError('offline')
    return get


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """No test reaches the network: the default logo fetch answers 'offline'."""
    monkeypatch.setattr(pub, 'fetch', fake_get(stockbit=()))


WAITS, AT_WAIT = [], []


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    """delete_replaced's wait is recorded, not slept (WAITS); a test sees the bucket during it through AT_WAIT."""
    WAITS.clear(); AT_WAIT.clear()
    monkeypatch.setattr(pub, 'wait', lambda seconds: (WAITS.append(seconds), [f() for f in AT_WAIT]))


def during_wait(bucket):
    """The bucket's objects at the moment of delete_replaced's wait (state.json written, nothing deleted yet)."""
    seen = []
    AT_WAIT.append(lambda: seen.append(dict(bucket.objects)))
    return seen


def test_logo_comes_from_stockbit_then_tradingview_and_a_page_is_not_an_image():
    assert pub.logo_image('BBCA', None, fake_get())[1:] == ('png', 'stockbit')
    assert pub.logo_image('IHSG', 'composite', fake_get(tradingview=True))[1:] == ('svg', 'tradingview')
    assert pub.logo_image('IHSG', None, fake_get()) is None
    html = lambda url, data=None, timeout=30: ('text/html', b'<html>not found</html>')
    assert pub.logo_image('BBCA', 'x', html) is None


def test_logos_mode_uploads_changed_images_only_and_writes_the_index():
    bucket = FakeBucket()
    p = pub.Publisher(FakeConn(PRICES, BROKERS, UNIVERSE), bucket, today=TODAY, get=fake_get(scan={'IHSG': 'composite'}, tradingview=True))
    p.run('logos')
    assert bucket.objects['logo/BBCA.png'].startswith(PNG) and bucket.objects['logo/IHSG.svg'] == SVG
    index = bucket.get_json('ref/logos.json.gz')
    assert index['ticker'] == ['BBCA', 'IHSG'] and index['source'] == ['stockbit', 'tradingview'] and index['generated_at']
    puts = []
    bucket.put = lambda key, body, ctype: (puts.append(key), FakeBucket.put(bucket, key, body, ctype))
    p.run('logos')
    assert [k for k in puts if k.startswith('logo/')] == []                 # nothing changed: no image uploaded again


def test_daily_refreshes_logos_only_when_the_index_is_older_than_a_week():
    bucket = FakeBucket()
    p = pub.Publisher(FakeConn(PRICES, BROKERS, UNIVERSE), bucket, today=TODAY, get=fake_get())
    p.run('daily')
    assert 'logo/BBCA.png' in bucket.objects
    first = bucket.get_json('ref/logos.json.gz')['generated_at']
    p.run('daily')
    assert bucket.get_json('ref/logos.json.gz')['generated_at'] == first    # fresh: not fetched again
    assert p.logos_stale(dt.datetime.fromisoformat(first) + dt.timedelta(days=8))


# ---- EXEC-TERMINAL-SPEED -----------------------------------------------------------------------------------------
def test_packs_hold_every_price_year_and_the_broker_years_before_the_last_two():
    p, conn, bucket = run('backfill')
    m = bucket.get_json('manifest/BBCA.json')
    price = doc_of(bucket, 'BBCA', 'pack', 'price')
    assert price['d'] == sorted(r[1] for r in PRICES if r[0] == 'BBCA') and m['packs']['price']['sha256']
    assert 'broker-archive' not in m['packs']                        # no broker row before 2025 in the fixture
    assert 'broker-archive' not in bucket.get_json('manifest/IHSG.json').get('packs', {})


def test_an_old_broker_year_rebuilds_the_archive_and_daily_leaves_it_otherwise():
    _, conn, bucket = run('backfill')
    conn.brokers = BROKERS + [('BBCA', '2022-03-01', 'YU', 'Domestic', 'Regular', 5.0, 1.0, 0.5, 0.1, False, 1, 0)]
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('broker-range', '2022-01-01', '2022-12-31')
    m = bucket.get_json('manifest/BBCA.json')
    assert m['packs']['broker-archive']['years'] == [2021, 2024] and m['packs']['broker-archive']['rows'] == 1
    assert doc_of(bucket, 'BBCA', 'pack', 'broker-archive')['d'] == ['2022-03-01']
    p3 = pub.Publisher(conn, bucket, today=TODAY)
    p3.run('daily')
    assert not any(k == 'pack' for k, _, _ in p3.changed)              # nothing changed: no pack rewritten


def test_packs_mode_builds_missing_packs_without_rewriting_existing_ones():
    _, conn, bucket = run('backfill')
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('packs')
    assert p2.written == 0
    del bucket.objects[key_of(bucket, 'BBCA', 'pack', 'price')]
    m = bucket.get_json('manifest/BBCA.json'); m.pop('packs'); bucket.objects['manifest/BBCA.json'] = json.dumps(m).encode()
    p3 = pub.Publisher(conn, bucket, today=TODAY)
    p3.run('packs')
    assert key_of(bucket, 'BBCA', 'pack', 'price') in bucket.objects and p3.written == 1


def test_state_counts_the_price_sessions_without_broker_data():
    """EXEC-TERMINAL-FRESH (user 2026-10-27): state.json says how many final price sessions have no broker data yet."""
    prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0),
                       ('BBCA', '2026-01-06', 101.0, 104.0, 100.0, 103.0, 700.0)]
    conn = FakeConn(prices, BROKERS, UNIVERSE); bucket = FakeBucket()
    p = pub.Publisher(conn, bucket, today=TODAY); p.run('daily')
    assert p.broker_behind == 2 and bucket.get_json('state.json')['broker_behind_sessions'] == 2


def test_the_evening_warning_time_is_the_listed_wib_time_with_slack(monkeypatch):
    calls = []
    monkeypatch.setattr(pub, 'notify_broker_behind', lambda day: calls.append(day))
    times = pub.run_times('19:00')
    assert pub.near_time(times, dt.datetime(2026, 10, 27, 12, 5, tzinfo=dt.timezone.utc))          # 19:05 WIB
    assert not pub.near_time(times, dt.datetime(2026, 10, 27, 0, 35, tzinfo=dt.timezone.utc))      # 07:35 WIB



# ---- EXEC-SCREENER: cross-sectional files (report 6.5, 7.1) ---------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]


def xsection(bucket, name):
    """The state.json index entry of an xsection file, and its document."""
    entry = bucket.get_json('state.json')['xsection'][name]
    return entry, bucket.get_json(entry['key'][len('v1/'):])


def xsection_puts(bucket, since=0):
    return [k for k in bucket.puts[since:] if k.startswith('xsection/')]


def test_each_ticker_slice_of_the_price_file_equals_its_price_pack():
    _, _, bucket = run('backfill')
    entry, doc = xsection(bucket, 'price')
    assert doc['columns'] == ['t', 'd', 'o', 'h', 'l', 'c', 'v'] and doc['dataset'] == 'xsection'
    # every published ticker with rows, ordered by ticker then date although the statement returns them newest first
    assert doc['t'] == ['BBCA', 'BBCA', 'IHSG'] and doc['d'] == ['2025-12-30', '2026-01-02', '2026-01-02']
    assert doc['v'] == [1000.0, 900.0, None]                                    # an index keeps its null volume
    slices = dict(pub.xsection_slices(doc))
    assert sorted(slices) == ['BBCA', 'IHSG']
    for e in doc['tickers']:
        t = e['t']
        pack_bytes = bucket.objects[key_of(bucket, t, 'pack', 'price')]
        assert pub.price_pack_doc(t, slices[t]) == doc_of(bucket, t, 'pack', 'price')
        assert pub.encode(pub.price_pack_doc(t, slices[t]))[0] == pack_bytes                 # byte for byte
        assert (e['pack_sha256'] == hashlib.sha256(pack_bytes).hexdigest()
                == bucket.get_json(f'manifest/{t}.json')['packs']['price']['sha256'])
        assert (e['rows'], e['first'], e['last']) == (len(slices[t]), slices[t][0][0], slices[t][-1][0])
    assert entry['rows'] == 3 and entry['as_of'] == '2026-01-02'


def test_a_pack_that_differs_from_the_table_is_republished_from_the_slice():
    _, conn, bucket = run('backfill')
    pub.Publisher(conn, bucket, today=TODAY).run('daily')                 # the manifests now hold the daily stamps
    # an open corrected without changing the stamp (rows, last date, sum of closes): daily plans no file and no pack
    conn.prices = [('BBCA', '2025-12-30', 99.0, 110.0, 95.0, 105.0, 1000.0)] + PRICES[1:]
    old = key_of(bucket, 'BBCA', 'pack', 'price')
    old_bytes = bucket.objects[old]
    seen = during_wait(bucket)
    p3 = pub.Publisher(conn, bucket, today=TODAY)
    p3.run('daily')
    assert ('price', 'BBCA', 2025) not in p3.changed and ('pack', 'BBCA', 'price') in p3.changed
    assert doc_of(bucket, 'BBCA', 'pack', 'price')['o'][0] == 99.0
    assert key_of(bucket, 'BBCA', 'pack', 'price') != old and seen[0][old] == old_bytes   # a new object (M250)
    assert old in p3.replaced and old not in bucket.objects                # replaced: gone after the wait
    entry, doc = xsection(bucket, 'price')
    sha = bucket.get_json('manifest/BBCA.json')['packs']['price']['sha256']                  # the manifest was saved
    assert (sha == hashlib.sha256(bucket.objects[key_of(bucket, 'BBCA', 'pack', 'price')]).hexdigest()
            == doc['tickers'][0]['pack_sha256'])
    assert doc['o'][0] == 99.0 and pub.verify(conn, bucket) == 0


def test_the_xsection_files_are_written_before_the_state_json_that_indexes_them():
    _, conn, bucket = run('backfill')
    state = bucket.get_json('state.json')
    # EXEC-SCREENER-FLOW-CANDLES P4: the broker day file of the fixture's one trade date is indexed beside them
    assert sorted(state['xsection']) == ['actions', 'broker-2026-01-02', 'price'] and bucket.puts[-1] == 'state.json'
    for name, e in state['xsection'].items():
        key = e['key'][len('v1/'):]
        assert re.fullmatch(rf'xsection/{name}\.{e["sha256"][:16]}\.json\.gz', key)          # content-addressed
        assert key in bucket.puts[:-1]                                                        # before state.json
        body = bucket.objects[key]
        assert (len(body), hashlib.sha256(body).hexdigest()) == (e['bytes'], e['sha256'])
        doc = bucket.get_json(key)
        assert e['rows'] == len(doc[doc['columns'][0]])                                       # t, or b for a broker day
    # a later run: the new object is put before that run's state.json
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    n = len(bucket.puts)
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    new = xsection_puts(bucket, n)
    assert len(new) == 1 and new[0].startswith('xsection/price.') and bucket.puts[-1] == 'state.json'
    assert bucket.get_json('state.json')['xsection']['price']['key'] == f'v1/{new[0]}'


def test_terminal_api_reads_the_index_as_written():
    """The reader of the index (terminal-api bucket.py xsection_index, /state and /xsection) keeps every entry, and the
    publisher keeps (carries forward, protects from pruning) exactly the entries terminal-api serves."""
    spec = importlib.util.spec_from_file_location('terminal_api_bucket', ROOT / 'apps/terminal-api/app/bucket.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    _, _, bucket = run('backfill')
    index = bucket.get_json('state.json')['xsection']
    assert reader.xsection_index(index) == index == pub.xsection_entries(index)
    good = index['price']
    own = lambda name, hexes=good['sha256'][:16]: f'v1/xsection/{name}.{hexes}.json.gz'
    raw = {**index, 'stamped': {**good, 'key': own('stamped'), 'stamp': 'x', 'as_of': 'y' * 65},
           'Price': good, 'other': good, 'a': {**good, 'key': own('a', 'g' * 16)}, 'b': {**good, 'key': 'v1/manifest/b.json'},
           'c': {**good, 'key': own('c', 'a' * 16), 'sha256': 'A' * 64}, 'd': {**good, 'key': own('d'), 'bytes': 0},
           'e': {**good, 'key': own('e'), 'bytes': True}, 'f': {**good, 'key': own('f'), 'rows': -1},
           'g': {**good, 'key': own('g'), 'rows': '5'}, 'h': 'v1/xsection/h.json.gz',
           'i': {**good, 'key': own('i', '0' * 16)}, 'j': {**good, 'key': own('j')[3:]}}
    assert pub.xsection_entries(raw) == reader.xsection_index(raw)
    assert sorted(pub.xsection_entries(raw)) == ['actions', 'broker-2026-01-02', 'price', 'stamped']


def test_modes_that_do_not_rebuild_an_xsection_file_carry_its_entry_forward():
    p, conn, bucket = run('backfill')
    before = bucket.get_json('state.json')['xsection']
    for mode, args in (('logos', ()), ('broker-range', ('2026-01-01', '2026-12-31'))):
        n = len(bucket.puts)
        pub.Publisher(conn, bucket, today=TODAY).run(mode, *args)
        assert bucket.get_json('state.json')['xsection'] == before and xsection_puts(bucket, n) == []
    # events rebuilds `actions` only; the price entry is carried as it is
    conn.actions.append(('BBCA', '2026-11-24', 'RIGHT_ISSUE', 4.0, 1.0, 1200.0, None, 'k6'))
    n = len(bucket.puts)
    p3 = pub.Publisher(conn, bucket, today=TODAY)
    p3.run('events')
    after = bucket.get_json('state.json')['xsection']
    assert after['price'] == before['price'] and after['actions']['key'] != before['actions']['key']
    assert [k.split('.')[0] for k in xsection_puts(bucket, n)] == ['xsection/actions']
    assert not any(s == pub.XSECTION_PRICE_SQL for s in conn.statements[-20:])


def test_pruning_keeps_the_objects_of_the_previous_index():
    """EXEC-PUBLISHER-SPEED: an xsection file the new index stops naming stays through the run and the wait after its
    state.json (a reader of the previous index keeps its file), then goes; other keys under xsection/ stay."""
    _, conn, bucket = run('backfill')
    k1 = xsection(bucket, 'price')[0]['key'][3:]
    actions = xsection(bucket, 'actions')[0]['key'][3:]
    bucket.objects['xsection/README.txt'] = b'not a file of the family'
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    seen = during_wait(bucket)
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    k2 = xsection(bucket, 'price')[0]['key'][3:]
    assert k2 != k1 and k1 in seen[0] and bucket.get_json('state.json')['xsection']['price']['key'] == f'v1/{k2}'
    assert k1 not in bucket.objects and {k2, actions, 'xsection/README.txt'} <= set(bucket.objects)
    pub.Publisher(conn, bucket, today=TODAY).run('logos')             # a carry-forward run replaces no xsection file
    assert {k2, actions} <= set(bucket.objects)


def test_an_indexed_object_missing_from_the_bucket_is_put_again():
    _, conn, bucket = run('backfill')
    key = xsection(bucket, 'price')[0]['key'][3:]
    body = bucket.objects.pop(key)                                    # deleted by hand: the index names a missing object
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert bucket.objects[key] == body and xsection(bucket, 'price')[0]['key'] == f'v1/{key}'


def test_a_bucket_that_cannot_list_or_delete_prunes_nothing_and_still_publishes(capsys):
    """Without listings the publication goes on and the replaced files still go by name; a bucket that refuses deletes
    keeps everything, and the run publishes."""
    _, conn, bucket = run('backfill')
    k1 = xsection(bucket, 'price')[0]['key'][3:]
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    bucket.list = lambda deadline=None, prefix='': (_ for _ in ()).throw(PermissionError())    # no ListObjectsV2
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run('daily')
    k2 = xsection(bucket, 'price')[0]['key'][3:]
    assert p.xsection_failed == [] and k2 in bucket.objects and k1 not in bucket.objects and bucket.puts[-1] == 'state.json'
    del bucket.list                                                   # listing works again, deleting does not
    bucket.delete = lambda keys: (_ for _ in ()).throw(PermissionError())
    conn.prices = conn.prices + [('BBCA', '2026-01-06', 101.0, 104.0, 100.0, 103.0, 700.0)]
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run('daily')
    k3 = xsection(bucket, 'price')[0]['key'][3:]
    assert p.xsection_failed == [] and {k2, k3} <= set(bucket.objects) and bucket.puts[-1] == 'state.json'
    assert '"replaced_failed"' in capsys.readouterr().out


def test_xsection_files_are_deterministic_and_never_rewritten():
    _, conn, bucket = run('backfill')
    _, _, other = run('backfill', conn=FakeConn(PRICES, BROKERS, UNIVERSE))
    for name in ('price', 'actions'):
        a, b = bucket.get_json('state.json')['xsection'][name], other.get_json('state.json')['xsection'][name]
        assert a == b and bucket.objects[a['key'][3:]] == other.objects[b['key'][3:]]
    n = len(bucket.puts)
    for mode in ('daily', 'packs', 'backfill'):
        pub.Publisher(conn, bucket, today=TODAY).run(mode)
    assert xsection_puts(bucket, n) == []                             # same content, same key: not put again


def test_the_actions_file_holds_share_count_changes_and_cash_dividends_on_their_ex_dates():
    p, _, bucket = run('backfill')
    entry, doc = xsection(bucket, 'actions')
    assert doc['columns'] == pub.ACTION_COLUMNS and entry['rows'] == 3
    assert doc['t'] == ['BBCA'] * 3 and doc['d'] == ['2026-03-10', '2026-10-14', '2026-11-03']   # future ex date kept
    assert doc['type'] == ['DIVIDEND', 'STOCK_SPLIT', 'DIVIDEND']
    assert (doc['ratio_old'], doc['ratio_new']) == ([None, 1.0, None], [None, 5.0, None])
    assert doc['amount_per_share'] == [250.0, None, None] and doc['currency'] == ['IDR', None, 'IDR']   # 0 -> null
    # read from the first published price year (2021 here): the 2012 split is not read; GONE is not published
    assert entry['as_of'] == '2026-10-25 17:04:28+00'
    assert p.price_first_year == 2021


def test_price_action_types_are_the_backtest_cores():
    src = (ROOT / 'apps/edge-bff/backtest/src/core/datafile.ts').read_text()
    m = re.search(r'export const PRICE_ACTION_TYPES: readonly string\[\] = \[([^\]]*)\]', src)
    assert m and tuple(re.findall(r"'([A-Z_]+)'", m.group(1))) == pub.PRICE_ACTION_TYPES
    assert pub.ACTION_TYPES == pub.PRICE_ACTION_TYPES + ('DIVIDEND',)


def test_a_failed_xsection_file_keeps_its_entry_and_the_rest_is_published():
    _, conn, bucket = run('backfill')
    before = bucket.get_json('state.json')
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    conn.actions.append(('BBCA', '2026-11-24', 'RIGHT_ISSUE', 4.0, 1.0, 1200.0, None, 'k6'))
    rows = conn._rows
    conn._rows = lambda sql, params: (_ for _ in ()).throw(TimeoutError()) if sql == pub.XSECTION_PRICE_SQL else rows(sql, params)
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('daily')
    after = bucket.get_json('state.json')
    assert p2.xsection_failed == ['price'] and after['finished_at'] != before['finished_at']
    assert after['xsection']['price'] == before['xsection']['price']              # the previous file stays indexed
    assert after['xsection']['actions'] != before['xsection']['actions']          # the other file was rebuilt
    assert bucket.get_json('manifest/BBCA.json')['datasets']['price']['files']['2026']['rows'] == 2   # Terminal files


def test_verify_checks_the_xsection_files():
    _, conn, bucket = run('backfill')
    assert pub.verify(conn, bucket) == 0
    conn.actions.append(('BBCA', '2026-11-24', 'RIGHT_ISSUE', 4.0, 1.0, 1200.0, None, 'k6'))
    assert pub.verify(conn, bucket) == 1                                          # actions differ from SQL now
    conn.actions.pop()
    key = xsection(bucket, 'price')[0]['key'][3:]
    bucket.objects[key] = gzip.compress(b'{}')
    assert pub.verify(conn, bucket) == 1                                          # not the indexed bytes


def test_an_index_entry_that_is_not_an_xsection_object_is_neither_carried_nor_protected():
    _, conn, bucket = run('backfill')
    state = bucket.get_json('state.json')
    state['xsection']['evil'] = {'key': 'v1/manifest/BBCA.json', 'sha256': 'ab' * 32, 'bytes': 1, 'rows': 0}
    bucket.put('state.json', json.dumps(state).encode(), 'application/json')
    pub.Publisher(conn, bucket, today=TODAY).run('logos')
    assert sorted(bucket.get_json('state.json')['xsection']) == ['actions', 'broker-2026-01-02', 'price']
    assert 'manifest/BBCA.json' in bucket.objects


# ---- content keys and collect_garbage (ERRORS M250) ---------------------------------------------------------------
HOUR = dt.timedelta(hours=1)


def at(bucket, conn, mode, hours, *args):
    """Run `mode` with the bucket's clock moved `hours` after the fixture's start (the publisher's clock follows it)."""
    bucket.clock = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc) + hours * HOUR
    p = pub.Publisher(conn, bucket, today=TODAY, clock=lambda: bucket.clock)
    p.run(mode, *args)
    return p


def named(bucket):
    return {k for t in ('BBCA', 'IHSG') for k in pub.named_keys(bucket.get_json(f'manifest/{t}.json'))}


def indexed(bucket):
    """The xsection keys (without v1/) the state.json index names (EXEC-SCREENER)."""
    return {e['key'][len(pub.PREFIX) + 1:] for e in pub.xsection_entries(bucket.get_json('state.json')['xsection']).values()}


def events(capsys, name):
    return [e for e in map(json.loads, capsys.readouterr().out.splitlines()) if e['event'] == name]


def test_every_data_file_and_pack_is_named_by_the_sha256_of_its_bytes():
    _, _, bucket = run('backfill')
    keys = named(bucket)
    assert {k.split('/')[0] for k in keys} == {'price', 'broker', 'events', 'pack'}
    for key in keys:
        family, ticker, file = key.split('/')
        name, sha, ext = file.split('.', 2)
        assert ext == 'json.gz' and sha == pub.hashlib.sha256(bucket.objects[key]).hexdigest()
        assert key == pub.content_key(family, ticker, name, sha)


def test_a_changed_file_is_a_new_object_and_the_bytes_the_old_manifest_names_stay_through_the_wait():
    """M250: during a run, and through the wait after its state.json, a reader holding the previous manifest still
    downloads exactly the bytes it names; then exactly the replaced objects go (EXEC-PUBLISHER-SPEED)."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    old = {k: bucket.objects[k] for k in named(bucket) | indexed(bucket)}     # the manifests' and the index's objects
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    conn.brokers = BROKERS + [('BBCA', '2026-01-05', 'AK', 'Foreign', 'Regular', 10.0, 0.0, 0.1, 0.0, False, 1, 0)]
    conn.events = EVENTS + [('BBCA', '2026-06-01', 'EX_DATE', 'CORPORATE_ACTION', 'DIVIDEND') + (None,) * 9 +
                            (5.0, None, None, None, {}, None, None)]
    seen = during_wait(bucket)
    p = at(bucket, conn, 'daily', 2)
    replaced = set(old) - named(bucket) - indexed(bucket)
    # every family changed; the xsection `price` file too (`actions` reads ACTIONS, unchanged here)
    assert {k.split('/')[0] for k in replaced} == {'price', 'broker', 'events', 'pack', 'xsection'}
    assert [k for k in replaced if k.startswith('xsection/')][0].startswith('xsection/price.')
    assert p.written == len(replaced) and WAITS == [pub.DELETE_AFTER_SECONDS]
    assert seen[0]['state.json'] == bucket.objects['state.json']          # the wait came after the switch
    assert all(seen[0][k] == body for k, body in old.items())             # nothing the old manifest names was touched
    assert set(p.replaced) == replaced and not replaced & set(bucket.objects)
    assert named(bucket) | indexed(bucket) <= set(bucket.objects) and pub.verify(conn, bucket) == 0


def test_an_unchanged_file_keeps_its_fixed_key_from_before_content_keys_and_a_change_retires_it():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    m = bucket.get_json('manifest/BBCA.json')
    entry = m['datasets']['price']['files']['2026']
    legacy = 'price/BBCA/2026.json.gz'
    bucket.objects[legacy] = bucket.objects.pop(entry['key'][len(pub.PREFIX) + 1:])
    bucket.modified[legacy] = bucket.modified['state.json']
    entry['key'] = f'{pub.PREFIX}/{legacy}'
    bucket.objects['manifest/BBCA.json'] = json.dumps(m).encode()
    p = at(bucket, conn, 'daily', 2)
    assert p.written == 0 and key_of(bucket, 'BBCA', 'price', 2026) == legacy and legacy in bucket.objects
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    seen = during_wait(bucket)
    p = at(bucket, conn, 'daily', 4)
    assert key_of(bucket, 'BBCA', 'price', 2026) != legacy and legacy in seen[0]      # kept through the wait
    assert legacy in p.replaced and legacy not in bucket.objects                       # then retired by name


def plant(bucket, key, hours):
    bucket.objects[key] = b'old'
    bucket.modified[key] = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc) + hours * HOUR


def test_gc_waits_for_the_grace_after_the_last_finished_run(capsys):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    plant(bucket, 'price/BBCA/2019.json.gz', -24)
    at(bucket, conn, 'daily', 0.5)                                         # 30 minutes after the backfill finished
    assert 'price/BBCA/2019.json.gz' in bucket.objects and not bucket.deleted
    assert events(capsys, 'gc_skipped')[0]['grace'] == pub.GC_GRACE_SECONDS
    at(bucket, conn, 'daily', 1.2)                                         # the daily run at 0.5 h finished at 0.5 h
    assert 'price/BBCA/2019.json.gz' in bucket.objects
    at(bucket, conn, 'daily', 2.5)
    assert 'price/BBCA/2019.json.gz' not in bucket.objects


def test_gc_keeps_what_an_unfinished_run_may_own_and_what_no_manifest_covers(capsys):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    finished = bucket.modified['state.json']
    plant(bucket, 'price/IHSG/2019.json.gz', -24)          # orphan of a ticker whose manifest is current: deleted
    plant(bucket, 'price/IHSG/2020.abc.json.gz', 1)        # written after the last finished run: kept
    plant(bucket, 'price/BBCA/2019.json.gz', -24)          # ticker whose manifest is newer than state.json: kept
    bucket.modified['manifest/BBCA.json'] = finished + dt.timedelta(seconds=1)
    plant(bucket, 'price/NEWT/2026.abc.json.gz', -24)      # ticker without a manifest: kept
    plant(bucket, 'logo/IHSG.png', -24)                    # logos, refs, manifests, state and other families: kept
    plant(bucket, 'ref/old.json.gz', -24)
    plant(bucket, '_probe/IHSG/x.json.gz', -24)
    bucket.clock = finished + 2 * HOUR
    p = pub.Publisher(conn, bucket, today=TODAY, clock=lambda: bucket.clock)
    assert p.collect_garbage() == 1 and bucket.deleted == ['price/IHSG/2019.json.gz']
    gc = events(capsys, 'gc')[0]
    assert gc['kept_newer_than_last_run'] == 1 and gc['tickers_skipped'] == 1
    assert gc['families'] == ['pack', 'price']                            # IHSG's (BBCA's manifest is skipped)
    assert named(bucket) <= set(bucket.objects)


def test_gc_families_come_from_the_manifests_so_a_new_dataset_is_covered():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    m = bucket.get_json('manifest/IHSG.json')
    m['datasets']['macro'] = {'files': {'2026': {'key': f'{pub.PREFIX}/macro/IHSG/2026.abc.json.gz', 'sha256': 'abc'}}}
    bucket.objects['manifest/IHSG.json'] = json.dumps(m).encode()
    bucket.modified['manifest/IHSG.json'] = bucket.modified['state.json']
    plant(bucket, 'macro/IHSG/2026.abc.json.gz', -24)
    plant(bucket, 'macro/IHSG/2025.old.json.gz', -24)
    bucket.clock += 2 * HOUR
    pub.Publisher(conn, bucket, today=TODAY, clock=lambda: bucket.clock).collect_garbage()
    assert bucket.deleted == ['macro/IHSG/2025.old.json.gz'] and 'macro/IHSG/2026.abc.json.gz' in bucket.objects


@pytest.mark.parametrize('mode,args', [('backfill', ()), ('packs', ()), ('events', ()), ('logos', ()),
                                       ('broker-range', ('2026-01-01', '2026-12-31'))])
def test_only_a_daily_run_collects_garbage(mode, args):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    plant(bucket, 'price/IHSG/2019.json.gz', -24)
    p = pub.Publisher(conn, bucket, today=TODAY, clock=lambda: bucket.clock + 2 * HOUR, get=fake_get())
    p.run(mode, *args)
    assert 'price/IHSG/2019.json.gz' in bucket.objects and not bucket.deleted


def test_a_failed_cleanup_never_stops_the_run(capsys):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    plant(bucket, 'price/IHSG/2019.json.gz', -24)
    bucket.delete = lambda keys: list(keys)                               # the bucket refuses every delete
    at(bucket, conn, 'daily', 2)
    assert events(capsys, 'gc')[0]['not_deleted'] == 1
    bucket.list = lambda deadline=None, prefix='': (_ for _ in ()).throw(OSError('secret detail'))
    at(bucket, conn, 'daily', 4)
    out = capsys.readouterr().out
    assert '"gc_failed"' in out and 'OSError' in out and 'secret detail' not in out and '"done"' in out
    assert bucket.modified['state.json'] == bucket.clock                   # the run still finished


def test_a_bucket_listing_past_its_deadline_skips_the_cleanup_and_the_run_publishes(capsys, monkeypatch):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    plant(bucket, 'price/IHSG/2019.json.gz', -24)
    bucket.list = lambda deadline=None, prefix='': (_ for _ in ()).throw(TimeoutError('bucket listing took too long'))
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    p = at(bucket, conn, 'daily', 2)
    assert '"TimeoutError"' in capsys.readouterr().out and p.written > 0
    assert 'price/IHSG/2019.json.gz' in bucket.objects                    # the sweep needs a listing: skipped
    assert sorted(bucket.deleted) == p.replaced                           # the replaced files go by name


# ---- one mechanism for both: the xsection family under content keys and collect_garbage (M250 x EXEC-SCREENER) -------
def price_key(bucket):
    return xsection(bucket, 'price')[0]['key'][len(pub.PREFIX) + 1:]


def test_two_runs_minutes_apart_each_delete_what_they_replaced_after_their_own_wait(capsys):
    """A manual run right after a scheduled one: each run deletes what it replaced, after the wait that follows its own
    state.json (a reader of the index before it keeps its file until then); the sweep keeps its one-hour grace."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = price_key(bucket)
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    at(bucket, conn, 'daily', 2)
    k2 = price_key(bucket)
    conn.prices = conn.prices + [('BBCA', '2026-01-06', 101.0, 104.0, 100.0, 103.0, 700.0)]
    seen = during_wait(bucket)
    at(bucket, conn, 'daily', 2.25)                                       # 15 minutes after the last run finished
    k3 = price_key(bucket)
    assert len({k1, k2, k3}) == 3 and k2 in seen[0] and k1 not in seen[0]
    assert k3 in bucket.objects and not {k1, k2} & set(bucket.objects) and {k1, k2} <= set(bucket.deleted)
    assert events(capsys, 'gc_skipped')[0]['grace'] == pub.GC_GRACE_SECONDS


def test_the_xsection_cleanup_keeps_newer_objects_other_keys_and_everything_when_no_index_names_a_file(capsys):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    finished = bucket.modified['state.json']
    stale = f'xsection/price.{"b" * 16}.json.gz'
    plant(bucket, stale, -24)                                             # named by no index: deleted
    newer = f'xsection/price.{"a" * 16}.json.gz'
    plant(bucket, newer, 1)                                               # written by a run that did not finish: kept
    plant(bucket, 'xsection/notes.txt', -24)                              # not an xsection object: never deleted
    bucket.clock = finished + 2 * HOUR
    p = pub.Publisher(conn, bucket, today=TODAY, clock=lambda: bucket.clock)
    assert p.collect_garbage() == 1 and bucket.deleted == [stale]
    gc = events(capsys, 'gc')[0]
    assert gc['xsection_named'] == 3 and gc['kept_newer_than_last_run'] == 1        # price, actions, broker-2026-01-02
    assert indexed(bucket) | {newer, 'xsection/notes.txt'} <= set(bucket.objects)
    # a state.json without an index (a publisher before the xsection writer, or a rollback to one) names no xsection
    # file: no xsection object is deleted until an index names one again
    state = bucket.get_json('state.json')
    state.pop('xsection')
    bucket.objects['state.json'] = json.dumps(state).encode()             # same LastModified
    plant(bucket, stale, -24)
    assert p.collect_garbage() == 0 and stale in bucket.objects and bucket.deleted == [stale]


def test_content_that_returns_to_an_object_the_cleanup_deleted_is_put_again():
    """A key deleted after a run's wait is gone from the next run's xsection listing, so content that returns to it is
    put again, never taken as present."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = price_key(bucket)
    body = bucket.objects[k1]
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    at(bucket, conn, 'daily', 2)                                          # k1 replaced, deleted after the wait
    k2 = price_key(bucket)
    assert k1 in bucket.deleted and k1 not in bucket.objects
    conn.prices = PRICES                                                  # the change is undone: k1's content again
    at(bucket, conn, 'daily', 4)
    assert price_key(bucket) == k1 and bucket.objects[k1] == body and k2 not in bucket.objects
    assert named(bucket) | indexed(bucket) <= set(bucket.objects) and pub.verify(conn, bucket) == 0


def test_content_that_returns_to_an_object_still_in_the_bucket_is_not_put_again():
    """A replaced key the bucket kept (its delete refused) and whose content returns is indexed again, not put again."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = price_key(bucket)
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    bucket.delete = lambda keys: list(keys)                              # every delete refused: k1 stays
    at(bucket, conn, 'daily', 2)
    conn.prices = PRICES
    n = len(bucket.puts)
    at(bucket, conn, 'daily', 2.5)
    assert price_key(bucket) == k1 and xsection_puts(bucket, n) == [] and k1 in bucket.objects


def test_the_cleanup_lists_each_folder_and_the_indexed_files_their_prefix_only():
    """The xsection and the content-keyed reference listings ask for `xsection/` and `ref/` only. A daily run first
    lists `state.json` and `manifest/` (the sweep's baseline, before its first write); the sweep, after state.json and
    the replaced files' deletion, lists `manifest/` and `state.json`, then each family folder (ERRORS M301)."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    asked, whole = [], bucket.list
    bucket.list = lambda deadline=None, prefix='': asked.append((prefix, len(bucket.puts))) or whole(deadline, prefix)
    n = len(bucket.puts)
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    at(bucket, conn, 'daily', 2)
    prefixes = [p for p, _ in asked]
    assert prefixes[:4] == ['state.json', 'manifest/', 'xsection/', 'ref/'] and asked[0][1] == asked[1][1] == n
    assert prefixes[4:6] == ['manifest/', 'state.json']
    # EXEC-RADAR R5: the Radar's indexed family is swept like the others
    assert sorted(prefixes[6:]) == ['broker/', 'events/', 'pack/', 'price/', 'radar/', 'ref/', 'xsection/'] and '' not in prefixes
    assert all(at_put == len(bucket.puts) for _, at_put in asked[4:]) and bucket.puts[-1] == 'state.json'

# ---- bucket retries (ERRORS M263; M253 on PR #41's branch) ----------------------------------------------------------
def client_error(code):
    from botocore.exceptions import ClientError
    return ClientError({'Error': {'Code': code, 'Message': 'x'}}, 'GetObject')


@pytest.mark.parametrize('error', ['RequestCanceled', 'SlowDown', '503', 'connection'])
def test_a_transient_bucket_error_is_asked_again(error):
    from botocore.exceptions import EndpointConnectionError
    calls, waits = [], []
    def call():
        calls.append(1)
        if len(calls) < 3:
            raise EndpointConnectionError(endpoint_url='https://bucket') if error == 'connection' else client_error(error)
        return 'body'
    assert pub.retried(call, sleep=waits.append) == 'body' and waits == [2, 4]


def test_a_lasting_or_other_bucket_error_still_ends_the_run():
    waits = []
    with pytest.raises(Exception) as e:
        pub.retried(lambda: (_ for _ in ()).throw(client_error('RequestCanceled')), sleep=waits.append)
    assert e.value.response['Error']['Code'] == 'RequestCanceled' and waits == list(pub.BUCKET_RETRY_DELAYS)
    waits.clear()
    with pytest.raises(Exception) as e:
        pub.retried(lambda: (_ for _ in ()).throw(client_error('AccessDenied')), sleep=waits.append)
    assert e.value.response['Error']['Code'] == 'AccessDenied' and waits == []


def test_the_bucket_listing_follows_every_page_and_asks_a_canceled_page_again(monkeypatch):
    monkeypatch.setattr(pub.time, 'sleep', lambda s: None)
    at = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc)
    pages = {None: {'IsTruncated': True, 'NextContinuationToken': 't1', 'Contents': [{'Key': 'v1/a', 'LastModified': at, 'Size': 1}]},
             't1': {'IsTruncated': False, 'Contents': [{'Key': 'v1/b', 'LastModified': at, 'Size': 2}]}}
    asked = []
    class S3:
        def list_objects_v2(self, **kw):
            asked.append(kw.get('ContinuationToken'))
            if asked.count('t1') == 1 and kw.get('ContinuationToken') == 't1':
                raise client_error('RequestCanceled')
            return pages[kw.get('ContinuationToken')]
    b = pub.Bucket.__new__(pub.Bucket)
    b.name, b.s3 = 'bucket', S3()
    assert b.list() == {'a': (at, 1), 'b': (at, 2)} and asked == [None, 't1', 't1']


def test_the_xsection_listing_asks_the_bucket_for_its_prefix_only():
    at = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc)
    asked = []
    class S3:
        def list_objects_v2(self, **kw):
            asked.append(kw['Prefix'])
            return {'IsTruncated': False, 'Contents': [{'Key': 'v1/xsection/price.0123456789abcdef.json.gz',
                                                        'LastModified': at, 'Size': 3}]}
    b = pub.Bucket.__new__(pub.Bucket)
    b.name, b.s3 = 'bucket', S3()
    assert b.list(prefix='xsection/') == {'xsection/price.0123456789abcdef.json.gz': (at, 3)} and asked == ['v1/xsection/']
    b.list()
    assert asked[-1] == 'v1/'


def test_every_bucket_call_is_asked_again_after_a_canceled_answer(monkeypatch):
    """ERRORS M263: put, get and delete go through `retried` as the listing does; a missing object is None at once."""
    monkeypatch.setattr(pub.time, 'sleep', lambda s: None)
    from botocore.exceptions import ClientError
    class NoSuchKey(ClientError):
        pass
    calls = []
    class S3:
        exceptions = type('Exceptions', (), {'NoSuchKey': NoSuchKey})
        def once(self, op):
            calls.append(op)
            if calls.count(op) == 1:
                raise client_error('RequestCanceled')
        def put_object(self, **kw):
            self.once('put')
        def get_object(self, Bucket, Key):
            if Key == 'v1/manifest/NONE.json':
                calls.append('missing')
                raise NoSuchKey({'Error': {'Code': 'NoSuchKey', 'Message': 'x'}}, 'GetObject')
            self.once('get')
            return {'Body': type('Body', (), {'read': lambda self: b'{"a": 1}'})()}
        def delete_objects(self, Bucket, Delete):
            self.once('delete')
            return {}
    b = pub.Bucket.__new__(pub.Bucket)
    b.name, b.s3 = 'bucket', S3()
    b.put('state.json', b'{}', 'application/json')
    assert b.get_json('state.json') == {'a': 1} and b.get_raw('manifest/NONE.json') is None
    assert b.delete(['price/BBCA/2026.json.gz']) == []
    assert calls == ['put', 'put', 'get', 'get', 'missing', 'delete', 'delete']


# ---- EXEC-MU-RUNTIME T5: reference files under content keys, listed in state.json `refs` ----------------------------
FIXED_REFS = {f'ref/{n}.json.gz' for n in pub.REF_NAMES}
# sha256 of the JSON inside ref/tickers.json.gz and ref/brokers.json.gz as the publisher before T5 (3f5156c) wrote them
# for this file's fixture: the fixed-key copies must stay byte for byte what the deployed readers already read.
# ref/brokers changed on purpose with EXEC-TERMINAL-FLOW-IND (user go 2026-10-30): the added `classification` column
# (before: a4075aee964c309e...); every reader takes its columns by name (backtest-worker terminal.ts reference,
# terminal live.ts), so the pin now holds the new bytes.
# tickers: EXEC-UNIVERSE-BROKER S1.4 (2026-11-05) added the column instrument; the bytes before it were 9c49504a...
BEFORE_T5_RAW_SHA256 = {'tickers': '176173761088fb67313a286f7e219a28ce67207c7143fad184802af5135796b7',
                        'brokers': '3b54f0d4cc28389f05abfaeefdd10dc05de0bf01211298542292edb277840afc'}


def refs(bucket):
    return bucket.get_json('state.json')['refs']


def ref_puts(bucket, since=0):
    """The content-keyed reference objects put since `since` (the fixed-key copies are not content-keyed)."""
    return [k for k in bucket.puts[since:] if pub.REF_KEY.fullmatch(k)]


def renamed(name):
    """The fixture universe with BBCA's company name changed: only ref/tickers changes."""
    return [(UNIVERSE[0][0], name) + UNIVERSE[0][2:]] + UNIVERSE[1:]


def test_every_reference_file_is_also_stored_under_its_content_key_and_listed_in_state_json():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    at(bucket, conn, 'logos', 1)                                           # the logo index exists from now on
    index = refs(bucket)
    assert sorted(index) == sorted(pub.REF_NAMES) and pub.ref_entries(index) == index    # exactly the well-formed shape
    for name, e in index.items():
        assert set(e) == {'key', 'sha256', 'bytes', 'rows'}
        key = e['key'][len(pub.PREFIX) + 1:]
        assert key == f'ref/{name}.{e["sha256"][:16]}.json.gz' and pub.REF_KEY.fullmatch(key)     # content-addressed
        body = bucket.objects[key]
        assert (len(body), hashlib.sha256(body).hexdigest()) == (e['bytes'], e['sha256'])
        assert body == bucket.objects[f'ref/{name}.json.gz']               # the fixed-key copy's exact bytes
        doc = bucket.get_json(key)
        assert e['rows'] == len(doc[doc['columns'][0]])
    assert index['tickers']['rows'] == len(UNIVERSE) and index['brokers']['rows'] == 2 and index['logos']['rows'] == 0


def test_equal_reference_bytes_give_the_same_key_and_are_never_put_again():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    first = refs(bucket)
    _, _, other = run('backfill', conn=FakeConn(PRICES, BROKERS, UNIVERSE))           # another bucket, same rows
    assert refs(other) == first
    n = len(bucket.puts)
    for i, (mode, args) in enumerate((('backfill', ()), ('packs', ()), ('events', ()),
                                      ('broker-range', ('2026-01-01', '2026-12-31')))):
        at(bucket, conn, mode, 0.1 * (i + 1), *args)
        assert {k: refs(bucket)[k] for k in first} == first
    assert ref_puts(bucket, n) == []                                       # same content, same key: not put again
    # a changed list is a new object, and the one it replaced goes after the wait; content that returns is put again
    conn.universe = renamed('Bank Central Asia Tbk')
    at(bucket, conn, 'daily', 2)
    changed = refs(bucket)['tickers']['key']
    assert changed != first['tickers']['key'] and refs(bucket)['brokers'] == first['brokers']
    assert first['tickers']['key'][3:] not in bucket.objects and first['brokers']['key'][3:] in bucket.objects
    conn.universe = UNIVERSE
    n = len(bucket.puts)
    at(bucket, conn, 'daily', 2.5)
    assert refs(bucket)['tickers'] == first['tickers'] and [k.split('.')[0] for k in ref_puts(bucket, n)] == ['ref/tickers']


def test_the_refs_index_is_written_after_its_objects_and_before_state_json():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    put, seen = bucket.put, []
    def checked(key, body, ctype):
        """Every state.json put names only reference objects the bucket already holds."""
        if key == 'state.json':
            named = {e['key'][3:] for e in json.loads(body).get('refs', {}).values()}
            assert named and named <= set(bucket.objects), named - set(bucket.objects)
            seen.append(named)
        put(key, body, ctype)
    bucket.put = checked
    at(bucket, conn, 'backfill', 0)
    assert len(seen) == 1
    assert bucket.puts[-1] == 'state.json'
    for e in refs(bucket).values():
        key = e['key'][len(pub.PREFIX) + 1:]
        assert key in bucket.puts[:-1]                                    # before state.json
        assert bucket.puts.index(key) > bucket.puts.index(f'ref/{key.split("/")[1].split(".")[0]}.json.gz')
    conn.universe = renamed('BCA')
    n = len(bucket.puts)
    at(bucket, conn, 'daily', 2)                                           # a later run: the new object first
    new = ref_puts(bucket, n)
    assert [k.split('.')[0] for k in new] == ['ref/tickers', 'ref/logos'] and bucket.puts[-1] == 'state.json'
    assert refs(bucket)['tickers']['key'] == f'v1/{new[0]}' and len(seen) == 2


@pytest.mark.parametrize('mode,args,logos', [('backfill', (), False), ('daily', (), True), ('logos', (), True),
                                             ('events', (), False), ('packs', (), False),
                                             ('broker-range', ('2026-01-01', '2026-12-31'), False)])
def test_fixed_key_reference_files_are_written_byte_identical_to_before(mode, args, logos):
    """The deployed readers (terminal-api REF_FILES and its logo index, the pages, both workers) open the fixed keys:
    each run still writes them, in the same order, with the same bytes as before the content-keyed copies."""
    bucket = FakeBucket()
    p = pub.Publisher(FakeConn(PRICES, BROKERS, UNIVERSE), bucket, today=TODAY, get=fake_get())
    p.run(mode, *args)
    fixed = [k for k in bucket.puts if k in FIXED_REFS]
    # EXEC-FI-TERMINAL: the bond list after the ticker and broker lists (empty here: the fixture has no bond)
    assert fixed == ['ref/tickers.json.gz', 'ref/brokers.json.gz', 'ref/stock_lists.json.gz', 'ref/fixed_income.json.gz'] + (['ref/logos.json.gz'] if logos else [])
    for name, sha in BEFORE_T5_RAW_SHA256.items():
        body = bucket.objects[f'ref/{name}.json.gz']
        raw = gzip.decompress(body)
        assert hashlib.sha256(raw).hexdigest() == sha and body == gzip.compress(raw, compresslevel=9, mtime=0)
    assert bucket.get_json('ref/tickers.json.gz')['columns'] == ['ticker', 'name', 'type', 'sector', 'industry', 'instrument']
    assert all(bucket.objects[e['key'][3:]] == bucket.objects[f'ref/{n}.json.gz'] for n, e in refs(bucket).items())


def test_ref_names_are_the_reference_files_terminal_api_serves():
    main = (ROOT / 'apps/terminal-api/app/main.py').read_text()
    m = re.search(r'^REF_FILES = (\{[^}]*\})', main, re.M)
    assert m and json.loads(m.group(1).replace("'", '"')) == {n: f'v1/{pub.ref_key(n)}' for n in pub.REF_NAMES}


def test_terminal_api_reads_the_refs_index_as_written():
    """Phase 1b gives terminal-api a refs_index validated like xsection_index; it must serve exactly the entries the
    publisher writes, carries and protects. Until 1b lands the reader is absent and the check is skipped."""
    spec = importlib.util.spec_from_file_location('terminal_api_bucket', ROOT / 'apps/terminal-api/app/bucket.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    if not hasattr(reader, 'refs_index'):
        pytest.skip('terminal-api bucket.refs_index is not built yet (EXEC-MU-RUNTIME Phase 1b)')
    _, _, bucket = run('backfill')
    index = refs(bucket)
    assert reader.refs_index(index) == index == pub.ref_entries(index)
    good = index['tickers']
    raw = {**index, 'Tickers': good, 'fixed': {**good, 'key': 'v1/ref/fixed.json.gz'},
           'x': {**good, 'key': f'v1/xsection/x.{good["sha256"][:16]}.json.gz'}, 'y': {**good, 'rows': -1}}
    assert reader.refs_index(raw) == pub.ref_entries(raw) == index


def test_a_refs_entry_that_is_not_a_content_keyed_reference_object_is_neither_carried_nor_protected():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    good = refs(bucket)['tickers']
    raw = {**refs(bucket), 'evil': {'key': 'v1/manifest/BBCA.json', 'sha256': 'ab' * 32, 'bytes': 1, 'rows': 0},
           'fixed': {**good, 'key': 'v1/ref/tickers.json.gz'}, 'other': good,
           'short': {**good, 'key': f'v1/ref/short.{"0" * 16}.json.gz'}, 'odd': {**good, 'bytes': True},
           'upper': {**good, 'sha256': good['sha256'].upper()},
           'xs': {**good, 'key': f'v1/xsection/xs.{good["sha256"][:16]}.json.gz'}}       # another family's object
    assert sorted(pub.ref_entries(raw)) == ['brokers', 'fixed_income', 'stock_lists', 'tickers']   # the well-formed entries of the run
    state = bucket.get_json('state.json')
    state['refs'] = raw
    bucket.put('state.json', json.dumps(state).encode(), 'application/json')
    bucket.modified['state.json'] -= 3 * HOUR
    at(bucket, conn, 'daily', 0.5)                                         # the cleanup reads that index
    assert sorted(refs(bucket)) == sorted(pub.REF_NAMES)
    assert {'manifest/BBCA.json'} | FIXED_REFS <= set(bucket.objects)


def test_the_logos_copy_follows_the_fixed_copy_and_a_bucket_from_before_t5_is_indexed_at_once():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    at(bucket, conn, 'logos', 1)
    logos = refs(bucket)['logos']
    for i, (mode, args) in enumerate((('events', ()), ('broker-range', ('2026-01-01', '2026-12-31')), ('packs', ()))):
        at(bucket, conn, mode, 1.1 + 0.1 * i, *args)                      # logos not refreshed: the fixed copy stands
        assert refs(bucket)['logos'] == logos
    p = pub.Publisher(conn, bucket, today=TODAY, get=fake_get(stockbit=('BBCA',)))
    p.run('logos')                                                         # a refreshed index is a new object
    assert refs(bucket)['logos']['key'] != logos['key'] and refs(bucket)['logos']['rows'] == 1
    assert bucket.objects[refs(bucket)['logos']['key'][3:]] == bucket.objects['ref/logos.json.gz']
    # a bucket the publisher before T5 wrote: fixed copies and a state.json without `refs`; the first run of this one
    # indexes all three, the logos from their fixed copy, without fetching any logo
    state = bucket.get_json('state.json')
    state.pop('refs')
    for k in [k for k in bucket.objects if pub.REF_KEY.fullmatch(k)]:
        del bucket.objects[k]
    bucket.objects['state.json'] = json.dumps(state).encode()
    fetched = []
    p = pub.Publisher(conn, bucket, today=TODAY, get=lambda url, data=None, timeout=30: fetched.append(url))
    p.run('events')
    assert sorted(refs(bucket)) == sorted(pub.REF_NAMES) and fetched == []
    assert bucket.objects[refs(bucket)['logos']['key'][3:]] == bucket.objects['ref/logos.json.gz']


def test_a_replaced_content_keyed_reference_object_goes_after_the_wait_and_fixed_copies_never():
    """As for xsection: a reference object the new refs index stops naming stays through the run and the wait after its
    state.json, then goes; a carry-forward run (logos) replaces none, and the fixed-key copies are never deleted."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = refs(bucket)['tickers']['key'][3:]
    conn.universe = renamed('BCA one')
    seen = during_wait(bucket)
    at(bucket, conn, 'daily', 2)
    k2 = refs(bucket)['tickers']['key'][3:]
    assert k1 in seen[0] and k1 not in bucket.objects and k2 in bucket.objects
    at(bucket, conn, 'logos', 4)                                           # the same ticker list: k2 stays
    assert k2 in bucket.objects
    assert not FIXED_REFS & set(bucket.deleted) and FIXED_REFS <= set(bucket.objects)
    assert {e['key'][3:] for e in refs(bucket).values()} <= set(bucket.objects)


def test_ref_cleanup_keeps_newer_objects_other_keys_and_everything_when_no_refs_index_names_a_file(capsys):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    finished = bucket.modified['state.json']
    stale, newer = f'ref/tickers.{"b" * 16}.json.gz', f'ref/brokers.{"a" * 16}.json.gz'
    plant(bucket, stale, -24)                                             # named by no index: deleted
    plant(bucket, newer, 1)                                               # written by a run that did not finish: kept
    for k in FIXED_REFS | {'ref/notes.txt', 'ref/old.json.gz', f'ref/x/tickers.{"c" * 16}.json.gz'}:
        plant(bucket, k, -24)                                             # not content-keyed reference objects: kept
    bucket.clock = finished + 2 * HOUR
    p = pub.Publisher(conn, bucket, today=TODAY, clock=lambda: bucket.clock)
    assert p.collect_garbage() == 1 and bucket.deleted == [stale]
    gc = events(capsys, 'gc')[0]
    assert gc['refs_named'] == len(pub.REF_NAMES) - 1 and gc['kept_newer_than_last_run'] == 1   # every list but logos
    # a state.json without `refs` (the publisher before T5, or a rollback to it) names no reference file: no
    # content-keyed reference object is deleted until an index names one again
    state = bucket.get_json('state.json')
    state.pop('refs')
    bucket.objects['state.json'] = json.dumps(state).encode()             # same LastModified
    plant(bucket, stale, -24)
    assert p.collect_garbage() == 0 and stale in bucket.objects and bucket.deleted == [stale]


def test_a_reference_object_the_cleanup_deleted_is_put_again_when_its_content_returns():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = refs(bucket)['tickers']['key'][3:]
    body = bucket.objects[k1]
    conn.universe = renamed('BCA')
    at(bucket, conn, 'daily', 2)                                           # k1 replaced: deleted after the wait
    assert k1 in bucket.deleted and k1 not in bucket.objects
    conn.universe = UNIVERSE                                               # undone: k1's content again
    at(bucket, conn, 'daily', 4)                                           # index_refs puts it again
    assert refs(bucket)['tickers']['key'] == f'v1/{k1}' and bucket.objects[k1] == body
    assert pub.verify(conn, bucket) == 0


def test_a_bucket_that_cannot_list_ref_still_indexes_the_reference_files(capsys):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    before = refs(bucket)
    whole = bucket.list
    bucket.list = lambda deadline=None, prefix='': ((_ for _ in ()).throw(PermissionError('detail'))
                                                    if prefix == 'ref/' else whole(deadline, prefix))
    n = len(bucket.puts)
    p = at(bucket, conn, 'events', 1)
    assert refs(bucket) == before and ref_puts(bucket, n) == [] and p.refs_failed == []
    out = capsys.readouterr().out
    assert '"ref_list_failed"' in out and 'detail' not in out


def test_a_failed_reference_copy_keeps_its_entry_the_rest_is_published_and_the_run_exits_3(capsys, monkeypatch):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    before = refs(bucket)
    conn.universe = renamed('BCA')
    put = bucket.put
    bucket.put = lambda key, body, ctype: ((_ for _ in ()).throw(OSError('secret detail'))
                                           if pub.REF_KEY.fullmatch(key) else put(key, body, ctype))
    monkeypatch.setattr(pub.psycopg, 'connect', lambda *a, **k: __import__('contextlib').nullcontext(conn))
    monkeypatch.setattr(pub, 'Bucket', lambda: bucket)
    monkeypatch.setenv('TERMINAL_PUBLISHER_DATABASE_URL', 'unused')
    monkeypatch.delenv('TERMINAL_RUN_TIMES_WIB', raising=False)
    assert pub.main(['publisher.py', 'events']) == 3
    after = bucket.get_json('state.json')
    assert after['refs']['tickers'] == before['tickers'] and after['refs']['brokers'] == before['brokers']
    assert bucket.get_json('ref/tickers.json.gz')['name'][0] == 'BCA'   # the fixed copy was written
    out = capsys.readouterr().out
    assert '"ref_failed"' in out and 'OSError' in out and 'secret detail' not in out
    bucket.put = put
    assert pub.main(['publisher.py', 'events']) == 0 and bucket.get_json('state.json')['refs']['tickers'] != before['tickers']


def test_verify_checks_the_refs_index():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    at(bucket, conn, 'logos', 1)
    assert pub.verify(conn, bucket) == 0 and pub.verify_refs(bucket) == (len(pub.REF_NAMES), 0)
    fixed = bucket.objects['ref/brokers.json.gz']
    bucket.objects['ref/brokers.json.gz'] = pub.encode({'columns': ['code'], 'code': []})[0]
    assert pub.verify_refs(bucket) == (len(pub.REF_NAMES), 1)              # the content copy is not the fixed copy
    bucket.objects['ref/brokers.json.gz'] = fixed
    key = refs(bucket)['tickers']['key'][3:]
    good = bucket.objects[key]
    bucket.objects[key] = gzip.compress(b'{}')
    assert pub.verify(conn, bucket) == 1                                   # not the indexed bytes
    bucket.objects[key] = good
    body, sha = pub.encode({'not': 'columnar'})                            # indexed bytes, but not a reference file
    state = bucket.get_json('state.json')
    state['refs']['brokers'] = {'key': f'v1/{pub.content_key("ref", None, "brokers", sha)}', 'sha256': sha,
                                'bytes': len(body), 'rows': 2}
    bucket.objects[state['refs']['brokers']['key'][3:]] = body
    bucket.objects['state.json'] = json.dumps(state).encode()
    assert pub.verify_refs(bucket) == (len(pub.REF_NAMES), 1)


def test_the_real_bucket_client_puts_and_lists_the_reference_copies_as_the_s3_api_expects():
    """The whole run through publisher.Bucket (not FakeBucket) over an in-memory S3 client: the content-keyed copies go
    to v1/ref/<name>.<16 hex>.json.gz with the gzip type and the long cache header, the listing asks for v1/ref/ only,
    and a second run puts none of them again."""
    from botocore.exceptions import ClientError
    class NoSuchKey(ClientError):
        pass
    class S3:
        exceptions = type('Exceptions', (), {'NoSuchKey': NoSuchKey})
        def __init__(self):
            self.objects, self.calls = {}, []
        def put_object(self, Bucket, Key, Body, ContentType, CacheControl):
            self.calls.append(('put', Key, ContentType, CacheControl))
            self.objects[Key] = (Body, dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc))
        def get_object(self, Bucket, Key):
            if Key not in self.objects:
                raise NoSuchKey({'Error': {'Code': 'NoSuchKey', 'Message': 'x'}}, 'GetObject')
            return {'Body': type('Body', (), {'read': lambda _, b=self.objects[Key][0]: b})()}
        def list_objects_v2(self, Bucket, Prefix, **kw):
            self.calls.append(('list', Prefix))
            return {'IsTruncated': False, 'Contents': [{'Key': k, 'LastModified': at, 'Size': len(b)}
                                                        for k, (b, at) in sorted(self.objects.items()) if k.startswith(Prefix)]}
        def delete_objects(self, Bucket, Delete):
            return {}
    b = pub.Bucket.__new__(pub.Bucket)
    b.name, b.s3 = 'bucket', S3()
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    pub.Publisher(conn, b, today=TODAY, get=fake_get()).run('logos')
    state = json.loads(b.s3.objects['v1/state.json'][0])
    puts = {key: (ctype, cache) for op, key, *rest in b.s3.calls if op == 'put' for ctype, cache in [rest]}
    assert sorted(state['refs']) == sorted(pub.REF_NAMES) and ('list', 'v1/ref/') in b.s3.calls
    for name, e in state['refs'].items():
        assert e['key'].startswith(f'v1/ref/{name}.') and puts[e['key']] == ('application/gzip', 'private, max-age=31536000')
        assert b.s3.objects[e['key']][0] == b.s3.objects[f'v1/ref/{name}.json.gz'][0]
    n = len(b.s3.calls)
    pub.Publisher(conn, b, today=TODAY, get=fake_get()).run('events')
    assert not [c for c in b.s3.calls[n:] if c[0] == 'put' and pub.REF_KEY.fullmatch(c[1][3:])]
    assert json.loads(b.s3.objects['v1/state.json'][0])['refs'] == state['refs']


# ---- EXEC-PUBLISHER-SPEED (user go 2026-10-29; ERRORS M301, M303) ------------------------------------------------------
class SlowBucket(FakeBucket):
    """A FakeBucket whose puts and gets take `delay` seconds and may overlap; it records when each put started and
    ended, and the most requests in flight at once."""
    def __init__(self, delay=0.02, slow=None):
        super().__init__()
        self.delay, self.lock, self.inflight, self.most = delay, pub.threading.Lock(), 0, 0
        self.slow = slow or (lambda key: 0)                # extra seconds for a key's put
        self.spans = {}                                    # key -> (start, end) of its last put

    def _enter(self):
        with self.lock:
            self.inflight += 1
            self.most = max(self.most, self.inflight)

    def _leave(self):
        with self.lock:
            self.inflight -= 1

    def put(self, key, body, content_type):
        self._enter()
        start = pub.time.monotonic()
        pub.time.sleep(self.delay + self.slow(key))
        try:
            super().put(key, body, content_type)
        finally:
            self.spans[key] = (start, pub.time.monotonic())
            self._leave()

    def get_json(self, key):
        self._enter()
        try:
            pub.time.sleep(self.delay)
            return super().get_json(key)
        finally:
            self._leave()


def many(n=24):
    """A universe of n stocks with two price years each, and broker rows: enough puts to overlap."""
    tickers = [f'T{i:02d}' for i in range(n)]
    prices = [(t, d, 10.0, 11.0, 9.0, 10.0 + i, 100.0) for i, t in enumerate(tickers) for d in ('2025-12-30', '2026-01-02')]
    brokers = [(t, '2026-01-02', 'AK', 'Foreign', 'Regular', 5.0, 0.0, 0.05, 0.0, False, 1, 0) for t in tickers]
    universe = [(t, f'Company {t}', 'stock', 'Finance', 'Banks', 'common') for t in tickers]
    return FakeConn(prices, brokers, universe, events=[], actions=[])


def test_puts_overlap_and_every_manifest_and_state_json_come_after_what_they_name():
    """The bucket requests go through TERMINAL_BUCKET_THREADS threads; the barriers keep the order readers rely on: no
    manifest put starts before every object it names is in the bucket, and state.json starts after every other put.
    T00's price pack and T23's manifest are slow: without a barrier, T00's manifest would start before its pack is
    written, and state.json before T23's manifest."""
    bucket = SlowBucket(slow=lambda key: 0.4 if key.startswith('pack/T00/price.') or key == 'manifest/T23.json' else 0)
    p = pub.Publisher(many(), bucket, today=TODAY, threads=8)
    p.run('backfill')
    assert bucket.most > 1 and p.threads == 8
    for t in [f'T{i:02d}' for i in range(24)]:
        start = bucket.spans[f'manifest/{t}.json'][0]
        for key in pub.named_keys(bucket.get_json(f'manifest/{t}.json')):
            assert bucket.spans[key][1] <= start, (t, key)
    state_start = bucket.spans['state.json'][0]
    assert all(end <= state_start for key, (_, end) in bucket.spans.items() if key != 'state.json')
    assert bucket.puts[-1] == 'state.json' and pub.verify(many(), bucket) == 0


def test_parallel_and_one_at_a_time_publish_the_same_bytes():
    one, eight = FakeBucket(), FakeBucket()
    pub.Publisher(many(), one, today=TODAY, threads=1).run('backfill')
    pub.Publisher(many(), eight, today=TODAY, threads=8).run('backfill')
    data = lambda b: {k: v for k, v in b.objects.items() if not k.startswith('manifest/') and k != 'state.json'}
    assert data(one) == data(eight)
    strip = lambda b, k: {**b.get_json(k), 'generated_at': None}
    assert all(strip(one, k) == strip(eight, k) for k in one.objects if k.startswith('manifest/'))
    assert {**one.get_json('state.json'), 'finished_at': None} == {**eight.get_json('state.json'), 'finished_at': None}


def test_the_manifests_are_read_in_parallel_before_planning():
    conn = many()
    _, _, filled = run('backfill', conn=conn)
    bucket = SlowBucket()
    bucket.objects, bucket.modified = dict(filled.objects), dict(filled.modified)
    started = pub.time.monotonic()
    p = pub.Publisher(conn, bucket, today=TODAY, threads=8)
    p.run('daily')
    assert bucket.most > 1 and p.written == 0                             # reads overlapped (no timing: CI speed varies)


def test_a_failed_put_stops_the_run_before_any_manifest_or_state_json_names_it():
    conn = many()
    bucket = FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('backfill')
    state, manifests = bucket.objects['state.json'], {k: v for k, v in bucket.objects.items() if k.startswith('manifest/')}
    conn.prices = conn.prices + [('T05', '2026-01-05', 10.0, 11.0, 9.0, 10.5, 100.0)]
    put = FakeBucket.put
    def failing(self, key, body, ctype):
        if key.startswith('price/T05/2026.'):
            raise PermissionError('denied')
        put(self, key, body, ctype)
    bucket.put = failing.__get__(bucket)
    p = pub.Publisher(conn, bucket, today=TODAY, threads=8)
    with pytest.raises(PermissionError):
        p.run('daily')
    assert bucket.objects['state.json'] == state                          # the previous publication stands
    assert {k: v for k, v in bucket.objects.items() if k.startswith('manifest/')} == manifests
    assert p.stage == 'files'                                             # the step of the put that failed
    assert p.uploads.pool is None and p.manifests == {}                   # the pool ended; nothing stale is kept


def test_the_cleanup_comes_after_state_json_so_a_slow_or_failed_listing_never_holds_the_publication(capsys):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    plant(bucket, 'price/IHSG/2019.json.gz', -24)
    whole, sweeping = bucket.list, []
    AT_WAIT.append(lambda: sweeping.append(True))                          # after state.json: the sweep's listings fail
    def listing(deadline=None, prefix=''):
        if sweeping:
            assert bucket.puts[-1] == 'state.json'                       # published before the sweep lists
            raise TimeoutError('bucket listing took too long')
        return whole(deadline, prefix)
    bucket.list = listing
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    at(bucket, conn, 'daily', 2)
    out = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    names = [e['event'] for e in out]
    assert names.index('done') < names.index('replaced') < names.index('gc_failed')
    assert 'price/IHSG/2019.json.gz' in bucket.objects and bucket.modified['state.json'] == bucket.clock
    done = [e for e in out if e['event'] == 'done'][0]
    assert set(done['phases']) == {'plan', 'files', 'packs', 'intraday', 'xsection', 'radar', 'manifests', 'refs', 'state'}


def test_after_the_run_a_ticker_whose_manifest_a_run_that_did_not_finish_wrote_keeps_its_objects(capsys):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    finished = bucket.modified['state.json']
    plant(bucket, 'price/BBCA/2019.json.gz', -24)                          # BBCA's manifest is from an unfinished run
    bucket.modified['manifest/BBCA.json'] = finished + dt.timedelta(seconds=1)
    plant(bucket, 'price/IHSG/2019.json.gz', -24)                          # IHSG's is the finished run's: deleted
    at(bucket, conn, 'daily', 2)
    assert 'price/BBCA/2019.json.gz' in bucket.objects and 'price/IHSG/2019.json.gz' not in bucket.objects
    gc = events(capsys, 'gc')[0]
    assert gc['after_publication'] and gc['tickers_skipped'] == 1 and gc['deleted'] == 1


def test_after_the_run_a_manifest_outside_the_universe_is_cleaned_by_its_own_names():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    gone = 'price/GONE/2026.' + 'a' * 64 + '.json.gz'
    plant(bucket, gone, -24)
    bucket.objects['manifest/GONE.json'] = json.dumps({'datasets': {'price': {'files': {'2026': {'key': f'v1/{gone}'}}}}}).encode()
    bucket.modified['manifest/GONE.json'] = bucket.modified['state.json']
    plant(bucket, 'price/GONE/2019.json.gz', -24)
    at(bucket, conn, 'daily', 2)
    assert gone in bucket.objects and 'price/GONE/2019.json.gz' not in bucket.objects


# ---- alerts (ERRORS M303) -----------------------------------------------------------------------------------------
@pytest.fixture
def alerts(monkeypatch):
    sent = []
    monkeypatch.setattr(pub, 'post_notify', lambda payload, event: sent.append(payload))
    return sent


def test_the_alert_ids_are_one_per_run_time_and_kind(alerts):
    slot = dt.datetime(2026, 10, 29, 19, 0, tzinfo=pub.WIB)
    pub.notify_publication('failed', slot, stage='files', error='ReadTimeoutError', last_published=None)
    pub.notify_publication('missing', slot, last_published='2026-10-29T00:35:00+00:00')
    pub.notify_publication('slow', slot, stage='packs', minutes=30)
    pub.notify_publication('partial', slot, files=['price'])
    pub.notify_publication('failed', dt.datetime(2026, 10, 29, 12, 3, tzinfo=dt.timezone.utc), True, stage='plan')
    ids = [a['execution_id'] for a in alerts]
    assert ids == ['terminal-publish-2026-10-29-1900'] * 2 + ['terminal-publish-2026-10-29-1900-slow',
                   'terminal-publish-2026-10-29-1900-partial', 'terminal-publish-manual-2026-10-29-1903']
    assert all(a['source_table'] == 'Terminal_Publisher_Health' for a in alerts)
    assert alerts[0]['details'] == {'status': 'failed', 'run_time': '2026-10-29 19:00', 'manual': False,
                                    'stage': 'files', 'error': 'ReadTimeoutError'}          # None is left out


def test_a_run_belongs_to_its_listed_run_time_and_a_manual_run_to_its_start():
    times = pub.run_times('07:30,19:00')
    utc = lambda d, h, m: dt.datetime(2026, 10, d, h, m, tzinfo=dt.timezone.utc)
    assert pub.run_slot(times, utc(29, 12, 4)) == (dt.datetime(2026, 10, 29, 19, 0, tzinfo=pub.WIB), False)
    assert pub.run_slot(times, utc(29, 0, 31)) == (dt.datetime(2026, 10, 29, 7, 30, tzinfo=pub.WIB), False)
    assert pub.run_slot(times, utc(29, 15, 2)) == (dt.datetime(2026, 10, 29, 22, 2, tzinfo=pub.WIB), True)
    assert pub.last_run_time(times, utc(29, 0, 0)) == dt.datetime(2026, 10, 28, 19, 0, tzinfo=pub.WIB)   # 07:00 WIB
    assert pub.last_run_time(times, utc(29, 1, 0)) == dt.datetime(2026, 10, 29, 7, 30, tzinfo=pub.WIB)   # 08:00 WIB


def test_a_check_tick_reports_a_missing_publication_once_per_run_time(alerts):
    times = pub.run_times('07:30,19:00')
    bucket = FakeBucket()
    state = lambda finished: bucket.put('state.json', json.dumps({'finished_at': finished}).encode(), 'application/json')
    check = dt.datetime(2026, 10, 29, 12, 30, tzinfo=dt.timezone.utc)                       # 19:30 WIB
    state('2026-10-29T12:05:00+00:00')                                                        # 19:05 WIB: out
    pub.check_publication(times, check, bucket)
    assert alerts == []
    state('2026-10-29T00:36:00+00:00')                                                        # only the morning's
    pub.check_publication(times, check, bucket)
    assert [a['details']['status'] for a in alerts] == ['missing']
    assert alerts[0]['execution_id'] == 'terminal-publish-2026-10-29-1900'
    assert alerts[0]['details']['last_published'] == '2026-10-29T00:36:00+00:00'
    bucket.get_json = lambda key: (_ for _ in ()).throw(OSError('secret detail'))
    pub.check_publication(times, check, bucket)                                              # logged only
    assert len(alerts) == 1


def test_main_on_a_tick_that_is_not_a_run_time_checks_and_never_publishes(monkeypatch, alerts):
    monkeypatch.setenv('TERMINAL_RUN_TIMES_WIB', '07:30,19:00')
    monkeypatch.setattr(pub, 'should_run', lambda times: False)
    checked = []
    monkeypatch.setattr(pub, 'check_publication', lambda times: checked.append(times))
    monkeypatch.setattr(pub.psycopg, 'connect', lambda *a, **k: pytest.fail('a check tick connected'))
    assert pub.main(['publisher.py', 'daily']) == 0 and checked == [[(7, 30), (19, 0)]]


def wire_main(monkeypatch, conn, bucket):
    monkeypatch.setattr(pub.psycopg, 'connect', lambda *a, **k: __import__('contextlib').nullcontext(conn))
    monkeypatch.setattr(pub, 'Bucket', lambda: bucket)
    monkeypatch.setenv('TERMINAL_PUBLISHER_DATABASE_URL', 'unused')
    monkeypatch.delenv('TERMINAL_RUN_TIMES_WIB', raising=False)


def test_a_failed_run_reports_its_step_and_error_class_and_still_fails(monkeypatch, alerts, capsys):
    conn, bucket = FakeConn(PRICES, BROKERS, UNIVERSE), FakeBucket()
    wire_main(monkeypatch, conn, bucket)
    assert pub.main(['publisher.py', 'backfill']) == 0
    put = bucket.put
    bucket.put = lambda key, body, ctype: ((_ for _ in ()).throw(OSError('secret detail'))
                                           if key.startswith('manifest/') else put(key, body, ctype))
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    with pytest.raises(OSError):
        pub.main(['publisher.py', 'daily'])
    (alert,) = alerts
    assert alert['details']['status'] == 'failed' and alert['details']['stage'] == 'manifests'
    assert alert['details']['error'] == 'OSError' and alert['details']['manual'] is True
    assert alert['details']['last_published'] == json.loads(bucket.objects['state.json'])['finished_at']
    assert 'secret detail' not in json.dumps(alert) and '"failed"' in capsys.readouterr().out
    conn._rows = lambda sql, params: (_ for _ in ()).throw(pub.psycopg.OperationalError('password=x'))
    assert pub.main(['publisher.py', 'daily']) == 2                       # a driver error: the class only, exit 2
    # EXEC-PUBLISH-FLOW: the first statement is now the run lock, before any step: the stage is 'connect'
    assert alerts[-1]['details']['stage'] == 'connect' and 'password' not in json.dumps(alerts[-1])


def test_a_run_that_publishes_without_an_xsection_file_reports_it_as_partial(monkeypatch, alerts):
    conn, bucket = FakeConn(PRICES, BROKERS, UNIVERSE), FakeBucket()
    wire_main(monkeypatch, conn, bucket)
    rows = conn._rows
    conn._rows = lambda sql, params: (_ for _ in ()).throw(TimeoutError()) if sql == pub.XSECTION_PRICE_SQL else rows(sql, params)
    assert pub.main(['publisher.py', 'daily']) == 3
    (alert,) = alerts
    assert alert['details']['status'] == 'partial' and alert['details']['files'] == ['price']
    assert alert['execution_id'].endswith('-partial')


def test_the_watchdog_alerts_once_after_its_minutes_and_never_once_stopped():
    calls = []
    dog = pub.Watchdog(0.001, lambda: calls.append(1))                   # 60 ms
    pub.time.sleep(0.3)
    assert calls == [1]
    dog = pub.Watchdog(0.01, lambda: calls.append(2))
    dog.stop()
    pub.time.sleep(0.8)
    assert calls == [1]


def test_a_failed_xsection_upload_is_that_files_failure_and_the_rest_is_published():
    """The xsection files are put at once (store now=True), not through the pool: a failed put is caught where the file
    is built (xsection_failed, exit 3), as before EXEC-PUBLISHER-SPEED, not the whole run's at the next barrier."""
    _, conn, bucket = run('backfill')
    before = bucket.get_json('state.json')['xsection']
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    put = bucket.put
    bucket.put = lambda key, body, ctype: ((_ for _ in ()).throw(PermissionError('denied'))
                                           if key.startswith('xsection/price.') else put(key, body, ctype))
    p = pub.Publisher(conn, bucket, today=TODAY, threads=8)
    p.run('daily')
    after = bucket.get_json('state.json')
    assert p.xsection_failed == ['price'] and after['xsection']['price'] == before['price']
    assert bucket.get_json('manifest/BBCA.json')['datasets']['price']['files']['2026']['rows'] == 2


def test_the_logo_index_is_put_after_the_images_it_names():
    bucket = SlowBucket(slow=lambda key: 0.3 if key == 'logo/BBCA.png' else 0)
    p = pub.Publisher(FakeConn(PRICES, BROKERS, UNIVERSE), bucket, today=TODAY, get=fake_get(), threads=8)
    p.run('logos')
    assert bucket.spans['logo/BBCA.png'][1] <= bucket.spans['ref/logos.json.gz'][0]


def test_telegram_monitor_accepts_every_alert_the_publisher_sends(alerts):
    """The two services share the shape of an alert: each one the publisher builds passes telegram-monitor's checks."""
    spec = importlib.util.spec_from_file_location('telegram_monitor', ROOT / 'apps/telegram-monitor/telegram_monitor.py')
    monitor = importlib.util.module_from_spec(spec)
    sys.modules.setdefault('telegram_monitor', monitor)                    # its dataclasses look their module up
    spec.loader.exec_module(monitor)
    slot = dt.datetime(2026, 10, 29, 19, 0, tzinfo=pub.WIB)
    last = '2026-10-29T00:36:12.101946+00:00'                              # state.json finished_at as written
    pub.notify_publication('failed', slot, stage='manifests', error='ReadTimeoutError', last_published=last)
    pub.notify_publication('failed', slot, True, stage='connect', error='OperationalError', last_published=None)
    pub.notify_publication('missing', slot, last_published=last)
    pub.notify_publication('missing', slot, last_published=None)
    pub.notify_publication('slow', slot, stage='packs', minutes=30, last_published=last)
    pub.notify_publication('partial', slot, files=['price', 'tickers'])
    for a in alerts:
        assert a['source_table'] == monitor.HEALTH_SOURCE
        health = monitor.parse_publisher_health(a['execution_id'], a['details'])
        assert health.status == a['details']['status'] and monitor.build_publisher_message(health)
    p = pub.Publisher(FakeConn(PRICES, BROKERS, UNIVERSE), FakeBucket(), today=TODAY)
    p.run('daily')
    assert set(p.phases) | {'connect', 'start', 'cleanup'} <= set(monitor.HEALTH_STAGES)   # every step it can report


# ---- review 2026-10-29 -----------------------------------------------------------------------------------------------
def test_a_barrier_raises_a_failed_put_even_before_its_done_callback_ran(monkeypatch):
    """Future.set_exception wakes a waiter before it runs the done callbacks: the barrier must use what
    future.exception() returns, not only what _done recorded (otherwise a manifest could name an unwritten object)."""
    monkeypatch.setattr(pub.Uploads, '_done', lambda self, future: self.slots.release())    # callbacks record nothing
    bucket = FakeBucket()
    bucket.put = lambda key, body, ctype: (_ for _ in ()).throw(PermissionError('denied'))
    uploads = pub.Uploads(bucket, 4)
    uploads.put('price/T/2026.x.json.gz', b'x', 'application/gzip')
    with pytest.raises(PermissionError):
        uploads.wait()
    assert uploads.error_key == 'price/T/2026.x.json.gz'
    uploads.close()


def test_a_publisher_used_again_after_a_failed_run_names_only_objects_that_exist():
    conn = many()
    bucket = FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('backfill')
    conn.prices = conn.prices + [('T05', '2026-01-05', 10.0, 11.0, 9.0, 10.5, 100.0)]
    put = FakeBucket.put
    fail = {'on': True}
    def flaky(self, key, body, ctype):
        if fail['on'] and key.startswith('price/T05/2026.'):
            raise PermissionError('denied')
        put(self, key, body, ctype)
    bucket.put = flaky.__get__(bucket)
    p = pub.Publisher(conn, bucket, today=TODAY, threads=8)
    with pytest.raises(PermissionError):
        p.run('daily')
    fail['on'] = False
    p.run('daily')                                                        # the same object, the bucket works again
    for t in [f'T{i:02d}' for i in range(24)]:
        assert pub.named_keys(bucket.get_json(f'manifest/{t}.json')) <= set(bucket.objects), t
    assert pub.verify(conn, bucket) == 0


def test_the_slow_alert_is_not_sent_once_the_run_is_in_its_cleanup(alerts):
    slot = dt.datetime(2026, 10, 29, 19, 0, tzinfo=pub.WIB)
    p = pub.Publisher(FakeConn(PRICES, BROKERS, UNIVERSE), FakeBucket(), today=TODAY)
    p.stage, p.previous_finished = 'cleanup', '2026-10-29T00:36:00+00:00'
    pub.slow_alert(p, slot, False, 30)
    assert alerts == []
    p.stage = 'packs'
    pub.slow_alert(p, slot, False, 30)
    assert [a['details']['stage'] for a in alerts] == ['packs']


def test_a_hung_baseline_listing_is_given_up_and_the_run_publishes_without_a_cleanup(capsys, monkeypatch):
    monkeypatch.setattr(pub, 'BASELINE_SECONDS', 0.2)
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    plant(bucket, 'price/IHSG/2019.json.gz', -24)
    whole, gate = bucket.list, pub.threading.Event()
    bucket.list = lambda deadline=None, prefix='': (gate.wait(5), whole(deadline, prefix))[1] if prefix == 'state.json' else whole(deadline, prefix)
    started = pub.time.monotonic()
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    at(bucket, conn, 'daily', 2)
    gate.set()
    out = capsys.readouterr().out
    assert pub.time.monotonic() - started < 4 and '"step": "baseline"' in out and '"TimeoutError"' in out
    assert bucket.puts[-1] == 'state.json' and 'price/IHSG/2019.json.gz' in bucket.objects


def test_a_logos_run_does_not_read_every_manifest(monkeypatch):
    monkeypatch.setattr(pub.Publisher, 'load_manifests', lambda self, tickers: pytest.fail('read every manifest'))
    bucket = FakeBucket()
    pub.Publisher(FakeConn(PRICES, BROKERS, UNIVERSE), bucket, today=TODAY, get=fake_get()).run('logos')
    assert bucket.puts[-1] == 'state.json'


# ---- delete the replaced files after the switch (user 2026-10-29: "Ok setuju"; ERRORS M301) ------------------------
def logged(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith('{')]


def test_the_wait_follows_its_variable_and_is_never_below_its_floor(monkeypatch):
    p = lambda **kw: pub.Publisher(None, FakeBucket(), today=TODAY, **kw)
    monkeypatch.delenv('TERMINAL_DELETE_AFTER_SECONDS', raising=False)
    assert p().delete_after == pub.DELETE_AFTER_SECONDS == 600
    monkeypatch.setenv('TERMINAL_DELETE_AFTER_SECONDS', '900')
    assert p().delete_after == 900
    monkeypatch.setenv('TERMINAL_DELETE_AFTER_SECONDS', '60')                # below what a reader may still hold
    assert p().delete_after == pub.MIN_DELETE_AFTER_SECONDS == 300
    assert p(delete_after=1).delete_after == 300 and p(delete_after=1200).delete_after == 1200


def test_a_key_the_new_publication_names_is_never_a_replaced_one():
    """replaced_keys: what a manifest named when it was read, or the previous index named, and the new publication no
    longer names anywhere (another ticker's manifest or either index naming it keeps it)."""
    key = lambda k: {'key': f'{pub.PREFIX}/{k}'}
    manifest = lambda *keys: {'datasets': {'price': {'files': {str(i): key(k) for i, k in enumerate(keys)}}}}
    p = pub.Publisher(None, FakeBucket(), today=TODAY)
    p.loaded_named = {'AAAA': {'price/AAAA/2025.a.json.gz', 'price/AAAA/2026.a.json.gz', 'price/AAAA/2024.a.json.gz'},
                      'BBBB': {'price/BBBB/2026.b.json.gz'}}
    p.manifests = {'AAAA': manifest('price/AAAA/2025.a.json.gz', 'price/AAAA/2026.c.json.gz'),
                   'BBBB': manifest('price/BBBB/2026.b.json.gz', 'price/AAAA/2024.a.json.gz')}
    previous = {'xsection': {'price': key('xsection/price.1111111111111111.json.gz'),
                             'actions': key('xsection/actions.2222222222222222.json.gz')}, 'ref': {}}
    now = {'xsection': {'price': key('xsection/price.3333333333333333.json.gz'),
                        'actions': key('xsection/actions.2222222222222222.json.gz')},
           'ref': {'tickers': key('xsection/price.1111111111111111.json.gz')}}
    assert p.replaced_keys(previous, now) == {'price/AAAA/2026.a.json.gz'}
    now['ref'] = {}
    assert p.replaced_keys(previous, now) == {'price/AAAA/2026.a.json.gz', 'xsection/price.1111111111111111.json.gz'}
    p.loaded_named['CCCC'] = {'price/CCCC/2026.c.json.gz'}               # read, but its manifest is no longer held
    assert 'price/CCCC/2026.c.json.gz' not in p.replaced_keys(previous, now)


def test_a_run_stopped_during_the_wait_deletes_nothing_and_the_full_cleanup_takes_what_it_left(monkeypatch):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = price_key(bucket)
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    monkeypatch.setattr(pub, 'wait', lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt()))   # the stop
    with pytest.raises(KeyboardInterrupt):
        at(bucket, conn, 'daily', 2)
    assert bucket.puts[-1] == 'state.json' and price_key(bucket) != k1                      # published
    assert k1 in bucket.objects and bucket.deleted == []                                    # nothing deleted
    left = set(bucket.objects) - named(bucket) - indexed(bucket) - {k for k in bucket.objects if '/' not in k
                                                                       or k.startswith(('manifest/', 'logo/'))}
    left -= {k for k in left if pub.REF_KEY.fullmatch(k)} | {k for k in left if k.startswith('ref/')}
    assert k1 in left
    # the cleanup outside a run, more than an hour later: what the stopped run replaced goes, what is named stays
    pub.Publisher(None, bucket, today=TODAY, clock=lambda: bucket.clock + 2 * HOUR).collect_garbage()
    assert k1 not in bucket.objects and named(bucket) | indexed(bucket) <= set(bucket.objects)
    assert pub.verify(conn, bucket) == 0


def test_a_newer_publication_during_the_wait_keeps_the_replaced_files_for_a_later_cleanup(capsys):
    """Another run published during the wait: its manifests may name a replaced key again (content that returned), so
    this run deletes nothing and skips its sweep; a later cleanup, which reads them, decides."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = price_key(bucket)
    capsys.readouterr()
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    newer = lambda: bucket.put('state.json', json.dumps({**json.loads(bucket.objects['state.json']),
                                                         'finished_at': '2099-01-01T00:00:00+00:00'}).encode(), 'x')
    AT_WAIT.append(newer)
    p = at(bucket, conn, 'daily', 2)
    lines = logged(capsys)
    assert k1 in p.replaced and k1 in bucket.objects and bucket.deleted == []
    assert [e['reason'] for e in lines if e['event'] == 'replaced_skipped'] == ['a newer publication came out during the wait']
    assert [e['reason'] for e in lines if e['event'] == 'gc_skipped'] == ['a newer publication came out after this run']


def test_a_run_outside_the_sweep_time_deletes_by_name_and_never_lists_the_bucket(capsys):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = price_key(bucket)
    plant(bucket, 'price/IHSG/2019.json.gz', -24)                        # an orphan only the full cleanup takes
    listed = []
    whole = bucket.list
    bucket.list = lambda deadline=None, prefix='': listed.append(prefix) or whole(deadline, prefix)
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    bucket.clock = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc) + 2 * HOUR
    p = pub.Publisher(conn, bucket, today=TODAY, clock=lambda: bucket.clock)
    capsys.readouterr()
    p.run('daily', sweep=False)
    done = [e for e in logged(capsys) if e['event'] == 'replaced']
    assert [prefix for prefix in listed if prefix != 'xsection/' and prefix != 'ref/'] == []   # no cleanup listing
    assert k1 in p.replaced and k1 not in bucket.objects and 'price/IHSG/2019.json.gz' in bucket.objects
    assert done[0]['objects'] == len(p.replaced) == done[0]['deleted'] and done[0]['waited'] == pub.DELETE_AFTER_SECONDS
    assert WAITS == [pub.DELETE_AFTER_SECONDS] and pub.verify(conn, bucket) == 0


def test_a_run_that_replaced_nothing_does_not_wait(capsys):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    WAITS.clear()
    p = at(bucket, conn, 'daily', 2)
    assert p.replaced == [] and WAITS == []


def test_the_full_cleanup_runs_in_the_scheduled_morning_run_only(monkeypatch):
    """EXEC-PUBLISH-FLOW: the 19:00 run is gone (the loaders start the publication); the cleanup runs in the 07:30 WIB
    safety run, never in a run started by a signal (away from the listed times: manual)."""
    monkeypatch.delenv('TERMINAL_SWEEP_WIB', raising=False)
    utc = lambda h, m: dt.datetime(2026, 10, 29, h, m, tzinfo=dt.timezone.utc)
    assert pub.sweep_due('daily', False, utc(0, 34))                     # 07:34 WIB
    assert not pub.sweep_due('daily', False, utc(12, 4))                 # 19:04 WIB
    assert not pub.sweep_due('daily', True, utc(0, 34))                  # a run started by a signal or by hand
    assert not pub.sweep_due('backfill', False, utc(0, 34))
    monkeypatch.setenv('TERMINAL_SWEEP_WIB', '19:00')
    assert pub.sweep_due('daily', False, utc(12, 4)) and not pub.sweep_due('daily', False, utc(0, 34))


def test_main_passes_the_sweep_to_the_run(monkeypatch):
    conn, bucket = FakeConn(PRICES, BROKERS, UNIVERSE), FakeBucket()
    wire_main(monkeypatch, conn, bucket)
    asked = []
    monkeypatch.setattr(pub, 'sweep_due', lambda mode, manual, now: asked.append((mode, manual)) or True)
    run = pub.Publisher.run
    monkeypatch.setattr(pub.Publisher, 'run', lambda self, *a, sweep=None: asked.append(sweep) or run(self, *a, sweep=sweep))
    assert pub.main(['publisher.py', 'backfill']) == 0
    assert asked == [('backfill', True), True]


def test_a_daily_run_waits_while_a_loader_writes_and_gives_up_with_an_alert(monkeypatch, alerts, capsys):
    """EXEC-PUBLISH-FLOW (user 2026-11-05: "publisher harus dijalankan setelah proses pengisian table selesai"): a loader
    holding the write lock or a RUNNING broker round keeps the run waiting; after the wait it publishes nothing and
    sends the `waiting` alert (the loader still writing signals again when it ends)."""
    conn, bucket = FakeConn(PRICES, BROKERS, UNIVERSE), FakeBucket()
    wire_main(monkeypatch, conn, bucket)
    conn.held.add(pub.WRITE_LOCK)
    monkeypatch.setenv('TERMINAL_LOADER_WAIT_MINUTES', '0')
    assert pub.main(['publisher.py', 'daily']) == 0
    assert 'state.json' not in bucket.objects
    assert [a['details']['status'] for a in alerts] == ['waiting'] and alerts[0]['details']['stage'] == 'loaders'
    assert any(e['event'] == 'gave_up_waiting' and e['busy'] == ['loader'] for e in logged(capsys))
    conn.held.clear(); conn.rounds = 1
    assert pub.loaders_writing(conn) == ['broker_round']


def test_a_broker_round_counts_only_while_its_heartbeat_is_fresh():
    """ERRORS M413: rounds whose process died (Postgres killed for memory, deployment removed) stayed RUNNING and
    kept the publisher waiting for up to six hours. Only a row stamped within ROUND_STALE_MINUTES counts; the updater
    stamps every HEARTBEAT_SECONDS, well inside it."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    pub.loaders_writing(conn)
    (sql, params), = [(q, p) for q, p in conn.calls if 'Monitoring_Stockbit_Update' in q]
    assert sql == pub.ROUNDS_RUNNING_SQL and params == ('RUNNING', pub.ROUND_RUNNING_HOURS, pub.ROUND_STALE_MINUTES)
    assert 'updated_at > now() - make_interval(mins => %s)' in sql
    import pathlib
    path = pathlib.Path(__file__).resolve().parents[2] / 'stockbit-updater/updater.py'
    source = path.read_text()
    beat = int(source.split('HEARTBEAT_SECONDS = ')[1].split()[0])
    assert beat * 3 <= pub.ROUND_STALE_MINUTES * 60      # three missed beats (a Postgres restart) still count as live


def test_a_loader_that_ends_while_the_run_waits_lets_it_publish():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    conn.held.add(pub.WRITE_LOCK)
    slept = []
    def sleep(seconds):
        slept.append(seconds); conn.held.clear()          # the loader commits and closes its connection
    assert pub.wait_for_loaders(conn, 45, sleep=sleep) == [] and slept == [pub.LOADER_POLL_SECONDS]


def test_only_one_publisher_runs_at_a_time(monkeypatch, capsys):
    conn, bucket = FakeConn(PRICES, BROKERS, UNIVERSE), FakeBucket()
    wire_main(monkeypatch, conn, bucket)
    conn.held.add(pub.RUN_LOCK)
    assert pub.main(['publisher.py', 'daily']) == 0
    assert bucket.puts == [] and any(e.get('reason') == 'another publisher run holds the lock' for e in logged(capsys))


def test_a_signal_during_the_run_makes_it_run_once_more_and_nothing_is_written_twice(monkeypatch, capsys):
    conn, bucket = FakeConn(PRICES, BROKERS, UNIVERSE), FakeBucket()
    wire_main(monkeypatch, conn, bucket)
    run, calls = pub.Publisher.run, []
    def signalled(self, *a, sweep=None):
        calls.append(sweep)
        out = run(self, *a, sweep=sweep)
        if len(calls) == 1:                               # a loader finishes while the first run is going
            conn.signals.append(dt.datetime.now(dt.timezone.utc))
        return out
    monkeypatch.setattr(pub.Publisher, 'run', signalled)
    assert pub.main(['publisher.py', 'daily']) == 0
    assert len(calls) == 2 and calls[1] is False          # the second run never sweeps
    data = [k for k in bucket.puts if k.startswith(('price/', 'broker/', 'pack/'))]
    assert len(data) == len(set(data))                    # the second run found nothing new to write
    assert sum(e['event'] == 'run_again' for e in logged(capsys)) == 1


def test_an_old_signal_does_not_make_the_run_repeat(monkeypatch):
    conn, bucket = FakeConn(PRICES, BROKERS, UNIVERSE), FakeBucket()
    wire_main(monkeypatch, conn, bucket)
    conn.signals.append(dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc))
    calls = []
    run = pub.Publisher.run
    monkeypatch.setattr(pub.Publisher, 'run', lambda self, *a, sweep=None: calls.append(1) or run(self, *a, sweep=sweep))
    assert pub.main(['publisher.py', 'daily']) == 0 and calls == [1]


def test_the_broker_behind_warning_is_due_from_17_wib():
    utc = lambda h, m: dt.datetime(2026, 11, 5, h, m, tzinfo=dt.timezone.utc)
    assert not pub.stale_alert_due(utc(0, 34))            # 07:34 WIB, the safety run
    assert pub.stale_alert_due(utc(10, 5))                # 17:05 WIB, after the price cron
    assert pub.stale_alert_due(utc(16, 50))               # 23:50 WIB


def test_the_cleanup_mode_needs_no_database_and_deletes_only_what_no_publication_names(monkeypatch, capsys):
    conn, bucket = FakeConn(PRICES, BROKERS, UNIVERSE), FakeBucket()
    at(bucket, conn, 'backfill', 0)
    plant(bucket, 'price/IHSG/2019.json.gz', -24)
    keep = named(bucket) | indexed(bucket)
    monkeypatch.setattr(pub, 'Bucket', lambda: bucket)
    monkeypatch.setattr(pub.psycopg, 'connect', lambda *a, **k: pytest.fail('the cleanup connected to the database'))
    monkeypatch.delenv('TERMINAL_RUN_TIMES_WIB', raising=False)
    assert pub.main(['publisher.py', 'cleanup']) == 0
    assert 'price/IHSG/2019.json.gz' not in bucket.objects and keep <= set(bucket.objects)
    assert bucket.puts[-1] == 'state.json' and WAITS == []
    (gc,) = [e for e in logged(capsys) if e['event'] == 'gc']
    assert gc['deleted'] == 1 and gc['not_deleted'] == 0


def test_the_listing_asks_small_pages_and_logs_each_folder_and_each_slow_page(monkeypatch, capsys):
    at = dt.datetime(2026, 10, 25, tzinfo=dt.timezone.utc)
    pages = {None: {'IsTruncated': True, 'NextContinuationToken': 't1', 'Contents': [{'Key': 'v1/price/a', 'LastModified': at, 'Size': 1}]},
             't1': {'IsTruncated': False, 'Contents': [{'Key': 'v1/price/b', 'LastModified': at, 'Size': 2}]}}
    asked = []
    class S3:
        def list_objects_v2(self, **kw):
            asked.append(kw)
            return pages[kw.get('ContinuationToken')]
    b = pub.Bucket.__new__(pub.Bucket)
    b.name, b.s3 = 'bucket', S3()
    monkeypatch.setattr(pub, 'SLOW_PAGE_SECONDS', -1)                    # every page counts as slow
    assert b.list(prefix='price/') == {'price/a': (at, 1), 'price/b': (at, 2)}
    assert [kw['MaxKeys'] for kw in asked] == [pub.LIST_PAGE_KEYS] * 2 == [200, 200]
    lines = logged(capsys)
    assert [(e['prefix'], e['page'], e['keys']) for e in lines if e['event'] == 'list_page_slow'] == [('price/', 0, 1), ('price/', 1, 1)]
    (done,) = [e for e in lines if e['event'] == 'listed']
    assert (done['prefix'], done['pages'], done['keys']) == ('price/', 2, 2) and 'slowest_page_seconds' in done


def test_a_retried_request_names_itself_in_the_log(capsys):
    calls = []
    def call():
        calls.append(1)
        if len(calls) == 1:
            raise client_error('RequestCanceled')
        return 'ok'
    assert pub.retried(call, sleep=lambda s: None, what='list price/ page 3') == 'ok'
    (retry,) = [e for e in logged(capsys) if e['event'] == 'bucket_retry']
    assert retry['request'] == 'list price/ page 3' and retry['error'] == 'ClientError'


def test_a_publisher_used_again_after_a_failed_run_deletes_nothing_a_manifest_still_names(monkeypatch):
    """The failed run's reads are dropped with its manifests; a logos run after it on the same object reads no manifest,
    so it replaces no data file."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    keep = named(bucket) | indexed(bucket)
    p = pub.Publisher(conn, bucket, today=TODAY, get=fake_get())
    put = bucket.put
    bucket.put = lambda key, body, ctype: ((_ for _ in ()).throw(OSError('x')) if key.startswith('manifest/')
                                           else put(key, body, ctype))
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    with pytest.raises(OSError):
        p.run('daily')
    assert p.manifests == {} and p.loaded_named == {}
    bucket.put = put
    p.run('logos')
    assert keep <= set(bucket.objects) and not set(p.replaced) & keep


# ---- ERRORS M301 / EXEC-PRICE-GAP-0917: deletes go in small batches, a failing batch does not stop the others ---------
class BatchS3:
    """delete_objects records each request's keys; `refuse` maps a key to the error code its whole request raises, and
    `report` lists keys the bucket answers as not deleted."""
    def __init__(self, refuse=None, report=()):
        self.requests, self.refuse, self.report, self.lock = [], refuse or {}, set(report), pub.threading.Lock()

    def delete_objects(self, Bucket, Delete):
        keys = [o['Key'] for o in Delete['Objects']]
        with self.lock:
            self.requests.append(keys)
        for k in keys:
            if k in self.refuse:
                raise client_error(self.refuse[k])
        return {'Errors': [{'Key': k} for k in keys if k in self.report]}


def batch_bucket(s3):
    b = pub.Bucket.__new__(pub.Bucket)
    b.name, b.s3 = 'bucket', s3
    return b


def test_delete_sends_batches_of_the_batch_size_and_returns_what_the_bucket_did_not_delete(capsys):
    keys = [f'price/T{i:03}/2026.0123456789abcdef.json.gz' for i in range(2 * pub.DELETE_BATCH_KEYS + 7)]
    s3 = BatchS3(report=['v1/' + keys[5]])
    assert batch_bucket(s3).delete(keys) == [keys[5]]
    assert sorted(len(r) for r in s3.requests) == [7, pub.DELETE_BATCH_KEYS, pub.DELETE_BATCH_KEYS]
    assert sorted(k for r in s3.requests for k in r) == sorted('v1/' + k for k in keys)
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if '"delete_batch"' in line]
    assert len(lines) == 3 and sum(line['keys'] for line in lines) == len(keys) and all('seconds' in line for line in lines)


def test_a_batch_that_keeps_failing_is_returned_and_the_other_batches_are_still_deleted(monkeypatch, capsys):
    monkeypatch.setattr(pub.time, 'sleep', lambda s: None)
    keys = [f'pack/T{i:03}/price.0123456789abcdef.json.gz' for i in range(pub.DELETE_BATCH_KEYS + 3)]
    bad = keys[pub.DELETE_BATCH_KEYS + 1]
    s3 = BatchS3(refuse={'v1/' + bad: 'RequestTimeout'})
    assert batch_bucket(s3).delete(keys) == keys[pub.DELETE_BATCH_KEYS:]
    # the failing batch was asked again after each retry delay; the full batch was asked once and deleted
    assert sum(1 for r in s3.requests if 'v1/' + bad in r) == len(pub.BUCKET_RETRY_DELAYS) + 1
    assert sum(1 for r in s3.requests if len(r) == pub.DELETE_BATCH_KEYS) == 1
    failed = [json.loads(line) for line in capsys.readouterr().out.splitlines() if '"delete_batch_failed"' in line]
    assert len(failed) == 1 and failed[0]['keys'] == 3 and failed[0]['error'] == 'ClientError'


def test_a_refused_batch_is_returned_without_retries_and_no_keys_send_no_request():
    keys = ['price/BBCA/2026.0123456789abcdef.json.gz']
    s3 = BatchS3(refuse={'v1/' + keys[0]: 'AccessDenied'})
    assert batch_bucket(s3).delete(keys) == keys and len(s3.requests) == 1
    assert batch_bucket(s3).delete([]) == [] and len(s3.requests) == 1


# ---- EXEC-INTRADAY-FEATURES C1 (user 2026-11-01): intraday files ----------------------------------------------------
JKT = dt.timezone(dt.timedelta(hours=7))


def bar(t, tf, y, mo, d, h, mi, c):
    """An intraday bar opened at the WIB time given: open c, high c+1, low c-1, close c, volume 100."""
    return (t, tf, dt.datetime(y, mo, d, h, mi, tzinfo=JKT).astimezone(dt.timezone.utc), c, c + 1, c - 1, c, 100.0)


INTRADAY = [bar('BBCA', '5m', 2026, 9, 30, 9, 0, 100.0), bar('BBCA', '5m', 2026, 10, 30, 15, 55, 101.0),
            bar('BBCA', '5m', 2026, 10, 30, 16, 0, 102.0), bar('BBCA', '1h', 2025, 12, 30, 9, 0, 90.0),
            bar('BBCA', '1h', 2026, 10, 30, 15, 0, 101.0), bar('IHSG', '5m', 2026, 10, 30, 16, 0, 7000.0)]
# 15m has no COMPLETE session yet (no bars per year): it is not published
TIMEFRAMES = [('5m', 16017), ('1h', 1766), ('15m', None)]
NOW = dt.datetime(2026, 11, 1, 8, 0, tzinfo=dt.timezone.utc)


def intraday_conn(bars=None, changes=None, now=NOW):
    return FakeConn(PRICES, BROKERS, UNIVERSE, intraday=list(INTRADAY if bars is None else bars), timeframes=TIMEFRAMES,
                    changes=changes, now=now)


def intraday_keys(bucket, ticker='BBCA'):
    m = bucket.get_json(f'manifest/{ticker}.json')
    return {tf: {part: f['key'][len(pub.PREFIX) + 1:] for part, f in s['files'].items()} for tf, s in m.get('intraday', {}).items()}


def test_the_period_is_derived_from_bars_per_year():
    assert pub.intraday_period(16017) == 'month' and pub.intraday_period(5652) == 'month'
    assert pub.intraday_period(1766) == 'year' and pub.intraday_period(504) == 'year'
    at = dt.datetime(2026, 10, 31, 18, 0, tzinfo=dt.timezone.utc)                 # 1 Nov 01:00 WIB
    assert pub.period_start(at, 'month', JKT)[0] == '2026-11'
    assert pub.period_start(at, 'year', JKT) == ('2026', dt.datetime(2026, 1, 1, tzinfo=JKT))


def test_the_intraday_mode_publishes_an_archive_and_the_current_period_of_every_series(monkeypatch):
    monkeypatch.setattr(pub, 'wait', lambda s: None)
    p, conn, bucket = run('intraday', conn=intraday_conn())
    m = bucket.get_json('manifest/BBCA.json')
    assert set(m['intraday']) == {'5m', '1h'}                                    # 15m: no bars per year
    five = m['intraday']['5m']
    assert (five['period'], five['current'], five['bars_per_year'], five['rows']) == ('month', '2026-10', 16017, 3)
    assert (five['timezone'], five['utc_offset_seconds']) == ('Asia/Jakarta', 25200)
    assert five['files']['archive']['rows'] == 1 and five['files']['current']['rows'] == 2
    assert five['files']['current']['from'] == '2026-10-01T00:00:00+07:00' and five['files']['current']['to'] is None
    assert five['last'] == INTRADAY[2][2].isoformat() and five['first'] == INTRADAY[0][2].isoformat()
    one = m['intraday']['1h']
    assert (one['period'], one['current']) == ('year', '2026') and one['files']['archive']['rows'] == 1
    doc = bucket.get_json(intraday_keys(bucket)['5m']['current'])
    assert doc['columns'] == ['t', 'o', 'h', 'l', 'c', 'v'] and doc['t'] == [int(b[2].timestamp()) for b in INTRADAY[1:3]]
    assert doc['c'] == [101.0, 102.0] and doc['part'] == '2026-10'
    assert set(bucket.get_json('manifest/IHSG.json')['intraday']['5m']['files']) == {'current'}
    keys = pub.named_keys(m)                                                    # the cleanup sees them as named
    assert all(k in keys for k in intraday_keys(bucket)['5m'].values())
    assert bucket.get_json('state.json')['intraday_change_seen'] == NOW.isoformat()
    assert pub.verify(conn, bucket, ['BBCA', 'IHSG']) == 0


def test_a_daily_run_republishes_only_the_changed_series_and_a_new_period_moves_the_old_one_to_the_archive(monkeypatch):
    monkeypatch.setattr(pub, 'wait', lambda s: None)
    _, _, bucket = run('intraday', conn=intraday_conn())
    before = intraday_keys(bucket)
    new = bar('BBCA', '5m', 2026, 11, 2, 9, 0, 103.0)
    later = NOW + dt.timedelta(days=1, hours=3)
    conn = intraday_conn(INTRADAY + [new], changes=[('BBCA', '5m', new[2], later - dt.timedelta(hours=1))], now=later)
    puts = len(bucket.puts)
    p, _, bucket = run('daily', conn=conn, bucket=bucket)
    written = [k for k in bucket.puts[puts:] if k.startswith('intraday/')]
    assert sorted(k.split('/')[2].split('.')[0] for k in written) == ['5m-2026-11', '5m-archive']
    five = bucket.get_json('manifest/BBCA.json')['intraday']['5m']
    assert five['current'] == '2026-11' and five['files']['archive']['rows'] == 3 and five['files']['current']['rows'] == 1
    assert intraday_keys(bucket)['1h'] == before['1h']                          # untouched series keep their files
    assert before['5m']['current'] in p.replaced and before['5m']['archive'] in p.replaced
    assert bucket.get_json('state.json')['intraday_change_seen'] == (later - dt.timedelta(hours=1)).isoformat()


def test_a_correction_before_the_current_period_rebuilds_the_archive_and_a_same_period_change_does_not(monkeypatch):
    monkeypatch.setattr(pub, 'wait', lambda s: None)
    _, _, bucket = run('intraday', conn=intraday_conn())
    later = NOW + dt.timedelta(hours=12)
    fixed = [bar('BBCA', '5m', 2026, 9, 30, 9, 0, 99.0)] + INTRADAY[1:]
    conn = intraday_conn(fixed, changes=[('BBCA', '5m', fixed[0][2], later)], now=later)
    run('daily', conn=conn, bucket=bucket)
    assert bucket.get_json(intraday_keys(bucket)['5m']['archive'])['c'] == [99.0]
    same = intraday_conn(fixed[:2] + [bar('BBCA', '5m', 2026, 10, 30, 16, 0, 104.0)] + fixed[3:],
                         changes=[('BBCA', '5m', INTRADAY[2][2], later + dt.timedelta(hours=12))], now=later + dt.timedelta(hours=13))
    puts = len(bucket.puts)
    run('daily', conn=same, bucket=bucket)
    assert [k.split('/')[2].split('.')[0] for k in bucket.puts[puts:] if k.startswith('intraday/')] == ['5m-2026-10']


def test_a_daily_run_without_a_recent_intraday_publication_republishes_every_series(monkeypatch):
    monkeypatch.setattr(pub, 'wait', lambda s: None)
    p, _, bucket = run('daily', conn=intraday_conn())                           # never published: every series
    assert set(bucket.get_json('manifest/BBCA.json')['intraday']) == {'5m', '1h'}
    stale = NOW + dt.timedelta(days=pub.INTRADAY_FULL_AFTER_DAYS + 1)
    conn = intraday_conn(changes=[], now=stale)
    plan, _, seen = pub.Publisher(conn, bucket, today=TODAY).intraday_plan('daily', {'BBCA': 'stock', 'IHSG': 'index'},
                                                                         bucket.get_json('state.json'))
    assert len(plan) == 4 and all(c is None for *_, c in plan) and seen == stale


def test_a_limited_intraday_run_publishes_those_tickers_and_does_not_move_the_change_mark(monkeypatch):
    monkeypatch.setattr(pub, 'wait', lambda s: None)
    conn = intraday_conn()
    bucket = FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('intraday', only=['IHSG'])
    assert 'intraday' in bucket.get_json('manifest/IHSG.json') and bucket.get_json('manifest/BBCA.json') is None
    assert bucket.get_json('state.json')['intraday_change_seen'] is None


def test_verify_finds_an_intraday_file_unlike_sql(monkeypatch):
    monkeypatch.setattr(pub, 'wait', lambda s: None)
    _, _, bucket = run('intraday', conn=intraday_conn())
    changed = INTRADAY[:2] + [bar('BBCA', '5m', 2026, 10, 30, 16, 0, 150.0)] + INTRADAY[3:]
    assert pub.verify(intraday_conn(changed), bucket, ['BBCA']) == 1


# ---- EXEC-FI-TERMINAL (user go 2026-11-01: "Samakan logicnya dengan price IDX") --------------------------------------
FIXED = [('ID10Y', 'yield_to_maturity', '2025-12-30', 6.1, 6.2, 6.0, 6.15, 'i1'),
         ('ID10Y', 'yield_to_maturity', '2026-10-29', 7.1, 7.2, 7.0, 7.15, 'i1'),
         ('ID10Y', 'price', '2026-10-28', 95.0, 95.5, 94.9, 95.2, 'i1'),     # a price date the yield lacks: own dates
         ('US01MY', 'price', '2026-10-29', 4.0, 4.1, 3.9, 4.05, 'i1'),
         ('US01MY', 'yield_to_maturity', '2026-10-29', 4.1, 4.2, 4.0, 4.15, 'i1')]
FIXED_UNIVERSE = [('ID10Y', 'Indonesia 10Y', 'Indonesia', 'percent', 'PCTPAR'),
                  ('US01MY', 'US 1M bill', 'United States', 'percent', 'PCTDY')]


def fi_conn(fixed=FIXED):
    return FakeConn(PRICES, BROKERS, UNIVERSE, fixed=fixed, fixed_universe=FIXED_UNIVERSE)


def test_backfill_publishes_each_bond_dataset_year_with_its_own_dates_and_a_pack():
    _, _, bucket = run('backfill', conn=fi_conn())
    m = bucket.get_json('manifest/ID10Y.json')
    assert m['kind'] == 'fixed_income' and m['instrument']['units'] == {'yield': 'percent', 'price': 'PCTPAR'}
    assert sorted(m['datasets']['yield']['files']) == ['2025', '2026'] and sorted(m['datasets']['price']['files']) == ['2026']
    assert m['datasets']['yield']['first_year'] == 2025 and m['datasets']['yield']['data_through'] == '2026-10-29'
    assert m['datasets']['price']['data_through'] == '2026-10-28'
    y = doc_of(bucket, 'ID10Y', 'yield', 2026)
    assert (y['d'], y['c'], y['v']) == (['2026-10-29'], [7.15], [None]) and y['units']['o'] == 'percent'
    assert doc_of(bucket, 'ID10Y', 'price', 2026)['d'] == ['2026-10-28']          # no invented yield date
    pack = bucket.get_json(m['packs']['yield']['key'][3:])
    assert pack['dataset'] == 'yield-pack' and pack['d'] == ['2025-12-30', '2026-10-29']
    assert bucket.get_json('manifest/US01MY.json')['instrument']['units']['price'] == 'PCTDY'
    ref = bucket.get_json('ref/fixed_income.json.gz')
    assert ref['columns'] == pub.FI_COLUMNS and ref['ticker'] == ['ID10Y', 'US01MY']
    assert (ref['yield_first'][0], ref['yield_last'][0], ref['price_first'][0]) == ('2025-12-30', '2026-10-29', '2026-10-28')
    # the bonds are not stocks: no broker file, no xsection row, not in ref/tickers
    assert not any(k.startswith('broker/ID10Y') for k in bucket.objects)
    assert 'ID10Y' not in bucket.get_json('ref/tickers.json.gz')['ticker']


def test_daily_writes_nothing_for_unchanged_bonds_and_only_the_changed_year_otherwise():
    _, conn, bucket = run('backfill', conn=fi_conn())
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('daily')
    assert p2.written == 0
    # a new session: the current year's yield file and the yield pack, nothing else (2025 and the price untouched)
    conn.fixed = FIXED + [('ID10Y', 'yield_to_maturity', '2026-10-30', 7.15, 7.3, 7.1, 7.25, 'i2')]
    p3 = pub.Publisher(conn, bucket, today=TODAY)
    p3.run('daily')
    assert p3.changed == {('yield', 'ID10Y', 2026), ('pack', 'ID10Y', 'yield')}
    assert p3.written == 2
    assert bucket.get_json('manifest/ID10Y.json')['datasets']['yield']['data_through'] == '2026-10-30'


def test_daily_republishes_an_old_bond_year_a_correction_changed():
    _, conn, bucket = run('backfill', conn=fi_conn())
    conn.fixed = [r[:6] + (6.16, 'i3') if r[2] == '2025-12-30' else r for r in FIXED]   # recovery wrote a revised close
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('daily')
    assert p2.changed == {('yield', 'ID10Y', 2025), ('pack', 'ID10Y', 'yield')}
    assert doc_of(bucket, 'ID10Y', 'yield', 2025)['c'] == [6.16]


def test_a_bond_year_gone_from_the_table_leaves_the_manifest():
    _, conn, bucket = run('backfill', conn=fi_conn())
    conn.fixed = [r for r in FIXED if r[2] != '2025-12-30']
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert sorted(bucket.get_json('manifest/ID10Y.json')['datasets']['yield']['files']) == ['2026']


def test_fixed_income_mode_publishes_only_the_bonds_and_verify_checks_them():
    conn, bucket = fi_conn(), FakeBucket()
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run('fixed_income')
    assert bucket.get_json('manifest/ID10Y.json') and bucket.get_json('manifest/BBCA.json') is None
    _, conn2, bucket2 = run('backfill', conn=fi_conn())
    assert pub.verify(conn2, bucket2) == 0
    conn2.fixed = [r[:6] + (7.5, 'i9') if r[2] == '2026-10-29' and r[0] == 'ID10Y' and r[1] == 'yield_to_maturity' else r
                   for r in FIXED]
    assert pub.verify(conn2, bucket2) == 2                              # the 2026 yield file and the yield pack


def test_the_cleanup_keeps_the_bond_files():
    _, conn, bucket = run('backfill', conn=fi_conn())
    named = pub.named_keys(bucket.get_json('manifest/ID10Y.json'))
    assert named and all(k in bucket.objects for k in named)
    bucket.clock += dt.timedelta(days=2)
    p = pub.Publisher(conn, bucket, today=TODAY, clock=lambda: bucket.clock + dt.timedelta(days=1))
    p.collect_garbage()
    assert all(k in bucket.objects for k in named)


# EXEC-IHSG-FLOW (user go 2026-11-03): an index's broker files come from Feature_05_..._INDEX, with its own date
INDEX_BROKERS = [('IHSG', '2026-01-02', 'AK', 'Foreign', 'Regular', 900.0, 100.0, 9.0, 1.0, False, 30, 4),
                 ('IHSG', '2026-01-02', 'YP', 'Domestic', 'Nego', 50.0, 850.0, 0.5, 8.5, False, 2, 25)]


def test_index_broker_files_come_from_the_index_table():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE, index_brokers=INDEX_BROKERS)
    _, _, bucket = run('backfill', conn)
    doc = doc_of(bucket, 'IHSG', 'broker', 2026)
    assert doc['b'] == ['AK', 'YP'] and doc['bv'] == [900.0, 50.0] and doc['bf'] == [30, 2]
    m = bucket.get_json('manifest/IHSG.json')
    assert m['datasets']['broker']['data_through'] == '2026-01-02'
    assert doc_of(bucket, 'BBCA', 'broker', 2026)['bv'] == [500.0, 0.0]          # a stock still reads Feature 05
    assert any(pub.BROKER_TABLES['index'] in s for s in conn.statements)
    state = json.loads(bucket.objects['state.json'])
    assert state['broker_through'] == '2026-01-02' and state['broker_index_through'] == '2026-01-02'
    assert pub.verify(conn, bucket, ['IHSG']) == 0                              # checked against the INDEX table


def test_daily_picks_up_a_new_index_date_on_its_own():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE, index_brokers=INDEX_BROKERS)
    _, _, bucket = run('backfill', conn)
    conn.index_brokers.append(('IHSG', '2026-01-05', 'AK', 'Foreign', 'Regular', 70.0, 0.0, 0.7, 0.0, False, 3, 0))
    p2, _, _ = run('daily', conn, bucket)
    assert doc_of(bucket, 'IHSG', 'broker', 2026)['d'][-1] == '2026-01-05'
    assert bucket.get_json('manifest/IHSG.json')['datasets']['broker']['data_through'] == '2026-01-05'
    assert json.loads(bucket.objects['state.json'])['broker_through'] == '2026-01-02'   # the stocks' date is unchanged


def test_an_index_without_index_rows_has_no_broker_dataset():
    _, _, bucket = run('backfill', FakeConn(PRICES, BROKERS, UNIVERSE))
    assert 'broker' not in bucket.get_json('manifest/IHSG.json')['datasets']


def test_broker_range_includes_the_index():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE, index_brokers=INDEX_BROKERS)
    _, _, bucket = run('backfill', FakeConn(PRICES, BROKERS, UNIVERSE))
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('broker-range', '2026-01-01', '2026-12-31', ['IHSG'])
    assert doc_of(bucket, 'IHSG', 'broker', 2026)['b'] == ['AK', 'YP']


def test_the_first_daily_run_after_the_change_publishes_every_index_year():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE, index_brokers=INDEX_BROKERS + [
        ('IHSG', '2025-06-02', 'AK', 'Foreign', 'Regular', 10.0, 0.0, 0.1, 0.0, False, 1, 0)])
    _, _, bucket = run('backfill', FakeConn(PRICES, BROKERS, UNIVERSE))          # a bucket from before EXEC-IHSG-FLOW
    state = json.loads(bucket.objects['state.json'])
    state.pop('broker_index_through', None)
    bucket.objects['state.json'] = json.dumps(state).encode()
    run('daily', conn, bucket)
    assert doc_of(bucket, 'IHSG', 'broker', 2026)['b'] == ['AK', 'YP']
    assert doc_of(bucket, 'IHSG', 'broker', 2025)['d'] == ['2025-06-02']
    assert json.loads(bucket.objects['state.json'])['broker_index_through'] == '2026-01-02'


def test_the_loaders_hold_the_lock_the_publisher_waits_for():
    """EXEC-PUBLISH-FLOW: the write lock's name is written in each loader; a rename on one side only would let the
    publisher read a half-written table."""
    apps = Path(__file__).resolve().parents[2]
    for loader in ('idx-price-cron/price_update.py', 'fixed-income-price-cron/fixed_income_update.py'):
        source = (apps / loader).read_text()
        assert f'PUBLISH_WRITE_LOCK = "{pub.WRITE_LOCK}"' in source, loader
        assert 'hold_publish_write_lock(connection)' in source, loader
    intraday = (apps / 'idx-price-cron/intraday_update.py').read_text()
    assert 'pu.hold_publish_write_lock(conn)' in intraday and 'pu.release_publish_write_lock(conn)' in intraday


# ---- EXEC-SCREENER-FLOW-CANDLES P4 (user 2026-11-07): broker day files for the Screener (P4_BROKER_DAYS.md) ----------
DAY_UNIVERSE = UNIVERSE + [('AALI', 'Astra Agro Lestari', 'stock', 'Consumer', 'Plantation', 'common')]
DAY_STOCKS = ['AALI', 'BBCA']                                  # kind 'stock' of DAY_UNIVERSE (IHSG is an index)


def day_rows(d):
    """Feature 05 rows of one date (ticker, date, broker, investor, board, bv, sv, bl, sl, gap, bf, sf): two stocks of the
    universe, an index and a code outside the universe (neither is in the file)."""
    return [('BBCA', d, 'YP', 'Domestic', 'Regular', 0.0, 500.0, 0.0, 4.5, True, 0, 2),
            ('BBCA', d, 'AK', 'Foreign', 'Regular', 500.0, 0.0, 5.0, 0.0, False, 3, 0),
            ('AALI', d, 'YP', 'Foreign', 'Nego', 1234.5, 1000.0, 1.0, 2.0, False, None, 1),
            ('IHSG', d, 'AK', 'Domestic', 'Regular', 7.0, 7.0, 1.0, 1.0, False, 1, 1),
            ('GONE', d, 'AK', 'Domestic', 'Regular', 9.0, 9.0, 1.0, 1.0, False, 1, 1)]


def day_conn(dates=('2026-01-02', '2026-01-05')):
    return FakeConn(PRICES, [r for d in dates for r in day_rows(d)], DAY_UNIVERSE)


def days(bucket):
    """{date: entry} of the broker day files state.json indexes."""
    return {n[len('broker-'):]: e for n, e in bucket.get_json('state.json')['xsection'].items() if n.startswith('broker-')}


def day_doc(bucket, d):
    return bucket.get_json(days(bucket)[d]['key'][len('v1/'):])


def day_puts(bucket, since=0):
    return [k for k in bucket.puts[since:] if k.startswith('xsection/broker-')]


def day_reads(conn, since=0):
    """The dates whose rows a run read (BROKER_DAY_SQL)."""
    return [p[0] for s, p in conn.calls[since:] if s == pub.BROKER_DAY_SQL]


def finished(hour):
    return dt.datetime(2026, 11, 7, hour, 0, tzinfo=dt.timezone.utc)


def test_the_window_is_the_newest_trade_dates_read_by_an_index_skip_scan(monkeypatch):
    sql = pub.BROKER_DAYS_WINDOW_SQL
    assert sql.startswith('WITH RECURSIVE') and 'max(f.trade_date)' in sql and 'f.trade_date < d.trade_date' in sql
    assert 'DISTINCT' not in sql.upper() and pub.BROKER_DAY_SESSIONS == 60                       # K1
    dates = [f'2026-01-{d:02d}' for d in range(2, 9)]
    monkeypatch.setattr(pub, 'BROKER_DAY_SESSIONS', 5)
    conn, bucket = day_conn(dates), FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('broker-days')
    assert sorted(days(bucket)) == dates[-5:] and (pub.BROKER_DAYS_WINDOW_SQL, (5,)) in conn.calls
    assert not any('DISTINCT' in s and pub.F05 in s for s in conn.statements)     # never a DISTINCT over Feature 05
    assert sorted(day_reads(conn)) == dates[-5:]                          # one statement per date of the window


def test_a_broker_day_file_holds_the_stock_rows_in_key_order_with_whole_numbers_as_integers():
    conn, bucket = day_conn(('2026-01-02',)), FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('backfill')
    e, doc = days(bucket)['2026-01-02'], day_doc(bucket, '2026-01-02')
    assert e['key'] == f"v1/xsection/broker-2026-01-02.{e['sha256'][:16]}.json.gz"
    assert (e['rows'], e['as_of'], set(e)) == (3, '2026-01-02', {'key', 'sha256', 'bytes', 'rows', 'as_of'})
    assert (doc['schema_version'], doc['dataset'], doc['name'], doc['date'], doc['source']) == (
        1, 'xsection', 'broker-2026-01-02', '2026-01-02', 'Feature_05_Foreign_Domestic_Broker_Detail')
    # the stocks only (not the index, not a code outside the universe), by ticker, broker, investor type, board
    assert doc['tickers'] == [{'t': 'AALI', 'rows': 1}, {'t': 'BBCA', 'rows': 2}]
    assert doc['brokers'] == ['AK', 'YP'] and doc['investor_types'] == ['Domestic', 'Foreign']
    assert doc['boards'] == ['Regular', 'Nego', 'Tunai'] and doc['columns'] == pub.BROKER_DAY_COLUMNS
    assert (doc['b'], doc['i'], doc['m']) == ([1, 0, 1], [1, 1, 0], [1, 0, 0])
    assert (doc['bv'], doc['sv'], doc['bl'], doc['sl']) == ([1234.5, 500, 0], [1000, 0, 500], [1, 5, 0], [2, 0, 4.5])
    assert (doc['bf'], doc['sf']) == ([None, 3, 0], [1, 0, 2]) and doc['gap'] == [['BBCA', 'Regular']]
    raw = gzip.decompress(bucket.objects[e['key'][3:]]).decode()
    assert '"bv":[1234.5,500,0]' in raw and '"sl":[2,0,4.5]' in raw                  # 500, not 500.0
    assert '"check":{"rows":3,"bv":1734.5,"sv":1500.0}' in raw                       # the sums stay floats
    assert set(doc['means']) >= set(pub.BROKER_DAY_COLUMNS) | {'tickers', 'gap', 'check'}
    assert pub.whole(1234.0) == 1234 and type(pub.whole(1234.0)) is int and pub.whole(0.5) == 0.5
    assert pub.whole(None) is None and pub.encode(doc) == pub.encode(pub.broker_day_doc('2026-01-02', [
        (r[0], *r[2:]) for r in day_rows('2026-01-02') if r[0] in DAY_STOCKS]))        # deterministic, any input order


def test_daily_fills_the_window_once_then_builds_only_a_new_date():
    conn, bucket = day_conn(), FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('daily', sweep=False)          # the first fill: no entry yet
    first = days(bucket)
    assert sorted(first) == ['2026-01-02', '2026-01-05'] and sorted(day_reads(conn)) == sorted(first)
    conn.brokers += day_rows('2026-01-06')
    n, c = len(bucket.puts), len(conn.calls)
    pub.Publisher(conn, bucket, today=TODAY).run('daily', sweep=False)
    now = days(bucket)
    assert {d: now[d] for d in first} == first and day_reads(conn, c) == ['2026-01-06']
    assert [p for s, p in conn.calls[c:] if s == pub.BROKER_DAY_STAMPS_SQL] == [(['2026-01-06'], DAY_STOCKS)]
    assert day_puts(bucket, n) == [now['2026-01-06']['key'][3:]] and now['2026-01-06']['as_of'] == '2026-01-06'
    stamps = bucket.get_json('state.json')['broker_day_stamps']
    assert sorted(stamps) == ['2026-01-02', '2026-01-05', '2026-01-06'] and stamps['2026-01-06'].startswith('rows=3;bv=1734.5;sv=1500.0;h=')


def test_a_finished_broker_round_rebuilds_the_dates_it_changed_once(capsys):
    conn, bucket = day_conn(), FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('backfill')
    before = days(bucket)
    conn.brokers = [r[:5] + (r[5] + 1,) + r[6:] if r[1] == '2026-01-02' and r[0] == 'BBCA' and r[2] == 'AK' else r
                    for r in conn.brokers]
    # a failed round and a VERIFY round are not taken into account; dates outside the window and other text are left out
    conn.broker_rounds = [(finished(1), 'APPLY', 'FAILED', ['2026-01-05']), (finished(2), 'VERIFY', 'SUCCESS', ['2026-01-05']),
                          (finished(3), 'APPLY', 'SUCCESS', ['2026-01-02', '2025-01-01', 'x'])]
    seen = during_wait(bucket)
    capsys.readouterr()
    pub.Publisher(conn, bucket, today=TODAY).run('daily', sweep=False)
    after, state = days(bucket), bucket.get_json('state.json')
    assert after['2026-01-02']['key'] != before['2026-01-02']['key'] and after['2026-01-05'] == before['2026-01-05']
    assert day_doc(bucket, '2026-01-02')['bv'][1] == 501 and state['broker_days_checked_at'] == finished(3).isoformat()
    old = before['2026-01-02']['key'][3:]
    assert old in seen[0] and old not in bucket.objects                   # one active copy: the old file goes after the wait
    line = events(capsys, 'broker_days')[0]
    assert line['reasons'] == {'round': ['2026-01-02']} and line['built'] == line['uploaded'] == ['2026-01-02']
    assert (line['first'], line['last'], line['sessions'], line['carried'], line['dropped']) == ('2026-01-02', '2026-01-05', 2, 1, [])
    assert {'bytes', 'seconds'} <= set(line)
    c = len(conn.calls)
    pub.Publisher(conn, bucket, today=TODAY).run('daily', sweep=False)  # nothing newer: no date is read again
    assert day_reads(conn, c) == [] and days(bucket) == after
    assert [p for s, p in conn.calls[c:] if s == pub.BROKER_ROUNDS_SQL] == [(finished(3).isoformat(),)]


def test_a_round_date_whose_rows_did_not_change_is_read_but_not_put_again():
    conn, bucket = day_conn(), FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('backfill')
    before = days(bucket)
    conn.broker_rounds = [(finished(3), 'APPLY', 'SUCCESS', ['2026-01-02'])]
    n, c = len(bucket.puts), len(conn.calls)
    pub.Publisher(conn, bucket, today=TODAY).run('daily', sweep=False)
    assert day_reads(conn, c) == ['2026-01-02'] and day_puts(bucket, n) == [] and days(bucket) == before


def test_only_the_sweep_run_compares_the_stamps_and_rebuilds_a_date_changed_outside_a_round():
    conn, bucket = day_conn(), FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('backfill')
    before = days(bucket)
    conn.brokers = [r[:6] + (r[6] + 2,) + r[7:] if r[1] == '2026-01-05' and r[0] == 'BBCA' else r for r in conn.brokers]
    c = len(conn.calls)
    pub.Publisher(conn, bucket, today=TODAY).run('daily', sweep=False)
    assert days(bucket) == before and not any(s == pub.BROKER_DAY_STAMPS_SQL for s, _ in conn.calls[c:])
    c = len(conn.calls)
    pub.Publisher(conn, bucket, today=TODAY).run('daily', sweep=True)
    after = days(bucket)
    assert after['2026-01-05']['key'] != before['2026-01-05']['key'] and after['2026-01-02'] == before['2026-01-02']
    # one aggregate over the window, then the one date whose stamp differs
    assert [p for s, p in conn.calls[c:] if s == pub.BROKER_DAY_STAMPS_SQL] == [(['2026-01-02', '2026-01-05'], DAY_STOCKS)]
    assert day_reads(conn, c) == ['2026-01-05']
    assert bucket.get_json('state.json')['broker_day_stamps']['2026-01-05'].startswith('rows=3;bv=1734.5;sv=1504.0;h=')
    c = len(conn.calls)
    pub.Publisher(conn, bucket, today=TODAY).run('daily', sweep=True)    # the stamps agree now: nothing is rebuilt
    assert day_reads(conn, c) == [] and days(bucket) == after


def test_the_sweep_stamp_sees_a_change_of_any_column_with_unchanged_value_sums():
    """QA unit B, QA2 D1 (2026-11-07): lots, a transaction count, the gap flag, or an investor type swapped with the
    value sums unchanged are each a changed stamp, so the sweep rebuilds the date."""
    for change in (lambda r: r[:7] + (r[7] + 1,) + r[8:],                         # buy lots
                   lambda r: r[:10] + ((r[10] or 0) + 1,) + r[11:],               # buy transactions
                   lambda r: r[:9] + (not r[9],) + r[10:],                        # the gap flag
                   lambda r: r[:3] + ('Foreign' if r[3] == 'Domestic' else 'Domestic',) + r[4:]):   # investor type
        conn, bucket = day_conn(), FakeBucket()
        pub.Publisher(conn, bucket, today=TODAY).run('backfill')
        before = days(bucket)
        hit = next(k for k, r in enumerate(conn.brokers) if r[1] == '2026-01-05')
        conn.brokers = [change(r) if k == hit else r for k, r in enumerate(conn.brokers)]
        c = len(conn.calls)
        pub.Publisher(conn, bucket, today=TODAY).run('daily', sweep=True)
        assert day_reads(conn, c) == ['2026-01-05']
        assert days(bucket)['2026-01-05']['key'] != before['2026-01-05']['key']


def test_an_entry_outside_the_window_is_dropped_and_its_object_deleted_after_the_wait(monkeypatch, capsys):
    monkeypatch.setattr(pub, 'BROKER_DAY_SESSIONS', 2)
    conn, bucket = day_conn(), FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('backfill')
    old = days(bucket)['2026-01-02']['key'][3:]
    conn.brokers += day_rows('2026-01-06')
    seen = during_wait(bucket)
    capsys.readouterr()
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run('daily', sweep=False)
    assert sorted(days(bucket)) == ['2026-01-05', '2026-01-06']
    assert sorted(bucket.get_json('state.json')['broker_day_stamps']) == ['2026-01-05', '2026-01-06']
    assert old in seen[0] and old in p.replaced and old not in bucket.objects
    assert events(capsys, 'broker_days')[0]['dropped'] == ['broker-2026-01-02']


def test_a_date_that_fails_keeps_its_previous_entry_and_the_run_goes_on(capsys):
    conn, bucket = day_conn(), FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('backfill')
    before, stamps = days(bucket), bucket.get_json('state.json')['broker_day_stamps']
    conn.brokers = [r[:5] + (r[5] + 1,) + r[6:] for r in conn.brokers]
    conn.broker_rounds = [(finished(3), 'APPLY', 'SUCCESS', ['2026-01-02', '2026-01-05'])]
    rows = conn._rows
    conn._rows = lambda sql, params: ((_ for _ in ()).throw(pub.psycopg.OperationalError('password=x'))
                                      if sql == pub.BROKER_DAY_SQL and params[0] == '2026-01-02' else rows(sql, params))
    capsys.readouterr()
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run('daily', sweep=False)
    out, after, state = capsys.readouterr().out, days(bucket), bucket.get_json('state.json')
    assert after['2026-01-02'] == before['2026-01-02'] and after['2026-01-05']['key'] != before['2026-01-05']['key']
    assert state['broker_day_stamps']['2026-01-02'] == stamps['2026-01-02']          # the kept file's stamp
    assert state['broker_days_checked_at'] is None                                    # the round is read again next run
    assert p.broker_days_failed == ['2026-01-02'] and p.xsection_failed == [] and bucket.puts[-1] == 'state.json'
    failed = [e for e in map(json.loads, out.splitlines()) if e['event'] == 'broker_day_failed']
    assert failed == [{'event': 'broker_day_failed', 'date': '2026-01-02', 'reason': 'round', 'error': 'OperationalError',
                       'kept': before['2026-01-02']['key']}] and 'password' not in out
    conn._rows = rows
    pub.Publisher(conn, bucket, today=TODAY).run('daily', sweep=False)
    assert days(bucket)['2026-01-02']['key'] != before['2026-01-02']['key']
    assert bucket.get_json('state.json')['broker_days_checked_at'] == finished(3).isoformat()


def test_a_broker_day_object_missing_from_the_bucket_is_put_again():
    conn, bucket = day_conn(('2026-01-02',)), FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('backfill')
    key = days(bucket)['2026-01-02']['key'][3:]
    body = bucket.objects.pop(key)                                    # deleted by hand: the index names a missing object
    pub.Publisher(conn, bucket, today=TODAY).run('daily', sweep=False)
    assert bucket.objects[key] == body and days(bucket)['2026-01-02']['key'] == f'v1/{key}'


def test_verify_checks_every_broker_day_file_against_sql(capsys):
    conn, bucket = day_conn(), FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('backfill')
    assert pub.verify(conn, bucket) == 0
    # a lot count the yearly broker file does not sum: only the broker day file of that date differs
    conn.brokers = [r[:7] + (r[7] + 0.5,) + r[8:] if r[1] == '2026-01-05' and r[0] == 'AALI' else r for r in conn.brokers]
    capsys.readouterr()
    assert pub.verify(conn, bucket) == 1
    (bad,) = [e for e in events(capsys, 'verify_mismatch')]
    assert bad['name'] == 'broker-2026-01-05' and 'first difference at row 0' in bad['problems'][0]
    conn.brokers = [r for r in conn.brokers if not (r[1] == '2026-01-05' and r[0] == 'AALI')]     # a row gone from SQL
    assert pub.verify(conn, bucket) == 2                                  # that file and the yearly broker file


def test_the_broker_days_mode_rebuilds_every_window_date_and_the_other_modes_carry_the_entries():
    conn, bucket = day_conn(), FakeBucket()
    pub.Publisher(conn, bucket, today=TODAY).run('backfill')
    state = bucket.get_json('state.json')
    mine = lambda s: ({n: e for n, e in s['xsection'].items() if n.startswith('broker-')}, s['broker_day_stamps'],
                      s['broker_days_checked_at'])
    statements = (pub.BROKER_DAYS_WINDOW_SQL, pub.BROKER_DAY_SQL, pub.BROKER_DAY_STAMPS_SQL, pub.BROKER_ROUNDS_SQL)
    for mode, args in (('logos', ()), ('events', ()), ('packs', ()), ('intraday', ()), ('broker-range', ('2026-01-01', '2026-12-31'))):
        c = len(conn.calls)
        pub.Publisher(conn, bucket, today=TODAY, get=fake_get()).run(mode, *args)
        assert mine(bucket.get_json('state.json')) == mine(state), mode
        assert not any(s in statements for s, _ in conn.calls[c:]), mode
    n, c = len(bucket.puts), len(conn.calls)
    pub.Publisher(conn, bucket, today=TODAY).run('broker-days')
    assert sorted(day_reads(conn, c)) == ['2026-01-02', '2026-01-05'] and day_puts(bucket, n) == []   # same bytes
    assert not any(k.startswith(('price/', 'broker/', 'events/', 'pack/', 'manifest/', 'xsection/price.', 'xsection/actions.'))
                   for k in bucket.puts[n:])
    assert mine(bucket.get_json('state.json')) == mine(state)
    # terminal-api serves neither publisher-private field (bucket.py STATE_FIELDS)
    spec = importlib.util.spec_from_file_location('terminal_api_bucket', ROOT / 'apps/terminal-api/app/bucket.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    assert not {'broker_days_checked_at', 'broker_day_stamps'} & set(reader.STATE_FIELDS)
    assert reader.xsection_index(state['xsection']) == state['xsection']               # every broker day entry served


# ---- EXEC-SCREENER-STOCK-LISTS: the stock_lists reference file ----------------------------------------------------------
def test_the_stock_lists_reference_file_holds_every_enabled_list_with_its_current_members_and_is_indexed():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    doc = bucket.get_json('ref/stock_lists.json.gz')
    assert doc['columns'] == ['list_key', 'kind', 'code', 'name', 'definition', 'as_of', 'members']
    assert doc['list_key'] == ['INDEX:550', 'KONGLO:1', 'KONGLO:2'] and doc['kind'] == ['INDEX', 'KONGLO', 'KONGLO']
    assert doc['members'] == [['BBCA', 'BBRI'], ['BBCA'], []]                  # a list before its first round: none
    assert doc['as_of'] == ['2026-11-09T13:31:48+00:00', '2026-11-09T13:31:48+00:00', None]
    e = refs(bucket)['stock_lists']
    assert e['rows'] == 3 and bucket.objects[e['key'][len(pub.PREFIX) + 1:]] == bucket.objects['ref/stock_lists.json.gz']
    # the statement is read-only and names only the two tables (no history, no write)
    assert 'Stock_List_Member_History' not in pub.STOCK_LISTS_SQL and pub.STOCK_LISTS_SQL.lstrip().startswith('SELECT')


def test_missing_stock_list_tables_leave_that_file_out_and_the_other_reference_files_unchanged():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    conn.stock_lists = None                                                    # an older database without the tables
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    assert 'ref/stock_lists.json.gz' not in bucket.objects and 'stock_lists' not in refs(bucket)
    assert {'tickers', 'brokers'} <= set(refs(bucket))
    ok = FakeBucket()
    at(ok, FakeConn(PRICES, BROKERS, UNIVERSE), 'backfill', 0)
    assert bucket.objects['ref/tickers.json.gz'] == ok.objects['ref/tickers.json.gz']
