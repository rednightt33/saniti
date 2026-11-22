"""Two Terminal builds side by side on the beta, signed in as the owner, with the same preferences (read once, never
written): the chart after the same horizontal wheel scrolls (0, +600, -1400, +900 px), compared pixel by pixel, with the
legend titles. The owner's first four view-following indicators are shown; HIDE_B=1 hides them on both pages before each
scroll and shows them again after it (EXEC-TERMINAL-LAG-2 U2: a line not drawn gets its data when it is shown again).
A wheel scroll has no glide, so both pages reach the same view; a mouse drag does not (its glide differs by a session).
Usage: python3 verification/terminal_api/drag_lag/compare_builds.py OUT_DIR BUILD_A BUILD_B
       (each BUILD a `vite build --minify false --outDir` of apps/edge-bff/terminal)"""
import json, sys, os, time, mimetypes
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'screener'))
import live_candles_dev as L
from playwright.sync_api import sync_playwright
class _A: base_url = None
base, login, password = L.credentials(_A); L.SECRETS.update([password])
OUT, A, B = sys.argv[1:4]
VB = {'FL18','FL19','FL20','FL23','FL44','FL45','FL51','FL52'}
snap = {}
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path='/opt/pw-browsers/chromium', args=['--no-sandbox'])
    def page_for(build, hidden=False):
        ctx = br.new_context(viewport={'width': 1600, 'height': 960})
        def prefs(route):
            if route.request.method != 'GET': return route.abort()
            if 'body' not in snap:
                r = route.fetch(); body = r.json(); pv = body.get('preferences', {})
                if 'ml.symbol' in pv: pv['ml.symbol']['value'] = 'BBCA'
                ind = pv.get('ml.ind.v1')
                arr = json.loads(ind['value']); arr = [dict(x, on=True) for x in arr if x.get('def') in VB][:4]
                ind['value'] = json.dumps(arr); snap['body'] = body; snap['status'] = r.status; snap['headers'] = r.headers
            body = json.loads(json.dumps(snap['body']))
            if hidden: ind = body['preferences']['ml.ind.v1']; ind['value'] = json.dumps([dict(x, on=False) for x in json.loads(ind['value'])])
            route.fulfill(status=snap['status'], headers=snap['headers'], json=body)
        ctx.route('**/api/v1/preferences**', prefs)
        ctx.route('**/api/v1/terminal/**', lambda r: r.abort() if r.request.method != 'GET' else r.continue_())
        def serve(route):
            u = route.request.url.split('?')[0]; tail = u.split('/terminal-app/', 1)[1] or 'index.html'
            path = os.path.join(build, tail)
            if not os.path.isfile(path): return route.continue_()
            route.fulfill(path=path, content_type=mimetypes.guess_type(path)[0] or 'application/javascript')
        ctx.route('**/terminal-app/**', serve)
        p = ctx.new_page()
        p.goto(base + '/login', wait_until='domcontentloaded')
        p.locator('#auth-login').fill(login); p.locator('#auth-password').fill(password)
        p.get_by_role('button', name='Sign In', exact=True).click(); p.wait_for_timeout(2500)
        p.goto(base + '/terminal', wait_until='domcontentloaded'); p.wait_for_timeout(15000)
        return p, next(f for f in p.frames if '-app/' in f.url)
    pages = [page_for(A, hidden=os.environ.get('HIDE_B') == '1'), page_for(B, hidden=os.environ.get('HIDE_B') == '1')]
    titles = "() => [...document.querySelectorAll('.ind-row .ind-k')].map(e => e.textContent).join(' | ')"
    for step, dx in enumerate([0, 600, -1400, 900]):
        shots = []
        for k, (p, f) in enumerate(pages):
            box = f.locator('#chart').bounding_box()
            p.mouse.move(box['x'] + box['width'] * .5, box['y'] + box['height'] * .5)
            if os.environ.get('HIDE_B') == '1': f.evaluate("(want) => document.querySelectorAll('.ind-row').forEach(r => { const b = r.querySelector(':scope > [data-act=\"eye\"]') || r.querySelector('[data-act=\"eye\"]'); if (b && /Loaders|Inventory/.test(r.querySelector('.ind-k').textContent) && b.getAttribute('aria-pressed') !== String(want)) b.click() })", False); p.wait_for_timeout(500)
            if dx: p.mouse.wheel(dx, 0)
            p.wait_for_timeout(1200)
            if os.environ.get('HIDE_B') == '1':     # shown again after the move
                f.evaluate("(want) => document.querySelectorAll('.ind-row').forEach(r => { const b = r.querySelector(':scope > [data-act=\"eye\"]') || r.querySelector('[data-act=\"eye\"]'); if (b && /Loaders|Inventory/.test(r.querySelector('.ind-k').textContent) && b.getAttribute('aria-pressed') !== String(want)) b.click() })", True); p.wait_for_timeout(800)
            p.mouse.move(box['x'] + 3, box['y'] + 3); p.wait_for_timeout(600)
            path = f'{OUT}/cmp_{step}_{k}.png'; f.locator('#chart').screenshot(path=path); shots.append((path, f.evaluate(titles)))
        same_titles = shots[0][1] == shots[1][1]
        from PIL import Image, ImageChops
        a, b = (Image.open(x[0]).convert('RGB') for x in shots)
        d = ImageChops.difference(a, b); n = sum(1 for px in d.getdata() if px != (0, 0, 0))
        print(f'step {step} wheel {dx}: titles equal {same_titles}, differing pixels {n} box {d.getbbox()}', flush=True)
        if k == 1: print('  B shown:', f.evaluate("() => [...document.querySelectorAll('.ind-row [data-act=eye]')].map(b => b.getAttribute('aria-pressed')).join(',')"))
        if not same_titles: print('  A', shots[0][1][:300], '\n  B', shots[1][1][:300])
    br.close()
