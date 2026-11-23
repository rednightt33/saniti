"""Step 9, the registration test window (EXEC.md EXEC-MU-ACCOUNTS; the user 2026-11-20 and 2026-11-23): a rehearsal of
the window on the live site's settings, against one database, before EDGE_PRELAUNCH is flipped on edge-bff-live.

Open (EDGE_PRELAUNCH=false on the live site): registration answers, the code mail is queued, the code signs the person
in, the account signs out and in again. Close (EDGE_PRELAUNCH unset: the live site's default, the pre-launch mode):
registration and a pending registration's code answer REGISTRATION_CLOSED, the window account's session ends at its next
request, and its sign-in is refused SIGN_IN_CLOSED. The admin then disables or keeps each window account on the beta's
admin page (no account is deleted: ERRORS M535).
"""
import dataclasses

from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_a2_stranger import OWNER, at
from test_auth_flows import PASSWORD, db, error_code, last_code, on, register, verify  # noqa: F401 (fixtures)


def client(settings, store):
    application = create_app(settings, store, FakeOrc())
    application.state.auth_flows.pwned_fetch = lambda prefix: ''          # never the real API in a test
    return TestClient(application)


def test_the_window_opens_registration_and_its_close_ends_the_window_accounts(on, store):
    live = dict(site='live', orc_url='', orc_key='')                         # the live site has no AI (CONTRACT 16)
    opened = dataclasses.replace(on, prelaunch_enabled=False, **live)
    closed = dataclasses.replace(on, prelaunch_enabled=None, **live)            # unset: the live site's default
    assert not opened.prelaunch and closed.prelaunch

    with client(opened, store) as c:
        assert c.get('/api/v1/auth/config').json()['registration'] is True
        assert register(c).status_code == 202
        assert db(store, "SELECT count(*) AS n FROM edge_bff.email_outbox WHERE to_email='ana@example.com' "
                         "AND purpose='register'")[0]['n'] == 1                  # the code mail is queued for Resend
        signed = verify(c, last_code(store, 'ana@example.com'))
        assert signed.status_code == 200, signed.text
        assert c.get('/api/v1/auth/session').status_code == 200
        out = c.post('/api/v1/auth/sign-out', headers={**at(OWNER), 'X-CSRF-Token': signed.json()['csrf_token']}, json={})
        assert out.status_code in (200, 204), out.text
        again = c.post('/api/v1/auth/sign-in', headers=at(OWNER), json={'login': 'ana_putri', 'password': PASSWORD})
        assert again.status_code == 200, again.text
        window_session = dict(c.cookies)
        # a second registration left pending when the window closes
        pending = client(opened, store)
        with pending:
            assert register(pending, email='budi@example.com', username='budi_s').status_code == 202
            pending_cookies = dict(pending.cookies)

    with client(closed, store) as c:
        assert c.get('/api/v1/auth/config').json()['registration'] is False
        refused = register(c, email='citra@example.com', username='citra_w')
        assert (refused.status_code, error_code(refused)) == (403, 'REGISTRATION_CLOSED')
        for name, value in pending_cookies.items():
            c.cookies.set(name, value)
        late = verify(c, last_code(store, 'budi@example.com'), email='budi@example.com')
        assert (late.status_code, error_code(late)) == (403, 'REGISTRATION_CLOSED')
        c.cookies.clear()
        for name, value in window_session.items():
            c.cookies.set(name, value)
        assert c.get('/api/v1/auth/session').status_code == 401           # the window account's session ends
        c.cookies.clear()
        shut = c.post('/api/v1/auth/sign-in', headers=at(OWNER), json={'login': 'ana_putri', 'password': PASSWORD})
        assert (shut.status_code, error_code(shut)) == (403, 'SIGN_IN_CLOSED')
    account = db(store, "SELECT status FROM edge_bff.users WHERE username='ana_putri'")
    assert account and account[0]['status'] == 'active'                  # kept until the admin disables it
