"""EDGE Backtest page timing (2026-10-27, user: "1" = measure first, change nothing). Read-only timing of the EDGE Backtest page in Railway dev (no Run is submitted: a run writes a job and a trial).
Signs in as the owner (credentials read from edge-bff's Railway variables into memory, never printed), opens
/backtest (EDGE shell + iframe /backtest-app/), cold then warm, switches the ticker to a large one, loads a flow
template (broker files), and times the API routes directly. Writes OUT/report.json and screenshots."""
import json, os, statistics, subprocess, sys, time
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
BIG = sys.argv[2] if len(sys.argv) > 2 else 'BBRI'
v = json.loads(subprocess.run(['railway', 'variable', 'list', '-s', 'edge-bff', '-e', 'dev', '--json'],
                              capture_output=True, text=True, timeout=60, check=True).stdout)
base = 'https://' + v['RAILWAY_PUBLIC_DOMAIN']
login, password = v.get('EDGE_LOGIN'), v.get('EDGE_INITIAL_PASSWORD')
del v

INIT = """
window.__lt = []; window.__t0 = performance.timeOrigin;
try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__lt.push([Math.round(performance.timeOrigin + e.startTime), Math.round(e.duration)]) })
  .observe({ type: 'longtask', buffered: true }) } catch (e) {}
"""

def kind(url):
    p = url.split('?')[0]
    if '.t3.storageapi.dev' in p:
        return 'bucket:' + '/'.join(p.split('/v1/')[-1].split('/')[:2])
    p = p.replace(base, '')
    return p

report = {'base_host': base.split('//')[1], 'big': BIG}
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=os.environ.get('EDGE_TEST_CHROMIUM') or None, proxy={'server': os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')})

    def new_ctx():
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        ctx.add_init_script(INIT)
        r = ctx.request.post(base + '/api/v1/auth/sign-in', data=json.dumps({'login': login, 'password': password}),
                             headers={'Content-Type': 'application/json', 'Origin': base})
        if r.status != 200:
            raise SystemExit(f'sign-in failed ({r.status})')
        return ctx

    def watch(page):
        log = []
        def done(req):
            try:
                t = req.timing; resp = req.response()
                size = len(resp.body()) if resp and req.resource_type in ('fetch', 'xhr') else None
            except Exception:
                t, resp, size = {}, None, None
            log.append({'k': kind(req.url), 'm': req.method, 'type': req.resource_type, 'status': resp.status if resp else None,
                        'start': round(t.get('startTime', 0)), 'ms': round(t.get('responseEnd', 0)) if t.get('responseEnd', -1) >= 0 else None,
                        'bytes': size})
        page.on('requestfinished', done)
        page.on('requestfailed', lambda req: log.append({'k': kind(req.url), 'm': req.method, 'failed': req.failure}))
        return log

    def frame(page):
        for f in page.frames:
            if '/backtest-app/' in f.url:
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

    def longtasks(f, since_ms=0):
        lt = f.evaluate('window.__lt') if f else []
        lt = [x for x in lt if x[0] >= since_ms]
        return {'count': len(lt), 'total_ms': sum(d for _, d in lt), 'max_ms': max([d for _, d in lt], default=0)}

    def boot(page, label):
        log = watch(page); t0 = time.time()
        page.goto(base + '/backtest', wait_until='load', timeout=120000)
        t_shell = round(time.time() - t0, 2)
        page.wait_for_function("() => [...document.querySelectorAll('iframe')].some(f => f.src.includes('/backtest-app/'))", timeout=60000)
        f = None
        while f is None:
            f = frame(page); page.wait_for_timeout(50)
        f.wait_for_function("() => document.querySelectorAll('.js-run').length && [...document.querySelectorAll('.js-run')].every(b => !b.disabled)", timeout=180000)
        t_ready = round(time.time() - t0, 2)
        settle = quiet(page, log)
        res = {'shell_load_s': t_shell, 'ready_s': t_ready, 'network_quiet_s': round(t_ready + settle, 2), 'longtasks': longtasks(f),
               'requests': log}
        page.screenshot(path=str(out / f'{label}.png'))
        return res, f, log

    # A. cold
    ctx = new_ctx(); page = ctx.new_page()
    report['cold'], f, log = boot(page, 'cold')
    # B. warm (same browser profile: IndexedDB file cache kept)
    page2 = ctx.new_page()
    report['warm'], f2, log2 = boot(page2, 'warm')
    # C. switch to a large ticker (price only)
    mark = int(f2.evaluate('Date.now()')); n0 = len(log2); t0 = time.time()
    f2.evaluate(f"""() => {{ const s = document.querySelector('select[data-k="ticker"]'); s.value = '{BIG}'; s.dispatchEvent(new Event('change', {{bubbles:true}})) }}""")
    q = quiet(page2, log2)
    report['switch_ticker'] = {'to': BIG, 'network_quiet_s': q, 'longtasks': longtasks(f2, mark), 'requests': log2[n0:]}
    # D. a flow template (broker files of the ticker)
    mark = int(f2.evaluate('Date.now()')); n0 = len(log2)
    f2.evaluate("""() => document.querySelector('[data-tpl="Divergence + flow"]').click()""")
    q = quiet(page2, log2, ms=3000)
    report['flow_template'] = {'network_quiet_s': q, 'longtasks': longtasks(f2, mark), 'requests': log2[n0:]}
    page2.screenshot(path=str(out / 'flow.png'))

    # E. the routes on their own (same session)
    rq = ctx.request
    def timed(fn, n):
        xs = []
        for _ in range(n):
            t = time.time(); r = fn(); xs.append(round((time.time() - t) * 1000)); st = r.status
        return {'status': st, 'ms': xs, 'median': statistics.median(xs)}
    sess = rq.get(base + '/api/v1/auth/session').json(); tok = sess.get('csrf_token', '')
    H = {'Content-Type': 'application/json', 'Origin': base, 'X-CSRF-Token': tok}
    report['api'] = {
        'session': timed(lambda: rq.get(base + '/api/v1/auth/session'), 5),
        'catalog': timed(lambda: rq.get(base + '/api/v1/backtests/catalog'), 3),
        'bundle_price': timed(lambda: rq.post(base + '/api/terminal/v1/bundle', data=json.dumps({'ticker': BIG, 'datasets': ['price'], 'packs': True}), headers=H), 3),
        'bundle_price_broker': timed(lambda: rq.post(base + '/api/terminal/v1/bundle', data=json.dumps({'ticker': BIG, 'datasets': ['price', 'broker'], 'packs': True}), headers=H), 3),
    }
    b = rq.post(base + '/api/terminal/v1/bundle', data=json.dumps({'ticker': BIG, 'datasets': ['price', 'broker'], 'packs': True}), headers=H).json()
    report['api']['bundle_files'] = {ds: [{'year': x.get('year'), 'bytes': x.get('bytes'), 'pack': x.get('pack')} for x in d.get('files', [])] for ds, d in b.get('datasets', {}).items()}
    jobs = rq.get(base + '/api/v1/backtests?limit=10').json()
    items = jobs.get('items') or jobs.get('jobs') or (jobs if isinstance(jobs, list) else [])
    fin = [j for j in items if j.get('state') == 'FINISHED']
    report['api']['jobs_listed'] = len(items)
    if fin:
        jid = fin[0].get('request_id') or fin[0].get('id')
        t = time.time(); r = rq.get(base + f'/api/v1/backtests/{jid}/result'); ms = round((time.time() - t) * 1000)
        report['api']['result'] = {'status': r.status, 'ms': ms, 'bytes_json': len(r.body()), 'mode': fin[0].get('mode'),
                                   'result_bytes': fin[0].get('result_bytes') or fin[0].get('sizes')}
        report['api']['result_again'] = timed(lambda: rq.get(base + f'/api/v1/backtests/{jid}/result'), 3)
    browser.close()
(out / 'report.json').write_text(json.dumps(report, indent=1))
print('ok')
