"""The live smoke, from outside (EXEC option A; LIVE_PROMOTION.md step 8). Run from the repository root with the
runner's variables, where the live admin's login lives since 2026-11-20 (never printed):
    railway run -s orc-test-runner -e dev -- python3 verification/edge_multiuser/live_smoke/http_smoke.py https://app.edgefinance.id
Checks /ready, the page and its headers, the config, a visitor's Terminal (BBCA open, another ticker refused with the
sign-in words), every gated route (beta-only: 404 before any session; others: 401 for a visitor), registration closed,
the origin check, and, only with --admin, the admin's sign-in up to its second step (MFA_REQUIRED, no enrolment made).
Prints only status codes, error codes and counts: never a password, an address or a cookie.

--admin (ERRORS M516): EDGE_ADMIN_INITIAL_PASSWORD is the admin's first password. Once the owner resets or changes it
(as on 2026-11-20) it no longer opens the account, and every try counts one failure toward the account's lock (100 in a
row lock it for 24 hours, app/accounts.py), so the default run tries no sign-in: the owner signs in themself after a
promotion. With --admin it tries once, by the username, and a 401 reads "the first password no longer opens"."""
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.request

from pathlib import Path  # noqa: E402

EDGE_BFF = Path(__file__).resolve().parents[3] / 'apps' / 'edge-bff'
sys.path.insert(0, str(EDGE_BFF / 'tests'))
sys.path.insert(0, str(EDGE_BFF))
from app.principal import beta_only  # noqa: E402
from test_phase3a_gates import ROUTE_CAPS as A  # noqa: E402
try:
    from test_phase3a_monitor_pages import ROUTE_CAPS as B  # noqa: E402
except Exception:
    B = {}

ARGS = [a for a in sys.argv[1:] if a != '--admin']
ADMIN = '--admin' in sys.argv[1:]
BASE = ARGS[0].rstrip('/')


def opener():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def call(o, method, path, body=None, origin=BASE, csrf=None):
    url = BASE + re.sub(r'\{[^}]+\}', 'x1', path)
    data = json.dumps(body if body is not None else {}).encode() if method in ('POST', 'PUT', 'PATCH', 'DELETE') else None
    h = {'content-type': 'application/json', 'origin': origin, **({'x-csrf-token': csrf} if csrf else {})}
    req = urllib.request.Request(url, method=method, data=data, headers=h)
    try:
        with o.open(req, timeout=40) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()
    except Exception as e:  # noqa: BLE001
        return f'error {type(e).__name__}', {}, b''


def code_of(raw):
    try:
        err = json.loads(raw or b'{}').get('error')
        return err.get('code') if isinstance(err, dict) else err
    except Exception:  # noqa: BLE001
        return None


out = {}
v = opener()
out['ready'] = call(v, 'GET', '/ready')[0]
st, headers, page = call(v, 'GET', '/')
csp = headers.get('Content-Security-Policy') or headers.get('content-security-policy') or ''
out['page'] = {'status': st, 'csp': bool(csp), 'csp_frame_ancestors_none': "frame-ancestors 'none'" in csp,
               'hsts': bool(headers.get('Strict-Transport-Security') or headers.get('strict-transport-security'))}
st, _, raw = call(v, 'GET', '/api/v1/auth/config')
cfg = json.loads(raw or b'{}')
out['config'] = {'status': st, 'multiuser': cfg.get('multiuser'), 'hidden_tabs': cfg.get('hidden_tabs'),
                 'registration': cfg.get('registration', cfg.get('registration_open')), 'keys': sorted(cfg)}
st, _, raw = call(v, 'GET', '/api/v1/session')
out['visitor_session'] = {'status': st, 'role': (json.loads(raw or b'{}') or {}).get('role') if st == 200 else code_of(raw)}
for page_path in ('/terminal', '/monitor', '/c/conv_' + '0' * 32, '/admin'):
    out[f'page {page_path}'] = call(v, 'GET', page_path)[0]
st, _, raw = call(v, 'GET', '/api/terminal/v1/manifest/BBCA')
out['visitor BBCA manifest'] = st
st, _, raw = call(v, 'GET', '/api/terminal/v1/manifest/TLKM')
body = json.loads(raw or b'{}') if raw else {}
err = body.get('error') if isinstance(body.get('error'), dict) else {}
out['visitor TLKM manifest'] = {'status': st, 'code': err.get('code'), 'visitor': (err.get('details') or {}).get('visitor'),
                                'says_sign_in': 'Sign in' in (err.get('message') or '')}
routes = sorted(set(A) | set(B))
wrong = {}
counts = {'beta_only_404': 0, 'gated_401': 0, 'relay_made_up_path_404': 0}
for (m, p), cap in ((r, (A.get(r) or B.get(r))) for r in routes):
    st = call(opener(), m, p)[0]
    caps = cap if isinstance(cap, (list, tuple, set, frozenset)) else [cap]
    # the Terminal relay is open to a visitor (its datasets are gated in the bundle, tests/test_live_terminal_locked.py),
    # so the route table's made-up path `{path:path}` reaches terminal-api and is its 404, not a sign-in refusal
    relay = p.startswith('/api/terminal/v1/{')
    want = 404 if relay or any(beta_only(c) for c in caps if isinstance(c, str)) else 401
    if st == want:
        counts['relay_made_up_path_404' if relay else 'beta_only_404' if want == 404 else 'gated_401'] += 1
    else:
        wrong[f'{m} {p}'] = {'status': st, 'expected': want}
out['routes'] = dict(counts, total=len(routes), unexpected=wrong)
st, _, raw = call(opener(), 'POST', '/api/v1/auth/register', {'email': 'nobody@example.invalid', 'username': 'nobody_x',
                  'password': 'a long enough password 1', 'password_repeat': 'a long enough password 1',
                  'first_name': 'No', 'last_name': 'Body'})
out['register'] = {'status': st, 'code': code_of(raw)}
st, _, raw = call(opener(), 'POST', '/api/v1/auth/sign-in', {'login': 'x', 'password': 'y'}, origin='https://evil.example')
out['foreign origin sign-in'] = {'status': st, 'code': code_of(raw)}
login = os.environ.get('EDGE_ADMIN_USERNAME', '')
if not ADMIN:
    out['admin'] = 'not tried (the owner signs in themself; --admin tries the first password once)'
elif not (login and os.environ.get('EDGE_ADMIN_INITIAL_PASSWORD')):
    out['admin'] = 'no login or first password in the environment'
else:
    st, _, raw = call(opener(), 'POST', '/api/v1/auth/sign-in', {'login': login,
                                                                 'password': os.environ['EDGE_ADMIN_INITIAL_PASSWORD']})
    body = json.loads(raw or b'{}')
    err = body.get('error') if isinstance(body.get('error'), dict) else {}
    out['admin'] = {'status': st, 'code': err.get('code'), 'mfa_enrolled': (err.get('details') or {}).get('mfa_enrolled'),
                    'reads': ('the first password no longer opens: the owner set their own (expected after a reset or '
                              'a change; one failure counted)') if st == 401 else 'the first password opens'}
st, _, raw = call(opener(), 'POST', '/api/v1/auth/sign-in', {'login': 'nobody_here', 'password': 'not the password'})
out['unknown sign-in'] = {'status': st, 'code': code_of(raw)}
print(json.dumps(out, indent=1))
