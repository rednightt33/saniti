"""EXEC-MU-ACCOUNTS Phase 3c (T2; verification/edge_multiuser/access_tiers/CONTRACT.md section 8b "3c in detail"): the
EDGE owner headers, the owner rows, the quotas per owner (decision D6), the filter on every data route and the cut of
exactly the last N days (decision D2 = A)."""
import copy
import datetime as dt
import gzip
import hashlib
import json
import os
import threading

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import cut as cut_mod
from app.config import Settings
from app.entitlements import CAPS_HEADER, OWNER_HEADER, window_after
from app.main import API, DATASETS, DATED, ROUTE_ACCESS, create_app
from test_api import ADMIN, LIMITS, NOW, ORIGIN, PRIVATE, PROXY_KEY, SETTINGS, FakeBucket, FakeStore

GATEWAY = {'x-terminal-proxy-key': PROXY_KEY}
THROUGH = '2026-11-17'


def caps(**kw):
    doc = {'v': 1, 'version': 'db-0123456789ab', 'admin': False, 'tickers': ['BBCA'], 'datasets': ['price'],
           'history_days': 730, 'quota': {}}
    doc.update(kw)
    return json.dumps(doc, separators=(',', ':'))


ADMIN_CAPS = caps(version='env', admin=True, tickers='*', datasets='*', history_days=None)


def owner(key='u_000000000000000000000001', capabilities=None):
    return {**GATEWAY, OWNER_HEADER: key, CAPS_HEADER: capabilities or caps()}


FREE = owner()                                     # the free plan: BBCA, daily price, 730 days


def gz(doc):
    raw = json.dumps(doc, separators=(',', ':')).encode()
    body = gzip.compress(raw, compresslevel=9, mtime=0)
    return body, hashlib.sha256(body).hexdigest()


def price_rows(dates):
    return {'columns': ['d', 'o', 'h', 'l', 'c', 'v'], 'd': dates, 'o': [1.0] * len(dates), 'h': [2.0] * len(dates),
            'l': [0.5] * len(dates), 'c': [1.5] * len(dates), 'v': [100.0] * len(dates)}


class CutBucket(FakeBucket):
    """FakeBucket whose BBCA files exist as real gzip JSON (read() for the cut), with the dates around the window start
    of N = 730 from 2026-11-17 (2024-11-17 out, 2024-11-18 in)."""
    def __init__(self):
        super().__init__()
        self.objects, self.reads = {}, []
        price_years = {2023: ['2023-01-03', '2023-12-29'], 2024: ['2024-01-02', '2024-11-15', '2024-11-17', '2024-11-18',
                                                                  '2024-12-30'],
                       2025: ['2025-01-02', '2025-12-30'], 2026: ['2026-01-02', '2026-11-16', '2026-11-17']}
        price = {str(y): self.put(f'v1/price/BBCA/{y}', {'schema_version': 1, 'dataset': 'price', 'ticker': 'BBCA',
                                                         'year': y, 'units': {'o': 'IDR'}, **price_rows(d)})
                 for y, d in price_years.items()}
        broker_old = {'columns': ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl'],          # before bf/sf existed
                      'd': ['2024-11-17', '2024-11-18'], 'b': ['YP', 'CC'], 'i': ['Foreign', 'Domestic'],
                      'm': ['Regular', 'Regular'], 'bv': [1.0, 2.0], 'sv': [0.5, 0.25], 'bl': [1.0, 1.0],
                      'sl': [1.0, 1.0], 'gap': [['2024-11-17', 'Nego'], ['2024-11-18', 'Tunai']]}
        broker_new = {'columns': ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf'],
                      'd': ['2026-11-17'], 'b': ['YP'], 'i': ['Foreign'], 'm': ['Regular'], 'bv': [3.0], 'sv': [1.0],
                      'bl': [2.0], 'sl': [1.0], 'bf': [4], 'sf': [2], 'gap': []}
        broker = {'2024': self.put('v1/broker/BBCA/2024', {'dataset': 'broker', 'year': 2024, **broker_old}, '2024-01-02',
                                   '2024-12-30'),
                  '2026': self.put('v1/broker/BBCA/2026', {'dataset': 'broker', 'year': 2026, **broker_new}, '2026-01-02',
                                   '2026-11-17')}
        events = {'columns': ['d', 'role', 'title'], 'd': ['2009-01-20', '2024-11-18', '2026-12-01'],
                  'role': ['EX_DATE', 'EX_DATE', 'EX_DATE'], 'title': ['old', 'in', 'upcoming'],
                  'basis': {'columns': ['ex', 'factor'], 'ex': ['2009-01-20', '2025-06-02'], 'factor': [2.0, 5.0],
                            'means': {'factor': 'x'}}}
        ev = {'all': self.put('v1/events/BBCA/all', {'dataset': 'events', **events}, '2009-01-20', '2026-12-01')}
        packs = {'price': self.put('v1/pack/BBCA/price', {'dataset': 'price-pack', **price_rows(['2023-01-03'])})}
        self.manifests = {'BBCA': {'window': {'first_year': 2023, 'last_year': 2026}, 'packs': packs, 'datasets': {
            'price': {'data_through': THROUGH, 'files': price},
            'broker': {'data_through': THROUGH, 'files': broker},
            'events': {'data_through': '2026-11-17T10:00:00Z', 'files': ev}}},
            'BBRI': {'window': {'first_year': 2023, 'last_year': 2026},
                     'datasets': {'price': {'data_through': THROUGH, 'files': price}}}}
        self.manifests['BBCA']['intraday'] = {'5m': {'files': {'current': {
            'key': 'v1/intraday/BBCA/5m-2026-11.json.gz', 'sha256': 'e' * 64, 'bytes': 900, 'rows': 10}},
            'first': '2026-11-01T02:00:00+00:00', 'last': '2026-11-17T09:00:00+00:00', 'rows': 10,
            'bars_per_year': 16017}}

    def put(self, name, doc, first=None, last=None):
        body, sha = gz(doc)
        key = f'{name}.{sha}.json.gz'
        self.objects[key] = body
        cols = doc['columns']
        return {'key': key, 'sha256': sha, 'bytes': len(body), 'rows': len(doc[cols[0]]),
                'first': first or doc['d'][0], 'last': last or doc['d'][-1]}

    def manifest(self, ticker):
        return self.manifests.get(ticker)

    def read(self, key):
        self.reads.append(key)
        return self.objects.get(key)


class OwnerStore(FakeStore):
    """FakeStore with the owner rows of migration 20261118_100 (kind 'owner', edge_owner_key), per-row quota overrides
    (terminal.quota_override) and the audit row's version."""
    def __init__(self):
        super().__init__()
        self.overrides = {}

    def limits(self, c, sid):
        return {**self.limits_value, **self.overrides.get(sid, {})}

    def owner_account(self, c, owner_key):
        self.events.append(('owner', owner_key))
        for sid, u in self.subs.items():
            if u.get('owner') == owner_key:
                break
        else:
            sid = max(self.subs) + 1
            self.subs[sid] = {'email': f'owner-{sid}@edge-owner.terminal.local', 'name': f'EDGE owner {owner_key}',
                              'hash': None, 'active': True, 'expires_at': NOW + dt.timedelta(days=365 * 70),
                              'kind': 'owner', 'owner': owner_key}
        u = self.subs[sid]
        if not u['active']:
            return None
        return {'subscriber_id': sid, 'email': u['email'], 'display_name': u['name'], 'expires_at': u['expires_at'],
                'kind': 'owner'}

    def log_access(self, c, sid, kind, ticker, ip, dataset=None, year=None, key=None, bytes_=0, keys=None, version=None):
        super().log_access(c, sid, kind, ticker, ip, dataset, year, key, bytes_, keys)
        self.access[-1]['version'] = version


def make(bucket=None, store=None):
    bucket, store = bucket or CutBucket(), store or OwnerStore()
    settings = Settings(**{**SETTINGS.__dict__, 'proxy_key': PROXY_KEY, 'proxy_subscriber': 'sub@example.com'})
    client = TestClient(create_app(settings, store, bucket), base_url=PRIVATE)
    r = client.post(f'{API}/admin/subscribers', headers={**ADMIN, 'origin': ORIGIN}, json={
        'email': 'sub@example.com', 'display_name': 'Gateway', 'password': 'correct horse battery',
        'expires_at': (NOW + dt.timedelta(days=30)).isoformat()})
    assert r.status_code == 201, r.text
    return client, store, bucket


def refused(r, capability, status=403):
    assert r.status_code == status, r.text
    body = r.json()
    assert body['error'] == 'capability_required' and body['capability'] == capability, body
    assert 'Fix:' in body['message'] and capability in body['message']
    return body


# ---- the window rule (decision D2 = A) ------------------------------------------------------------------------------
def test_the_window_is_the_rows_dated_after_data_through_minus_n_days():
    after = window_after('2026-11-17', 730)
    assert after == dt.date(2024, 11, 17)                                 # 2024-11-17 out, 2024-11-18 in
    assert (dt.date(2026, 11, 17) - dt.date(2024, 11, 18)).days + 1 == 730    # exactly 730 calendar days served
    assert window_after('2026-11-17T10:00:00Z', 1) == dt.date(2026, 11, 16)
    assert window_after(None, 730) is None and window_after('soon', 730) is None


# ---- a capped owner on every second path ----------------------------------------------------------------------------
# One refused request per data route an owner's plan gates (ROUTE_ACCESS 'owner'), each a second path to content the
# free plan lacks; test_every_owner_route_is_in_the_refusal_table holds this table to the routes.
SECOND_PATHS = {
    '/files': [('post', '/files', {'ticker': 'BBCA', 'dataset': 'price', 'years': [2024]}, 'terminal.history_days'),
               ('post', '/files', {'ticker': 'BBCA', 'dataset': 'broker', 'years': [2026]}, 'terminal.dataset:broker'),
               ('post', '/files', {'ticker': 'BBCA', 'dataset': 'events'}, 'terminal.dataset:events'),
               ('post', '/files', {'ticker': 'BBRI', 'dataset': 'price', 'years': [2026]}, 'terminal.tickers')],
    '/bundle': [('post', '/bundle', {'ticker': 'BBRI', 'datasets': ['price'], 'packs': False}, 'terminal.tickers')],
    '/manifest/{ticker}': [('get', '/manifest/BBRI', None, 'terminal.tickers')],
    '/history/price': [('get', '/history/price?ticker=BBCA&from=2019-01-01&to=2019-12-31', None,
                        'terminal.history_days'),
                       ('get', '/history/price?ticker=BBRI&from=2025-01-01&to=2025-01-31', None, 'terminal.tickers')],
    '/history/broker': [('get', '/history/broker?ticker=BBCA&from=2019-01-01&to=2019-12-31', None,
                         'terminal.dataset:broker')],
    '/reference/{name}': [('get', '/reference/tickers', None, 'terminal.dataset:reference'),
                          ('get', '/reference/brokers', None, 'terminal.dataset:reference')],
    '/cut/{ticker}/{dataset}': [('get', f'/cut/BBCA/broker?sha256={"a" * 64}', None, 'terminal.dataset:broker'),
                                ('get', f'/cut/BBRI/price?sha256={"a" * 64}', None, 'terminal.tickers')],
}


def test_a_free_owner_is_refused_on_every_second_path_and_nothing_is_counted():
    client, store, bucket = make()
    for path, cases in SECOND_PATHS.items():
        for method, url, body, capability in cases:
            r = getattr(client, method)(f'{API}{url}', headers=FREE, **({'json': body} if body is not None else {}))
            refused(r, capability)
    assert store.access == [] and bucket.reads == []                     # nothing granted, no bucket file read
    # /bundle with packs false: the locked data sets carry no url, sha or rows; intraday is locked as well
    r = client.post(f'{API}/bundle', headers=FREE, json={'ticker': 'BBCA', 'datasets': ['price', 'broker', 'events'],
                                                         'packs': False, 'timeframe': '5m'})
    assert r.status_code == 200, r.text
    d = r.json()['datasets']
    assert d['broker'] == {'locked': True, 'capability': 'terminal.dataset:broker'}
    assert d['events'] == {'locked': True, 'capability': 'terminal.dataset:events'}
    assert d['intraday'] == {'timeframe': '5m', 'locked': True, 'capability': 'terminal.dataset:intraday'}
    assert [f['pack'] for f in d['price']['files']] == ['cut'] and 'bucket.example' not in r.text
    # the cross-sectional files: refused to the gateway key with an owner header, whatever the plan
    for headers in (FREE, owner(capabilities=ADMIN_CAPS)):
        r = client.post(f'{API}/xsection', headers=headers, json={'names': ['price']})
        assert r.status_code == 403 and r.json()['error'] == 'gateway_only' and 'Fix:' in r.json()['message']
    # the manifest names no file outside the plan: broker and events locked, the price years inside the window only
    m = client.get(f'{API}/manifest/BBCA', headers=FREE).json()['datasets']
    assert m['broker'] == {'locked': True, 'capability': 'terminal.dataset:broker'}
    assert list(m['price']['years']) == ['2025', '2026'] and m['price']['cut'] == {'history_days': 730,
                                                                                   'after': '2024-11-17'}
    # a yearly file entirely inside the window is not history beyond it: granted as for any account
    r = client.post(f'{API}/files', headers=FREE, json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2025, 2026]})
    assert r.status_code == 200 and [f['year'] for f in r.json()['files']] == [2025, 2026]
    # /history inside the window would reach the published-file rule, not the plan's
    r = client.get(f'{API}/history/price', headers=FREE, params={'ticker': 'BBCA', 'from': '2025-01-01',
                                                                 'to': '2025-01-31'})
    assert r.status_code == 400 and r.json()['error'] == 'use_published_files'


def test_a_paid_owner_with_every_dataset_but_a_cap_gets_cuts_and_no_intraday():
    client, store, bucket = make()
    h = owner(capabilities=caps(tickers='*', datasets='*'))
    r = client.post(f'{API}/bundle', headers=h, json={'ticker': 'BBCA', 'datasets': ['price', 'broker', 'events'],
                                                      'packs': True, 'timeframe': '5m'})
    assert r.status_code == 200, r.text
    d = r.json()['datasets']
    assert all([f['pack'] for f in d[n]['files']] == ['cut'] for n in ('price', 'broker', 'events'))
    assert d['intraday']['locked'] and d['intraday']['capability'] == 'terminal.history_days' and d['intraday']['reason']
    assert 'url' not in json.dumps(d['intraday'])
    assert r.json()['expires_in_seconds'] == 0 and store.access == []      # the cuts are counted when served
    refused(client.post(f'{API}/files', headers=h, json={'ticker': 'BBCA', 'dataset': 'events'}), 'terminal.history_days')


# ---- the cut ---------------------------------------------------------------------------------------------------------
def cut_doc(client, headers, dataset, ticker='BBCA'):
    b = client.post(f'{API}/bundle', headers=headers, json={'ticker': ticker, 'datasets': [dataset], 'packs': True})
    assert b.status_code == 200, b.text
    (entry,) = b.json()['datasets'][dataset]['files']
    assert entry['url'] == f'{API}/cut/{ticker}/{dataset}?sha256={entry["sha256"]}' and entry['year'] is None
    r = client.get(entry['url'], headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers['content-type'] == 'application/gzip' and 'content-encoding' not in r.headers
    assert hashlib.sha256(r.content).hexdigest() == entry['sha256'] == r.headers['x-terminal-cut-sha256']
    assert len(r.content) == entry['bytes']
    doc = json.loads(gzip.decompress(r.content))
    assert len(doc[doc['columns'][0]]) == entry['rows']
    return entry, r.content, doc


def test_the_cut_holds_exactly_the_window_in_the_shape_the_page_reads_and_is_stable():
    client, store, _ = make()
    entry, body, doc = cut_doc(client, FREE, 'price')
    # boundary dates on both sides: 2024-11-17 (= data_through - 730) out, 2024-11-18 in, data_through itself in
    assert doc['d'] == ['2024-11-18', '2024-12-30', '2025-01-02', '2025-12-30', '2026-01-02', '2026-11-16', '2026-11-17']
    # worker.ts priceRows reads d, o, h, l, c, v by name: every column has one value per date
    assert doc['columns'] == ['d', 'o', 'h', 'l', 'c', 'v'] and all(len(doc[c]) == 7 for c in doc['columns'])
    assert doc['dataset'] == 'price-cut' and doc['year'] is None and doc['units'] == {'o': 'IDR'}
    assert doc['cut'] == {'history_days': 730, 'after': '2024-11-17', 'through': '2026-11-17'}
    # counted as one file of its bytes, one audit row on the owner's own row with the header's version
    (row,) = store.access
    assert (row['files'], row['bytes'], row['ticker'], row['dataset'], row['version']) == (1, len(body), 'BBCA',
                                                                                            'price', 'db-0123456789ab')
    assert row['key'] == f'cut/BBCA/price/730/{entry["sha256"]}' and row['sid'] != 1
    # deterministic: a second build (a new process, an empty cut cache) gives the same bytes and sha256
    again, body2, _ = cut_doc(make()[0], FREE, 'price')
    assert again == entry and body2 == body
    # another N is another cut
    other, _, doc3 = cut_doc(client, owner(capabilities=caps(history_days=10)), 'price')
    assert other['sha256'] != entry['sha256'] and doc3['d'] == ['2026-11-16', '2026-11-17']


def test_a_broker_cut_cuts_its_gap_list_and_fills_a_column_an_older_file_lacks():
    client, _, _ = make()
    _, _, doc = cut_doc(client, owner(capabilities=caps(datasets=['broker'])), 'broker')
    assert doc['d'] == ['2024-11-18', '2026-11-17'] and doc['gap'] == [['2024-11-18', 'Tunai']]
    assert doc['columns'] == ['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf']
    assert doc['bf'] == [None, 4] and doc['sf'] == [None, 2]                  # worker.ts flowRowsOf: null -> NaN


def test_an_events_cut_keeps_upcoming_events_and_cuts_the_basis_block_by_its_ex_date():
    client, _, _ = make()
    _, _, doc = cut_doc(client, owner(capabilities=caps(datasets=['events'])), 'events')
    assert doc['d'] == ['2024-11-18', '2026-12-01'] and doc['title'] == ['in', 'upcoming']
    assert doc['basis'] == {'means': {'factor': 'x'}, 'columns': ['ex', 'factor'], 'ex': ['2025-06-02'], 'factor': [5.0]}


def test_the_cut_is_built_once_per_publication_and_n_and_the_cache_is_bounded():
    client, _, bucket = make()
    cut_doc(client, FREE, 'price')
    reads = len(bucket.reads)
    assert reads == 3                                                       # 2024, 2025 and 2026; never 2023
    cut_doc(client, FREE, 'price')
    assert len(bucket.reads) == reads                                       # the cache answered the second bundle
    cache = cut_mod.CutCache(max_bytes=10, max_entries=5)
    for k in range(3):
        cache.get_or_build(k, lambda: cut_mod.Cut(b'x' * 6, 's', 1))
    assert list(cache._items) == [2] and cache._size == 6


def test_the_cut_route_takes_n_from_the_header_only_and_refuses_what_it_cannot_serve():
    client, store, bucket = make()
    entry, body, _ = cut_doc(client, FREE, 'price')
    # N in the query is not read (FastAPI ignores an unknown parameter): the header's 730 decides
    r = client.get(entry['url'] + '&history_days=36500&n=36500', headers=FREE)
    assert r.content == body
    # a stale sha256 (the publication changed since /bundle): the current cut, which the page's check then refuses
    r = client.get(f'{API}/cut/BBCA/price?sha256={"0" * 64}', headers=FREE)
    assert r.status_code == 200 and r.content == body
    assert client.get(f'{API}/cut/BBCA/price', headers=FREE).status_code == 400      # sha256 is required
    # no cap, no owner, an unknown or undated data set
    for headers in (GATEWAY, owner(capabilities=ADMIN_CAPS), owner(capabilities=caps(history_days=None))):
        r = client.get(entry['url'], headers=headers)
        assert r.status_code == 404 and r.json()['error'] == 'no_cut' and 'Example:' in r.json()['message']
    assert client.get(f'{API}/cut/BBCA/intraday?sha256={"a" * 64}',
                      headers=owner(capabilities=caps(datasets='*'))).json()['error'] == 'unknown_dataset'
    # a file that cannot be cut correctly is refused with its reason, never served whole
    m = bucket.manifests['BBCA']
    m['datasets']['price']['files']['2026'] = bucket.put('v1/price/BBCA/2026x', {**price_rows(['2026-11-17']),
                                                                                 'notes': ['a list without dates']})
    r = client.get(f'{API}/cut/BBCA/price?sha256={"a" * 64}', headers=FREE)
    assert r.status_code == 503 and r.json()['error'] == 'cut_unavailable' and "'notes'" in r.json()['message']
    b = client.post(f'{API}/bundle', headers=FREE, json={'ticker': 'BBCA', 'datasets': ['price']}).json()
    assert b['datasets']['price']['locked'] and b['datasets']['price']['capability'] == 'terminal.history_days'
    assert 'notes' in b['datasets']['price']['reason'] and 'files' not in b['datasets']['price']
    # bytes unlike the manifest's sha256 are not cut either
    m['datasets']['price']['files']['2026'] = {**m['datasets']['price']['files']['2025'], 'sha256': 'f' * 64}
    r = client.get(f'{API}/cut/BBCA/price?sha256={"a" * 64}', headers=FREE)
    assert r.status_code == 503 and 'not the one its manifest announces' in r.json()['message']


def test_the_cut_counts_against_the_owners_quota():
    client, store, _ = make()
    h = owner(capabilities=caps(quota={'files_per_hour': 1}))
    entry, _, _ = cut_doc(client, h, 'price')
    r = client.get(entry['url'], headers=h)
    assert r.status_code == 429 and 'files_per_hour reached (1 per hour)' in r.json()['message']
    assert len(store.access) == 1


# ---- owner rows and quotas (decision D6) -----------------------------------------------------------------------------
def test_owner_rows_are_per_owner_and_two_owners_do_not_share_usage():
    client, store, _ = make()
    one = {'files_per_hour': 1}
    a = owner('u_00000000000000000000000a', caps(tickers='*', datasets='*', history_days=None, quota=one))
    b = owner('u_00000000000000000000000b', caps(tickers='*', datasets='*', history_days=None, quota=one))
    ask = {'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]}
    assert client.post(f'{API}/files', headers=a, json=ask).status_code == 200
    assert client.post(f'{API}/files', headers=a, json=ask).status_code == 429             # a's quota used up
    assert client.post(f'{API}/files', headers=b, json=ask).status_code == 200             # b's own
    rows = {s['owner']: sid for sid, s in store.subs.items() if s.get('kind') == 'owner'}
    assert set(rows) == {'u_00000000000000000000000a', 'u_00000000000000000000000b'}
    assert [r['sid'] for r in store.access] == [rows['u_00000000000000000000000a'], rows['u_00000000000000000000000b']]
    assert 1 not in {r['sid'] for r in store.access}                                       # never the gateway's row
    # made once per owner: the second request found the row
    assert sum(1 for s in store.subs.values() if s.get('owner') == 'u_00000000000000000000000a') == 1
    # the gateway without the headers keeps its own account and its rows carry no version
    assert client.post(f'{API}/files', headers=GATEWAY, json=ask).status_code == 200
    assert store.access[-1]['sid'] == 1 and store.access[-1]['version'] is None


def test_quotas_defaults_header_overlay_and_admin_keeping_the_gateways_own_limits():
    store = OwnerStore()
    store.limits_value = {**LIMITS, 'files_per_hour': 2}                  # terminal.quota defaults
    store.overrides[1] = {'files_per_hour': 1_000_000_000}                 # the gateway's 1e9 override
    client, store, _ = make(store=store)
    bundle = {'ticker': 'BBCA', 'datasets': ['price', 'broker', 'events'], 'packs': False}   # 7 files
    paid = caps(tickers='*', datasets='*', history_days=None)
    r = client.post(f'{API}/bundle', headers=owner('u_paid', paid), json=bundle)
    assert r.status_code == 429 and '(2 per hour)' in r.json()['message']                 # defaults, never the override
    over = caps(tickers='*', datasets='*', history_days=None, quota={'files_per_hour': 300})
    assert client.post(f'{API}/bundle', headers=owner('u_paid', over), json=bundle).status_code == 200   # the overlay
    over = caps(tickers='*', datasets='*', history_days=None, quota={'tickers_per_hour': 1, 'files_per_hour': 300})
    h = owner('u_other', over)
    assert client.post(f'{API}/bundle', headers=h, json=bundle).status_code == 200
    r = client.post(f'{API}/bundle', headers=h, json={**bundle, 'ticker': 'BBRI', 'datasets': ['price']})
    assert r.status_code == 429 and 'tickers_per_hour' in r.json()['message']
    # admin: the gateway subscriber's own limits (its override), counted on the owner's own row
    for _ in range(3):
        assert client.post(f'{API}/bundle', headers=owner('edge-private', ADMIN_CAPS), json=bundle).status_code == 200
    sid = next(s for s, u in store.subs.items() if u.get('owner') == 'edge-private')
    assert sum(r['files'] for r in store.access if r['sid'] == sid) == 21 and store.overrides == {1: {'files_per_hour': 1_000_000_000}}
    assert {r['version'] for r in store.access if r['sid'] == sid} == {'env'}
    # an admin owner is filtered by nothing: the whole bundle, packs and all, as without the headers
    full = client.post(f'{API}/bundle', headers=owner('edge-private', ADMIN_CAPS), json={**bundle, 'packs': True}).json()
    plain = client.post(f'{API}/bundle', headers=GATEWAY, json={**bundle, 'packs': True}).json()
    assert full == plain


def test_an_inactive_owner_row_or_gateway_account_is_refused():
    client, store, _ = make()
    assert client.get(f'{API}/manifest/BBCA', headers=FREE).status_code == 200
    sid = next(s for s, u in store.subs.items() if u.get('kind') == 'owner')
    store.subs[sid]['active'] = False
    client.post(f'{API}/admin/subscribers/{sid}', headers={**ADMIN, 'origin': ORIGIN}, json={'active': False})
    r = client.post(f'{API}/bundle', headers=FREE, json={'ticker': 'BBCA', 'datasets': ['price']})
    assert r.status_code == 401 and r.json()['error'] == 'session_ended' and 'u_000000000000000000000001' in r.json()['message']
    assert client.post(f'{API}/bundle', headers=owner('u_new'), json={'ticker': 'BBCA', 'datasets': ['price']}).status_code == 200
    store.subs[1]['active'] = False                                          # the gateway's own account
    client.post(f'{API}/admin/subscribers/1', headers={**ADMIN, 'origin': ORIGIN}, json={'active': False})
    assert client.get(f'{API}/manifest/BBCA', headers=owner('u_new')).status_code == 401


# ---- the other routes -----------------------------------------------------------------------------------------------
def test_state_logo_and_the_page_routes_with_an_owner():
    bucket = CutBucket()
    bucket.state_doc = {**FakeBucket.state_doc, 'refs': {}, 'xsection': {}}
    from test_api import RADAR
    bucket.state_doc['radar'] = copy.deepcopy(RADAR)
    client, store, _ = make(bucket)
    s = client.get(f'{API}/state', headers=FREE).json()
    assert s['xsection'] is None and s['refs'] is None and s['finished_at']
    s = client.get(f'{API}/state', headers=owner(capabilities=caps(datasets=['price', 'reference']))).json()
    assert s['xsection'] is None and s['refs'] is not None
    assert client.get(f'{API}/state', headers=owner(capabilities=ADMIN_CAPS)).json() == client.get(
        f'{API}/state', headers=GATEWAY).json()
    assert client.get(f'{API}/logo/BBRI', headers=FREE).status_code in (200, 404)          # no data file: no refusal
    # a page route: no new refusal, the grant audited on the owner's row with the version
    assert client.get(f'{API}/radar', headers=FREE).status_code == 200
    r = client.post(f'{API}/radar', headers=FREE, json={'names': [next(iter(RADAR))]})
    assert r.status_code == 200, r.text
    assert store.access[-1]['sid'] != 1 and store.access[-1]['version'] == 'db-0123456789ab'


def test_reference_with_the_reference_dataset():
    bucket = CutBucket()
    client, store, _ = make(bucket)
    r = client.get(f'{API}/reference/tickers', headers=owner(capabilities=caps(datasets=['price', 'reference'])))
    assert r.status_code == 200 and store.access[-1]['ticker'] == 'REF'


# ---- the headers -----------------------------------------------------------------------------------------------------
BAD = [
    ({OWNER_HEADER: 'u_1 or 1=1'}, OWNER_HEADER),
    ({OWNER_HEADER: ''}, OWNER_HEADER),
    ({CAPS_HEADER: 'not json'}, 'header'),
    ({CAPS_HEADER: '[1]'}, 'header'),
    ({CAPS_HEADER: caps(tickers=['BBCA'] * 1) + ' ' * 9000}, 'header'),
    ({CAPS_HEADER: caps().replace('db-0', 'd\xe9-0').encode('latin-1')}, 'header'),
    ({CAPS_HEADER: caps(extra=1)}, 'extra'),
    ({CAPS_HEADER: json.dumps({k: v for k, v in json.loads(caps()).items() if k != 'quota'})}, 'quota'),
    ({CAPS_HEADER: caps(v=2)}, 'v'),
    ({CAPS_HEADER: caps(v=True)}, 'v'),
    ({CAPS_HEADER: caps(version='')}, 'version'),
    ({CAPS_HEADER: caps(admin='yes')}, 'admin'),
    ({CAPS_HEADER: caps(admin=True)}, 'admin'),
    ({CAPS_HEADER: caps(tickers=['bbca'])}, 'tickers'),
    ({CAPS_HEADER: caps(tickers='all')}, 'tickers'),
    ({CAPS_HEADER: caps(tickers=['BBCA', 'BBCA'])}, 'tickers'),
    # re-check R2-5: an id this terminal-api does not know is left out (test_terminal_fix_round.py); one that breaks
    # the id rule is still refused
    ({CAPS_HEADER: caps(datasets=['price', 'Options'])}, 'datasets'),
    # re-check R1-22: 0 is the empty window (test_terminal_fix_round.py); below it is refused
    ({CAPS_HEADER: caps(history_days=-1)}, 'history_days'),
    ({CAPS_HEADER: caps(history_days=36601)}, 'history_days'),
    ({CAPS_HEADER: caps(history_days=True)}, 'history_days'),
    ({CAPS_HEADER: caps(history_days=730.5)}, 'history_days'),
    ({CAPS_HEADER: caps(quota={'files_per_day': 5})}, 'quota'),
    ({CAPS_HEADER: caps(quota={'files_per_hour': 0})}, 'quota'),
    ({CAPS_HEADER: caps(quota=[])}, 'quota'),
]


@pytest.mark.parametrize('change, field', BAD)
def test_a_malformed_header_is_refused_with_the_field_named(change, field):
    client, store, _ = make()
    r = client.get(f'{API}/manifest/BBCA', headers={**FREE, **change})
    assert r.status_code == 400, r.text
    body = r.json()
    assert body['error'] == 'invalid_owner_headers' and body['field'] == field, body
    assert 'Fix:' in body['message'] and 'Example:' in body['message']
    assert store.access == [] and not any(u.get('kind') == 'owner' for u in store.subs.values())


def test_one_header_alone_a_service_key_or_a_session_never_names_an_owner():
    client, _, _ = make()
    for only, missing in ((OWNER_HEADER, CAPS_HEADER), (CAPS_HEADER, OWNER_HEADER)):
        r = client.get(f'{API}/state', headers={**GATEWAY, only: FREE[only]})
        assert r.status_code == 400 and r.json()['field'] == missing and 'Example:' in r.json()['message']
    from test_api import BACKTEST, services_client
    sclient, _, _ = services_client()
    r = sclient.get(f'{API}/state', headers={**BACKTEST, CAPS_HEADER: caps()})
    assert r.status_code == 400 and r.json()['error'] == 'owner_not_allowed'
    session = TestClient(client.app, base_url=PRIVATE, headers={'origin': ORIGIN})
    r = session.get(f'{API}/manifest/BBCA', headers={OWNER_HEADER: 'u_x', CAPS_HEADER: caps()})
    assert r.status_code == 400 and r.json()['error'] == 'owner_not_allowed'


def test_the_example_headers_are_accepted():
    from app.entitlements import ADMIN_EXAMPLE, EXAMPLE
    client, _, _ = make()
    for c in (EXAMPLE, ADMIN_EXAMPLE):
        assert client.get(f'{API}/manifest/BBCA', headers=owner(capabilities=c)).status_code == 200


# ---- every data route has its gate (the class, not the instance) ----------------------------------------------------
def api_routes(app):
    return {r.path[len(API):] for r in app.routes if isinstance(r, APIRoute) and r.path.startswith(API)}


def test_every_api_route_declares_how_an_owner_is_gated():
    client, _, _ = make()
    paths = api_routes(client.app)
    missing = paths - set(ROUTE_ACCESS)
    assert not missing, f'routes without an entry in main.py ROUTE_ACCESS: {sorted(missing)}'
    assert not set(ROUTE_ACCESS) - paths, 'ROUTE_ACCESS names a route that does not exist'


def test_every_owner_route_is_in_the_refusal_table():
    """A new data route marked 'owner' must get a second-path refusal case here (SECOND_PATHS)."""
    owner_routes = {p for p, kind in ROUTE_ACCESS.items() if kind == 'owner'}
    assert owner_routes == set(SECOND_PATHS)


def test_the_dataset_ids_come_from_terminal_apis_own_definitions():
    from typing import get_args
    from app.main import BUNDLE_DATASET, FilesRequest
    assert DATED == get_args(BUNDLE_DATASET) and set(DATASETS) == set(DATED) | {'intraday', 'reference'}
    assert set(get_args(FilesRequest.model_fields['dataset'].annotation)) <= set(DATED)


# ---- the owner row on a real server (TERMINAL_TEST_POSTGRES_URL with the terminal schema and 20261118_100) ----------
def test_owner_rows_on_a_real_server_are_made_once_under_concurrent_first_use():
    url = os.environ.get('TERMINAL_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('TERMINAL_TEST_POSTGRES_URL is not set')
    import psycopg
    from app.store import Store, owner_email
    with psycopg.connect(url) as c:
        if not c.execute("SELECT 1 FROM information_schema.columns WHERE table_schema = 'terminal' "
                         "AND table_name = 'subscriber' AND column_name = 'edge_owner_key'").fetchone():
            pytest.skip('the server has no terminal schema with migration 20261118_100')
    store = Store(url, max_size=8)
    store.open()
    key = f'test-owner-{os.getpid()}-{NOW.timestamp():.0f}'
    try:
        ids, gate = [], threading.Barrier(8)

        def first_use():
            gate.wait()
            with store.tx() as c:
                ids.append(store.owner_account(c, key)['subscriber_id'])
        threads = [threading.Thread(target=first_use) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(ids) == 8 and len(set(ids)) == 1
        with store.tx() as c:
            row = c.execute('SELECT kind, email, edge_owner_key FROM terminal.subscriber WHERE subscriber_id = %s',
                            (ids[0],)).fetchone()
            assert row == {'kind': 'owner', 'email': owner_email(key), 'edge_owner_key': key}
            store.log_access(c, ids[0], 'file', 'BBCA', None, dataset='price', key='cut/BBCA/price/730/x', bytes_=10,
                             version='db-0123456789ab')
            assert c.execute('SELECT version FROM terminal.access_log WHERE subscriber_id = %s',
                             (ids[0],)).fetchone() == {'version': 'db-0123456789ab'}
            assert store.subscriber_by_email(c, owner_email(key))['kind'] == 'owner'      # never a person: no sign-in
            c.execute('UPDATE terminal.subscriber SET active = false WHERE subscriber_id = %s', (ids[0],))
            assert store.owner_account(c, key) is None
    finally:
        with store.tx() as c:
            c.execute('DELETE FROM terminal.subscriber WHERE edge_owner_key = %s', (key,))
        store.close()
