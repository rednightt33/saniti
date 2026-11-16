"""EXEC-OVERVIEW live page check on dev, signed in as the owner through the browser (credentials from Railway, in memory
only, never printed; the sign-in of verification/screener/live_candles_dev.py): the post-release fixes (P1-P4, B2, ERRORS
M446), the phone pages menu (1B) and the Custom range on the five panels (F1), each measured in the rendered page, not
looked at. The expected Custom figures are computed here from the files that live_check_dev.py downloaded and checked
against the database, so run that first and pass its OUT folder as FILES. Needs the Railway CLI on PATH (credentials)
and Playwright's Chromium. Writes three screenshots to OUT; prints one ok/FAIL line per check.
2026-11-15 (second release, `main` 724d130c): 33/33 ok (verification/overview/live_20261115/live_page_check.txt).
Usage: python3 verification/overview/live_page_check_dev.py FILES OUT"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'screener'))
import live_candles_dev as L  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

FILES, OUT = sys.argv[1], sys.argv[2]
rd = lambda n: json.load(open(f'{FILES}/{n}.json'))
st, series, meta = rd('overview-stocks'), rd('overview-series'), rd('overview-meta')
A, B = '2026-10-01', '2026-11-13'
di = st['dates']
first = next(i for i, d in enumerate(di) if d >= A)
last = max(i for i, d in enumerate(di) if d <= B)
base = first - 1


def ret(t):
    k = st['ticker'].index(t)
    c0, c1 = st['close'][k][base], st['close'][k][last]
    return (c1 / c0 - 1) * 100 if c0 and c1 is not None else None


pct = lambda v: ('+' if v > 0 else '−' if v < 0 else '') + f'{abs(v):.2f}%'
norm = lambda s: (s or '').replace(' ', ' ').strip()
fails, errs = [], []


def ok(c, m):
    if not c:
        fails.append(m)
    print(('ok   ' if c else 'FAIL ') + m, flush=True)


class Args:
    base_url = None


base_url, login, password = L.credentials(Args)
L.SECRETS.update(x for x in (password,) if x)

FIX_JS = """() => {
  const box = e => e.getBoundingClientRect();
  const vals = [...document.querySelectorAll('#ihk .kpi b')].map(b => Math.round(box(b).bottom));
  const ohlcOver = [...document.querySelectorAll('#ohlc b')].some(b => b.scrollWidth > b.clientWidth + 1);
  const cut = [...document.querySelectorAll('#kpis .k .lt, #kpis .k .s')].some(e => e.scrollWidth > e.clientWidth + 1);
  const heads = [...document.querySelectorAll('.card-h')].filter(h => h.querySelector('.seg') && !h.closest('.tmc')).map(h => {
    const seg = h.querySelector('.seg'), first = h.firstElementChild, hb = box(h), sb = box(seg), fb = box(first);
    const pad = parseFloat(getComputedStyle(h).paddingLeft);
    return { sameRow: sb.top < fb.bottom - 2, left: Math.abs(box(h.querySelector('.pctl') || seg).left - (hb.left + pad)) < 2 || Math.abs(sb.left - (hb.left + pad)) < 2, over: h.scrollWidth > h.clientWidth + 1 };
  });
  return { vals, ohlcOver, cut, heads, tabs: [...document.querySelectorAll('#tm .tile')].filter(t => t.tabIndex === 0).length,
           tmvs: document.querySelector('#tmvs').textContent, ffs: document.querySelector('.ff .ttl-s')?.textContent,
           doc: document.documentElement.scrollWidth - innerWidth };
}"""


def sign_in(ctx, mobile):
    p = ctx.new_page()
    p.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'favicon' not in m.text else None)
    p.on('pageerror', lambda e: errs.append(str(e)))
    p.goto(base_url + '/monitor', wait_until='domcontentloaded')
    p.locator('#auth-login').fill(login)
    p.locator('#auth-password').fill(password)
    p.get_by_role('button', name='Sign In', exact=True).click()
    p.wait_for_timeout(2500)
    p.goto(base_url + '/overview', wait_until='domcontentloaded')
    p.frame_locator('iframe.terminal-frame').locator('body[data-ready="1"]').wait_for(timeout=60000)
    p.wait_for_timeout(1500)
    frame = next(f for f in p.frames if '/overview-app/' in f.url)
    return p, frame


def fixes(f, tag, mobile, w, h):
    r = f.evaluate(FIX_JS)
    ok(len(set(r['vals'])) == 1, f'{tag}: P1 the three values under the IHSG chart share one bottom line {r["vals"]}')
    ok(not r['ohlcOver'] and not r['cut'], f'{tag}: OHLC values and KPI labels not cut')
    ok(all(not x['over'] and (x['sameRow'] or x['left']) for x in r['heads']), f'{tag}: B2 every panel header fits ({len(r["heads"])})')
    ok(r['tabs'] == 1, f'{tag}: one tab stop in the map ({r["tabs"]})')
    ok(r['tmvs'].startswith('All stocks') and r['ffs'] == 'All stocks · Regular board', f'{tag}: Top Movers and Foreign Flow say All stocks')
    ok(r['doc'] == 0, f'{tag}: no sideways overflow in the page ({r["doc"]})')
    (f.locator('#uni').tap if mobile else f.locator('#uni').click)()
    f.wait_for_timeout(250)
    um = f.evaluate("() => { const m = document.querySelector('.unipop'), l = m.querySelector('.unilist'); return { h: m.getBoundingClientRect().height, scroll: l.scrollHeight > l.clientHeight, focus: document.activeElement.tagName } }")
    ok(um['h'] <= 441 and um['scroll'], f'{tag}: P2 universe menu {round(um["h"])} px tall, its list scrolls')
    ok((um['focus'] != 'INPUT') if mobile else (um['focus'] == 'INPUT'), f'{tag}: search focused only with a mouse ({um["focus"]})')
    f.locator('body').press('Escape')
    n = f.locator('#tm .tile').count()
    clipped = f.evaluate("""() => { let bad = 0; const m = document.querySelector('#tm').getBoundingClientRect();
      for (const t of [...document.querySelectorAll('#tm .tile')]) { t.click(); const q = document.querySelector('#tm .pop');
        if (q) { const r = q.getBoundingClientRect(); if (r.top < m.top - .5 || r.bottom > m.bottom + .5 || r.left < m.left - .5 || r.right > m.right + .5) bad++; }
        document.querySelector('#tm .tile.on')?.click(); } return bad; }""")
    ok(clipped == 0, f'{tag}: P3 no tile popover cut off among {n} tiles ({clipped})')
    return n


def custom(f, sel, a, b, tap=False):
    (f.locator(sel).tap if tap else f.locator(sel).click)()
    f.locator('#cpa').fill(a)
    f.locator('#cpb').fill(b)
    f.locator('.cpop [data-act=apply]').click()
    f.wait_for_timeout(400)


with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path='/opt/pw-browsers/chromium', args=['--no-sandbox'])
    # desktop
    ctx = br.new_context(viewport={'width': 1440, 'height': 1100}, device_scale_factor=2)
    p, f = sign_in(ctx, False)
    fixes(f, '1440', False, 1440, 1100)
    small = f.evaluate("() => { const t = [...document.querySelectorAll('#tm .tile')].find(t => !t.querySelector('b')); if (!t) return null; const r = t.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, t: t.dataset.t } }")
    if small:
        fb = p.locator('iframe.terminal-frame').bounding_box()
        p.mouse.move(fb['x'] + small['x'], fb['y'] + small['y'])
        p.wait_for_timeout(150)
        tip = f.evaluate("() => { const e = document.querySelector('.ttip'); return e && !e.hidden ? e.textContent : null }")
        ok(bool(tip) and tip.startswith(small['t']), f'1440: P4 hover on unlabelled tile {small["t"]} shows "{(tip or "")[:40]}"')
        p.mouse.move(5, 5)
    else:
        ok(False, '1440: P4 no unlabelled tile found to hover')
    # Custom: validation
    f.locator('#tper [data-v=C]').click()
    ok(f.locator('.cpop').is_visible(), 'Custom opens its popover')
    f.locator('#cpa').fill('2025-08-25'); f.locator('#cpb').fill(B); f.locator('.cpop [data-act=apply]').click()
    ok('at most 1 year' in f.locator('.cp-err').text_content(), 'a range over a year is refused: ' + f.locator('.cp-err').text_content())
    f.locator('#cpa').fill(B); f.locator('#cpb').fill(A); f.locator('.cpop [data-act=apply]').click()
    ok('Swap them' in f.locator('.cp-err').text_content(), 'a reversed range is refused')
    f.locator('body').press('Escape')
    # Custom: market map, switched to all stocks for BBCA
    f.locator('#uni').click(); f.wait_for_timeout(200)
    f.locator('.unipop').get_by_text('All stocks', exact=False).first.click(); f.wait_for_timeout(600)
    custom(f, '#tper [data-v=C]', A, B)
    ok(norm(f.locator('#tbar .sum').text_content()).startswith('1 Oct – 13 Nov'), 'map names the range: ' + norm(f.locator('#tbar .sum').text_content())[:40])
    f.locator('#tm .tile[data-t=BBCA]').evaluate('e => e.click()')
    shown = norm(f.locator('#tm .pop .kv b').first.text_content())
    ok(shown == pct(ret('BBCA')), f'BBCA Custom return {shown} = {pct(ret("BBCA"))} from the live file')
    f.locator('#tm .tile.on').evaluate('e => e.click()')
    # Top Movers
    custom(f, '#tmvp [data-p=C]', A, B)
    gainers = f.eval_on_selector_all('#tmvb .tmv-g:first-child .tk', 'e => e.map(x => x.textContent)')
    day = rd(f'overview-day-{B}')
    day_stocks = {meta['stocks']['ticker'][i] for i in day['stocks']['i']}
    allr = sorted(((t, ret(t)) for t in st['ticker'] if ret(t) is not None and ret(t) > 0 and t in day_stocks), key=lambda x: (-x[1], x[0]))
    want = [t for t, _ in allr[:5]]
    ok(gainers == want, f'Top Movers Custom gainers {gainers} = {want}')
    # Sector performance
    custom(f, '#spp [data-p=C]', A, B)
    sd = series['dates']; sb = max(i for i, d in enumerate(sd) if d < A); se = sd.index(B)
    fin = (series['sector']['Financials'][se] / series['sector']['Financials'][sb] - 1) * 100
    fin_shown = norm(f.locator('#spb .bl .r[data-n="Financials"] b').text_content())
    ok(fin_shown == ('+' if fin > 0 else '−') + f'{abs(fin):.1f}%', f'Financials Custom {fin_shown} vs {fin:.2f} (from {sd[sb]})')
    # % above EMA
    custom(f, '#brpp [data-p=C]', A, B)
    big = norm(f.locator('#brpb .big b').text_content())
    ok(big == f'{round(series["above_ema50"][se])}%', f'% above EMA at the range end {big}')
    # Foreign Flow
    custom(f, '#ffp [data-v=C]', A, B)
    fl = series['flow']; idx = [i for i, d in enumerate(fl['dates']) if A <= d <= B]
    buy = sum(fl['foreign_buy'][i] for i in idx)
    fshown = norm(f.locator('#ffb .pd-kpis .kpi b').first.text_content())
    ok(fshown == f'Rp {buy / 1e12:.2f}T', f'Foreign Flow Custom buy {fshown} = Rp {buy / 1e12:.2f}T')
    h = f.evaluate('() => location.hash')
    ok(all(k + '2026-10-01_2026-11-13' in h for k in ('clr=', 'spr=', 'brr=', 'tmr=', 'ffr=')), 'the address keeps the five ranges')
    p.screenshot(path=f'{OUT}/live_custom_1440.png')
    ctx.close()
    # phone
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    p, f = sign_in(ctx, True)
    btn = p.locator('.topbar .pages-btn')
    ok(btn.is_visible(), 'phone: the pages button is in the header')
    btn.tap(); p.wait_for_timeout(250)
    items = p.locator('.pages-menu > button').all_text_contents()
    mb = p.locator('.pages-menu').bounding_box()
    ok(len(items) >= 2 and 'Overview' in items[0] and mb['x'] >= 0 and mb['x'] + mb['width'] <= 390,
       f'phone: pages menu lists {len(items)} pages, Overview first, inside the screen')
    p.screenshot(path=f'{OUT}/live_pages_menu_390.png')
    p.keyboard.press('Escape'); p.wait_for_timeout(200)
    ok(p.locator('.pages-menu').count() == 0, 'phone: Escape closes the pages menu')
    fixes(f, '390', True, 390, 844)
    f.locator('#ffp [data-v=C]').tap(); f.wait_for_timeout(200)
    fb = p.locator('iframe.terminal-frame').bounding_box()
    cb = f.locator('.cpop').bounding_box()
    ok(cb and cb['x'] >= 0 and cb['x'] + cb['width'] <= fb['width'] + 0.5, f'phone: Custom popover inside the screen (x {round(cb["x"])}, w {round(cb["width"])})')
    p.screenshot(path=f'{OUT}/live_custom_390.png')
    ctx.close()
    br.close()
del password
print('fails', len(fails), '| page errors', errs[:5] or 'none')
