"""EXEC-MU-ACCOUNTS re-check round 2, checker C2-LIFE (data lifecycle, privacy and logs): failing tests of the verified
findings. Each test names the rule it holds; the fix round makes them pass.

- L1: the hourly purge deletes a never-verified registration (CONTRACT.md section 4: "A pending user is deleted 24 h
  after creation if never verified"), but every email_outbox row that names its address stays for ever: the outbox has
  no retention, and edge_bff_runtime holds no DELETE on it (20261116_003:225), so the purge cannot remove them either.
- L2: an exception no route expected is answered 503 SERVICE_UNAVAILABLE by main.py's handler, whose comment says no
  exception body or traceback is written because database errors may contain secrets; Starlette re-raises it after the
  handler and uvicorn logs it with its full text, PostgreSQL's DETAIL included ("Failing row contains (...)": the
  person's email, names and phone).
"""
import asyncio
import dataclasses
import logging
import socket
import threading
import time
import uuid
from urllib.parse import urlsplit, urlunsplit

import httpx
import psycopg
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.mailer import EmailSender
from app.main import create_app
from app.store import Store
from conftest import FakeOrc
from test_auth_flows import SECRET, db, outbox, register

STRANGER = 'someone.else@example.com'


@pytest.fixture
def on(settings):
    return dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40,
                               resend_webhook_secret=SECRET)


@pytest.fixture
def app(on, store):
    application = create_app(on, store, FakeOrc())
    application.state.auth_flows.pwned_fetch = lambda prefix: ''          # never the real API in a test
    with TestClient(application) as c:
        yield c


@pytest.fixture
def runtime_store(database):
    """The store as production runs it: a login that holds only edge_bff_runtime's grants (edge_bff_login on dev,
    scripts/provision_edge_bff_login.py), so a statement the grants refuse fails here as it would there."""
    name = 'r2_life_' + uuid.uuid4().hex[:8]
    with psycopg.connect(database, autocommit=True) as c:
        c.execute(f'CREATE ROLE "{name}" LOGIN INHERIT IN ROLE edge_bff_runtime')
    p = urlsplit(database)
    s = Store(urlunsplit((p.scheme, f'{name}@{p.hostname}:{p.port}', p.path, p.query, p.fragment)))
    try:
        yield s
    finally:
        s.close()
        with psycopg.connect(database, autocommit=True) as c:
            c.execute(f'DROP ROLE "{name}"')


def test_l1_the_purge_of_a_never_verified_registration_leaves_no_row_naming_its_address(app, store, on, runtime_store):
    """CONTRACT.md section 4 deletes a pending registration after 24 h, and anyone may type any address into the
    registration form. The registration's code email was sent (Resend, payload nulled); a day later the hourly cleanup
    runs as the production login. Afterwards nothing in edge_bff may still say that this address was registered: today
    the users row goes (with its identity and code, ON DELETE CASCADE) but the outbox row keeps to_email, purpose
    'register', the times and the provider id for ever, and edge_bff_runtime cannot delete it."""
    assert register(app, STRANGER, 'some_one').status_code == 202
    sender = EmailSender(dataclasses.replace(on, email_mode='resend', resend_api_key='re_test_key',
                                             email_from='EDGE <no-reply@mail.example.com>'), store,
                         transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'id': 'em_1'})))

    async def send():
        assert await sender.step() is True
        await sender.aclose()
    asyncio.run(send())
    assert [(r['status'], r['payload']) for r in outbox(store, STRANGER)] == [('sent', None)]
    db(store, "UPDATE edge_bff.users SET created_at = now() - interval '25 hours' WHERE email=%s", STRANGER)
    db(store, "UPDATE edge_bff.email_outbox SET created_at = created_at - interval '25 hours', "
              "sent_at = sent_at - interval '25 hours' WHERE to_email=%s", STRANGER)
    runtime_store.cleanup_sessions()                       # the worker loop's hourly cleanup, as edge_bff_runtime
    assert db(store, 'SELECT user_id FROM edge_bff.users WHERE email=%s', STRANGER) == [], 'the purge did not run'
    left = [(r['purpose'], r['status']) for r in outbox(store, STRANGER)]
    assert left == [], (f'the registration was purged but its outbox rows still name {STRANGER}: {left}; the outbox '
                        'needs a retention (and edge_bff_runtime a DELETE grant for it)')


# ---- L2 -------------------------------------------------------------------------------------------------------------

class Captured(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))


def test_l2_an_unexpected_database_error_never_writes_the_persons_data_to_the_server_log(on, store):
    """main.py:331-334 answers any unexpected exception 503 and says no exception body or traceback is written
    (database errors may contain secrets; worker.py:56 and backtest.py failure_of keep that rule for the loops). Under
    uvicorn, as on Railway (Dockerfile CMD), the request path breaks it: Starlette's ServerErrorMiddleware re-raises
    after the handler and uvicorn.error logs 'Exception in ASGI application' with the exception's text, whose DETAIL
    lists the failing row. The unexpected error here is a database constraint the running edge-bff does not know (the
    beta/live case: a migration applied for the beta while the live version still writes the old shape); the person's
    registration then fails with 503 and their email, names and phone go to the log."""
    with store.connect() as c:
        c.execute("ALTER TABLE edge_bff.users ADD CONSTRAINT r2_life_probe CHECK (phone_e164 NOT LIKE '+628%')")
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    settings = dataclasses.replace(on, origin=f'http://127.0.0.1:{port}')
    application = create_app(settings, store, FakeOrc())
    application.state.auth_flows.pwned_fetch = lambda prefix: ''
    captured = Captured()
    error_log = logging.getLogger('uvicorn.error')
    error_log.addHandler(captured)
    server = uvicorn.Server(uvicorn.Config(application, log_level='error', log_config=None, access_log=False))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True); thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.02)
        assert server.started
        r = httpx.post(f'http://127.0.0.1:{port}/api/v1/auth/register', headers={'Origin': settings.origin}, json={
            'username': 'leak_probe', 'first_name': 'Sinta', 'last_name': 'Probe', 'email': 'sinta.probe@example.com',
            'phone': '0812 9999 0000', 'password': 'a long enough password', 'password_repeat': 'a long enough password'},
            timeout=20)
        assert r.status_code == 503 and r.json()['error']['code'] == 'SERVICE_UNAVAILABLE', r.text
        for _ in range(50):                                    # uvicorn logs right after the answer
            if captured.lines:
                break
            time.sleep(0.02)
    finally:
        server.should_exit = True; thread.join(timeout=10); sock.close()
        error_log.removeHandler(captured)
        with store.connect() as c:
            c.execute('ALTER TABLE edge_bff.users DROP CONSTRAINT r2_life_probe')
        store.close()                                      # the server's lifespan closed the pool; this read reopened it
    text = '\n'.join(captured.lines)
    leaked = [d for d in ('sinta.probe@example.com', '+6281299990000', 'Sinta') if d in text]
    assert not leaked, ('the server log holds the person\'s data from an unexpected database error: '
                        f'{leaked}; first line: {text.splitlines()[0] if text else ""!r}')
