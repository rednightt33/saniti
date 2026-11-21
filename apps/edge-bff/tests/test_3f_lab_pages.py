"""3f (EXEC option A item 4; CONTRACT.md 8 "Lab code"): who is served a page's lab build and a lab tab.

- The Terminal and Backtest pages have a lab build (every item, the lab formulas). edge-bff serves it from /<app>/ to the
  admin on the beta only (auth.lab_viewer: admin.access and the second factor passed); its assets answer under
  /<app>/lab/assets/ to that admin only, cached privately. Everyone else, and everyone on the live site, gets the public
  build, and the lab assets answer 404.
- A tab at the lab stage (releases.tab_stage) is served to the admin on the beta only; its page and assets answer 404 to
  everyone else and on the live site. The tabs are read from the release file, each switched to lab in turn.
"""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import main, releases
from app.main import create_app
from conftest import FakeOrc
from test_beta_live_site import live_of, sign_in_admin
from test_edge import ORIGIN, login
from test_phase3a_gates import paid_user

LAB_APPS = (('terminal-app', main.TERMINAL_CSP), ('backtest-app', main.BACKTEST_CSP))


def beta_on(settings):
    return dataclasses.replace(live_of(settings), site='beta', orc_url=settings.orc_url, orc_key=settings.orc_key)


@pytest.fixture
def built(tmp_path, monkeypatch):
    """Every page's public build, and the Terminal's and Backtest's lab builds, as small stand-ins."""
    for name, title in (('public', 'PUBLIC BUILD'), ('lab', 'LAB BUILD')):
        (tmp_path / name / 'assets').mkdir(parents=True)
        (tmp_path / name / 'index.html').write_text(f'<!doctype html><title>{title}</title>')
        (tmp_path / name / 'assets' / f'index-{name}01.js').write_text('void 0')
    for app in ('TERMINAL', 'BACKTEST', 'SCREENER', 'RADAR', 'OVERVIEW', 'WATCHLIST'):
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


def test_on_the_live_site_nobody_gets_a_lab_build(settings, store, built):
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:
        assert [served(c, p) for p, _ in LAB_APPS] == [('public', 404)] * 2
        sign_in_admin(c, store)
        assert [served(c, p) for p, _ in LAB_APPS] == [('public', 404)] * 2             # '*' included


def tab_statuses(c, prefix):
    return c.get(f'/{prefix}/').status_code, c.get(f'/{prefix}/assets/index-public01.js').status_code


@pytest.mark.parametrize('tab', sorted(releases.CURRENT.tabs()))
def test_a_tab_at_the_lab_stage_is_served_to_the_admin_on_the_beta_only(settings, store, built, monkeypatch, tab):
    tabs = [{'id': t, 'stage': releases.LAB if t == tab else st} for t, st in releases.CURRENT.tabs().items()]
    monkeypatch.setattr(releases, 'CURRENT', releases.Releases({'schema_version': 1, 'items': [
        {'kind': k, 'id': e['id'], 'stage': e['stage']} for k in releases.KINDS for e in releases.entries(k)], 'tabs': tabs}))
    prefix = f'{tab}-app'
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        assert tab_statuses(c, prefix) == (404, 404)                                    # a visitor
        others = [t for t in releases.CURRENT.tabs() if t != tab]
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
        r = c.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'owner', 'password': 'local-test-password'})
        assert r.status_code == 403 and r.json()['error']['code'] == 'MFA_REQUIRED', r.text
        assert tab_statuses(c, prefix) == (404, 404)
        sign_in_admin(c, store)
        assert tab_statuses(c, prefix) == (200, 200)
    with TestClient(create_app(live_of(settings), store, FakeOrc())) as c:
        sign_in_admin(c, store)
        assert tab_statuses(c, prefix) == (404, 404)


def test_an_ended_session_and_the_old_cookie_name_get_what_signed_in_would(settings, store, built):
    """3f checker SERVE-5: lab_viewer reads the session as every route does: an ended session is no session (the
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
