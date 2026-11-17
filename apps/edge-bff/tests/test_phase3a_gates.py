"""EXEC-MU-ACCOUNTS Phase 3a (CONTRACT.md 8b "3a in detail", decisions D1-D8; builder B1): the edge-bff route gates and
the saved-item caps of the Backtest, Screener, Terminal saves (layouts, presets, drawings) and Watchlist lists.

- route walk: every route these modules register carries its `auth.need(capability, write)` (found in FastAPI's
  dependant tree), as ROUTE_CAPS names it; a new route without an entry fails with the entry to add;
- switch on: a free principal (the default plan) is refused 403 CAPABILITY_REQUIRED on each gated route; a paid or an
  admin principal is not;
- caps: min(plan limit, HARD); a lowered limit (an override) is refused at that limit with LIMIT_EXCEEDED and reported
  by the routes that publish limits; an override above HARD stays at HARD;
- D5: a lowered plan cannot read the old items (kept; readable again once the plan is raised), an ended plan answers
  PLAN_EXPIRED;
- a queued backtest whose owner lost backtest.run ends FAILED CAPABILITY_REQUIRED at dispatch, with no worker call;
- the migration 20261117_004 refuses a second run and the paid seed holds today's constants.
The switch-off principal of the configured owner holds '*' (conftest settings admin_owners = (owner,), as production's
default), so every existing suite runs unchanged.
"""
import dataclasses
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi import Depends
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import backtest as backtest_module, drawings, layouts, presets, screener, watchlist
from app.config import Settings
from app.main import create_app
from app.principal import Principal
from conftest import FakeOrc
from test_backtest import run_next, single
from test_edge import ORIGIN, login
from test_presets import CONFIG as PRESET_CONFIG
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401 - the fixtures
from test_screener import item_id, screen_item

ROOT = Path(__file__).resolve().parents[3]
MIGRATION = ROOT / 'database/migrations/20261117_004_edge_bff_catalog_phase3a.sql'

# the modules whose every route is gated here (the Monitor routes, the page files and the Terminal proxy are B2's)
GATED_MODULES = {'app.backtest', 'app.screener', 'app.layouts', 'app.drawings', 'app.presets', 'app.watchlist'}
BT, SC, LAY, PRE, DRW, WL = ('/api/v1/backtests', '/api/v1/screener', '/api/v1/terminal/layouts', '/api/v1/terminal/presets',
                             '/api/v1/terminal/drawings', '/api/v1/watchlist')
# (method, path) -> (capability, write): D5 = B, reads need the view or the item's capability, writes the run or save one
ROUTE_CAPS = {
    ('GET', f'{BT}/catalog'): ('backtest.view', False),
    ('GET', BT): ('backtest.view', False),
    ('GET', f'{BT}/{{request_id}}'): ('backtest.view', False),
    ('GET', f'{BT}/{{request_id}}/result'): ('backtest.view', False),
    ('GET', f'{BT}/{{request_id}}/events'): ('backtest.view', False),
    ('POST', f'{BT}/{{request_id}}/cancel'): ('backtest.view', True),
    ('POST', f'{BT}/signals'): ('backtest.run', True),
    ('POST', BT): ('backtest.run', True),
    ('GET', f'{SC}/catalog'): ('screener.view', False),
    ('GET', f'{SC}/universe'): ('screener.view', False),
    ('GET', f'{SC}/items'): ('screener.view', False),
    ('GET', f'{SC}/watchlist'): ('screener.view', False),
    ('POST', f'{SC}/run'): ('screener.run', True),
    ('POST', f'{SC}/preview'): ('screener.run', True),
    ('POST', f'{SC}/validate'): ('screener.run', True),
    ('POST', f'{SC}/counts'): ('screener.run', True),
    ('PUT', f'{SC}/items/{{item_id}}'): ('screener.run', True),
    ('DELETE', f'{SC}/items/{{item_id}}'): ('screener.view', True),
    ('PUT', f'{SC}/watchlist/{{ticker}}'): ('screener.run', True),
    ('DELETE', f'{SC}/watchlist/{{ticker}}'): ('screener.run', True),
    ('GET', LAY): ('terminal.layouts', False),
    ('GET', f'{LAY}/{{layout_id}}'): ('terminal.layouts', False),
    ('PUT', f'{LAY}/{{layout_id}}'): ('terminal.layouts', True),
    ('PATCH', f'{LAY}/{{layout_id}}'): ('terminal.layouts', True),
    ('DELETE', f'{LAY}/{{layout_id}}'): ('terminal.layouts', True),
    ('GET', PRE): ('terminal.presets', False),
    ('PUT', f'{PRE}/{{preset_id}}'): ('terminal.presets', True),
    ('PATCH', f'{PRE}/{{preset_id}}'): ('terminal.presets', True),
    ('DELETE', f'{PRE}/{{preset_id}}'): ('terminal.presets', True),
    ('GET', DRW): ('terminal.drawings', False),
    ('PUT', f'{DRW}/{{ticker}}/{{set_id}}'): ('terminal.drawings', True),
    ('DELETE', f'{DRW}/{{ticker}}/{{set_id}}'): ('terminal.drawings', True),
    ('GET', f'{WL}/lists'): ('watchlist.view', False),
    ('POST', f'{WL}/lists'): ('watchlist.view', True),
    ('PATCH', f'{WL}/lists/{{list_id}}'): ('watchlist.view', True),
    ('DELETE', f'{WL}/lists/{{list_id}}'): ('watchlist.view', True),
    ('PUT', f'{WL}/indicators'): ('watchlist.view', True),
    ('POST', f'{WL}/lists/{{list_id}}/tickers'): ('watchlist.view', True),
    ('DELETE', f'{WL}/lists/{{list_id}}/tickers/{{ticker}}'): ('watchlist.view', True),
}
SAMPLE = {'request_id': 'bt_' + '0' * 32, 'item_id': item_id(1), 'ticker': 'BBCA', 'layout_id': 'lay_' + 'a' * 32,
          'preset_id': 'ipr_' + 'a' * 32, 'set_id': 'chart', 'list_id': str(uuid.uuid4())}
GATE_CODES = ('CAPABILITY_REQUIRED', 'PLAN_EXPIRED')


def calls(dependant):
    for dependency in dependant.dependencies:
        yield dependency.call
        yield from calls(dependency)


def gate_problems(app):
    """What the route walk finds: a gated module's route without a ROUTE_CAPS entry, a route without the need its entry
    names (the capability and, for a write, the CSRF variant), and an entry naming no route."""
    needs = {check: key[1:] for key, check in app.state.auth._needs.items() if key[0] == 'need'}
    found, seen = [], set()
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.endpoint.__module__ not in GATED_MODULES:
            continue
        held = {needs[c] for c in calls(route.dependant) if c in needs}
        for method in sorted(route.methods):
            key = (method, route.path)
            seen.add(key)
            if key not in ROUTE_CAPS:
                found.append(f'{method} {route.path} ({route.endpoint.__module__}): no entry in ROUTE_CAPS; add '
                             f"ROUTE_CAPS[('{method}', '{route.path}')] = ('<tab>.view or the run/save capability', "
                             f"{method not in ('GET', 'HEAD')}) and gate the route with auth.need(...)")
            elif ROUTE_CAPS[key] not in held:
                found.append(f'{method} {route.path}: carries {sorted(held)}, not auth.need{ROUTE_CAPS[key]}')
    found += [f'{m} {p}: ROUTE_CAPS names a route that is not served' for m, p in sorted(set(ROUTE_CAPS) - seen)]
    return found


def configured(settings):
    from test_route_table import configured as every_feature
    return every_feature(settings)


def url_of(path):
    return path.format(**SAMPLE)


def paid_plan(store):
    """The plan that grants backtest.run without '*' (found by data, as the code does: no plan key in code)."""
    rows = db(store, '''SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = 'backtest.run'
        AND plan_key NOT IN (SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*')''')
    assert len(rows) == 1, rows
    return rows[0]['plan_key']


def subscribe(store, user_id, plan, expires='NULL'):
    db(store, f'''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, starts_at, expires_at, provider)
        VALUES (%s, %s, 'active', now() - interval '1 day', {expires}, 'test')''', user_id, plan)


def override(store, user_id, key, value):
    db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
        VALUES (%s, %s, %s::jsonb, 'test') ON CONFLICT (user_id, capability_key) DO UPDATE SET value = EXCLUDED.value''',
       user_id, key, value)


def paid_user(store, name):
    user = make_user(store, name, name + '-password')
    subscribe(store, user['user_id'], paid_plan(store))
    return user


def request(c, h, method, path, json=None):
    write = method not in ('GET', 'HEAD')
    return c.request(method, url_of(path), headers=h if write else None, json=json if write else None,
                     params={'ticker': 'BBCA'} if path.endswith('/events') or path == DRW else None)


# ---- the route walk ---------------------------------------------------------------------------------------------------

def test_every_gated_route_carries_its_need(settings, store):
    app = create_app(configured(settings), store, FakeOrc())
    assert gate_problems(app) == []
    gated = {(m, r.path) for r in app.routes if isinstance(r, APIRoute) and r.endpoint.__module__ in GATED_MODULES
             for m in r.methods}
    assert gated == set(ROUTE_CAPS) and len(gated) == 39


def test_the_walk_refuses_a_route_without_its_need(settings, store):
    app = create_app(configured(settings), store, FakeOrc())
    auth = app.state.auth

    async def unlisted(p: Principal = Depends(auth.principal)):
        return {}
    unlisted.__module__ = 'app.backtest'
    app.get('/api/v1/backtests/example/unlisted')(unlisted)

    async def wrong(p: Principal = Depends(auth.need('backtest.view'))):
        return {}
    wrong.__module__ = 'app.screener'
    app.post('/api/v1/screener/example/wrong')(wrong)
    ROUTE_CAPS[('POST', '/api/v1/screener/example/wrong')] = ('screener.run', True)
    try:
        found = gate_problems(app)
    finally:
        del ROUTE_CAPS[('POST', '/api/v1/screener/example/wrong')]
    assert any('/api/v1/backtests/example/unlisted' in f and 'no entry in ROUTE_CAPS; add' in f for f in found), found
    assert any('/api/v1/screener/example/wrong' in f and "('screener.run', True)" in f for f in found), found


# ---- free, paid and admin principals (switch on) -------------------------------------------------------------------

def test_a_free_principal_is_refused_on_every_gated_route(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        make_user(store, 'alice', 'alice-password')
        h = sign_in(c, 'alice', 'alice-password')
        for (method, path), (capability, _) in ROUTE_CAPS.items():
            r = request(c, h, method, path, {})
            assert r.status_code == 403, (method, path, r.status_code, r.text)
            error = r.json()['error']
            assert error['code'] == 'CAPABILITY_REQUIRED' and error['details']['capability'] == capability, (method, path, error)
            assert error['message']
        # a write keeps the CSRF check first (the clients retry once on CSRF_INVALID)
        r = c.put(url_of(f'{LAY}/{{layout_id}}'), headers=ORIGIN, json={})
        assert r.json()['error']['code'] == 'CSRF_INVALID'


@pytest.mark.parametrize('who', ['paid', 'admin'])
def test_a_paid_or_admin_principal_passes_every_gate(on, store, who):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        if who == 'paid':
            paid_user(store, 'alice')
        else:
            make_user(store, 'alice', 'alice-password', role='admin')
        h = sign_in(c, 'alice', 'alice-password')
        if who == 'admin':
            db(store, 'UPDATE edge_bff.sessions SET mfa_passed_at = now() WHERE revoked_at IS NULL')
        for method, path in ROUTE_CAPS:
            r = request(c, h, method, path, {})
            code = r.json().get('error', {}).get('code') if r.headers.get('content-type', '').startswith('application/json') \
                and isinstance(r.json(), dict) else None
            assert code not in GATE_CODES and r.status_code != 401, (method, path, r.status_code, r.text)


def test_the_paid_seed_holds_todays_constants_and_no_monitor(store, settings):
    plan = paid_plan(store)
    got = {r['capability_key']: r['value'] for r in db(store, 'SELECT capability_key, value FROM edge_bff.plan_capabilities '
                                                              'WHERE plan_key = %s', plan)}
    assert got['terminal.layouts_max'] == layouts.LAYOUT_LIMIT
    assert got['terminal.presets_max'] == presets.PRESET_LIMIT
    assert got['terminal.drawings_max'] == drawings.SET_LIMIT
    assert got['screener.saved_items'] == screener.SCREEN_LIMIT
    assert got['backtest.queued_jobs'] == Settings.__dataclass_fields__['backtest_queued_per_owner'].default == 3
    assert (got['watchlist.lists'], got['watchlist.per_list'], got['watchlist.indicators']) == \
        (watchlist.LISTS, watchlist.PER_LIST, watchlist.INDICATORS)
    assert got['monitor.example'] is True and got['terminal.presets'] is True
    assert not {'monitor.view', 'monitor.chat', 'monitor.model'} & set(got)
    assert not db(store, "SELECT 1 FROM edge_bff.plan_capabilities WHERE capability_key = 'admin.manual'")
    kinds = {r['capability_key']: (r['kind'], r['unit']) for r in db(store, 'SELECT capability_key, kind, unit FROM edge_bff.capabilities')}
    assert kinds['admin.manual'] == ('flag', None) and kinds['terminal.presets'] == ('flag', None)
    for key in ('terminal.layouts_max', 'terminal.presets_max', 'terminal.drawings_max', 'screener.saved_items',
                'backtest.queued_jobs'):
        assert kinds[key][0] == 'limit' and kinds[key][1], key
    # the value-shape trigger of 20261117_003 checks the new rows too
    with pytest.raises(psycopg.errors.RaiseException, match='does not fit'):
        db(store, "UPDATE edge_bff.plan_capabilities SET value = '\"50\"' WHERE plan_key = %s AND capability_key = 'terminal.layouts_max'", plan)


def test_the_phase3a_migration_refuses_a_second_run(database):
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='reconcile before applying'):
            conn.execute(MIGRATION.read_text())


# ---- caps: min(plan limit, HARD) ------------------------------------------------------------------------------------

def test_a_lowered_limit_is_refused_at_that_limit_and_reported(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        for key in ('terminal.layouts_max', 'terminal.presets_max', 'terminal.drawings_max', 'screener.saved_items',
                    'watchlist.lists', 'watchlist.per_list', 'watchlist.indicators'):
            override(store, alice['user_id'], key, '1')
        h = sign_in(c, 'alice', 'alice-password')

        def refused(r, limit, allowed=1, needed=2):
            assert r.status_code == 422, r.text
            error = r.json()['error']
            assert error['code'] == 'LIMIT_EXCEEDED' and error['details'] == {'limit': limit, 'allowed': allowed, 'needed': needed}, error
            return error

        # layouts
        assert c.put(f'{LAY}/lay_{"1" * 32}', headers=h, json={'name': 'A', 'state': {'ml.tf': 'D'}}).status_code == 201
        assert 'At most 1 layouts' in refused(c.put(f'{LAY}/lay_{"2" * 32}', headers=h, json={'name': 'B', 'state': {}}), 'layouts')['message']
        assert c.get(LAY).json()['limit'] == 1
        # a replace is no new item: never refused by the cap
        assert c.put(f'{LAY}/lay_{"1" * 32}', headers=h, json={'name': 'A2', 'state': {}, 'revision': 1}).status_code == 200
        # presets
        assert c.put(f'{PRE}/ipr_{"1" * 32}', headers=h, json={'name': 'P', 'def_id': 'FL03', 'config': PRESET_CONFIG}).status_code == 201
        refused(c.put(f'{PRE}/ipr_{"2" * 32}', headers=h, json={'name': 'Q', 'def_id': 'FL03', 'config': PRESET_CONFIG}), 'presets')
        assert c.get(PRE).json()['limit'] == 1
        # drawings
        line = {'id': 'd1', 'kind': 'trend-line', 'points': [{'time': '2026-10-01', 'price': 58.6}, {'time': '2026-11-03', 'price': 61.2}]}
        assert c.put(f'{DRW}/BBRI/chart', headers=h, json={'drawings': [line]}).status_code == 201
        refused(c.put(f'{DRW}/BBCA/chart', headers=h, json={'drawings': [line]}), 'sets')
        assert c.get(DRW, params={'ticker': 'BBRI'}).json()['limits']['sets'] == 1
        # screener saved items, and the star (watchlist.per_list)
        assert c.put(f'{SC}/items/{item_id(1)}', headers=h, json=screen_item()).status_code == 200
        refused(c.put(f'{SC}/items/{item_id(2)}', headers=h, json=screen_item(name='Second')), 'saved_items')
        assert c.put(f'{SC}/watchlist/BBCA', headers=h).status_code == 204
        refused(c.put(f'{SC}/watchlist/BBRI', headers=h), 'watchlist')
        published = {x['name']: x['value'] for x in c.get(f'{SC}/catalog').json()['limits']}
        assert (published['saved_items'], published['watchlist']) == (1, 1)
        # the watchlist lists (the star made the first list)
        listed = c.get(f'{WL}/lists').json()
        assert {x['name']: x['value'] for x in listed['limits']} == {'lists': 1, 'tickers': 1, 'indicators': 1,
                                                                    'name': watchlist.NAME_CHARS}
        refused(c.post(f'{WL}/lists', headers=h, json={'name': 'Second'}), 'lists')
        first = listed['lists'][0]['id']
        refused(c.post(f'{WL}/lists/{first}/tickers', headers=h, json={'tickers': ['BBRI']}), 'tickers')
        refused(c.patch(f'{WL}/lists/{first}', headers=h, json={'indicators': ['rsi', 'fn5']}), 'indicators')
        # an override above HARD stays at HARD (the storage guarantee)
        override(store, alice['user_id'], 'terminal.layouts_max', '100000')
        assert c.get(LAY).json()['limit'] == layouts.LAYOUT_LIMIT


def test_the_switch_off_principal_and_the_paid_plan_publish_hard(settings, store, on):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        login(c)
        assert c.get(LAY).json()['limit'] == layouts.LAYOUT_LIMIT
        assert c.get(PRE).json()['limit'] == presets.PRESET_LIMIT
        assert c.get(f'{WL}/lists').json()['limits'] == watchlist.limits()
    with TestClient(create_app(on, store, FakeOrc())) as c:
        paid_user(store, 'alice')
        sign_in(c, 'alice', 'alice-password')
        assert c.get(LAY).json()['limit'] == layouts.LAYOUT_LIMIT
        assert c.get(DRW, params={'ticker': 'BBCA'}).json()['limits']['sets'] == drawings.SET_LIMIT
        assert c.get(f'{WL}/lists').json()['limits'] == watchlist.limits()
        mine = [x for x in c.get(f'{SC}/catalog').json()['limits'] if x['name'] in ('saved_items', 'watchlist')]
        assert mine == screener.own_limits()[:2]


def test_the_queued_backtest_limit_follows_the_plan(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        override(store, alice['user_id'], 'backtest.queued_jobs', '1')
        h = sign_in(c, 'alice', 'alice-password')
        assert c.post(BT, headers=h, json={**single(), 'client_request_id': 'one'}).status_code == 202
        r = c.post(BT, headers=h, json={**single('BBRI'), 'client_request_id': 'two'})
        assert r.status_code == 429 and r.json()['error']['code'] == 'LIMIT_REACHED', r.text    # C1 F2: a plan limit


# ---- D5: a lowered plan loses the reads; a queued job is checked again at dispatch ----------------------------------

def test_a_lowered_plan_cannot_read_old_items_until_it_is_raised(on, store):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        h = sign_in(c, 'alice', 'alice-password')
        lay = f'{LAY}/lay_{"1" * 32}'
        assert c.put(lay, headers=h, json={'name': 'Swing', 'state': {'ml.tf': 'D'}}).status_code == 201
        made = c.post(f'{WL}/lists', headers=h, json={'name': 'Banks', 'tickers': ['BBCA']}).json()['list']
        assert c.put(f'{SC}/items/{item_id(1)}', headers=h, json=screen_item()).status_code == 200
        reads = (lay, LAY, f'{WL}/lists', f'{SC}/items')
        # lowered (the subscription cancelled): the default plan; every read refused, the rows kept
        db(store, "UPDATE edge_bff.subscriptions SET status = 'cancelled' WHERE user_id = %s", alice['user_id'])
        for path in reads:
            r = c.get(path)
            assert r.status_code == 403 and r.json()['error']['code'] == 'CAPABILITY_REQUIRED', (path, r.text)
        assert c.delete(lay, headers=h).json()['error']['code'] == 'CAPABILITY_REQUIRED'
        assert db(store, 'SELECT count(*) AS n FROM edge_bff.terminal_layouts WHERE owner_key = %s', alice['owner_key'])[0]['n'] == 1
        # raised again: the same items, as they were
        subscribe(store, alice['user_id'], paid_plan(store))
        assert c.get(lay).json()['name'] == 'Swing'
        assert [x['id'] for x in c.get(f'{WL}/lists').json()['lists']] == [made['id']]
        assert len(c.get(f'{SC}/items').json()['items']) == 1
        # ended (expired a moment ago): PLAN_EXPIRED, which names the ended plan
        db(store, "UPDATE edge_bff.subscriptions SET starts_at = now() - interval '2 days', expires_at = now() - interval '1 second' "
                  "WHERE user_id = %s AND status = 'active'", alice['user_id'])
        r = c.get(lay)
        assert r.status_code == 403 and r.json()['error']['code'] == 'PLAN_EXPIRED'
        assert r.json()['error']['details']['expired_plan'] == paid_plan(store)


def test_a_queued_backtest_is_refused_at_dispatch_when_the_plan_lost_run(on, store, workers):
    with TestClient(create_app(on, store, FakeOrc())) as c:
        alice = paid_user(store, 'alice')
        h = sign_in(c, 'alice', 'alice-password')
        job = c.post(BT, headers=h, json={**single(), 'client_request_id': 'mine'})
        assert job.status_code == 202, job.text
        db(store, "UPDATE edge_bff.subscriptions SET status = 'cancelled' WHERE user_id = %s", alice['user_id'])
        before = len(workers[0].posted('/v1/jobs'))
        run_next(c)
        assert len(workers[0].posted('/v1/jobs')) == before                    # the worker was never called
        row = db(store, 'SELECT state, error FROM edge_bff.backtest_jobs WHERE request_id = %s', job.json()['request_id'])[0]
        assert row['state'] == 'FAILED' and row['error']['code'] == 'CAPABILITY_REQUIRED'
        assert row['error']['details']['capability'] == 'backtest.run' and row['error']['message']
        # raised again, a new job runs
        subscribe(store, alice['user_id'], paid_plan(store))
        assert c.post(BT, headers=h, json={**single('BBRI'), 'client_request_id': 'again'}).status_code == 202
        run_next(c)
        assert len(workers[0].posted('/v1/jobs')) == before + 1


def test_the_switch_off_principal_dispatches_as_before(settings, store, workers):
    from test_backtest import KEY
    s = dataclasses.replace(settings, backtest_worker_url=workers[0].url, backtest_worker_key=KEY,
                            backtest_timeout_seconds=30, backtest_max_result_bytes=2 ** 20)
    with psycopg.connect(settings.database_url) as conn:
        conn.execute('TRUNCATE edge_bff.backtest_results, edge_bff.backtest_trials, edge_bff.backtest_jobs')
    with TestClient(create_app(s, store, FakeOrc())) as c:
        h = login(c)
        assert c.post(BT, headers=h, json={**single(), 'client_request_id': 'one'}).status_code == 202
        run_next(c)
        assert len(workers[0].posted('/v1/jobs')) == 1
    assert backtest_module.RUN == 'backtest.run'
