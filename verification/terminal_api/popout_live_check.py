"""EXEC-TERMINAL-POPOUT W1 + I2 live check (based on terminal_live_check.py): the panel windows over the terminal page.
Opens Broker summary, Top brokers and Broker inventory as windows on a ticker (BMRI by default), reads their rows,
compares Broker inventory with the panel under the same filters, picks a broker from Broker summary, moves the
crosshair from the window, moves, resizes and pins windows, reloads (same windows, same places), docks one, and
reloads on the weekly timeframe.

Same set-up as terminal_live_check.py: a local edge-bff (built terminal page, disposable Postgres) forwards
/api/terminal to the deployed terminal-api with the gateway key (read into memory, never printed).
Environment: EDGE_TEST_POSTGRES_URL (disposable server), EDGE_TEST_CHROMIUM (optional), the Railway CLI logged in.
Usage: python popout_live_check.py <out dir> [TICKER]
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
        report['pop_buttons'] = J("[...document.querySelectorAll('.st-pop')].map(b => b.title)")
        # Broker summary window
        page.click('.st[data-sec="bs"] .st-pop'); page.wait_for_selector('.fw[data-win="bs"] .pw-t tbody tr'); page.wait_for_timeout(300)
        rows = "(w) => [...document.querySelectorAll(`.fw[data-win=${w}] .pw-t tbody tr`)].slice(0, 3).map(r => r.innerText.replace(/\\s+/g, ' '))"
        foot = "(w) => document.querySelector(`.fw[data-win=${w}] .pw-t tfoot`)?.innerText.replace(/\\s+/g, ' ')"
        sub = "(w) => document.querySelector(`.fw[data-win=${w}] .fw-sub`).textContent"
        report['bs_default'] = {'sub': page.evaluate(sub, 'bs'), 'rows': page.evaluate(rows, 'bs'), 'total': page.evaluate(foot, 'bs'),
                                'count': J("document.querySelectorAll('.fw[data-win=bs] .pw-t tbody tr[data-b]').length"),
                                'gap': J("document.querySelector('.fw[data-win=bs] .pw-gap')?.innerText")}
        page.screenshot(path=str(out / 'pop-bs.png'))
        page.click('.fw[data-win="bs"] [data-k="p"][data-v="1"]'); page.wait_for_timeout(200)
        page.click('.fw[data-win="bs"] [data-sort="bv"]'); page.wait_for_timeout(200)
        report['bs_1d_buyvalue'] = {'sub': page.evaluate(sub, 'bs'), 'rows': page.evaluate(rows, 'bs')}
        page.fill('.fw[data-win="bs"] .pw-search', 'YU'); page.wait_for_timeout(200)
        report['bs_search'] = page.evaluate(rows, 'bs')
        page.fill('.fw[data-win="bs"] .pw-search', ''); page.wait_for_timeout(200)
        page.click('.fw[data-win="bs"] [data-k="p"][data-v="view"]'); page.wait_for_timeout(200)
        report['bs_view'] = page.evaluate(sub, 'bs')
        # Top brokers window
        page.click('.st[data-sec="acc"] .st-pop'); page.wait_for_selector('.fw[data-win="acc"] .pw-t tbody tr'); page.wait_for_timeout(300)
        report['acc'] = {'sub': page.evaluate(sub, 'acc'), 'rows': page.evaluate(rows, 'acc')}
        # Broker inventory window, Foreign + Regular, against the panel with the same filters
        page.click('.st[data-sec="inv"] .st-pop'); page.wait_for_selector('.fw[data-win="inv"] .pw-svg'); page.wait_for_timeout(300)
        page.select_option('.fw[data-win="inv"] select[data-k="inv"]', 'Foreign'); page.select_option('.fw[data-win="inv"] select[data-k="board"]', 'Regular'); page.wait_for_timeout(300)
        page.select_option('#invInv', 'Foreign'); page.select_option('#invBoard', 'Regular'); page.wait_for_timeout(300)
        chips = "(sel) => [...document.querySelectorAll(sel + ' .rp-chip')].map(c => c.innerText.replace(/\\s+/g, ' '))"
        report['inv'] = {'sub': page.evaluate(sub, 'inv'), 'window': page.evaluate(chips, '.fw[data-win=inv]'), 'panel': page.evaluate(chips, '#invLegend'),
                         'table': page.evaluate(rows, 'inv')}
        # a broker clicked in Broker summary joins the inventory (panel and window)
        page.dispatch_event('.fw[data-win="bs"]', 'pointerdown'); page.click('.fw[data-win="bs"] tbody tr[data-b]:nth-child(2)'); page.wait_for_timeout(300)
        page.dispatch_event('.fw[data-win="inv"]', 'pointerdown')
        report['after_pick'] = {'window': page.evaluate(chips, '.fw[data-win=inv]'), 'panel': page.evaluate(chips, '#invLegend')}
        # crosshair: hovering the window chart moves the main chart's crosshair (its legend date)
        box = page.locator('.fw[data-win="inv"] .pw-svg').bounding_box()
        page.mouse.move(box['x'] + box['width'] * .6, box['y'] + box['height'] / 2); page.wait_for_timeout(300)
        report['cross'] = {'window_at': J("document.querySelector('.fw[data-win=inv] .pw-at')?.textContent"), 'panel_date': J("document.querySelector('#invBody .rp-invdate')?.textContent")}
        page.screenshot(path=str(out / 'pop-three.png'))
        # move and resize the inventory window, pin Top brokers, then reload: the same windows in the same places
        h = page.locator('.fw[data-win="inv"] .fw-head strong').bounding_box()
        page.mouse.move(h['x'] + 5, h['y'] + 5); page.mouse.down(); page.mouse.move(h['x'] - 200, h['y'] + 60, steps=6); page.mouse.up()
        g = page.locator('.fw[data-win="inv"] .fw-grip').bounding_box()
        page.mouse.move(g['x'] + 8, g['y'] + 8); page.mouse.down(); page.mouse.move(g['x'] + 108, g['y'] + 48, steps=6); page.mouse.up(); page.wait_for_timeout(300)
        page.dispatch_event('.fw[data-win="acc"]', 'pointerdown'); page.click('.fw[data-win="acc"] [data-act="pin"]')
        geo = "() => Object.fromEntries([...document.querySelectorAll('.fw')].map(w => [w.dataset.win, [w.style.left, w.style.top, w.style.width, w.style.height, w.classList.contains('pinned')]]))"
        report['geo_before'] = J(geo)
        page.reload(wait_until='load'); page.wait_for_function(ready, timeout=180000); page.wait_for_timeout(1500)
        report['geo_after'] = J(geo)
        report['inv_after_reload'] = page.evaluate(chips, '.fw[data-win=inv]')
        page.screenshot(path=str(out / 'pop-reload.png'))
        # dock Broker summary: the window closes and the panel section stays open
        page.dispatch_event('.fw[data-win="bs"]', 'pointerdown'); page.click('.fw[data-win="bs"] [data-act="dock"]'); page.wait_for_timeout(300)
        report['after_dock'] = J("({ open: [...document.querySelectorAll('.fw')].map(w => w.dataset.win), stored: localStorage.getItem('ml.win.open'), bsCollapsed: document.querySelector('.st[data-sec=bs]').classList.contains('collapsed') })")
        # weekly timeframe: the windows come back and follow the weekly chart
        page.evaluate("localStorage.setItem('ml.tf', 'W')"); page.reload(wait_until='load'); page.wait_for_function(ready, timeout=180000); page.wait_for_timeout(1500)
        report['weekly'] = {'inv': page.evaluate(sub, 'inv'), 'acc': page.evaluate(sub, 'acc')}
        page.evaluate("localStorage.setItem('ml.tf', 'D')")
        report['errors'] = errors
        browser.close()
finally:
    server.should_exit = True
    time.sleep(.5)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)'); c.execute('DROP ROLE IF EXISTS edge_bff_runtime')
print(json.dumps(report, indent=1, ensure_ascii=False))
