"""Where a bond's Terminal page spends its time (user 2026-11-01: "untuk load data obligasi kayaknya lama banget ...
cuma dua komponen, statistik dan chart"). Read-only, Railway dev, signed in as the owner (credentials read from
edge-bff's Railway variables into memory, never printed).

For each ticker of TICKERS, the Terminal frame (/terminal-app/?perf=1, the page a ticker switch reloads) is opened twice
in one browser profile: `cold` (its files not in the browser cache yet) and `cached`. Each open records the page's own
stage marks (app/perf.ts), every request with its start and end relative to the open, the main-thread long tasks, and
the time until the Statistics panel shows its figures. LATENCY_MS (default 0) adds that delay to every request through
the browser's network emulation (200: roughly Jakarta to Railway's us-west region). The state is the one a user who
added Flow indicators on a stock and opened Statistics has: the saved list and the open panel are seeded.
LOCAL_BUILD=1 serves /terminal-app/ from the local build (apps/edge-bff/static/terminal-app) on the live data, to time a
change before it is deployed. Writes OUT/report.json.

Usage: python3 bond_timing_check.py OUT [TICKER ...]"""
import json, mimetypes, os, subprocess, sys, time
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
TICKERS = sys.argv[2:] or ['ID10Y', 'ID03MY', 'US10Y', 'BBRI']
LATENCY = int(os.environ.get('LATENCY_MS', '0'))
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'edge-bff', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
base = 'https://' + v['RAILWAY_PUBLIC_DOMAIN']
login, password = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD')
del v
HOST = urlsplit(base).netloc
SAVED = [{'def': 'FL24'}, {'def': 'FL01'}, {'def': 'sma'}, {'def': 'rsi'}]
INIT = """window.__lt = [];
try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt.push([Math.round(e.startTime), Math.round(e.duration)]) })
  .observe({ type: 'longtask', buffered: true }) } catch (e) {}"""


def name(url):
    p = urlsplit(url)
    if p.netloc == HOST:
        return p.path
    return 'bucket:' + '/'.join(p.path.split('/v1/', 1)[-1].split('/')[:2])


report = {'latency_ms': LATENCY, 'tickers': TICKERS, 'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
with sync_playwright() as pw:
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None,
                                 **({'proxy': {'server': proxy}} if proxy else {}))
    ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
    ctx.add_init_script(INIT)
    r = ctx.request.post(base + '/api/v1/auth/sign-in', data=json.dumps({'login': login, 'password': password}),
                         headers={'Content-Type': 'application/json', 'Origin': base})
    if r.status != 200:
        raise SystemExit(f'sign-in failed ({r.status})')
    if os.environ.get('LOCAL_BUILD') == '1':
        build = Path(__file__).resolve().parents[2] / 'apps/edge-bff/static/terminal-app'
        def serve(route):
            path = route.request.url.split('/terminal-app/', 1)[1].split('?', 1)[0] or 'index.html'
            f = build / path
            if not f.is_file():
                return route.continue_()
            route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
        ctx.route('**/terminal-app/**', serve)
        report['local_build'] = True
    page = ctx.new_page()
    if LATENCY:
        cdp = ctx.new_cdp_session(page)
        cdp.send('Network.enable')
        cdp.send('Network.emulateNetworkConditions', {'offline': False, 'latency': LATENCY,
                                                     'downloadThroughput': 20e6 / 8, 'uploadThroughput': 5e6 / 8})
    page.goto(base + '/favicon.svg')
    page.evaluate("""s => { localStorage.setItem('ml.ind.v1', JSON.stringify(s)); localStorage.setItem('ml.stats.collapsed', '0');
                            localStorage.setItem('ml.tf', 'D') }""", SAVED)
    log = []

    def done(req, failed=False):
        t = {}
        try:
            t = req.timing
        except Exception:
            pass
        log.append({'k': name(req.url), 'start': t.get('startTime'), 'end': t.get('responseEnd'), 'failed': failed,
                    'type': req.resource_type})
    page.on('requestfinished', done)
    page.on('requestfailed', lambda req: done(req, True))

    def open_one(ticker, label):
        page.evaluate("t => localStorage.setItem('ml.symbol', t)", ticker)
        n0 = len(log); t0 = time.time()
        page.goto(base + '/terminal-app/?perf=1')
        page.wait_for_function("() => performance.getEntriesByName('terminal:chart drawn').length || document.querySelector('[role=alert]')", timeout=120000)
        drawn = round(time.time() - t0, 2)
        # the Statistics panel's first figure (its loading ring gone)
        page.wait_for_function("() => { const s = document.getElementById('distStats'); return s && s.textContent.trim() && !s.querySelector('.ml-spin, .spin') }", timeout=60000)
        stats = round(time.time() - t0, 2)
        page.wait_for_timeout(2500)
        got = page.evaluate("""() => ({ o: performance.timeOrigin,
            marks: performance.getEntriesByType('mark').filter(m => m.name.startsWith('terminal:')).map(m => [m.name.slice(9), Math.round(m.startTime)]),
            lt: window.__lt, symbol: document.getElementById('symText')?.textContent,
            perf: document.querySelector('.ml-perf')?.textContent || '' })""")
        origin = got['o']
        reqs = [{'k': x['k'], 'type': x['type'], 'failed': x['failed'],
                 'start_ms': round(x['start'] - origin) if x['start'] else None,
                 'end_ms': round(x['start'] + x['end'] - origin) if x['start'] and x['end'] and x['end'] >= 0 else None}
                for x in log[n0:]]
        return {'label': label, 'symbol': got['symbol'], 'drawn_s': drawn, 'stats_s': stats, 'marks_ms': dict(got['marks']),
                'longtasks': {'count': len(got['lt']), 'total_ms': sum(d for _, d in got['lt']), 'max_ms': max([d for _, d in got['lt']], default=0),
                              'list': got['lt']},
                'requests': sorted(reqs, key=lambda x: x['start_ms'] or 0), 'perf_box': got['perf']}

    report['runs'] = []
    for ticker in TICKERS:
        for label in ('cold', 'cached'):
            report['runs'].append({'ticker': ticker, **open_one(ticker, label)})
    browser.close()

(out / 'report.json').write_text(json.dumps(report, indent=1))
for r in report['runs']:
    print(f"{r['ticker']:7} {r['label']:6} drawn {r['drawn_s']:5}s stats {r['stats_s']:5}s  marks {r['marks_ms']}  longtasks {r['longtasks']['total_ms']}ms")
