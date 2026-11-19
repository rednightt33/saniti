"""EXEC-MU-ACCOUNTS fix round, track "plans" (the re-check of Phases 0-3b, findings R1-* and R2-* named per test): the
tests the fix round adds beside the re-check's own failing tests, which are the acceptance of each finding."""
from fastapi.testclient import TestClient

from app import preferences
from app.main import create_app
from conftest import FakeOrc
from test_principal import db, on, sign_in, workers  # noqa: F401 (fixtures)
from test_phase3a_gates import override, paid_user
from test_auth_pages import page  # noqa: F401 (fixture)
from test_auth_pages_live import live  # noqa: F401 (fixture)


def test_every_preference_capability_is_a_flag_of_the_catalog(store):
    """R1-18: the capability a sync key needs (catalog/storage_sync.json, from the registry) is a flag the plan catalog
    defines, so no key can name a capability nobody can hold."""
    named = {cap for cap in preferences.CAPABILITY_OF.values() if cap}
    rows = db(store, 'SELECT capability_key, kind FROM edge_bff.capabilities WHERE capability_key = ANY(%s)', list(named))
    assert {r['capability_key']: r['kind'] for r in rows} == {cap: 'flag' for cap in named}


def test_a_preference_of_a_tab_the_plan_holds_is_served_and_one_of_a_shared_key_always(on, store):
    """R1-18: a paid plan without the Watchlist keeps its Terminal and shared preferences; only the Watchlist's key is
    left out and refused, and its row is kept (D5: back when the plan holds the tab again)."""
    with TestClient(create_app(on, store, FakeOrc())) as c:
        paula = paid_user(store, 'paula')
        h = sign_in(c, 'paula', 'paula-password')
        for key in ('ml.symbol', 'ml.tf', 'edge.watchlist.view'):
            assert c.put(f'/api/v1/preferences/{key}', headers=h, json={'value': 'x', 'version': None}).status_code == 201
        override(store, paula['user_id'], 'watchlist.view', 'false')
        held = set(c.get('/api/v1/preferences').json()['preferences'])
        assert held == {'ml.symbol', 'ml.tf'}
        refused = c.put('/api/v1/preferences/edge.watchlist.view', headers=h, json={'value': 'y', 'version': 1})
        assert refused.status_code == 403 and refused.json()['error']['code'] == 'CAPABILITY_REQUIRED'
        assert refused.json()['error']['details']['capability'] == 'watchlist.view'
        assert db(store, 'SELECT value FROM edge_bff.user_preferences WHERE pref_key = %s', 'edge.watchlist.view')[0]['value'] == 'x'
        db(store, 'DELETE FROM edge_bff.user_capability_overrides WHERE user_id = %s', paula['user_id'])
        assert 'edge.watchlist.view' in c.get('/api/v1/preferences').json()['preferences']


# ---- R2-21, R2-22, R2-19: transport and cookie protections on an https origin ---------------------------------------

def https_app(settings, store, **kw):
    import dataclasses
    return create_app(dataclasses.replace(settings, origin='https://testserver', secure_cookie=True, **kw), store, FakeOrc())


def test_an_https_origin_sends_hsts_and_a_host_only_session_cookie(settings, store):
    """R2-21: every answer of an https origin carries Strict-Transport-Security (host only, no preload); an http origin
    none. R2-22: the session cookie is __Host-edge_session (Secure, Path=/, no Domain); the policy has form-action."""
    with TestClient(https_app(settings, store), base_url='https://testserver') as c:
        login = c.get('/login')
        assert login.headers['strict-transport-security'] == 'max-age=31536000'
        assert "form-action 'self'" in login.headers['content-security-policy']
        signed = c.post('/api/v1/auth/sign-in', headers={'origin': 'https://testserver'},
                        json={'login': 'owner', 'password': 'local-test-password'})
        assert signed.status_code == 200, signed.text
        cookie = signed.headers['set-cookie']
        assert cookie.startswith('__Host-edge_session=') and 'Secure' in cookie and 'Path=/' in cookie
        assert 'Domain' not in cookie
        assert c.get('/api/v1/auth/session').status_code == 200
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        assert 'strict-transport-security' not in c.get('/login').headers


def test_the_switch_off_owners_session_moves_to_the_new_cookie_name_once(settings, store):
    """R2-22: the configured owner signed in before the __Host- name (cookie edge_session) is not signed out: its next
    answer sets the session under __Host-edge_session and removes the old name. With the switch on the old name is
    never read (a cookie another host set under it is no session)."""
    import secrets
    from app.security import token_hash
    token = secrets.token_hex(32)
    store.session_create(token_hash(token), settings.owner, settings.session_seconds)
    with TestClient(https_app(settings, store), base_url='https://testserver') as c:
        moved = c.get('/api/v1/auth/session', headers={'cookie': f'edge_session={token}'})
        assert moved.status_code == 200, moved.text
        headers = moved.headers.get_list('set-cookie')
        assert any(h.startswith(f'__Host-edge_session={token}') and 'Secure' in h for h in headers), headers
        assert any(h.startswith('edge_session=') and 'Max-Age=0' in h for h in headers), headers
    with TestClient(https_app(settings, store, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40),
                    base_url='https://testserver') as c:
        assert c.get('/api/v1/auth/session', headers={'cookie': f'edge_session={token}'}).status_code == 401


# ---- R2-20: the password change and sign-out everywhere have a page ------------------------------------------------

def test_the_account_menu_changes_the_password_and_signs_out_everywhere(live, page):
    """R2-20 (CONTRACT.md section 4): with accounts on, the account menu opens "Password and sign-in": a password
    change keeps this session and ends the account's others; "Sign out everywhere" ends them all and shows sign-in."""
    import secrets
    from app.security import token_hash
    on, store = live
    paid_user(store, 'paula')
    other = secrets.token_hex(32)                           # the account's session on another device
    page.goto(on.origin + '/login')
    page.get_by_label('Login', exact=True).fill('paula')
    page.get_by_label('Password', exact=True).fill('paula-password')
    page.get_by_role('button', name='Sign In').click()
    page.wait_for_function("() => window.Edge && Edge.auth !== null && ['/monitor', '/terminal'].includes(location.pathname)")
    uid = db(store, "SELECT user_id FROM edge_bff.users WHERE username = 'paula'")[0]['user_id']
    db(store, "INSERT INTO edge_bff.sessions(token_hash, owner_key, user_id, expires_at) SELECT %s, owner_key, user_id, "
              "now() + interval '1 day' FROM edge_bff.users WHERE user_id = %s", token_hash(other), uid)
    page.get_by_role('button', name='Account menu').first.click()
    page.get_by_role('menuitem', name='Password and sign-in').click()
    page.get_by_label('Current password', exact=True).fill('paula-password')
    page.get_by_label('New password', exact=True).fill('a new long password')
    page.get_by_label('Repeat new password', exact=True).fill('a new long password')
    page.get_by_role('button', name='Change password').click()
    page.get_by_role('status').filter(has_text='Your password was changed').wait_for()
    assert db(store, 'SELECT revoked_at FROM edge_bff.sessions WHERE token_hash = %s', token_hash(other))[0]['revoked_at']
    assert page.evaluate("() => fetch('/api/v1/auth/session').then(r => r.status)") == 200
    page.get_by_role('button', name='Sign out everywhere').click()
    page.get_by_label('Login', exact=True).wait_for()
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.sessions WHERE user_id = %s AND revoked_at IS NULL', uid)[0]['n'] == 0


# ---- R2-18: one rule for a person's name, and one for showing it ----------------------------------------------------

def test_a_name_is_stored_as_nfc_text_without_hidden_control_or_markup_characters():
    """R2-18: registration stores a name in NFC with single spaces; a bidi override, a zero-width space, a control
    character or < > is refused with a sentence; the joiners some scripts need are kept; an exported cell never starts
    a formula."""
    from app.text_rules import export_cell, person_name
    assert person_name('  Ana   Putri ') == ('Ana Putri', '')
    assert person_name('cafe\u0301')[0] == 'caf\u00e9'                                  # NFC, never NFKC
    assert person_name('\u0915\u094d\u200d\u0937') == ('\u0915\u094d\u200d\u0937', '')    # a joiner of a script stays
    assert person_name('Ana\u2028Putri') == ('Ana Putri', '')          # a line separator is white space: one space
    for bad in ('Ana\u202eimda', 'A\u200bna', 'Ana\x07', '<b>Ana</b>', '', 'x' * 101):
        name, problem = person_name(bad)
        assert problem and ' ' in problem, bad
    assert [export_cell(v) for v in ('=1+1', '+62', '-x', '@a', 'Ana')] == ["'=1+1", "'+62", "'-x", "'@a", 'Ana']


def test_registration_refuses_a_name_with_a_bidi_override(settings, store):
    """R2-18 at the route: the field and the sentence say what to change."""
    import dataclasses
    on = dataclasses.replace(settings, multiuser=True, code_secret='c' * 40, mfa_key='m' * 40)
    application = create_app(on, store, FakeOrc())
    application.state.auth_flows.pwned_fetch = lambda prefix: ''
    with TestClient(application) as c:
        r = c.post('/api/v1/auth/register', headers={'origin': 'http://testserver'}, json={
            'username': 'ana_putri', 'first_name': 'Ana\u202eimda', 'last_name': 'Putri', 'email': 'ana@example.com',
            'phone': '0812 3456 7890', 'password': 'a long enough password', 'password_repeat': 'a long enough password'})
        assert r.status_code in (400, 422), r.text
        error = r.json()['error']
        assert error['code'] == 'INVALID_INPUT' and 'first_name' in error['details']['fields'], r.text


# ---- R2-19: the shell runs no inline script ------------------------------------------------------------------------

def test_the_shell_has_no_inline_script_and_its_policy_no_unsafe_inline_script(settings, store):
    """R2-19: the shell's scripts are files (static/edge-boot.js, static/edge-app.js and the others), so its policy is
    script-src 'self' with no 'unsafe-inline'; an injected inline script or handler cannot run."""
    import re
    from pathlib import Path
    html = (Path(__file__).resolve().parents[1] / 'static' / 'index.html').read_text()
    assert not re.search(r'<script(?![^>]*\bsrc=)[^>]*>', html), 'an inline <script> in static/index.html'
    assert not re.search(r'\son[a-z]+\s*=\s*["\']', html), 'an inline event handler attribute in static/index.html'
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        for path in ('/', '/login', '/monitor'):
            policy = c.get(path).headers['content-security-policy']
            script = next(d for d in policy.split(';') if d.strip().startswith('script-src'))
            assert script.strip() == "script-src 'self'" and "form-action 'self'" in policy, policy
        for name in ('edge-boot.js', 'edge-app.js'):
            assert c.get('/' + name).status_code == 200, name
