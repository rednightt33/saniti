"""terminal-api behaviour with an in-memory store and bucket (the SQL itself is checked live, Phase 7)."""
import copy
import datetime as dt
import json
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app import quota
from app.config import Settings
from app.main import API, create_app
from app.security import password_verifier, verify_password

ORIGIN = 'https://terminal.example'
NOW = dt.datetime.now(dt.timezone.utc)
LIMITS = {'url_ttl_seconds': 120, 'files_per_hour': 60, 'tickers_per_hour': 30, 'tickers_per_day': 150,
          'megabytes_per_day': 300, 'history_per_hour': 20, 'sessions_per_subscriber': 2, 'session_hours': 24,
          'failed_sign_ins_per_email': 10, 'failed_sign_ins_per_ip': 30,
          # EXEC-MU-RUNTIME T1: the service ceilings of migration 20261028_100
          'service_grants_per_hour': 20000, 'service_files_per_hour': 100000, 'service_megabytes_per_hour': 100000}


class FakeStore:
    """The SQL of app/store.py in memory. A transaction rolls back what it added when it raises (as psycopg's
    transaction() does): the audit rows and the service hour counters. `events` records the order of the account
    reads and the locks of every transaction (T3), `txs` the number of transactions."""
    def __init__(self):
        self.subs = {}
        self.sessions = {}
        self.access = []
        self.attempts = []
        self.limits_value = dict(LIMITS)
        self.history_rows = []
        self.admin = []
        self.events = []
        self.txs = 0
        self.hours = {}                                  # terminal.usage_hour: (sid, hour_start) -> counters
        self.hour = NOW.replace(minute=0, second=0, microsecond=0)

    @contextmanager
    def tx(self):
        self.txs += 1
        self.events.append(('tx',))
        access, hours = len(self.access), copy.deepcopy(self.hours)
        try:
            yield None
        except BaseException:
            del self.access[access:]
            self.hours = hours
            raise

    def ready(self):
        pass

    def lock_subscriber(self, c, sid):
        self.events.append(('lock', sid))

    def meter(self, c, sid, files, bytes_):
        h = self.hours.setdefault((sid, self.hour), {'hour_start': self.hour, 'grants': 0, 'files': 0, 'bytes': 0})
        h.update(grants=h['grants'] + 1, files=h['files'] + files, bytes=h['bytes'] + bytes_)
        return dict(h)

    def limits(self, c, sid):
        return dict(self.limits_value)

    def usage(self, c, sid):
        mine = [a for a in self.access if a['sid'] == sid]
        tickers = frozenset(a['ticker'] for a in mine if a['ticker'] != quota.REF)
        return quota.Usage(sum(a.get('files', 1) for a in mine if a['kind'] == 'file'), tickers, tickers,
                           sum(a['bytes'] for a in mine), sum(1 for a in mine if a['kind'].startswith('history')))

    def log_access(self, c, sid, kind, ticker, ip, dataset=None, year=None, key=None, bytes_=0, keys=None):
        self.access.append({'sid': sid, 'kind': kind, 'ticker': ticker, 'key': key or (keys[0] if keys else None),
                            'keys': keys, 'files': len(keys) if keys else 1, 'bytes': bytes_, 'dataset': dataset})

    def prune(self, c, days):
        self.pruned = days

    def failed_sign_ins(self, c, email, ip):
        bad = [a for a in self.attempts if not a[2]]
        return sum(1 for a in bad if a[0] == email), sum(1 for a in bad if a[1] == ip)

    def record_sign_in(self, c, email, ip, ok):
        self.attempts.append((email, ip, ok))

    def subscriber_by_email(self, c, email):
        for sid, s in self.subs.items():
            if s['email'] == email:
                return {'subscriber_id': sid, 'password_hash': s['hash'], 'active': s['active'],
                        'current': s['expires_at'] > dt.datetime.now(dt.timezone.utc), 'kind': s.get('kind', 'person')}
        return None

    def open_session(self, c, sid, th, ip, hours, max_sessions):
        mine = [k for k, v in self.sessions.items() if v['sid'] == sid and not v['revoked']]
        for k in mine[:max(0, len(mine) - (max_sessions - 1))]:
            self.sessions[k]['revoked'] = True
        self.sessions[th] = {'sid': sid, 'revoked': False}

    def session_subscriber(self, c, th):
        self.events.append(('session', th))
        s = self.sessions.get(th)
        if not s or s['revoked']:
            return None
        u = self.subs[s['sid']]
        if not u['active'] or u['expires_at'] <= dt.datetime.now(dt.timezone.utc) or u.get('kind', 'person') != 'person':
            return None
        return {'subscriber_id': s['sid'], 'email': u['email'], 'display_name': u['name'], 'expires_at': u['expires_at'],
                'kind': 'person'}

    def account(self, c, email, kind):
        self.events.append(('account', email))
        for sid, u in self.subs.items():
            if (u['email'] == email and u.get('kind', 'person') == kind and u['active']
                    and u['expires_at'] > dt.datetime.now(dt.timezone.utc)):
                return {'subscriber_id': sid, 'email': email, 'display_name': u['name'], 'expires_at': u['expires_at'],
                        'kind': kind}
        return None

    def revoke_session(self, c, th):
        if th in self.sessions:
            self.sessions[th]['revoked'] = True

    def password_hash(self, c, sid):
        return self.subs[sid]['hash']

    def set_password(self, c, sid, verifier, keep_token_hash=None):
        self.subs[sid]['hash'] = verifier
        for k, v in self.sessions.items():
            if v['sid'] == sid and k != keep_token_hash:
                v['revoked'] = True

    def add_subscriber(self, c, email, name, verifier, expires_at):
        sid = len(self.subs) + 1
        self.subs[sid] = {'email': email, 'name': name, 'hash': verifier, 'active': True, 'expires_at': expires_at}
        return sid

    def list_subscribers(self, c):
        return [{'subscriber_id': k, 'email': v['email'], 'active': v['active'], 'expires_at': v['expires_at']}
                for k, v in self.subs.items()]

    def update_subscriber(self, c, sid, fields):
        if sid not in self.subs:
            return False
        u = self.subs[sid]
        for k, v in fields.items():
            u[{'password_hash': 'hash', 'display_name': 'name'}.get(k, k)] = v
        if fields.get('active') is False or 'password_hash' in fields:
            for v in self.sessions.values():
                if v['sid'] == sid:
                    v['revoked'] = True
        return True

    def admin_log(self, c, action, sid, detail, ip):
        self.admin.append((action, sid, detail))

    def price_history(self, c, ticker, lo, hi):
        return self.history_rows

    def broker_history(self, c, *args):
        return self.history_rows


class FakeBucket:
    def __init__(self):
        files = {str(y): {'key': f'v1/price/BBCA/{y}.json.gz', 'sha256': 'a' * 64, 'bytes': 2000, 'rows': 240,
                          'first': f'{y}-01-02', 'last': f'{y}-12-30'} for y in range(2021, 2027)}
        broker = {str(y): {'key': f'v1/broker/BBCA/{y}.json.gz', 'sha256': 'b' * 64, 'bytes': 250_000,
                           'rows': 24000, 'first': f'{y}-01-02', 'last': f'{y}-12-30'} for y in range(2021, 2027)}
        events = {'all': {'key': 'v1/events/BBCA/all.json.gz', 'sha256': 'c' * 64, 'bytes': 9000, 'rows': 120,
                          'first': '2009-01-20', 'last': '2026-11-03'}}
        self.manifests = {'BBCA': {'window': {'first_year': 2021, 'last_year': 2026}, 'datasets': {
            'price': {'data_through': '2026-10-23', 'files': files},
            'events': {'data_through': '2026-10-25T17:04:28Z', 'files': events},
            'broker': {'data_through': '2026-08-31', 'files': broker}}}}

    def manifest(self, ticker):
        m = self.manifests.get('BBCA') if ticker == 'BBCA' else None
        if ticker.startswith('T') and ticker[1:].isdigit():  # T1..T999: tickers for the quota tests
            m = self.manifests['BBCA']
        return m

    state_doc = {'finished_at': '2026-10-27T13:03:17Z', 'price_through': '2026-10-27', 'broker_through': '2026-10-27',
                 'broker_behind_sessions': 0}

    def state(self):
        return self.state_doc

    def presign(self, key, ttl):
        return f'https://bucket.example/{key}?X-Amz-Expires={ttl}&sig=x'

    def logo(self, ticker):
        return (b'\x89PNG-logo', 'image/png', 'd' * 64) if ticker == 'BBCA' else None


SETTINGS = Settings(database_url='postgresql://terminal_api_login@x/db', admin_key='k' * 40, bucket_name='b',
                    bucket_endpoint='https://e', bucket_region='auto', bucket_access_key_id='a',
                    bucket_secret_access_key='s', allowed_origins=(ORIGIN,), secure_cookie=False)
ADMIN = {'x-terminal-admin-key': 'k' * 40}


@pytest.fixture()
def env():
    store, bucket = FakeStore(), FakeBucket()
    client = TestClient(create_app(SETTINGS, store, bucket), headers={'origin': ORIGIN})
    r = client.post(f'{API}/admin/subscribers', headers=ADMIN, json={
        'email': 'Sub@Example.com', 'display_name': 'Sub', 'password': 'correct horse battery',
        'expires_at': (NOW + dt.timedelta(days=30)).isoformat()})
    assert r.status_code == 201, r.text
    return client, store, bucket


def sign_in(client, password='correct horse battery'):
    return client.post(f'{API}/auth/sign-in', json={'email': 'sub@example.com', 'password': password})


def test_password_verifier_round_trip_and_unknown_account():
    v = password_verifier('correct horse battery')
    assert verify_password('correct horse battery', v) and not verify_password('wrong', v)
    assert not verify_password('anything', None)


def test_data_needs_a_session(env):
    client, _, _ = env
    assert client.get(f'{API}/manifest/BBCA').status_code == 401


def test_sign_in_then_manifest_and_files(env):
    client, store, _ = env
    assert sign_in(client).status_code == 200
    m = client.get(f'{API}/manifest/BBCA').json()
    assert m['datasets']['broker']['data_through'] == '2026-08-31' and 'key' not in m['datasets']['price']['years']['2026']
    r = client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'broker', 'years': [2025, 2026]}).json()
    assert [f['year'] for f in r['files']] == [2025, 2026] and r['expires_in_seconds'] == 120
    assert all('X-Amz-Expires=120' in f['url'] for f in r['files'])
    assert [a['key'] for a in store.access] == ['v1/broker/BBCA/2025.json.gz', 'v1/broker/BBCA/2026.json.gz']


def test_wrong_password_is_generic_and_throttled(env):
    client, store, _ = env
    assert sign_in(client, 'wrong password!').json()['error'] == 'sign_in_failed'
    store.limits_value['failed_sign_ins_per_email'] = 1
    assert sign_in(client).status_code == 429


def test_expired_or_disabled_subscription_is_refused(env):
    client, store, _ = env
    assert sign_in(client).status_code == 200
    client.post(f'{API}/admin/subscribers/1', headers=ADMIN, json={'active': False})
    assert client.get(f'{API}/manifest/BBCA').status_code == 401
    assert sign_in(client).json()['error'] == 'subscription_inactive'


def test_post_from_another_origin_is_refused(env):
    client, _, _ = env
    sign_in(client)
    r = client.post(f'{API}/files', headers={'origin': 'https://evil.example'},
                    json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]})
    assert r.status_code == 403 and r.json()['error'] == 'origin_not_allowed'


def test_quota_files_per_hour(env):
    client, store, _ = env
    sign_in(client)
    store.limits_value['files_per_hour'] = 3
    ok = client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2024, 2025, 2026]})
    assert ok.status_code == 200
    r = client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2023]})
    assert r.status_code == 429 and 'files_per_hour' in r.json()['message']


def test_quota_distinct_tickers_stops_a_crawl(env):
    client, store, _ = env
    sign_in(client)
    store.limits_value['tickers_per_hour'] = 5
    codes = [client.post(f'{API}/files', json={'ticker': f'T{i}', 'dataset': 'price', 'years': [2026]}).status_code
             for i in range(1, 8)]
    assert codes == [200] * 5 + [429, 429]
    # an already opened ticker stays available
    assert client.post(f'{API}/files', json={'ticker': 'T1', 'dataset': 'price', 'years': [2025]}).status_code == 200


def test_quota_bytes_per_day(env):
    client, store, _ = env
    sign_in(client)
    store.limits_value['megabytes_per_day'] = 1
    assert client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'broker',
                                             'years': [2021, 2022, 2023, 2024]}).status_code == 200
    r = client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'broker', 'years': [2025]})
    assert r.status_code == 429 and 'megabytes_per_day' in r.json()['message']


def test_unpublished_year_and_unknown_ticker(env):
    client, _, _ = env
    sign_in(client)
    r = client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2019]})
    assert r.status_code == 404 and 'history' in r.json()['message']
    assert client.get(f'{API}/manifest/ZZZZ').status_code == 404
    assert client.get(f'{API}/manifest/bbca').status_code == 400


def test_history_only_before_the_published_window_and_bounded(env):
    client, store, _ = env
    sign_in(client)
    r = client.get(f'{API}/history/price', params={'ticker': 'BBCA', 'from': '2020-01-01', 'to': '2021-03-01'})
    assert r.status_code == 400 and r.json()['error'] == 'use_published_files'
    r = client.get(f'{API}/history/broker', params={'ticker': 'BBCA', 'from': '2018-01-01', 'to': '2019-12-31'})
    assert r.json()['error'] == 'range_too_long'
    store.history_rows = [{'d': '2019-01-02', 'o': 1.0, 'h': 2.0, 'l': 0.5, 'c': 1.5, 'v': 10.0}]
    r = client.get(f'{API}/history/price', params={'ticker': 'BBCA', 'from': '2019-01-01', 'to': '2019-12-31'})
    assert r.status_code == 200 and r.json()['c'] == [1.5]
    assert store.access[-1]['kind'] == 'history_price' and store.access[-1]['bytes'] > 0


def test_history_broker_rejects_bad_broker_code(env):
    client, _, _ = env
    sign_in(client)
    r = client.get(f'{API}/history/broker', params={'ticker': 'BBCA', 'from': '2019-01-01', 'to': '2019-02-01',
                                                    'brokers': ['YP', 'x;drop']})
    assert r.status_code == 400 and r.json()['error'] == 'invalid_broker'


def test_admin_needs_the_key(env):
    client, _, _ = env
    assert client.get(f'{API}/admin/subscribers').status_code == 401
    assert client.get(f'{API}/admin/subscribers', headers={'x-terminal-admin-key': 'wrong'}).status_code == 401
    assert client.get(f'{API}/admin/subscribers', headers=ADMIN).json()['subscribers'][0]['email'] == 'sub@example.com'


def test_password_change_signs_out_other_sessions(env):
    client, store, _ = env
    other = TestClient(client.app, headers={'origin': ORIGIN})
    sign_in(other)
    sign_in(client)
    r = client.post(f'{API}/auth/change-password', json={'current_password': 'correct horse battery',
                                                          'new_password': 'a new long password'})
    assert r.status_code == 200
    assert other.get(f'{API}/auth/session').status_code == 401
    assert client.get(f'{API}/auth/session').status_code == 200


def test_third_session_revokes_the_oldest(env):
    client, _, _ = env
    a, b = (TestClient(client.app, headers={'origin': ORIGIN}) for _ in range(2))
    sign_in(a), sign_in(b), sign_in(client)
    assert a.get(f'{API}/auth/session').status_code == 401
    assert b.get(f'{API}/auth/session').status_code == 200


def test_reference_files_do_not_count_as_tickers(env):
    client, store, _ = env
    sign_in(client)
    r = client.get(f'{API}/reference/brokers')
    assert r.status_code == 200 and 'ref/brokers' in r.json()['url']
    assert store.usage(None, 1).tickers_hour == frozenset()


def test_responses_are_not_cached(env):
    client, _, _ = env
    assert client.get('/health').headers['cache-control'] == 'no-store'


def test_history_uses_the_window_of_its_own_dataset(env):
    client, store, bucket = env
    sign_in(client)
    bucket.manifests['BBCA']['datasets']['price']['first_year'] = 2018
    r = client.get(f'{API}/history/price', params={'ticker': 'BBCA', 'from': '2019-01-01', 'to': '2019-12-31'})
    assert r.status_code == 400 and '2018-01-01' in r.json()['message']
    r = client.get(f'{API}/history/broker', params={'ticker': 'BBCA', 'from': '2019-01-01', 'to': '2019-12-31'})
    assert r.status_code == 200


def test_events_file_needs_no_years_and_counts_as_one_file(env):
    client, store, _ = env
    sign_in(client)
    r = client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'events'})
    assert r.status_code == 200 and r.json()['files'][0]['year'] is None
    assert store.access[-1]['key'] == 'v1/events/BBCA/all.json.gz'
    r = client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'events', 'years': [2026]})
    assert r.status_code == 400
    r = client.post(f'{API}/files', json={'ticker': 'BBCA', 'dataset': 'price'})
    assert r.status_code == 400


def test_bundle_gives_every_file_of_the_ticker_in_one_call_with_the_same_counting(env):
    client, store, _ = env
    sign_in(client)
    store.locks = 0
    store.lock_subscriber = lambda c, sid: setattr(store, 'locks', store.locks + 1)
    r = client.post(f'{API}/bundle', json={'ticker': 'BBCA'})
    assert r.status_code == 200, r.text
    b = r.json()
    assert [f['year'] for f in b['datasets']['price']['files']] == list(range(2021, 2027))
    assert [f['year'] for f in b['datasets']['broker']['files']] == list(range(2021, 2027))
    assert b['datasets']['events']['files'][0]['year'] is None and b['expires_in_seconds'] == 120
    assert b['datasets']['broker']['data_through'] == '2026-08-31'
    assert len(store.access) == 1 and store.access[0]['files'] == 13 and store.locks == 1   # one row counts 13 files
    assert store.access[0]['bytes'] == 6 * 2000 + 6 * 250_000 + 9000 and store.pruned == 90
    r = client.post(f'{API}/bundle', json={'ticker': 'BBCA', 'datasets': ['price']})
    assert list(r.json()['datasets']) == ['price'] and sum(a['files'] for a in store.access) == 19


def test_bundle_quota_refuses_the_whole_bundle_and_logs_nothing(env):
    client, store, _ = env
    sign_in(client)
    store.limits_value['files_per_hour'] = 12
    r = client.post(f'{API}/bundle', json={'ticker': 'BBCA'})
    assert r.status_code == 429 and 'files_per_hour' in r.json()['message'] and store.access == []
    assert client.post(f'{API}/bundle', json={'ticker': 'NOPE'}).status_code == 404
    assert client.post(f'{API}/bundle', json={'ticker': 'BBCA', 'datasets': []}).status_code == 400
    assert client.post(f'{API}/bundle', json={'ticker': 'BBCA', 'datasets': ['history']}).status_code == 400


def test_logo_is_an_image_kept_a_week_without_quota_or_audit(env):
    client, store, _ = env
    assert client.get(f'{API}/logo/BBCA').status_code == 401
    sign_in(client)
    store.limits_value['files_per_hour'] = 0
    r = client.get(f'{API}/logo/BBCA')
    assert r.status_code == 200 and r.content == b'\x89PNG-logo' and r.headers['content-type'] == 'image/png'
    assert r.headers['cache-control'] == 'private, max-age=604800' and "sandbox" in r.headers['content-security-policy']
    assert store.access == []
    assert client.get(f'{API}/logo/GOTO').status_code == 404 and client.get(f'{API}/logo/bbca').status_code == 400
    assert client.get(f'{API}/manifest/BBCA').headers['cache-control'] == 'no-store'


def test_bundle_packs_give_one_price_file_and_the_broker_archive_before_the_last_yearly_files(env):
    client, store, bucket = env
    sign_in(client)
    bucket.manifests['BBCA']['packs'] = {
        'price': {'key': 'v1/pack/BBCA/price.json.gz', 'sha256': 'p' * 64, 'bytes': 30_000, 'rows': 1400},
        'broker-archive': {'key': 'v1/pack/BBCA/broker-archive.json.gz', 'sha256': 'q' * 64, 'bytes': 900_000,
                           'rows': 90_000, 'years': [2021, 2024]}}
    b = client.post(f'{API}/bundle', json={'ticker': 'BBCA', 'packs': True}).json()['datasets']
    assert [(f['year'], f.get('pack')) for f in b['price']['files']] == [(None, 'price')]
    assert [(f['year'], f.get('pack')) for f in b['broker']['files']] == [(None, 'broker-archive'), (2025, None), (2026, None)]
    assert store.access[-1]['files'] == 5                            # price pack, archive, 2025, 2026, events
    plain = client.post(f'{API}/bundle', json={'ticker': 'BBCA'}).json()['datasets']   # without packs: yearly files
    assert len(plain['price']['files']) == 6


PROXY_KEY = 'p' * 40


@pytest.fixture()
def gateway():
    store, bucket = FakeStore(), FakeBucket()
    settings = Settings(**{**SETTINGS.__dict__, 'proxy_key': PROXY_KEY, 'proxy_subscriber': 'sub@example.com'})
    client = TestClient(create_app(settings, store, bucket))
    r = client.post(f'{API}/admin/subscribers', headers={**ADMIN, 'origin': ORIGIN}, json={
        'email': 'sub@example.com', 'display_name': 'Owner', 'password': 'correct horse battery',
        'expires_at': (NOW + dt.timedelta(days=30)).isoformat()})
    assert r.status_code == 201, r.text
    return client, store


def test_gateway_key_acts_as_its_subscriber_with_quotas_and_audit(gateway):
    client, store = gateway
    h = {'x-terminal-proxy-key': PROXY_KEY}
    assert client.get(f'{API}/manifest/BBCA', headers=h).status_code == 200
    r = client.post(f'{API}/files', headers=h, json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]})
    assert r.status_code == 200 and store.access[-1]['sid'] == 1
    store.limits_value['files_per_hour'] = 1
    r = client.post(f'{API}/files', headers=h, json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2025]})
    assert r.status_code == 429


def test_gateway_wrong_key_or_inactive_account_is_refused(gateway):
    client, _ = gateway
    assert client.get(f'{API}/manifest/BBCA', headers={'x-terminal-proxy-key': 'x' * 40}).json()['error'] == \
        'proxy_key_rejected'
    client.post(f'{API}/admin/subscribers/1', headers={**ADMIN, 'origin': ORIGIN}, json={'active': False})
    assert client.get(f'{API}/manifest/BBCA', headers={'x-terminal-proxy-key': PROXY_KEY}).status_code == 401


def test_gateway_key_is_refused_when_not_configured(env):
    client, _, _ = env
    r = client.get(f'{API}/manifest/BBCA', headers={'x-terminal-proxy-key': PROXY_KEY})
    assert r.status_code == 401 and r.json()['error'] == 'proxy_key_rejected'


def test_proxy_settings_come_together_and_strong():
    with pytest.raises(ValueError):
        Settings(**{**SETTINGS.__dict__, 'proxy_key': PROXY_KEY}).validate()
    with pytest.raises(ValueError):
        Settings(**{**SETTINGS.__dict__, 'proxy_key': 'short', 'proxy_subscriber': 'a@b.c'}).validate()


def test_manifest_cache_holds_until_the_publisher_finishes_a_run(monkeypatch):
    """EXEC-TERMINAL-SPEED step 4: one state.json read per check interval, manifests read again only after a new run."""
    import io
    from app import bucket as bucket_mod
    reads = []
    state = {'finished_at': 'run-1'}

    class S3:
        class exceptions:
            NoSuchKey = KeyError
        def get_object(self, Bucket, Key):
            reads.append(Key)
            body = json.dumps(state if Key.endswith('state.json') else {'ticker': 'BBCA', 'run': state['finished_at']})
            return {'Body': io.BytesIO(body.encode())}
    b = object.__new__(bucket_mod.Bucket)
    b.name, b.s3, b.cache_seconds, b._cache, b._version, b._checked = 'x', S3(), 60, {}, None, None
    clock = [1000.0]
    monkeypatch.setattr(bucket_mod.time, 'monotonic', lambda: clock[0])
    assert b.manifest('BBCA')['run'] == 'run-1' and b.manifest('BBCA')['run'] == 'run-1'
    assert reads == ['v1/state.json', 'v1/manifest/BBCA.json']
    clock[0] += 3600; state['finished_at'] = 'run-1'
    b.manifest('BBCA'); assert reads[-1] == 'v1/state.json'               # same run: no manifest read
    clock[0] += 61; state['finished_at'] = 'run-2'
    assert b.manifest('BBCA')['run'] == 'run-2' and reads[-1] == 'v1/manifest/BBCA.json'


def test_state_names_the_publication_without_quota_or_audit(gateway):
    """EXEC-BACKTEST-LOAD K1: the publication the files belong to; no file granted, so no access row."""
    client, store = gateway
    h = {'x-terminal-proxy-key': PROXY_KEY}
    rows = len(store.access)
    r = client.get(f'{API}/state', headers=h)
    assert r.status_code == 200 and r.json()['finished_at'] == '2026-10-27T13:03:17Z' and r.json()['broker_through'] == '2026-10-27'
    assert len(store.access) == rows
    assert client.get(f'{API}/state').status_code == 401                     # no gateway key, no session


def test_state_unreadable_is_503():
    store, bucket = FakeStore(), FakeBucket()
    bucket.state_doc = None
    settings = Settings(**{**SETTINGS.__dict__, 'proxy_key': PROXY_KEY, 'proxy_subscriber': 'sub@example.com'})
    client = TestClient(create_app(settings, store, bucket))
    client.post(f'{API}/admin/subscribers', headers={**ADMIN, 'origin': ORIGIN}, json={
        'email': 'sub@example.com', 'display_name': 'Owner', 'password': 'correct horse battery',
        'expires_at': (NOW + dt.timedelta(days=30)).isoformat()})
    r = client.get(f'{API}/state', headers={'x-terminal-proxy-key': PROXY_KEY})
    assert r.status_code == 503 and r.json()['error'] == 'state_unavailable'


SHA_PRICE, SHA_ACTIONS = 'e' * 64, 'f' * 64
XSECTION = {   # EXEC-SCREENER: state.json `xsection`, as the publisher indexes the run's cross-sectional files
    'price': {'key': f'v1/xsection/price.{SHA_PRICE[:16]}.json.gz', 'sha256': SHA_PRICE, 'bytes': 14_000_000,
              'rows': 1_330_000, 'as_of': '2026-10-27'},
    'actions': {'key': f'v1/xsection/actions.{SHA_ACTIONS[:16]}.json.gz', 'sha256': SHA_ACTIONS, 'bytes': 40_000,
                'rows': 900, 'as_of': '2026-10-27'}}


def test_bucket_state_keeps_the_last_read_publication(monkeypatch):
    import io
    from app import bucket as bucket_mod
    state = {'finished_at': 'run-1', 'price_through': '2026-10-26', 'broker_through': '2026-10-23', 'broker_behind_sessions': 1,
             'window': {'first_year': 2021},
             'xsection': {'price': {**XSECTION['price'], 'stamp': 'publisher-only'},
                          'bad': {**XSECTION['actions'], 'key': 'v1/price/BBCA/2026.json.gz'}}}

    class S3:
        class exceptions:
            NoSuchKey = KeyError
        def get_object(self, Bucket, Key):
            if not Key.endswith('state.json'):
                raise KeyError(Key)
            return {'Body': io.BytesIO(json.dumps(state).encode())}
    b = object.__new__(bucket_mod.Bucket)
    b.name, b.s3, b.cache_seconds, b._cache, b._version, b._checked, b._state = 'x', S3(), 60, {}, None, None, None
    clock = [1000.0]
    monkeypatch.setattr(bucket_mod.time, 'monotonic', lambda: clock[0])
    assert b.state() == {'finished_at': 'run-1', 'price_through': '2026-10-26', 'broker_through': '2026-10-23',
                         'broker_behind_sessions': 1,                       # only the publication fields
                         'xsection': {'price': XSECTION['price']},          # and the index's well-formed entries
                         'refs': None}                                      # a run before the reference index
    state.update(finished_at='run-2', broker_through='2026-10-27', xsection=XSECTION)
    assert b.state()['finished_at'] == 'run-1'                              # within the check interval
    clock[0] += 61
    assert b.state()['finished_at'] == 'run-2' and b.state()['broker_through'] == '2026-10-27'
    assert b.state()['xsection'] == XSECTION                                # the index of the same read
    del state['xsection']
    clock[0] += 61
    assert b.state()['xsection'] is None                                    # a run without an index: null


# ---- EXEC-SCREENER: cross-sectional files (P1 a, user 2026-10-28; report 08 §8.12, test plan 10b.11) ---------------
GATEWAY = {'x-terminal-proxy-key': PROXY_KEY}


def gateway_client(bucket, store=None):
    """terminal-api with the gateway configured and its subscriber (sub@example.com, id 1) added."""
    store = store or FakeStore()
    settings = Settings(**{**SETTINGS.__dict__, 'proxy_key': PROXY_KEY, 'proxy_subscriber': 'sub@example.com'})
    client = TestClient(create_app(settings, store, bucket))
    r = client.post(f'{API}/admin/subscribers', headers={**ADMIN, 'origin': ORIGIN}, json={
        'email': 'sub@example.com', 'display_name': 'Owner', 'password': 'correct horse battery',
        'expires_at': (NOW + dt.timedelta(days=30)).isoformat()})
    assert r.status_code == 201, r.text
    return client, store


@pytest.fixture()
def rack():
    """The gateway, with a publication whose state.json indexes two cross-sectional files."""
    bucket = FakeBucket()
    bucket.state_doc = {**FakeBucket.state_doc, 'xsection': json.loads(json.dumps(XSECTION))}
    client, store = gateway_client(bucket)
    return client, store, bucket


def s3_bucket(state):
    """The real Bucket over a fake S3 that holds only state.json (and presigns any key)."""
    import io
    from app import bucket as bucket_mod

    class S3:
        class exceptions:
            NoSuchKey = KeyError

        def get_object(self, Bucket, Key):
            if not Key.endswith('state.json'):
                raise KeyError(Key)
            return {'Body': io.BytesIO(json.dumps(state).encode())}

        def generate_presigned_url(self, op, Params, ExpiresIn):
            return f'https://bucket.example/{Params["Key"]}?X-Amz-Expires={ExpiresIn}&sig=x'
    b = object.__new__(bucket_mod.Bucket)
    b.name, b.s3, b.cache_seconds, b._cache, b._version, b._checked, b._state = 'x', S3(), 60, {}, None, None, None
    return b


def test_xsection_grants_the_indexed_files_to_the_gateway_in_one_audit_row_under_ref(rack):
    client, store, _ = rack
    store.locks = 0
    store.lock_subscriber = lambda c, sid: setattr(store, 'locks', store.locks + 1)
    r = client.post(f'{API}/xsection', headers=GATEWAY, json={'names': ['price', 'actions', 'price']})
    assert r.status_code == 200, r.text
    b = r.json()
    assert (b['finished_at'], b['expires_in_seconds'], b['encoding']) == ('2026-10-27T13:03:17Z', 120, 'gzip json')
    assert [f['name'] for f in b['files']] == ['price', 'actions']             # a repeated name is one file
    assert b['files'][0] == {'name': 'price', 'url': f'https://bucket.example/{XSECTION["price"]["key"]}'
                                                     '?X-Amz-Expires=120&sig=x', 'sha256': SHA_PRICE,
                             'bytes': 14_000_000, 'rows': 1_330_000, 'as_of': '2026-10-27'}
    assert len(store.access) == 1 and store.locks == 1
    row = store.access[0]
    assert (row['sid'], row['kind'], row['ticker'], row['dataset']) == (1, 'file', quota.REF, 'xsection')
    assert row['keys'] == [XSECTION['price']['key'], XSECTION['actions']['key']] and row['files'] == 2
    assert row['bytes'] == 14_000_000 + 40_000                                 # bytes counted
    assert store.usage(None, 1).tickers_hour == frozenset()                    # REF is never an opened ticker
    assert store.usage(None, 1).files_hour == 2


def test_xsection_refuses_a_subscriber_session_and_a_caller_without_the_gateway_key(rack):
    client, store, _ = rack
    direct = TestClient(client.app, headers={'origin': ORIGIN})
    assert sign_in(direct).status_code == 200
    assert direct.get(f'{API}/state').status_code == 200                       # /state keeps its access: it grants nothing
    r = direct.post(f'{API}/xsection', json={'names': ['price']})
    assert r.status_code == 403 and r.json()['error'] == 'gateway_only' and 'x-terminal-proxy-key' in r.json()['message']
    r = client.post(f'{API}/xsection', json={'names': ['price']})             # neither key nor session
    assert r.status_code == 403 and r.json()['error'] == 'gateway_only'
    r = direct.post(f'{API}/xsection', headers={'x-terminal-proxy-key': 'x' * 40}, json={'names': ['price']})
    assert r.status_code == 401 and r.json()['error'] == 'proxy_key_rejected'
    assert store.access == []


def test_xsection_with_the_gateway_key_where_no_gateway_is_configured_is_refused(env):
    client, store, _ = env
    sign_in(client)
    r = client.post(f'{API}/xsection', headers=GATEWAY, json={'names': ['price']})
    assert r.status_code == 401 and r.json()['error'] == 'proxy_key_rejected' and store.access == []


def test_xsection_quota_refuses_every_name_and_logs_nothing(rack):
    client, store, _ = rack
    store.limits_value['files_per_hour'] = 1
    r = client.post(f'{API}/xsection', headers=GATEWAY, json={'names': ['price', 'actions']})
    assert r.status_code == 429 and 'files_per_hour' in r.json()['message'] and store.access == []
    store.limits_value.update(files_per_hour=60, megabytes_per_day=14)
    r = client.post(f'{API}/xsection', headers=GATEWAY, json={'names': ['price', 'actions']})
    assert r.status_code == 429 and 'megabytes_per_day' in r.json()['message'] and store.access == []
    assert client.post(f'{API}/xsection', headers=GATEWAY, json={'names': ['actions']}).status_code == 200
    assert len(store.access) == 1 and store.access[0]['bytes'] == 40_000


def test_xsection_unknown_or_malformed_names_are_refused_with_the_indexed_list(rack):
    client, store, _ = rack
    r = client.post(f'{API}/xsection', headers=GATEWAY, json={'names': ['price', 'flow_f06']})
    assert r.status_code == 404 and r.json()['error'] == 'xsection_not_published'
    assert "['flow_f06']" in r.json()['message'] and "['actions', 'price']" in r.json()['message']
    r = client.post(f'{API}/xsection', headers=GATEWAY, json={'names': ['price', 'Price!']})
    assert r.status_code == 400 and r.json()['fields'][0]['field'] == 'names.1'
    assert client.post(f'{API}/xsection', headers=GATEWAY, json={'names': []}).status_code == 400
    assert client.post(f'{API}/xsection', headers=GATEWAY, json={}).status_code == 400
    assert client.post(f'{API}/xsection', headers=GATEWAY,
                       json={'names': [f'n{i}' for i in range(17)]}).status_code == 400
    r = client.post(f'{API}/xsection', headers=GATEWAY,                    # a client never names a key
                    json={'names': ['price'], 'key': 'v1/manifest/BBCA.json'})
    assert r.status_code == 400 and r.json()['fields'][0]['field'] == 'key'
    assert store.access == []


def test_xsection_presigns_only_keys_of_the_xsection_family(rack):
    client, store, bucket = rack
    bucket.state_doc['xsection'].update(
        evil={**XSECTION['actions'], 'key': 'v1/manifest/BBCA.json'},
        other={**XSECTION['price']})                                       # another name's key
    for name in ('evil', 'other'):
        r = client.post(f'{API}/xsection', headers=GATEWAY, json={'names': [name]})
        assert r.status_code == 404 and "indexed: ['actions', 'price']" in r.json()['message']
    assert store.access == []


def test_xsection_without_an_index_or_a_readable_state(rack):
    client, store, bucket = rack
    bucket.state_doc = dict(FakeBucket.state_doc)                         # a publisher before the xsection writer
    r = client.post(f'{API}/xsection', headers=GATEWAY, json={'names': ['price']})
    assert r.status_code == 404 and 'indexed: none' in r.json()['message']
    bucket.state_doc = None
    r = client.post(f'{API}/xsection', headers=GATEWAY, json={'names': ['price']})
    assert r.status_code == 503 and r.json()['error'] == 'state_unavailable' and store.access == []


def test_state_returns_xsection_when_state_json_holds_it_and_still_answers_the_backtest_worker():
    publication = {'finished_at': '2026-10-28T12:58:02Z', 'price_through': '2026-10-28', 'broker_through': '2026-10-27',
                   'broker_behind_sessions': 1}
    state = {'schema_version': 1, **publication, 'window': [2021, 2026], 'price_first_year': 2018,
             'broker_first_year': 2016, 'last_mode': 'daily',
             'xsection': {**XSECTION, 'price': {**XSECTION['price'], 'stamp': 'publisher-only'}}}
    client, store = gateway_client(s3_bucket(state))
    s = client.get(f'{API}/state', headers=GATEWAY).json()
    assert s == {**publication, 'xsection': XSECTION, 'refs': None}         # each entry's five fields only
    # what apps/backtest-worker/src/terminal.ts publication() reads is unchanged
    assert {k: s[k] for k in ('finished_at', 'price_through', 'broker_through')} == \
        {k: publication[k] for k in ('finished_at', 'price_through', 'broker_through')}
    f = client.post(f'{API}/xsection', headers=GATEWAY, json={'names': ['actions']}).json()
    assert f['finished_at'] == publication['finished_at']
    assert f['files'][0]['url'] == f'https://bucket.example/{XSECTION["actions"]["key"]}?X-Amz-Expires=120&sig=x'
    assert len(store.access) == 1 and store.access[0]['dataset'] == 'xsection'
    del state['xsection']                                                  # the same app, a state without an index
    client2, _ = gateway_client(s3_bucket(state))
    assert client2.get(f'{API}/state', headers=GATEWAY).json() == {**publication, 'xsection': None, 'refs': None}


def test_xsection_index_keeps_only_well_formed_entries():
    from app.bucket import xsection_index
    good = XSECTION['price']
    assert xsection_index(None) is None and xsection_index(['price']) is None and xsection_index({}) == {}
    assert xsection_index({'price': {**good, 'stamp': 'x'}}) == {'price': good}
    own = lambda name, hexes=SHA_PRICE[:16]: f'v1/xsection/{name}.{hexes}.json.gz'   # the key the publisher writes
    refused = {
        'Price': good,                                                     # name: lower case, digits, _ and -
        'actions': good,                                                   # key of another name
        'a': {**good, 'key': own('a', 'g' * 16)},                          # not hex
        'b': {**good, 'key': 'v1/manifest/b.json'},
        'c': {**good, 'key': own('c', 'a' * 16), 'sha256': 'A' * 64},
        'd': {**good, 'key': own('d'), 'bytes': 0},
        'e': {**good, 'key': own('e'), 'bytes': True},
        'f': {**good, 'key': own('f'), 'rows': -1},
        'g': {**good, 'key': own('g'), 'rows': '5'},
        'h': 'v1/xsection/h.json.gz',
        'i': {**good, 'key': own('i', '0' * 16)}}                          # the 16 hex are not the sha256's first 16
    assert xsection_index(refused) == {}
    assert xsection_index({'a': {**good, 'key': own('a'), 'as_of': 7}})['a']['as_of'] is None



# ---- EXEC-MU-RUNTIME Phase 1b (user 2026-10-28, option A; verification/edge_multiuser/runtime/terminal.md) --------
BACKTEST_KEY, SCREENER_KEY = 'B' * 40, 'S' * 40
BACKTEST = {'x-terminal-proxy-key': BACKTEST_KEY}
SCREENER = {'x-terminal-proxy-key': SCREENER_KEY}


def services_client(bucket=None):
    """terminal-api with the gateway (sub@example.com, id 1) and the two service accounts of migration 20261028_100
    (backtest-worker id 2, screener-worker id 3), each with its own key."""
    bucket = bucket or FakeBucket()
    store = FakeStore()
    settings = Settings(**{**SETTINGS.__dict__, 'proxy_key': PROXY_KEY, 'proxy_subscriber': 'sub@example.com',
                           'service_keys': (('backtest-worker', BACKTEST_KEY), ('screener-worker', SCREENER_KEY))})
    settings.validate()
    client = TestClient(create_app(settings, store, bucket))
    r = client.post(f'{API}/admin/subscribers', headers={**ADMIN, 'origin': ORIGIN}, json={
        'email': 'sub@example.com', 'display_name': 'Owner', 'password': 'correct horse battery',
        'expires_at': (NOW + dt.timedelta(days=30)).isoformat()})
    assert r.status_code == 201, r.text
    for sid, name in ((2, 'backtest-worker'), (3, 'screener-worker')):
        store.subs[sid] = {'email': f'{name}@terminal.local', 'name': f'{name} (service account)', 'kind': 'service',
                           'hash': password_verifier('a service never signs in'), 'active': True,
                           'expires_at': NOW + dt.timedelta(days=365 * 70)}
    return client, store, bucket


def test_service_key_acts_as_its_own_account_and_cannot_name_an_owner():
    client, store, _ = services_client()
    assert client.get(f'{API}/manifest/BBCA', headers=BACKTEST).status_code == 200
    r = client.post(f'{API}/bundle', headers=BACKTEST, json={'ticker': 'BBCA', 'packs': True})
    assert r.status_code == 200, r.text
    row = store.access[-1]
    assert (row['sid'], row['ticker'], row['files']) == (2, 'BBCA', 13)              # its own audit row
    assert store.hours[(2, store.hour)] == {'hour_start': store.hour, 'grants': 1, 'files': 13,
                                            'bytes': 6 * 2000 + 6 * 250_000 + 9000}   # its own hourly counter
    assert ('lock', 2) in store.events and ('lock', 1) not in store.events          # its own lock
    assert store.usage(None, 1) == quota.Usage(0, frozenset(), frozenset(), 0, 0)    # nothing on the people's account
    store.limits_value.update(files_per_hour=1, tickers_per_hour=1)                 # a person's quotas never apply to it
    assert client.post(f'{API}/bundle', headers=BACKTEST, json={'ticker': 'T7'}).status_code == 200
    # the gateway key works as before: the people's account, its rolling quotas, no hourly counter
    assert client.post(f'{API}/bundle', headers=GATEWAY, json={'ticker': 'BBCA', 'datasets': ['events']}).status_code == 200
    assert store.access[-1]['sid'] == 1 and set(store.hours) == {(2, store.hour)}
    # an owner header with a service key: refused (where, why, how to fix, example); the gateway ignores it until T2
    rows = len(store.access)
    for path in ('/state', '/manifest/BBCA'):
        r = client.get(f'{API}{path}', headers={**BACKTEST, 'x-terminal-proxy-owner': 'owner-a'})
        m = r.json()['message']
        assert r.status_code == 400 and r.json()['error'] == 'owner_not_allowed'
        assert 'backtest-worker' in m and 'can never name an owner' in m and 'Fix:' in m and 'Example:' in m
    r = client.post(f'{API}/bundle', headers={**BACKTEST, 'x-terminal-proxy-owner': 'owner-a'}, json={'ticker': 'BBCA'})
    assert r.status_code == 400 and len(store.access) == rows
    assert client.get(f'{API}/state', headers={**GATEWAY, 'x-terminal-proxy-owner': 'owner-a'}).status_code == 200
    # a service account never signs in, whatever its password, and never uses a person's routes
    r = TestClient(client.app, headers={'origin': ORIGIN}).post(f'{API}/auth/sign-in', json={
        'email': 'backtest-worker@terminal.local', 'password': 'a service never signs in'})
    assert r.status_code == 401 and r.json()['error'] == 'sign_in_failed'
    r = client.get(f'{API}/history/price', headers=BACKTEST, params={'ticker': 'BBCA', 'from': '2019-01-01',
                                                                      'to': '2019-12-31'})
    assert r.status_code == 403 and r.json()['error'] == 'not_for_service_accounts' and 'Example:' in r.json()['message']
    # an unknown key, and the key of an account that is not active, are refused with their fix
    r = client.get(f'{API}/state', headers={'x-terminal-proxy-key': 'Z' * 40})
    assert r.status_code == 401 and r.json()['error'] == 'proxy_key_rejected'
    assert 'TERMINAL_SERVICE_KEY_' in r.json()['message'] and 'Example:' in r.json()['message']
    store.subs[2]['active'] = False
    r = client.post(f'{API}/bundle', headers=BACKTEST, json={'ticker': 'BBCA'})
    assert r.status_code == 401 and r.json()['error'] == 'service_account_inactive'
    assert 'backtest-worker@terminal.local' in r.json()['message'] and 'Fix:' in r.json()['message']


def test_service_keys_are_strong_distinct_and_named():
    base = {**SETTINGS.__dict__, 'proxy_key': PROXY_KEY, 'proxy_subscriber': 'sub@example.com'}
    Settings(**{**base, 'service_keys': (('backtest-worker', BACKTEST_KEY),)}).validate()
    for bad in ((('backtest-worker', 'short'),), (('backtest-worker', PROXY_KEY),), (('backtest-worker', 'k' * 40),),
                (('backtest-worker', BACKTEST_KEY), ('screener-worker', BACKTEST_KEY)), (('Bad Name', BACKTEST_KEY),)):
        with pytest.raises(ValueError):
            Settings(**{**base, 'service_keys': bad}).validate()


def test_xsection_admits_only_the_screener_service_account():
    bucket = FakeBucket()
    bucket.state_doc = {**FakeBucket.state_doc, 'xsection': json.loads(json.dumps(XSECTION))}
    client, store, _ = services_client(bucket)
    r = client.post(f'{API}/xsection', headers=SCREENER, json={'names': ['price', 'actions']})
    assert r.status_code == 200, r.text
    row = store.access[-1]
    assert (row['sid'], row['ticker'], row['dataset'], row['files']) == (3, quota.REF, 'xsection', 2)
    assert store.hours[(3, store.hour)]['files'] == 2
    r = client.post(f'{API}/xsection', headers=BACKTEST, json={'names': ['price']})          # another service
    assert r.status_code == 403 and r.json()['error'] == 'gateway_only'
    assert 'backtest-worker' in r.json()['message'] and 'TERMINAL_SERVICE_KEY_SCREENER_WORKER' in r.json()['message']
    assert '${{terminal-api.TERMINAL_SERVICE_KEY_SCREENER_WORKER}}' in r.json()['message']
    # the gateway key keeps its access until a later step removes it (compatibility)
    assert client.post(f'{API}/xsection', headers=GATEWAY, json={'names': ['actions']}).status_code == 200
    assert store.access[-1]['sid'] == 1
    direct = TestClient(client.app, headers={'origin': ORIGIN})
    assert sign_in(direct).status_code == 200
    assert direct.post(f'{API}/xsection', json={'names': ['price']}).json()['error'] == 'gateway_only'
    assert len(store.access) == 2


def test_service_ceiling_refuses_with_its_message():
    client, store, _ = services_client()
    store.limits_value['service_grants_per_hour'] = 2
    codes = [client.post(f'{API}/bundle', headers=BACKTEST, json={'ticker': 'BBCA', 'datasets': ['events']}).status_code
             for _ in range(3)]
    assert codes == [200, 200, 429]
    r = client.post(f'{API}/bundle', headers=BACKTEST, json={'ticker': 'BBCA', 'datasets': ['events']})
    b, reset = r.json(), (store.hour + dt.timedelta(hours=1)).strftime('%H:%M UTC')
    assert r.status_code == 429 and b['error'] == 'service_ceiling_reached'
    for part in ('backtest-worker', 'service_grants_per_hour', '3 of 2 grants', 'runaway guard', f'until {reset}',
                 'Fix:', 'terminal.quota_override', 'Example of normal use:'):
        assert part in b['message'], part
    # a refused grant is rolled back with its transaction: no audit row, the counter not raised
    assert store.hours[(2, store.hour)]['grants'] == 2 and sum(a['sid'] == 2 for a in store.access) == 2
    # the gateway is not a service: its own rolling quotas, unaffected
    assert client.post(f'{API}/bundle', headers=GATEWAY, json={'ticker': 'BBCA', 'datasets': ['events']}).status_code == 200
    # files and megabytes have their own ceilings; a new clock hour starts from zero
    store.hour += dt.timedelta(hours=1)
    store.limits_value.update(service_grants_per_hour=100, service_files_per_hour=12)
    r = client.post(f'{API}/bundle', headers=BACKTEST, json={'ticker': 'BBCA'})              # 13 files
    assert r.status_code == 429 and '13 of 12 files' in r.json()['message']
    store.limits_value.update(service_files_per_hour=100, service_megabytes_per_hour=1)
    r = client.post(f'{API}/bundle', headers=BACKTEST, json={'ticker': 'BBCA'})              # 1.52 MB
    assert r.status_code == 429 and 'service_megabytes_per_hour' in r.json()['message'] and '(1.52 of 1 MB' in r.json()['message']
    assert client.post(f'{API}/bundle', headers=BACKTEST, json={'ticker': 'BBCA', 'datasets': ['price']}).status_code == 200


def test_inactive_account_is_refused_at_the_grant(monkeypatch):
    client, store, _ = services_client()
    assert client.get(f'{API}/manifest/BBCA', headers=GATEWAY).status_code == 200            # the account is known
    store.events.clear()
    assert client.post(f'{API}/bundle', headers=GATEWAY, json={'ticker': 'BBCA'}).status_code == 200
    # one transaction: the lock, then the account read (a process's first grant prunes after it, in its own)
    assert store.events[:4] == [('tx',), ('lock', 1), ('account', 'sub@example.com'), ('tx',)]
    # deactivated by the administrator through another process (this process's cache is not cleared)
    store.subs[1]['active'] = False
    assert client.get(f'{API}/manifest/BBCA', headers=GATEWAY).status_code == 200            # reads: up to 60 s more
    rows = len(store.access)
    r = client.post(f'{API}/bundle', headers=GATEWAY, json={'ticker': 'BBCA'})
    assert r.status_code == 401 and r.json()['error'] == 'session_ended' and len(store.access) == rows
    assert client.get(f'{API}/manifest/BBCA', headers=GATEWAY).status_code == 401            # the refusal drops the cache
    # deactivated while the grant waited for the lock: the account is read after it, so the grant is refused
    store.subs[1]['active'] = True
    assert client.get(f'{API}/state', headers=GATEWAY).status_code == 200
    def lock(c, sid):
        store.events.append(('lock', sid))
        store.subs[sid]['active'] = False
    monkeypatch.setattr(store, 'lock_subscriber', lock)
    r = client.post(f'{API}/files', headers=GATEWAY, json={'ticker': 'BBCA', 'dataset': 'events'})
    assert r.status_code == 401 and len(store.access) == rows
    # a signed-in session revoked elsewhere is refused at its next grant the same way
    store.subs[1]['active'] = True
    monkeypatch.undo()
    direct = TestClient(client.app, headers={'origin': ORIGIN})
    assert sign_in(direct).status_code == 200 and direct.get(f'{API}/manifest/BBCA').status_code == 200
    for v in store.sessions.values():
        v['revoked'] = True
    assert direct.post(f'{API}/bundle', json={'ticker': 'BBCA'}).status_code == 401 and len(store.access) == rows


def test_read_routes_reuse_the_account_for_60_seconds(monkeypatch):
    from app import accounts as accounts_mod
    clock = [5000.0]
    monkeypatch.setattr(accounts_mod.time, 'monotonic', lambda: clock[0])
    client, store, _ = services_client()
    lookups = lambda: sum(1 for e in store.events if e[0] in ('account', 'session'))
    assert client.get(f'{API}/manifest/BBCA', headers=BACKTEST).status_code == 200
    assert (lookups(), store.txs) == (1, 2)                     # the admin's add, then one lookup
    for path in ('/manifest/BBCA', '/state', '/logo/BBCA', '/manifest/BBCA'):
        clock[0] += 14
        assert client.get(f'{API}{path}', headers=BACKTEST).status_code == 200
    assert (lookups(), store.txs) == (1, 2)                     # 56 s later: no transaction for four reads
    clock[0] += 5
    assert client.get(f'{API}/state', headers=BACKTEST).status_code == 200
    assert (lookups(), store.txs) == (2, 3)                     # 61 s after the check: read once more
    # one transaction per grant once the account is known (the first grant of a process also prunes, once)
    client.post(f'{API}/bundle', headers=BACKTEST, json={'ticker': 'BBCA', 'datasets': ['events']})
    before = store.txs
    for _ in range(3):
        assert client.post(f'{API}/bundle', headers=BACKTEST, json={'ticker': 'BBCA', 'datasets': ['events']}).status_code == 200
    assert store.txs - before == 3
    # each credential has its own entry: the gateway is read once for itself
    assert client.get(f'{API}/state', headers=GATEWAY).status_code == 200 and store.events[-1] == ('account', 'sub@example.com')


REF_SHA = {name: (c * 64) for name, c in (('tickers', '1'), ('brokers', '2'), ('logos', '3'), ('sectors', '4'))}


def ref_entry(name, **over):
    return {'key': f'v1/ref/{name}.{REF_SHA[name][:16]}.json.gz', 'sha256': REF_SHA[name], 'bytes': 14_449,
            'rows': 845, **over}


def test_state_lists_refs_and_reference_presigns_only_indexed_keys():
    """T5 (api side; the bundle `refs` of T4 are Phase 3): /state shows the reference index, /reference presigns the
    indexed content key, and the fixed key for a name the index lacks or a publication without an index."""
    state = {'finished_at': '2026-10-29T00:51:00Z', 'price_through': '2026-10-28', 'broker_through': '2026-10-28',
             'broker_behind_sessions': 0,
             'refs': {'tickers': {**ref_entry('tickers'), 'stamp': 'publisher-only'},
                      'brokers': ref_entry('brokers', key='v1/xsection/brokers.2222222222222222.json.gz'),  # wrong family
                      'sectors': ref_entry('sectors', rows=40)}}
    client, store = gateway_client(s3_bucket(state))
    s = client.get(f'{API}/state', headers=GATEWAY).json()
    assert s['refs'] == {'tickers': ref_entry('tickers'), 'sectors': ref_entry('sectors', rows=40)}
    r = client.get(f'{API}/reference/tickers', headers=GATEWAY).json()
    assert r == {'url': f'https://bucket.example/{ref_entry("tickers")["key"]}?X-Amz-Expires=120&sig=x',
                 'expires_in_seconds': 120, 'encoding': 'gzip json', 'sha256': REF_SHA['tickers'], 'bytes': 14_449,
                 'rows': 845}
    a = store.access[-1]
    assert (a['ticker'], a['dataset'], a['key'], a['bytes']) == (quota.REF, 'reference', ref_entry('tickers')['key'], 14_449)
    assert store.usage(None, 1).tickers_hour == frozenset()                       # never an opened ticker
    for name in ('brokers', 'logos'):                                             # malformed or not indexed: fixed key
        r = client.get(f'{API}/reference/{name}', headers=GATEWAY).json()
        assert r['url'].startswith(f'https://bucket.example/v1/ref/{name}.json.gz?') and r['sha256'] is None
        assert store.access[-1]['key'] == f'v1/ref/{name}.json.gz' and store.access[-1]['bytes'] == 0
    assert 'v1/ref/sectors.4444' in client.get(f'{API}/reference/sectors', headers=GATEWAY).json()['url']
    r = client.get(f'{API}/reference/manifest', headers=GATEWAY)
    assert r.status_code == 404 and r.json()['message'] == 'Reference files: brokers, logos, sectors, tickers.'
    rows = len(store.access)
    del state['refs']                                                             # a publication before the index
    old, _ = gateway_client(s3_bucket(state))
    assert old.get(f'{API}/state', headers=GATEWAY).json()['refs'] is None
    r = old.get(f'{API}/reference/tickers', headers=GATEWAY).json()
    assert 'v1/ref/tickers.json.gz?' in r['url'] and (r['sha256'], r['bytes'], r['rows']) == (None, None, None)
    assert old.get(f'{API}/reference/sectors', headers=GATEWAY).status_code == 404 and len(store.access) == rows


def test_refs_index_keeps_only_well_formed_entries():
    from app.bucket import refs_index
    good = ref_entry('tickers')
    assert refs_index(None) is None and refs_index(['tickers']) is None and refs_index({}) == {}
    assert refs_index({'tickers': {**good, 'as_of': '2026-10-28', 'stamp': 'x'}}) == {'tickers': good}
    own = lambda name, hexes=REF_SHA['tickers'][:16]: f'v1/ref/{name}.{hexes}.json.gz'
    refused = {
        'Tickers': good,                                                           # name: lower case, digits, _ and -
        'brokers': good,                                                           # key of another name
        'a': {**good, 'key': own('a', 'g' * 16)},                                  # not hex
        'b': {**good, 'key': 'v1/ref/b.json.gz'},                                  # the fixed key is not an index key
        'c': {**good, 'key': f'v1/xsection/c.{REF_SHA["tickers"][:16]}.json.gz'},  # another family
        'd': {**good, 'key': own('d'), 'bytes': 0},
        'e': {**good, 'key': own('e'), 'rows': True},
        'f': {**good, 'key': own('f'), 'sha256': 'A' * 64},
        'g': {**good, 'key': own('g', '0' * 16)},                                  # 16 hex not the sha256's first 16
        'h': 'v1/ref/h.json.gz'}
    assert refs_index(refused) == {}


def test_pool_size_comes_from_the_environment(monkeypatch):
    from app.store import Store
    for name, value in {'TERMINAL_DATABASE_URL': 'postgresql://terminal_api_login@db/x', 'TERMINAL_ADMIN_KEY': 'k' * 40,
                        'TERMINAL_BUCKET_NAME': 'b', 'TERMINAL_BUCKET_ENDPOINT': 'https://e',
                        'TERMINAL_BUCKET_REGION': 'auto', 'TERMINAL_BUCKET_ACCESS_KEY_ID': 'a',
                        'TERMINAL_BUCKET_SECRET_ACCESS_KEY': 's', 'TERMINAL_ALLOWED_ORIGINS': ORIGIN}.items():
        monkeypatch.setenv(name, value)
    for name in [n for n in __import__('os').environ if n.startswith('TERMINAL_SERVICE_KEY_')] + ['TERMINAL_POOL_MAX']:
        monkeypatch.delenv(name, raising=False)
    assert Settings.from_env().pool_max == 8                                      # the value before the variable
    monkeypatch.setenv('TERMINAL_POOL_MAX', '4')
    s = Settings.from_env()
    assert s.pool_max == 4 and Store(s.database_url, s.pool_max).pool.max_size == 4
    import app.store as store_mod                                                 # the store create_app builds
    built = []
    with monkeypatch.context() as m:
        m.setattr(store_mod, 'Store', lambda url, max_size=8: built.append(Store(url, max_size)) or built[-1])
        create_app(s, None, FakeBucket())
    assert [b.pool.max_size for b in built] == [4]
    for bad in ('0', '21', 'eight'):
        monkeypatch.setenv('TERMINAL_POOL_MAX', bad)
        with pytest.raises(ValueError, match='TERMINAL_POOL_MAX'):
            Settings.from_env()
    monkeypatch.setenv('TERMINAL_POOL_MAX', '8')
    monkeypatch.setenv('TERMINAL_SERVICE_KEY_BACKTEST_WORKER', BACKTEST_KEY)
    monkeypatch.setenv('TERMINAL_SERVICE_KEY_SCREENER_WORKER', SCREENER_KEY)
    monkeypatch.setenv('TERMINAL_SERVICE_KEY_UNUSED', '')                          # an empty variable names no service
    assert Settings.from_env().service_keys == (('backtest-worker', BACKTEST_KEY), ('screener-worker', SCREENER_KEY))


def test_ready_fails_while_the_schema_lacks_what_this_build_reads():
    """T9: /ready is the healthcheck (.railway/railway.ts), so a deployment started before migration 20261028_100
    never becomes ready (Railway keeps the previous one serving). Store.ready reads, without rows, every column and
    table the later migrations added; on a disposable PostgreSQL 16 the same check answered 503 before the migration
    and 200 after it (scratchpad build log api.md)."""
    from contextlib import contextmanager as cm
    from app.store import READY, Store

    class Conn:
        def __init__(self, missing):
            self.missing, self.ran = missing, []

        def execute(self, statement):
            self.ran.append(statement)
            if any(m in statement for m in self.missing):
                raise RuntimeError('column or relation does not exist')

    def store_with(missing):
        s, conn = Store('postgresql://terminal_api_login@db/x'), Conn(missing)
        s.tx = cm(lambda: (yield conn))
        return s, conn

    s, conn = store_with(())
    s.ready()
    assert conn.ran == list(READY)
    assert any('subscriber' in q and 'kind' in q for q in READY) and any('usage_hour' in q for q in READY)
    assert all(q.endswith('LIMIT 0') or q.endswith('LIMIT 1') for q in READY)          # no row is read
    for missing in ('kind', 'usage_hour', 'file_count'):
        s, _ = store_with((missing,))
        client = TestClient(create_app(SETTINGS, s, FakeBucket()))
        r = client.get('/ready')
        assert r.status_code == 503 and r.json() == {'status': 'not_ready'}, missing   # the driver error never leaks
    s, _ = store_with(())
    assert TestClient(create_app(SETTINGS, s, FakeBucket())).get('/ready').json() == {'status': 'ready'}


def test_railway_declares_the_healthcheck_and_a_key_variable_for_every_service_account():
    """T1/T9: the terminal-api block of .railway/railway.ts names /ready as its healthcheck and one
    TERMINAL_SERVICE_KEY_<NAME> per service account the migrations create (derived from their rows), so the IaC file,
    the migration and app/config.py cannot drift apart unnoticed."""
    import pathlib
    import re as re_
    from app.config import SERVICE_DOMAIN, service_variable
    root = pathlib.Path(__file__).resolve().parents[3]
    block = re_.search(r'service\("terminal-api", \{(.*?)\n  \}\);', (root / '.railway/railway.ts').read_text(), re_.S)
    assert block, 'terminal-api block not found in .railway/railway.ts'
    body = block.group(1)
    assert 'healthcheck: "/ready"' in body and 'TERMINAL_POOL_MAX' not in body.split('env:')[1]   # default 8 applies
    sql = ''.join(p.read_text() for p in sorted((root / 'database/migrations').glob('*_terminal_*.sql')))
    rows = re_.findall(r'INSERT INTO terminal\.subscriber \([^)]*\bkind\) VALUES(.*?)ON CONFLICT', sql, re_.S)
    services = sorted({m.group(1) for block in rows for m in re_.finditer(
        r"\('([a-z0-9-]+)@" + re_.escape(SERVICE_DOMAIN) + r"',[^\n]*\n[^\n]*'service'\)", block)})
    assert services == ['backtest-worker', 'screener-worker']
    for name in services:
        assert f'{service_variable(name)}: preserve()' in body, name
    assert 'TERMINAL_PROXY_KEY: preserve()' in body and 'TERMINAL_PROXY_SUBSCRIBER: preserve()' in body


# ---- EXEC-MU-RUNTIME Phase 1b review (adversarial reviewer of the api role, 2026-10-29) ----------------------------
def test_one_service_account_takes_one_key_variable(monkeypatch):
    """Two TERMINAL_SERVICE_KEY_ variables that differ only in case or in '-'/'_' name one service: both keys would act
    as that one account (a leftover after a rotation would stay valid). Refused at start, naming the variable to keep."""
    base = {**SETTINGS.__dict__, 'proxy_key': PROXY_KEY, 'proxy_subscriber': 'sub@example.com'}
    for twice in ((('backtest-worker', BACKTEST_KEY), ('backtest-worker', SCREENER_KEY)),
                  (('screener-worker', SCREENER_KEY), ('backtest-worker', BACKTEST_KEY), ('screener-worker', 'Q' * 40))):
        with pytest.raises(ValueError, match='one service account, one key') as e:
            Settings(**{**base, 'service_keys': twice}).validate()
        assert 'Fix: keep only TERMINAL_SERVICE_KEY_' in str(e.value)
    Settings(**{**base, 'service_keys': (('backtest-worker', BACKTEST_KEY), ('screener-worker', SCREENER_KEY))}).validate()
    for name, value in {'TERMINAL_DATABASE_URL': 'postgresql://terminal_api_login@db/x', 'TERMINAL_ADMIN_KEY': 'k' * 40,
                        'TERMINAL_BUCKET_NAME': 'b', 'TERMINAL_BUCKET_ENDPOINT': 'https://e',
                        'TERMINAL_BUCKET_REGION': 'auto', 'TERMINAL_BUCKET_ACCESS_KEY_ID': 'a',
                        'TERMINAL_BUCKET_SECRET_ACCESS_KEY': 's', 'TERMINAL_ALLOWED_ORIGINS': ORIGIN}.items():
        monkeypatch.setenv(name, value)
    for name in [n for n in __import__('os').environ if n.startswith('TERMINAL_SERVICE_KEY_')]:
        monkeypatch.delenv(name)
    monkeypatch.setenv('TERMINAL_SERVICE_KEY_BACKTEST_WORKER', BACKTEST_KEY)
    monkeypatch.setenv('TERMINAL_SERVICE_KEY_backtest-worker', SCREENER_KEY)                 # the same service again
    with pytest.raises(ValueError, match='2 variables name the service backtest-worker'):
        Settings.from_env()


def test_pool_limit_is_the_login_limit_shared_by_the_processes_of_a_replica(monkeypatch):
    """TERMINAL_POOL_MAX is per process; terminal_api_login's connection limit is for all of them together, and a
    replica runs the Dockerfile's --workers processes. A value the processes together could not open is refused at
    start (where, why, fix, example) instead of failing with 'too many connections' at the first peak."""
    import pathlib
    import re as re_
    from app.config import POOL_MAX_DEFAULT, POOL_MAX_LIMIT, PROCESSES_PER_REPLICA, ROLE_CONNECTION_LIMIT
    root = pathlib.Path(__file__).resolve().parents[3]
    cmd = re_.search(r'^CMD (\[.*\])$', (root / 'apps/terminal-api/Dockerfile').read_text(), re_.M)
    args = json.loads(cmd.group(1))
    assert int(args[args.index('--workers') + 1]) == PROCESSES_PER_REPLICA
    limit = re_.search(r"'terminal_api_login': \{.*?'limit': (\d+)", (root / 'scripts/provision_terminal_logins.py').read_text(),
                       re_.S)
    assert int(limit.group(1)) == ROLE_CONNECTION_LIMIT
    assert POOL_MAX_LIMIT * PROCESSES_PER_REPLICA <= ROLE_CONNECTION_LIMIT < (POOL_MAX_LIMIT + 1) * PROCESSES_PER_REPLICA
    assert 1 <= POOL_MAX_DEFAULT <= POOL_MAX_LIMIT
    base = {**SETTINGS.__dict__}
    Settings(**{**base, 'pool_max': POOL_MAX_LIMIT}).validate()
    for bad in (0, POOL_MAX_LIMIT + 1, ROLE_CONNECTION_LIMIT):
        with pytest.raises(ValueError) as e:
            Settings(**{**base, 'pool_max': bad}).validate()
        m = str(e.value)
        assert f'TERMINAL_POOL_MAX must be 1-{POOL_MAX_LIMIT}' in m and f'{bad} was given' in m
        assert 'Fix:' in m and 'for example TERMINAL_POOL_MAX=' in m


def test_railway_healthcheck_probes_the_port_the_app_listens_on():
    """Railway probes a healthcheck on the service's PORT. A service whose Dockerfile fixes its port (uvicorn --port
    8080) and that has a healthcheck must declare PORT (set to that port), as every other such service does; without it
    the probe goes to the port Railway injects and the deployment is never promoted. Derived for every service of
    .railway/railway.ts with a healthcheck, terminal-api included."""
    import pathlib
    import re as re_
    root = pathlib.Path(__file__).resolve().parents[3]
    text = (root / '.railway/railway.ts').read_text()
    checked = []
    for name, body in re_.findall(r'service\("([^"]+)", \{(.*?)\n  \}\);', text, re_.S):
        if 'healthcheck:' not in body:
            continue
        rootdir = re_.search(r'rootDirectory: "/(apps/[^"]+)"', body)
        dockerfile = root / (rootdir.group(1) if rootdir else f'apps/{name}') / 'Dockerfile'
        if not dockerfile.exists():
            continue
        fixed = re_.search(r'^CMD \[.*"--port", "(\d+)"', dockerfile.read_text(), re_.M)
        if fixed:
            assert re_.search(r'\bPORT: preserve\(\)', body.split('env:')[1]), f'{name}: healthcheck on port {fixed.group(1)} without PORT'
            checked.append(name)
    assert 'terminal-api' in checked and len(checked) >= 2


def test_megabyte_ceiling_message_never_reads_within_the_ceiling():
    hour = NOW.replace(minute=0, second=0, microsecond=0)
    limits = {'service_grants_per_hour': 10, 'service_files_per_hour': 10, 'service_megabytes_per_hour': 100_000}
    used = lambda b: {'hour_start': hour, 'grants': 1, 'files': 1, 'bytes': b}
    assert quota.check_service('backtest-worker', limits, used(100_000 * 1_000_000)) is None              # at the ceiling
    tiny = quota.check_service('backtest-worker', limits, used(100_000 * 1_000_000 + 4_000)).message()  # 4 KB over
    assert '(100,000.01 of 100,000 MB' in tiny
    limits['service_megabytes_per_hour'] = 1
    assert '(1.52 of 1 MB' in quota.check_service('backtest-worker', limits, used(1_521_000)).message()
    assert '(2 of 1 MB' in quota.check_service('backtest-worker', limits, used(2_000_000)).message()


def test_account_cache_is_dropped_where_this_process_changes_the_account():
    """T3: the read cache is never the reason a changed account keeps reading on the process that changed it: sign-out
    drops that session, an admin change and a password change clear the process's entries; a grant whose cached id is
    no longer the key's account takes the new account's lock and books on it; a service key never changes a password."""
    client, store, _ = services_client()
    store.limits_value['sessions_per_subscriber'] = 3
    one, two = (TestClient(client.app, headers={'origin': ORIGIN}) for _ in range(2))
    for c in (one, two):
        assert sign_in(c).status_code == 200 and c.get(f'{API}/manifest/BBCA').status_code == 200   # both cached
    # a password change on this process ends the other session at once (no cached read for it here)
    r = one.post(f'{API}/auth/change-password', json={'current_password': 'correct horse battery',
                                                       'new_password': 'another horse battery'})
    assert r.status_code == 200 and two.get(f'{API}/manifest/BBCA').status_code == 401
    # sign-out drops this session's entry at once (the same cookie, sent again, is not served from the cache)
    assert one.get(f'{API}/state').status_code == 200
    replay = TestClient(client.app, headers={'origin': ORIGIN}, cookies={'terminal_session': one.cookies.get('terminal_session')})
    assert replay.get(f'{API}/state').status_code == 200 and one.post(f'{API}/auth/sign-out').status_code == 200
    r = replay.get(f'{API}/state')
    assert r.status_code == 401 and r.json()['error'] == 'session_ended'
    # an admin change through this process: the gateway's next read is checked again, not served from the cache
    assert client.get(f'{API}/state', headers=GATEWAY).status_code == 200
    assert client.post(f'{API}/admin/subscribers/1', headers={**ADMIN, 'origin': ORIGIN}, json={'active': False}).status_code == 200
    assert client.get(f'{API}/state', headers=GATEWAY).status_code == 401
    client.post(f'{API}/admin/subscribers/1', headers={**ADMIN, 'origin': ORIGIN}, json={'active': True})
    # the gateway's account row replaced (same address, new id) while its old id is cached: the grant re-locks and
    # books on the new account
    assert client.get(f'{API}/state', headers=GATEWAY).status_code == 200
    store.subs[7] = store.subs.pop(1)
    store.events.clear()
    assert client.post(f'{API}/bundle', headers=GATEWAY, json={'ticker': 'BBCA', 'datasets': ['events']}).status_code == 200
    assert [e for e in store.events if e[0] == 'lock'][:2] == [('lock', 1), ('lock', 7)] and store.access[-1]['sid'] == 7
    # a service key never changes its account's password, even with the right current one
    before = store.subs[2]['hash']
    r = client.post(f'{API}/auth/change-password', headers=BACKTEST, json={
        'current_password': 'a service never signs in', 'new_password': 'a new service password'})
    assert r.status_code == 403 and r.json()['error'] == 'not_for_service_accounts' and store.subs[2]['hash'] == before
