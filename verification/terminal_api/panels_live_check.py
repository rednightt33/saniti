"""EXEC-TERMINAL-PANELS live check (based on terminal_live_check.py): annotation rail, two-year broker panels, range
calendar, period dragged on the chart (all four panels), and section reordering that survives a reload.

Original header: EXEC-TERMINAL-API T4/T5 live check of the Terminal tab before edge-bff is deployed: a local edge-bff (built
terminal page, disposable Postgres) forwards /api/terminal to the deployed terminal-api with the gateway key, and a
browser opens /terminal-app/ signed in as the EDGE owner. Presigned downloads are fetched by the test browser's
route handler (the bucket's CORS names only the deployed origins, not this local one).

Environment: EDGE_TEST_POSTGRES_URL (disposable server), EDGE_TEST_CHROMIUM (optional), the Railway CLI logged in to the
project (the gateway key is read from terminal-api's variables into memory, never printed).
Usage: python terminal_live_check.py <out dir> [TICKER ...]
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
        ticker = tickers[0]
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)

        def bucket(route):
            for attempt in range(3):                       # the sandbox proxy sometimes cuts a transfer short
                try:
                    with urllib.request.urlopen(route.request.url, timeout=60) as r:
                        status, body, ctype = r.status, r.read(), r.headers.get('content-type', 'application/octet-stream')
                    break
                except urllib.error.HTTPError as e:
                    status, body, ctype = e.code, e.read(), 'text/plain'; break
                except Exception:
                    if attempt == 2: raise
            route.fulfill(status=status, body=body, headers={'content-type': ctype,
                                                             'access-control-allow-origin': f'http://127.0.0.1:{port}'})
        page.route('https://*.t3.storageapi.dev/**', bucket)
        r = page.request.post(f'http://127.0.0.1:{port}/api/v1/auth/sign-in', headers={'Origin': settings.origin},
                              data={'login': 'owner', 'password': 'local-live-check'})
        assert r.ok, r.status
        page.goto(f'http://127.0.0.1:{port}/terminal-app/')
        page.evaluate(f"localStorage.setItem('ml.symbol', '{ticker}'); localStorage.setItem('ml.broker.collapsed', '0')")
        page.goto(f'http://127.0.0.1:{port}/terminal-app/', wait_until='load', timeout=120000)
        flow_done = "() => document.getElementById('flowNote').hidden || !/^Loading/.test(document.getElementById('flowNote').textContent)"
        page.wait_for_function("() => document.querySelector('#bsBody tr[data-b]')", timeout=180000)
        page.wait_for_function(flow_done, timeout=180000)
        page.wait_for_timeout(1500)
        hints = "() => ['bsHint','accHint','invHint'].map(id => document.getElementById(id).textContent)"
        # rail: markers below the chart, the chart 24 px shorter than its frame
        rail = page.evaluate("""() => { const w = document.getElementById('chart').parentElement, c = document.getElementById('chart');
            const mk = document.querySelector('.ev-mk'); const cr = c.getBoundingClientRect(), wr = w.getBoundingClientRect();
            return { railed: w.classList.contains('ev-rail'), gap: Math.round(wr.bottom - cr.bottom), markers: document.querySelectorAll('.ev-mk').length,
                     marker_below_chart: mk ? mk.getBoundingClientRect().top >= cr.bottom - 2 : null } }""")
        box = page.locator('#chart').bounding_box()
        page.mouse.move(box['x'] + box['width'] * .6, box['y'] + box['height'] * .4); page.wait_for_timeout(300)
        page.screenshot(path=str(out / 'rail_crosshair.png'))
        report['rail'] = rail
        # EXEC-TERMINAL-PANELS-2 B: the Flow legend labels and the Cumulative pill share one middle line
        report['legend_middles'] = page.evaluate("""() => [document.querySelector('.flow-legend > span'), document.querySelector('.pill-toggle')]
            .map(e => { const r = e.getBoundingClientRect(); return Math.round(r.top + r.height / 2) })""")
        # F: the marker of the session under the crosshair grows
        mk = page.locator('.ev-mk').last.bounding_box()
        page.mouse.move(mk['x'] + mk['width'] / 2, box['y'] + box['height'] * .4); page.wait_for_timeout(300)
        report['hot_marker'] = page.evaluate("() => document.querySelectorAll('.ev-mk.hot').length")
        page.screenshot(path=str(out / 'hot_marker.png'))
        # E: accumulators and distributors in one table
        report['paired'] = page.evaluate("() => ({ title: document.getElementById('accTitle').textContent, head: document.querySelector('.pa-head')?.innerText.replace(/\\s+/g, ' '), rows: document.querySelectorAll('.pa-row').length, switch_hidden: document.getElementById('accSide').closest('.rp-ctl').hidden })")
        # calendar: a Saturday is clickable and maps to the session before it
        page.click('#bsRange [data-n="custom"]'); page.wait_for_selector('.rc-pop')
        satday = page.evaluate("() => [...document.querySelectorAll('.rc-day')].map(b => b.dataset.day).find(t => new Date(t + 'T00:00:00Z').getUTCDay() === 6)")
        page.click(f'.rc-day[data-day="{satday}"]'); page.click(f'.rc-day[data-day="{satday}"]'); page.wait_for_timeout(300)
        report['saturday'] = {'day': satday, 'hint': page.evaluate("() => document.getElementById('bsHint').textContent"),
                              'note': page.evaluate("() => document.querySelector('#bsRange .rp-note:not([hidden])')?.textContent || null")}
        # calendar on Broker summary: years offered, pick two days
        page.click('#bsRange [data-n="custom"]')
        page.wait_for_selector('.rc-pop')
        cal = page.evaluate("() => ({ years: [...document.querySelectorAll('.rc-years button')].map(b => b.textContent), enabled: document.querySelectorAll('.rc-day:not([disabled])').length, days: document.querySelectorAll('.rc-day').length })")
        page.screenshot(path=str(out / 'calendar.png'))
        days = page.locator('.rc-day')
        n = days.count()
        days.nth(max(0, n - 6)).click(); days.nth(n - 2).click()
        cal['after_pick'] = page.evaluate(hints)
        report['calendar'] = cal
        # Select on chart: drag across the middle of the chart, every panel follows
        page.click('#accRange [data-n="custom"]'); page.wait_for_selector('.rc-pop'); page.click('.rc-chart')
        page.wait_for_selector('.rs-layer')
        y = box['y'] + box['height'] * .5
        page.mouse.move(box['x'] + box['width'] * .55, y); page.mouse.down()
        page.mouse.move(box['x'] + box['width'] * .75, y, steps=8)
        page.screenshot(path=str(out / 'chart_range_drag.png'))
        page.mouse.up(); page.wait_for_timeout(500)
        report['chart_range'] = {'hints': page.evaluate(hints), 'layer_gone': page.locator('.rs-layer').count() == 0,
                                 'notes': page.evaluate("() => [...document.querySelectorAll('.rp-note:not([hidden])')].map(n => n.textContent)")}
        # one day: click, then click the same place
        page.click('#bsRange [data-n="custom"]'); page.wait_for_selector('.rc-pop'); page.click('.rc-chart'); page.wait_for_selector('.rs-layer')
        px = box['x'] + box['width'] * .6
        page.mouse.click(px, y); page.wait_for_timeout(150); page.mouse.click(px, y); page.wait_for_timeout(400)
        report['one_day'] = {'hints': page.evaluate(hints), 'layer_gone': page.locator('.rs-layer').count() == 0}
        # a range reaching back before the two-year window (zoomed-out chart, from its left edge): clipped, with a note
        page.mouse.move(box['x'] + box['width'] * .5, box['y'] + box['height'] * .5)
        for _ in range(6):                                    # dragging the chart to the right shows older sessions
            page.mouse.move(box['x'] + box['width'] * .1, box['y'] + box['height'] * .3); page.mouse.down()
            page.mouse.move(box['x'] + box['width'] * .9, box['y'] + box['height'] * .3, steps=10); page.mouse.up(); page.wait_for_timeout(100)
        page.wait_for_timeout(300)
        page.click('#bsRange [data-n="custom"]'); page.wait_for_selector('.rc-pop'); page.click('.rc-chart')
        page.wait_for_selector('.rs-layer')
        page.mouse.move(box['x'] + box['width'] * .12, y); page.mouse.down()
        page.mouse.move(box['x'] + box['width'] * .9, y, steps=8); page.mouse.up(); page.wait_for_timeout(500)
        page.screenshot(path=str(out / 'chart_range_clipped.png'))
        report['clipped'] = {'hints': page.evaluate(hints),
                             'notes': page.evaluate("() => [...document.querySelectorAll('.rp-note:not([hidden])')].map(n => n.textContent)")}
        # reorder: drag Top accumulators above Broker summary
        order = "() => [...document.querySelectorAll('#rightScroll > .st')].map(s => s.dataset.sec)"
        before = page.evaluate(order)
        g = page.locator('#rightScroll .st[data-sec="acc"] .st-head').bounding_box()
        t = page.locator('#rightScroll .st[data-sec="bs"] .st-head').bounding_box()
        page.mouse.move(g['x'] + 60, g['y'] + g['height'] / 2); page.mouse.down()          # D: the header itself, no grip
        page.mouse.move(g['x'] + 60, t['y'] + 2, steps=12); page.mouse.up(); page.wait_for_timeout(300)
        after = page.evaluate(order)
        collapsed = page.evaluate("() => document.querySelector('#rightScroll .st[data-sec=acc]').classList.contains('collapsed')")
        page.click('#rightScroll .st[data-sec="inv"] .st-head'); page.wait_for_timeout(200)          # a plain click still folds
        folded = page.evaluate("() => document.querySelector('#rightScroll .st[data-sec=inv]').classList.contains('collapsed')")
        page.click('#rightScroll .st[data-sec="inv"] .st-head')
        page.reload(wait_until='load'); page.wait_for_function("() => document.querySelector('#rightScroll .st-head[aria-keyshortcuts]')", timeout=120000)
        report['reorder'] = {'before': before, 'after': after, 'after_reload': page.evaluate(order), 'folded_by_drag': collapsed, 'click_folds': folded}
        report['errors'] = errors
        ctx.close(); browser.close()
finally:
    server.should_exit = True
    time.sleep(.5)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)'); c.execute('DROP ROLE IF EXISTS edge_bff_runtime')
(out / 'report.json').write_text(json.dumps(report, indent=1))
print(json.dumps(report, indent=1))
