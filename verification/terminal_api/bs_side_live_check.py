"""EXEC-TERMINAL-BS-SIDE live check (set-up of popout_live_check.py): the Broker summary window's two sides (net
buyers left, net sellers right, largest first; Gross; All; search; the CSV), Alt+B (choose a period on the chart for the
right panel, from a collapsed panel) and the blue crosshair while choosing (it follows the pointer, then is put back).

Environment: EDGE_TEST_POSTGRES_URL (disposable server), EDGE_TEST_CHROMIUM (optional), the Railway CLI logged in.
Usage: python bs_side_live_check.py <out dir> [TICKER]
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
        page.evaluate("localStorage.setItem('ml.tf', 'D')"); page.goto(f'http://127.0.0.1:{port}/terminal-app/', wait_until='load', timeout=120000)
        ready = "() => document.querySelector('#flowSummary .flow-stat') && (document.getElementById('flowNote').hidden || !/^Loading/.test(document.getElementById('flowNote').textContent))"
        page.wait_for_function(ready, timeout=180000); page.wait_for_timeout(1500)
        J = lambda js: page.evaluate(js)
        J = lambda js: page.evaluate(js)
        ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin=f'http://127.0.0.1:{port}')
        W = '.fw[data-win="bs"]'
        side = """(w) => { const t = document.querySelector(`.fw[data-win=${w}] .pw-bs`); if (!t) return null;
          const rows = [...t.querySelectorAll('tbody tr')].map(r => [...r.children].map(c => c.innerText.trim()));
          const num = s => { if (!s) return null; const m = s.replace(/[+,%]/g, '').match(/^(-?[0-9.]+)([KMBT]?)$/); return m ? +m[1] * ({ '':1, K:1e3, M:1e6, B:1e9, T:1e12 })[m[2]] : NaN };
          const L = rows.map(r => [r[1], num(r[2])]).filter(x => x[0]), R = rows.map(r => [r[12], num(r[11])]).filter(x => x[0]);
          const desc = a => a.every((x, i) => !i || Math.abs(a[i - 1][1]) >= Math.abs(x[1]));
          return { head: [...t.querySelectorAll('thead th')].map(th => th.innerText.trim()), first: rows.slice(0, 3).map(r => r.join(' | ')),
                   total: [...t.querySelectorAll('tfoot td')].map(c => c.innerText.trim()).join(' | '), left: L.length, right: R.length,
                   left_desc: desc(L), right_desc: desc(R), left_sign: L.every(x => x[1] > 0), right_sign: R.every(x => x[1] < 0),
                   foot: document.querySelector(`.fw[data-win=${w}] .pw-foot`)?.textContent } }"""
        page.click('.st[data-sec="bs"] .st-pop'); page.wait_for_selector(W + ' .pw-bs tbody tr'); page.wait_for_timeout(300)
        page.click(W + ' [data-k="mode"][data-v="net"]'); page.click(W + ' [data-k="limit"][data-v="20"]'); page.wait_for_timeout(200)
        report['net20'] = page.evaluate(side, 'bs'); page.screenshot(path=str(out / 'bs-net20.png'))
        page.click(W + ' [data-k="limit"][data-v="all"]'); page.wait_for_timeout(200)
        report['net_all'] = page.evaluate(side, 'bs')
        page.click(W + ' [data-k="mode"][data-v="gross"]'); page.click(W + ' [data-k="limit"][data-v="10"]'); page.wait_for_timeout(200)
        g = page.evaluate(side, 'bs'); g.pop('left_sign'); g.pop('right_sign'); report['gross10'] = g; page.screenshot(path=str(out / 'bs-gross10.png'))
        page.click(W + ' [data-k="mode"][data-v="net"]'); page.click(W + ' [data-k="limit"][data-v="20"]')
        page.fill(W + ' .pw-search', 'Y'); page.wait_for_timeout(200)
        report['search_Y'] = page.evaluate(side, 'bs')['first']
        page.fill(W + ' .pw-search', ''); page.wait_for_timeout(200)
        page.dispatch_event(W, 'pointerdown'); page.click(W + ' .pw-bs tbody tr:first-child td:nth-child(13)'); page.wait_for_timeout(300)
        report['pick_right'] = {'picked': J("document.querySelector('.fw[data-win=bs] .pw-bs td.sel')?.dataset.b"),
                                'inventory': J("[...document.querySelectorAll('#invLegend .rp-chip')].map(c => c.innerText.split(/\\s/)[0])")}
        page.click(W + ' .fw-tools [data-tool="csv"]'); page.wait_for_timeout(300)
        csv = J("navigator.clipboard.readText()").splitlines()
        report['csv'] = {'head': csv[0] if csv else None, 'lines': len(csv), 'first': csv[1] if len(csv) > 1 else None, 'last': csv[-1] if csv else None}
        page.click(W + ' [data-act="close"]'); page.wait_for_timeout(200)
        # Alt+B from a collapsed right panel: the chart takes the pointer, the crosshair follows it in blue
        page.click('#rpCollapse') if J("!document.getElementById('workspace').classList.contains('right-collapsed')") else None
        page.wait_for_timeout(300)
        before = J("document.querySelector('#bsRange .rp-date')?.textContent")
        page.mouse.move(5, 5); page.keyboard.press('Alt+KeyB'); page.wait_for_timeout(200)
        report['altb_layer'] = J("({ layer: !!document.querySelector('.rs-layer'), hint: document.querySelector('.rs-hint')?.textContent })")
        cb = page.locator('#chart').bounding_box()
        page.mouse.move(cb['x'] + cb['width'] * .55, cb['y'] + cb['height'] * .4, steps=4); page.wait_for_timeout(200)
        page.screenshot(path=str(out / 'altb-hover.png'), clip={'x': cb['x'], 'y': cb['y'], 'width': cb['width'], 'height': cb['height'] + 30})
        legend = "() => [document.getElementById('flowTip')?.innerText.replace(/\\s+/g, ' ').slice(0, 60), document.querySelector('#invBody .rp-invdate')?.textContent]"
        report['hover_legend_1'] = J(legend)
        page.mouse.move(cb['x'] + cb['width'] * .75, cb['y'] + cb['height'] * .4, steps=4); page.wait_for_timeout(200)
        report['hover_legend_2'] = J(legend)
        page.mouse.click(cb['x'] + cb['width'] * .55, cb['y'] + cb['height'] * .4); page.wait_for_timeout(150)
        page.mouse.move(cb['x'] + cb['width'] * .7, cb['y'] + cb['height'] * .5, steps=4)
        page.screenshot(path=str(out / 'altb-between.png'), clip={'x': cb['x'], 'y': cb['y'], 'width': cb['width'], 'height': cb['height'] + 30})
        page.mouse.click(cb['x'] + cb['width'] * .7, cb['y'] + cb['height'] * .5); page.wait_for_timeout(800)
        report['altb_done'] = J("({ layer: !!document.querySelector('.rs-layer'), collapsed: document.getElementById('workspace').classList.contains('right-collapsed'), "
                                "bs: document.querySelector('#bsRange .rp-date')?.textContent, acc: document.querySelector('#accRange .rp-date, #accHint')?.textContent, "
                                "custom: document.querySelector('#bsRange .seg button.active')?.dataset.n })")
        report['bs_before'] = before
        page.mouse.move(cb['x'] + cb['width'] * .4, cb['y'] + cb['height'] * .3, steps=3); page.wait_for_timeout(200)
        page.screenshot(path=str(out / 'after-normal-crosshair.png'), clip={'x': cb['x'], 'y': cb['y'], 'width': cb['width'], 'height': cb['height'] + 30})
        # Esc cancels; Alt+B inside a text field does nothing
        page.keyboard.press('Alt+KeyB'); page.wait_for_timeout(150); page.keyboard.press('Escape'); page.wait_for_timeout(150)
        report['esc'] = J("!!document.querySelector('.rs-layer')")
        page.evaluate("() => { const i = document.createElement('input'); i.id = 'tmpIn'; document.body.appendChild(i); i.focus() }")
        page.keyboard.press('Alt+KeyB'); page.wait_for_timeout(150)
        report['typing'] = J("!!document.querySelector('.rs-layer')")
        report['errors'] = errors
        browser.close()
finally:
    server.should_exit = True
    time.sleep(.5)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)'); c.execute('DROP ROLE IF EXISTS edge_bff_runtime')
print(json.dumps(report, indent=1, ensure_ascii=False))
