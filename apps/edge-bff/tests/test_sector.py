"""EXEC-SECTOR-ANALYSIS S3 (the user's go 2026-11-26: "1A 2A 3 go"; decisions UD66 F and J;
verification/sector_analysis/CONTRACT.md 3 and 4): Sector Analysis through this gateway, as the Market Overview's
(tests/test_overview.py, tests/test_examples.py):

- /api/v1/sector/index and /api/v1/sector/file/<name>?sha= relay terminal-api's family `sector` with the gateway key, the
  page-files rules of app/pages.py (sector.view before the caches, `private, no-cache` with the ETag, a 304 only after
  the check), the family's own refusal codes and names (a sector's stock file named with its index lowercased);
- the page /sector-app/ with the Overview's policy, the shell's /sector, the session's `capabilities.sector`;
- the plans (migration 20261126_050): the paid plan opens the tab, the free plan and a visitor get its example (decision
  J), the admin's '*' covers both; the tab is released (catalog/releases.json, decision F), and a live site whose
  release file does not list it holds neither key for anyone;
- the example: the live publication's opening view on its newest day (sector-meta with that one date, sector-series up
  to it, that day's file), each file cut to the contract's fields; the other days and every sector-stocks-<index> stay
  with sector.view;
- the shell in Chromium: the rail and the phone's pages menu put Sector Analysis right after Overview, its tab opens its
  frame, a visitor gets the example's frame under its dated note and the sign-in box when the page asks for it.
The page itself (apps/edge-bff/sector, built into static/sector-app) is another part's: a probe page stands in for it."""
import dataclasses
import hashlib
import json
import os
import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import examples as examples_module, main, releases, sector as sector_module, terminal_access
from app import principal as principal_module
from app.config import LIVE
from app.main import create_app
from conftest import FakeOrc
from example_docs import SECTOR_DATES, SECTOR_DAYS, SECTOR_GROUPS, sector_files
from test_edge import ORIGIN, login
from test_examples import gz, plan_rows  # noqa: F401 - the fixture
from test_guest import VISITOR, guests  # noqa: F401 - the fixture
from test_plan_catalog import subscribe
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401 - the fixtures
from test_terminal_access import KEY, URL, FakeApi, api, terminal_calls  # noqa: F401 - the fixture

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
NEWEST = SECTOR_DAYS[-1]
OPENING = {'sector-meta', 'sector-series', f'sector-day-{NEWEST}'}


class SectorApi(FakeApi):
    """terminal-api's /sector routes and the bucket, serving a made-up publication (example_docs.sector_files)."""
    files = {}

    def answer(self, method, url, content):
        if url.endswith('/api/terminal/v1/sector') and method == 'GET':
            return httpx.Response(200, json={'finished_at': '2026-11-26T11:00:00Z', 'files': {
                n: {'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b), 'rows': 1, 'as_of': NEWEST}
                for n, b in SectorApi.files.items()}})
        if url.endswith('/api/terminal/v1/sector') and method == 'POST':
            name = json.loads(content)['names'][0]
            if name not in SectorApi.files:
                return httpx.Response(404, json={'error': 'sector_not_published', 'message': 'not published'})
            b = SectorApi.files[name]
            return httpx.Response(200, json={'files': [{'name': name, 'url': f'https://bucket.example/sector/{name}',
                                                        'sha256': hashlib.sha256(b).hexdigest(), 'bytes': len(b)}]})
        return super().answer(method, url, content)

    def stream(self, method, url, params=None, headers=None):
        if not url.startswith('https://bucket.example/sector/'):
            return super().stream(method, url, params, headers)
        FakeApi.calls.append({'method': method, 'url': url, 'params': {}, 'body': None, 'headers': dict(headers or {})})
        body = SectorApi.files[url.rsplit('/', 1)[1]]

        class Answer:
            status_code = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def aiter_bytes(self):
                yield body
        return Answer()


@pytest.fixture
def sector_api(api, monkeypatch):
    monkeypatch.setattr(httpx, 'AsyncClient', SectorApi)
    SectorApi.files = {n: gz(doc) for n, doc in sector_files().items()}
    return SectorApi


def sector_calls():
    return [x for x in terminal_calls() if x['url'].endswith('/api/terminal/v1/sector')]


@pytest.fixture
def page_dir(monkeypatch, tmp_path):
    """A probe in place of the built page (the page part builds the real one into static/sector-app)."""
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>sector</title>')
    (tmp_path / 'assets' / 'index-abc123.js').write_text('void 0')
    monkeypatch.setattr(main, 'SECTOR_APP', tmp_path)
    return tmp_path


@pytest.fixture
def gw(settings, store, sector_api, page_dir):
    """The beta's switch off: the configured owner holds '*'."""
    configured = dataclasses.replace(settings, terminal_url=URL, terminal_proxy_key=KEY)
    with TestClient(create_app(configured, store, FakeOrc())) as c:
        yield c


def entry(c, name):
    return c.get('/api/v1/sector/index').json()['files'][name]


# ---- the relay (app/sector.py on app/pages.py) ------------------------------------------------------------------------

def test_the_sector_files_need_a_session(gw):
    for path in ('/api/v1/sector/index', '/api/v1/sector/file/sector-meta'):
        assert gw.get(path).status_code == 401, path
    assert sector_calls() == []


def test_its_index_and_files_come_from_terminal_apis_sector_routes_with_the_gateway_key(gw):
    login(gw)
    docs = sector_files()
    index = gw.get('/api/v1/sector/index')
    assert index.status_code == 200 and set(index.json()['files']) == set(docs)
    for name in ('sector-meta', 'sector-series', f'sector-day-{NEWEST}', 'sector-stocks-idxfinance'):
        sha = index.json()['files'][name]['sha256']
        r = gw.get(f'/api/v1/sector/file/{name}?sha={sha}')
        assert r.status_code == 200 and r.json() == docs[name], name
        assert (r.headers['cache-control'], r.headers['etag']) == ('private, no-cache', f'"{sha[:32]}"')
        again = gw.get(f'/api/v1/sector/file/{name}?sha={sha}', headers={'if-none-match': f'"{sha[:32]}"'})
        assert again.status_code == 304 and again.headers['cache-control'] == 'private, no-cache'
    calls = sector_calls()
    assert calls and all(x['headers']['x-terminal-proxy-key'] == KEY for x in calls)
    # a file already relayed is served from the process's cache by its sha (no second grant of the same bytes)
    before = len([x for x in calls if x['method'] == 'POST'])
    sha = entry(gw, 'sector-meta')['sha256']
    assert gw.get(f'/api/v1/sector/file/sector-meta?sha={sha}').status_code == 200
    assert len([x for x in sector_calls() if x['method'] == 'POST']) == before


def test_refusals_carry_the_sector_codes_and_the_way_out(gw):
    login(gw)
    for path, status, code in (
            ('/api/v1/sector/file/overview-meta', 400, 'SECTOR_INVALID_NAME'),             # another family's name
            ('/api/v1/sector/file/sector-stocks-IDXFINANCE', 400, 'SECTOR_INVALID_NAME'),  # the index is lowercased
            ('/api/v1/sector/file/sector-day-26-11-2026', 400, 'SECTOR_INVALID_NAME'),
            ('/api/v1/sector/file/sector-day-2026-01-02', 404, 'SECTOR_FILE_NOT_PUBLISHED'),
            ('/api/v1/sector/file/sector-meta?sha=XYZ', 400, 'SECTOR_INVALID_SHA'),
            (f'/api/v1/sector/file/sector-meta?sha={"0" * 64}', 409, 'SECTOR_FILE_REPLACED')):
        r = gw.get(path)
        assert (r.status_code, r.json()['error']['code']) == (status, code), (path, r.text)
        message = r.json()['error']['message']
        assert 'Sector Analysis' in message or 'GET /api/v1/sector/index' in message, path
    message = gw.get('/api/v1/sector/file/x').json()['error']['message']
    assert 'sector-meta, sector-series, sector-day-YYYY-MM-DD, sector-stocks-<index>' in message
    assert 'GET /api/v1/sector/index' in message


def test_the_relay_takes_every_name_of_the_contract_and_terminal_api_keeps_each():
    """CONTRACT 3: sector-meta, sector-series, sector-day-<date>, sector-stocks-<index>, the index lowercased (CONTRACT
    3.4 as amended 2026-11-26): terminal-api keeps only names of its XSECTION_NAME and the publisher's key rule is the
    same, so every name the relay takes fits both, and none longer than 32 characters."""
    bucket = (REPO / 'apps' / 'terminal-api' / 'app' / 'bucket.py').read_text()
    xsection = re.compile(re.search(r"XSECTION_NAME = re\.compile\(r'([^']+)'\)", bucket).group(1))
    publisher = (REPO / 'apps' / 'terminal-publisher' / 'publisher.py').read_text()
    assert "([a-z0-9][a-z0-9_-]{{0,31}})" in publisher                     # the publisher's content key rule
    indexes = ('IDXENERGY', 'IDXBASIC', 'IDXINDUST', 'IDXNONCYC', 'IDXCYCLIC', 'IDXHEALTH', 'IDXFINANCE', 'IDXPROPERT',
               'IDXTECHNO', 'IDXINFRA', 'IDXTRANS')                         # the 11 IDX sector indexes
    names = ['sector-meta', 'sector-series', 'sector-day-2026-11-26', *(f'sector-stocks-{i.lower()}' for i in indexes)]
    for name in names:
        assert sector_module.NAME.fullmatch(name) and xsection.fullmatch(name), name
    for name in ('sector-stocks-IDXFINANCE', 'sector-stocks-', 'sector-stocks-' + 'a' * 19, 'sector-x', 'overview-meta',
                 'sector-day-2026-11-26x', 'Sector-meta'):
        assert not sector_module.NAME.fullmatch(name), name
    assert len('sector-stocks-' + 'a' * 18) == 32 and sector_module.NAME.fullmatch('sector-stocks-' + 'a' * 18)


def test_the_relay_and_the_publisher_name_the_same_files():
    """The publisher part (S2) writes the family in apps/terminal-publisher/sector.py with its NAME, as overview.py's
    (tests/test_overview.py test_the_relay_accepts_every_file_name_the_publisher_writes): both take the contract's names
    and refuse the same wrong ones. Until that module lands on this branch there is nothing to compare."""
    path = REPO / 'apps' / 'terminal-publisher' / 'sector.py'
    if not path.is_file():
        pytest.skip('apps/terminal-publisher/sector.py (the publisher part, S2) is not on this branch yet')
    found = re.search(r"^NAME = re\.compile\(r'([^']+)'\)", path.read_text(), re.M)
    assert found, 'apps/terminal-publisher/sector.py has no module-level NAME = re.compile(r\'...\') as overview.py has'
    publisher = re.compile(found.group(1))
    for name in ('sector-meta', 'sector-series', 'sector-day-2026-11-26', 'sector-stocks-idxfinance',
                 'sector-stocks-idxpropert'):
        assert publisher.fullmatch(name) and sector_module.NAME.fullmatch(name), name
    for name in ('sector-stocks-IDXFINANCE', 'sector-x', 'overview-meta', 'sector-day-26-11-2026'):
        assert not publisher.fullmatch(name) and not sector_module.NAME.fullmatch(name), name


def test_the_page_its_policy_the_shell_route_and_the_capability(gw, settings, store):
    page = gw.get('/sector-app/')
    assert page.status_code == 200 and "connect-src 'self';" in page.headers['content-security-policy']
    assert gw.get('/sector-app/assets/index-abc123.js').headers['cache-control'] == 'public, max-age=31536000, immutable'
    assert gw.get('/sector-app/assets/missing-1.js').status_code == 404
    assert gw.get('/sector').status_code == 200                                  # the shell's route
    login(gw)
    caps = gw.get('/api/v1/auth/session').json()['capabilities']
    assert caps['sector'] is True and caps['overview'] is True
    with TestClient(create_app(settings, store, FakeOrc())) as plain:             # no terminal-api configured
        login(plain)
        assert plain.get('/api/v1/auth/session').json()['capabilities']['sector'] is False
        r = plain.get('/api/v1/sector/index')
        assert (r.status_code, r.json()['error']['code']) == (503, 'SECTOR_NOT_CONFIGURED')


# ---- the plans and the release (decisions F and J; migration 20261126_050) ---------------------------------------------

def test_the_tab_is_released_and_its_capabilities_are_the_overviews(store):
    assert releases.tab_stage('sector') == releases.RELEASED
    rows = {r['capability_key']: r for r in db(store, "SELECT capability_key, kind, data_scope, display_name, means "
                                                      "FROM edge_bff.capabilities WHERE starts_with(capability_key, 'sector.')")}
    assert set(rows) == {'sector.view', 'sector.example'}
    assert all(r['kind'] == 'flag' and r['data_scope'] is None for r in rows.values())
    assert rows['sector.view']['display_name'] == 'Sector Analysis'
    assert 'five tabs' in rows['sector.example']['means']
    held = {(r['plan_key'], r['capability_key']) for r in db(
        store, "SELECT plan_key, capability_key FROM edge_bff.plan_capabilities WHERE starts_with(capability_key, 'sector.') "
               "AND value = 'true'::jsonb")}
    plans = {r['plan_key']: r for r in db(store, 'SELECT plan_key, is_default, for_guests FROM edge_bff.plans')}
    default = next(k for k, r in plans.items() if r['is_default'])
    guest = next(k for k, r in plans.items() if r['for_guests'])
    everything = db(store, "SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*'")[0]['plan_key']
    examples = {p for p, k in held if k == 'sector.example'}
    views = {p for p, k in held if k == 'sector.view'}
    assert examples == {default, guest} and len(views) == 1 and not views & {default, guest, everything}
    # as the Market Overview's: the plan that opens the Overview opens Sector Analysis, the ones with its example get this
    overview = {(r['plan_key'], r['capability_key'].split('.')[1]) for r in db(
        store, "SELECT plan_key, capability_key FROM edge_bff.plan_capabilities WHERE capability_key IN "
               "('overview.view', 'overview.example') AND value = 'true'::jsonb")}
    assert {(p, k.split('.')[1]) for p, k in held} == overview


MIGRATION = REPO / 'database' / 'migrations' / '20261126_050_edge_bff_sector_capabilities.sql'


def test_the_migration_refuses_a_second_run_and_its_rollback_block_runs_as_written(database):
    """On the suite's database (conftest applies it): a second run stops in its preflight; the commented rollback block,
    run in a transaction that is rolled back, takes the two capabilities and their plan rows away, and the rest of the
    catalog stays (the data_scope and value triggers accept it)."""
    import psycopg
    text = MIGRATION.read_text()
    with psycopg.connect(database) as c:
        with pytest.raises(psycopg.errors.RaiseException, match='this migration ran already'):
            c.execute(text)
    lines = text.splitlines()
    tail = lines[max(i for i, line in enumerate(lines) if line.strip() == 'COMMIT;') + 1:]
    start = next(i for i, line in enumerate(tail) if line.strip() == '-- BEGIN;')
    end = next(i for i, line in enumerate(tail) if line.strip() == '-- COMMIT;')
    body = '\n'.join(line[3:] for line in tail[start + 1:end])
    with psycopg.connect(database) as c:
        before = c.execute('SELECT count(*) FROM edge_bff.capabilities').fetchone()[0]
        c.execute(body)
        assert c.execute("SELECT count(*) FROM edge_bff.capabilities WHERE starts_with(capability_key, 'sector.')").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM edge_bff.plan_capabilities WHERE starts_with(capability_key, 'sector.')").fetchone()[0] == 0
        assert c.execute('SELECT count(*) FROM edge_bff.capabilities').fetchone()[0] == before - 2
        c.rollback()
        assert c.execute("SELECT count(*) FROM edge_bff.plan_capabilities WHERE starts_with(capability_key, 'sector.')").fetchone()[0] == 3


def test_paid_opens_the_tab_free_and_visitors_get_the_example(guests, store, sector_api, plan_rows):
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        paid = make_user(store, 'pablo', 'pablo-password')
        subscribe(store, paid['user_id'], 'paid')
        make_user(store, 'freda', 'freda-password')                          # the default plan: free
        h = sign_in(c, 'pablo', 'pablo-password')
        assert 'sector.view' in c.get('/api/v1/auth/session', headers=h).json()['access']['capabilities']
        assert c.get('/api/v1/sector/index', headers=h).status_code == 200
        r = c.get('/api/v1/examples/sector/index', headers=h)
        assert (r.status_code, r.json()['error']['details']['capability']) == (403, 'sector.example')   # the tab itself
        c.post('/api/v1/auth/sign-out', headers=h)
        h = sign_in(c, 'freda', 'freda-password')
        for path in ('/api/v1/sector/index', '/api/v1/sector/file/sector-meta'):
            r = c.get(path, headers=h)
            assert (r.status_code, r.json()['error']['code']) == (403, 'CAPABILITY_REQUIRED'), path
            assert r.json()['error']['details']['capability'] == 'sector.view'
        assert c.get('/api/v1/examples/sector/index', headers=h).json()['as_of'] == NEWEST
        c.post('/api/v1/auth/sign-out', headers=h)
        c.cookies.clear()
        assert c.get('/api/v1/sector/index', headers=VISITOR).status_code == 401
        assert c.get('/api/v1/examples/sector/index', headers=VISITOR).json()['as_of'] == NEWEST
        guest = c.get('/api/v1/auth/guest', headers=VISITOR).json()['access']['capabilities']
        assert 'sector.example' in guest and 'sector.view' not in guest
        # the plan's rows, read on every request: without the guest plan's row the visitor is asked to sign in
        db(store, "DELETE FROM edge_bff.plan_capabilities WHERE capability_key = 'sector.example' AND plan_key IN "
                  "(SELECT plan_key FROM edge_bff.plans WHERE for_guests)")
        r = c.get('/api/v1/examples/sector/index', headers=VISITOR)
        assert r.status_code == 403 and r.json()['error']['details'] == {
            'capability': 'sector.example', 'visitor': True, 'display_name': 'Sector Analysis example'}
        assert 'Sign in' in r.json()['error']['message']


def test_a_live_site_whose_release_file_does_not_list_the_tab_holds_it_for_no_one(guests, store, sector_api, monkeypatch):
    """The migration's rows are in the database both sites share (LIVE_PROMOTION.md principle 3): until `live` runs a
    commit whose release file lists `sector`, the live site refuses both keys to everyone (an unlisted tab is lab:
    principal.beta_only), the admin's '*' included; with the tab released it serves them by plan."""
    site = dataclasses.replace(guests, site=LIVE, prelaunch_enabled=False, orc_url='', orc_key='')
    with TestClient(create_app(site, store, FakeOrc())) as c:
        make_user(store, 'freda', 'freda-password')
        assert c.get('/api/v1/examples/sector/index', headers=VISITOR).status_code == 200      # released here
        h = sign_in(c, 'freda', 'freda-password')
        assert c.get('/api/v1/examples/sector/index', headers=h).status_code == 200
        held = c.get('/api/v1/auth/session', headers=h).json()['access']['capabilities']
        assert 'sector.example' in held
        data = releases.load()
        older = {'schema_version': releases.SCHEMA_VERSION, 'items': [],
                 'tabs': [{'id': t, 'stage': st} for t, st in data.tabs().items() if t != 'sector']}
        monkeypatch.setattr(releases, 'CURRENT', releases.Releases(older, 'the live commit'))
        assert principal_module.beta_only('sector.view') and principal_module.beta_only('sector.example')
        assert c.get('/api/v1/examples/sector/index', headers=h).status_code == 403
        assert c.get('/api/v1/examples/sector/index', headers=VISITOR).status_code == 403
        held = c.get('/api/v1/auth/session', headers=h).json()['access']['capabilities']
        assert not [k for k in held if k.startswith('sector.')]


# ---- the example (decision J; app/examples.py SectorLatest) ----------------------------------------------------------

def sector_example(c, headers):
    r = c.get('/api/v1/examples/sector/index', headers=headers)
    assert r.status_code == 200, r.text
    index = r.json()
    files = {}
    for name, e in index['files'].items():
        f = c.get(f'/api/v1/examples/sector/file/{name}?sha={e["sha256"]}', headers=headers)
        assert f.status_code == 200 and f.headers['etag'] == f'"{e["sha256"][:32]}"', name
        assert f.headers['cache-control'] == 'private, no-cache'
        files[name] = f.json()
    return index, files


def test_a_visitor_reads_the_latest_sector_analysis_as_it_opens(guests, store, sector_api):
    live = sector_files()
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        index, files = sector_example(c, VISITOR)
        assert set(index['files']) == OPENING and index['as_of'] == NEWEST
        assert {e['as_of'] for e in index['files'].values()} == {NEWEST}
        meta, series, day = files['sector-meta'], files['sector-series'], files[f'sector-day-{NEWEST}']
        # the date picker holds the example's day; the rest of meta is the publication's (the sectors, the stocks, the
        # periods, the weight basis and its label)
        assert meta['dates'] == [NEWEST]
        assert {k: v for k, v in meta.items() if k != 'dates'} == {k: v for k, v in live['sector-meta'].items() if k != 'dates'}
        # the series to its day, whole: the five tabs' opening views read up to a year of it (CONTRACT 5)
        assert series == live['sector-series'] and series['dates'][-1] == NEWEST
        assert len(series['dates']) == examples_module.SECTOR_SESSIONS == len(SECTOR_DATES)
        assert day == live[f'sector-day-{NEWEST}']
        assert index['files']['sector-meta']['rows'] == len(meta['stocks']['ticker'])
        assert index['files'][f'sector-day-{NEWEST}']['rows'] == len(day['stocks']['i'])
        # the files behind a click stay with sector.view: the other days of the picker and every sector's stock lines
        for name in (*(f'sector-day-{d}' for d in SECTOR_DAYS[:-1]), *(f'sector-stocks-{i.lower()}' for _, _, i in SECTOR_GROUPS)):
            r = c.get(f'/api/v1/examples/sector/file/{name}', headers=VISITOR)
            assert (r.status_code, r.json()['error']['code']) == (404, 'EXAMPLE_FILE_NOT_FOUND'), name
            assert 'Sector Analysis' in r.json()['error']['message']
        # terminal-api was asked as the visitor (the guest owner, the gateway key), once per file and publication
        calls = sector_calls()
        assert calls and all(x['headers'][terminal_access.OWNER_HEADER] == principal_module.GUEST_OWNER for x in calls)
        before = len(calls)
        sector_example(c, VISITOR)
        assert len(sector_calls()) <= before + 1


def test_the_example_keeps_only_the_contracts_fields_and_ends_at_its_day(guests, store, sector_api):
    """Fail closed at every depth, as the Overview's (the example-mode checker, ERRORS M527): a field the publisher adds
    later is left out until app/examples.py names it; a series date after the example's day is cut with every line; a
    stock column of another length than the day's stocks (read by position) is null."""
    docs = sector_files()
    meta, series, day = docs['sector-meta'], docs['sector-series'], docs[f'sector-day-{NEWEST}']
    meta['private'] = 'x'
    meta['sectors'][0]['private'] = 'x'
    meta['stocks']['private'] = [1] * len(meta['stocks']['ticker'])
    series['private'] = {'a': [1]}
    series['dates'] = series['dates'] + ['2026-11-27']                  # a later session than the newest day file
    for block in ('index', 'sector'):
        for k in series[block]:
            series[block][k] = series[block][k] + [9.0]
    for group in series['breadth'].values():
        group['private'] = [1] * len(series['dates'])
        for k in examples_module.SECTOR_BREADTH_KEYS:
            group[k] = group[k] + [0]
    for ind in series['industry'].values():
        ind['private'] = [1]
        ind['level'], ind['members'] = ind['level'] + [1.0], ind['members'] + [1]
    day['private'] = 'x'
    day['stocks']['private'] = [1] * len(day['stocks']['i'])
    day['stocks']['volume'] = day['stocks']['volume'][:-1]               # one value short: null, never shifted
    day['stocks']['close'] = [{'nested': 1}] + day['stocks']['close'][1:]  # a value holding an object: null
    SectorApi.files.update({'sector-meta': gz(meta), 'sector-series': gz(series), f'sector-day-{NEWEST}': gz(day)})
    clean = sector_files()
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        _, files = sector_example(c, VISITOR)
    m, s, d = files['sector-meta'], files['sector-series'], files[f'sector-day-{NEWEST}']
    assert 'private' not in m and 'private' not in m['sectors'][0] and 'private' not in m['stocks']
    assert m['stocks'] == clean['sector-meta']['stocks'] and m['sectors'] == clean['sector-meta']['sectors']
    assert 'private' not in s and s == clean['sector-series']                # the 27th and every field it lacks cut
    assert 'private' not in d and 'private' not in d['stocks']
    n = len(d['stocks']['i'])
    assert d['stocks']['volume'] == [None] * n and d['stocks']['close'] == [None] * n
    assert {k: v for k, v in d['stocks'].items() if k not in ('volume', 'close')} == \
        {k: v for k, v in clean[f'sector-day-{NEWEST}']['stocks'].items() if k not in ('volume', 'close')}
    assert set(d['stocks']) == set(examples_module.SECTOR_STOCK_KEYS)


def test_the_example_keeps_every_field_the_contract_names():
    """The shapes app/examples.py keeps are CONTRACT 3.1-3.3's fields (verification/sector_analysis/CONTRACT.md): each
    field the contract's files name is kept, so the page reads in the example what it reads live."""
    contract = (REPO / 'verification' / 'sector_analysis' / 'CONTRACT.md').read_text()
    meta = contract.split('### 3.1', 1)[1].split('### 3.2', 1)[0]
    series = contract.split('### 3.2', 1)[1].split('### 3.3', 1)[0]
    day = contract.split('### 3.3', 1)[1].split('### 3.4', 1)[0]
    keys = lambda text: set(re.findall(r'"([a-z_0-9]+)":', text))
    kept_meta = set(examples_module.SECTOR_META_SHAPE) | {'name', 'short', 'index', 'sector', 'ticker', 'industry'}
    assert keys(meta) - {'1D', '3D', '1W', '2W', '1M', '3M', '6M', '1Y'} <= kept_meta, keys(meta) - kept_meta
    kept_series = {'schema', 'dates', 'index', 'sector', 'breadth', 'industry', 'IHSG', 'LQ45', 'Financials', 'Banks',
                   *examples_module.SECTOR_BREADTH_KEYS, *examples_module.SECTOR_INDUSTRY_KEYS}
    assert keys(series) <= kept_series, keys(series) - kept_series
    kept_day = set(examples_module.SECTOR_DAY_SHAPE) | set(examples_module.SECTOR_STOCK_KEYS)
    assert keys(day) <= kept_day, keys(day) - kept_day
    assert set(sector_files()[f'sector-day-{NEWEST}']['stocks']) == set(examples_module.SECTOR_STOCK_KEYS)


def test_the_example_follows_a_new_publication_and_refuses_a_day_file_that_is_not_its_date(guests, store, sector_api):
    docs = sector_files()
    later = dict(docs[f'sector-day-{NEWEST}'], date='2026-11-27', prior_date=NEWEST)
    SectorApi.files['sector-day-2026-11-27'] = gz(later)
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        index, files = sector_example(c, VISITOR)
        assert index['as_of'] == '2026-11-27' and 'sector-day-2026-11-27' in index['files']
        assert files['sector-meta']['dates'] == ['2026-11-27']
    SectorApi.files['sector-day-2026-11-30'] = gz(dict(later, date='2026-11-27'))   # named for a date it does not hold
    with TestClient(create_app(guests, store, FakeOrc())) as c:
        r = c.get('/api/v1/examples/sector/index', headers=VISITOR)
        assert (r.status_code, r.json()['error']['code']) == (503, 'EXAMPLE_UNAVAILABLE')
    del SectorApi.files['sector-day-2026-11-30'], SectorApi.files['sector-day-2026-11-27'], SectorApi.files['sector-meta']
    with TestClient(create_app(guests, store, FakeOrc())) as c:                      # no meta yet: not ready
        r = c.get('/api/v1/examples/sector/index', headers=VISITOR)
        assert (r.status_code, r.json()['error']['code']) == (404, 'EXAMPLE_NOT_READY')
        assert 'Sector Analysis' in r.json()['error']['message']


# ---- the shell (static/edge-app.js, static/edge-labels.js) in Chromium ---------------------------------------------------

SHELL = ROOT / 'static' / 'edge-app.js'


def test_the_shell_names_the_tab_in_its_rail_routes_labels_and_frames():
    page = SHELL.read_text()
    assert ('[[EdgeLabels.overview.nav, "overview"], [EdgeLabels.sector.nav, "sector"], '
            '[EdgeLabels.watchlist.nav, "watchlist"], ["Monitor", "monitor"]') in page
    assert 'const OWNER_PAGES = ["overview", "sector", "watchlist", "radar"];' in page
    assert '"/sector":"sector"' in page and '{path:"/sector", names:["sector"], auth:true, title:"sector"}' in page
    assert '"radar", "overview", "sector", "watchlist"].includes(e.data.route)' in page
    assert 'src: "/sector-app/"' in page and 'navSector:' in page
    labels = (ROOT / 'static' / 'edge-labels.js').read_text()
    assert 'sector: { nav:"Sector Analysis", frameTitle:"Sector analysis" }' in labels
    assert 'sector:"EDGE — Sector Analysis"' in labels


def chromium_or_skip():
    return pytest.importorskip('playwright.sync_api')


def launch(pw):
    return pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM', '/usr/bin/chromium'), headless=True,
                              args=['--no-sandbox'])


def owner_signs_in(page, origin):
    page.route('https://fonts.*/*', lambda route: route.abort())
    page.goto(origin + '/monitor')
    page.locator('#auth-login').fill('owner')
    page.locator('#auth-password').fill('local-test-password')
    page.get_by_role('button', name='Sign In', exact=True).click()


def test_the_rail_puts_sector_analysis_after_overview_and_its_tab_opens_the_frame(settings, store, monkeypatch, tmp_path):
    """The real shell: the rail starts Overview, Sector Analysis, Watchlist; the tab opens /sector with the page's frame
    and title; the page's edge-nav message (Open in Terminal, decision G) switches the shell to the Terminal."""
    playwright = chromium_or_skip()
    from test_screener import serve
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text('<!doctype html><title>Sector frame</title><button id="go">Open in Terminal</button>'
                                         '<script src="/sector-app/assets/probe-1.js"></script>')
    (tmp_path / 'assets' / 'probe-1.js').write_text(
        "document.getElementById('go').onclick = () => parent.postMessage({type: 'edge-nav', route: 'terminal'}, location.origin);"
        "document.body.dataset.ready = '1';")
    monkeypatch.setattr(main, 'SECTOR_APP', tmp_path)
    local, stop = serve(dataclasses.replace(settings, terminal_url=URL, terminal_proxy_key=KEY), store)
    try:
        with playwright.sync_playwright() as pw:
            browser = launch(pw)
            try:
                page = browser.new_page()
                owner_signs_in(page, local.origin)
                tabs = page.locator('.side-nav > button[class*="nav-"]')
                tabs.first.wait_for()
                assert [tabs.nth(i).get_attribute('aria-label') for i in range(3)] == ['Overview', 'Sector Analysis', 'Watchlist']
                assert page.locator('.side-nav button.nav-sector').get_attribute('data-tip') == 'Sector Analysis'
                assert page.locator('.side-nav button.nav-sector svg').count() == 1          # its icon is drawn
                page.locator('.side-nav button.nav-sector').click()
                page.wait_for_url(local.origin + '/sector')
                frame = page.locator('iframe.terminal-frame')
                assert frame.get_attribute('src').endswith('/sector-app/') and frame.get_attribute('title') == 'Sector analysis'
                assert page.title() == 'EDGE — Sector Analysis'
                assert page.locator('.side-nav button.nav-sector').get_attribute('aria-current') == 'page'
                page.frame_locator('iframe.terminal-frame').locator('body[data-ready="1"]').wait_for()
                page.frame_locator('iframe.terminal-frame').locator('#go').click()
                page.wait_for_url(local.origin + '/terminal')
                page.goto(local.origin + '/sector')                                         # a reload stays on the tab
                page.locator('iframe.terminal-frame[src$="/sector-app/"]').wait_for()
            finally:
                browser.close()
    finally:
        stop()


def test_a_phone_reaches_sector_analysis_through_the_pages_menu(settings, store, monkeypatch, tmp_path):
    playwright = chromium_or_skip()
    from test_screener import serve
    (tmp_path / 'index.html').write_text('<!doctype html><title>Sector frame</title><body data-ready="1">')
    monkeypatch.setattr(main, 'SECTOR_APP', tmp_path)
    local, stop = serve(dataclasses.replace(settings, terminal_url=URL, terminal_proxy_key=KEY), store)
    try:
        with playwright.sync_playwright() as pw:
            browser = launch(pw)
            try:
                page = browser.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
                owner_signs_in(page, local.origin)
                button = page.locator('.topbar .pages-btn')
                button.wait_for()
                button.tap()
                items = page.locator('.pages-menu [role=menuitem]')
                assert items.all_text_contents()[:3] == ['Overview', 'Sector Analysis', 'Watchlist']
                item = page.locator('.pages-menu [role=menuitem].pages-sector')
                assert item.bounding_box()['height'] >= 44 and item.locator('svg').count() == 1
                item.tap()
                page.wait_for_url(local.origin + '/sector')
                button.tap()
                assert page.locator('.pages-menu [aria-current=page]').inner_text() == 'Sector Analysis'
                assert page.evaluate('() => document.documentElement.scrollWidth') <= 390      # no sideways scroll
            finally:
                browser.close()
    finally:
        stop()


def test_a_visitor_gets_the_example_frame_under_its_note_and_the_sign_in_box(guests, store, sector_api, monkeypatch, tmp_path):
    """Decision J in the shell (static/edge-app.js ExampleTabPage, LockedDialog): a visitor opening /sector gets the page
    in its frame with ?example=1 under the note naming the example's day, read from /api/v1/examples/sector only; when
    the page asks for the box (a click on any control but its five tabs: the page's own lockOnly) the shell opens "Sign in
    to open Sector Analysis". The probe stands in for the page: it reads the example's index and posts the box's message."""
    playwright = chromium_or_skip()
    from test_screener import serve
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'index.html').write_text(
        '<!doctype html><title>Sector frame</title><div role="tablist"><button role="tab" id="tab2">Relative Strength</button>'
        '</div><button id="period">1M</button><script src="/sector-app/assets/probe-2.js"></script>')
    (tmp_path / 'assets' / 'probe-2.js').write_text(
        "const example = new URLSearchParams(location.search).get('example') === '1';"
        "fetch('/api/v1/examples/sector/index').then(r => r.json()).then(i => { document.body.dataset.asOf = i.as_of; });"
        "document.getElementById('tab2').onclick = () => { document.body.dataset.tab = '2'; };"
        "document.getElementById('period').onclick = () => example && parent.postMessage("
        "{source: 'sector', type: 'locked', kind: 'example', id: 'sector', name: 'Sector Analysis'}, location.origin);")
    monkeypatch.setattr(main, 'SECTOR_APP', tmp_path)
    local, stop = serve(guests, store)
    try:
        with playwright.sync_playwright() as pw:
            browser = launch(pw)
            try:
                page = browser.new_page()
                page.route('https://fonts.*/*', lambda route: route.abort())
                seen = []
                page.on('request', lambda r: seen.append(r.url))
                page.goto(local.origin + '/sector')
                frame_el = page.locator('main.example-page[data-example-tab="sector"] iframe.terminal-frame')
                frame_el.wait_for(timeout=20000)
                assert frame_el.get_attribute('src').endswith('/sector-app/?example=1')
                assert frame_el.get_attribute('title') == 'Sector Analysis example'
                note = ' '.join(page.locator('.example-bar').inner_text().split())
                assert 'Sector Analysis with the data of Thu 26 Nov 2026' in note, note
                frame = page.frame_locator('main.example-page iframe.terminal-frame')
                frame.locator(f'body[data-as-of="{NEWEST}"]').wait_for(timeout=10000)
                frame.locator('#tab2').click()                                   # an internal tab: no box
                frame.locator('body[data-tab="2"]').wait_for()
                assert page.locator('.locked-dialog').count() == 0
                frame.locator('#period').click()                                 # any other control: the sign-in box
                box = page.locator('.locked-dialog')
                box.wait_for(timeout=10000)
                assert 'Sign in to open Sector Analysis' in box.inner_text()
                paths = {u.split('?')[0].replace(local.origin, '') for u in seen if u.startswith(local.origin)}
                assert not [p for p in paths if p.startswith('/api/v1/sector/')], paths     # no live route asked
            finally:
                browser.close()
    finally:
        stop()
