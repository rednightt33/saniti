"""EXEC-INTRADAY-FEATURES C3-C4 indicator check (based on intraday_live_check.py): the 5M, 15M, 1H and 4H buttons the manifest offers (each reloads the page),
then D; per timeframe the candles, the axis, the Flow labels and its Daily tag, the Broker panel tag, the annotation
markers and page errors. Usage: python intraday_live_check.py <out dir> [TICKER]
Based on timeframe_live_check.py (same environment)."""

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
IND = [{'def': 'vwap'}, {'def': 'adr'}, {'def': 'hist_vol'}, {'def': 'FL24'}]
try:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page(); errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        def bucket(route):
            with urllib.request.urlopen(route.request.url, timeout=60) as r:
                status, body, ctype = r.status, r.read(), r.headers.get('content-type', 'application/octet-stream')
            route.fulfill(status=status, body=body, headers={'content-type': ctype, 'access-control-allow-origin': f'http://127.0.0.1:{port}'})
        page.route('https://*.t3.storageapi.dev/**', bucket)
        page.request.post(f'http://127.0.0.1:{port}/api/v1/auth/sign-in', headers={'Origin': settings.origin}, data={'login': 'owner', 'password': 'local-live-check'})
        page.goto(f'http://127.0.0.1:{port}/terminal-app/')
        values = {}
        for tf in ('D', '1h'):
            page.evaluate(f"""() => {{ localStorage.setItem('ml.symbol', '{tickers[0]}'); localStorage.setItem('ml.tf', '{tf}');
                localStorage.setItem('ml.ind.v1', JSON.stringify({json.dumps(IND)})) }}""")
            page.goto(f'http://127.0.0.1:{port}/terminal-app/', wait_until='load', timeout=120000)
            page.wait_for_function("() => window.__flowAll === true", timeout=240000)
            page.wait_for_timeout(1500)
            values[tf] = page.evaluate("""() => ({ list: window.marketLabIndicators.list().map(i => ({ def: i.def, params: i.params,
                 values: Object.fromEntries(Object.entries(i.values || {}).filter(([k, v]) => Array.isArray(v)).map(([k, v]) => [k, v.slice(-400)])) })) })""")
            page.screenshot(path=str(out / f'ind-{tf}.png'))
        report['errors'] = errors
        browser.close()
finally:
    server.should_exit = True
    time.sleep(.5)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)'); c.execute('DROP ROLE IF EXISTS edge_bff_runtime')
(out / 'indicator_values.json').write_text(json.dumps(values))
print(json.dumps({'errors': report.get('errors'), 'defs': {tf: [(i['def'], sorted(i['values'])) for i in v['list']] for tf, v in values.items()},
                  'hist_vol_param': {tf: [i['params'].get('annualization_periods') for i in v['list'] if i['def'] == 'hist_vol'] for tf, v in values.items()}}, indent=1))
