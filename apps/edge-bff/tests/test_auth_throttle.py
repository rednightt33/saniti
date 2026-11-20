"""EXEC-MU-ACCOUNTS Phase 0 (CONTRACT.md sections 1 and 4 "Throttle"; migration 20261116_002): the sign-in throttle in
PostgreSQL, shared by every edge-bff instance.

Rule (a): 10 failed sign-ins per login in 15 minutes, counted for every login typed. How to pass (b): wait the
Retry-After seconds, or sign in correctly before the tenth failure (a success forgets the login's failures). Right (c):
nine wrong passwords, then the right one, signs in. Wrong (c): ten wrong passwords, then the right one, answers 429
SIGN_IN_RATE_LIMIT with Retry-After. Message (d): errors.MESSAGES['SIGN_IN_RATE_LIMIT'].
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main as main_module
from app.main import create_app
from app.store import Store
from app.throttle import SIGNIN_IP, SIGNIN_LOGIN, Throttle
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
MIGRATION = Path(__file__).resolve().parents[3] / 'database/migrations/20261116_002_edge_bff_accounts_auth_throttle.sql'


def sign_in(c, login='owner', password='local-test-password', **headers):
    return c.post('/api/v1/auth/sign-in', headers={**ORIGIN, **headers}, json={'login': login, 'password': password})


def rows(store):
    with store.connect() as c:
        return c.execute('SELECT scope, key_hash, count FROM edge_bff.auth_throttle ORDER BY scope').fetchall()


def test_ten_failures_across_two_instances_limit_the_login(settings, store):
    """Two app instances, each with its own connection pool, share one count: five failures on each, then both refuse,
    the right password included, with Retry-After."""
    with TestClient(create_app(settings, store, FakeOrc())) as a, \
            TestClient(create_app(settings, Store(settings.database_url), FakeOrc())) as b:
        for client in (a, b):
            for _ in range(5):
                assert sign_in(client, password='wrong').status_code == 401
        for client in (b, a):
            r = sign_in(client)
            assert r.status_code == 429, r.text
            error = r.json()['error']
            assert error['code'] == 'SIGN_IN_RATE_LIMIT' and error['message'] and 'Wait' in error['message']
            wait = int(r.headers['retry-after'])
            assert 1 <= wait <= 960 and error['details'] == {'retry_after_s': wait}
            assert 'edge_session' not in r.cookies
        # another login is not limited by the owner's failures
        assert sign_in(a, login='someone', password='wrong').status_code == 401


def test_the_login_is_normalised_and_a_success_forgets_its_failures(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        for login in ['OWNER', ' owner ', 'Owner'] * 3:              # nine failures of one login, however it is typed
            assert sign_in(c, login=login, password='wrong').status_code == 401
        assert sign_in(c).status_code == 200                           # (c) right: the tenth try is the right one
        for _ in range(9):
            assert sign_in(c, password='wrong').status_code == 401
        assert sign_in(c).status_code == 200
        assert sign_in(c, password='wrong').status_code == 401
        assert sum(r['count'] for r in rows(store) if r['scope'] == 'signin_email') == 1


def test_a_failure_outside_the_window_no_longer_counts(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        for _ in range(10):
            sign_in(c, password='wrong')
        assert sign_in(c).status_code == 429
        with store.connect() as db:
            db.execute("UPDATE edge_bff.auth_throttle SET window_start = window_start - interval '17 minutes'")
        assert sign_in(c).status_code == 200


def test_the_client_address_is_recorded_but_not_enforced(settings, store):
    """CONTRACT.md section 4: until a probe proves what Railway forwards, the per-address count is kept, not applied."""
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        for n in range(32):                                            # 32 failures from one address, 8 per login
            assert sign_in(c, login=f'user{n % 4}', password='wrong',
                           **{'X-Forwarded-For': '10.0.0.1, 203.0.113.7, 152.233.40.1'}).status_code == 401
        assert sign_in(c).status_code == 200
    ip = [r for r in rows(store) if r['scope'] == 'signin_ip']
    assert len(ip) >= 1 and sum(r['count'] for r in ip) == 32 > SIGNIN_IP.allowed
    assert ip[0]['key_hash'] == Throttle(store, settings.session_secret).key_hash(SIGNIN_IP, '203.0.113.7')


def test_keys_are_stored_only_as_keyed_hashes(settings, store):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        sign_in(c, login='Someone@Example.com', password='wrong')
    found = rows(store)
    assert {r['scope'] for r in found} == {'signin_email', 'signin_ip'}
    login = [r['key_hash'] for r in found if r['scope'] == 'signin_email'][0]
    throttle = Throttle(store, settings.session_secret)
    assert login == throttle.key_hash(SIGNIN_LOGIN, ('someone@example.com', 'testclient'))
    assert login != hashlib.sha256(b'someone@example.com').hexdigest()
    assert login != Throttle(store, 'another-secret-' * 3).key_hash(SIGNIN_LOGIN, ('someone@example.com', 'testclient'))
    with store.connect() as db:
        dump = str(db.execute('SELECT * FROM edge_bff.auth_throttle').fetchall()).lower()
    assert 'someone' not in dump and 'example' not in dump and 'testclient' not in dump


def test_the_password_is_checked_before_the_login_is_compared(settings, store, monkeypatch):
    """The timing property: a wrong login still runs the password check, so it costs what a wrong password costs."""
    seen = []
    real = main_module.verify_password
    monkeypatch.setattr(main_module, 'verify_password', lambda p, v: seen.append(p) or real(p, v))
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        assert sign_in(c, login='nobody', password='guess').status_code == 401
    assert seen == ['guess']


def test_counts_are_atomic_under_concurrency(settings, store):
    throttle = Throttle(store, settings.session_secret)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: Throttle(Store(settings.database_url), settings.session_secret).count(
            (SIGNIN_LOGIN, 'race')), range(24)))
    assert [r['count'] for r in rows(store)] == [24]
    assert throttle.retry_after(SIGNIN_LOGIN, 'race') > 0 and throttle.retry_after(SIGNIN_LOGIN, 'other') == 0
    assert throttle.retry_after(SIGNIN_IP, 'race') == 0                # not enforced


def test_rows_older_than_two_days_are_purged_with_the_sessions(settings, store):
    throttle = Throttle(store, settings.session_secret)
    throttle.count((SIGNIN_LOGIN, 'fresh'), (SIGNIN_LOGIN, 'old'))
    with store.connect() as db:
        db.execute("UPDATE edge_bff.auth_throttle SET window_start = now() - interval '2 days 1 minute' WHERE key_hash = %s",
                   (throttle.key_hash(SIGNIN_LOGIN, 'old'),))
    store.cleanup_sessions()
    assert [r['key_hash'] for r in rows(store)] == [throttle.key_hash(SIGNIN_LOGIN, 'fresh')]


def test_the_migration_refuses_a_second_run_and_grants_no_truncate(database, store):
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='auth_throttle exists'):
            conn.execute(MIGRATION.read_text())
        conn.execute('ROLLBACK')
    with store.connect() as c:
        c.execute('SET LOCAL ROLE edge_bff_runtime')
        c.execute("INSERT INTO edge_bff.auth_throttle(scope,key_hash,window_start) VALUES ('signin_email',%s,now())", ('a' * 64,))
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute('TRUNCATE edge_bff.auth_throttle')
    with store.connect() as c, pytest.raises(psycopg.errors.CheckViolation):
        c.execute("INSERT INTO edge_bff.auth_throttle(scope,key_hash,window_start) VALUES ('other',%s,now())", ('a' * 64,))


def test_provisioned_login_reaches_the_throttle_with_its_grants(database, monkeypatch):
    helper = Path(__file__).resolve().parents[3] / 'scripts/provision_edge_bff_login.py'
    spec = importlib.util.spec_from_file_location('edge_provision_throttle', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('DATABASE_URL', database)
    monkeypatch.setenv('EDGE_DB_PASSWORD', secrets.token_hex(24))
    p = urlsplit(database)
    restricted = urlunsplit((p.scheme, 'edge_bff_login:' + os.environ['EDGE_DB_PASSWORD'] + '@' + p.netloc.split('@')[-1],
                             p.path, p.query, p.fragment))
    try:
        module.main()
        with psycopg.connect(restricted) as conn:
            for _ in range(2):                                         # the UPSERT the throttle runs, twice
                conn.execute('''INSERT INTO edge_bff.auth_throttle(scope,key_hash,window_start) VALUES ('signin_email',%s,
                    date_trunc('minute', now())) ON CONFLICT (scope,key_hash,window_start)
                    DO UPDATE SET count = edge_bff.auth_throttle.count + 1''', ('b' * 64,))
            assert conn.execute('SELECT count FROM edge_bff.auth_throttle').fetchone()[0] == 2
            conn.execute('DELETE FROM edge_bff.auth_throttle')
            conn.rollback()
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                conn.execute('TRUNCATE edge_bff.auth_throttle')
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('GRANT TRUNCATE ON edge_bff.auth_throttle TO edge_bff_runtime')
        with pytest.raises(RuntimeError, match='Unexpected EDGE grants'):
            module.main()
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('REVOKE TRUNCATE ON edge_bff.auth_throttle FROM edge_bff_runtime')
        module.main()
    finally:
        with psycopg.connect(database, autocommit=True) as conn:
            conn.execute('DROP OWNED BY edge_bff_login')
            conn.execute('DROP ROLE edge_bff_login')
