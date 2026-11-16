"""C1 adversarial security check of EXEC-MU-ACCOUNTS Phase 0 (ERRORS M470): failing tests for the findings (no fix
here). Contract: verification/edge_multiuser/access_tiers/CONTRACT.md section 7 "terminal-api"."""
import pytest

from app.main import API
from test_api import BACKTEST, SCREENER_KEY
from test_private_only import GATEWAY, app_with

PUBLIC = 'terminal-api-dev.up.railway.app'
EDGE = {'x-forwarded-for': '203.0.113.9', 'x-railway-edge': 'railway/asia-southeast1'}


@pytest.mark.parametrize('key', [BACKTEST, {'x-terminal-proxy-key': SCREENER_KEY}])
def test_c1_a_service_key_is_refused_through_the_public_edge(key):
    """M470's class is "a private-service credential usable from the public edge". The host rule (main.py
    private_call) is applied to the gateway key only: while the public domain exists (an origin configured, the state
    until the domain is removed) a worker's service key, the screener-worker's included (cross-sectional files of
    every ticker), is still accepted on terminal-api-dev.up.railway.app from the internet. Workers call only over the
    private network, so the same rule should hold for every service key."""
    client, _ = app_with(('https://terminal.example',))
    r = client.get(f'{API}/state', headers={**key, 'host': PUBLIC, **EDGE})
    assert r.status_code == 403, r.text


@pytest.mark.parametrize('host', ['evil.example@terminal-api.railway.internal',
                                  'terminal-api.railway.internal/evil', 'terminal-api.railway.internal?x',
                                  'terminal-api.railway.internal#x'])
def test_c1_the_gateway_host_rule_reads_only_a_plain_host(host):
    """private_call parses Host with urlsplit('//' + host).hostname, which takes userinfo, a path, a query or a
    fragment out of the Host header and accepts what is left: a Host that is not a host name (RFC 9110 7.2:
    uri-host [":" port]) passes the rule. Compare the Host header to the allowed names exactly (lower case, an
    optional :port of digits), refusing anything else."""
    client, _ = app_with(())
    r = client.get(f'{API}/state', headers={**GATEWAY, 'host': host})
    assert r.status_code == 403 and r.json()['error'] == 'gateway_host_not_allowed', r.text
