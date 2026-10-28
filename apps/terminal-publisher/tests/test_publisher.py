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
        self.objects = {}
        self.puts = []                                     # every put, in order (the objects dict keeps first order)

    def put(self, key, body, content_type):
        self.objects[key] = body
        self.puts.append(key)

    def keys(self, prefix):
        return [k for k in self.objects if k.startswith(prefix)]

    def delete(self, key):
        del self.objects[key]

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
    assert 'price/BBCA/2025.json.gz' in keys and 'price/BBCA/2026.json.gz' in keys
    assert 'broker/BBCA/2026.json.gz' in keys and not any(k.startswith('broker/IHSG') for k in keys)
    assert keys.index('broker/BBCA/2026.json.gz') < keys.index('manifest/BBCA.json')
    m = bucket.get_json('manifest/BBCA.json')
    assert m['datasets']['broker']['data_through'] == '2026-01-02'
    assert m['datasets']['price']['files']['2026']['rows'] == 1
    assert 'broker' not in bucket.get_json('manifest/IHSG.json')['datasets']


def test_broker_file_keeps_decimal_lots_investor_type_and_gaps():
    _, _, bucket = run('backfill')
    doc = bucket.get_json('broker/BBCA/2026.json.gz')
    assert doc['sl'] == [0.0, 4.5]
    assert doc['i'] == ['Foreign', 'Domestic']
    assert doc['gap'] == [['2026-01-02', 'Regular']]


def test_index_price_file_keeps_null_volume():
    _, _, bucket = run('backfill')
    assert bucket.get_json('price/IHSG/2026.json.gz')['v'] == [None]


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
    bucket.objects['price/BBCA/2026.json.gz'] = gzip.compress(b'{}')
    assert pub.verify(conn, bucket) == 1


def test_price_and_broker_are_published_from_their_own_first_year():
    # T8 (user 2026-10-26): broker no longer keeps the 5-year window; each dataset starts at its first stored year
    prices = PRICES + [('BBCA', '2019-06-03', 50.0, 51.0, 49.0, 50.5, 10.0)]
    brokers = BROKERS + [('BBCA', '2020-06-03', 'AK', 'Foreign', 'Regular', 1.0, 0.0, 0.01, 0.0, False)]
    p, _, bucket = run('backfill', conn=FakeConn(prices, brokers, UNIVERSE))
    assert (p.price_first_year, p.broker_first_year) == (2019, 2020)
    assert 'price/BBCA/2019.json.gz' in bucket.objects and 'broker/BBCA/2020.json.gz' in bucket.objects
    m = bucket.get_json('manifest/BBCA.json')
    assert m['datasets']['price']['first_year'] == 2019 and m['datasets']['broker']['first_year'] == 2020
    assert '2019' in m['datasets']['price']['files'] and '2020' in m['datasets']['broker']['files']
    assert m['window']['broker_first_year'] == 2020


def test_daily_adds_missing_early_price_years():
    _, conn, bucket = run('backfill')
    conn.prices = PRICES + [('BBCA', '2019-06-03', 50.0, 51.0, 49.0, 50.5, 10.0)]
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('daily')
    assert 'price/BBCA/2019.json.gz' in bucket.objects and p2.written == 3   # the year, the price pack, the xsection price


def test_events_are_one_file_per_listed_ticker_with_display_columns_only():
    _, _, bucket = run('backfill')
    doc = bucket.get_json('events/BBCA/all.json.gz')
    assert doc['columns'] == pub.EVENT_COLUMNS and doc['d'] == ['2026-03-10', '2026-05-02']
    assert doc['holder'] == [None, 'A. Holder'] and doc['pct_flag'] == [None, 'OK']
    assert 'source_payload' not in doc and 'events/GONE/all.json.gz' not in bucket.objects  # delisted: not served
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
    assert p3.written == 1 and len(bucket.get_json('events/BBCA/all.json.gz')['d']) == 3


def test_ticker_reference_carries_the_sector_and_industry_for_search_and_portfolio_filters():
    _, _, bucket = run('backfill')
    doc = bucket.get_json('ref/tickers.json.gz')
    assert doc['columns'] == ['ticker', 'name', 'type', 'sector', 'industry']
    assert doc['sector'] == ['Finance', None] and doc['industry'] == ['Banks', None]


def test_corporate_action_detail_comes_from_the_payload_and_blank_is_none():
    _, _, bucket = run('backfill')
    doc = bucket.get_json('events/BBCA/all.json.gz')
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
    assert 'broker/BBCA/2016.json.gz' in bucket.objects
    ds = bucket.get_json('manifest/BBCA.json')['datasets']['broker']
    assert ds['first_year'] == 2016 and '2016' in ds['files']


def test_run_times_skip_only_the_unlisted_cron_ticks():
    times = pub.run_times('07:30,19:00')
    assert pub.cron_for(times) == '0,30 0,12 * * *'                   # 00:30 and 12:00 UTC are 07:30 and 19:00 WIB
    at = lambda h, m: dt.datetime(2026, 10, 26, h, m, tzinfo=dt.timezone.utc)
    assert pub.should_run(times, at(0, 31)) and pub.should_run(times, at(12, 2))      # listed times
    assert not pub.should_run(times, at(0, 1)) and not pub.should_run(times, at(12, 31))  # 07:00 and 19:30 WIB
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
    price = bucket.get_json('pack/BBCA/price.json.gz')
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
    assert bucket.get_json('pack/BBCA/broker-archive.json.gz')['d'] == ['2022-03-01']
    p3 = pub.Publisher(conn, bucket, today=TODAY)
    p3.run('daily')
    assert not any(k == 'pack' for k, _, _ in p3.changed)              # nothing changed: no pack rewritten


def test_packs_mode_builds_missing_packs_without_rewriting_existing_ones():
    _, conn, bucket = run('backfill')
    p2 = pub.Publisher(conn, bucket, today=TODAY)
    p2.run('packs')
    assert p2.written == 0
    del bucket.objects['pack/BBCA/price.json.gz']
    m = bucket.get_json('manifest/BBCA.json'); m.pop('packs'); bucket.objects['manifest/BBCA.json'] = json.dumps(m).encode()
    p3 = pub.Publisher(conn, bucket, today=TODAY)
    p3.run('packs')
    assert 'pack/BBCA/price.json.gz' in bucket.objects and p3.written == 1


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
        pack_bytes = bucket.objects[f'pack/{t}/price.json.gz']
        assert pub.price_pack_doc(t, slices[t]) == bucket.get_json(f'pack/{t}/price.json.gz')
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
    p3 = pub.Publisher(conn, bucket, today=TODAY)
    p3.run('daily')
    assert ('price', 'BBCA', 2025) not in p3.changed and ('pack', 'BBCA', 'price') in p3.changed
    assert bucket.get_json('pack/BBCA/price.json.gz')['o'][0] == 99.0
    entry, doc = xsection(bucket, 'price')
    sha = bucket.get_json('manifest/BBCA.json')['packs']['price']['sha256']                  # the manifest was saved
    assert sha == hashlib.sha256(bucket.objects['pack/BBCA/price.json.gz']).hexdigest() == doc['tickers'][0]['pack_sha256']
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
    """The reader of the index (terminal-api bucket.py xsection_index, /state and /xsection) keeps every entry."""
    spec = importlib.util.spec_from_file_location('terminal_api_bucket', ROOT / 'apps/terminal-api/app/bucket.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    _, _, bucket = run('backfill')
    index = bucket.get_json('state.json')['xsection']
    assert reader.xsection_index(index) == index


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
