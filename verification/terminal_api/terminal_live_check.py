"""EXEC-TERMINAL-API T4/T5 live check of the Terminal tab before edge-bff is deployed: a local edge-bff (built
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
        for ticker in tickers:
            ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
            page = ctx.new_page()
            errors, downloads = [], []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)

            def bucket(route):
                # fetched here (Python honours the environment's HTTPS proxy), then handed to the page with the CORS
                # header the bucket gives its deployed origins
                try:
                    with urllib.request.urlopen(route.request.url, timeout=60) as r:
                        status, body, ctype = r.status, r.read(), r.headers.get('content-type', 'application/octet-stream')
                except urllib.error.HTTPError as e:
                    status, body, ctype = e.code, e.read(), 'text/plain'
                downloads.append({'status': status, 'bytes': len(body)})
                route.fulfill(status=status, body=body, headers={'content-type': ctype,
                                                                 'access-control-allow-origin': f'http://127.0.0.1:{port}'})
            page.route('https://*.t3.storageapi.dev/**', bucket)
            r = page.request.post(f'http://127.0.0.1:{port}/api/v1/auth/sign-in', headers={'Origin': settings.origin},
                                  data={'login': 'owner', 'password': 'local-live-check'})
            assert r.ok, r.status
            page.goto(f'http://127.0.0.1:{port}/terminal-app/')
            page.evaluate(f"localStorage.setItem('ml.symbol', '{ticker}')")
            t0 = time.time()
            page.goto(f'http://127.0.0.1:{port}/terminal-app/', wait_until='load', timeout=120000)
            # F4: what shows before the data (loading notice, side panels already in their state)
            shell = page.evaluate("() => ({ notice: document.querySelector('[role=status]')?.textContent || null, rpSub: document.getElementById('rpSub').textContent, left: document.getElementById('workspace').classList.contains('left-collapsed'), right: document.getElementById('workspace').classList.contains('right-collapsed') })")
            try:
                # EXEC-TERMINAL-UI-1026 U5: the chart first, then the Flow Timeline; the side panels start closed
                page.wait_for_function("() => document.querySelector('#flowSummary .flow-stat') || document.querySelector('[role=alert]')", timeout=90000)
                first = round(time.time() - t0, 2)
                page.wait_for_function("() => !/^Loading/.test(document.getElementById('flowNote').textContent) || document.getElementById('flowNote').hidden", timeout=90000)
                flow = round(time.time() - t0, 2)
                closed = page.evaluate("() => [document.getElementById('workspace').classList.contains('left-collapsed'), document.getElementById('workspace').classList.contains('right-collapsed')]")
                page.click('#statsExpand'); page.click('#rpExpand')
                page.wait_for_function("() => document.getElementById('statsRange')?.textContent.includes('sessions') && !/Loading/.test(document.getElementById('relStats').textContent) && !/Loading/.test(document.getElementById('bsBody').textContent)", timeout=90000)
            except Exception:
                (out / f'{ticker}.html').write_text(page.content()); print('page stuck', ticker, page.url, errors[:5], downloads[:5]); raise
            loaded = round(time.time() - t0, 2)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(out / f'{ticker}.png'), full_page=True)
            report[ticker] = page.evaluate("""() => ({
              symbol: document.getElementById('symText').textContent,
              stats: document.getElementById('statsRange').textContent + ' · ' + document.getElementById('statsRange').title,
              flow: document.getElementById('flowSummary').innerText.replace(/\\n/g, ' '),
              relative: document.getElementById('relStats').innerText.replace(/\\s+/g, ' ').trim(),
              broker: document.getElementById('rpSub').textContent,
              brokerRows: document.querySelectorAll('#bsBody tr[data-b]').length,
              bandarHidden: document.querySelector('.st[data-sec="bd"]').hidden,
              events: document.getElementById('evList').innerText.replace(/\\s+/g, ' ').trim(),
              markers: document.querySelectorAll('.ev-mk').length,
              alert: document.querySelector('[role=alert]')?.textContent || null })""")
            report[ticker].update(seconds_to_chart=first, seconds_to_flow=flow, side_panels_closed_at_start=closed)
            # U3: the info mark's tooltip; U2: the Flow Timeline's right-click menu; U4: the event tooltip's date
            checks = {}
            info = page.query_selector('#flowSummary .flow-info')
            if info:
                info.hover(); page.wait_for_timeout(200)
                checks['info_tip'] = page.evaluate("() => document.querySelector('.st-tip:not([hidden])')?.innerText || null")
            box = page.query_selector('.flow-wrap').bounding_box()
            page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2, button='right'); page.wait_for_timeout(200)
            checks['flow_menu'] = page.evaluate("() => [...document.querySelectorAll('.flow-wrap .dr-menu:not([hidden]) .dr-mi')].map(b => b.innerText)")
            page.keyboard.press('Escape')
            mk = page.query_selector('.ev-mk')
            if mk:
                mk.hover(); page.wait_for_timeout(300)
                checks['event_tip'] = page.evaluate("() => document.querySelector('.ev-tip')?.innerText.slice(0, 160) || null")
            # F2: Ray in the line menu; F5: the Flow note once the whole broker history is in
            checks['line_menu'] = page.evaluate("() => [...document.querySelectorAll('.dr-mi')].map(b => b.innerText.split('\\n')[0]).filter(t => /ray|line/i.test(t))")
            page.wait_for_function("() => !/^Loading/.test(document.getElementById('flowNote').textContent) || document.getElementById('flowNote').hidden", timeout=90000)
            checks['flow_note_after_all'] = page.evaluate("() => document.getElementById('flowNote').hidden ? null : document.getElementById('flowNote').textContent")
            checks['shell'] = shell
            # EXEC-TERMINAL-LOGO: the symbol pill's logo has loaded (or the monogram stands in)
            checks['logo'] = page.evaluate("() => { const i = document.querySelector('#symbolPill .tk-logo'); return i ? {src: i.getAttribute('src').split('?')[0], loaded: i.complete && i.naturalWidth > 0} : {monogram: document.querySelector('#symbolPill .tk-mono')?.textContent || null} }")
            report[ticker]['checks'] = checks
            report[ticker].update(seconds_to_panels=loaded, downloads=len(downloads),
                                  download_status=sorted({d['status'] for d in downloads}),
                                  megabytes=round(sum(d['bytes'] for d in downloads) / 1e6, 2), errors=errors)
            # EXEC-TERMINAL-SPEED: a second visit reads the files from the browser cache (IndexedDB by sha256), and
            # ?perf=1 shows the stage and file timings
            before = len(downloads); t0 = time.time()
            page.goto(f'http://127.0.0.1:{port}/terminal-app/?perf=1', wait_until='load', timeout=120000)
            page.wait_for_function("() => document.querySelector('#flowSummary .flow-stat') || document.querySelector('[role=alert]')", timeout=90000)
            again = round(time.time() - t0, 2)
            page.wait_for_function("() => /KB +(cache|net)/.test(document.querySelector('.ml-perf')?.innerText || '') && (document.getElementById('flowNote').hidden || !/^Loading/.test(document.getElementById('flowNote').textContent))", timeout=90000)
            page.wait_for_timeout(1000)
            report[ticker]['second_visit'] = {'seconds_to_flow': again, 'downloads': len(downloads) - before,
                                              'perf': page.evaluate("() => document.querySelector('.ml-perf')?.innerText || null")}
            ctx.close()
        browser.close()
finally:
    server.should_exit = True
    time.sleep(.5)
    with psycopg.connect(admin, autocommit=True) as c:
        c.execute(f'DROP DATABASE "{name}" WITH (FORCE)'); c.execute('DROP ROLE IF EXISTS edge_bff_runtime')
(out / 'report.json').write_text(json.dumps(report, indent=1))
print(json.dumps(report, indent=1))
