import datetime as dt
import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publisher as pub  # noqa: E402


class FakeBucket:
    def __init__(self):
        self.objects, self.modified, self.deleted = {}, {}, []
        self.clock = dt.datetime(2026, 10, 25, 0, 0, tzinfo=dt.timezone.utc)   # the bucket's LastModified clock

    def put(self, key, body, content_type):
        self.objects[key] = body
        self.modified[key] = self.clock

    def list(self, deadline=None):
        return {k: (self.modified.get(k, self.clock), len(v)) for k, v in self.objects.items()}

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


class FakeConn:
    """Answers the publisher's statements from small in-memory tables."""
    def __init__(self, prices, brokers, universe, events=None):
        self.prices, self.brokers, self.universe = prices, brokers, universe
        self.events = list(EVENTS if events is None else events)
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append(sql)
        rows = self._rows(sql, params)
        return type('R', (), {'fetchall': lambda s: rows, 'fetchone': lambda s: rows[0] if rows else None})()

    def _rows(self, sql, params):
        if sql == pub.UNIVERSE_SQL:
            return self.universe
        if sql == pub.PRICE_SQL:
            t, lo, hi = params
            return [r[1:] for r in self.prices if r[0] == t and lo <= r[1] <= hi]
        if sql == pub.BROKER_SQL:
            t, lo, hi = params
            return [r[1:] for r in self.brokers if r[0] == t and lo <= r[1] <= hi]
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
    assert p2.written == 3  # price/BBCA/2026, broker/BBCA/2026 and BBCA's price pack; 2025 and IHSG untouched
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
    assert key_of(bucket, 'BBCA', 'price', 2019) in bucket.objects and p2.written == 2   # the year and the price pack


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
    old = {k: bucket.objects[k] for k in named(bucket)}
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    conn.brokers = BROKERS + [('BBCA', '2026-01-05', 'AK', 'Foreign', 'Regular', 10.0, 0.0, 0.1, 0.0, False)]
    conn.events = EVENTS + [('BBCA', '2026-06-01', 'EX_DATE', 'CORPORATE_ACTION', 'DIVIDEND') + (None,) * 9 +
                            (5.0, None, None, None, {}, None, None)]
    p = at(bucket, conn, 'daily', 2)
    replaced = set(old) - named(bucket)
    assert {k.split('/')[0] for k in replaced} == {'price', 'broker', 'events', 'pack'}   # every family changed
    assert p.written == len(replaced)
    assert all(bucket.objects[k] == body for k, body in old.items())     # nothing the old manifest names was touched
    at(bucket, conn, 'daily', 4)                                          # the next run: no reader can hold it now
    assert not replaced & set(bucket.objects) and named(bucket) <= set(bucket.objects)
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
    bucket.list = lambda deadline=None: (_ for _ in ()).throw(OSError('secret detail'))
    at(bucket, conn, 'daily', 4)
    out = capsys.readouterr().out
    assert '"gc_failed"' in out and 'OSError' in out and 'secret detail' not in out and '"done"' in out
    assert bucket.modified['state.json'] == bucket.clock                   # the run still finished


def test_a_bucket_listing_past_its_deadline_skips_the_cleanup_and_the_run_publishes(capsys, monkeypatch):
    conn = FakeConn(PRICES, BROKERS, UNIVERSE)
    bucket = FakeBucket()
    at(bucket, conn, 'backfill', 0)
    plant(bucket, 'price/IHSG/2019.json.gz', -24)
    bucket.list = lambda deadline=None: (_ for _ in ()).throw(TimeoutError('bucket listing took too long'))
    conn.prices = PRICES + [('BBCA', '2026-01-05', 102.0, 103.0, 100.0, 101.0, 800.0)]
    p = at(bucket, conn, 'daily', 2)
    assert '"TimeoutError"' in capsys.readouterr().out and p.written > 0
    assert 'price/IHSG/2019.json.gz' in bucket.objects and not bucket.deleted
