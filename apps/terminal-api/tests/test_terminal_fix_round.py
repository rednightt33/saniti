"""EXEC-MU-ACCOUNTS re-check of Phases 0-3b, fix round, track "terminal" (verification/edge_multiuser/fix_round/
terminal.md): terminal-api's side of the relay contract.

- R1-1, R1-26: every 429 names its quota, its limit, its window and when the refused request fits (`retry_after_s` and
  the Retry-After header), so edge-bff answers 429 LIMIT_REACHED with details.limit and retry_after_s without reading
  the message.
- R2-5: a dataset id this terminal-api does not know is left out (and logged), never a 400 for every call.
- R1-22: history_days 0 is the empty window (the value a plan whose limit reads as 0 sends), so page files still work.
- R2-4: every answer to an owner call carries x-terminal-capabilities-applied, so edge-bff can refuse the answer of a
  terminal-api that ignored the owner headers.
- R2-32: an owner whose plan lacks the dataset `reference` gets its own copy of each reference file (refcut.py): the
  free plan's ticker list names BBCA alone, and no copy names another ticker.
- R1-4: /ready reports the gateway's own account (ok, expiring, expired, inactive, missing) and stays ready.
"""
import datetime as dt
import os

import pytest

from app import quota
from app.main import API
from test_api import LIMITS, sign_in
from test_api import env  # noqa: F401 - the fixture


# ---- R1-1, R1-26: every 429 says which quota and when ----------------------------------------------------------------

def test_a_quota_refusal_names_the_quota_and_when_to_try_again(env):  # noqa: F811 - the fixture
    client, store, _ = env
    sign_in(client)
    store.limits_value = {**LIMITS, 'files_per_hour': 1}
    assert client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]}).status_code == 200
    r = client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2025]})
    assert r.status_code == 429, r.text
    body = r.json()
    assert body['error'] == 'quota_exceeded' and body['quota'] == 'files_per_hour' and body['limit'] == 1
    assert body['window'] == 'hour'
    # the in-memory store cannot tell when its rows leave the window: the window's length, never more
    assert body['retry_after_s'] == 3600 and r.headers['retry-after'] == '3600'
    assert 'Try again in 3600 seconds' in body['message']


def test_the_wait_comes_from_the_store_and_never_exceeds_the_window(env):  # noqa: F811
    client, store, _ = env
    sign_in(client)
    store.limits_value = {**LIMITS, 'tickers_per_hour': 1}
    store.frees_in = lambda c, sid, refusal: 125 if refusal.quota == 'tickers_per_hour' else None
    assert client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]}).status_code == 200
    r = client.post(f'{API}/files', json={'ticker': 'T1', 'dataset': 'price', 'years': [2026]})
    assert r.status_code == 429 and r.json()['retry_after_s'] == 125 and r.headers['retry-after'] == '125'
    store.frees_in = lambda c, sid, refusal: 10 ** 7                                 # a broken store: the window caps it
    r = client.post(f'{API}/files', json={'ticker': 'T1', 'dataset': 'price', 'years': [2026]})
    assert r.json()['retry_after_s'] == 3600


def test_the_excess_is_what_must_leave_the_window_for_the_request_to_fit():
    usage = quota.Usage(files_hour=58, tickers_hour=frozenset({'BBCA'}), tickers_day=frozenset({'BBCA'}),
                        bytes_day=299_000_000, history_hour=20)
    refused = quota.check(LIMITS, usage, files=5, ticker='BBCA')
    assert (refused.quota, refused.excess, refused.longest_wait) == ('files_per_hour', 3, 3600)
    refused = quota.check(LIMITS, usage, bytes_=3_000_000, ticker='BBCA')
    assert (refused.quota, refused.excess, refused.longest_wait) == ('megabytes_per_day', 2_000_000, 86400)
    assert quota.check(LIMITS, usage, history=1).excess == 1
    assert quota.check({**LIMITS, 'tickers_per_day': 1}, usage, ticker='BBRI').quota == 'tickers_per_day'


def test_the_sign_in_throttle_says_when_to_try_again(env):  # noqa: F811
    client, store, _ = env
    for _ in range(LIMITS['failed_sign_ins_per_email']):
        sign_in(client, 'wrong password!!')
    r = sign_in(client)
    assert r.status_code == 429 and r.headers['retry-after'] == '900' and r.json()['retry_after_s'] == 900


def test_a_service_ceiling_says_when_the_next_hour_starts():
    now = dt.datetime(2026, 11, 19, 10, 59, 30, tzinfo=dt.timezone.utc)
    refused = quota.check_service('backtest-worker', {'service_grants_per_hour': 1, 'service_files_per_hour': 9,
                                                     'service_megabytes_per_hour': 9},
                                  {'hour_start': now.replace(minute=0, second=0), 'grants': 2, 'files': 1, 'bytes': 1})
    assert refused.seconds_left(now) == 30


def test_frees_in_reads_the_window_on_a_real_server():
    """Store.frees_in on PostgreSQL (TERMINAL_TEST_POSTGRES_URL with the terminal schema): the oldest rows leave first,
    and the row whose leaving makes the excess names the wait; a new ticker fits once one ticker's newest read left."""
    url = os.environ.get('TERMINAL_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('TERMINAL_TEST_POSTGRES_URL is not set')
    from app.store import Store
    store = Store(url, max_size=2)
    store.open()
    try:
        with store.tx() as c:
            sid = c.execute("INSERT INTO terminal.subscriber(email, display_name, password_hash, expires_at) VALUES "
                            "(%s, 'frees', %s, now() + interval '1 day') RETURNING subscriber_id",
                            (f'frees-{os.getpid()}@example.com', 'scrypt$' + '0' * 32 + '$' + '0' * 64)).fetchone()
            sid = sid['subscriber_id']
            for minutes, kind, ticker, files, size in ((50, 'file', 'BBCA', 2, 400), (40, 'file', 'BBRI', 3, 100),
                                                       (30, 'history_price', 'BBCA', 1, 50), (5, 'file', 'BBCA', 1, 10)):
                c.execute("INSERT INTO terminal.access_log(subscriber_id, at, kind, ticker, bytes, file_count) "
                          "VALUES (%s, now() - make_interval(mins => %s), %s, %s, %s, %s)",
                          (sid, minutes, kind, ticker, size, files))
            near = lambda q, excess, minutes: abs(store.frees_in(c, sid, quota.Refusal(q, 1, 'hour', excess))
                                                  - minutes * 60) <= 2
            assert near('files_per_hour', 1, 10) and near('files_per_hour', 2, 10)       # the first row frees 2 files
            assert near('files_per_hour', 3, 20) and near('files_per_hour', 6, 55)
            assert store.frees_in(c, sid, quota.Refusal('files_per_hour', 1, 'hour', 7)) is None   # never enough
            assert near('history_per_hour', 1, 30)
            assert near('tickers_per_hour', 1, 20)                    # BBRI's newest read (40 min ago) leaves first
            assert abs(store.frees_in(c, sid, quota.Refusal('tickers_per_day', 1, '24 hours')) - (24 * 60 - 40) * 60) <= 2
            assert abs(store.frees_in(c, sid, quota.Refusal('megabytes_per_day', 1, '24 hours', 450))
                       - (24 * 60 - 40) * 60) <= 2
            c.execute('DELETE FROM terminal.subscriber WHERE subscriber_id = %s', (sid,))
    finally:
        store.close()


def test_every_quota_of_check_has_a_frees_query():
    from app.store import FREES
    names = {quota.check(LIMITS | {k: 0}, quota.Usage(0, frozenset(), frozenset(), 0, 0), files=1, ticker='BBCA',
                         bytes_=1, history=1).quota for k in ('files_per_hour', 'history_per_hour', 'tickers_per_hour',
                                                              'tickers_per_day', 'megabytes_per_day')}
    assert names == set(FREES)


# ---- R2-5: a dataset id this terminal-api does not know is left out, never a failure of every call ------------------

def test_an_unknown_dataset_id_is_left_out_and_logged(caplog):
    from test_phase3c import caps, make, owner
    client, store, _ = make()
    ahead = owner(capabilities=caps(datasets=['price', 'fx']))           # an edge-bff that knows one dataset more
    with caplog.at_level('WARNING', 'terminal-api'):
        r = client.post(f'{API}/bundle', headers=ahead, json={'ticker': 'BBCA', 'datasets': ['price', 'broker']})
    assert r.status_code == 200, r.text
    assert r.json()['datasets']['broker'] == {'locked': True, 'capability': 'terminal.dataset:broker'}
    assert 'owner_datasets_ignored' in caplog.text and '"fx"' in caplog.text
    # an id the plan holds but this terminal-api lacks is not served: left out, so only the known ones count
    from app.entitlements import parse_capabilities
    got = parse_capabilities(caps(datasets=['fx']), ('price', 'broker'))
    assert got.datasets == frozenset() and got.ignored == ('fx',) and not got.dataset_ok('fx')


# ---- R1-22: history_days 0 is the empty window ------------------------------------------------------------------------

def test_history_days_zero_serves_no_dated_row_and_the_page_files_still_work():
    from test_phase3c import caps, make, owner
    client, store, bucket = make()
    none = owner(capabilities=caps(history_days=0))
    m = client.get(f'{API}/manifest/BBCA', headers=none).json()['datasets']
    assert m['price']['years'] == {} and m['price']['cut'] == {'history_days': 0, 'after': '2026-11-17'}
    r = client.post(f'{API}/bundle', headers=none, json={'ticker': 'BBCA', 'datasets': ['price']})
    assert r.status_code == 200 and r.json()['datasets']['price']['files'] == []
    r = client.post(f'{API}/files', headers=none, json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]})
    assert r.status_code == 403 and r.json()['capability'] == 'terminal.history_days'
    assert client.get(f'{API}/radar', headers=none).status_code in (200, 503)      # no history window: not refused


# ---- R2-4: every answer to an owner call acknowledges the header it applied ------------------------------------------

def test_every_answer_to_an_owner_call_carries_the_applied_version():
    from app.entitlements import APPLIED_HEADER
    from test_phase3c import FREE, GATEWAY, make
    client, _, _ = make()
    for method, url, body in (('get', '/manifest/BBCA', None), ('get', '/manifest/BBRI', None),     # 200 and a refusal
                              ('post', '/bundle', {'ticker': 'BBCA', 'datasets': ['price']}),
                              ('get', '/state', None), ('get', '/logo/BBCA', None),
                              ('post', '/files', {'ticker': 'BBCA', 'dataset': 'price', 'years': [1999]})):
        r = getattr(client, method)(f'{API}{url}', headers=FREE, **({'json': body} if body else {}))
        assert r.headers.get(APPLIED_HEADER) == '1 db-0123456789ab', (url, r.status_code, dict(r.headers))
    # a call without the owner headers is answered as before, with no acknowledgement
    assert APPLIED_HEADER not in client.get(f'{API}/manifest/BBCA', headers=GATEWAY).headers


# ---- R2-32: a plan without the reference lists gets its own copy of each reference file ------------------------------

OTHERS = ('BBRI', 'TLKM', 'IHSG', 'FR0100')                  # what the free plan's copies may never name
REFERENCE_FILES = {
    'tickers': {'schema_version': 1, 'columns': ['ticker', 'name', 'type', 'sector'],
                'ticker': ['BBCA', 'BBRI', 'TLKM', 'IHSG'], 'name': ['Bank Central Asia', 'BRI', 'Telkom', 'Composite'],
                'type': ['stock', 'stock', 'stock', 'index'], 'sector': ['Finance', 'Finance', 'Infra', None]},
    'brokers': {'schema_version': 1, 'columns': ['code', 'name', 'type', 'classification'], 'code': ['YP', 'CC'],
                'name': ['YP', 'CC'], 'type': ['Domestic', 'Foreign'], 'classification': ['Retail-heavy', 'Mixed'],
                'type_means': 'broker domicile'},
    'logos': {'schema_version': 1, 'columns': ['ticker', 'file', 'sha256', 'source', 'fetched_at'],
              'ticker': ['BBCA', 'TLKM'], 'file': ['BBCA.png', 'TLKM.svg'], 'sha256': ['a' * 64, 'b' * 64],
              'source': ['tv', 'tv'], 'fetched_at': ['2026-11-01', '2026-11-01'], 'generated_at': '2026-11-01'},
    'fixed_income': {'schema_version': 1, 'columns': ['ticker', 'name', 'country'], 'ticker': ['FR0100'],
                     'name': ['FR0100'], 'country': ['ID'], 'means': 'government bonds'},
    'stock_lists': {'schema_version': 1, 'columns': ['list_key', 'kind', 'code', 'name', 'members'],
                    'list_key': ['INDEX:LQ45'], 'kind': ['INDEX'], 'code': ['LQ45'], 'name': ['LQ45'],
                    'members': [['BBCA', 'BBRI', 'TLKM']]},
}


def reference_app():
    from test_api import FakeBucket
    from test_phase3c import CutBucket, gz, make
    bucket = CutBucket()
    refs = {}
    for name, doc in REFERENCE_FILES.items():
        body, sha = gz(doc)
        key = f'v1/ref/{name}.{sha[:16]}.json.gz'
        bucket.objects[key] = body
        refs[name] = {'key': key, 'sha256': sha, 'bytes': len(body), 'rows': len(doc[doc['columns'][0]])}
    bucket.state_doc = {**FakeBucket.state_doc, 'refs': refs}
    client, store, _ = make(bucket)
    return client, store, bucket


def own_copy(client, headers, name):
    import gzip
    import hashlib
    import json
    a = client.get(f'{API}/reference/{name}', headers=headers)
    assert a.status_code == 200, a.text
    a = a.json()
    assert a['url'] == f'{API}/reference/{name}/cut?sha256={a["sha256"]}' and a['expires_in_seconds'] == 0
    r = client.get(a['url'], headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers['content-type'] == 'application/gzip' and 'content-encoding' not in r.headers
    assert hashlib.sha256(r.content).hexdigest() == a['sha256'] == r.headers['x-terminal-cut-sha256']
    assert len(r.content) == a['bytes']
    doc = json.loads(gzip.decompress(r.content))
    assert len(doc[doc['columns'][0]]) == a['rows'] and doc['columns'] == REFERENCE_FILES[name]['columns']
    return doc, r.content


def test_the_free_plan_gets_reference_lists_that_name_its_own_tickers_only():
    from test_phase3c import FREE
    client, store, bucket = reference_app()
    copies = {name: own_copy(client, FREE, name) for name in REFERENCE_FILES}
    assert copies['tickers'][0]['ticker'] == ['BBCA'] and copies['tickers'][0]['name'] == ['Bank Central Asia']
    assert copies['logos'][0]['ticker'] == ['BBCA'] and copies['logos'][0]['generated_at'] == '2026-11-01'
    assert copies['brokers'][0]['code'] == [] and copies['brokers'][0]['type_means'] == 'broker domicile'
    assert copies['fixed_income'][0]['ticker'] == [] and copies['stock_lists'][0]['members'] == []
    for name, (doc, raw) in copies.items():
        for other in OTHERS:
            assert other not in str(doc), (name, other)
    # counted when served: one audit row per copy read, under REF, none for the announcements
    rows = [a for a in store.access if a['dataset'] == 'reference']
    assert len(rows) == len(REFERENCE_FILES) and all(a['ticker'] == 'REF' for a in rows)
    assert all(a['key'].startswith('refcut/') for a in rows)
    # one source, one plan: one copy, built once (the browser's cache by sha256 keeps working)
    reads = len(bucket.reads)
    assert own_copy(client, FREE, 'tickers')[1] == copies['tickers'][1] and len(bucket.reads) == reads


def test_the_broker_list_follows_the_broker_dataset_and_the_full_lists_follow_reference():
    from test_phase3c import ADMIN_CAPS, GATEWAY, caps, owner
    client, store, _ = reference_app()
    brokers = owner(capabilities=caps(tickers=['BBCA', 'TLKM'], datasets=['price', 'broker']))
    assert own_copy(client, brokers, 'brokers')[0]['code'] == ['YP', 'CC']
    assert own_copy(client, brokers, 'tickers')[0]['ticker'] == ['BBCA', 'TLKM']
    # every ticker and no reference lists: every ticker row, still a copy (the dataset decides, not the tickers)
    every = owner(capabilities=caps(tickers='*', datasets=['price']))
    assert own_copy(client, every, 'tickers')[0]['ticker'] == ['BBCA', 'BBRI', 'TLKM', 'IHSG']
    # the reference lists in full, an admin owner and the gateway without an owner: the published file, presigned
    for headers in (owner(capabilities=caps(datasets=['price', 'reference'])), owner(capabilities=ADMIN_CAPS), GATEWAY):
        a = client.get(f'{API}/reference/tickers', headers=headers).json()
        assert a['url'].startswith('https://bucket.example/v1/ref/tickers.'), a
        r = client.get(f'{API}/reference/tickers/cut?sha256={"a" * 64}', headers=headers)
        assert r.status_code == 404 and r.json()['error'] == 'no_cut' and 'Fix:' in r.json()['message']


def test_a_reference_file_that_cannot_be_filtered_is_refused_not_served_whole():
    from test_phase3c import FREE, gz
    client, store, bucket = reference_app()
    broken = {'columns': ['ticker', 'name'], 'ticker': ['BBCA', 'BBRI'], 'name': ['only one']}
    body, sha = gz(broken)
    key = f'v1/ref/tickers.{sha[:16]}.json.gz'
    bucket.objects[key] = body
    bucket.state_doc['refs']['tickers'] = {'key': key, 'sha256': sha, 'bytes': len(body), 'rows': 2}
    r = client.get(f'{API}/reference/tickers', headers=FREE)
    assert r.status_code == 503 and r.json()['error'] == 'reference_unavailable' and 'not served whole' in r.text
    other = gz({'columns': ['ticker'], 'ticker': ['BBRI']})[0]
    bucket.objects[key] = other                                   # not the bytes the publication announces
    bucket.state_doc['refs']['tickers']['sha256'] = sha.replace(sha[16], 'f' if sha[16] != 'f' else 'e', 1)
    r = client.get(f'{API}/reference/tickers', headers=FREE)
    assert r.status_code in (404, 503) and 'BBRI' not in r.text


def test_every_reference_file_the_publisher_writes_has_its_rule_here():
    """A new reference file (publisher.py REF_NAMES) gets a fixture above and a decided copy for the free plan before
    it ships: refcut.py serves an undeclared file without a ticker column with no rows."""
    import re
    from pathlib import Path
    from app import refcut
    publisher = (Path(__file__).resolve().parents[2] / 'terminal-publisher' / 'publisher.py').read_text()
    names = set(re.findall(r"'([a-z_]+)'", re.search(r'^REF_NAMES = \(([^)]*)\)', publisher, re.M).group(1)))
    assert names == set(REFERENCE_FILES), names
    assert set(refcut.BY_DATASET) <= names


# ---- R1-4: the gateway's own account, on which every EDGE call depends, is visible on /ready ----------------------

def test_ready_reports_the_gateway_account_and_stays_ready(caplog):
    from test_phase3c import make
    client, store, _ = make()
    states = {}
    store.gateway_state = lambda c, email: states.get(email)
    sub = 'sub@example.com'                                          # make()'s TERMINAL_PROXY_SUBSCRIBER
    for row, want in ((None, {'state': 'missing'}),
                      ({'active': True, 'seconds_left': 400 * 86400.0}, {'state': 'ok', 'days_left': 400}),
                      ({'active': True, 'seconds_left': 29.5 * 86400}, {'state': 'expiring', 'days_left': 29}),
                      ({'active': True, 'seconds_left': -5.0}, {'state': 'expired', 'days_left': 0}),
                      ({'active': False, 'seconds_left': 400 * 86400.0}, {'state': 'inactive', 'days_left': 400})):
        states[sub] = row
        caplog.clear()
        with caplog.at_level('WARNING', 'terminal-api'):
            r = client.get('/ready')
        assert r.status_code == 200 and r.json() == {'status': 'ready', 'gateway_account': want}, (row, r.text)
        assert (f'gateway_account_{want["state"]}' in caplog.text) == (want['state'] != 'ok')


def test_the_gateway_state_reads_the_row_on_a_real_server():
    url = os.environ.get('TERMINAL_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('TERMINAL_TEST_POSTGRES_URL is not set')
    from app.store import Store
    store = Store(url, max_size=2)
    store.open()
    email = f'gateway-{os.getpid()}@example.com'
    try:
        with store.tx() as c:
            c.execute("INSERT INTO terminal.subscriber(email, display_name, password_hash, expires_at) VALUES "
                      "(%s, 'gateway', %s, now() + interval '10 days')", (email, 'scrypt$' + '0' * 32 + '$' + '0' * 64))
            row = store.gateway_state(c, email)
            assert row['active'] is True and 9.9 * 86400 < row['seconds_left'] <= 10 * 86400
            assert store.gateway_state(c, 'nobody@example.com') is None
            c.execute('DELETE FROM terminal.subscriber WHERE email = %s', (email,))
    finally:
        store.close()
