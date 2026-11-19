"""EXEC-MU-ACCOUNTS 3c check, lens guest (checker c3c-guest): failing tests of the verified findings about the guest
principal's client address and the pre-launch mode (verification/edge_multiuser/fix_round/guest.md).

- The visitor key is made from the right-most entry of the FIRST X-Forwarded-For line only (principal.client_of reads
  request.headers.get). When a request carries two lines, the client's own and the one an edge adds after it, the
  client chooses its key, and so its per-visitor quotas: guest.md and ERRORS M487 say the worst case without the
  client-address probe is "every visitor shares one quota: stricter, never wider", which this case contradicts.
- The pre-launch rule (only the admin and accounts marked test_account sign in) is applied at sign-in only
  (main.py sign_in); removing the mark (scripts/edge_test_account.py --off) leaves the account's sessions working.
"""
import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import terminal_access
from app.main import create_app
from conftest import FakeOrc
from test_edge import ORIGIN
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401 - the fixtures
from test_terminal_access import FakeApi, URL, KEY, api, terminal_calls  # noqa: F401

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def guests(on, api):
    """The switch on with guests, as the live site has them."""
    return dataclasses.replace(on, terminal_url=URL, terminal_proxy_key=KEY, guests_enabled=True)


def test_a_client_written_forwarded_for_line_never_chooses_the_visitor_key(guests, store):
    """One client (the edge-added line names 203.0.113.7 each time) sends three different lines of its own first: it
    must stay one visitor, never three (each with fresh quotas at terminal-api)."""
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        keys = set()
        for forged in ('198.51.100.1', '198.51.100.2', '198.51.100.3'):
            r = c.get('/api/terminal/v1/manifest/BBCA',
                      headers=[('x-forwarded-for', forged), ('x-forwarded-for', '203.0.113.7')])
            assert r.status_code == 200, r.text
            keys.add(terminal_calls()[-1]['headers'][terminal_access.CLIENT_HEADER])
        assert len(keys) == 1, f'one client got {len(keys)} visitor keys, one per line it wrote itself'


def test_an_account_whose_test_mark_is_removed_no_longer_uses_the_prelaunch_site(guests, store, database):
    pre = dataclasses.replace(guests, prelaunch_enabled=True)
    with TestClient(create_app(pre, store, FakeOrc())) as c:
        tess = make_user(store, 'tessa', 'tessa-password')
        with psycopg.connect(database) as conn:
            conn.execute('''INSERT INTO edge_bff.admin_audit(action, target_user_id, after, reason)
                VALUES ('account.test_mark', %s, '{"test_account": true}', 'operator: test')''', (tess['user_id'],))
            conn.execute('UPDATE edge_bff.users SET test_account = true WHERE user_id = %s', (tess['user_id'],))
        email = db(store, 'SELECT email FROM edge_bff.users WHERE user_id = %s', tess['user_id'])[0]['email']
        h = sign_in(c, 'tessa', 'tessa-password')
        assert c.get('/api/v1/auth/session', headers=h).status_code == 200
        r = subprocess.run([sys.executable, str(ROOT / 'scripts/edge_test_account.py'), '--email', email, '--plan', 'free',
                            '--reason', 'the test is over', '--off'], env={**os.environ, 'DATABASE_URL': database},
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0 and '"unmarked"' in r.stdout, r.stdout + r.stderr
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'tessa', 'password': 'tessa-password'})
        assert r.status_code == 403 and r.json()['error']['code'] == 'SIGN_IN_CLOSED'
        # the session made while the account was marked must end with the mark
        r = c.get('/api/v1/auth/session', headers=h)
        assert r.status_code == 401, 'the unmarked account still uses the live site in pre-launch mode'
