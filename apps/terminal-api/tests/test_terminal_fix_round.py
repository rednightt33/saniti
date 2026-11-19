"""EXEC-MU-ACCOUNTS re-check of Phases 0-3b, fix round, track "terminal" (verification/edge_multiuser/fix_round/
terminal.md): terminal-api's side of the relay contract.

- R1-1, R1-26: every 429 names its quota, its limit, its window and when the refused request fits (`retry_after_s` and
  the Retry-After header), so edge-bff answers 429 LIMIT_REACHED with details.limit and retry_after_s without reading
  the message.
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
