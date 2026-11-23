"""3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"): who is served a page's lab build and a lab tab.

- The Terminal and Backtest pages have a lab build (every item, the lab formulas). edge-bff serves it from /<app>/ to the
  admin on the beta (auth.lab_admin: admin.access and the second factor passed) who holds every item of every kind
  (catalog.holds_every_item, the catalogs' own rule; round 2 of the checker, CS-1); its assets answer under
  /<app>/lab/assets/ to that admin only, cached privately. Everyone else, and everyone on the live site, gets the public
  build, and the lab assets answer 404.
- A tab at the lab stage (releases.tab_stage) is served to that admin on the beta when it holds the tab's own
  <tab>.view; its page and assets answer 404 to everyone else and on the live site. The tabs are read from the release
  file, each switched to lab in turn.
- The repository's real builds are served once too (round 2, CRIT-2): every file a lab page names answers to the
  admin, and no lab file to a visitor.
"""
import dataclasses
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main, releases
from app.main import create_app
from conftest import FakeOrc
from test_beta_live_site import db, live_of, sign_in_admin
from test_edge import ORIGIN, login
from test_3f_public_bundles import missing
from test_auth_flows import on  # noqa: F401 - the fixture `on` (the switch on)
from test_phase3a_gates import override, paid_user

LAB_APPS = (('terminal-app', main.TERMINAL_CSP), ('backtest-app', main.BACKTEST_CSP))
# the pages edge-bff serves (main.py <TAB>_APP, each a /<tab>-app/): a tab of the release file is a page, or a capability
# domain the shell shows without a page of its own (Phase 4's support.send: the rail's Contact support dialog), which
# test_live_switch.py holds to its live switch. Derived from main, so a new page or a new page-less domain needs no list
PAGE_APPS = sorted(name.removesuffix('_APP') for name in vars(main) if name.endswith('_APP') and not name.endswith('_LAB_APP'))
PAGE_TABS = {name.lower() for name in PAGE_APPS}


def beta_on(settings):
    return dataclasses.replace(live_of(settings), site='beta', orc_url=settings.orc_url, orc_key=settings.orc_key)


@pytest.fixture
def built(tmp_path, monkeypatch):
    """Every page's public build, and the Terminal's and Backtest's lab builds, as small stand-ins."""
    for name, title in (('public', 'PUBLIC BUILD'), ('lab', 'LAB BUILD')):
        (tmp_path / name / 'assets').mkdir(parents=True)
        (tmp_path / name / 'index.html').write_text(f'<!doctype html><title>{title}</title>')
        (tmp_path / name / 'assets' / f'index-{name}01.js').write_text('void 0')
    for app in PAGE_APPS:
        monkeypatch.setattr(main, f'{app}_APP', tmp_path / 'public')
    for app in ('TERMINAL', 'BACKTEST'):
        monkeypatch.setattr(main, f'{app}_LAB_APP', tmp_path / 'lab')


def served(c, prefix):
    """(the build its page is, the status of a lab asset)"""
    page = c.get(f'/{prefix}/')
    build = 'lab' if 'LAB BUILD' in page.text else 'public' if 'PUBLIC BUILD' in page.text else page.status_code
    return build, c.get(f'/{prefix}/lab/assets/index-lab01.js').status_code


def test_on_the_beta_with_the_switch_off_the_owner_gets_the_lab_build_and_a_visitor_the_public_one(settings, store,
                                                                                                  built):
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        for prefix, _ in LAB_APPS:
            assert served(c, prefix) == ('public', 404), prefix
        login(c)
        for prefix, csp in LAB_APPS:
            assert served(c, prefix) == ('lab', 200), prefix
            asset = c.get(f'/{prefix}/lab/assets/index-lab01.js')
            assert asset.headers['cache-control'] == 'private, max-age=31536000, immutable'
            assert asset.headers['content-security-policy'] == csp
            assert c.get(f'/{prefix}/lab/assets/..%2F..%2Fapp%2Fmain.py').status_code == 404
            assert c.get(f'/{prefix}/lab/assets/missing.js').status_code == 404
            assert c.get(f'/{prefix}/assets/index-public01.js').status_code == 200        # the public assets stay public
        assert served(c, 'screener-app') == ('public', 404)                             # a page without a lab build


def test_on_the_beta_with_the_switch_on_only_the_admin_past_the_second_factor_gets_the_lab_build(settings, store,
                                                                                               built):
    with TestClient(create_app(beta_on(settings), store, FakeOrc())) as c:
        assert [served(c, p) for p, _ in LAB_APPS] == [('public', 404)] * 2             # a visitor
        alice = paid_user(store, 'alice')
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': alice['username'], 'password': 'alice-password'})
        assert r.status_code == 200, r.text
        assert [served(c, p) for p, _ in LAB_APPS] == [('public', 404)] * 2             # a paid account
    with TestClient(create_app(beta_on(settings), store, FakeOrc())) as c:
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
        assert r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED', r.text
        assert [served(c, p) for p, _ in LAB_APPS] == [('public', 404)] * 2             # the second factor not passed
        sign_in_admin(c, store)
        assert [served(c, p) for p, _ in LAB_APPS] == [('lab', 200)] * 2


def with_lab(monkeypatch, item=None, tab=None):
    """The release file with one item (kind, id) or one tab at the lab stage, every other as it is."""
    items = [{'kind': k, 'id': e['id'], 'stage': releases.LAB if (k, e['id']) == item else e['stage']}
             for k in releases.KINDS for e in releases.entries(k)]
    tabs = [{'id': t, 'stage': releases.LAB if t == tab else st} for t, st in releases.CURRENT.tabs().items()]
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases({'schema_version': 1, 'items': items, 'tabs': tabs}))


def admin_access_account(c, store, name, overrides=()):
    """A paid account given admin.access by an override (no '*'), past the second factor."""
    user = paid_user(store, name)
    for key, value in (('admin.access', 'true'), *overrides):
        override(store, user['user_id'], key, value)
    r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': name, 'password': f'{name}-password'})
    assert r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED', r.text
    db(store, '''UPDATE edge_bff.sessions s SET mfa_passed_at = now() FROM edge_bff.users u
                 WHERE s.user_id = u.user_id AND u.username = %s AND s.revoked_at IS NULL''', name)
    caps = c.get('/api/v1/auth/session').json()['access']['capabilities']
    assert 'admin.access' in caps and '*' not in caps, caps
    return user


@pytest.mark.parametrize('kind', [k for k in releases.KINDS if releases.entries(k)])
def test_with_the_switch_on_the_lab_build_goes_only_to_the_admin_holding_every_item(settings, store, built, monkeypatch,
                                                                                   kind):
    """CS-1 (3f checker round 2): the lab build carries every item, so admin.access alone does not open it: the admin
    must hold every item of every kind, as the catalogs decide (catalog.holds_every_item)."""
    item = releases.entries(kind)[0]['id']
    with_lab(monkeypatch, item=(kind, item))
    with TestClient(create_app(beta_on(settings), store, FakeOrc())) as c:
        user = admin_access_account(c, store, f'ops_{kind}')
        listed = [e['id'] for e in c.get(f'/api/v1/catalog/{kind}').json()['entries']]
        assert item not in listed                                                   # the catalogs hide the lab item
        assert [served(c, p) for p, _ in LAB_APPS] == [('public', 404)] * 2         # and so does the page
        others = sorted({f for k in releases.KINDS if k != kind for f in releases.FAMILIES_OF_KIND[k]})
        for family in others:
            override(store, user['user_id'], family, json.dumps({'all': True}))       # every item of every other kind
        assert item not in [e['id'] for e in c.get(f'/api/v1/catalog/{kind}').json()['entries']]
        assert [served(c, p) for p, _ in LAB_APPS] == [('public', 404)] * 2
        for family in releases.FAMILIES_OF_KIND[kind]:
            override(store, user['user_id'], family, json.dumps({'all': True}))       # and every item of this kind
        assert item in [e['id'] for e in c.get(f'/api/v1/catalog/{kind}').json()['entries']]
        assert [served(c, p) for p, _ in LAB_APPS] == [('lab', 200)] * 2
    with TestClient(create_app(beta_on(settings), store, FakeOrc())) as c:
        sign_in_admin(c, store)                                                     # user #1, '*'
        assert [served(c, p) for p, _ in LAB_APPS] == [('lab', 200)] * 2


def test_on_the_live_site_nobody_gets_a_lab_build(settings, store, built):
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:
        assert [served(c, p) for p, _ in LAB_APPS] == [('public', 404)] * 2
        sign_in_admin(c, store)
        assert [served(c, p) for p, _ in LAB_APPS] == [('public', 404)] * 2             # '*' included


def tab_statuses(c, prefix):
    return c.get(f'/{prefix}/').status_code, c.get(f'/{prefix}/assets/index-public01.js').status_code


def test_every_tab_of_the_release_file_is_a_page_or_a_capability_domain(database):
    """The release file's tabs: each a page (PAGE_TABS, served at /<tab>-app/) or the first part of a capability key
    (the live switch of a page-less domain, e.g. support); never a name nothing reads. The pages are those main.py
    serves, so the lab-page test below covers every one of them."""
    import psycopg
    with psycopg.connect(database) as c:
        domains = {r[0] for r in c.execute("SELECT DISTINCT split_part(capability_key, '.', 1) FROM edge_bff.capabilities "
                                           "WHERE capability_key <> '*'")}
    assert PAGE_TABS >= {'terminal', 'backtest', 'screener'} and 'support' in domains - PAGE_TABS, (PAGE_TABS, domains)
    stray = sorted(t for t in releases.CURRENT.tabs() if t not in PAGE_TABS and t not in domains)
    assert not stray, f'{stray} in catalog/releases.json "tabs" is neither a page of main.py nor a capability domain'


@pytest.mark.parametrize('tab', sorted(t for t in releases.CURRENT.tabs() if t in PAGE_TABS))
def test_a_tab_at_the_lab_stage_is_served_to_the_admin_on_the_beta_only(settings, store, built, monkeypatch, tab):
    tabs = [{'id': t, 'stage': releases.LAB if t == tab else st} for t, st in releases.CURRENT.tabs().items()]
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases({'schema_version': 1, 'items': [
        {'kind': k, 'id': e['id'], 'stage': e['stage']} for k in releases.KINDS for e in releases.entries(k)], 'tabs': tabs}))
    prefix = f'{tab}-app'
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        assert tab_statuses(c, prefix) == (404, 404)                                    # a visitor
        others = [t for t in releases.CURRENT.tabs() if t != tab and t in PAGE_TABS]
        assert all(c.get(f'/{t}-app/').status_code == 200 for t in others)              # the released tabs as before
        login(c)
        assert tab_statuses(c, prefix) == (200, 200)
        asset = c.get(f'/{prefix}/assets/index-public01.js')
        assert asset.headers['cache-control'] == 'private, max-age=31536000, immutable'   # 3f checker SERVE-1
    # the switch on (3f checker TR-8): a paid account and the admin before the second factor are not the admin
    with TestClient(create_app(beta_on(settings), store, FakeOrc())) as c:
        alice = paid_user(store, f'alice_{tab}')
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': alice['username'], 'password': f'alice_{tab}-password'})
        assert r.status_code == 200, r.text
        assert tab_statuses(c, prefix) == (404, 404)
    with TestClient(create_app(beta_on(settings), store, FakeOrc())) as c:
        # CS-1: admin.access without the tab's own <tab>.view is not served the tab; with it, it is
        user = admin_access_account(c, store, f'ops_{tab}', ((f'{tab}.view', 'false'),))
        assert tab_statuses(c, prefix) == (404, 404)
        db(store, 'DELETE FROM edge_bff.user_capability_overrides WHERE user_id = %s AND capability_key = %s',
           user['user_id'], f'{tab}.view')                                         # the plan's own <tab>.view again
        assert tab_statuses(c, prefix) == (200, 200)
    with TestClient(create_app(beta_on(settings), store, FakeOrc())) as c:
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
        assert r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED', r.text
        assert tab_statuses(c, prefix) == (404, 404)
        sign_in_admin(c, store)
        assert tab_statuses(c, prefix) == (200, 200)
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:
        sign_in_admin(c, store)
        assert tab_statuses(c, prefix) == (404, 404)


@pytest.mark.parametrize('prefix', [p for p, _ in LAB_APPS])
def test_a_lab_tab_with_a_lab_build_needs_the_tab_and_every_item(settings, store, built, monkeypatch, prefix):
    """CS-1: a lab tab that has a lab build: its lab files need the tab's own <tab>.view as its page does, whatever
    items the admin holds."""
    tab = prefix.removesuffix('-app')
    with_lab(monkeypatch, tab=tab)
    every = sorted({f for k in releases.KINDS for f in releases.FAMILIES_OF_KIND[k]})
    with TestClient(create_app(beta_on(settings), store, FakeOrc())) as c:
        admin_access_account(c, store, f'opsl_{tab}', ((f'{tab}.view', 'false'),
                                                       *((f, json.dumps({'all': True})) for f in every)))
        assert served(c, prefix) == (404, 404)
        db(store, 'DELETE FROM edge_bff.user_capability_overrides WHERE capability_key = %s', f'{tab}.view')
        assert served(c, prefix) == ('lab', 200)


def test_on_the_live_site_even_a_principal_holding_admin_access_gets_no_lab_code(settings, store, built, monkeypatch):
    """3f round 2 (TRC2-7): on the live site no principal holds admin.access, and none holds a lab tab's own keys
    (principal.live_view, beta_only), so the test above cannot tell which guard holds. Here the principal is let hold
    every capability: the lab build stays out (auth.lab_admin's own check of the site, and holds_every, which never
    holds there), and so does every lab tab, which only auth.lab_admin's own check of the site then keeps out."""
    from app import principal
    monkeypatch.setattr(principal.Principal, 'can', lambda self, cap: True)
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:
        sign_in_admin(c, store)
        assert [served(c, p) for p, _ in LAB_APPS] == [('public', 404)] * 2
        for tab in sorted(releases.CURRENT.tabs()):
            with_lab(monkeypatch, tab=tab)
            assert tab_statuses(c, f'{tab}-app') == (404, 404), tab


# the repository's builds (CI's edge-bff job builds every page first); the image puts the Backtest's under static/
# L11: the fixed-name file only a lab build holds, read from shared/release-filter.mjs (LAB_PROBE), the one place it is named
LAB_PROBE = re.search(r"export const LAB_PROBE = '([\w.-]+)';", (Path(main.__file__).parents[1] / 'shared' / 'release-filter.mjs')
                      .read_text(encoding='utf-8')).group(1)
REAL_BUILDS = {'TERMINAL_APP': (main.TERMINAL_APP,), 'TERMINAL_LAB_APP': (main.TERMINAL_LAB_APP,),
               'BACKTEST_APP': (main.BACKTEST_APP, main.STATIC.parent / 'backtest' / 'dist'),
               'BACKTEST_LAB_APP': (main.BACKTEST_LAB_APP, main.STATIC.parent / 'backtest' / 'dist-lab')}


def named(c, prefix, text):
    """Every page path under /<prefix>/ the text names, and those the scripts it names name in turn (the Web Worker)."""
    found, todo = set(), [text]
    while todo:
        for ref in re.findall(rf"""["'`(](/{prefix}/[^"'`)\s]*)""", todo.pop()):
            if ref not in found:
                found.add(ref)
                r = c.get(ref)
                if r.status_code == 200 and ref.endswith('.js'):
                    todo.append(r.text)
    return sorted(found)


def test_the_real_lab_builds_are_served_whole_to_the_owner_and_not_at_all_to_a_visitor(settings, store, monkeypatch):
    """3f round 2 (CRIT-2): stand-in files cannot show that a lab page loads its own files. With the repository's builds:
    the owner's page is the lab build, every file it names (its script, its style, the Web Worker its script starts) is
    under /<app>/lab/assets/ and answers 200, cached privately; a visitor's page is the public build, every file it names
    answers 200, and each lab file answers 404."""
    for name, places in REAL_BUILDS.items():
        folder = next((f for f in places if (f / 'index.html').is_file() and (f / 'assets').is_dir()), None)
        if folder is None:
            missing(f'{name}: not built ({", ".join(str(f) for f in places)}; npm run build in the page)')
        monkeypatch.setattr(main, name, folder)
    pages = (('terminal-app', 'TERMINAL_APP', 'TERMINAL_LAB_APP'), ('backtest-app', 'BACKTEST_APP', 'BACKTEST_LAB_APP'))
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        lab_files = {}
        for prefix, public, lab in pages:
            page = c.get(f'/{prefix}/')
            assert page.text == (getattr(main, public) / 'index.html').read_text(), prefix      # the public build
            files = named(c, prefix, page.text)
            assert files and all(f.startswith(f'/{prefix}/assets/') and c.get(f).status_code == 200 for f in files), files
            lab_files[prefix] = [f'/{prefix}/lab/assets/{p.name}' for p in (getattr(main, lab) / 'assets').iterdir()]
            assert lab_files[prefix] and all(c.get(f).status_code == 404 for f in lab_files[prefix]), prefix
            # L11: the fixed-name probe only a lab build holds (shared/release-filter.mjs labProbe); the live smoke asks
            # for exactly this name
            assert (getattr(main, lab) / 'assets' / LAB_PROBE).is_file(), f'{prefix}: the lab build has no {LAB_PROBE}'
            assert not (getattr(main, public) / 'assets' / LAB_PROBE).exists(), f'{prefix}: the public build has the probe'
            assert c.get(f'/{prefix}/lab/assets/{LAB_PROBE}').status_code == 404, prefix
        login(c)
        for prefix, public, lab in pages:
            page = c.get(f'/{prefix}/')
            assert page.text == (getattr(main, lab) / 'index.html').read_text(), prefix         # the lab build
            files = named(c, prefix, page.text)
            assert any(f.endswith('.js') and 'worker' in f for f in files), files               # its Web Worker too
            probe = c.get(f'/{prefix}/lab/assets/{LAB_PROBE}')                                  # L11: the owner's 200
            assert probe.status_code == 200 and b'lab build probe' in probe.content, (prefix, probe.status_code)
            for f in files:
                r = c.get(f)
                assert f.startswith(f'/{prefix}/lab/assets/') and r.status_code == 200, (f, r.status_code)
                assert r.headers['cache-control'] == 'private, max-age=31536000, immutable', f


def test_an_ended_session_and_the_old_cookie_name_get_what_signed_in_would(settings, store, built):
    """3f checker SERVE-5: lab_admin reads the session as every route does: an ended session is no session (the
    public build), and the switch-off owner's session under the cookie name from before __Host- is still the owner's."""
    import secrets
    from app.security import token_hash
    from test_fix_plans import https_app
    token = secrets.token_hex(32)
    store.session_create(token_hash(token), settings.owner, settings.session_seconds)
    with TestClient(https_app(settings, store), base_url='https://testserver') as c:
        page = c.get('/terminal-app/', headers={'cookie': f'edge_session={token}'})
        assert 'LAB BUILD' in page.text, page.text
    with store.connect() as conn:
        conn.execute('UPDATE edge_bff.sessions SET revoked_at = now() WHERE token_hash = %s', (token_hash(token),))
    with TestClient(https_app(settings, store), base_url='https://testserver') as c:
        page = c.get('/terminal-app/', headers={'cookie': f'__Host-edge_session={token}'})
        assert 'PUBLIC BUILD' in page.text
        assert c.get('/terminal-app/lab/assets/index-lab01.js', headers={'cookie': f'__Host-edge_session={token}'}).status_code == 404


def test_a_lab_build_without_its_assets_is_not_served(settings, store, built, tmp_path, monkeypatch):
    """3f checker SERVE-8: a lab folder with an index but no assets (a broken build) leaves the admin on the public
    build, not on a page whose files all answer 404."""
    half = tmp_path / 'half'
    half.mkdir()
    (half / 'index.html').write_text('<!doctype html><title>LAB BUILD</title>')
    monkeypatch.setattr(main, 'TERMINAL_LAB_APP', half)
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        login(c)
        assert served(c, 'terminal-app') == ('public', 404)


def test_sign_out_clears_the_browsers_cache_of_this_site(settings, store):
    """3f checker SERVE-2: a lab build's files stayed in the admin's private browser cache after sign-out. The sign-out
    answer now asks the browser to clear this site's cache (Clear-Site-Data "cache"), not its storage."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    from conftest import FakeOrc
    from test_edge import login
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        h = login(c)
        r = c.post('/api/v1/auth/sign-out', headers=h, json={})
        assert r.status_code == 200 and r.headers.get('clear-site-data') == '"cache"', r.headers


def test_every_route_that_ends_this_browsers_session_clears_its_cache_and_a_password_change_does_not(on, store):
    """Its test-out (wf_c72ae04c-a73, terminal-shell SERVE-2): POST /api/v1/auth/sign-out-all ended this browser's
    session and deleted its cookie without Clear-Site-Data. Every route that ends this browser's session asks for it
    (auth_flows.ended_here): sign-out, sign-out everywhere, a finished password reset. A password change keeps this
    browser's session (its other sessions end), so it does not; nor does an admin action, which never targets the
    admin's own account (admin.py OWN)."""
    from fastapi.testclient import TestClient
    from app.main import create_app
    from conftest import FakeOrc
    from test_auth_flows import PASSWORD, cooldown_over, last_code, make_account
    from test_edge import ORIGIN
    application = create_app(on, store, FakeOrc())
    application.state.auth_flows.pwned_fetch = lambda prefix: ''
    with TestClient(application) as c:
        h = {**ORIGIN, 'X-CSRF-Token': make_account(c, store).json()['csrf_token']}
        changed = c.post('/api/v1/auth/password/change', headers=h, json={
            'current_password': PASSWORD, 'password': 'another password', 'password_repeat': 'another password'})
        assert changed.json() == {'status': 'PASSWORD_CHANGED'} and 'clear-site-data' not in changed.headers
        everywhere = c.post('/api/v1/auth/sign-out-all', headers=h)
        assert everywhere.json() == {'authenticated': False} and everywhere.headers.get('clear-site-data') == '"cache"'
        h = {**ORIGIN, 'X-CSRF-Token': c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={
            'login': 'ana_putri', 'password': 'another password'}).json()['csrf_token']}
        out = c.post('/api/v1/auth/sign-out', headers=h, json={})
        assert out.status_code == 200 and out.headers.get('clear-site-data') == '"cache"'
        cooldown_over(store)
        assert c.post('/api/v1/auth/password/forgot', headers=ORIGIN, json={'email': 'ana@example.com'}).status_code == 202
        reset = c.post('/api/v1/auth/password/reset', headers=ORIGIN, json={
            'email': 'ana@example.com', 'code': last_code(store, 'ana@example.com'), 'password': 'a third password',
            'password_repeat': 'a third password'})
        assert reset.json() == {'next': 'sign_in'} and reset.headers.get('clear-site-data') == '"cache"'
