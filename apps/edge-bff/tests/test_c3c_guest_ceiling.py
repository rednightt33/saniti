"""EXEC-MU-ACCOUNTS 3c check fixes: one ceiling for every visitor of the guest plan together (the user, 2026-11-19: "2A
tapi harus bisa di set dibackend variable ya batasannya"). EDGE_GUEST_CALLS_PER_HOUR sets it (Settings.
guest_calls_per_hour); unset, nothing is counted and no ceiling holds; set, every visitor's Terminal calls count
together (edge_bff.auth_throttle scope 'guest_total', migration 20261119_071) and a call beyond it answers 429
LIMIT_REACHED with the visitor's words and Retry-After, before terminal-api is asked. A signed-in account never counts
here.
"""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from conftest import FakeOrc
from test_beta_live_site import env_of
from test_edge import ORIGIN
from test_guest import VISITOR, OTHER_VISITOR, guests  # noqa: F401 - the fixtures
from test_principal import db, on, workers  # noqa: F401 - the fixtures
from test_terminal_access import FakeApi, api  # noqa: F401 - the fixtures


def guest_rows(store):
    return db(store, "SELECT count(*) AS n FROM edge_bff.auth_throttle WHERE scope = 'guest_total'")[0]['n']


def test_without_the_setting_no_visitor_call_is_counted(guests, store):
    assert guests.guest_calls_per_hour == 0
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        for _ in range(5):
            assert c.get('/api/terminal/v1/manifest/BBCA', headers=VISITOR).status_code == 200
    assert guest_rows(store) == 0


def test_every_visitor_together_meets_the_ceiling_the_setting_gives(guests, store):
    capped = dataclasses.replace(guests, guest_calls_per_hour=3)
    with TestClient(create_app(capped, store, FakeOrc())) as c:
        # two visitors (two client addresses) share the one ceiling
        for headers in (VISITOR, OTHER_VISITOR, VISITOR):
            assert c.get('/api/terminal/v1/manifest/BBCA', headers=headers).status_code == 200
        before = len(FakeApi.calls)
        r = c.get('/api/terminal/v1/manifest/BBCA', headers=OTHER_VISITOR)
        assert r.status_code == 429 and len(FakeApi.calls) == before          # refused before terminal-api
        error = r.json()['error']
        assert error['code'] == 'LIMIT_REACHED' and error['details']['limit'] == 'guest_total'
        assert int(r.headers['retry-after']) >= 1 and error['details']['retry_after_s'] >= 1
        # a visitor's words: no plan to upgrade, and the way on is to wait or to sign in
        assert 'visitors without an account' in error['message'] and 'plan' not in error['message']
        assert 'sign in' in error['message'].lower()


def test_the_setting_is_read_strictly(monkeypatch):
    env_of(monkeypatch, EDGE_GUEST_CALLS_PER_HOUR='5000')
    assert Settings.from_env().guest_calls_per_hour == 5000
    env_of(monkeypatch, EDGE_GUEST_CALLS_PER_HOUR='')
    assert Settings.from_env().guest_calls_per_hour == 0
    for wrong in ('-1', 'lots', '5e3', '1.5'):
        env_of(monkeypatch, EDGE_GUEST_CALLS_PER_HOUR=wrong)
        with pytest.raises(ValueError, match='EDGE_GUEST_CALLS_PER_HOUR'):
            Settings.from_env()
    env_of(monkeypatch, EDGE_GUEST_CALLS_PER_HOUR=str(10 ** 9 + 1))
    with pytest.raises(ValueError, match='EDGE_GUEST_CALLS_PER_HOUR'):
        Settings.from_env()
