"""EXEC-TERMINAL-WM live check: the D, W and M buttons (each reloads the page), the Flow and Statistics labels, the
annotation markers and page errors per timeframe. Usage: python timeframe_live_check.py <out dir> [TICKER]
Based on terminal_live_check.py (same environment)."""

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/edge-bff'))
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.security import password_verifier  # noqa: E402

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
tickers = sys.argv[2:] or ['BBCA']
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'terminal-api', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)

admin = os.environ['EDGE_TEST_POSTGRES_URL']
name = 'edge_live_' + uuid.uuid4().hex[:10]
p = urlsplit(admin); db = urlunsplit((p.scheme, p.netloc, '/' + name, p.query, p.fragment))
with psycopg.connect(admin, autocommit=True) as c:
    c.execute(f'CREATE DATABASE "{name}"')
with psycopg.connect(db, autocommit=True) as c:
    for m in ('20261008_002_create_edge_bff.sql', '20261012_008_edge_bff_conversation_hidden.sql',
              '20261024_002_edge_bff_conversation_branch.sql'):
        c.execute((ROOT / 'database/migrations' / m).read_text())

port = 18765
settings = Settings(database_url=db, orc_url='http://orc.invalid', orc_key='local', owner='local-owner', login='owner',
                    password_verifier=password_verifier('local-live-check'), session_secret='local-live-secret-' * 3,
                    origin=f'http://127.0.0.1:{port}', environment='local', secure_cookie=False, worker_enabled=False,
                    terminal_url='https://' + v['RAILWAY_PUBLIC_DOMAIN'], terminal_proxy_key=v['TERMINAL_PROXY_KEY'])
server = uvicorn.Server(uvicorn.Config(create_app(settings), host='127.0.0.1', port=port, log_level='warning'))
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(.05)

from playwright.sync_api import sync_playwright  # noqa: E402

report = {}
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page(); errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        def bucket(route):
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(route.request.url, timeout=60) as r:
                        status, body, ctype = r.status, r.read(), r.headers.get('content-type', 'application/octet-stream')
                    break
                except urllib.error.HTTPError as e:
                    status, body, ctype = e.code, e.read(), 'text/plain'; break
                except Exception:
                    if attempt == 2: raise
            route.fulfill(status=status, body=body, headers={'content-type': ctype, 'access-control-allow-origin': f'http://127.0.0.1:{port}'})
        page.route('https://*.t3.storageapi.dev/**', bucket)
        page.request.post(f'http://127.0.0.1:{port}/api/v1/auth/sign-in', headers={'Origin': settings.origin}, data={'login': 'owner', 'password': 'local-live-check'})
        page.goto(f'http://127.0.0.1:{port}/terminal-app/')
        page.evaluate(f"localStorage.setItem('ml.symbol', '{tickers[0]}'); localStorage.setItem('ml.broker.collapsed', '0'); localStorage.setItem('ml.stats.collapsed', '0'); localStorage.setItem('ml.flow.collapsed', '0')")
        page.goto(f'http://127.0.0.1:{port}/terminal-app/', wait_until='load', timeout=120000)
        for tf in ('W', 'M', 'D'):
            page.click(f'#timeframeGroup [data-timeframe="{tf}"]')
            page.wait_for_load_state('load'); page.wait_for_function("() => document.querySelector('#flowSummary .flow-stat')", timeout=180000)
            page.wait_for_function("() => document.getElementById('flowNote').hidden || !/^Loading/.test(document.getElementById('flowNote').textContent)", timeout=180000)
            page.wait_for_timeout(1500)
            cb = page.locator('#chart').bounding_box(); page.mouse.move(cb['x'] + cb['width'] * .7, cb['y'] + cb['height'] * .4); page.wait_for_timeout(300)
            report[tf] = page.evaluate("""() => ({ active: document.querySelector('#timeframeGroup .active')?.dataset.timeframe,
               flow: document.getElementById('flowSummary').innerText.replace(/\\s+/g, ' '),
               tip: document.getElementById('flowTip').innerText.replace(/\\s+/g, ' '),
               stats: document.getElementById('statsRange').textContent,
               vol_label: document.querySelector('#statsPanel .st[data-sec=vol] small')?.textContent,
               weekday_hidden: document.querySelector('#seasToggle [data-mode=weekday]')?.hidden,
               markers: document.querySelectorAll('.ev-mk').length })""")
            page.screenshot(path=str(out / f'tf-{tf}.png'))
        report['errors'] = errors
        browser.close()
finally:
    server.should_exit = True
    time.sleep(.5)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)'); c.execute('DROP ROLE IF EXISTS edge_bff_runtime')
print(json.dumps(report, indent=1, ensure_ascii=False))
