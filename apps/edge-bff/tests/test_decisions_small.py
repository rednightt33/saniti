"""EXEC-MU-ACCOUNTS fix round, track decisions (verification/edge_multiuser/fix_round/decisions.md): the user's small
decisions of 2026-11-19 and the main agent's design value, built.

- Retention ("Decisions from the fix round" item 2, user: "a"): every sent, failed, expired or suppressed outbox row of
  every address goes 30 days after it was made (an address with no account after 24 h, as before, R2-24), with the used
  email codes and the handled webhook deliveries; a live code, an unsent row and a suppression are kept. The hourly
  housekeeping makes it as the production login (edge_bff_runtime's grants, no DELETE on the outbox or the deliveries).
- MFA re-enrolment (the main agent's design value, EXEC "Decisions after the fix round"): starting a new authenticator
  beside a confirmed one needs a second factor passed within MFA_RECENT_SECONDS (10 minutes); an older pass is answered
  403 MFA_REQUIRED with details.recent_s, and a fresh code (POST /api/v1/auth/mfa/verify) opens it again.
- ERRORS M260 (the user's go, "a"): a terminal-api 2xx JSON answer reaches a page only through client.public_data, in
  terminal_access.relayed. The walk derives the routes from the app (every route holding terminal_access.guard) and
  each kind of proxy path from main.TERMINAL_ROUTES, plants private keys and an internal address in every answer, and
  finds none on any page; its self-test finds them once the filter is taken out.
- R1-35 (the user's "1a"): the universe attributes every Screener answer shows (the Screener catalog's entries naming
  their /universe row field) are allowed to every principal (allow.allow_of) and listed by its catalog (catalog.held),
  by one rule (catalog.ungated), as the worker no longer gates them by id.
"""
import dataclasses
import json
import re
import uuid
from urllib.parse import urlsplit, urlunsplit

import httpx
import psycopg
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import catalog, main, mfa, releases, terminal_access
from app.accounts import EMAIL_RETENTION_DAYS
from app.allow import allow_of
from app.auth_flows import MFA_RECENT_SECONDS
from app.errors import words
from app.main import create_app
from app.principal import account_principal
from app.store import PURGE_BATCH, PURGES, Store
from conftest import FakeOrc
from test_answer_view import fixture_server  # noqa: F401 - the fixture
from test_auth_flows import admin_sign_in, app, db, error_code, on, outbox  # noqa: F401 - the fixtures
from test_auth_pages import answer, page  # noqa: F401 - the fixture
from test_edge import ORIGIN, login
from test_terminal_access import KEY, PAGE, PAGE_SHA, URL, FakeApi, dependency_calls


@pytest.fixture
def runtime_store(database):
    """The store as production runs it: a login holding only edge_bff_runtime's grants (as test_r2_life.py)."""
    name = 'dec_small_' + uuid.uuid4().hex[:8]
    with psycopg.connect(database, autocommit=True) as c:
        c.execute(f'CREATE ROLE "{name}" LOGIN INHERIT IN ROLE edge_bff_runtime')
    p = urlsplit(database)
    s = Store(urlunsplit((p.scheme, f'{name}@{p.hostname}:{p.port}', p.path, p.query, p.fragment)))
    try:
        yield s
    finally:
        s.close()
        with psycopg.connect(database, autocommit=True) as c:
            c.execute(f'DROP ROLE "{name}"')


# ---- retention: 30 days ------------------------------------------------------------------------------------------------

def account(store, email):
    return db(store, "INSERT INTO edge_bff.users(owner_key, username, email, status) VALUES ('u_' || %s, %s, %s, 'active') "
                     "RETURNING user_id", uuid.uuid4().hex[:24], 'u' + uuid.uuid4().hex[:12], email)[0]['user_id']


def mail(store, key, to, status, days):
    db(store, "INSERT INTO edge_bff.email_outbox(idempotency_key, purpose, to_email, status, sent_at, created_at) "
              "VALUES (%s, 'reset', %s, %s, CASE WHEN %s = 'sent' THEN now() - make_interval(days => %s) END, "
              "now() - make_interval(days => %s))", key, to, status, status, days, days)


def code(store, user_id, purpose, days, consumed):
    """A code made `days` ago (its 300 s life ended then too), used at that time when `consumed`."""
    db(store, "INSERT INTO edge_bff.email_codes(purpose, user_id, code_hash, created_at, expires_at, consumed_at) "
              "VALUES (%s, %s, %s, now() - make_interval(days => %s), now() - make_interval(days => %s) + interval '300 seconds', "
              "CASE WHEN %s THEN now() - make_interval(days => %s) END)",
       purpose, user_id, uuid.uuid4().hex + uuid.uuid4().hex, days, days, consumed, days)


def test_outbox_rows_codes_and_deliveries_are_kept_30_days_then_purged_as_the_production_login(store, runtime_store):
    assert EMAIL_RETENTION_DAYS == 30
    older, younger = EMAIL_RETENTION_DAYS + 1, EMAIL_RETENTION_DAYS - 1
    ana = account(store, 'ana@example.com')
    for key, status, days in (('old-sent', 'sent', older), ('old-failed', 'failed', older), ('old-expired', 'expired', older),
                              ('old-suppressed', 'suppressed', older), ('young-sent', 'sent', younger),
                              ('old-pending', 'pending', older + 30), ('old-sending', 'sending', older)):
        mail(store, key, 'ana@example.com', status, days)
    mail(store, 'gone-day', 'gone@example.com', 'sent', 2)            # no account: after 24 h (R2-24), unchanged
    for purpose, days, consumed in (('reset', older, True), ('register', younger, True), ('email_change', older, False)):
        if purpose == 'email_change':
            db(store, "INSERT INTO edge_bff.email_codes(purpose, user_id, code_hash, target_email, created_at, expires_at) "
                      "VALUES ('email_change', %s, %s, 'new@example.com', now() - make_interval(days => %s), "
                      "now() - make_interval(days => %s) + interval '300 seconds')",
               ana, uuid.uuid4().hex * 2, days, days)
        else:
            code(store, ana, purpose, days, consumed)
    db(store, "INSERT INTO edge_bff.email_codes(purpose, user_id, code_hash, created_at, expires_at) "
              "VALUES ('reset', %s, %s, now(), now() + interval '300 seconds')", ana, 'f' * 64)        # live: kept
    for svix, days in (('msg_old', older), ('msg_young', younger)):
        db(store, "INSERT INTO edge_bff.email_hook_events(svix_id, event_type, received_at) "
                  "VALUES (%s, 'email.delivered', now() - make_interval(days => %s))", svix, days)
    db(store, "INSERT INTO edge_bff.email_suppression(email, reason, at) VALUES ('ana@example.com', 'bounce', "
              "now() - interval '400 days')")

    runtime_store.cleanup_sessions()                       # the hourly housekeeping, as edge_bff_runtime

    assert sorted(r['idempotency_key'] for r in outbox(store)) == ['old-pending', 'old-sending', 'young-sent']
    left = db(store, 'SELECT purpose, consumed_at IS NOT NULL AS used, expires_at > now() AS live FROM edge_bff.email_codes '
                     'ORDER BY code_id')
    assert left == [{'purpose': 'register', 'used': True, 'live': False}, {'purpose': 'reset', 'used': False, 'live': True}]
    assert [r['svix_id'] for r in db(store, 'SELECT svix_id FROM edge_bff.email_hook_events')] == ['msg_young']
    # a bounce or complaint stays: the address is not mailed again (CONTRACT section 10, "Account deletion")
    assert db(store, 'SELECT email, reason FROM edge_bff.email_suppression') == [{'email': 'ana@example.com', 'reason': 'bounce'}]


def test_the_retention_purges_are_housekeeping_entries_held_to_the_batch_bound(store):
    assert list(PURGES)[-3:] == ['outbox', 'codes', 'hook_events']
    ana = account(store, 'bo@example.com')
    for k in range(7):
        mail(store, f'k{k}', 'bo@example.com', 'sent', 40)
        code(store, ana, 'reset', 40, True)
        db(store, "INSERT INTO edge_bff.email_hook_events(svix_id, received_at) VALUES (%s, now() - interval '40 days')",
           f'msg_{k}')
    for name in ('outbox', 'codes', 'hook_events'):
        assert [store.purge(name, 3) for _ in range(4)] == [3, 3, 1, 0], name
    assert PURGE_BATCH >= 3


def test_the_runtime_still_cannot_delete_the_outbox_or_the_deliveries_itself(store):
    grants = db(store, '''SELECT t, has_table_privilege('edge_bff_runtime', 'edge_bff.' || t, 'DELETE') AS d
        FROM unnest(ARRAY['email_outbox', 'email_hook_events', 'email_codes']) t ORDER BY t''')
    assert grants == [{'t': 'email_codes', 'd': True}, {'t': 'email_hook_events', 'd': False}, {'t': 'email_outbox', 'd': False}]
    functions = db(store, '''SELECT p.proname, p.prosecdef, p.proconfig,
            has_function_privilege('edge_bff_runtime', p.oid, 'EXECUTE') AS runtime,
            has_function_privilege('public', p.oid, 'EXECUTE') AS public
        FROM pg_proc p WHERE p.pronamespace = 'edge_bff'::regnamespace AND p.proname LIKE 'purge_email_%%' ORDER BY 1''')
    assert [(f['proname'], f['prosecdef'], f['runtime'], f['public']) for f in functions] == [
        ('purge_email_hook_events', True, True, False), ('purge_email_outbox', True, True, False)]
    assert all(f['proconfig'] == ['search_path=pg_catalog, edge_bff'] for f in functions)


# ---- MFA: a new authenticator needs a recent second factor ---------------------------------------------------------------

def enrolled_admin(app, store, on):
    """The admin with a confirmed authenticator and a session that has just passed MFA: its headers, the secret, the
    page clock and the first enrolment's answer."""
    flows = app.app.state.auth_flows
    now = {'t': 1_800_000_000.0}
    flows.clock = lambda: now['t']
    h = admin_sign_in(app)
    first = app.post('/api/v1/auth/mfa/enroll', headers=h).json()
    secret = mfa.secret_of(on.mfa_key, *(lambda r: (r['user_id'], bytes(r['nonce'])))(
        db(store, 'SELECT user_id, nonce FROM edge_bff.mfa_totp')[0]))
    ok = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': mfa.code_at(secret, int(now['t']) // 30)})
    assert ok.status_code == 200 and ok.json()['access']['mfa_ok'] is True
    return {**ORIGIN, 'X-CSRF-Token': ok.json()['csrf_token']}, secret, now, first


def age_mfa_pass(store, seconds):
    db(store, 'UPDATE edge_bff.sessions SET mfa_passed_at = mfa_passed_at - make_interval(secs => %s) '
              'WHERE mfa_passed_at IS NOT NULL AND revoked_at IS NULL', seconds)


def test_a_new_authenticator_needs_a_second_factor_passed_within_ten_minutes(app, store, on):
    assert MFA_RECENT_SECONDS == 600
    h, secret, now, _ = enrolled_admin(app, store, on)
    # within the ten minutes: the waiting enrolment is made (R1-7), as the re-check's own test expects
    age_mfa_pass(store, MFA_RECENT_SECONDS - 60)
    assert app.post('/api/v1/auth/mfa/enroll', headers=h).status_code == 200
    waiting = db(store, 'SELECT pending_nonce FROM edge_bff.mfa_totp')[0]['pending_nonce']
    # past them: refused, and nothing of the waiting enrolment changes
    age_mfa_pass(store, 120)
    r = app.post('/api/v1/auth/mfa/enroll', headers=h)
    assert (r.status_code, error_code(r)) == (403, 'MFA_REQUIRED'), r.text
    assert r.json()['error']['details'] == {'mfa_enrolled': True, 'recent_s': MFA_RECENT_SECONDS}
    assert r.json()['error']['message'] == words('MFA_REQUIRED', 403, {'mfa_enrolled': True, 'recent_s': 600})
    assert '10 minutes' in r.json()['error']['message'] and 'authenticator' in r.json()['error']['message']
    assert db(store, 'SELECT pending_nonce FROM edge_bff.mfa_totp')[0]['pending_nonce'] == waiting
    # the session is still signed in and passed MFA (every other route works): only the set-up asks for a fresh code
    assert app.get('/api/v1/auth/session').json()['access']['mfa_ok'] is True
    # a fresh code from the current authenticator opens it again
    now['t'] += 30
    fresh = app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': mfa.code_at(secret, int(now['t']) // 30)})
    assert fresh.status_code == 200, fresh.text
    again = app.post('/api/v1/auth/mfa/enroll', headers={**ORIGIN, 'X-CSRF-Token': fresh.json()['csrf_token']})
    assert again.status_code == 200, again.text


def test_the_first_enrolment_needs_no_recent_pass(app, store, on):
    """CONTRACT 4: with no confirmed authenticator any session of the account sets one up (the admin enrols at
    switch-on), so the ten minutes apply only beside a confirmed one."""
    h = admin_sign_in(app)
    assert app.post('/api/v1/auth/mfa/enroll', headers=h).status_code == 200
    assert app.post('/api/v1/auth/mfa/enroll', headers=h).status_code == 200      # the candidate is replaced


def test_the_mfa_page_takes_a_fresh_code_then_starts_the_set_up_again(fixture_server, page):
    """The page side of the ten minutes: the refusal's own sentence is shown above the code form, and the code's
    success starts the set-up again instead of leaving the page."""
    origin, _ = fixture_server
    calls, enrol = [], {'n': 0}
    refused = {'error': {'code': 'MFA_REQUIRED', 'message': words('MFA_REQUIRED', 403, {'mfa_enrolled': True, 'recent_s': 600}),
                         'details': {'mfa_enrolled': True, 'recent_s': 600}}}
    codes = [f'code-{i:02d}' for i in range(10)]

    def enroll(route):
        enrol['n'] += 1
        calls.append('enroll')
        if enrol['n'] == 1:
            return answer(route, 403, refused)
        return answer(route, 200, {'otpauth_uri': 'otpauth://totp/EDGE:owner?secret=JBSWY3DPEHPK3PXP&issuer=EDGE',
                                   'recovery_codes': codes})
    page.route('**/api/v1/auth/sign-in', lambda r: answer(r, 403, {'error': {'code': 'MFA_REQUIRED', 'message': 'Enter your authenticator code.', 'details': {'csrf_token': 'pending-token'}}}))
    page.route('**/api/v1/auth/mfa/enroll', enroll)
    page.route('**/api/v1/auth/mfa/verify', lambda r: (calls.append('verify'), answer(r, 200, {'ok': True})))
    page.goto(origin + '/login')
    page.get_by_label('Login', exact=True).fill('owner')
    page.get_by_label('Password', exact=True).fill('local-test-password')
    page.get_by_role('button', name='Sign In').click()
    page.wait_for_function("() => location.pathname === '/mfa'")
    page.get_by_role('button', name='Set up an authenticator app').click()
    page.get_by_role('alert').wait_for()
    assert page.get_by_role('alert').inner_text() == refused['error']['message']
    page.get_by_label('Code', exact=True).fill('123456')
    page.get_by_role('button', name='Continue').click()
    page.locator('svg.auth-qr path').wait_for()
    assert page.locator('.auth-codes li').all_inner_texts() == codes and calls == ['enroll', 'verify', 'enroll']
    assert page.evaluate('location.pathname') == '/mfa'


# ---- ERRORS M260: public_data on every relay of terminal-api's JSON -----------------------------------------------------

PLANTED = 'planted-private-value-0123456789'
INTERNAL = 'http://terminal-api.railway.internal:8080/api/terminal/v1/state'
FAMILY_SAMPLE = {'radar': 'radar-days', 'overview': 'overview-meta', 'watchlist': 'watchlist-stocks'}


class Planted(FakeApi):
    """terminal-api answering every JSON call 2xx with what must never reach a page: private keys (client.PRIVATE_KEYS)
    beside the real fields, and an internal address in a string, at the top and nested."""

    def answer(self, method, url, content):
        if '/logo/' in url:
            return httpx.Response(200, content=b'<svg/>', headers={'content-type': 'image/svg+xml'})
        family = url.rsplit('/', 1)[1]
        if family in FAMILY_SAMPLE and method == 'GET':
            return httpx.Response(200, json={'finished_at': '2026-11-14T10:00:00Z', 'api_key': PLANTED, 'files': {
                FAMILY_SAMPLE[family]: {'sha256': PAGE_SHA, 'bytes': len(PAGE), 'token': PLANTED, 'note': INTERNAL}}})
        if family in FAMILY_SAMPLE:
            return httpx.Response(200, json={'files': [{'name': FAMILY_SAMPLE[family], 'url': 'https://bucket.example/f',
                                                        'sha256': PAGE_SHA, 'bytes': len(PAGE), 'token': PLANTED}]})
        return httpx.Response(200, json={'ticker': 'BBCA', 'ok': True, 'token': PLANTED, 'where': INTERNAL,
                                         'files': [{'name': 'x', 'reasoning': PLANTED, 'note': f'see {INTERNAL}'}]})


def guarded_routes(app):
    """Every route that calls terminal-api for a principal: the ones whose dependencies hold terminal_access.guard
    (derived from the app, as tests/test_terminal_access.py finds them)."""
    return [r for r in app.routes if isinstance(r, APIRoute)
            and any(getattr(call, 'terminal_guard', False) for call in dependency_calls(r.dependant))]


def top_alternatives(pattern):
    """The alternatives of a regex at its top level (a '|' inside a group belongs to the group)."""
    out, depth, part = [], 0, ''
    for ch in pattern:
        depth += {'(': 1, ')': -1}.get(ch, 0)
        if ch == '|' and depth == 0:
            out.append(part)
            part = ''
        else:
            part += ch
    return [*out, part]


def terminal_samples():
    """(method, path, body) for each kind of path the proxy forwards: one at least per alternative of
    main.TERMINAL_ROUTES, so a new kind of terminal-api route fails here until it has a sample."""
    gets = ['manifest/BBCA', 'reference/tickers', *[f'history/{d}' for d in terminal_access.HISTORY_DATASETS], 'logo/BBCA',
            *[f'cut/BBCA/{d}' for d in terminal_access.CUT_DATASETS], 'reference/tickers/cut']
    posts = {'files': {'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]}, 'bundle': {'ticker': 'BBCA', 'datasets': ['price']}}
    for method, samples in (('GET', gets), ('POST', list(posts))):
        assert all(main.TERMINAL_ROUTES[method].fullmatch(s) for s in samples), samples
        for alternative in top_alternatives(main.TERMINAL_ROUTES[method].pattern):
            assert any(re.fullmatch(alternative, s) for s in samples), f'{method} {alternative}: add a sample path'
    return [('GET', s, None) for s in gets] + [('POST', s, b) for s, b in posts.items()]


def walk(c, app, h):
    """Every guarded route called with each of its sample paths: [(route, path, answer)] of the calls that reached
    terminal-api."""
    out = []
    for route in guarded_routes(app):
        for method in sorted(route.methods):
            if route.path == '/api/terminal/v1/{path:path}':
                calls = [(m, f'/api/terminal/v1/{s}', b) for m, s, b in terminal_samples() if m == method]
            else:
                family = route.path.split('/')[3]
                assert family in FAMILY_SAMPLE, f'{route.path}: add the family {family} to FAMILY_SAMPLE'
                calls = [(method, route.path.replace('{name}', FAMILY_SAMPLE[family]), None)]
            for m, path, body in calls:
                before = len(FakeApi.calls)
                r = c.post(path, headers=h, json=body) if m == 'POST' else c.get(path)
                if len(FakeApi.calls) > before:
                    out.append((route.path, path, r))
    return out


def leaks(r):
    text = r.content.decode('utf-8', 'replace') if 'json' in r.headers.get('content-type', '') else ''
    return PLANTED in text or 'railway.internal' in text


def planted_app(settings, store, monkeypatch):
    monkeypatch.setattr(main.httpx, 'AsyncClient', Planted)        # one module: the proxy's and the page files' client
    FakeApi.calls, FakeApi.cut_headers = [], {}
    return create_app(dataclasses.replace(settings, terminal_url=URL, terminal_proxy_key=KEY), store, FakeOrc())


def test_no_private_key_or_internal_address_of_terminal_api_reaches_a_page(settings, store, monkeypatch):
    app = planted_app(settings, store, monkeypatch)
    with TestClient(app) as c:
        answers = walk(c, app, login(c))
    # every guarded route was reached, and each kind of proxy path
    assert {route for route, _, _ in answers} == {r.path for r in guarded_routes(app)}
    assert {p.split('/')[4] for route, p, _ in answers if route.startswith('/api/terminal/')} >= {
        'manifest', 'reference', 'history', 'logo', 'cut', 'files', 'bundle'}
    json_ok = {p: r for _, p, r in answers if r.status_code == 200 and 'json' in r.headers.get('content-type', '')}
    assert {'/api/terminal/v1/manifest/BBCA', '/api/terminal/v1/bundle', '/api/v1/radar/index'} <= set(json_ok), sorted(json_ok)
    assert [(p, r.status_code) for _, p, r in answers if leaks(r)] == []
    # the public part of each answer is kept: only the private keys and the internal address are taken out
    assert json_ok['/api/terminal/v1/manifest/BBCA'].json() == {
        'ticker': 'BBCA', 'ok': True, 'where': '[internal address]', 'files': [{'name': 'x', 'note': 'see [internal address]'}]}
    assert json_ok['/api/v1/radar/index'].json()['files'] == {
        'radar-days': {'sha256': PAGE_SHA, 'bytes': len(PAGE), 'note': '[internal address]'}}


def test_the_walk_finds_a_relay_without_the_filter(settings, store, monkeypatch):
    """Self-test: with the filter taken out of the one rule, the same walk finds the planted values (so the test above
    cannot pass by reaching no answer)."""
    app = planted_app(settings, store, monkeypatch)
    monkeypatch.setattr(terminal_access, 'public_data', lambda value: value)
    with TestClient(app) as c:
        found = {p for _, p, r in walk(c, app, login(c)) if leaks(r)}
    assert {'/api/terminal/v1/manifest/BBCA', '/api/terminal/v1/files', '/api/v1/radar/index'} <= found, found


# ---- R1-35 ("1a"): the attributes every Screener answer shows are not gated by id ---------------------------------------

def plan_principal(grants):
    return account_principal({'user_id': 7, 'owner_key': 'u_' + 'a' * 32, 'username': 'alice', 'role': 'user',
                              'status': 'active', 'plan_key': 'p', 'versions': {},
                              'grants': {k: {'kind': kind, 'value': v} for k, (kind, v) in grants.items()}})


def test_the_shown_attributes_are_the_screener_catalogs_row_entries():
    """One definition: the Screener catalog's universe entries that name their /universe row field (the worker's
    tests/shown.test.ts holds them to the rows it answers); the user's list: last price, 1-day change, average traded
    value, history bars, index membership."""
    assert catalog.SHOWN_ATTRIBUTES == {'last', 'chg_1d_pct', 'adv20_idr', 'bars', 'index_membership'}
    metrics = json.loads(catalog.SCREENER_METRICS.read_text())['metrics']
    assert catalog.SHOWN_ATTRIBUTES == {m['id'] for m in metrics if m['kind'] == 'universe' and 'row' in m}
    assert catalog.SHOWN_ATTRIBUTES <= {e['id'] for e in releases.entries('screener_metric')}
    with pytest.raises(RuntimeError, match='cannot be read'):
        catalog.shown_attributes(catalog.SCREENER_METRICS.with_name('missing.json'))


def test_a_plan_without_screener_metrics_is_allowed_the_shown_attributes_and_the_catalog_lists_them():
    nothing = plan_principal({'terminal.indicator': ('items', {'ids': ['I01']})})
    for worker in ('screener', 'backtest'):
        assert allow_of(nothing, worker)['screener_metric'] == sorted(catalog.SHOWN_ATTRIBUTES), worker
    assert [e['id'] for e in catalog.held(nothing, 'screener_metric')] == [
        e['id'] for e in releases.entries('screener_metric') if e['id'] in catalog.SHOWN_ATTRIBUTES]
    # a plan's own Screener metrics come beside them; every other kind is unchanged
    some = plan_principal({'screener.metric': ('items', {'ids': ['breakout']})})
    assert allow_of(some, 'screener')['screener_metric'] == sorted({'breakout', *catalog.SHOWN_ATTRIBUTES})
    assert allow_of(some, 'screener')['indicator'] == [] and not catalog.ungated('indicator', 'last')
    # a principal holding everything still sends "*"
    assert allow_of(plan_principal({'*': ('flag', True)}), 'screener')['screener_metric'] == '*'
