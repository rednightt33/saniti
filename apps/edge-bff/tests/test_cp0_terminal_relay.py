"""Checker C-P0 (EXEC-MU-ACCOUNTS, Phase 0 runtime and downstream identity): the Terminal gateway relays terminal-api's
own status codes and flat error bodies to the page unchanged (main.py forward_terminal, the last line:
`JSONResponse(status_code=answer.status_code, content=data)`).

CONTRACT.md section 3: every edge-bff refusal has the shape {"error": {"code", "message", "details"}}; a 401 means
UNAUTHENTICATED and the page goes to sign-in; a 429 is LIMIT_REACHED with Retry-After. A terminal-api 401 is about
terminal-api's own account (the gateway subscriber inactive or past its expires_at, 2027-10-25 for subscriber 2,
DATABASE_CHANGELOG.md 2026-10-25; or a rotated TERMINAL_PROXY_KEY that edge-bff has not been redeployed with, M308),
never about the EDGE session, which is valid here. Relayed as a 401, the shared module drops the session
(shared/edge-session.ts send(): `if (res.status === 401) invalidate()`) and the Terminal page says "Sign in to EDGE
first" (terminal/src/data/live.ts api()); signing in again cannot help.

Phase 3c makes both answers routine: per-owner terminal-api quotas at D6 numbers (429 for paid and free users) and
per-owner subscriber rows that follow a disable (401 session_ended for that owner).
"""
import dataclasses

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import create_app
from conftest import FakeOrc

ORIGIN = {'Origin': 'http://testserver'}
KEY = 'g' * 40


def login(c):
    r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
    assert r.status_code == 200, r.text
    return {**ORIGIN, 'X-CSRF-Token': r.json()['csrf_token']}


class Upstream:
    """Stands in for httpx.AsyncClient and answers like terminal-api does (app/main.py error(): a flat body)."""
    answer = None

    def __init__(self, timeout):
        pass

    async def request(self, method, url, params=None, content=None, headers=None):
        return Upstream.answer


@pytest.fixture
def gateway(settings, store, monkeypatch):
    monkeypatch.setattr(main.httpx, 'AsyncClient', Upstream)
    configured = dataclasses.replace(settings, terminal_url='http://terminal-api.railway.internal:8080',
                                     terminal_proxy_key=KEY)
    with TestClient(create_app(configured, store, FakeOrc())) as c:
        yield c


def test_a_terminal_api_401_is_not_relayed_as_the_edge_sign_out(gateway):
    """terminal-api's 401 session_ended (main.py refuse(), caller kind 'gateway') while the EDGE session is valid."""
    c = gateway
    login(c)
    Upstream.answer = httpx.Response(401, json={'error': 'session_ended',
                                                'message': 'The terminal account of this gateway is not active.'})
    r = c.get('/api/terminal/v1/manifest/BBCA')
    assert c.get('/api/v1/auth/session').status_code == 200            # the EDGE session is fine
    assert r.status_code != 401, ('a terminal-api 401 reached the page as a 401: the page drops a valid EDGE session '
                                  'and asks the user to sign in again')
    body = r.json()
    assert isinstance(body.get('error'), dict) and body['error'].get('code'), body   # the contract shape


def test_a_terminal_api_429_reaches_the_page_in_the_contract_shape_with_retry_after(gateway):
    """terminal-api's 429 quota_exceeded (main.py take()); CONTRACT.md section 3: 429 LIMIT_REACHED, Retry-After on
    every 429."""
    c = gateway
    h = login(c)
    Upstream.answer = httpx.Response(429, json={'error': 'quota_exceeded', 'message': 'Quota files_per_hour reached '
                                                '(300 per hour). It frees up as older requests leave the rolling hour; '
                                                'ask the administrator if you need a higher limit.'})
    r = c.post('/api/terminal/v1/bundle', headers=h, json={'ticker': 'BBCA', 'datasets': ['price']})
    assert r.status_code == 429
    assert r.headers.get('retry-after'), 'a 429 without Retry-After (CONTRACT.md section 3: set on every 429)'
    body = r.json()
    assert isinstance(body.get('error'), dict) and body['error'].get('code') == 'LIMIT_REACHED', body
