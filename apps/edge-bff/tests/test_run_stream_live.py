"""EXEC-MU-ACCOUNTS fix round (records track, re-check R1-28; ERRORS M481 "C3 gaps"): the run stream re-checks the
principal on every loop.

CONTRACT section 4 "Sessions" and 8b D5: GET /api/v1/runs/{id}/events re-resolves the session and requires its
monitor.view on each loop (main.py still_signed_in). Starlette's TestClient runs a streamed answer to its end before
the test can read it (240 s here), so this runs on a real local server (tests/test_auth_pages_live.py serve) with
httpx streaming. Shown by mutation: with still_signed_in no longer asking found.can(MONITOR_VIEW), the stream keeps
sending after the plan loses monitor.view and this test fails.
"""
import dataclasses
import socket
import time

import httpx

from test_auth_pages_live import serve
from test_phase3a_monitor_pages import GLM, chat_user, override


def test_the_run_stream_ends_once_the_plan_loses_monitor_view(settings, store):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    on = dataclasses.replace(settings, origin=origin, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40,
                             poll_seconds=0.05)
    server, thread = serve(on, store, port, sock)
    try:
        user = chat_user(store, 'sean', [GLM])
        with httpx.Client(base_url=origin, timeout=5) as c:
            r = c.post('/api/v1/auth/sign-in', headers={'Origin': origin},
                       json={'login': 'sean', 'password': 'sean-password'})
            assert r.status_code == 200, r.text
            h = {'Origin': origin, 'X-CSRF-Token': r.json()['csrf_token']}
            r = c.post('/api/v1/runs', headers=h, json={'message': 'x', 'submission_key': 'one', 'model': GLM})
            assert r.status_code == 202, r.text
            rid = r.json()['request_id']
            with c.stream('GET', f'/api/v1/runs/{rid}/events') as stream:
                assert stream.status_code == 200
                lines = stream.iter_lines()
                assert next(lines).startswith('id: ')               # the first snapshot: the stream is live
                override(store, user['user_id'], 'monitor.view', False)
                lowered_at = time.monotonic()
                for _ in lines:
                    assert time.monotonic() - lowered_at < 5, 'the stream kept running after the plan lost monitor.view'
            assert time.monotonic() - lowered_at < 5
            r = c.get(f'/api/v1/runs/{rid}/events')
            assert r.status_code == 403 and r.json()['error']['code'] == 'CAPABILITY_REQUIRED', r.text
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
