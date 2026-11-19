"""EXEC-MU-ACCOUNTS Phase 3a (CONTRACT.md 8b, decisions D1 and D5; builder B2): the Monitor (AI) routes, the Terminal
proxy and the Overview/Radar/Watchlist page files need their capability.

- a route walk: every Monitor route, every Terminal proxy route and every page-file route depends on
  auth.need(<capability>, write) as ROUTE_CAPS names it; a new route without an entry fails with the entry to add;
- a principal without the capability gets 403 CAPABILITY_REQUIRED on each, and neither Orc nor terminal-api is asked;
- D1: a paid account is refused the Monitor; the run's model (the request's, else Orc's server default) must be held
  (monitor.model:<id>), and saniti/claude-manual needs admin.manual; /api/v1/models lists only the held models;
- the worker re-checks a queued run's owner at dispatch: FAILED CAPABILITY_REQUIRED, no Orc call;
- page files: refused even after another account filled the shared caches; `private, no-cache` with the ETag; a
  `?sha=` request with a matching If-None-Match answers 304 only after the check;
- with the switch off nothing changes for the configured owner ('*').

Until B1's migration 20261117_004 lands, the paid plan of the seed still holds monitor.view, monitor.chat and
monitor.model; `paid_without_monitor` takes them away with per-user overrides (the shape decision D1 gives the paid plan),
so the tests hold both before and after that migration. The plans are found by data, never by key.
"""
import asyncio
import dataclasses
import json
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import main, radar
from app.main import create_app
from conftest import FakeOrc
from test_edge import ORIGIN, login
from test_principal import db, make_user, sign_in
from test_radar import BODY, KEY, SHA, FakeHttp
from test_route_table import GUEST_OPEN, calls, configured

CONV = 'conv_' + 'c' * 32
RUN = 'edge_' + 'a' * 32
EXPORT = 'exp_' + 'e' * 24
OUTPUT = 'out_' + 'o' * 24
DEEPSEEK, GLM, MANUAL = 'deepseek/deepseek-v4.1-flash', 'z-ai/glm-5.3-flash', 'saniti/claude-manual'

# (method, path) -> (capability, write). A new Monitor, Terminal proxy or page-file route needs its line here
ROUTE_CAPS = {
    ('POST', '/api/v1/runs'): ('monitor.chat', True),
    ('GET', '/api/v1/runs'): ('monitor.view', False),
    ('GET', '/api/v1/runs/{request_id}'): ('monitor.view', False),
    ('GET', '/api/v1/runs/{request_id}/progress'): ('monitor.view', False),
    ('GET', '/api/v1/runs/{request_id}/events'): ('monitor.view', False),
    ('POST', '/api/v1/runs/{request_id}/stop'): ('monitor.chat', True),
    ('POST', '/api/v1/runs/{request_id}/branch'): ('monitor.chat', True),
    ('PATCH', '/api/v1/runs/{request_id}/preferences'): ('monitor.chat', True),
    ('GET', '/api/v1/models'): ('monitor.view', False),
    ('GET', '/api/v1/conversations'): ('monitor.view', False),
    ('GET', '/api/v1/conversations/{conversation_id}/messages'): ('monitor.view', False),
    ('DELETE', '/api/v1/conversations/{conversation_id}'): ('monitor.chat', True),
    ('PATCH', '/api/v1/conversations/{conversation_id}/preferences'): ('monitor.chat', True),
    ('POST', '/api/v1/conversations/{conversation_id}/outputs/{output_id}/export'): ('monitor.chat', True),
    ('GET', '/api/v1/exports/{export_id}'): ('monitor.view', False),
    ('GET', '/api/terminal/v1/{path:path}'): ('terminal.view', False),
    ('POST', '/api/terminal/v1/{path:path}'): ('terminal.view', True),
    ('GET', '/api/v1/overview/index'): ('overview.view', False),
    ('GET', '/api/v1/overview/file/{name}'): ('overview.view', False),
    ('GET', '/api/v1/radar/index'): ('radar.view', False),
    ('GET', '/api/v1/radar/file/{name}'): ('radar.view', False),
    ('GET', '/api/v1/watchlist/index'): ('watchlist.view', False),
    ('GET', '/api/v1/watchlist/file/{name}'): ('watchlist.view', False),
}
# the routes of this stage: the Monitor's, the Terminal proxy's and the page files'
IN_SCOPE = re.compile(r'/api/v1/(?:runs|conversations|exports|models)(?:/.*)?|/api/terminal/v1/.*'
                      r'|/api/v1/(?:overview|radar|watchlist)/(?:index|file/\{name\})')
# what each refused request sends (a valid shape, so only the capability can refuse it)
BODIES = {
    ('POST', '/api/v1/runs'): {'message': 'Explain GOTO', 'submission_key': 'one'},
    ('POST', '/api/v1/runs/{request_id}/branch'): {'kind': 'BRANCH', 'title': 'More'},
    ('PATCH', '/api/v1/runs/{request_id}/preferences'): {'pinned': True},
    ('PATCH', '/api/v1/conversations/{conversation_id}/preferences'): {'title': 'x'},
    ('POST', '/api/v1/conversations/{conversation_id}/outputs/{output_id}/export'): {'columns': [], 'titles': []},
    ('POST', '/api/terminal/v1/{path:path}'): {'tickers': ['BBCA']},
}
PARAMS = {'request_id': RUN, 'conversation_id': CONV, 'output_id': OUTPUT, 'export_id': EXPORT, 'name': 'radar-days',
          'path:path': 'manifest/BBCA'}


def concrete(path, method):
    out = path
    for key, value in PARAMS.items():
        out = out.replace('{' + key + '}', value)
    if method == 'POST' and out.startswith('/api/terminal/v1/'):
        out = '/api/terminal/v1/bundle'
    return out.replace('/overview/file/radar-days', '/overview/file/overview-meta') \
              .replace('/watchlist/file/radar-days', '/watchlist/file/watchlist-stocks')


class CountingOrc(FakeOrc):
    """FakeOrc that records every call that would reach Orc."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.asked = []

    def _note(self, name):
        self.asked.append(name)

    def run(self, *a):
        self._note('run'); return super().run(*a)

    def request(self, *a):
        self._note('request'); return super().request(*a)

    def messages(self, *a, **kw):
        self._note('messages'); return super().messages(*a, **kw)

    def models(self, *a):
        self._note('models'); return super().models(*a)

    def stop(self, *a):
        self._note('stop'); return super().stop(*a)

    def branch(self, *a):
        self._note('branch'); return super().branch(*a)

    def progress(self, *a):
        self._note('progress'); return super().progress(*a)

    def execution_ready(self, *a):
        self._note('execution_ready'); return super().execution_ready(*a)

    def export_table(self, *a):
        self._note('export_table'); return {'export_id': EXPORT}


@pytest.fixture
def on(settings, store, monkeypatch):
    monkeypatch.setattr(radar.httpx, 'AsyncClient', FakeHttp)           # terminal-api, the bucket and Orc's export
    FakeHttp.calls = []
    FakeHttp.files = {'radar-days': {'sha256': SHA, 'bytes': len(BODY), 'rows': 1, 'as_of': '2026-11-09'}}
    FakeHttp.stored = {'radar-days': BODY}
    FakeHttp.granted_sha, FakeHttp.grant_status = None, 200
    return dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40,
                               terminal_url='http://terminal-api.railway.internal:8080', terminal_proxy_key=KEY)


def plan_holding(store, capability):
    return db(store, '''SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = %s
        ORDER BY plan_key LIMIT 1''', capability)[0]['plan_key']


def override(store, user_id, capability, value):
    db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
        VALUES (%s, %s, %s::jsonb, 'phase 3a test') ON CONFLICT (user_id, capability_key) DO UPDATE SET value = EXCLUDED.value''',
       user_id, capability, json.dumps(value))


def subscribe(store, user_id, plan):
    db(store, '''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, starts_at, provider)
        VALUES (%s, %s, 'active', now() - interval '1 day', 'test')''', user_id, plan)


def paid(store, username):
    """An account on the plan that runs backtests (the paid plan, found by data)."""
    user = make_user(store, username, f'{username}-password')
    subscribe(store, user['user_id'], plan_holding(store, 'backtest.run'))
    return user


def paid_without_monitor(store, username):
    """Decision D1: the paid plan without monitor.view, monitor.chat and monitor.model (B1's migration 20261117_004
    does it in the seed; until then the overrides do it per account)."""
    user = paid(store, username)
    override(store, user['user_id'], 'monitor.view', False)
    override(store, user['user_id'], 'monitor.chat', False)
    override(store, user['user_id'], 'monitor.model', {'ids': []})
    return user


def chat_user(store, username, models):
    """A paid account holding the Monitor with exactly these models."""
    user = paid(store, username)
    override(store, user['user_id'], 'monitor.view', True)
    override(store, user['user_id'], 'monitor.chat', True)
    override(store, user['user_id'], 'monitor.model', {'ids': list(models)})
    return user


def jobs(store):
    return db(store, 'SELECT request_id, state, error_code FROM edge_bff.jobs ORDER BY created_at')


# ---- the route walk -------------------------------------------------------------------------------------------------

def in_scope(app):
    for route in app.routes:
        if isinstance(route, APIRoute) and IN_SCOPE.fullmatch(route.path):
            for method in sorted(route.methods):
                yield method, route


def test_every_monitor_terminal_and_page_route_needs_its_capability(on, store):
    app = create_app(configured(on), store, FakeOrc())
    auth = app.state.auth
    seen, found = set(), []
    for method, route in in_scope(app):
        key = (method, route.path)
        seen.add(key)
        if key not in ROUTE_CAPS:
            found.append(f'{method} {route.path}: no entry in ROUTE_CAPS; add ({method!r}, {route.path!r}): '
                         f"('<capability>', {method not in ('GET', 'HEAD')}) and give the route "
                         "Depends(auth.need('<capability>', write=...))")
            continue
        capability, write = ROUTE_CAPS[key]
        # track guest (decision 1 of 2026-11-19, "1a"): a route a visitor without an account reaches is named in
        # test_route_table.GUEST_OPEN and needs its capability through the visitor dependency (guests=True)
        guests = key in GUEST_OPEN
        if auth.need(capability, write, guests=guests) not in set(calls(route.dependant)):
            found.append(f'{method} {route.path}: does not depend on auth.need({capability!r}, write={write}'
                         f'{", guests=True" if guests else ""})')
    found += [f'{m} {p}: in ROUTE_CAPS but no such route (remove the entry)' for m, p in set(ROUTE_CAPS) - seen]
    assert found == []
    assert len(seen) == len(ROUTE_CAPS) >= 20


def test_the_walk_fails_on_a_new_route_without_its_need(on, store):
    from fastapi import Depends
    app = create_app(configured(on), store, FakeOrc())

    @app.get('/api/v1/runs/{request_id}/extra')
    async def extra(request_id: str, p=Depends(app.state.auth.principal)):
        return {}
    missing = [(m, r.path) for m, r in in_scope(app) if (m, r.path) not in ROUTE_CAPS]
    assert missing == [('GET', '/api/v1/runs/{request_id}/extra')]


# ---- refusals ------------------------------------------------------------------------------------------------------

def test_without_the_capability_every_route_refuses_and_asks_no_service(on, store):
    orc = CountingOrc()
    with TestClient(create_app(on, store, orc)) as c:
        user = make_user(store, 'freddie', 'freddie-password')        # the default plan: no Monitor, no pages
        override(store, user['user_id'], 'terminal.view', False)
        h = sign_in(c, 'freddie', 'freddie-password')
        for (method, path), (capability, _) in ROUTE_CAPS.items():
            r = c.request(method, concrete(path, method), headers=h, json=BODIES.get((method, path)))
            assert r.status_code == 403, (method, path, r.status_code, r.text)
            error = r.json()['error']
            assert error['code'] == 'CAPABILITY_REQUIRED' and error['details']['capability'] == capability, (path, error)
        assert orc.asked == [] and FakeHttp.calls == [] and jobs(store) == []


def test_everything_passes_the_gates(on, store):
    """'*' (the account of the plan that holds everything) reaches each service; MFA passed for the test."""
    orc = CountingOrc()
    with TestClient(create_app(on, store, orc)) as c:
        make_user(store, 'ada', 'ada-password', role='admin')
        h = sign_in(c, 'ada', 'ada-password')
        db(store, 'UPDATE edge_bff.sessions SET mfa_passed_at = now()')
        assert c.get('/api/v1/models').json() == FakeOrc.MODELS
        r = c.post('/api/v1/runs', headers=h, json={'message': 'Explain GOTO', 'submission_key': 'one', 'model': MANUAL})
        assert r.status_code == 202, r.text
        assert c.get('/api/v1/radar/index').status_code == 200
        assert c.get('/api/terminal/v1/manifest/BBCA').status_code != 403
        assert any('/api/terminal/v1/manifest/BBCA' in call[1] for call in FakeHttp.calls)


def test_a_paid_account_is_refused_the_monitor_but_keeps_its_pages(on, store):
    orc = CountingOrc()
    with TestClient(create_app(on, store, orc)) as c:
        paid_without_monitor(store, 'pat')
        h = sign_in(c, 'pat', 'pat-password')
        access = c.get('/api/v1/auth/session').json()['access']
        assert 'monitor.view' not in access['capabilities'] and 'radar.view' in access['capabilities']
        for method, path, body in (('GET', '/api/v1/conversations', None), ('GET', '/api/v1/models', None),
                                   ('POST', '/api/v1/runs', BODIES[('POST', '/api/v1/runs')])):
            r = c.request(method, path, headers=h, json=body)
            assert r.status_code == 403 and r.json()['error']['code'] == 'CAPABILITY_REQUIRED', (path, r.text)
        assert orc.asked == [] and jobs(store) == []
        assert c.get('/api/v1/radar/index').status_code == 200


# ---- the model rules -----------------------------------------------------------------------------------------------

def test_the_run_model_is_resolved_and_must_be_held(on, store):
    orc = CountingOrc()
    with TestClient(create_app(on, store, orc)) as c:
        chat_user(store, 'mia', [GLM])
        h = sign_in(c, 'mia', 'mia-password')
        # no model: Orc's server default (DeepSeek) is the run's model, not held
        r = c.post('/api/v1/runs', headers=h, json={'message': 'Explain GOTO', 'submission_key': 'one'})
        assert r.status_code == 403, r.text
        assert r.json()['error']['details']['capability'] == f'monitor.model:{DEEPSEEK}'
        r = c.post('/api/v1/runs', headers=h, json={'message': 'Explain GOTO', 'submission_key': 'two', 'model': DEEPSEEK})
        assert r.status_code == 403 and r.json()['error']['details']['capability'] == f'monitor.model:{DEEPSEEK}'
        assert jobs(store) == [] and orc.asked == ['models']          # only the (cached) list was read
        r = c.post('/api/v1/runs', headers=h, json={'message': 'Explain GOTO', 'submission_key': 'three', 'model': GLM})
        assert r.status_code == 202, r.text
        assert len(jobs(store)) == 1 and 'run' not in orc.asked


def test_the_manual_model_needs_admin_manual(on, store):
    orc = CountingOrc()
    with TestClient(create_app(on, store, orc)) as c:
        user = chat_user(store, 'max', [MANUAL])
        override(store, user['user_id'], 'monitor.model', {'all': True})
        h = sign_in(c, 'max', 'max-password')
        r = c.post('/api/v1/runs', headers=h, json={'message': 'x', 'submission_key': 'one', 'model': MANUAL})
        assert r.status_code == 403 and r.json()['error']['details']['capability'] == 'admin.manual'
        assert jobs(store) == []
        assert c.post('/api/v1/runs', headers=h, json={'message': 'x', 'submission_key': 'two', 'model': DEEPSEEK}).status_code == 202


def test_the_models_list_is_filtered_per_principal(on, store):
    orc = CountingOrc()
    with TestClient(create_app(on, store, orc)) as c:
        user = chat_user(store, 'lia', [GLM])
        h = sign_in(c, 'lia', 'lia-password')
        got = c.get('/api/v1/models', headers=h).json()
        assert [m['model'] for m in got['models']] == [GLM]
        assert got['edge_default'] is None and got['server_default'] is None
        assert got['prices_fetched_at'] == FakeOrc.MODELS['prices_fetched_at']
        override(store, user['user_id'], 'monitor.model', {'ids': [GLM, DEEPSEEK]})
        got = c.get('/api/v1/models', headers=h).json()
        assert [m['model'] for m in got['models']] == [DEEPSEEK, GLM]
        assert got['edge_default'] == FakeOrc.MODELS['edge_default'] and got['server_default'] == FakeOrc.MODELS['server_default']
        assert orc.asked == ['models']                                 # the shared cache, filtered after it
        assert FakeOrc.MODELS['models'][2]['model'] == 'xiaomi/mimo-v2.6-flash'   # the shared list itself is unchanged


# ---- the worker at dispatch ----------------------------------------------------------------------------------------

def dispatch(app, store):
    row = store.claim(30)
    assert row is not None
    asyncio.run(app.state.worker.execute(row))
    return row['request_id']


@pytest.mark.parametrize('lowered', ['chat', 'model'])
def test_a_queued_run_is_refused_at_dispatch_when_the_plan_was_lowered(on, store, lowered):
    orc = CountingOrc()
    app = create_app(on, store, orc)
    with TestClient(app) as c:
        user = chat_user(store, 'quinn', [GLM])
        h = sign_in(c, 'quinn', 'quinn-password')
        assert c.post('/api/v1/runs', headers=h, json={'message': 'x', 'submission_key': 'one', 'model': GLM}).status_code == 202
        if lowered == 'chat':
            override(store, user['user_id'], 'monitor.chat', False)
        else:
            override(store, user['user_id'], 'monitor.model', {'ids': []})
        orc.asked.clear()
        dispatch(app, store)
        assert [(j['state'], j['error_code']) for j in jobs(store)] == [('FAILED', 'CAPABILITY_REQUIRED')]
        assert orc.asked == []


def test_a_queued_run_still_allowed_is_dispatched(on, store):
    orc = CountingOrc()
    app = create_app(on, store, orc)
    with TestClient(app) as c:
        chat_user(store, 'rhea', [GLM])
        h = sign_in(c, 'rhea', 'rhea-password')
        assert c.post('/api/v1/runs', headers=h, json={'message': 'x', 'submission_key': 'one', 'model': GLM}).status_code == 202
        dispatch(app, store)
        assert [j['state'] for j in jobs(store)] == ['FINISHED'] and 'run' in orc.asked


def test_switch_off_the_worker_dispatches_the_configured_owner(settings, store):
    orc = CountingOrc()
    app = create_app(settings, store, orc)
    with TestClient(app) as c:
        h = login(c)
        assert c.post('/api/v1/runs', headers=h, json={'message': 'x', 'submission_key': 'one'}).status_code == 202
        dispatch(app, store)
        assert [j['state'] for j in jobs(store)] == ['FINISHED'] and orc.asked.count('run') == 1
        assert 'models' not in orc.asked                                # '*' needs no model resolution


# ---- page files ----------------------------------------------------------------------------------------------------

def test_a_page_file_is_refused_even_after_another_account_filled_the_shared_cache(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as a:
        b = TestClient(a.app)
        paid_without_monitor(store, 'pat')
        make_user(store, 'freddie', 'freddie-password')
        sign_in(a, 'pat', 'pat-password')
        sign_in(b, 'freddie', 'freddie-password')
        assert a.get('/api/v1/radar/index').status_code == 200
        assert a.get(f'/api/v1/radar/file/radar-days?sha={SHA}').status_code == 200   # the index and bytes are cached
        before = list(FakeHttp.calls)
        for path in ('/api/v1/radar/index', f'/api/v1/radar/file/radar-days?sha={SHA}', '/api/v1/radar/file/radar-days'):
            r = b.get(path, headers={'If-None-Match': f'"{SHA[:32]}"'})
            assert r.status_code == 403 and r.json()['error']['code'] == 'CAPABILITY_REQUIRED', (path, r.text)
            assert r.json()['error']['details']['capability'] == 'radar.view'
        assert FakeHttp.calls == before


def test_page_files_answer_no_cache_and_304_only_after_the_check(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        user = paid_without_monitor(store, 'pat')
        sign_in(c, 'pat', 'pat-password')
        r = c.get(f'/api/v1/radar/file/radar-days?sha={SHA}')
        assert r.status_code == 200 and r.headers['cache-control'] == 'private, no-cache'
        assert r.headers['etag'] == f'"{SHA[:32]}"'
        before = list(FakeHttp.calls)
        r = c.get(f'/api/v1/radar/file/radar-days?sha={SHA}', headers={'If-None-Match': f'"{SHA[:32]}"'})
        assert r.status_code == 304 and r.headers['cache-control'] == 'private, no-cache' and FakeHttp.calls == before
        # the plan lowered (decision D5): the next revalidation is refused, not 304
        override(store, user['user_id'], 'radar.view', False)
        r = c.get(f'/api/v1/radar/file/radar-days?sha={SHA}', headers={'If-None-Match': f'"{SHA[:32]}"'})
        assert r.status_code == 403 and r.json()['error']['code'] == 'CAPABILITY_REQUIRED'


def test_switch_off_the_configured_owner_keeps_every_route(settings, store, monkeypatch):
    monkeypatch.setattr(radar.httpx, 'AsyncClient', FakeHttp)
    FakeHttp.calls = []
    FakeHttp.files = {'radar-days': {'sha256': SHA, 'bytes': len(BODY), 'rows': 1, 'as_of': '2026-11-09'}}
    FakeHttp.stored = {'radar-days': BODY}
    FakeHttp.granted_sha, FakeHttp.grant_status = None, 200
    s = dataclasses.replace(settings, terminal_url='http://terminal-api.railway.internal:8080', terminal_proxy_key=KEY)
    orc = CountingOrc()
    with TestClient(create_app(s, store, orc)) as c:
        h = login(c)
        assert c.get('/api/v1/models').json() == FakeOrc.MODELS
        assert c.get('/api/v1/conversations').status_code == 200
        r = c.post('/api/v1/runs', headers=h, json={'message': 'x', 'submission_key': 'one', 'model': MANUAL})
        assert r.status_code == 202, r.text
        assert c.get(f'/api/v1/radar/file/radar-days?sha={SHA}').status_code == 200
        assert c.get(f'/api/v1/radar/file/radar-days?sha={SHA}', headers={'If-None-Match': f'"{SHA[:32]}"'}).status_code == 304
        assert c.get('/api/terminal/v1/manifest/BBCA').status_code != 403
        assert c.get('/api/v1/auth/session').headers['X-Edge-Entitlements'] == 'env'
