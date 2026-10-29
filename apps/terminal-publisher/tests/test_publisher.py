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
    def __init__(self, prices, brokers, universe, events=None, actions=None):
        self.prices, self.brokers, self.universe = prices, brokers, universe
        self.events = list(EVENTS if events is None else events)
        self.actions = list(ACTIONS if actions is None else actions)
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
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

    def _rows(self, sql, params):
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
            return [(len(r), min(x[1] for x in r), max(x[1] for x in r), sum(x[5] + x[6] for x in r))]
        if 'min(trade_date)' in sql:
            return [(min(r[1] for r in self.brokers),)]
        if 'IDX_Broker_Profile' in sql:
            return [('AK', 'UBS', 'Foreign'), ('YP', 'Mirae', 'Domestic')]
        if 'min(date)' in sql:
            return [(min(r[1] for r in self.prices),)]
        if 'max(date)' in sql:
            return [(max(r[1] for r in self.prices),)]
        if 'max(trade_date)' in sql:
            return [(max(r[1] for r in self.brokers),)]
        if 'DISTINCT ticker' in sql:
            return sorted({(r[0], int(r[1][:4])) for r in self.brokers if r[1] > params[0]})
        raise AssertionError(sql)


PRICES = [('BBCA', '2025-12-30', 100.0, 110.0, 95.0, 105.0, 1000.0),
          ('BBCA', '2026-01-02', 105.0, 106.0, 101.0, 102.0, 900.0),
          ('IHSG', '2026-01-02', 7000.0, 7100.0, 6950.0, 7050.0, None)]
BROKERS = [('BBCA', '2026-01-02', 'AK', 'Foreign', 'Regular', 500.0, 0.0, 5.0, 0.0, False),
           ('BBCA', '2026-01-02', 'YP', 'Domestic', 'Regular', 0.0, 500.0, 0.0, 4.5, True)]
# the 17 display columns, then source_payload and the two closes of EVENTS_SQL
EVENTS = [('BBCA', '2026-03-10', 'EX_DATE', 'CORPORATE_ACTION', 'DIVIDEND', None, None, None, None, None, None, None,
           None, None, 250.0, None, None, None, {'dividend_value': '250', 'dividend_currency': 'CURRENCY_IDR', 'dividend_cumdate': '2026-03-09', 'dividend_exdate': '2026-03-10', 'dividend_recdate': '2026-03-11', 'dividend_paydate': ''}, 10000.0, None),
          ('BBCA', '2026-05-02', 'TRANSACTION_DATE', 'INSIDER', 'INSIDER_TRANSACTION', 'BUY', 'A. Holder', 'Director',
           'YP', None, 10000.0, 1.25, 0.01, 'OK', 9000.0, False, 90000000.0, 'KSEI', None, None, None),
          ('GONE', '2026-01-02', 'EX_DATE', 'CORPORATE_ACTION', 'DIVIDEND', None, None, None, None, None, None, None,
           None, None, 10.0, None, None, None, {}, None, None)]
UNIVERSE = [('BBCA', 'Bank Central Asia', 'stock', 'Finance', 'Banks'), ('IHSG', 'Composite', 'index', None, None)]
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
    conn.brokers = BROKERS + [('BBCA', '2026-01-05', 'AK', 'Foreign', 'Regular', 10.0, 0.0, 0.1, 0.0, False)]
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
    brokers = BROKERS + [('BBCA', '2020-06-03', 'AK', 'Foreign', 'Regular', 1.0, 0.0, 0.01, 0.0, False)]
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
    assert doc['columns'] == ['ticker', 'name', 'type', 'sector', 'industry']
    assert doc['sector'] == ['Finance', None] and doc['industry'] == ['Banks', None]


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
    conn = FakeConn(PRICES, BROKERS + [('BBCA', '2016-01-04', 'AK', 'Foreign', 'Regular', 1.0, 0.0, 0.01, 0.0, False)],
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
    conn.brokers = BROKERS + [('BBCA', '2022-03-01', 'YU', 'Domestic', 'Regular', 5.0, 1.0, 0.5, 0.1, False)]
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
    p3 = pub.Publisher(conn, bucket, today=TODAY)
    p3.run('daily')
    assert ('price', 'BBCA', 2025) not in p3.changed and ('pack', 'BBCA', 'price') in p3.changed
    assert doc_of(bucket, 'BBCA', 'pack', 'price')['o'][0] == 99.0
    assert key_of(bucket, 'BBCA', 'pack', 'price') != old and bucket.objects[old] == old_bytes   # a new object (M250)
    entry, doc = xsection(bucket, 'price')
    sha = bucket.get_json('manifest/BBCA.json')['packs']['price']['sha256']                  # the manifest was saved
    assert (sha == hashlib.sha256(bucket.objects[key_of(bucket, 'BBCA', 'pack', 'price')]).hexdigest()
            == doc['tickers'][0]['pack_sha256'])
    assert doc['o'][0] == 99.0 and pub.verify(conn, bucket) == 0


def test_the_xsection_files_are_written_before_the_state_json_that_indexes_them():
    _, conn, bucket = run('backfill')
    state = bucket.get_json('state.json')
    assert sorted(state['xsection']) == ['actions', 'price'] and bucket.puts[-1] == 'state.json'
    for name, e in state['xsection'].items():
        key = e['key'][len('v1/'):]
        assert re.fullmatch(rf'xsection/{name}\.{e["sha256"][:16]}\.json\.gz', key)          # content-addressed
        assert key in bucket.puts[:-1]                                                        # before state.json
        body = bucket.objects[key]
        assert (len(body), hashlib.sha256(body).hexdigest()) == (e['bytes'], e['sha256'])
        assert e['rows'] == len(bucket.get_json(key)['t'])
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
    assert sorted(pub.xsection_entries(raw)) == ['actions', 'price', 'stamped']


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
    """The xsection cleanup is collect_garbage's (daily runs, before the first write): an object goes on the first daily
    run after the run that stopped naming it, so a reader holding the previous index keeps its file."""
    _, conn, bucket = run('backfill')
    k1 = xsection(bucket, 'price')[0]['key'][3:]
    actions = xsection(bucket, 'actions')[0]['key'][3:]
    bucket.objects['xsection/README.txt'] = b'not a file of the family'
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    k2 = xsection(bucket, 'price')[0]['key'][3:]
    assert k2 != k1 and k1 in bucket.objects                          # k1 is the previous index's: a reader may hold it
    pub.Publisher(conn, bucket, today=TODAY).run('logos')             # a carry-forward run deletes nothing
    assert k1 in bucket.objects
    conn.prices = conn.prices + [('BBCA', '2026-01-06', 101.0, 104.0, 100.0, 103.0, 700.0)]
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    k3 = xsection(bucket, 'price')[0]['key'][3:]
    assert k1 not in bucket.objects and {k2, k3, actions, 'xsection/README.txt'} <= set(bucket.objects)


def test_an_indexed_object_missing_from_the_bucket_is_put_again():
    _, conn, bucket = run('backfill')
    key = xsection(bucket, 'price')[0]['key'][3:]
    body = bucket.objects.pop(key)                                    # deleted by hand: the index names a missing object
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    assert bucket.objects[key] == body and xsection(bucket, 'price')[0]['key'] == f'v1/{key}'


def test_a_bucket_that_cannot_list_or_delete_prunes_nothing_and_still_publishes():
    _, conn, bucket = run('backfill')
    k1 = xsection(bucket, 'price')[0]['key'][3:]
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    pub.Publisher(conn, bucket, today=TODAY).run('daily')
    k2 = xsection(bucket, 'price')[0]['key'][3:]
    conn.prices = conn.prices + [('BBCA', '2026-01-06', 101.0, 104.0, 100.0, 103.0, 700.0)]
    bucket.list = lambda deadline=None, prefix='': (_ for _ in ()).throw(PermissionError())    # no ListObjectsV2
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run('daily')
    k3 = xsection(bucket, 'price')[0]['key'][3:]
    assert p.xsection_failed == [] and {k1, k2, k3} <= set(bucket.objects) and bucket.puts[-1] == 'state.json'
    del bucket.list                                                   # listing works again, deleting does not
    bucket.delete = lambda keys: (_ for _ in ()).throw(PermissionError())
    conn.prices = conn.prices + [('BBCA', '2026-01-07', 103.0, 104.0, 100.0, 102.0, 600.0)]
    p = pub.Publisher(conn, bucket, today=TODAY)
    p.run('daily')
    assert p.xsection_failed == [] and {k1, k2, k3} <= set(bucket.objects) and bucket.puts[-1] == 'state.json'


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
    assert sorted(bucket.get_json('state.json')['xsection']) == ['actions', 'price']
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


def test_a_changed_file_is_a_new_object_and_the_bytes_the_old_manifest_names_stay_until_the_next_run():
    """M250: during a run, a reader holding the previous manifest still downloads exactly the bytes it names."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    old = {k: bucket.objects[k] for k in named(bucket) | indexed(bucket)}     # the manifests' and the index's objects
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    conn.brokers = BROKERS + [('BBCA', '2026-01-05', 'AK', 'Foreign', 'Regular', 10.0, 0.0, 0.1, 0.0, False)]
    conn.events = EVENTS + [('BBCA', '2026-06-01', 'EX_DATE', 'CORPORATE_ACTION', 'DIVIDEND') + (None,) * 9 +
                            (5.0, None, None, None, {}, None, None)]
    p = at(bucket, conn, 'daily', 2)
    replaced = set(old) - named(bucket) - indexed(bucket)
    # every family changed; the xsection `price` file too (`actions` reads ACTIONS, unchanged here)
    assert {k.split('/')[0] for k in replaced} == {'price', 'broker', 'events', 'pack', 'xsection'}
    assert [k for k in replaced if k.startswith('xsection/')][0].startswith('xsection/price.')
    assert p.written == len(replaced)
    assert all(bucket.objects[k] == body for k, body in old.items())     # nothing the old manifest names was touched
    at(bucket, conn, 'daily', 4)                                          # the next run: no reader can hold it now
    assert not replaced & set(bucket.objects) and named(bucket) | indexed(bucket) <= set(bucket.objects)
    assert sorted(bucket.deleted) == sorted(replaced)


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
    at(bucket, conn, 'daily', 4)
    assert key_of(bucket, 'BBCA', 'price', 2026) != legacy and legacy in bucket.objects
    at(bucket, conn, 'daily', 6)
    assert legacy not in bucket.objects


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
    assert 'price/IHSG/2019.json.gz' in bucket.objects and not bucket.deleted


# ---- one mechanism for both: the xsection family under content keys and collect_garbage (M250 x EXEC-SCREENER) -------
def price_key(bucket):
    return xsection(bucket, 'price')[0]['key'][len(pub.PREFIX) + 1:]


def test_the_xsection_cleanup_waits_for_the_grace_so_two_runs_minutes_apart_keep_the_previous_index(capsys):
    """A manual run right after a scheduled one deletes nothing: a reader of the index before it keeps its files."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = price_key(bucket)
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    at(bucket, conn, 'daily', 2)
    k2 = price_key(bucket)
    conn.prices = conn.prices + [('BBCA', '2026-01-06', 101.0, 104.0, 100.0, 103.0, 700.0)]
    at(bucket, conn, 'daily', 2.25)                                       # 15 minutes after the last run finished
    k3 = price_key(bucket)
    assert len({k1, k2, k3}) == 3 and {k1, k2, k3} <= set(bucket.objects)
    assert events(capsys, 'gc_skipped')[0]['grace'] == pub.GC_GRACE_SECONDS
    at(bucket, conn, 'daily', 4)
    assert k1 not in bucket.objects and k2 not in bucket.objects and k3 in bucket.objects
    assert {k1, k2} <= set(bucket.deleted)


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
    assert gc['xsection_named'] == 2 and gc['kept_newer_than_last_run'] == 1
    assert indexed(bucket) | {newer, 'xsection/notes.txt'} <= set(bucket.objects)
    # a state.json without an index (a publisher before the xsection writer, or a rollback to one) names no xsection
    # file: no xsection object is deleted until an index names one again
    state = bucket.get_json('state.json')
    state.pop('xsection')
    bucket.objects['state.json'] = json.dumps(state).encode()             # same LastModified
    plant(bucket, stale, -24)
    assert p.collect_garbage() == 0 and stale in bucket.objects and bucket.deleted == [stale]


def test_content_that_returns_to_an_object_the_cleanup_deleted_is_put_again():
    """EXEC-PUBLISHER-SPEED: the cleanup runs after state.json. Content that returns to a key the previous index still
    names is neither deleted nor put again; a key a cleanup deleted is gone from the next run's xsection listing, so
    content that returns to it is put again, never taken as present."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = price_key(bucket)
    body = bucket.objects[k1]
    changed = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    conn.prices = changed
    at(bucket, conn, 'daily', 2)
    k2 = price_key(bucket)
    conn.prices = PRICES                                                  # undone: k1's content again
    n = len(bucket.puts)
    at(bucket, conn, 'daily', 4)                                          # k1 is still there (k2's run kept it)
    assert price_key(bucket) == k1 and xsection_puts(bucket, n) == [] and {k1, k2} <= set(bucket.objects)
    conn.prices = changed
    at(bucket, conn, 'daily', 6)                                          # k2's content again: named, so k2 is kept
    at(bucket, conn, 'daily', 8)                                          # this cleanup deletes k1 (named by no index)
    assert k1 in bucket.deleted and k1 not in bucket.objects and price_key(bucket) == k2
    conn.prices = PRICES
    at(bucket, conn, 'daily', 10)                                         # back to k1: put again from the rebuild
    assert price_key(bucket) == k1 and bucket.objects[k1] == body
    assert named(bucket) | indexed(bucket) <= set(bucket.objects) and pub.verify(conn, bucket) == 0


def test_content_that_returns_to_an_object_still_in_the_bucket_is_not_put_again():
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = price_key(bucket)
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    at(bucket, conn, 'daily', 2)
    conn.prices = PRICES                                                  # undone within the grace: k1 is still there
    n = len(bucket.puts)
    at(bucket, conn, 'daily', 2.5)
    assert price_key(bucket) == k1 and xsection_puts(bucket, n) == [] and k1 not in bucket.deleted


def test_the_cleanup_lists_the_whole_bucket_and_the_indexed_files_their_prefix_only():
    """The xsection and the content-keyed reference listings ask for `xsection/` and `ref/` only (these listings have no
    deadline). EXEC-PUBLISHER-SPEED: a daily run first lists `state.json` and `manifest/` (the cleanup's baseline, before
    its first write), and the cleanup's listing of the whole bucket comes last, after state.json."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    asked, whole = [], bucket.list
    bucket.list = lambda deadline=None, prefix='': asked.append((prefix, len(bucket.puts))) or whole(deadline, prefix)
    n = len(bucket.puts)
    at(bucket, conn, 'daily', 2)
    assert [p for p, _ in asked] == ['state.json', 'manifest/', 'xsection/', 'ref/', '']
    assert asked[0][1] == asked[1][1] == n                                 # the baseline: before the run's first put
    assert asked[-1][1] == len(bucket.puts) and bucket.puts[-1] == 'state.json'   # the cleanup: after state.json

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
# for this file's fixture: the fixed-key copies must stay byte for byte what the deployed readers already read
BEFORE_T5_RAW_SHA256 = {'tickers': '9c49504a1d4896d948dc24ba00dfc4c3a10060782496fdb8691a0085ac1e4ef0',
                        'brokers': 'a4075aee964c309ecf8cb5575d7b128baee86a8e51fa8a778e05ba72267c4597'}


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
    # a changed list is a new object; undone within the grace, the old key is still there and is not put again
    conn.universe = renamed('Bank Central Asia Tbk')
    at(bucket, conn, 'daily', 2)
    changed = refs(bucket)['tickers']['key']
    assert changed != first['tickers']['key'] and refs(bucket)['brokers'] == first['brokers']
    conn.universe = UNIVERSE
    n = len(bucket.puts)
    at(bucket, conn, 'daily', 2.5)
    assert refs(bucket)['tickers'] == first['tickers'] and ref_puts(bucket, n) == []


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
    assert fixed == ['ref/tickers.json.gz', 'ref/brokers.json.gz'] + (['ref/logos.json.gz'] if logos else [])
    for name, sha in BEFORE_T5_RAW_SHA256.items():
        body = bucket.objects[f'ref/{name}.json.gz']
        raw = gzip.decompress(body)
        assert hashlib.sha256(raw).hexdigest() == sha and body == gzip.compress(raw, compresslevel=9, mtime=0)
    assert bucket.get_json('ref/tickers.json.gz')['columns'] == ['ticker', 'name', 'type', 'sector', 'industry']
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
    assert sorted(pub.ref_entries(raw)) == ['brokers', 'tickers']
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


def test_cleanup_removes_an_unnamed_content_keyed_reference_object_only_after_the_grace():
    """The same rule as for xsection: the first daily run that starts an hour or more after the last finished run
    deletes the content-keyed reference objects its index does not name; a reader of the previous index keeps its file
    until then, and the fixed-key copies are never deleted."""
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    k1 = refs(bucket)['tickers']['key'][3:]
    conn.universe = renamed('BCA one')
    at(bucket, conn, 'daily', 2)
    k2 = refs(bucket)['tickers']['key'][3:]
    conn.universe = renamed('BCA two')
    at(bucket, conn, 'daily', 2.25)                                        # 15 minutes after the last run: no cleanup
    k3 = refs(bucket)['tickers']['key'][3:]
    assert len({k1, k2, k3}) == 3 and {k1, k2, k3} <= set(bucket.objects)
    at(bucket, conn, 'logos', 4)                                           # not a daily run: deletes nothing
    assert {k1, k2} <= set(bucket.objects)
    at(bucket, conn, 'daily', 6)
    assert k1 not in bucket.objects and k2 not in bucket.objects and k3 in bucket.objects
    assert {k1, k2} <= set(bucket.deleted) and not FIXED_REFS & set(bucket.deleted)
    assert FIXED_REFS <= set(bucket.objects) and {e['key'][3:] for e in refs(bucket).values()} <= set(bucket.objects)


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
    assert gc['refs_named'] == 2 and gc['kept_newer_than_last_run'] == 1
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
    at(bucket, conn, 'daily', 2)
    k2 = refs(bucket)['tickers']['key'][3:]
    conn.universe = UNIVERSE                                               # undone: k1's content again
    n = len(bucket.puts)
    at(bucket, conn, 'daily', 4)                                           # k1 is still there: indexed, not put again
    assert refs(bucket)['tickers']['key'] == f'v1/{k1}' and ref_puts(bucket, n) == [] and {k1, k2} <= set(bucket.objects)
    conn.universe = renamed('BCA')
    at(bucket, conn, 'daily', 6)                                           # k2 again
    at(bucket, conn, 'daily', 8)                                           # this cleanup deletes k1
    assert k1 in bucket.deleted and k1 not in bucket.objects
    conn.universe = UNIVERSE
    at(bucket, conn, 'daily', 10)                                          # back to k1: index_refs puts it again
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
    assert pub.verify(conn, bucket) == 0 and pub.verify_refs(bucket) == (3, 0)
    fixed = bucket.objects['ref/brokers.json.gz']
    bucket.objects['ref/brokers.json.gz'] = pub.encode({'columns': ['code'], 'code': []})[0]
    assert pub.verify_refs(bucket) == (3, 1)                               # the content copy is not the fixed copy
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
    assert pub.verify_refs(bucket) == (3, 1)


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
    brokers = [(t, '2026-01-02', 'AK', 'Foreign', 'Regular', 5.0, 0.0, 0.05, 0.0, False) for t in tickers]
    universe = [(t, f'Company {t}', 'stock', 'Finance', 'Banks') for t in tickers]
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
    # 24 manifests at 0.02 s each one at a time would be 0.48 s for the reads alone
    assert bucket.most > 1 and p.written == 0 and pub.time.monotonic() - started < 0.48 + 0.3


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
    assert p.stage in ('files', 'packs', 'xsection')                      # stopped before the manifests step
    assert p.uploads.pool is None                                         # the pool ended with the run


def test_the_cleanup_comes_after_state_json_so_a_slow_or_failed_listing_never_holds_the_publication(capsys):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    plant(bucket, 'price/IHSG/2019.json.gz', -24)
    whole = bucket.list
    def listing(deadline=None, prefix=''):
        if prefix == '':
            assert bucket.puts[-1] == 'state.json'                       # published before the cleanup lists
            raise TimeoutError('bucket listing took too long')
        return whole(deadline, prefix)
    bucket.list = listing
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    at(bucket, conn, 'daily', 2)
    out = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    names = [e['event'] for e in out]
    assert names.index('done') < names.index('gc_failed') and 'price/IHSG/2019.json.gz' in bucket.objects
    assert bucket.modified['state.json'] == bucket.clock
    done = [e for e in out if e['event'] == 'done'][0]
    assert set(done['phases']) == {'plan', 'files', 'packs', 'xsection', 'manifests', 'refs', 'state'}


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
    assert alerts[-1]['details']['stage'] == 'plan' and 'password' not in json.dumps(alerts[-1])


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
