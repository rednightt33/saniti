"""Terminal drag lag on the beta (edge-bff dev), signed in as the owner (ERRORS M538): frame intervals, long tasks and a
CPU profile (self and inclusive time per function) during a horizontal, a vertical and a diagonal pan of 80 steps.
Credentials come from Railway into memory only (verification/screener/live_candles_dev.py), never printed.
  TERMINAL_LOCAL=<dir>   serve a local build (vite build --minify false --outDir <dir>) in place of the live bundle:
                         the live page and data, readable function names in the profile
  OPEN_PANELS=1          open the Statistics and Broker activity panels first
Usage: python3 verification/terminal_api/drag_lag/drag_live.py OUT_DIR [cpu throttle]"""
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
    for label, path in [('horizontal', lambda k: (.7 - .4 * __import__('math').sin(k / 80 * 3.14159), .5)),
                        ('vertical', lambda k: (.5, .5 - .3 * __import__('math').sin(k / 80 * 3.14159))),
                        ('diagonal', lambda k: (.7 - .35 * __import__('math').sin(k / 80 * 3.14159), .5 - .25 * __import__('math').sin(k / 80 * 3.14159)))]:
        f.evaluate(JS_SETUP)
        cdp.send('Profiler.enable'); cdp.send('Profiler.setSamplingInterval', {'interval': 200}); cdp.send('Profiler.start')
        x0, y0 = path(0); p.mouse.move(box['x'] + box['width'] * x0, box['y'] + box['height'] * y0); p.mouse.down()
        t0 = time.time()
        for k in range(81):
            x, y = path(k); p.mouse.move(box['x'] + box['width'] * x, box['y'] + box['height'] * y)
        ms = round((time.time() - t0) * 1000); p.mouse.up(); p.wait_for_timeout(400)
        prof = cdp.send('Profiler.stop')['profile']
        m = f.evaluate(JS_READ)
        print(f'--- {label} (throttle {THR}x) dragMs={ms}', json.dumps(m), flush=True)
        print('\n'.join(profile_top(prof)), flush=True)
    p.screenshot(path=f'{OUT}/after_drag.png')
    br.close()
