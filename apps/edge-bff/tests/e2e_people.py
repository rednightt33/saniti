"""C2-E2E (EXEC-MU-ACCOUNTS re-check, round 2): the harness of the end-to-end checks of three people with EDGE_MULTIUSER
on (tests/test_c2_e2e_people.py). Not a test module itself.

edge-bff runs on a real local server (uvicorn, as tests/test_auth_pages_live.py does) against the test Postgres, with:
- FakeOrc (conftest) for the Monitor;
- the fake screener-worker of tests/test_screener.py and the fake backtest worker of tests/test_backtest.py;
- FakeTerminalApi below: terminal-api's gateway routes (reference, bundle, logo and the page families overview, radar
  and watchlist) with made-up rows (no real market data, ERRORS M469), every call recorded with its headers. The
  Terminal downloads its files in a Web Worker, which a browser context's routes do not see, so the bucket host
  (https://e2e.t3.storageapi.dev, inside the Terminal's connect-src) is mapped to a local HTTPS server with a throw-away
  certificate (browser_args); edge-bff fetches the page files' objects itself from http://127.0.0.1:<fake>/bucket/.
- the built pages (npm run build in each app folder) from their dist folders; a test that needs one skips without it.

People: the admin is user #1 (the seed row, login 'owner'), who enrols the authenticator on the first switch-on sign-in;
a paid and a free user register through /register with the emailed code (EDGE_EMAIL_MODE=log, read from the outbox row
as test_auth_pages_live does). The paid plan is given as the Phase 4 admin page will: one active manual subscription.
"""
import dataclasses
import gzip
import hashlib
import importlib.util
import json
import os
import sys
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import uvicorn

from app import main, mfa
from app.main import create_app
from conftest import FakeOrc

ROOT = Path(__file__).resolve().parents[1]
TERMINAL_API = ROOT.parents[0] / 'terminal-api' / 'app'
CHROMIUM = os.environ.get('EDGE_TEST_CHROMIUM', '/usr/bin/chromium')
BUCKET_HOST = 'e2e.t3.storageapi.dev'
BUCKET = 'https://' + BUCKET_HOST
PASSWORD = 'a long enough password'
TERMINAL_KEY = 't' * 40
SCREENER_KEY, BACKTEST_KEY = 's' * 40, 'w' * 40          # the keys of the fakes in test_screener.py and test_backtest.py
REFUSAL_WORDS = 'This feature is not part of your EDGE plan. Upgrade the plan to use it; you are still signed in.'


def gz(doc):
    return gzip.compress(json.dumps(doc, separators=(',', ':')).encode(), mtime=0)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def price_rows(days=400, start=1000.0):
    """Made-up daily rows [d, o, h, l, c, v] up to 2026-11-13, weekdays only."""
    rows, d, price, k = [], date(2026, 11, 13), start, 0
    while len(rows) < days:
        if d.weekday() < 5:
            k += 1
            o = price * (1 + ((k * 37) % 11 - 5) / 1000)
            c = o * (1 + ((k * 53) % 13 - 6) / 1000)
            rows.append([d.isoformat(), round(o, 2), round(max(o, c) * 1.004, 2), round(min(o, c) * 0.996, 2), round(c, 2),
                         1_000_000 + (k * 7919) % 500_000])
            price = c
        d -= timedelta(days=1)
    return rows[::-1]


TICKERS = {'BBCA': ('Bank Central Asia', 'stock', 'Finance', 9000.0), 'BBRI': ('Bank Rakyat Indonesia', 'stock', 'Finance', 4000.0),
           'TLKM': ('Telkom Indonesia', 'stock', 'Infrastructure', 3000.0), 'IHSG': ('Composite Index', 'index', None, 7000.0)}


def terminal_api(module):
    """A module of terminal-api's own code (apps/terminal-api/app), loaded under the package name terminal_api_e2e (its
    package is called `app` like edge-bff's), so the fake below answers the way terminal-api decides (EXEC-MU-ACCOUNTS
    re-check R2-32): its header parser, its cut and its reference copies."""
    if 'terminal_api_e2e' not in sys.modules:
        spec = importlib.util.spec_from_file_location('terminal_api_e2e', TERMINAL_API / '__init__.py',
                                                      submodule_search_locations=[str(TERMINAL_API)])
        package = importlib.util.module_from_spec(spec)
        sys.modules['terminal_api_e2e'] = package
        spec.loader.exec_module(package)
    return importlib.import_module(f'terminal_api_e2e.{module}')


def capability_refusal(capability, display_name):
    """A 403 in edge-bff's shape, as p3c-int's forward_terminal answers it (terminal_access.check)."""
    return {'error': {'code': 'CAPABILITY_REQUIRED', 'message': REFUSAL_WORDS,
                      'details': {'capability': capability, 'display_name': display_name}}}


class FakeTerminalApi:
    """terminal-api's gateway routes on 127.0.0.1 (the shapes of verification/terminal_api/terminal_look/serve.mjs and of
    tests/test_watchlist_page.py). Switches give the answers Phase 3c gives a capped plan (CONTRACT.md 8b "3c in
    detail"): `refuse` (a route prefix answered with a refusal), `tickers` (the tickers /bundle serves), `locked` (the
    datasets /bundle answers {locked, capability}).

    `apply_header` (EXEC-MU-ACCOUNTS re-check R2-32): the fake reads the x-terminal-capabilities edge-bff really sends
    and answers as terminal-api decides with its own code (terminal_api(): entitlements.parse_capabilities, refcut.build,
    cut.build): a plan without the dataset `reference` gets its own copy of each reference file as a relative cut URL, a
    dataset outside the plan is locked, a capped dated dataset is a cut, and both are served by the GET routes edge-bff
    relays byte for byte. Every answer to an owner call acknowledges the header it read (re-check R2-4)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.calls, self.downloads = [], []
        self.objects = {}            # bucket key -> bytes
        self.refs = {
            'tickers': gz({'columns': ['ticker', 'name', 'type', 'sector'], 'ticker': list(TICKERS),
                           'name': [v[0] for v in TICKERS.values()], 'type': [v[1] for v in TICKERS.values()],
                           'sector': [v[2] for v in TICKERS.values()]}),
            'brokers': gz({'columns': ['code', 'name', 'type'], 'code': ['YP', 'CC'], 'name': ['YP', 'CC'], 'type': ['Domestic', 'Foreign']}),
            'logos': gz({'columns': ['ticker', 'sha256'], 'ticker': [], 'sha256': []}),
        }
        sample = ROOT / 'watchlist' / 'tests' / 'fixture' / 'watchlist-stocks.sample.json'
        self.pages = {'watchlist': {'watchlist-stocks': gzip.compress(sample.read_bytes(), mtime=0)}, 'overview': {}, 'radar': {}}
        self.refuse, self.locked, self.tickers = {}, set(), None
        self.apply_header, self.cuts = False, {}
        fake = self

        def capabilities(headers):
            """terminal-api's Capabilities of the owner header edge-bff sent, or None (no header, or one holding *)."""
            raw = headers.get('x-terminal-capabilities')
            if not raw or not fake.apply_header:
                return None
            ent = terminal_api('entitlements')
            caps = ent.parse_capabilities(raw, ('price', 'broker', 'events', 'yield', 'intraday', 'reference'))
            return None if caps.admin else caps

        def own_copy(kind, key, body):
            sha_ = sha(body)
            fake.cuts[f'{kind}/{sha_}'] = body
            return sha_

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def answer(self, status, body=None, raw=None, ctype='application/json'):
                data = raw if raw is not None else json.dumps(body).encode()
                self.send_response(status)
                self.send_header('Content-Type', ctype)
                caps = self.headers.get('x-terminal-capabilities')
                if caps:                                  # terminal-api acknowledges the owner header (re-check R2-4)
                    self.send_header('x-terminal-capabilities-applied', f"1 {json.loads(caps)['version']}")
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def one(self, method):
                length = int(self.headers.get('content-length') or 0)
                raw = self.rfile.read(length) if length else b''
                path = self.path.split('?')[0]
                with fake.lock:
                    fake.calls.append({'method': method, 'path': self.path, 'body': raw.decode(errors='replace'),
                                       'headers': {k.lower(): v for k, v in self.headers.items()}})
                if path.startswith('/bucket/'):
                    body = fake.objects.get(path[len('/bucket/'):])
                    return self.answer(200, raw=body, ctype='application/gzip') if body is not None else self.answer(404, {'error': 'not_found'})
                if self.headers.get('x-terminal-proxy-key') != TERMINAL_KEY:
                    return self.answer(401, {'error': 'unauthorized'})
                api = '/api/terminal/v1/'
                if not path.startswith(api):
                    return self.answer(404, {'error': 'not_found'})
                route = path[len(api):]
                for prefix, (status, refusal) in fake.refuse.items():
                    if route.startswith(prefix):
                        return self.answer(status, refusal)
                caps = capabilities(self.headers)
                if method == 'GET' and (route.startswith('cut/') or route.endswith('/cut')):
                    body = fake.cuts.get(f'{route.rsplit("/", 1)[0] if route.endswith("/cut") else route}/'
                                         f'{self.path.split("sha256=")[-1]}')
                    if body is None:
                        return self.answer(404, {'error': 'no_cut'})
                    return self.answer(200, raw=body, ctype='application/gzip')
                if method == 'GET' and route.startswith('reference/'):
                    name = route.split('/', 1)[1]
                    if name not in fake.refs:
                        return self.answer(404, {'error': 'unknown_reference'})
                    if caps is not None and not caps.dataset_ok('reference'):
                        # terminal-api's refcut.py: the plan's own copy, announced in the shape of a cut
                        refcut = terminal_api('refcut')
                        copy, _ = refcut.encode(refcut.build(json.loads(gzip.decompress(fake.refs[name])), name, caps))
                        sha_ = own_copy(f'reference/{name}', name, copy)
                        doc = json.loads(gzip.decompress(copy))
                        return self.answer(200, {'url': f'/api/terminal/v1/reference/{name}/cut?sha256={sha_}',
                                                 'sha256': sha_, 'bytes': len(copy), 'rows': len(doc[doc['columns'][0]]),
                                                 'expires_in_seconds': 0})
                    fake.objects[f'ref/{name}'] = fake.refs[name]
                    return self.answer(200, {'url': f'{BUCKET}/ref/{name}', 'sha256': sha(fake.refs[name]),
                                             'bytes': len(fake.refs[name]), 'rows': 1})
                if method == 'POST' and route == 'bundle':
                    body = json.loads(raw or b'{}')
                    ticker, out = body.get('ticker'), {}
                    if ticker not in TICKERS:
                        return self.answer(404, {'error': 'unknown_ticker'})
                    if fake.tickers is not None and ticker not in fake.tickers:
                        return self.answer(403, capability_refusal('terminal.tickers', 'Terminal tickers'))
                    if caps is not None and not caps.ticker_ok(ticker):
                        return self.answer(403, {'error': 'capability_required', 'capability': 'terminal.tickers',
                                                 'message': 'The ticker is not in the plan.'})
                    for d in body.get('datasets') or []:
                        if d in fake.locked or (caps is not None and not caps.dataset_ok(d)):
                            out[d] = {'locked': True, 'capability': f'terminal.dataset:{d}'}
                        elif d == 'price':
                            rows = price_rows(start=TICKERS[ticker][3])
                            doc = {'schema_version': 1, 'dataset': 'price-pack', 'ticker': ticker, 'columns': ['d', 'o', 'h', 'l', 'c', 'v'],
                                   **{c: [r[k] for r in rows] for k, c in enumerate(['d', 'o', 'h', 'l', 'c', 'v'])}}
                            b = gz(doc)
                            fake.objects[f'price/{ticker}'] = b
                            out[d] = {'data_through': rows[-1][0], 'first_year': int(rows[0][0][:4]),
                                      'files': [{'pack': 'price', 'url': f'{BUCKET}/price/{ticker}', 'sha256': sha(b),
                                                 'bytes': len(b), 'rows': len(rows)}]}
                            if caps is not None and caps.history_days is not None:
                                # terminal-api's cut.py: exactly the plan's last N days, relayed by edge-bff
                                cut = terminal_api('cut')
                                cut_doc = cut.build([doc], 'price', caps.history_days, rows[-1][0])
                                c, _ = cut.encode(cut_doc)
                                sha_ = own_copy(f'cut/{ticker}/price', ticker, c)
                                out[d]['files'] = [{'year': None, 'pack': 'cut', 'sha256': sha_, 'bytes': len(c),
                                                    'rows': len(cut_doc['d']),
                                                    'url': f'/api/terminal/v1/cut/{ticker}/price?sha256={sha_}'}]
                        else:
                            out[d] = {'files': [], 'data_through': None}
                    return self.answer(200, {'ticker': ticker, 'datasets': out, 'expires_in_seconds': 120})
                if method == 'GET' and route.startswith('logo/'):
                    return self.answer(404, {'error': 'no_logo'})
                if route in fake.pages:
                    files = fake.pages[route]
                    if method == 'GET':
                        return self.answer(200, {'finished_at': '2026-11-16T10:00:00Z', 'files': {
                            n: {'sha256': sha(b), 'bytes': len(b), 'rows': 14, 'as_of': '2026-11-13'} for n, b in files.items()}})
                    granted = []
                    for n in json.loads(raw or b'{}').get('names') or []:
                        if n not in files:
                            return self.answer(404, {'error': 'not_published'})
                        fake.objects[f'page/{route}/{n}'] = files[n]
                        granted.append({'name': n, 'url': f'{fake.url}/bucket/page/{route}/{n}', 'sha256': sha(files[n]),
                                        'bytes': len(files[n])})
                    return self.answer(200, {'files': granted})
                return self.answer(404, {'error': 'not_found'})

            def do_GET(self):
                self.one('GET')

            def do_POST(self):
                self.one('POST')

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

        class Bucket(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                key = self.path.split('?')[0].lstrip('/')
                body = fake.objects.get(key)
                with fake.lock:
                    fake.downloads.append(key)
                self.send_response(200 if body is not None else 404)
                self.send_header('Content-Type', 'application/gzip')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Length', str(len(body or b'')))
                self.end_headers()
                self.wfile.write(body or b'')

        certs = tempfile.mkdtemp(prefix='e2e-bucket-')
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=' + BUCKET_HOST, '-days', '1',
                        '-keyout', certs + '/k.pem', '-out', certs + '/c.pem'], check=True, capture_output=True)
        self.tls = ThreadingHTTPServer(('127.0.0.1', 0), Bucket)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(certs + '/c.pem', certs + '/k.pem')
        self.tls.socket = tls.wrap_socket(self.tls.socket, server_side=True)
        threading.Thread(target=self.tls.serve_forever, daemon=True).start()

    def browser_args(self):
        return ['--no-sandbox', '--no-proxy-server', '--ignore-certificate-errors',
                f'--host-resolver-rules=MAP {BUCKET_HOST}:443 127.0.0.1:{self.tls.server_address[1]}']

    def close(self):
        for server in (self.server, self.tls):
            server.shutdown()
            server.server_close()


def db(store, sql, *args):
    with store.connect() as c:
        cur = c.execute(sql, args)
        return cur.fetchall() if cur.description else cur.rowcount


def last_code(store, email):
    rows = [r for r in db(store, 'SELECT * FROM edge_bff.email_outbox WHERE to_email=%s ORDER BY outbox_id', email)
            if r['purpose'] in ('register', 'reset')]
    return rows[-1]['payload']['mask'][0]


class Live:
    """edge-bff with the switch on, on a real local server, with its fakes (module docstring)."""

    def __init__(self, settings, store, monkeypatch, **change):
        from test_screener import FakeScreenerWorker
        from test_backtest import FakeWorker
        self.store = store
        self.terminal, self.screener, self.backtest = FakeTerminalApi(), FakeScreenerWorker(), FakeWorker()
        for name, folder in (('BACKTEST_APP', 'backtest'), ('SCREENER_APP', 'screener'), ('RADAR_APP', 'radar'),
                             ('OVERVIEW_APP', 'overview'), ('WATCHLIST_APP', 'watchlist')):
            if (ROOT / folder / 'dist' / 'index.html').is_file():
                monkeypatch.setattr(main, name, ROOT / folder / 'dist')
        self.sock = socket.socket(); self.sock.bind(('127.0.0.1', 0)); port = self.sock.getsockname()[1]
        self.settings = dataclasses.replace(
            settings, origin=f'http://127.0.0.1:{port}', multiuser=True, code_secret='c' * 40, mfa_key='m' * 40,
            worker_enabled=True, poll_seconds=0.02,
            terminal_url=self.terminal.url, terminal_proxy_key=TERMINAL_KEY,
            screener_worker_url=self.screener.url, screener_worker_key=SCREENER_KEY, screener_timeout_seconds=20,
            backtest_worker_url=self.backtest.url, backtest_worker_key=BACKTEST_KEY, backtest_timeout_seconds=30,
            backtest_max_result_bytes=2 ** 20, **change)
        self.orc = FakeOrc()
        self.app = create_app(self.settings, store, self.orc)
        self.app.state.auth_flows.pwned_fetch = lambda prefix: ''          # never the real range API in a test
        self.server = uvicorn.Server(uvicorn.Config(self.app, log_level='critical', access_log=False))
        self.thread = threading.Thread(target=self.server.run, kwargs={'sockets': [self.sock]}, daemon=True)
        self.thread.start()
        for _ in range(300):
            if self.server.started:
                break
            time.sleep(0.02)
        assert self.server.started
        self.origin = self.settings.origin

    def close(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)
        self.sock.close()
        self.terminal.close(); self.screener.close(); self.backtest.close()

    def user_id(self, username):
        return db(self.store, 'SELECT user_id FROM edge_bff.users WHERE username=%s', username)[0]['user_id']

    def subscribe(self, username, plan):
        """The plan as the admin (Phase 4) will give it: the active subscription ended, one active manual one, no end."""
        uid = self.user_id(username)
        db(self.store, "UPDATE edge_bff.subscriptions SET status='cancelled' WHERE user_id=%s AND status='active'", uid)
        db(self.store, '''INSERT INTO edge_bff.subscriptions(user_id, plan_key, status, expires_at, provider, provider_ref)
            VALUES (%s, %s, 'active', NULL, 'manual', 'e2e')''', uid, plan)
        return uid

    def totp_code(self, user_id):
        row = db(self.store, 'SELECT nonce FROM edge_bff.mfa_totp WHERE user_id=%s', user_id)[0]
        return mfa.code_at(mfa.secret_of(self.settings.mfa_key, user_id, bytes(row['nonce'])), mfa.step_now())


def browser_context(browser, **kw):
    ctx = browser.new_context(viewport={'width': 1440, 'height': 900}, ignore_https_errors=True, **kw)
    ctx.route('https://fonts.*/*', lambda route: route.abort())
    return ctx


def register(page, live, username, email):
    """/register, then the emailed code on /verify, which signs the new account in (user decision)."""
    page.goto(live.origin + '/login')
    page.get_by_role('link', name='Create account').click()
    for label, value in (('Username', username), ('First name', 'Ana'), ('Last name', 'Putri'), ('Email', email),
                         ('Phone', '0812 3456 7890'), ('Password', PASSWORD), ('Repeat password', PASSWORD)):
        page.get_by_label(label, exact=True).fill(value)
    page.get_by_role('button', name='Create account').click()
    page.wait_for_function("() => location.pathname === '/verify'")
    page.get_by_label('Code', exact=True).fill(last_code(live.store, email))
    page.get_by_role('button', name='Verify').click()
    signed_in_workspace(page)


def signed_in_workspace(page, seconds=15):
    """The shell signed in on its landing page: the Monitor for an account that holds it, else the Terminal (fix round,
    re-check R2-14: a new account holds no monitor.view, decision D1)."""
    page.wait_for_function("() => window.Edge && Edge.auth !== null && ['/monitor', '/terminal'].includes(location.pathname)",
                           timeout=seconds * 1000)


def sign_in(page, live, login, password):
    page.goto(live.origin + '/login')
    page.get_by_label('Login', exact=True).fill(login)
    page.get_by_label('Password', exact=True).fill(password)
    page.get_by_role('button', name='Sign In').click()


def admin_sign_in(page, live):
    """User #1's first switch-on sign-in: the password, then the authenticator set-up (contract section 4)."""
    sign_in(page, live, 'owner', 'local-test-password')
    page.wait_for_function("() => location.pathname === '/mfa'")
    page.locator('svg.auth-qr path').wait_for()
    uid = db(live.store, 'SELECT user_id FROM edge_bff.users WHERE owner_key=%s', live.settings.owner)[0]['user_id']
    page.get_by_label('Code', exact=True).fill(live.totp_code(uid))
    page.get_by_label('I have saved my recovery codes').check()
    page.get_by_role('button', name='Continue').click()
    page.get_by_placeholder('Ask a research question…').wait_for(timeout=15000)
    return uid


def shell_navigate(page, path):
    """The shell's own route change (no reload), as its rail and edge-nav do (index.html go(): pushState, then the
    popstate listener's setPath)."""
    page.evaluate("p => { history.pushState({}, '', p); dispatchEvent(new PopStateEvent('popstate')) }", path)


def terminal_drawn(page, seconds=40):
    """(drawn, text) of the Terminal frame: drawn when its chart canvases exist and no 'Loading' remains."""
    f = page.frame_locator('iframe.terminal-frame')
    text = ''
    for _ in range(seconds):
        time.sleep(1)
        try:
            text = f.locator('body').inner_text(timeout=1000)
            if f.locator('canvas').count() and 'Loading' not in text:
                return True, text
            if REFUSAL_WORDS in text:
                return False, text
        except Exception:  # noqa: BLE001 - the frame is still loading
            pass
    return False, text
