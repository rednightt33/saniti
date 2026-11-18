"""C-P3A (ultracode re-check of Phases 0-3b, user 2026-11-18 "Cek juga fase sebelumnya"; lens: Phase 3a route gates
and caps, CONTRACT.md 8b, decisions D1-D8). Failing tests of the verified findings, written against main 93c9f645;
the fix round makes them pass.

- Retry-After on every 429 (CONTRACT 3): the page-file grant and the Terminal gateway relay, the two paths 3c's
  per-owner Terminal quotas (decision D6) reach the page through;
- the 3a route walks are scoped by module and path (ERRORS M481 "C3 gaps", OPEN): a new route that serves a tab's content
  with the principal only is reported by none;
- the session's access.limits names the plan's raw value, not the min(plan, HARD) the routes apply.
"""
from fastapi import Depends
from fastapi.testclient import TestClient

from app.main import create_app
from conftest import FakeOrc
from test_principal import on, workers  # noqa: F401 - the fixtures (switch on, the fake workers)
from test_radar import FakeHttp, gw  # noqa: F401 - the fixture
from test_radar import login as radar_login
from test_terminal import gateway  # noqa: F401 - the fixture
from test_terminal import login as terminal_login


# ---- CONTRACT 3 "Retry-After is set on every 429" ---------------------------------------------------------------------

def test_a_page_file_quota_refusal_sets_retry_after(gw):
    """pages.py page_file: terminal-api's 429 on a page-file grant answers <FAMILY>_QUOTA 429 without Retry-After."""
    radar_login(gw)
    FakeHttp.grant_status = 429
    r = gw.get('/api/v1/radar/file/radar-days')
    assert r.status_code == 429
    assert 'retry-after' in r.headers, dict(r.headers)


def test_a_terminal_quota_refusal_relayed_by_the_gateway_sets_retry_after(gateway):
    """main.py forward_terminal: a JSON answer is rebuilt as JSONResponse(status, content) only, so terminal-api's 429
    (quota_exceeded, itself sent without the header) reaches the page with no Retry-After; any header terminal-api adds
    is dropped too."""
    h = terminal_login(gateway)
    r = gateway.post('/api/terminal/v1/files', headers=h, json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]})
    assert r.status_code == 429
    assert 'retry-after' in r.headers, dict(r.headers)


# ---- ERRORS M481 "C3 gaps" (OPEN): the 3a route walks are scoped by module and path ------------------------------------

def test_a_new_gated_route_outside_the_scoped_walks_is_reported(settings, store):
    """A route that serves a tab's content with the principal only (e.g. 3e's GET /api/v1/examples/<tab>/..., gated by
    <tab>.example in CONTRACT 8b, or a 3c relay placed outside /api/terminal/v1/) is reported by no walk:
    test_phase3a_gates walks six modules, test_phase3a_monitor_pages one path pattern, test_route_table the session only."""
    from test_phase3a_gates import gate_problems
    from test_phase3a_monitor_pages import IN_SCOPE, ROUTE_CAPS as MONITOR_CAPS
    from test_route_table import configured, problems
    app = create_app(configured(settings), store, FakeOrc())

    async def example(tab: str, name: str, p=Depends(app.state.auth.principal)):
        return {}
    app.get('/api/v1/examples/{tab}/{name}')(example)
    found = gate_problems(app) + problems(app) + [
        path for path in (r.path for r in app.routes)
        if IN_SCOPE.fullmatch(path) and not any(path == p for _, p in MONITOR_CAPS)]
    assert any('/api/v1/examples/' in f for f in found), found


# ---- CONTRACT 8b "limits() and the answers report the principal's own numbers" -----------------------------------------

def test_the_session_access_limits_are_the_numbers_the_routes_apply(on, store):
    """principal.py Principal.access: `limits` is the plan's raw value; the routes apply min(plan, HARD)
    (Principal.capped). capability_value_check accepts a value above HARD, so the session answer (the page's
    limit(key), shared/edge-session.ts) names a number the server never applies."""
    from test_phase3a_gates import override, paid_user
    from test_principal import sign_in
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        override(store, alice['user_id'], 'terminal.layouts_max', '100000')
        sign_in(c, 'alice', 'alice-password')
        applied = c.get('/api/v1/terminal/layouts').json()['limit']
        assert applied == 50
        assert c.get('/api/v1/auth/session').json()['access']['limits']['terminal.layouts_max'] == applied
