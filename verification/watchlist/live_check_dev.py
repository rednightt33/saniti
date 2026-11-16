"""EXEC-WATCHLIST W7: live check on dev, signed in as the owner (credentials from Railway, in memory only, never printed;
the sign-in of verification/screener/live_candles_dev.py). Leaves the account's lists as it found them, except that a
first "Watchlist" list exists afterwards (what the page's first visit and the Screener star create anyway).

1. The daily file through edge-bff: index -> file by sha256; saved to OUT/watchlist-stocks.json for
   validate_watchlist.py (the independent recalculation from PostgreSQL).
2. The lists API: create, rename, indicators, add, remove, delete (the deleted snapshot), Undo (create at the old
   position), refusals (control character, 9 indicators, a list over 50 stocks), the last list kept.
3. The Screener star fills the first list, and its removal empties it.
4. The page at 1440 and 390 px: the lists, one card per stock with the file's price, the Radar and corporate-action
   badges where the file has them, a loaded logo or the monogram on every card, the Radar filter and its toast, no "Figures unavailable", no console error, no
   sideways scroll. Screenshots to OUT.
Usage: python3 verification/watchlist/live_check_dev.py OUT     (Railway CLI on PATH, Playwright's Chromium)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screener'))
import live_candles_dev as L  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
fails, errs, bad = [], [], []


def ok(c, m):
    if not c:
        fails.append(m)
    print(('ok   ' if c else 'FAIL ') + m, flush=True)


class Args:
    base_url = None


for attempt in range(4):                                       # the CLI's variable list fails now and then (exit 1, no text)
    try:
        base, login, password = L.credentials(Args)
        break
    except Exception:                                           # noqa: BLE001
        if attempt == 3:
            raise
        import time
        time.sleep(5)
L.SECRETS.update(x for x in (password,) if x)
edge = L.Edge(base)
s, _, _, _ = edge.raw('POST', '/api/v1/auth/sign-in', {'login': login, 'password': password})
if s != 200:
    raise SystemExit(f'sign-in failed ({s})')
L.SECRETS.update(c.value for c in edge.jar if c.value)
s, sess, _ = edge.call('GET', '/api/v1/auth/session')
edge.csrf = (sess or {}).get('csrf_token', '')
L.SECRETS.update(x for x in (edge.csrf,) if x)
del sess
api = lambda m, p, b=None: edge.call(m, p, b, retries=1)
LP = '/api/v1/watchlist/lists'

# ---- 1. the daily file ------------------------------------------------------------------------------------------------
s, idx, _ = api('GET', '/api/v1/watchlist/index')
ok(s == 200, f'index {s}')
files = (idx or {}).get('files') or {}                      # app/pages.py: {finished_at, files: {name: {sha256, ...}}}
name = next(k for k in files if k.startswith('watchlist-stocks'))
sha = files[name]['sha256']
print('index', {'finished_at': idx.get('finished_at'), 'files': sorted(files)}, flush=True)
s, doc, _ = api('GET', f'/api/v1/watchlist/file/{name}?sha={sha}')
ok(s == 200 and doc.get('schema') == 1 and 0 < len(doc.get('ticker', [])) == len(doc.get('last', [])) == len(doc.get('trend', [])), f'file {s}: schema {doc.get("schema")}, {len(doc.get("ticker", []))} stocks, prices {doc.get("prices_through")}, broker {doc.get("broker_through")}, radar {doc.get("radar_date")}')
(OUT / 'watchlist-stocks.json').write_text(json.dumps(doc))
at = {t: i for i, t in enumerate(doc['ticker'])}
radar_t = sorted(doc['radar'])[0] if doc['radar'] else None
event_t = next((t for t in sorted(doc['events']) if t != radar_t), None)
print('sample', {'radar': radar_t, 'event': event_t}, flush=True)

# ---- 2. the Screener star (it creates the first list when the account has none) ---------------------------------------------------------------------------------------------
s, before, _ = api('GET', LP)
ok(s == 200, f'lists {s}: {len(before["lists"])} lists before')
for x in before['lists']:                                     # a list an interrupted run of this check left behind
    if x['name'].startswith('Live check'):
        if len(before['lists']) == 1:                         # the last list is kept: put the first list in its place
            api('POST', LP, {'name': 'Watchlist', 'position': 0})
        s, _, _ = api('DELETE', f'{LP}/{x["id"]}')
        print('removed a list left by an earlier run', s, flush=True)
s, before, _ = api('GET', LP)
star = [t for t in ('BBCA', radar_t, event_t) if t]
for t in star:
    s, _, _ = api('PUT', f'/api/v1/screener/watchlist/{t}')
    ok(s == 204, f'star {t} {s}')
s, lists, _ = api('GET', LP)
first = sorted(lists['lists'], key=lambda x: x['position'])[0]
ok([x['ticker'] for x in sorted(first['tickers'], key=lambda x: x['position'])][:len(star)] == star, f'the star fills the first list "{first["name"]}"')
s, sw, _ = api('GET', '/api/v1/screener/watchlist')
ok(s == 200 and set(star) <= {x['ticker'] for x in sw['tickers']}, 'the Screener reads its stars from the first list')

s, r, _ = api('DELETE', f'{LP}/{first["id"]}') if len(lists['lists']) == 1 else (409, {'error': {'code': 'LAST_LIST'}}, 0)
ok(s == 409 and (r.get('error') or {}).get('code') == 'LAST_LIST', f'the last list is kept {s}')

# ---- 3. the lists API -------------------------------------------------------------------------------------------------
s, before2, _ = api('GET', LP)
NAME = 'Live check 1116'
s, made, _ = api('POST', LP, {'name': NAME, 'tickers': ['TLKM', 'BBRI'], 'indicators': ['rsi', 'fn5']})
ok(s in (200, 201) and made['list']['name'] == NAME and [x['ticker'] for x in made['list']['tickers']] == ['TLKM', 'BBRI'], f'create {s}')
lid = made['list']['id']
s, r, _ = api('PATCH', f'{LP}/{lid}', {'name': NAME + ' b'})
ok(s == 200 and r['list']['name'] == NAME + ' b', f'rename {s}')
s, r, _ = api('PATCH', f'{LP}/{lid}', {'indicators': ['adx', 'ema50', 'dd60']})
ok(s == 200 and r['list']['indicators'] == ['adx', 'ema50', 'dd60'], f'indicators {s}')
s, r, _ = api('POST', f'{LP}/{lid}/tickers', {'tickers': ['ASII', 'TLKM']})
ok(s == 200 and r['added'] == ['ASII'] and r['already'] == ['TLKM'], f'add {s}: added {r.get("added")}, already {r.get("already")}')
s, _, _ = api('DELETE', f'{LP}/{lid}/tickers/TLKM')
ok(s == 204, f'remove a stock {s}')
s, r, _ = api('POST', f'{LP}/{lid}/tickers', {'tickers': ['TLKM'], 'position': 0})
s2, now, _ = api('GET', LP)
mine = next(x for x in now['lists'] if x['id'] == lid)
ok(s == 200 and [x['ticker'] for x in sorted(mine['tickers'], key=lambda x: x['position'])][0] == 'TLKM', 'Undo of a removed stock puts it back first')
s, r, _ = api('POST', LP, {'name': 'bad\u0000name'})
ok(s == 422 and (r.get('error') or {}).get('field') == 'name', f'control character refused {s}')
s, r, _ = api('PATCH', f'{LP}/{lid}', {'indicators': ['rsi', 'macdh', 'adx', 'ema50', 'ema200', 'r5d', 'r3m', 'volr', 'vol20']})
ok(s == 422, f'9 indicators refused {s}')
s, r, _ = api('POST', f'{LP}/{lid}/tickers', {'tickers': doc['ticker'][:60]})
ok(s in (409, 422) and 'At most 50' in json.dumps(r), f'over 50 stocks refused {s}')
s, gone, _ = api('DELETE', f'{LP}/{lid}')
snap = (gone or {}).get('deleted') or {}
ok(s == 200 and snap.get('name') == NAME + ' b' and snap.get('indicators') == ['adx', 'ema50', 'dd60'] and len(snap.get('tickers', [])) == 3, f'delete {s}: the deleted snapshot')
s, back, _ = api('POST', LP, {'name': snap['name'], 'tickers': [x['ticker'] for x in sorted(snap['tickers'], key=lambda x: x['position'])],
                              'indicators': snap['indicators'], 'position': snap['position']})
ok(s in (200, 201) and back['list']['position'] == snap['position'], f'Undo of a deleted list {s}: back at position {snap["position"]}')
s, _, _ = api('DELETE', f'{LP}/{back["list"]["id"]}')
s2, after, _ = api('GET', LP)
ok(s == 200 and [x['id'] for x in after['lists']] == [x['id'] for x in before2['lists']], f'cleanup {s}: lists as before')

# ---- 4. the page ------------------------------------------------------------------------------------------------------
PAGE_JS = """() => ({
  tabs: [...document.querySelectorAll('.bar1 .tabs [role=tab]')].map(t => [t.firstChild?.textContent.trim(), Number(t.querySelector('.cnt')?.textContent)]),
  cards: [...document.querySelectorAll('.cg .wc[data-t]')].map(c => ({ t: c.dataset.t, px: c.querySelector('.px b')?.textContent,
    radar: !!c.querySelector('.pill.radar'), event: !!c.querySelector('.pill.info') })),
  logos: [...document.querySelectorAll('.wc[data-t]')].map(c => { const e = c.querySelector('.lg'); return e ? (e.tagName === 'IMG' ? (e.naturalWidth > 0 ? 'logo' : 'broken') : 'monogram') : 'none' }),
  fileerr: document.querySelectorAll('.card.fileerr').length,
  warn: [...document.querySelectorAll('.pill.warn')].map(p => p.textContent),
  overflow: document.documentElement.scrollWidth - innerWidth })"""


def page_check(br, width, mobile):
    ctx = br.new_context(viewport={'width': width, 'height': 900 if not mobile else 844}, device_scale_factor=2,
                         is_mobile=mobile, has_touch=mobile)
    p = ctx.new_page()
    p.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'favicon' not in m.text else None)
    p.on('pageerror', lambda e: errs.append(str(e)))
    p.on('response', lambda r: bad.append(f'{r.status} {r.url.split("?")[0].replace(base, "")}') if r.status >= 400 else None)
    p.goto(base + '/monitor', wait_until='domcontentloaded')
    p.locator('#auth-login').fill(login)
    p.locator('#auth-password').fill(password)
    p.get_by_role('button', name='Sign In', exact=True).click()
    p.wait_for_timeout(2500)
    print(f'{width}px before the Watchlist:', bad or 'no failed response', flush=True)
    signed = len(errs), len(bad)
    p.goto(base + '/watchlist', wait_until='domcontentloaded')
    p.wait_for_timeout(1000)
    f = next(x for x in p.frames if '/watchlist-app/' in x.url)
    f.locator('.cg .wc[data-t]').first.wait_for(timeout=60000)
    # the page draws monograms first and swaps in the logos once the logo list is read (kept in localStorage on
    # success): wait for the list, then for every logo image, before anything is measured or photographed
    f.wait_for_function("""() => { let c = null; try { c = localStorage.getItem('edge.watchlist.logos') } catch (e) { return true }
      return !!c && [...document.querySelectorAll('.wc .lg')].every(e => e.tagName !== 'IMG' || (e.complete && e.naturalWidth > 0)) }""", timeout=30000)
    p.wait_for_timeout(500)
    have = set(f.evaluate("() => Object.keys((JSON.parse(localStorage.getItem('edge.watchlist.logos') || '{}').map) || {})"))
    v = f.evaluate(PAGE_JS)
    tag = f'{width}px'
    ok(v['tabs'][:1] == [[first['name'], len(star)]], f'{tag}: lists {v["tabs"]} (name, count)')
    ok([c['t'] for c in v['cards']] == star, f'{tag}: one card per stock {[c["t"] for c in v["cards"]]}')
    for c in v['cards']:
        i = at[c['t']]
        want = f'{round(doc["last"][i]):,}' if doc['last'][i] is not None else '—'
        ok(c['px'] == want, f'{tag}: {c["t"]} price {c["px"]} = file {want}')
        ok(c['radar'] == (c['t'] in doc['radar']), f'{tag}: {c["t"]} Radar badge {c["radar"]} (file {c["t"] in doc["radar"]})')
        ok(c['event'] == (c['t'] in doc['events']), f'{tag}: {c["t"]} corporate-action badge {c["event"]} (file {c["t"] in doc["events"]})')
    want = ['logo' if c['t'] in have else 'monogram' for c in v['cards']]
    ok(v['logos'] == want, f'{tag}: the logo where the logo list has one, else the monogram {v["logos"]} ({len(have)} logos listed)')
    ok(v['fileerr'] == 0 and 'Figures unavailable' not in v['warn'], f'{tag}: the figures were read')
    ok(v['overflow'] <= 0, f'{tag}: no sideways scroll ({v["overflow"]})')
    p.screenshot(path=str(OUT / f'watchlist_{width}.png'))
    ok(len(errs) == signed[0] and len(bad) == signed[1], f'{tag}: no failed response or console error on the Watchlist {bad[signed[1]:] + errs[signed[0]:]}')
    if radar_t:
        f.locator('[data-act=f-radar]').click()
        p.wait_for_timeout(500)
        shown = f.evaluate("() => [...document.querySelectorAll('.cg .wc[data-t]')].map(c => c.dataset.t)")
        toast = f.evaluate("() => document.querySelector('.toast, #toast')?.textContent || ''")
        ok(shown == [t for t in star if t in doc['radar']], f'{tag}: the Radar filter shows {shown}')
        ok('Filtered' in toast, f'{tag}: the filter toast "{toast.strip()[:60]}"')
        p.screenshot(path=str(OUT / f'watchlist_{width}_radar.png'))
        f.locator('[data-act=f-radar]').click()
    ctx.close()


with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path='/opt/pw-browsers/chromium', args=['--no-sandbox'])
    try:
        page_check(br, 1440, False)
        page_check(br, 390, True)
    finally:
        br.close()

# ---- cleanup: the stars removed, the first list left empty --------------------------------------------------------------
for t in star:
    s, _, _ = api('DELETE', f'/api/v1/screener/watchlist/{t}')
    ok(s == 204, f'unstar {t} {s}')
s, end, _ = api('GET', LP)
ok(all(not x['tickers'] for x in end['lists']) and len(end['lists']) == max(1, len(before['lists'])), f'cleanup: {len(end["lists"])} list(s), no stock left')
del password
print(json.dumps({'checks_failed': len(fails), 'failed': fails}), flush=True)
sys.exit(1 if fails else 0)
