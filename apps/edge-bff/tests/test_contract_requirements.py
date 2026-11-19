"""EXEC-MU-ACCOUNTS fix round (records track, re-check R2-40): contract requirements whose code no test held.

The re-check removed each of these lines and every suite stayed green, because each requirement was tested only through
a neighbour (the idle timeout, the code-try Retry-After, the need() refusal path). Each test below fails on the mutation
the finder ran (named in its docstring). Where the class can recur in new code, the test is derived from the code
(every 429 an answer is built with, every message table, every /api answer of the two-user walk in
test_two_users_every_route.py for the default no-store) instead of naming one site.
"""
import ast
import dataclasses
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import errors
from app.main import create_app
from conftest import FakeOrc
from test_auth_flows import admin_sign_in, app, error_code, last_code, on, register, verify  # noqa: F401 - fixtures
from test_edge import ORIGIN, login
from test_principal import db, make_user, sign_in

APP = Path(__file__).resolve().parents[1] / 'app'


# ---- sessions: the absolute lifetime in both modes (CONTRACT 2 and 4: 24 h, idle 8 h) ---------------------------------

def test_an_expired_session_answers_401_with_the_switch_off(settings, store):
    """Mutation survived: store.session without `AND expires_at>now()` (a switch-off session never expired)."""
    with TestClient(create_app(settings, store, FakeOrc())) as c:
        login(c)
        assert c.get('/api/v1/auth/session').status_code == 200
        db(store, """UPDATE edge_bff.sessions SET created_at = now() - interval '25 hours',
            expires_at = now() - interval '1 second'""")
        r = c.get('/api/v1/auth/session')
        assert r.status_code == 401 and r.json()['error']['code'] == 'UNAUTHENTICATED', r.text


def test_an_expired_session_answers_401_with_the_switch_on_although_it_was_used_a_moment_ago(app, store):
    """Mutation survived: accounts.resolve without `s.expires_at > now()` (a session used within the idle window lived
    for ever)."""
    make_user(store, 'alice', 'alice-password')
    sign_in(app, 'alice', 'alice-password')
    assert app.get('/api/v1/auth/session').status_code == 200
    db(store, """UPDATE edge_bff.sessions SET created_at = now() - interval '25 hours',
        expires_at = now() - interval '1 second', last_seen_at = now()""")
    r = app.get('/api/v1/auth/session')
    assert r.status_code == 401 and error_code(r) == 'UNAUTHENTICATED', r.text


# ---- 429: Retry-After on every one (CONTRACT 3) -----------------------------------------------------------------------

def test_the_mfa_tries_limit_answers_with_retry_after(app):
    """Mutation survived: the Retry-After header of 429 LIMIT_REACHED mfa_tries removed."""
    h = admin_sign_in(app)
    app.post('/api/v1/auth/mfa/enroll', headers=h)
    answers = [app.post('/api/v1/auth/mfa/verify', headers=h, json={'code': '000000'}) for _ in range(11)]
    limited = [r for r in answers if r.status_code == 429]
    assert limited, [r.status_code for r in answers]
    r = limited[0]
    assert error_code(r) == 'LIMIT_REACHED' and int(r.headers['Retry-After']) > 0, (r.headers, r.text)
    assert int(r.headers['Retry-After']) == r.json()['error']['details']['retry_after_s']


ANSWER_BUILDERS = {'Refusal', 'refusal', 'failure', 'error', 'JSONResponse', 'Response'}


def builders_of_429():
    """Every call in app/ that builds an answer (a refusal, a failure, a response) with the status 429."""
    for path in sorted(APP.glob('*.py')):
        text = path.read_text()
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, 'id', '')
            values = [*node.args, *(k.value for k in node.keywords)]
            if name in ANSWER_BUILDERS and any(isinstance(v, ast.Constant) and v.value == 429 for v in values):
                yield path.name, node.lineno, ast.get_source_segment(text, node)


def test_every_429_an_answer_is_built_with_says_when_to_try_again():
    """The class of R2-40 item 3 (and R1-26): a 429 without Retry-After leaves the page to guess. Every call that builds
    an answer with 429 passes a Retry-After header; a new limit fails here until it does."""
    found = list(builders_of_429())
    assert len(found) >= 3, found                      # the walk sees the known limits (sign-in, codes, MFA, queue)
    missing = [f'{name}:{line}' for name, line, source in found if 'Retry-After' not in source]
    assert missing == [], (f'429 answers without a Retry-After header: {missing}. Pass headers={{"Retry-After": '
                           'str(seconds)}} and details.retry_after_s (CONTRACT.md section 3)')


# ---- X-Edge-Entitlements on the signed-in answers (CONTRACT 8a: every answer made for a principal) --------------------

def test_the_sign_in_and_the_registration_answers_carry_the_entitlements_version(app, store):
    """Mutation survived: the sign-in answer without request.state.principal; register/verify never set it."""
    assert register(app).status_code == 202
    made = verify(app, last_code(store, 'ana@example.com'))
    assert made.status_code == 200, made.text
    assert made.headers.get('X-Edge-Entitlements') == made.json()['access']['version'], made.headers
    app.post('/api/v1/auth/sign-out', headers={**ORIGIN, 'X-CSRF-Token': made.json()['csrf_token']})
    signed = app.post('/api/v1/auth/sign-in', headers=ORIGIN, json={'login': 'ana_putri',
                                                                    'password': 'a long enough password'})
    assert signed.status_code == 200, signed.text
    assert signed.headers.get('X-Edge-Entitlements') == signed.json()['access']['version'], signed.headers


# ---- the names refusals show come from the catalog at start (C1 Phase 3a F3) ------------------------------------------

def test_refusals_name_the_catalogs_items_from_the_start_without_a_refusal_first(on, store):
    """Mutation survived: the start-up load of the display names removed (only a need() refusal loaded them, so a
    refusal outside auth.need, as the backtest loop's dispatch or a worker's relayed one, showed the plain phrase)."""
    errors.set_display_names({})
    with TestClient(create_app(on, store, FakeOrc())):
        rows = db(store, "SELECT capability_key, display_name FROM edge_bff.capabilities WHERE capability_key <> '*'")
        assert rows
        shown = {r['capability_key']: errors.display_name(r['capability_key']) for r in rows}
        assert shown == {r['capability_key']: r['display_name'] for r in rows}


# ---- a subscription that has not started yet (CONTRACT 8a) ------------------------------------------------------------

def test_a_subscription_that_starts_tomorrow_gives_the_default_plan_today(app, store):
    """Mutation survived: the GRANTS live CTE without `s.starts_at <= now()`."""
    user = make_user(store, 'alice', 'alice-password')
    paid = db(store, '''SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = 'backtest.run'
        AND plan_key NOT IN (SELECT plan_key FROM edge_bff.plan_capabilities WHERE capability_key = '*')''')[0]['plan_key']
    default = db(store, 'SELECT plan_key FROM edge_bff.plans WHERE is_default')[0]['plan_key']
    db(store, '''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, provider, starts_at)
        VALUES (%s, %s, 'active', 'test', now() + interval '1 day')''', user['user_id'], paid)
    sign_in(app, 'alice', 'alice-password')
    access = app.get('/api/v1/auth/session').json()['access']
    assert access['plan'] == default and 'backtest.run' not in access['capabilities'], access
    db(store, "UPDATE edge_bff.subscriptions SET starts_at = now() - interval '1 second' WHERE user_id = %s",
       user['user_id'])
    assert app.get('/api/v1/auth/session').json()['access']['plan'] == paid


# ---- sends per client address are recorded until the probe (CONTRACT 4 "Client IP") -----------------------------------

def test_an_email_send_records_the_client_address_count(app, store):
    """Mutation survived: the SEND_IP row no longer written (the per-address count the probe will turn on)."""
    assert db(store, "SELECT count(*) AS n FROM edge_bff.auth_throttle WHERE scope = 'send_ip'")[0]['n'] == 0
    assert register(app).status_code == 202
    assert db(store, "SELECT coalesce(sum(count), 0) AS n FROM edge_bff.auth_throttle WHERE scope = 'send_ip'")[0]['n'] >= 1


# ---- a session waiting for its second factor may sign out (CONTRACT 4 "Admin MFA") -------------------------------------

def test_a_session_waiting_for_mfa_can_sign_out(app, store):
    """Mutation survived: sign-out removed from MFA_OPEN (the pending session could not end itself)."""
    h = admin_sign_in(app)
    r = app.post('/api/v1/auth/sign-out', headers=h)
    assert r.status_code in (200, 204), r.text
    assert db(store, 'SELECT count(*) AS n FROM edge_bff.sessions WHERE revoked_at IS NULL')[0]['n'] == 0
    assert app.get('/api/v1/auth/session').status_code == 401


# ---- plain words in every message table (CONTRACT 3; EXEC-UI-1019B) ---------------------------------------------------

CODE = re.compile(r'^[A-Z][A-Z0-9_]+$')
SETTING = re.compile(r'\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b')         # a setting or an internal code, as EDGE_TERMINAL_URL
INTERNAL = ('csrf', 'token', 'edge_', 'fastapi', 'owner_key', 'http')


def text_of(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return ''.join(v.value if isinstance(v, ast.Constant) else '{}' for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = text_of(node.left), text_of(node.right)
        return None if left is None or right is None else left + right
    return None


def message_tables():
    """Every dict literal in app/ that maps codes (UPPER_CASE) to sentences: errors.MESSAGES and each module's own."""
    for path in sorted(APP.glob('*.py')):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Dict) or len(node.keys) < 2:
                continue
            if not all(isinstance(k, ast.Constant) and isinstance(k.value, str) and CODE.match(k.value) for k in node.keys):
                continue
            texts = [text_of(v) for v in node.values]
            if all(t is not None and ' ' in t for t in texts):
                yield path.name, node.lineno, dict(zip((k.value for k in node.keys), texts))


def test_every_message_table_speaks_plain_words():
    """test_error_contract.py held errors.MESSAGES only; the same rule over every table found pages.py NOT_CONFIGURED
    naming EDGE_TERMINAL_URL and TERMINAL_PROXY_KEY, which the Radar, Overview and Watchlist pages show."""
    tables = list(message_tables())
    assert {'errors.py', 'pages.py'} <= {name for name, _, _ in tables}, tables
    wrong = [f'{name}:{line} {code}: {SETTING.findall(text) or [w for w in INTERNAL if w in text.lower()]}'
             for name, line, table in tables for code, text in table.items()
             if SETTING.search(text) or any(w in text.lower() for w in INTERNAL)]
    assert wrong == [], ('messages people see name settings or internal words (say what happened and what to do; the '
                         f'code already tells the operator): {wrong}')
