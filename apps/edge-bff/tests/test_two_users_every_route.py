"""EXEC-MU-ACCOUNTS fix round (records track, re-check R1-21): CONTRACT 13.3, two users, derived from the app.

tests/test_principal.py test_two_users_see_none_of_each_others_rows lists the owned kinds and routes by hand, and the
re-check found it left out several (the backtest /events and /cancel, exports, branch and pin, the PUT of a layout,
preset or screener item with another owner's id, adding a ticker to another owner's list, the trials a queued job is
given). This walk derives both sides instead:
- the kinds: every edge_bff table with an owner_key column (information_schema). A makes one row of each through the
  routes; a new owner-keyed table (3c, 3e, Phase 4, Phase 5) fails here until the setup makes a row of it;
- the routes: every /api route and method of app.routes. B calls each with A's values in its path parameters (a new
  path parameter fails here until it has A's value) and a body that passes validation;
- after every call, every row A owns is exactly as before, Orc holds nothing new for A, and B's answer carries none
  of A's content; a route that names an owned id answers B 404, or 409 for a create-or-replace PUT (the no-overwrite
  rule: nothing learned);
- B's backtest is dispatched with B's trials only, though A has trials on the same strategy line.
FakeOrc (conftest.py) is owner-aware for the routes that rely on Orc alone, and the export download (a direct Orc
call) runs against an owner-aware stand-in of Orc's download route.
"""
import asyncio
import json
import re
import secrets
import uuid

import httpx
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import hooks, main as main_module
from app.client import OrcError
from app.main import create_app
from conftest import FakeOrc
from test_backtest import run_next, single
from test_presets import CONFIG as PRESET_CONFIG
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401 - the fixtures
from test_route_table import PRINCIPAL_ONLY, PUBLIC
from test_screener import item_id, screen_item

# path parameters that name one owner's row: another owner's request names nothing (404, or 409 on a create-or-replace
# PUT, as for an id of one's own: nothing learned)
OWNED_IDS = {'request_id', 'conversation_id', 'output_id', 'export_id', 'item_id', 'layout_id', 'preset_id', 'list_id',
             'step_id'}
# routes that change only the caller's own sign-in state: B would end its own session; they carry no owned id
OWN_SESSION = {path for _, path in PRINCIPAL_ONLY if path.startswith('/api/v1/auth/')} - {'/api/v1/auth/session'}
LAYOUT, PRESET, ITEM = 'lay_' + 'a' * 32, 'ipr_' + 'a' * 32, item_id(1)
LINE = {'id': 'd1', 'kind': 'trend-line', 'points': [{'time': '2026-10-01', 'price': 58.6},
                                                      {'time': '2026-11-03', 'price': 61.2}]}
# the bodies A makes its rows with, and B sends on the same route; a write route not named here gets {}
BODIES = {
    ('POST', '/api/v1/runs'): {'message': 'Explain GOTO for alice-only', 'submission_key': 'one'},
    ('PUT', '/api/v1/terminal/layouts/{layout_id}'): {'name': 'Alice swing', 'state': {'ml.tf': 'D'}},
    ('PATCH', '/api/v1/terminal/layouts/{layout_id}'): {'favorite': True},
    ('PUT', '/api/v1/terminal/presets/{preset_id}'): {'name': 'Alice preset', 'def_id': 'FL03', 'config': PRESET_CONFIG},
    ('PATCH', '/api/v1/terminal/presets/{preset_id}'): {'favorite': True},
    ('PUT', '/api/v1/terminal/drawings/{ticker}/{set_id}'): {'drawings': [LINE]},
    ('POST', '/api/v1/watchlist/lists'): {'name': 'Alice banks', 'tickers': ['BBCA']},
    ('PATCH', '/api/v1/watchlist/lists/{list_id}'): {'name': 'Taken over'},
    ('POST', '/api/v1/watchlist/lists/{list_id}/tickers'): {'tickers': ['BMRI']},
    ('PUT', '/api/v1/screener/items/{item_id}'): screen_item(),
    ('POST', '/api/v1/backtests'): {**single(), 'client_request_id': 'mine'},
    ('PUT', '/api/v1/preferences/{key}'): {'value': {'alice': 'alice-only'}, 'version': None},
    ('PATCH', '/api/v1/runs/{request_id}/preferences'): {'pinned': True},
    ('POST', '/api/v1/runs/{request_id}/branch'): {'kind': 'BRANCH', 'title': 'Taken over'},
    ('PATCH', '/api/v1/conversations/{conversation_id}/preferences'): {'title': 'Taken over'},
    ('POST', '/api/v1/conversations/{conversation_id}/outputs/{output_id}/export'): {'columns': [], 'titles': []},
}
OUTPUT = 'out_' + 'ab' * 12


class ExportOrc(FakeOrc):
    """FakeOrc with Orc's table export, owned by the conversation's owner (Orc refuses another owner's output)."""
    def __init__(self):
        super().__init__()
        self.exports = {}

    def export_table(self, owner, conversation_id, output_id, columns, titles):
        if not self.conv_mine(conversation_id, owner) or conversation_id not in self.conversation_owner:
            raise OrcError('OUTPUT_NOT_FOUND', 404)
        export_id = 'exp_' + secrets.token_hex(12)
        self.exports[export_id] = owner
        return {'export_id': export_id, 'file_name': 'alice-only.xlsx', 'size_bytes': 10, 'format': 'xlsx'}

    def state_of(self, owner):
        return json.dumps({'runs': sorted(k for k, t in self.saved.items() if t.get('owner') == owner),
                           'conversations': sorted(k for k, o in self.conversation_owner.items() if o == owner),
                           'exports': sorted(k for k, o in self.exports.items() if o == owner),
                           'stopped': sorted(getattr(self, 'stopped', []))}, sort_keys=True)


def everything_but_admin(store, user):
    """The plan that grants backtest.run without '*' (found by data) and the Monitor by override (admin only in the
    seed, decisions D1 and D8): every tab's gate passes, so a refusal is the isolation's, not the plan's."""
    plan = db(store, '''SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = 'backtest.run'
        AND plan_key NOT IN (SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*')''')[0]['plan_key']
    db(store, "INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, provider) VALUES (%s, %s, 'active', 'test')",
       user['user_id'], plan)
    for key, value in (('monitor.view', 'true'), ('monitor.chat', 'true'), ('monitor.model', '{"all": true}')):
        db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
            VALUES (%s, %s, %s::jsonb, 'test')''', user['user_id'], key, value)


def owner_tables(store):
    return sorted(r['table_name'] for r in db(store, '''SELECT table_name FROM information_schema.columns
        WHERE table_schema = 'edge_bff' AND column_name = 'owner_key' ORDER BY table_name'''))


def rows_of(store, owner, tables):
    return {t: sorted(json.dumps(r['row'], sort_keys=True, default=str) for r in db(
        store, f'SELECT to_jsonb(x) AS row FROM edge_bff.{t} x WHERE owner_key = %s', owner)) for t in tables}


def download_stand_in(orc, url):
    """Orc's GET /v1/exports/{id}/download for the edge-bff download route: the file only to its owner, else 404."""
    real = httpx.AsyncClient

    def handler(request):
        export_id = request.url.path.split('/')[3]
        if orc.exports.get(export_id) == request.headers.get('x-saniti-owner'):
            return httpx.Response(200, content=b'alice-only', headers={'content-type': 'application/octet-stream'})
        return httpx.Response(404, json={'detail': {'code': 'EXPORT_NOT_FOUND'}})

    def client(*args, **kwargs):
        if kwargs.get('base_url') == url:
            kwargs['transport'] = httpx.MockTransport(handler)
        return real(*args, **kwargs)
    return client


def as_bob(body):
    """B's own body on the same route: A's words replaced by B's, so a word of A's in B's answer is A's, never an echo
    of what B sent."""
    return None if body is None else json.loads(json.dumps(body).replace('Alice', 'Bob').replace('alice', 'bob'))


def twin(value):
    """An id of the same form as `value` that nobody made (a callable value gives a callable twin)."""
    if callable(value):
        return lambda path: twin(value(path))
    if re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', value):
        return str(uuid.uuid4())
    head, _, tail = value.rpartition('_')
    return head + '_' + ''.join(secrets.choice('0123456789abcdef') for _ in tail)


def code_of(response):
    try:
        return ((response.json() or {}).get('error') or {}).get('code')
    except ValueError:
        return None


class Person:
    """One signed-in person on the app's one event loop (as in production: one process, one loop). Two TestClients
    would run two loops and the shared worker clients (screener, backtest relay) would be used across them; here every
    person shares the one client and keeps its own cookie jar."""
    def __init__(self, client):
        self.client, self.jar = client, httpx.Cookies()

    @property
    def app(self):
        return self.client.app

    def request(self, method, path, **kwargs):
        self.client.cookies = self.jar
        try:
            return self.client.request(method, path, **kwargs)
        finally:
            self.jar = httpx.Cookies(self.client.cookies)

    def get(self, path, **kwargs):
        return self.request('GET', path, **kwargs)

    def post(self, path, **kwargs):
        return self.request('POST', path, **kwargs)

    def put(self, path, **kwargs):
        return self.request('PUT', path, **kwargs)

    def patch(self, path, **kwargs):
        return self.request('PATCH', path, **kwargs)


def concrete(route, method, ids):
    """The route's path with A's value in every parameter; a parameter with no value is reported."""
    missing = [name for name in re.findall(r'{(\w+)(?::\w+)?}', route.path) if name not in ids]
    if missing:
        return None, missing
    path = re.sub(r'{(\w+)(?::\w+)?}', lambda m: ids[m.group(1)](route.path) if callable(ids[m.group(1)])
                  else ids[m.group(1)], route.path)
    return path, []


def test_b_reaches_nothing_of_a_on_any_route(on, store, workers, monkeypatch):
    orc = ExportOrc()
    monkeypatch.setattr(main_module.httpx, 'AsyncClient', download_stand_in(orc, on.orc_url))
    app = create_app(on, store, orc)
    with TestClient(app) as client:
        a, b = Person(client), Person(client)
        alice, bob = make_user(store, 'alice', 'alice-password'), make_user(store, 'bob_b', 'bob-password')
        for user in (alice, bob):
            everything_but_admin(store, user)
        ha, hb = sign_in(a, 'alice', 'alice-password'), sign_in(b, 'bob_b', 'bob-password')

        # ---- A makes a row of every owned kind through the routes -------------------------------------------------
        run = a.post('/api/v1/runs', headers=ha, json=BODIES[('POST', '/api/v1/runs')])
        assert run.status_code == 202, run.text
        rid = run.json()['request_id']
        job = store.claim(60)
        asyncio.run(app.state.worker.process(job))                     # Orc answers A's run: A's conversation
        conv = orc.saved[rid]['conversation_id']
        if not db(store, 'SELECT 1 FROM edge_bff.conversation_ui WHERE owner_key = %s', alice['owner_key']):
            assert a.patch(f'/api/v1/conversations/{conv}/preferences', headers=ha,
                           json={'title': 'Alice conversation'}).status_code == 200
        made = a.post(f'/api/v1/conversations/{conv}/outputs/{OUTPUT}/export', headers=ha,
                      json=BODIES[('POST', '/api/v1/conversations/{conversation_id}/outputs/{output_id}/export')])
        assert made.status_code == 200, made.text
        export = made.json()['export_id']
        assert a.get(f'/api/v1/exports/{export}').content == b'alice-only'       # the stand-in serves its owner
        for (method, path), value in (
                (('PUT', f'/api/v1/terminal/layouts/{LAYOUT}'), BODIES[('PUT', '/api/v1/terminal/layouts/{layout_id}')]),
                (('PUT', f'/api/v1/terminal/presets/{PRESET}'), BODIES[('PUT', '/api/v1/terminal/presets/{preset_id}')]),
                (('PUT', '/api/v1/terminal/drawings/BBRI/chart'),
                 BODIES[('PUT', '/api/v1/terminal/drawings/{ticker}/{set_id}')]),
                (('PUT', f'/api/v1/screener/items/{ITEM}'), BODIES[('PUT', '/api/v1/screener/items/{item_id}')]),
                (('PUT', '/api/v1/screener/watchlist/BBCA'), None),
                (('PUT', '/api/v1/preferences/ml.my'), BODIES[('PUT', '/api/v1/preferences/{key}')])):
            r = a.request(method, path, headers=ha, json=value)
            assert r.status_code in (200, 201, 204), (path, r.text)
        listed = a.post('/api/v1/watchlist/lists', headers=ha, json=BODIES[('POST', '/api/v1/watchlist/lists')])
        assert listed.status_code == 201, listed.text
        list_id = listed.json()['list']['id']
        bt = a.post('/api/v1/backtests', headers=ha, json=BODIES[('POST', '/api/v1/backtests')])
        assert bt.status_code == 202, bt.text
        bid = bt.json()['request_id']
        assert run_next(a) == bid                                       # A's run ends with its trials recorded
        tables = owner_tables(store)
        empty = [t for t, rows in rows_of(store, alice['owner_key'], tables).items() if not rows]
        assert empty == [], (f'A owns no row in {empty}: make one through its route in this setup, so the walk covers '
                             'that owned kind')
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.backtest_trials WHERE owner_key = %s',
                  alice['owner_key'])[0]['n'] > 0

        # ---- B calls every route with A's values -------------------------------------------------------------------
        ids = {'request_id': lambda path: bid if path.startswith('/api/v1/backtests') else rid,
               'conversation_id': conv, 'output_id': OUTPUT, 'export_id': export, 'item_id': ITEM,
               'layout_id': LAYOUT, 'preset_id': PRESET, 'list_id': list_id, 'step_id': 'step_' + 'a' * 16,
               'ticker': lambda path: 'BBRI' if '/drawings/' in path else 'BBCA', 'set_id': 'chart',
               'key': 'ml.my', 'kind': 'indicator', 'name': 'radar-days', 'path': 'v1/bundle'}
        content = [alice['owner_key'], 'alice-only', 'Alice swing', 'Alice preset', 'Alice banks']
        before, orc_before = rows_of(store, alice['owner_key'], tables), orc.state_of(alice['owner_key'])
        problems, walked = [], 0
        for route in app.routes:
            if not isinstance(route, APIRoute) or not route.path.startswith('/api/') or route.path in PUBLIC \
                    or route.path in OWN_SESSION or hooks.is_hook_path(route.path):
                continue
            admin_only = any(key[0] == 'admin' and check in {d.call for d in route.dependant.dependencies}
                             for key, check in app.state.auth._needs.items())
            for method in sorted(route.methods - {'HEAD'}):
                path, missing = concrete(route, method, ids)
                if missing:
                    problems.append(f'{method} {route.path}: add A\'s value for {missing} to `ids` (an owned id: A\'s '
                                    'row; else the name A used), and to OWNED_IDS when it names one owner\'s row')
                    continue
                body = as_bob(BODIES.get((method, route.path), {})) if method not in ('GET', 'DELETE') else None
                headers, params = (hb if method != 'GET' else None), ({'ticker': 'BBRI'} if method == 'GET' else None)
                r = b.request(method, path, headers=headers, json=body, params=params)
                walked += 1
                sent = set(re.findall(r'[A-Za-z0-9_]+', path))
                leaked = [m for m in content if m in r.text and m not in sent]
                if leaked:
                    problems.append(f'{method} {path}: B\'s answer carries A\'s {leaked}')
                owned = set(re.findall(r'{(\w+)', route.path)) & OWNED_IDS
                if owned and method == 'PUT':
                    # create-or-replace: A's id answers the conflict A's own second create answers (no overwrite)
                    if r.status_code != 409 and not (admin_only and r.status_code == 403):
                        problems.append(f'{method} {path}: B got {r.status_code} on A\'s {sorted(owned)} (expected '
                                        f'409, the conflict of an own id): {r.text[:200]}')
                elif owned:
                    # nothing learned: A's id answers exactly what an id nobody made answers, and never a success
                    other, _ = concrete(route, method, {**ids, **{k: twin(ids[k]) for k in owned}})
                    unmade = b.request(method, other, headers=headers, json=body, params=params)
                    if r.status_code < 400 or (r.status_code, code_of(r)) != (unmade.status_code, code_of(unmade)):
                        problems.append(f'{method} {path}: B got {r.status_code} {code_of(r)} on A\'s {sorted(owned)}, '
                                        f'but {unmade.status_code} {code_of(unmade)} on an id nobody made: '
                                        f'{r.text[:200]}')
                after = rows_of(store, alice['owner_key'], tables)
                if after != before:
                    changed = [t for t in tables if after[t] != before[t]]
                    problems.append(f'{method} {path}: B changed A\'s rows in {changed}')
                    before = after
                if orc.state_of(alice['owner_key']) != orc_before:
                    problems.append(f'{method} {path}: B changed what Orc holds for A')
                    orc_before = orc.state_of(alice['owner_key'])
        assert problems == [], '\n'.join(problems)
        assert walked > 60, walked                                      # the walk really covers the table

        # ---- B's own backtest on A's strategy line gets B's trials only ---------------------------------------------
        b_jobs = db(store, "SELECT request_id FROM edge_bff.backtest_jobs WHERE owner_key = %s AND state = 'QUEUED'",
                    bob['owner_key'])
        assert b_jobs, 'the walk queued B\'s backtest'
        run_next(b)
        context = workers[0].posted('/v1/jobs')[-1]['body']['context']
        assert (context['prior_trials'], context['owner_trials']) == ([], []), context
        # A still reads everything it made
        assert a.get(f'/api/v1/terminal/layouts/{LAYOUT}').status_code == 200
        assert a.get(f'/api/v1/exports/{export}').content == b'alice-only'
        assert a.get(f'/api/v1/backtests/{bid}/result').status_code == 200


@pytest.mark.parametrize('kind', ['layout', 'preset', 'screener item'])
def test_a_put_with_another_owners_id_is_the_same_conflict_as_an_own_one(on, store, kind):
    """The no-overwrite rule by itself: B's create with A's id answers exactly what A's own second create answers."""
    path, body = {'layout': (f'/api/v1/terminal/layouts/{LAYOUT}', BODIES[('PUT', '/api/v1/terminal/layouts/{layout_id}')]),
                  'preset': (f'/api/v1/terminal/presets/{PRESET}', BODIES[('PUT', '/api/v1/terminal/presets/{preset_id}')]),
                  'screener item': (f'/api/v1/screener/items/{ITEM}', BODIES[('PUT', '/api/v1/screener/items/{item_id}')])}[kind]
    app = create_app(on, store, FakeOrc())
    with TestClient(app) as client:
        a, b = Person(client), Person(client)
        alice, bob = make_user(store, 'alice', 'alice-password'), make_user(store, 'bob_b', 'bob-password')
        for user in (alice, bob):
            everything_but_admin(store, user)
        ha, hb = sign_in(a, 'alice', 'alice-password'), sign_in(b, 'bob_b', 'bob-password')
        assert a.put(path, headers=ha, json=body).status_code in (200, 201)
        own_again = a.put(path, headers=ha, json=body)
        foreign = b.put(path, headers=hb, json=body)
        assert foreign.status_code == own_again.status_code == 409, (foreign.text, own_again.text)
        assert foreign.json()['error']['code'] == own_again.json()['error']['code'] == 'REVISION_CONFLICT'
        assert 'revision' not in json.dumps(foreign.json()['error'].get('details') or {}), foreign.text
