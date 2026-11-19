"""Independent 3c checker, lens "terminal" (EXEC-MU-ACCOUNTS; CONTRACT.md 8b "3c in detail"): failing tests of the
defects found on the session branch dec1cfef (main bf273f52 + Phase 3c, the fix round and the decisions of 2026-11-19).

1. A terminal-api refusal raised while terminal-api identifies the caller carries no acknowledgement, and edge-bff reads
   it as "terminal-api is older than Phase 3c". terminal-api's middleware adds x-terminal-capabilities-applied only
   when request.state.caller was set (apps/terminal-api/app/main.py `headers`, :256-263); the refusals of identify_now
   come before it is set: the owner header rules (owner_of: invalid_owner_headers), a key that is neither the gateway's
   nor a service's (proxy_key_rejected) and a key off the private host (gateway_host_not_allowed) (main.py :319-326,
   :341-371, :393-405). For every principal without '*', terminal_access.relayed checks the acknowledgement first and
   logs only `terminal_capabilities_not_applied` with the fix "terminal-api is older than Phase 3c: deploy terminal-api
   first", never `terminal_refused` with the upstream status and code. After the switch goes on, a rotated
   TERMINAL_PROXY_KEY or a header rule edge-bff breaks is logged as a deploy-order problem and its code is lost.

2. On the live site user #1 is sent to terminal-api as a capped owner with no quota. principal.live_view drops '*' from
   the capabilities (it keeps grants['*'], so p.can() still holds every non-beta key), and terminal_access.admin(p)
   reads '*' in p.capabilities only. The live admin's x-terminal-capabilities is therefore "admin": false with
   "quota": {}, and terminal-api (main.py limits_of) gives it its terminal.quota defaults (60 files and 30 tickers an
   hour, 150 tickers and 300 MB a day): less than the paid plan's D6 numbers (300, 60, 200, 500), and unlike the beta,
   where the same owner gets the gateway's limits (CONTRACT 8b Quotas: "admin: true uses the gateway subscriber's own
   limits").
"""
import dataclasses
import json
import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app import terminal_access
from app.main import create_app
from app.principal import Principal
from conftest import FakeOrc
from test_beta_live_site import live_of, sign_in_admin
from test_terminal_access import KEY, QUOTA, URL, api, sent_caps, terminal_calls  # noqa: F401 - the fixtures


def capped():
    """The free plan's principal (BBCA, price, 730 days), as account_principal reads it."""
    return Principal(user_id=7, owner_key='u_' + 'a' * 24, username='x', role='user', plan_key='free', status='active',
                     expires_at=None, mfa_ok=True, capabilities=frozenset({'terminal.view'}), version='db-123456789abc',
                     limits={'terminal.tickers': ['BBCA'], 'terminal.history_days': 730},
                     grants={'terminal.dataset': {'ids': ['price']}}, kinds={'terminal.dataset': 'items'})


# terminal-api's refusals made before it knows the caller: no x-terminal-capabilities-applied on any of them
IDENTIFY_REFUSALS = [
    (401, {'error': 'proxy_key_rejected', 'message': 'The x-terminal-proxy-key header holds no key ...'}),
    (403, {'error': 'gateway_host_not_allowed', 'message': 'This address does not accept keyed requests.'}),
    (400, {'error': 'invalid_owner_headers', 'field': 'quota', 'message': 'x'}),
]


@pytest.mark.parametrize('status, body', IDENTIFY_REFUSALS, ids=[b['error'] for _, b in IDENTIFY_REFUSALS])
def test_a_refusal_terminal_api_makes_before_it_knows_the_caller_is_logged_with_its_code(status, body, caplog):
    with caplog.at_level(logging.WARNING, 'edge_bff.terminal_access'):
        refused, data = terminal_access.relayed(capped(), status, body, httpx.Headers(), 'manifest/BBCA')
    assert (refused.status, refused.code, data) == (503, 'TERMINAL_UNAVAILABLE', None)       # the page's answer stands
    logged = [json.loads(r.getMessage()) for r in caplog.records]
    named = [e for e in logged if e.get('code') == body['error'] and e.get('status') == status]
    assert named, ('the upstream refusal is logged without its status and code, as a deploy-order problem '
                   f'("terminal-api is older than Phase 3c"): {logged}')


def test_user_one_on_the_live_site_gets_no_less_terminal_quota_than_a_paid_account(settings, store, api):
    live = dataclasses.replace(live_of(settings), terminal_url=URL, terminal_proxy_key=KEY)
    with TestClient(create_app(live, store, FakeOrc())) as c:
        sign_in_admin(c, store)
        r = c.get('/api/terminal/v1/manifest/BBCA')
        assert r.status_code == 200, r.text
    caps = sent_caps(terminal_calls()[-1])
    # what terminal-api then applies (main.py limits_of): admin -> the gateway's limits; otherwise its defaults
    # overlaid by `quota`, so a quota key left out is terminal-api's default (30 tickers an hour, 60 files an hour)
    weaker = {k: caps['quota'].get(k) for k, v in QUOTA.items() if caps['quota'].get(k, 0) < v}
    assert caps['admin'] or not weaker, (
        f'the live site sends user #1 as {caps}: "admin" false and the paid quotas missing {sorted(weaker)}, so '
        f'terminal-api counts it with its defaults, below the paid plan')

