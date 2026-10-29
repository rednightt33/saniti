"""EDGE Terminal page timing (EXEC-MU-RUNTIME Phase 0; verification/edge_multiuser/runtime/terminal.md T12.2, RUNTIME.md
section 7). Read-only timing of the EDGE Terminal tab in Railway dev, the way verification/backtest/page_timing_dev.py
times the Backtest tab: signs in as the owner (credentials read from edge-bff's Railway variables into memory, never
printed), opens /terminal (EDGE shell + iframe /terminal-app/)
  A. cold: a new browser profile (no IndexedDB file cache, no stored ticker: the page's default);
  B. warm: a second tab of the same profile (its file cache kept);
  C. ticker switch, not cached: to SWITCH_TO through the page's own search (store + frame reload, search.ts choose);
  D. ticker switch, cached: back to the first ticker;
  E. timeframe change: Weekly through the page's own button (main.ts timeframeButtons: store + frame reload), then
  F. back to Daily;
and times the gateway routes directly (session, the reference files, one /bundle of SWITCH_TO with prices and with
prices and broker files, and the files that bundle names with their sizes).
For each page action: seconds until the chart is drawn (the page's own mark 'chart drawn', performance mark
'terminal:chart drawn', the stage marks ?perf=1 shows: app/perf.ts), every stage mark relative to the action, the
seconds until the network is quiet (the broker files of the Flow Timeline included), the requests through EDGE by
route and the bucket downloads (count, bytes, slowest), the grants (each 200 answer of /bundle and /reference is one
terminal-api grant with its audit row, terminal.md 2.2), and the main-thread long tasks. Writes OUT/report.json and one
screenshot per action. Writes nothing anywhere else: terminal-api adds the audit rows of the grants the page and the
route timings ask, as for any visit.

Usage: python3 page_timing_dev.py OUT [SWITCH_TO]     (SWITCH_TO: a ticker the first open does not show; default BBRI)
Environment: EDGE_TEST_CHROMIUM (a Chromium binary, else Playwright's), HTTPS_PROXY (the sandbox's proxy, as the
Backtest script). A local run against a local edge-bff instead of dev: EDGE_TIMING_BASE (its http origin) with
EDGE_TIMING_LOGIN and EDGE_TIMING_PASSWORD (read from the environment, never printed); then the browser takes no
proxy and accepts a self-signed certificate, and EDGE_TIMING_CHROMIUM_ARGS adds Chromium flags, one per line (a
local file server must answer under the bucket host the page's CSP allows, https://*.t3.storageapi.dev, on port 443:
--host-resolver-rules maps the name to it)."""
import json, os, re, statistics, subprocess, sys, time, traceback
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


# Review of measure (EXEC-MU-RUNTIME Phase 0): a Playwright error message ends with its call log, and the call log of an
# API request lists the request's headers, the session cookie and the CSRF token among them. So no error is shown or
# written as it is: safe_error keeps the message before its call log, without any credential value this script holds
# (SECRETS) and without a URL's query (a presigned signature); an uncaught error prints where it happened (file and
# line, never a value) and safe_error, not Python's own traceback.
SECRETS = set()


def safe_error(e, limit=300):
    text = str(e).split('\nCall log:', 1)[0]
    for secret in sorted(SECRETS, key=len, reverse=True):
        text = text.replace(secret, '[redacted]')
    text = re.sub(r'(https?://[^\s?#"\']+)[?#][^\s"\']*', r'\1?[query]', text)
    return f'{type(e).__name__}: {text[:limit]}'


def uncaught(kind, e, tb):
    sys.stderr.write('Traceback (most recent call last):\n' + ''.join(traceback.format_tb(tb)) + safe_error(e) + '\n')


sys.excepthook = uncaught

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
SWITCH_TO = sys.argv[2] if len(sys.argv) > 2 else 'BBRI'
if os.environ.get('EDGE_TIMING_BASE'):
    base = os.environ['EDGE_TIMING_BASE'].rstrip('/')
    login, password = os.environ.get('EDGE_TIMING_LOGIN'), os.environ.get('EDGE_TIMING_PASSWORD')
else:
    v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'edge-bff', '-e', 'dev', '--json'],
                                  capture_output=True, text=True, timeout=60, check=True).stdout)
    base = 'https://' + v['RAILWAY_PUBLIC_DOMAIN']
    login, password = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD')
    del v
SECRETS.update(x for x in (password,) if x)
HOST = urlsplit(base).netloc
GRANTS = ('/api/terminal/v1/bundle', '/api/terminal/v1/reference/')

INIT = """
window.__lt = [];
try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt.push([Math.round(performance.timeOrigin + e.startTime), Math.round(e.duration)]) })
  .observe({ type: 'longtask', buffered: true }) } catch (e) {}
"""


def kind(url):
    """A request by route: EDGE's own paths as they are, any other host (the bucket) by family and ticker."""
    p = urlsplit(url)
    if p.netloc == HOST:
        return p.path
    return 'bucket:' + '/'.join(p.path.split('/v1/', 1)[-1].split('/')[:2])


def summary(log):
    """The requests of one action: per route count, statuses and bytes; the bucket downloads; the grants."""
    routes, files = {}, [r for r in log if r['k'].startswith('bucket:') and not r.get('failed')]
    for r in log:
        if r['k'].startswith('bucket:'):
            continue
        s = routes.setdefault(r['k'], {'n': 0, 'status': [], 'bytes': 0, 'ms': []})
        s['n'] += 1
        s['status'].append(r.get('status'))
        s['bytes'] += r.get('bytes') or 0
        if r.get('ms') is not None:
            s['ms'].append(r['ms'])
    return {'routes': routes,
            'grants': sum(1 for r in log if r['k'].startswith(GRANTS) and r.get('status') == 200),
            'bucket_files': len(files), 'bucket_bytes': sum(r.get('bytes') or 0 for r in files),
            'bucket_slowest_ms': max([r['ms'] for r in files if r.get('ms') is not None], default=None),
            'failed': [r for r in log if r.get('failed') or (r.get('status') or 0) >= 400]}


report = {'base_host': HOST, 'switch_to': SWITCH_TO, 'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
with sync_playwright() as pw:
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    local = bool(os.environ.get('EDGE_TIMING_BASE'))
    browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None,
                                 # local: no proxy at all (Chromium would take HTTPS_PROXY from the environment)
                                 args=(['--no-proxy-server'] + [a for a in os.environ.get('EDGE_TIMING_CHROMIUM_ARGS', '').split('\n') if a]) if local else [],
                                 **({'proxy': {'server': proxy}} if proxy and not local else {}))

    def new_ctx():
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000}, ignore_https_errors=local)
        ctx.add_init_script(INIT)
        r = ctx.request.post(base + '/api/v1/auth/sign-in', data=json.dumps({'login': login, 'password': password}),
                             headers={'Content-Type': 'application/json', 'Origin': base})
        if r.status != 200:
            raise SystemExit(f'sign-in failed ({r.status})')
        SECRETS.update(c['value'] for c in ctx.cookies() if c.get('value'))   # the session cookie
        return ctx

    def watch(page):
        log = []
        def done(req):
            t, resp, size = {}, None, None
            try:
                t = req.timing; resp = req.response()
            except Exception:
                pass
            if resp and req.resource_type in ('fetch', 'xhr'):
                try:
                    size = len(resp.body())
                except Exception:                     # a 304 has none
                    size = None
            log.append({'k': kind(req.url), 'm': req.method, 'type': req.resource_type, 'status': resp.status if resp else None,
                        'start': round(t.get('startTime', 0)), 'ms': round(t.get('responseEnd', 0)) if t.get('responseEnd', -1) >= 0 else None,
                        'bytes': size})
        page.on('requestfinished', done)
        def failed(req):
            try:
                resp = req.response()                 # an answer that arrived before the browser ended the request
            except Exception:
                resp = None
            log.append({'k': kind(req.url), 'm': req.method, 'failed': req.failure, 'status': resp.status if resp else None})
        page.on('requestfailed', failed)
        return log

    def frame(page):
        for f in page.frames:
            if '/terminal-app/' in f.url:
                return f
        return None

    def quiet(page, log, ms=2500, cap=120):
        t0 = time.time(); n = -1; since = time.time()
        while time.time() - t0 < cap:
            if len(log) != n:
                n = len(log); since = time.time()
            elif time.time() - since > ms / 1000:
                break
            page.wait_for_timeout(200)
        return round(time.time() - t0 - ms / 1000, 2)

    def probe(f, expr, default=None):
        """An expression in the frame; default while the frame is between two documents (a reload)."""
        try:
            return f.evaluate(expr)
        except Exception:
            return default

    def drawn(page, origin_before=None, cap=120):
        """Waits for the frame's 'chart drawn' mark (of a new document when origin_before is given), or its failure
        notice; (frame, outcome)."""
        t0 = time.time()
        while time.time() - t0 < cap:
            f = frame(page)
            if f:
                state = probe(f, """() => ({ origin: performance.timeOrigin, drawn: performance.getEntriesByName('terminal:chart drawn').length > 0,
                                           alert: document.querySelector('[role=alert]')?.textContent || null })""")
                if state and (origin_before is None or state['origin'] != origin_before):
                    if state['drawn']:
                        return f, 'drawn'
                    if state['alert']:
                        return f, 'failed: ' + state['alert'][:200]
            page.wait_for_timeout(25)
        return frame(page), 'timeout'

    def marks(f, since_epoch):
        """The stage marks of the frame's document, in milliseconds after the action started (epoch milliseconds)."""
        got = probe(f, "() => ({ o: performance.timeOrigin, m: performance.getEntriesByType('mark').filter(m => m.name.startsWith('terminal:')).map(m => [m.name.slice(9), m.startTime]) })")
        if not got:
            return {}
        return {name: round(got['o'] + t - since_epoch) for name, t in got['m']}

    def longtasks(f, since_ms=0):
        lt = [x for x in (probe(f, 'window.__lt', []) or []) if x[0] >= since_ms]
        return {'count': len(lt), 'total_ms': sum(d for _, d in lt), 'max_ms': max([d for _, d in lt], default=0)}

    def finish(page, log, n0, f, outcome, t0, epoch, label):
        res = {'outcome': outcome, 'drawn_s': round(time.time() - t0, 2)}
        res['network_quiet_s'] = round(res['drawn_s'] + quiet(page, log), 2)
        f = frame(page) or f
        res['marks_ms'] = marks(f, epoch)
        res['symbol'] = probe(f, "() => document.getElementById('symText')?.textContent || null")
        res['timeframe'] = probe(f, "() => document.querySelector('#timeframeGroup button.active')?.dataset.timeframe || null")
        res['longtasks'] = longtasks(f, epoch)
        res['summary'] = summary(log[n0:])
        res['requests'] = log[n0:]
        page.screenshot(path=str(out / f'{label}.png'))
        return res

    def open_tab(page, label):
        log = watch(page); t0 = time.time(); epoch = t0 * 1000
        page.goto(base + '/terminal', wait_until='load', timeout=120000)
        shell = round(time.time() - t0, 2)
        f, outcome = drawn(page)
        res = finish(page, log, 0, f, outcome, t0, epoch, label)
        res['shell_load_s'] = shell
        return res, log

    def reload_action(page, log, label, act):
        """An action the page answers by reloading its frame (a ticker or timeframe change): `act(frame)` starts it."""
        f = frame(page); before = probe(f, 'performance.timeOrigin'); n0 = len(log)
        t0 = time.time(); epoch = t0 * 1000
        act(f)
        f, outcome = drawn(page, before)
        return finish(page, log, n0, f, outcome, t0, epoch, label)

    def search_to(ticker):
        def act(f):
            f.locator('#symSearch').click()
            f.locator('.gp-dialog input').fill(ticker)
            try:
                picked = f.evaluate("""t => { const row = [...document.querySelectorAll('.gp-row')].find(r => (r.querySelector('.gp-ticker')?.firstChild?.textContent || '').trim() === t);
                                             if (row) row.click(); return !!row }""", ticker)
            except Exception:
                picked = True                     # the click's reload took the document away before the answer
            if not picked:
                raise RuntimeError(f'{ticker} is not in the page\'s ticker list')
        return act

    def timeframe(tf):
        return lambda f: f.locator(f'#timeframeGroup button[data-timeframe="{tf}"]').click()

    # A. cold (a new profile)
    ctx = new_ctx(); page = ctx.new_page()
    report['cold'], _ = open_tab(page, 'cold')
    first = report['cold']['symbol']
    if first == SWITCH_TO:
        raise SystemExit(f'the first open shows {SWITCH_TO}: name another SWITCH_TO')
    # B. warm (the same profile: IndexedDB terminal-files kept)
    page2 = ctx.new_page()
    report['warm'], log2 = open_tab(page2, 'warm')
    # C. D. ticker switches: not cached, then back to the cached first ticker; E. F. timeframe. Each from a drawn page
    # (the controls exist only once the chart is drawn: main.ts start); a failed one is recorded and the next skipped.
    for label, act in (('switch_uncached', search_to(SWITCH_TO)), ('switch_cached', search_to(first)),
                       ('timeframe_weekly', timeframe('W')), ('timeframe_daily', timeframe('D'))):
        previous = [v for k, v in report.items() if isinstance(v, dict) and 'outcome' in v][-1]
        if previous['outcome'] != 'drawn':
            report[label] = {'outcome': 'skipped: the page before it was not drawn'}
            continue
        try:
            report[label] = reload_action(page2, log2, label, act)
        except Exception as e:                    # recorded, never a half-written report
            report[label] = {'outcome': 'failed: ' + safe_error(e)}

    # G. the gateway routes on their own (same session)
    rq = ctx.request
    def timed(fn, n):
        xs, st = [], None
        for _ in range(n):
            t = time.time(); r = fn(); xs.append(round((time.time() - t) * 1000)); st = r.status
        return {'status': st, 'ms': xs, 'median': statistics.median(xs)}
    sess = rq.get(base + '/api/v1/auth/session').json(); tok = sess.get('csrf_token', '')
    SECRETS.update(x for x in (tok,) if x)
    H = {'Content-Type': 'application/json', 'Origin': base, 'X-CSRF-Token': tok}
    bundle = lambda ds: rq.post(base + '/api/terminal/v1/bundle', data=json.dumps({'ticker': SWITCH_TO, 'datasets': ds, 'packs': True}), headers=H)
    report['api'] = {
        'session': timed(lambda: rq.get(base + '/api/v1/auth/session'), 5),
        'reference_tickers': timed(lambda: rq.get(base + '/api/terminal/v1/reference/tickers'), 3),
        'bundle_price': timed(lambda: bundle(['price']), 3),
        'bundle_price_broker': timed(lambda: bundle(['price', 'broker']), 3),
    }
    b = bundle(['price', 'broker', 'events']).json()
    report['api']['bundle_files'] = {ds: [{'year': x.get('year'), 'bytes': x.get('bytes'), 'pack': x.get('pack')} for x in d.get('files', [])]
                                     for ds, d in (b.get('datasets') or {}).items()}
    report['api']['bundle_bytes'] = sum(x['bytes'] or 0 for files in report['api']['bundle_files'].values() for x in files)
    browser.close()
report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
(out / 'report.json').write_text(json.dumps(report, indent=1))
print('ok')
