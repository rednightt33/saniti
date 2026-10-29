"""EDGE Screener page timing (EXEC-MU-RUNTIME Phase 0; verification/edge_multiuser/runtime/RUNTIME.md section 7, the
Screener rows: first results, a run after an edit, the preview). Read-only timing of the EDGE Screener tab in Railway
dev, the way verification/backtest/page_timing_dev.py times the Backtest tab: signs in as the owner (credentials read
from edge-bff's Railway variables into memory, never printed), opens /screener (EDGE shell + iframe /screener-app/)
  A. cold: a new browser profile (no boot pointer, no cached catalog, universe or result): until the first results
     (the empty screen listed from the universe, `#app[data-boot=results]`, app.ts refresh; report 6c.4 S5);
  B. warm: a second tab of the same profile (the boot pointer and its cached files, S3-S4);
  C. first run: loading a preset (PRESET_ID, else the first preset chip that is available), which asks POST run;
  D. edited run: a changed value of the screen's first condition with a number field (the page's own change event,
     debounced 350 ms, run.ts), which asks POST run again;
  E. preview: a click on the first result row (preview.ts pickStock, askPreview after 120 ms: POST preview);
and times the routes directly (session, catalog and universe with and without If-None-Match, the edited run's request
and the preview's request sent again three times each under this script's own page order).
For each action: seconds until its answer is drawn (the page's own stage marks, performance marks 'terminal:<stage>'
as ?perf=1 shows: 'results' for a screen, the preview's answer for the preview), the stage marks relative to the
action, the requests through EDGE by route with status, bytes and time, and the answer's own `timings_ms` and versions
where the run answer carries them; the main-thread long tasks. Writes OUT/report.json and one screenshot per action.
Writes nothing: a run or a preview is a computation (no saved screen, no watchlist change); the page's own
remembered screen lives in the browser profile, which the script throws away.

Usage: python3 page_timing_dev.py OUT [PRESET_ID]
Environment: EDGE_TEST_CHROMIUM (a Chromium binary, else Playwright's), HTTPS_PROXY (the sandbox's proxy, as the
Backtest script). A local run against a local edge-bff instead of dev: EDGE_TIMING_BASE (its http origin) with
EDGE_TIMING_LOGIN and EDGE_TIMING_PASSWORD (read from the environment, never printed); then the browser takes no
proxy and accepts a self-signed certificate, and EDGE_TIMING_CHROMIUM_ARGS adds Chromium flags (one per line)."""
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
PRESET = sys.argv[2] if len(sys.argv) > 2 else None
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
API = '/api/v1/screener'

INIT = """
window.__lt = [];
try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt.push([Math.round(performance.timeOrigin + e.startTime), Math.round(e.duration)]) })
  .observe({ type: 'longtask', buffered: true }) } catch (e) {}
"""


def kind(url):
    p = urlsplit(url)
    return p.path if p.netloc == HOST else 'other:' + p.netloc


report = {'base_host': HOST, 'preset': PRESET, 'started_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
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
            t, resp, body = {}, None, None
            try:
                t = req.timing; resp = req.response()
            except Exception:
                pass
            if resp and req.resource_type in ('fetch', 'xhr'):
                try:
                    body = resp.body()
                except Exception:                     # a 304 has none
                    body = None
            entry = {'k': kind(req.url), 'm': req.method, 'type': req.resource_type, 'status': resp.status if resp else None,
                     'start': round(t.get('startTime', 0)), 'ms': round(t.get('responseEnd', 0)) if t.get('responseEnd', -1) >= 0 else None,
                     'bytes': len(body) if body is not None else None, 'at': round(time.time() * 1000)}
            if body is not None and entry['k'] in (API + '/run', API + '/preview') and resp.status == 200:
                try:
                    answer = json.loads(body)
                    entry['answer'] = {k: answer.get(k) for k in ('timings_ms', 'versions') if k in answer}
                    entry['answer']['rows'] = len(answer.get('rows') or [])
                except ValueError:
                    pass
            if req.method == 'POST' and entry['k'] in (API + '/run', API + '/preview'):
                entry['request'] = req.post_data            # replayed in G (a definition, no secret)
            log.append(entry)
        page.on('requestfinished', done)
        def failed(req):
            # a request the browser ended without a body, a conditional GET answered 304 included (Chromium reports it
            # aborted): its status when an answer arrived
            try:
                resp = req.response()
            except Exception:
                resp = None
            log.append({'k': kind(req.url), 'm': req.method, 'failed': req.failure, 'status': resp.status if resp else None, 'at': round(time.time() * 1000)})
        page.on('requestfailed', failed)
        return log

    def frame(page):
        for f in page.frames:
            if '/screener-app/' in f.url:
                return f
        return None

    def probe(f, expr, arg=None, default=None):
        try:
            return f.evaluate(expr, arg) if arg is not None else f.evaluate(expr)
        except Exception:
            return default

    def quiet(page, log, ms=2000, cap=120):
        t0 = time.time(); n = -1; since = time.time()
        while time.time() - t0 < cap:
            if len(log) != n:
                n = len(log); since = time.time()
            elif time.time() - since > ms / 1000:
                break
            page.wait_for_timeout(100)
        return round(time.time() - t0 - ms / 1000, 2)

    def marks(f, since_epoch):
        got = probe(f, "() => ({ o: performance.timeOrigin, m: performance.getEntriesByType('mark').filter(m => m.name.startsWith('terminal:')).map(m => [m.name.slice(9), m.startTime]) })")
        if not got:
            return []
        return [[name, round(got['o'] + t - since_epoch)] for name, t in got['m'] if got['o'] + t >= since_epoch]

    def results_marks(f):
        return probe(f, "() => performance.getEntriesByName('terminal:results').length", default=0)

    def longtasks(f, since_ms):
        lt = [x for x in (probe(f, 'window.__lt', default=[]) or []) if x[0] >= since_ms]
        return {'count': len(lt), 'total_ms': sum(d for _, d in lt), 'max_ms': max([d for _, d in lt], default=0)}

    def wait_for(page, check, cap=120):
        t0 = time.time()
        while time.time() - t0 < cap:
            got = check()
            if got:
                return got
            page.wait_for_timeout(20)
        return None

    def requests_of(log, n0):
        return [{k: v for k, v in r.items() if k != 'request'} for r in log[n0:]]

    def open_tab(page, label):
        log = watch(page); t0 = time.time(); epoch = t0 * 1000
        page.goto(base + '/screener', wait_until='load', timeout=120000)
        shell = round(time.time() - t0, 2)
        wait_for(page, lambda: frame(page))
        f = frame(page)
        state = wait_for(page, lambda: probe(f, "() => { const a = document.getElementById('app'); const err = document.querySelector('#resPane [role=alert]');"
                                                 " return a && a.dataset.boot === 'results' ? 'results' : err ? 'failed: ' + err.textContent.slice(0, 200) : null }"))
        res = {'outcome': state or 'timeout', 'shell_load_s': shell, 'first_results_s': round(time.time() - t0, 2)}
        res['network_quiet_s'] = round(res['first_results_s'] + quiet(page, log), 2)
        res['marks_ms'] = marks(f, epoch)
        res['boot'] = probe(f, "() => document.getElementById('app').dataset.boot")
        res['longtasks'] = longtasks(f, epoch)
        res['requests'] = requests_of(log, 0)
        page.screenshot(path=str(out / f'{label}.png'))
        return res, log, f

    def answered(page, log, n0, route, f, mark_count=None, cap=120):
        """Waits for the answer of `route` asked after n0 (and, for a screen, a new 'results' mark): its log entry
        (cap 0: looks once)."""
        def check():
            got = [r for r in log[n0:] if r['k'] == route]
            if not got:
                return None
            if mark_count is not None and results_marks(f) <= mark_count:
                return None
            return got[-1]
        return check() if cap == 0 else wait_for(page, check, cap)

    def screen_action(page, log, f, label, act):
        n0, before = len(log), results_marks(f)
        t0 = time.time(); epoch = t0 * 1000
        acted = act(f)
        if acted is False:
            return {'outcome': 'skipped: nothing to act on'}
        refused = "() => document.querySelector('#resPane [role=alert]')?.textContent || null"
        got = wait_for(page, lambda: answered(page, log, n0, API + '/run', f, before, cap=0) or (probe(f, refused) and 'refused'))
        res = {'outcome': 'results' if isinstance(got, dict) else ('refused: ' + str(probe(f, refused))[:300]) if got else 'timeout',
               'edit': acted, 'to_results_s': round(time.time() - t0, 2)}
        got = got if isinstance(got, dict) else None
        if got:
            res['run'] = {k: got.get(k) for k in ('status', 'ms', 'bytes', 'answer')}
            res['runs_asked'] = sum(1 for r in log[n0:] if r['k'] == API + '/run')
        res['marks_ms'] = marks(f, epoch)
        res['longtasks'] = longtasks(f, epoch)
        quiet(page, log, ms=1000)
        res['requests'] = requests_of(log, n0)
        page.screenshot(path=str(out / f'{label}.png'))
        return res

    def load_preset(f):
        return probe(f, """id => { const all = [...document.querySelectorAll('[data-open^="p:"]')].filter(b => b.getAttribute('aria-disabled') !== 'true');
                                   const b = id ? all.find(x => x.dataset.open === 'p:' + id || x.dataset.open === id) : all[0];
                                   if (!b) return false; b.click(); return b.dataset.open }""", PRESET or '', default=False)

    def edit_value(f):
        """The first number field of the screen's conditions (a threshold first) moved by one step of its own (its step
        attribute, inside its min and max; a free number by 10 %), so the edit stays a valid definition."""
        return probe(f, """() => { const inp = document.querySelector('#cardC input.inp[type=number][data-k="value"]') || document.querySelector('#cardC input.inp[type=number]');
                                   if (!inp) return false;
                                   const v = Number(inp.value), step = Number(inp.step), lo = inp.min === '' ? -Infinity : Number(inp.min), hi = inp.max === '' ? Infinity : Number(inp.max);
                                   let next = Number.isFinite(step) && step > 0 ? v + step : (v === 0 ? 1 : Math.round(v * 1.1 * 1e4) / 1e4);
                                   if (next > hi) next = Number.isFinite(step) && step > 0 ? v - step : lo;
                                   if (next < lo) return false;
                                   inp.value = String(next);
                                   inp.dispatchEvent(new Event('input', { bubbles: true })); inp.dispatchEvent(new Event('change', { bubbles: true }));
                                   return (inp.dataset.k || inp.getAttribute('aria-label') || 'number') + ': ' + v + ' -> ' + next }""", default=False)

    # A. cold, B. warm
    ctx = new_ctx(); page = ctx.new_page()
    report['cold'], _, _ = open_tab(page, 'cold')
    page2 = ctx.new_page()
    report['warm'], log2, f2 = open_tab(page2, 'warm')
    # C. first run (a preset), D. edited run
    report['first_run'] = screen_action(page2, log2, f2, 'first_run', load_preset)
    report['first_run']['preset'] = next((r for r in [probe(f2, "() => document.querySelector('[data-open][aria-pressed=true]')?.dataset.open")] if r), None)
    report['edited_run'] = screen_action(page2, log2, f2, 'edited_run', edit_value)
    # E. preview: the first result row
    n0 = len(log2); t0 = time.time(); epoch = t0 * 1000
    clicked = probe(f2, "() => { const tr = document.querySelector('#resPane tr[data-tk]'); if (!tr) return null; tr.click(); return tr.dataset.tk }")
    got = answered(page2, log2, n0, API + '/preview', f2) if clicked else None
    report['preview'] = {'ticker': clicked, 'outcome': 'answered' if got else ('timeout' if clicked else 'skipped: no result row'),
                         'to_answer_s': round(time.time() - t0, 2)}
    if got:
        drawn = wait_for(page2, lambda: probe(f2, "() => !document.querySelector('#dtb .ml-loading') && document.getElementById('dtb').children.length > 0"), cap=30)
        report['preview'].update({'drawn_s': round(time.time() - t0, 2) if drawn else None,
                                  'answer': {k: got.get(k) for k in ('status', 'ms', 'bytes', 'answer')}})
    report['preview']['marks_ms'] = marks(f2, epoch)
    report['preview']['longtasks'] = longtasks(f2, epoch)
    quiet(page2, log2, ms=1000)
    report['preview']['requests'] = requests_of(log2, n0)
    page2.screenshot(path=str(out / 'preview.png'))

    # F. the routes on their own (same session); the page's last run and preview asked again under this script's order
    rq = ctx.request
    def timed(fn, n):
        xs, st = [], None
        for _ in range(n):
            t = time.time(); r = fn(); xs.append(round((time.time() - t) * 1000)); st = r.status
        return {'status': st, 'ms': xs, 'median': statistics.median(xs)}
    sess = rq.get(base + '/api/v1/auth/session').json(); tok = sess.get('csrf_token', '')
    SECRETS.update(x for x in (tok,) if x)
    H = {'Content-Type': 'application/json', 'Origin': base, 'X-CSRF-Token': tok}
    api = report['api'] = {'session': timed(lambda: rq.get(base + '/api/v1/auth/session'), 5)}
    for name in ('catalog', 'universe'):
        first = rq.get(base + f'{API}/{name}')
        tag = first.headers.get('etag')
        api[name] = timed(lambda: rq.get(base + f'{API}/{name}'), 3)
        api[name]['bytes'] = len(first.body())
        if tag:
            api[name + '_if_none_match'] = timed(lambda: rq.get(base + f'{API}/{name}', headers={'If-None-Match': tag}), 3)
    seq = {'n': 0}
    def again(route):
        sent = [r for r in log2 if r['k'] == API + route and r.get('request')]
        if not sent:
            return None
        body = json.loads(sent[-1]['request'])
        def one():
            seq['n'] += 1
            return rq.post(base + API + route, data=json.dumps({**body, 'client_order': {'page': 'pg_timing_' + str(int(t0)), 'seq': seq['n']}}), headers=H)
        return timed(one, 3)
    api['run_again'] = again('/run')
    api['preview_again'] = again('/preview')
    browser.close()
report['finished_at'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
(out / 'report.json').write_text(json.dumps(report, indent=1))
print('ok')
