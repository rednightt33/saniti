"""EXEC-MU-ACCOUNTS re-check of Phases 0-3b, fix round, track "terminal" (verification/edge_multiuser/fix_round/
terminal.md): edge-bff's side of the Terminal path. The re-check's own failing tests (test_cp0_terminal_relay.py,
test_c_p3a_probes.py, test_c_p2_terminal_wire_domain.py, test_c2_e2e_people.py) hold the findings; these hold the rest
of each fix:

- R1-1, R1-26: terminal_access.relayed maps every terminal-api answer onto the contract (CONTRACT.md section 3), the one
  rule of forward_terminal, relay_cut and PageFiles;
- R2-4: an answer for a capped principal is relayed only when terminal-api acknowledges the header it applied (a
  terminal-api from before Phase 3c ignores it and would serve the plan in full);
- R1-22: history_days 0 refuses every dated path first and still lets the page files through; the catalog holds a
  value domain per capability (migration 20261119_050) that the value trigger reads, equal to terminal-api's bounds;
- R1-31: PageFiles applies the principal's own refusals before its shared caches;
- R2-32: the plan's own copy of a reference file is relayed byte for byte;
- the names edge-bff maps are terminal-api's own (read from apps/terminal-api).
"""
import hashlib
import importlib.util
import json
import logging
import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import terminal_access
from app.errors import Refusal
from app.main import create_app
from app.principal import switch_off_principal
from conftest import FakeOrc
from test_principal import db, make_user, on, sign_in, workers  # noqa: F401 - the fixtures
from test_terminal_access import (CUT, PAGE_SHA, URL, FakeApi, api, paid_plan, principal, subscribe,  # noqa: F401
                                  switched_off, switched_on, terminal_calls)
from test_edge import login

ROOT = Path(__file__).resolve().parents[3]
TERMINAL_API = ROOT / 'apps/terminal-api/app'
_spec = importlib.util.spec_from_file_location('terminal_api_entitlements_fix', TERMINAL_API / 'entitlements.py')
entitlements = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(entitlements)


def answer(status, body=None, **headers):
    return status, body, httpx.Headers(headers)


# ---- R1-1, R1-26: one rule for every terminal-api answer ------------------------------------------------------------

RELAYED = [
    # terminal-api's own account, key or host rule: never the EDGE sign-in (503, logged)
    (answer(401, {'error': 'session_ended', 'message': 'The terminal account of this gateway is not active.'}),
     (503, 'TERMINAL_UNAVAILABLE', {})),
    (answer(401, {'error': 'proxy_key_rejected', 'message': 'no key'}), (503, 'TERMINAL_UNAVAILABLE', {})),
    (answer(403, {'error': 'gateway_host_not_allowed', 'message': 'This address does not accept keyed requests.'}),
     (503, 'TERMINAL_UNAVAILABLE', {})),
    (answer(403, {'error': 'direct_access_closed', 'message': 'closed'}), (503, 'TERMINAL_UNAVAILABLE', {})),
    # edge-bff's own headers refused: edge-bff's fault, not the page's
    (answer(400, {'error': 'invalid_owner_headers', 'field': 'history_days', 'message': 'x'}),
     (503, 'TERMINAL_UNAVAILABLE', {})),
    (answer(400, {'error': 'owner_not_allowed', 'message': 'x'}), (503, 'TERMINAL_UNAVAILABLE', {})),
    # the request's own problem: its status, terminal-api's code as the reason, the field names only
    (answer(400, {'error': 'invalid_request', 'message': 'Check the listed fields.',
                  'fields': [{'field': 'years', 'problem': 'must hold 1-6 years'}]}),
     (400, 'INVALID_INPUT', {'reason': 'invalid_request', 'fields': ['years']})),
    (answer(404, {'error': 'unknown_ticker', 'message': 'No published data for ZZZZ.'}),
     (404, 'NOT_FOUND', {'reason': 'unknown_ticker'})),
    (answer(404, {'error': 'Not Found'}), (404, 'NOT_FOUND', {})),
    # terminal-api cannot answer now
    (answer(503, {'error': 'state_unavailable', 'message': 'try again'}), (503, 'TERMINAL_UNAVAILABLE', {})),
    (answer(500, None), (503, 'TERMINAL_UNAVAILABLE', {})),
    (answer(502, {'detail': 'bad gateway'}), (503, 'TERMINAL_UNAVAILABLE', {})),
    # its quota: LIMIT_REACHED with the limit and the wait it names; an older terminal-api's header, else an hour
    (answer(429, {'error': 'quota_exceeded', 'quota': 'tickers_per_day', 'limit': 200, 'window': '24 hours',
                  'retry_after_s': 77}, **{'Retry-After': '77'}),
     (429, 'LIMIT_REACHED', {'limit': 'terminal.tickers_per_day', 'allowed': 200, 'retry_after_s': 77})),
    (answer(429, {'error': 'quota_exceeded', 'message': 'Quota files_per_hour reached'}, **{'Retry-After': '120'}),
     (429, 'LIMIT_REACHED', {'limit': 'terminal.quota', 'retry_after_s': 120})),
    (answer(429, {'error': 'quota_exceeded', 'quota': 'Files Per Hour!', 'retry_after_s': 10 ** 9}),
     (429, 'LIMIT_REACHED', {'limit': 'terminal.quota', 'retry_after_s': 3600})),
    # its own capability refusal, in EDGE's shape
    (answer(403, {'error': 'capability_required', 'capability': 'terminal.history_days', 'message': 'x'}),
     (403, 'CAPABILITY_REQUIRED', {'capability': 'terminal.history_days'})),
]


@pytest.mark.parametrize('upstream, want', RELAYED, ids=[f'{a[0]}-{(a[1] or {}).get("error")}' for a, _ in RELAYED])
def test_every_terminal_api_answer_maps_onto_the_contract(settings, upstream, want, caplog):
    status, body, headers = upstream
    p = switch_off_principal(settings, settings.owner)                   # holds '*': acknowledged by definition
    with caplog.at_level(logging.WARNING, 'edge_bff.terminal_access'):
        refused = terminal_access.relayed(p, status, body, headers, 'manifest/BBCA')
    assert isinstance(refused, Refusal)
    code_status, code, details = want
    assert (refused.status, refused.code) == (code_status, code), (refused.status, refused.code, refused.details)
    if code == 'CAPABILITY_REQUIRED':
        assert refused.details['capability'] == details['capability'] and refused.details['display_name']
    else:
        assert refused.details == details
    if code_status == 429:
        assert refused.headers == {'Retry-After': str(details['retry_after_s'])}       # CONTRACT 3: on every 429
    # terminal-api's prose (it names internal routes and hosts) never reaches the page; the 503s are logged with the code
    assert 'message' not in json.dumps(refused.details) and 'railway' not in json.dumps(refused.details)
    if code == 'TERMINAL_UNAVAILABLE':
        logged = [json.loads(r.getMessage()) for r in caplog.records if 'terminal_refused' in r.getMessage()]
        assert logged and logged[-1]['status'] == status and logged[-1]['code'] == (body or {}).get('error')
    assert terminal_access.relayed(p, 200, {'ok': True}, httpx.Headers(), 'manifest/BBCA') is None


def test_a_relayed_refusal_reaches_the_page_and_the_session_stays(switched_off, store, monkeypatch):
    """Through the real routes: a terminal-api 401 is a 503 with the EDGE session intact, a 429 is LIMIT_REACHED with
    Retry-After, on the JSON relay and on the byte relay alike."""
    with TestClient(create_app(switched_off, store, FakeOrc())) as c:
        h = login(c)
        monkeypatch.setattr(FakeApi, 'answer', lambda self, method, url, content: httpx.Response(
            401, json={'error': 'session_ended', 'message': 'The terminal account of this gateway is not active.'}))
        for r in (c.get('/api/terminal/v1/manifest/BBCA'), c.post('/api/terminal/v1/bundle', headers=h,
                                                                    json={'ticker': 'BBCA', 'datasets': ['price']})):
            assert r.status_code == 503 and r.json()['error']['code'] == 'TERMINAL_UNAVAILABLE', r.text
        assert c.get('/api/v1/auth/session').status_code == 200
        monkeypatch.setattr(FakeApi, 'answer', lambda self, method, url, content: httpx.Response(
            429, json={'error': 'quota_exceeded', 'quota': 'files_per_hour', 'limit': 300, 'retry_after_s': 42},
            headers={'Retry-After': '42'}))
        r = c.post('/api/terminal/v1/files', headers=h, json={'ticker': 'BBCA', 'dataset': 'price', 'years': [2026]})
        assert r.status_code == 429 and r.headers['retry-after'] == '42'
        assert r.json()['error']['details'] == {'limit': 'terminal.files_per_hour', 'allowed': 300, 'retry_after_s': 42}
        # the byte relay: terminal-api's refusal of a cut in the same shape
        r = c.get('/api/terminal/v1/cut/BBCA/yield')
        assert r.status_code == 404 and r.json()['error'] == {
            'code': 'NOT_FOUND', 'message': r.json()['error']['message'], 'details': {'reason': 'cannot_cut'}}


# ---- R2-4: no relay without terminal-api's acknowledgement ------------------------------------------------------------

def pre_3c(monkeypatch):
    """terminal-api from before Phase 3c: it ignores the owner headers and acknowledges nothing."""
    import test_terminal_access
    monkeypatch.setattr(test_terminal_access, 'acknowledge', lambda response, headers: response)


def test_a_terminal_api_that_ignores_the_header_never_serves_a_capped_principal(switched_on, store, monkeypatch,
                                                                                caplog):
    pre_3c(monkeypatch)
    with TestClient(create_app(switched_on, store, FakeOrc())) as c:
        user = make_user(store, 'pat', 'pat-password')
        subscribe(store, user, paid_plan(store))
        h = sign_in(c, 'pat', 'pat-password')
        with caplog.at_level(logging.WARNING, 'edge_bff.terminal_access'):
            for r in (c.get('/api/terminal/v1/manifest/BBCA'), c.get('/api/terminal/v1/logo/BBCA'),
                      c.post('/api/terminal/v1/bundle', headers=h, json={'ticker': 'BBCA', 'datasets': ['price']}),
                      c.get('/api/terminal/v1/cut/BBCA/price'), c.get('/api/terminal/v1/reference/tickers/cut'),
                      c.get('/api/v1/radar/index'), c.get(f'/api/v1/radar/file/radar-days?sha={PAGE_SHA}')):
                assert r.status_code == 503, (r.request.url, r.status_code, r.text)
                assert r.json()['error']['code'] in ('TERMINAL_UNAVAILABLE', 'RADAR_UNAVAILABLE'), r.text
        assert 'terminal_capabilities_not_applied' in caplog.text
        assert terminal_calls()                                          # it was asked; its answer was not relayed


def test_the_switch_off_owner_needs_no_acknowledgement(switched_off, store, monkeypatch):
    pre_3c(monkeypatch)
    with TestClient(create_app(switched_off, store, FakeOrc())) as c:
        login(c)
        assert c.get('/api/terminal/v1/manifest/BBCA').status_code == 200
        assert c.get('/api/terminal/v1/cut/BBCA/price').content == CUT
        assert c.get('/api/v1/radar/index').status_code == 200


def test_the_acknowledgement_is_the_version_of_this_principal(settings):
    p = principal()
    assert terminal_access.acknowledged(p, httpx.Headers({terminal_access.APPLIED_HEADER: '1 db-123456789abc'}))
    for value in ('1 db-000000000000', '2 db-123456789abc', '', 'db-123456789abc'):
        assert not terminal_access.acknowledged(p, httpx.Headers({terminal_access.APPLIED_HEADER: value})), value
    assert not terminal_access.acknowledged(p, httpx.Headers())
    assert terminal_access.acknowledged(switch_off_principal(settings, settings.owner), httpx.Headers())


# ---- R1-22: history_days 0 -------------------------------------------------------------------------------------------

def test_history_days_zero_refuses_every_dated_path_first_and_keeps_the_rest(settings):
    zero = principal(limits={'terminal.history_days': 0, 'terminal.tickers': ['BBCA']},
                     grants={'terminal.dataset': {'ids': ['price']}}, kinds={'terminal.dataset': 'items'})
    q = httpx.QueryParams
    for method, path, query, body in (('POST', 'files', q(), b'{"ticker": "BBCA", "dataset": "price", "years": [2026]}'),
                                      ('POST', 'bundle', q(), b'{"ticker": "BBCA", "datasets": ["price"]}'),
                                      ('GET', 'cut/BBCA/price', q(), None),
                                      ('GET', 'history/price', q('ticker=BBCA&from=2019-01-01&to=2019-02-01'), None)):
        with pytest.raises(Refusal) as e:
            terminal_access.check(zero, method, path, query, body)
        assert (e.value.status, e.value.code, e.value.details['capability']) == (403, 'CAPABILITY_REQUIRED',
                                                                                 'terminal.history_days'), path
    for path in ('manifest/BBCA', 'logo/BBCA', 'reference/tickers', 'reference/tickers/cut'):
        terminal_access.check(zero, 'GET', path, q(), None)              # no dated row asked: not refused
    caps = entitlements.parse_capabilities(terminal_access.capabilities_header(zero), terminal_access.DATASET_IDS)
    assert caps.history_days == 0                                        # the page files' header still parses


def test_a_ticker_outside_terminal_apis_rule_is_left_out_and_logged(caplog):
    p = principal(limits={'terminal.tickers': ['BBCA', 'bbri', ' TLKM', '']})
    with caplog.at_level(logging.WARNING, 'edge_bff.terminal_access'):
        header = terminal_access.capabilities_header(p)
    assert json.loads(header)['tickers'] == ['BBCA']
    assert 'terminal_tickers_dropped' in caplog.text and '"count": 3' in caplog.text
    assert 'bbri' not in caplog.text                                     # the log names the count, not the values


# ---- R1-31: the principal's own refusals before the shared caches --------------------------------------------------

def test_a_page_file_refusal_of_the_principal_holds_when_another_account_warmed_the_cache(switched_on, store):
    with TestClient(create_app(switched_on, store, FakeOrc())) as first:
        user = make_user(store, 'pat', 'pat-password')
        subscribe(store, user, paid_plan(store))
        sign_in(first, 'pat', 'pat-password')
        assert first.get(f'/api/v1/radar/file/radar-days?sha={PAGE_SHA}').status_code == 200   # index and bytes kept
        quinn = make_user(store, 'quinn', 'quinn-password')
        subscribe(store, quinn, paid_plan(store))
        # a 0 the value check no longer takes (migration 20261119_050) but a read can still give (principal.RESTRICTIVE):
        # written past the triggers, as a value stored before a check would be
        with store.connect() as conn:
            conn.execute("SET LOCAL session_replication_role = replica")
            conn.execute('''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
                VALUES (%s, 'terminal.files_per_hour', '0', 'test')''', (quinn['user_id'],))
        calls = len(FakeApi.calls)
        second = TestClient(first.app)
        sign_in(second, 'quinn', 'quinn-password')
        for path in ('/api/v1/radar/index', f'/api/v1/radar/file/radar-days?sha={PAGE_SHA}'):
            r = second.get(path)
            assert r.status_code == 403 and r.json()['error']['details']['capability'] == 'terminal.files_per_hour', r.text
        assert len(FakeApi.calls) == calls                               # refused before any terminal-api call


# ---- R2-32: the plan's own copy of a reference file, byte for byte --------------------------------------------------

def test_the_plans_copy_of_a_reference_file_is_relayed_byte_for_byte(switched_on, store):
    with TestClient(create_app(switched_on, store, FakeOrc())) as c:
        make_user(store, 'freda', 'freda-password')                     # the default plan: no reference lists
        sign_in(c, 'freda', 'freda-password')
        sha = hashlib.sha256(CUT).hexdigest()
        r = c.get(f'/api/terminal/v1/reference/tickers/cut?sha256={sha}')
        assert r.status_code == 200 and r.content == CUT and r.headers['cache-control'].startswith('private')
        assert 'content-encoding' not in r.headers
        call = terminal_calls()[-1]
        assert call['url'] == f'{URL}/api/terminal/v1/reference/tickers/cut' and call['params'] == {'sha256': sha}
        assert c.get('/api/terminal/v1/reference/tickers/cut/more').status_code == 404


# ---- the names are terminal-api's own -------------------------------------------------------------------------------

def test_the_wire_names_and_bounds_are_terminal_apis():
    assert terminal_access.APPLIED_HEADER == entitlements.APPLIED_HEADER
    assert terminal_access.MAX_HISTORY_DAYS == entitlements.MAX_HISTORY_DAYS
    assert '^' + terminal_access.TICKER.pattern + '$' == entitlements.TICKER_RE.pattern
    main = (TERMINAL_API / 'main.py').read_text()
    for code in terminal_access.OWN_HEADER_CODES:                     # refusals of the owner headers edge-bff builds
        assert re.search(rf"error\(400, '{code}'", main), code
    assert re.search(r"wait_error\('quota_exceeded', .*quota=refusal\.quota, limit=refusal\.limit", main)


# ---- R1-22: the catalog's value domain per capability (migration 20261119_050) ----------------------------------

DOMAIN_MIGRATION = ROOT / 'database/migrations/20261119_050_edge_bff_capability_domains.sql'
OUTSIDE = [('terminal.history_days', '0'), ('terminal.history_days', '36601'), ('terminal.tickers', '["bbca"]'),
           ('terminal.tickers', '[" BBCA"]'), ('terminal.tickers', '["BBCA", ""]'),
           ('terminal.tickers', json.dumps([f'T{i:03d}' for i in range(501)])), ('terminal.files_per_hour', '0'),
           ('terminal.megabytes_per_day', '1000000001')]
INSIDE = [('terminal.history_days', '1'), ('terminal.history_days', '36600'), ('terminal.tickers', '[]'),
          ('terminal.tickers', json.dumps([f'T{i:03d}' for i in range(500)])), ('terminal.files_per_hour', '1')]


@pytest.mark.parametrize('key, value', OUTSIDE)
def test_a_value_outside_its_capabilitys_domain_is_refused_when_written(store, key, value):
    import psycopg
    user = make_user(store, 'dora', 'dora-password')
    for sql, args in (('''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
                          VALUES (%s, %s, %s::jsonb, 'typo')''', (user['user_id'], key, value)),
                      ('''UPDATE edge_bff.plan_capabilities SET value = %s::jsonb
                          WHERE capability_key = %s AND plan_key = (SELECT plan_key FROM edge_bff.plans WHERE is_default)''',
                       (value, key))):
        with pytest.raises(psycopg.errors.RaiseException, match='is outside the domain of capability') as caught:
            db(store, sql, *args)
        hint = caught.value.diag.message_hint or ''
        assert hint.startswith(f'{key} takes ') and 'Example:' in hint, hint      # the rule, and a right example


@pytest.mark.parametrize('key, value', INSIDE)
def test_a_value_inside_its_domain_is_written(store, key, value):
    user = make_user(store, 'dora', 'dora-password')
    db(store, '''INSERT INTO edge_bff.user_capability_overrides(user_id, capability_key, value, reason)
        VALUES (%s, %s, %s::jsonb, 'ok')''', user['user_id'], key, value)


def test_a_domain_a_stored_value_would_not_fit_is_refused(store):
    import psycopg
    with pytest.raises(psycopg.errors.RaiseException, match='fall outside its new domain') as caught:
        db(store, "UPDATE edge_bff.capabilities SET value_max = 100 WHERE capability_key = 'terminal.history_days'")
    assert 'plan ' in str(caught.value) and '730' in str(caught.value)             # names the value that holds it
    db(store, "UPDATE edge_bff.capabilities SET value_max = 36600 WHERE capability_key = 'terminal.history_days'")


def test_the_domains_are_the_wires_and_fit_the_header(store):
    rows = {r['capability_key']: r for r in db(store, '''SELECT capability_key, kind, value_min, value_max, item_pattern
        FROM edge_bff.capabilities WHERE value_min IS NOT NULL OR value_max IS NOT NULL OR item_pattern IS NOT NULL''')}
    assert rows['terminal.history_days']['value_max'] == entitlements.MAX_HISTORY_DAYS
    assert rows['terminal.tickers']['item_pattern'] == entitlements.TICKER_RE.pattern
    assert {k for k, r in rows.items() if r['value_max'] == entitlements.MAX_QUOTA} == {
        f'terminal.{name}' for name in terminal_access.QUOTA}
    # the most the domain lets a plan hold still fits terminal-api's 8 KiB header
    widest = principal(limits={'terminal.tickers': [f'{i:012d}' for i in range(rows['terminal.tickers']['value_max'])],
                               'terminal.history_days': 36600,
                               **{f'terminal.{n}': entitlements.MAX_QUOTA for n in terminal_access.QUOTA}},
                       grants={'terminal.dataset': {'all': True}}, kinds={'terminal.dataset': 'items'})
    header = terminal_access.capabilities_header(widest)
    assert len(header) <= entitlements.MAX_CAPS_BYTES
    assert entitlements.parse_capabilities(header, terminal_access.DATASET_IDS).tickers


def test_the_domain_migration_refuses_a_second_run_and_a_wrong_domain(database):
    import psycopg
    with psycopg.connect(database, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.RaiseException, match='already has a value domain'):
            conn.execute(DOMAIN_MIGRATION.read_text())
    text = DOMAIN_MIGRATION.read_text()
    body = text.split('DO $verify$', 1)[1].split('END $verify$;', 1)[0]
    with psycopg.connect(database) as conn:
        conn.execute("UPDATE edge_bff.capabilities SET value_max = 36599 WHERE capability_key = 'terminal.history_days'")
        with pytest.raises(psycopg.errors.RaiseException, match='the domain of terminal.history_days is not'):
            conn.execute('DO $verify$' + body + 'END $verify$;')
        conn.rollback()
