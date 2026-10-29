"""The page timing scripts never show a credential (review of measure, EXEC-MU-RUNTIME Phase 0): neither the Terminal's
(verification/terminal_api/page_timing_dev.py), the Screener's (verification/screener/page_timing_dev.py) nor the
Backtest's (verification/backtest/page_timing_dev.py).

A failed Playwright API request raises an error whose message ends with a call log that lists the request's headers,
the session cookie and the CSRF token among them (seen with Playwright 1.56). Each script is run here against a local
stand-in for edge-bff that signs the script in (a session cookie and a CSRF token of test values), serves pages that
end every page step at once (an alert in the frame), and hangs up on the first route the script times on its own
(the session route): the script must stop with the error named, and no credential value in its output or its files.

Run: EDGE_TEST_CHROMIUM=<chromium binary> python -m pytest -q verification/terminal_api/test_page_timing_scripts.py
(any Python with Playwright; the edge-bff test venv has it)."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

pytest.importorskip('playwright')

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = {'terminal': ROOT / 'verification/terminal_api/page_timing_dev.py',
           'screener': ROOT / 'verification/screener/page_timing_dev.py',
           'backtest': ROOT / 'verification/backtest/page_timing_dev.py'}
COOKIE, CSRF, PASSWORD = 'cookie-value-must-not-show-3f9a', 'csrf-value-must-not-show-77c1', 'password-must-not-show-0b2e'
PAGES = {
    '/terminal': '<!doctype html><iframe src="/terminal-app/"></iframe>',
    '/terminal-app/': '<!doctype html><div role="alert">stand-in: no chart</div>',
    '/screener': '<!doctype html><iframe src="/screener-app/"></iframe>',
    '/screener-app/': '<!doctype html><div id="app"></div><div id="resPane"><div role="alert">stand-in: no results</div></div>',
    '/backtest': '<!doctype html><iframe src="/backtest-app/"></iframe>',
    '/backtest-app/': ('<!doctype html><button class="js-run">Run</button><select data-k="ticker"><option>BBRI</option></select>'
                       '<button data-tpl="Divergence + flow">flow</button>'),
}


class StandIn(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def answer(self, status, body, kind='text/html', headers=()):
        data = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(data)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length') or 0))
        if self.path == '/api/v1/auth/sign-in':
            return self.answer(200, json.dumps({'csrf_token': CSRF}), 'application/json',
                               [('Set-Cookie', f'edge_session={COOKIE}; Path=/; HttpOnly')])
        self.answer(404, '')

    def do_GET(self):
        if self.path == '/api/v1/auth/session':
            self.close_connection = True       # no answer: the client sees the connection hang up
            return
        if self.path in PAGES:
            return self.answer(200, PAGES[self.path])
        self.answer(404, '')


@pytest.fixture
def stand_in():
    server = ThreadingHTTPServer(('127.0.0.1', 0), StandIn)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_address[1]}'
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize('name', sorted(SCRIPTS))
def test_a_failed_request_names_the_error_and_shows_no_credential(name, stand_in, tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy')}
    env.update(EDGE_TIMING_BASE=stand_in, EDGE_TIMING_LOGIN='owner', EDGE_TIMING_PASSWORD=PASSWORD)
    run = subprocess.run([sys.executable, str(SCRIPTS[name]), str(tmp_path / 'out')], env=env, capture_output=True,
                         text=True, timeout=240)
    shown = run.stdout + run.stderr
    assert run.returncode != 0 and 'socket hang up' in shown, shown     # it stopped at the hung-up session route
    for secret in (COOKIE, CSRF, PASSWORD):
        assert secret not in shown, shown
    assert 'Call log' not in shown, shown
    for f in (tmp_path / 'out').rglob('*'):
        if f.suffix in ('.json', '.txt'):
            text = f.read_text()
            assert COOKIE not in text and CSRF not in text and PASSWORD not in text, f
