"""EXEC-MU-ACCOUNTS Phase 3a, fix round after the checkers C1-C3 (CONTRACT.md 8b; ERRORS M481).

- C3 F1 is tests/test_c3_phase3a_check.py: the queued-backtest refusal names the plan's limit and sets Retry-After.
- C2's two probes are tests/test_c2_probe_phase3a.py: the Screener star needs the Watchlist too, and never makes a list
  beyond the lists cap.
- Here: the other side of each (a principal with the Watchlist still stars; the lists cap above 0 still makes the first
  list; the queue below its cap still accepts), and the start guard of EDGE_ADMIN_OWNERS (C2/C3 R1).
"""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from conftest import FakeOrc
from test_phase3a_gates import SC, WL, override, paid_user
from test_principal import db, on, sign_in, workers  # noqa: F401 - the fixtures


def test_the_star_works_with_the_watchlist_and_makes_the_first_list_within_the_cap(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        override(store, alice['user_id'], 'watchlist.lists', '1')
        h = sign_in(c, 'alice', 'alice-password')
        assert c.put(f'{SC}/watchlist/BBCA', headers=h).status_code == 204
        assert [t['ticker'] for t in c.get(f'{SC}/watchlist').json()['tickers']] == ['BBCA']
        assert len(c.get(f'{WL}/lists').json()['lists']) == 1                  # the first list, within the cap of 1
        assert c.delete(f'{SC}/watchlist/BBCA', headers=h).status_code == 204


def test_a_full_lists_cap_still_lets_the_star_use_the_existing_first_list(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        h = sign_in(c, 'alice', 'alice-password')
        assert c.put(f'{SC}/watchlist/BBCA', headers=h).status_code == 204     # makes the first list
        override(store, alice['user_id'], 'watchlist.lists', '0')                # a cap below what is held
        assert c.put(f'{SC}/watchlist/BBRI', headers=h).status_code == 204     # no new list: the first one is used
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.watchlist_lists')[0]['n'] == 1


def env(monkeypatch, **extra):
    for name, value in {'EDGE_DATABASE_URL': 'postgresql://edge_bff_login@db/x', 'EDGE_ORC_URL': 'http://orc',
                        'MARKET_AI_ORC_API_KEY': 'k', 'EDGE_OWNER': 'edge-private', 'EDGE_LOGIN': 'owner',
                        'EDGE_PASSWORD_VERIFIER': 'scrypt$' + '0' * 32 + '$' + '0' * 64, 'EDGE_SESSION_SECRET': 's' * 40,
                        'EDGE_PUBLIC_ORIGIN': 'http://localhost', 'EDGE_ENVIRONMENT': 'local', **extra}.items():
        monkeypatch.setenv(name, value)


def test_the_start_refuses_admin_owners_without_the_configured_owner_while_the_switch_is_off(monkeypatch):
    env(monkeypatch)
    assert Settings.from_env().admin_owners == ('edge-private',)              # unset: the configured owner
    monkeypatch.setenv('EDGE_ADMIN_OWNERS', 'edge-private,another-a')
    assert Settings.from_env().admin_owners == ('edge-private', 'another-a')
    monkeypatch.setenv('EDGE_ADMIN_OWNERS', 'another-a')
    with pytest.raises(ValueError, match='EDGE_ADMIN_OWNERS must list EDGE_OWNER'):
        Settings.from_env()
    # with the switch on the list no longer grants anything to accounts (plans do), so it may leave the owner out
    env(monkeypatch, EDGE_MULTIUSER='true', EDGE_CODE_SECRET='c' * 40, EDGE_MFA_KEY='m' * 40)
    assert Settings.from_env().admin_owners == ('another-a',)
