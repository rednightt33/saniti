"""EXEC-TERMINAL-FLOW-IND live check (set-up of popout_live_check.py): the 39 Flow indicators on the local Terminal
with dev data. Adds every FL indicator with its defaults, reads the legend values at the last candle and a date before
it (`window.marketLabIndicators.values()`), the menu subgroups, the settings dialog fields of each, and times a
recompute on the largest tickers. Writes <out>/flow_values.json for the comparison with the independent oracle.

Environment: EDGE_TEST_POSTGRES_URL (disposable server), EDGE_TEST_CHROMIUM (optional), the Railway CLI logged in.
Usage: python flow_indicators_live_check.py <out dir> [TICKER ...]
"""
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

ROOT = Path('/home/user/saniti')
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
        page.on('pageerror', lambda e: errors.append(str(e) + ' | ' + (e.stack or '')[:600]))
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
        page.evaluate("localStorage.setItem('ml.tf', 'D')"); page.goto(f'http://127.0.0.1:{port}/terminal-app/', wait_until='load', timeout=120000)
        ready = "() => document.querySelector('#flowSummary .flow-stat') && (document.getElementById('flowNote').hidden || !/^Loading/.test(document.getElementById('flowNote').textContent))"
        page.wait_for_function(ready, timeout=180000); page.wait_for_timeout(1500)
        J = lambda js: page.evaluate(js)
        report['tickers'] = {}
        for tk in tickers:
            if tk != tickers[0]:
                page.evaluate(f"localStorage.setItem('ml.symbol', '{tk}')"); page.reload(wait_until='load')
                page.wait_for_function(ready, timeout=180000); page.wait_for_timeout(1500)
            # wait for the full broker history (the indicators recompute when it arrives)
            page.wait_for_function("() => window.__flowAll === true || document.getElementById('flowNote').hidden", timeout=240000)
            page.wait_for_timeout(4000)
            res = page.evaluate("""() => {
              const I = window.marketLabIndicators; I.removeAll && I.removeAll();
              const ids = I.flowIds(), out = {}, t0 = performance.now();
              for (const id of ids) { const s = performance.now(); I.add(id); out[id] = { ms: Math.round(performance.now() - s) } }
              const total = Math.round(performance.now() - t0);
              const vals = I.values();
              return { total, ids, timing: out, values: vals };
            }""")
            # the calculation alone, per indicator at its defaults (the drawing excluded)
            report.setdefault('compute_ms', {})[tk] = page.evaluate("""() => {
              const I = window.marketLabIndicators, out = {};
              for (const d of I.defs.filter(d => d.flow)) {
                const p = Object.fromEntries(d.inputs.filter(f => f.def !== undefined).map(f => [f.key, f.def]));
                const s = performance.now(); d.compute(p); out[d.id] = Math.round((performance.now() - s) * 10) / 10;
              }
              return out;
            }""")
            report['tickers'][tk] = {'total_ms': res['total'], 'slowest': sorted(res['timing'].items(), key=lambda x: -x[1]['ms'])[:5],
                                     'n': len(res['ids'])}
            json.dump(res['values'], open(out / f'flow_values_{tk}.json', 'w'))
            page.screenshot(path=str(out / f'flow_all_{tk}.png'))
        # menu subgroups and one dialog
        page.click('#indBtn'); page.wait_for_timeout(300)
        report['menu_groups'] = J("[...document.querySelectorAll('#indList .ind-group')].map(g => g.textContent)")
        page.fill('#indSearch', 'bandar'); page.wait_for_timeout(200)
        report['search_bandar'] = J("[...document.querySelectorAll('#indList .ind-item')].map(i => i.dataset.ind)")
        page.screenshot(path=str(out / 'menu_bandar.png'))
        page.keyboard.press('Escape')
        J("window.marketLabIndicators.removeAll()"); J("window.marketLabIndicators.add('FL01')"); page.wait_for_timeout(500)
        page.click('.ind-row[data-def="FL01"] [data-act="cfg"]'); page.wait_for_timeout(300)
        report['dialog_FL01'] = J("[...document.querySelectorAll('.idlg-body .idlg-row')].map(r => r.innerText.replace(/\\s+/g, ' ').trim())")
        page.screenshot(path=str(out / 'dialog_FL01.png'))
        report['errors'] = errors
        browser.close()
finally:
    server.should_exit = True
    time.sleep(.5)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)'); c.execute('DROP ROLE IF EXISTS edge_bff_runtime')
print(json.dumps(report, indent=1, ensure_ascii=False))
