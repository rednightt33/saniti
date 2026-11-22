"""Terminal: what a drag costs while it moves and once it is released (ERRORS M538, EXEC-TERMINAL-LAG-2 U1-U4), on the beta
signed in as the owner. Six one-way drags of 40 steps (left, right, three times): the long tasks while the pointer is held
and in the WAIT_MS after the release (the recompute of the indicators that follow the view lands there), frame intervals,
and a CPU profile. The owner's settings are read, never written: every write to /api/v1/preferences and
/api/v1/terminal/ is refused in the browser. Credentials come from Railway into memory only, never printed.
  SYMBOL=BBCA            the ticker opened (default BBCA; empty = the owner's own)
  FOUR=1 | FOUR=0        only the owner's first four view-following indicators (FL18-FL20, FL23, FL44, FL45, FL51, FL52),
                         all shown (1) or all hidden (0); unset = the owner's layout as saved
  DROP_VIEWBOUND=1       none of them (ONLY=<id>: just the first of that id)
  TERMINAL_LOCAL=<dir>   serve a local build (vite build --minify false --outDir <dir>) in place of the live bundle
  ROUNDS, WAIT_MS        rounds (3) and the wait after each release (1500)
  SETTLE_PROFILE=1       profile only the time after the release
Usage: python3 verification/terminal_api/drag_lag/drag_settle.py OUT_DIR [cpu throttle, e.g. 4 for a slower laptop]"""
import json, sys, os, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'screener'))
import live_candles_dev as L  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

class _A: base_url = None
def creds():
    for _ in range(5):
        try:
            b, l, p = L.credentials(_A); L.SECRETS.update([p]); return b, l, p
        except Exception:
            time.sleep(5)
    raise SystemExit('no credentials')
def sign_in(page, base, login, password):
    page.goto(base + '/login', wait_until='domcontentloaded')
    page.locator('#auth-login').fill(login); page.locator('#auth-password').fill(password)
    page.get_by_role('button', name='Sign In', exact=True).click(); page.wait_for_timeout(2500)
def app_frame(page):
    return next((f for f in page.frames if '-app/' in f.url), None)
OUT = sys.argv[1]; THR = float(sys.argv[2]) if len(sys.argv) > 2 else 1
base, login, password = creds()
JS_SETUP = """() => { const w = window; w.__lt = []; w.__fr = [];
  new PerformanceObserver(l => l.getEntries().forEach(e => w.__lt.push(e.duration))).observe({ type:'longtask' });
  let last = performance.now(); const tick = t => { w.__fr.push(t - last); last = t; if (w.__on) requestAnimationFrame(tick) }; w.__on = true; requestAnimationFrame(tick); }"""
JS_READ = """() => { const w = window; w.__on = false; const f = w.__fr.slice(2).sort((a, b) => a - b);
  return { frames:f.length, p50:+f[Math.floor(f.length*.5)].toFixed(1), p95:+f[Math.floor(f.length*.95)].toFixed(1), max:+f.at(-1).toFixed(1),
           over50:f.filter(x=>x>50).length, longtasks:w.__lt.length, longMs:Math.round(w.__lt.reduce((a,b)=>a+b,0)) } }"""
def profile_top(profile, n=22):
    dt = profile['timeDeltas']; idOf = {x['id']: x for x in profile['nodes']}; cnt = {}
    for k, i in enumerate(profile['samples']): cnt[i] = cnt.get(i, 0) + (dt[k] if k < len(dt) else 0)
    self = {}
    for i, us in cnt.items():
        f = idOf[i]['callFrame']; key = f"{f['functionName'] or '(anon)'} {f['url'].split('/')[-1][:40]}:{f['lineNumber']+1}"
        self[key] = self.get(key, 0) + us
    out = [f'{us/1000:7.0f} ms  {k}' for k, us in sorted(self.items(), key=lambda x: -x[1])[:n]]
    # total (inclusive) time per function, counted once per stack
    parent = {}
    for x in profile['nodes']:
        for c in x.get('children', []): parent[c] = x['id']
    tot = {}
    for i, us in cnt.items():
        seen = set(); j = i
        while j is not None:
            f = idOf[j]['callFrame']; key = f"{f['functionName'] or '(anon)'} {f['url'].split('/')[-1][:40]}:{f['lineNumber']+1}"
            if key not in seen: tot[key] = tot.get(key, 0) + us; seen.add(key)
            j = parent.get(j)
    out.append('  -- inclusive --')
    out += [f'{us/1000:7.0f} ms  {k}' for k, us in sorted(tot.items(), key=lambda x: -x[1]) if 'index-' in k][:n]
    return out
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path='/opt/pw-browsers/chromium', args=['--no-sandbox'])
    ctx = br.new_context(viewport={'width': 1600, 'height': 960}); p = ctx.new_page()

    VB = {'FL18','FL19','FL20','FL23','FL44','FL45','FL51','FL52'}
    DROP = os.environ.get('DROP_VIEWBOUND') == '1'
    def prefs(route):
        req = route.request
        if req.method != 'GET':
            print('blocked write', req.method, req.url.split('?')[0].rsplit('/', 1)[-1], flush=True); return route.abort()
        r = route.fetch(); body = r.json(); pv = body.get('preferences', {})
        sym = os.environ.get('SYMBOL', 'BBCA')
        if sym and 'ml.symbol' in pv: pv['ml.symbol']['value'] = sym
        ind = pv.get('ml.ind.v1')
        if ind:
            arr = json.loads(ind['value']) if isinstance(ind['value'], str) else ind['value']
            print('indicators', [x.get('def') for x in arr], flush=True)
            if os.environ.get('FOUR'):          # the owner's four view-following indicators only, shown (1) or hidden (0)
                arr = [dict(x, on=os.environ['FOUR'] == '1') for x in arr if x.get('def') in VB][:4]
                ind['value'] = json.dumps(arr) if isinstance(ind['value'], str) else arr
                print('four', [(x.get('def'), x.get('on')) for x in arr], flush=True)
            if DROP:
                only = os.environ.get('ONLY')
                if only: idx = next(i for i, x in enumerate(arr) if x.get('def') == only); keep = [arr[idx]]
                else: keep = [x for x in arr if x.get('def') not in VB]
                ind['value'] = json.dumps(keep) if isinstance(ind['value'], str) else keep
                print('kept', [x.get('def') for x in keep], flush=True)
        route.fulfill(response=r, json=body)
    ctx.route('**/api/v1/preferences**', prefs)
    def no_writes(route):
        if route.request.method != 'GET':
            print('blocked write', route.request.method, route.request.url.split('?')[0].split('/api/v1/')[-1], flush=True); return route.abort()
        route.continue_()
    ctx.route('**/api/v1/terminal/**', no_writes)
    LOCAL = os.environ.get('TERMINAL_LOCAL')
    if LOCAL:                                   # serve the local unminified build in place of the live bundle
        import mimetypes
        def serve(route):
            u = route.request.url.split('?')[0]; tail = u.split('/terminal-app/', 1)[1] or 'index.html'
            path = os.path.join(LOCAL, tail)
            if not os.path.isfile(path): return route.continue_()
            route.fulfill(path=path, content_type=mimetypes.guess_type(path)[0] or 'application/javascript')
        ctx.route('**/terminal-app/**', serve)
    sign_in(p, base, login, password)
    p.goto(base + '/terminal', wait_until='domcontentloaded'); p.wait_for_timeout(15000)
    f = app_frame(p)
    info = f.evaluate("() => ({ symbol: document.querySelector('#symbolPill')?.textContent?.trim(), canvases: document.querySelectorAll('canvas').length, panes: document.querySelectorAll('.ind-pane, .pane').length, bars: (window.ctx && window.ctx.ohlc) ? window.ctx.ohlc.length : null })")
    print('state', json.dumps(info), flush=True)
    if os.environ.get('OPEN_PANELS'):
        for sel in ('#statsExpand', '#rpExpand'):
            try: f.locator(sel).click(timeout=3000); p.wait_for_timeout(2500)
            except Exception as e: print('could not open', sel, str(e)[:80])
        print('panels', f.evaluate("() => ({stats: !!document.querySelector('.stats-open, body.stats-on, #statsPanel:not([hidden])'), w: document.querySelector('#chart').getBoundingClientRect().width})"), flush=True)
    cdp = ctx.new_cdp_session(p)
    if THR > 1: cdp.send('Emulation.setCPUThrottlingRate', {'rate': THR})
    box = f.locator('#chart').bounding_box()
    JS_LT = """() => { const w = window; w.__lt2 = []; new PerformanceObserver(l => l.getEntries().forEach(e => w.__lt2.push([Math.round(e.startTime), Math.round(e.duration)]))).observe({ type:'longtask' }); w.__t0 = performance.now() }"""
    f.evaluate(JS_LT)
    for rnd in range(int(os.environ.get('ROUNDS', '3'))):
        for label, x0, x1 in [('left', .75, .35), ('right', .35, .75)]:
            f.evaluate(JS_SETUP)
            cdp.send('Profiler.enable'); cdp.send('Profiler.setSamplingInterval', {'interval': 200}); cdp.send('Profiler.start')
            p.mouse.move(box['x'] + box['width'] * x0, box['y'] + box['height'] * .5); p.mouse.down()
            t0 = time.time()
            for k in range(41):
                x = x0 + (x1 - x0) * k / 40; p.mouse.move(box['x'] + box['width'] * x, box['y'] + box['height'] * .5)
            ms = round((time.time() - t0) * 1000)
            stopAt = f.evaluate("() => Math.round(performance.now())")
            if os.environ.get('SETTLE_PROFILE'): cdp.send('Profiler.stop'); cdp.send('Profiler.start')
            p.mouse.up(); p.wait_for_timeout(int(os.environ.get('WAIT_MS', '1500')))
            prof = cdp.send('Profiler.stop')['profile']
            m = f.evaluate(JS_READ)
            after = f.evaluate("s => window.__lt2.filter(e => e[0] >= s).map(e => e[1])", stopAt)
            during = f.evaluate("s => window.__lt2.filter(e => e[0] < s && e[0] >= window.__t0).map(e => e[1])", stopAt)
            f.evaluate("() => { window.__t0 = performance.now() }")
            print(f'--- {label} #{rnd} (throttle {THR}x) dragMs={ms} during={during} afterStop={after}', json.dumps(m), flush=True)
            if rnd == 0: print('\n'.join(l for l in profile_top(prof, 40) if os.environ.get('SETTLE_PROFILE') or any(w in l for w in ('followView','recompute','setData','refreshMulti','showTip','paintRow','compute','inclusive'))), flush=True)
    p.screenshot(path=f'{OUT}/after_drag.png')
    br.close()
