/* EXEC-RADAR-VIEW (user 2026-11-28, "go kerjakan semuanya di branch"; the artifact https://claude.ai/artifact/2q6RANeiRs1JYx9pJxwnpz
   version 12): the browser check of the Radar's new view, each step named by its item, on the fixture build (the saved
   Radar files of tests/fixture/data, outside Git) or on another server (CHECK_BASE). No beta, no login, no network but
   this machine.
   R-V1 the board is one row per filter; R-V2 Table | Cards, remembered; R-V3 the "N stocks" pill; Met; the day's chips
   box of 3 rows; the Today card's fixed height; the frozen head; the column-head sort; the chart's axes; the logo place.

   Usage: npm run build:fixture && node tests/look/view.mjs   (CHECK_BASE=<url of /radar-app/>, CHECK_ONLY=<regex>).
   Uses the preinstalled Playwright (PLAYWRIGHT_MODULE_DIR). */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { existsSync, readFileSync } from 'node:fs';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url)), app = join(here, '..', '..');
const playwright = (() => {
  for (const f of [process.env.PLAYWRIGHT_MODULE_DIR, '/opt/node-tools/node_modules', import.meta.url].filter(Boolean)) {
    try { return createRequire(f.startsWith('file:') ? f : join(f, 'noop.js'))('playwright') } catch { /* next */ }
  }
  throw new Error('view: playwright not found (set PLAYWRIGHT_MODULE_DIR)');
})();
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' };
function serve() {
  const dist = join(app, 'dist-fixture'), fonts = join(app, '..', 'static', 'fonts');
  if (!existsSync(join(dist, 'index.html'))) throw new Error('view: run `npm run build:fixture` first');
  return new Promise(ok => {
    const srv = createServer((req, res) => {
      const p = new URL(req.url, 'http://x').pathname, send = (c, t, b) => { res.writeHead(c, { 'content-type': t }); res.end(b) };
      if (p.startsWith('/fonts/')) { const f = join(fonts, p.slice(7)); return existsSync(f) ? send(200, TYPES[extname(f)] || 'text/css', readFileSync(f)) : send(404, 'text/plain', '') }
      if (p.startsWith('/radar-app/')) { let f = join(dist, p.slice(11) || 'index.html'); if (!existsSync(f) || f.endsWith('/')) f = join(dist, 'index.html'); return send(200, TYPES[extname(f)] || 'application/octet-stream', readFileSync(f)) }
      send(404, 'text/plain', '');
    }).listen(0, () => ok({ srv, base: `http://localhost:${srv.address().port}/radar-app/` }));
  });
}
const local = process.env.CHECK_BASE ? null : await serve(), BASE = process.env.CHECK_BASE || local.base;
const ONLY = process.env.CHECK_ONLY ? new RegExp(process.env.CHECK_ONLY) : null;
const browser = await playwright.chromium.launch();
const fails = [], done = [];
let ctx, page, errs = [];
async function open(w, route = '#/radar', theme = 'light', o = {}) {
  await ctx?.close();
  ctx = await browser.newContext({ viewport: { width: w >= 1000 ? w - 56 : w, height: w >= 1000 ? 900 : w === 390 ? 844 : 740 }, deviceScaleFactor: 1, ...(o.touch ? { hasTouch: true, isMobile: true } : {}) });
  await ctx.addInitScript(t => { try { localStorage.setItem('edge-auth-monitor-theme', t) } catch {} }, theme);
  page = await ctx.newPage(); errs = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()) });
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(BASE + (theme === 'dark' ? '?theme=dark' : '') + route, { waitUntil: 'load' });
  await page.waitForSelector(route.startsWith('#/filter') ? '.ct-head' : '#kb .kc', { timeout: 20000 });
  await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(400);
}
const step = async (name, fn) => {
  if (ONLY && !ONLY.test(name)) return;
  try { await fn(); if (errs.length) throw new Error('console: ' + errs.join(' | ')); done.push(`ok   ${name}`) } catch (e) { fails.push(`${name}: ${e.message.split('\n')[0]}`); done.push(`FAIL ${name}`) }
};
const must = (ok, msg) => { if (!ok) throw new Error(msg) };
const settle = (ms = 350) => page.waitForTimeout(ms);
const sideways = () => page.evaluate(() => document.scrollingElement.scrollWidth - innerWidth);

/* ---------- R-V1, R-V3: the board ---------- */
for (const w of [1440, 1152, 390, 360]) for (const theme of ['light', 'dark']) await step(`R-V1 R-V3 the board: a row per filter, cards side by side, the "N stocks" pill (${w} ${theme})`, async () => {
  await open(w, '#/radar', theme);
  const m = await page.evaluate(() => [...document.querySelectorAll('#kb > .kc')].map(k => {
    const h = k.querySelector('.kh').getBoundingClientRect(), l = k.querySelector('.kl'), lb = l.getBoundingClientRect(), cards = [...l.querySelectorAll('.ki')];
    const tops = new Set(cards.map(c => Math.round(c.getBoundingClientRect().top))), pill = k.querySelector('.cpill');
    const hb = k.querySelector('.kh b').getBoundingClientRect(), t0 = cards.map(c => Math.round(c.querySelector('.t').getBoundingClientRect().top - c.getBoundingClientRect().top));
    const full = cards.every(c => c.querySelector('.t').getBoundingClientRect().width >= c.clientWidth - 2 * parseFloat(getComputedStyle(c).paddingLeft) - 2);
    return { id: k.querySelector('.kh b')?.textContent, full, left: hb.left - h.left < 30, tops: new Set(t0).size, side: innerWidth >= 721 ? h.right <= lb.left + 1 : h.bottom <= lb.top + 1, lines: tops.size, n: cards.length,
      pill: pill?.textContent || '', over: l.scrollWidth > l.clientWidth + 1, cue: l.classList.contains('xs-r'), zero: pill?.classList.contains('z') };
  }));
  must(m.length >= 7, `${m.length} filter rows`);
  for (const r of m) {
    must(r.side, `${r.id}: the head is not ${w >= 1000 ? 'left of' : 'above'} its cards`);
    must(r.n === 0 || r.lines === 1, `${r.id}: cards on ${r.lines} lines`);
    must(r.left, `${r.id}: the head's name is not at its left edge`);
    must(r.full, `${r.id}: a card's first line does not span the card (ticker left, change right)`);
    must(r.n === 0 || r.tops === 1, `${r.id}: the cards' first lines at ${r.tops} different heights`);
    must(r.pill === `${r.n} stock${r.n === 1 ? '' : 's'}`, `${r.id}: pill "${r.pill}" for ${r.n} cards`);
    must(!!r.zero === (r.n === 0), `${r.id}: the pill's grey state`);
    must(!r.over || r.cue, `${r.id}: the row scrolls sideways with no cue`);
  }
  must(await sideways() <= 0, `the page scrolls sideways ${await sideways()} px`);
});
await step('R-V1 a row scrolled to its end shows the cue on its left only', async () => {
  await open(1440);
  const r = await page.evaluate(async () => { const l = [...document.querySelectorAll('#kb .kl')].find(x => x.scrollWidth > x.clientWidth + 1); if (!l) return null; l.scrollLeft = l.scrollWidth; await new Promise(f => setTimeout(f, 120)); return [l.classList.contains('xs-l'), l.classList.contains('xs-r')] });
  must(r === null || (r[0] && !r[1]), `cues ${JSON.stringify(r)}`);
});
await step('logo place on the board, the table, the cards and the preview (monogram without the Terminal\'s logo list)', async () => {
  await open(1440);
  const b = await page.evaluate(() => [document.querySelectorAll('#kb .ki').length, document.querySelectorAll('#kb .ki .slg').length]);
  must(b[0] > 0 && b[0] === b[1], `board ${b[1]} of ${b[0]}`);
  await open(1440, '#/filter/S1');
  const t = await page.evaluate(() => [document.querySelectorAll('#tb tbody tr[data-s]').length, document.querySelectorAll('#tb tbody tr[data-s] .slg').length, !!document.querySelector('#pv .card-h .slg')]);
  must(t[0] > 0 && t[0] === t[1] && t[2], `table ${t[1]} of ${t[0]}, preview ${t[2]}`);
});

/* ---------- R-V2: Table | Cards, remembered ---------- */
await step('R-V2 Table | Cards: the cards show the filter\'s first four figures; the choice is remembered', async () => {
  await open(1440, '#/filter/S1');
  must(await page.locator('[data-dview] [data-v=table]').getAttribute('aria-pressed') === 'true', 'the page did not open on Table');
  const heads = await page.$$eval('#tb thead th', x => x.map(t => t.dataset.k));
  await page.click('[data-dview] [data-v=cards]'); await settle();
  const c = await page.evaluate(() => { const cards = [...document.querySelectorAll('#cg .rc')]; return { n: cards.length, chips: cards.map(k => k.querySelectorAll('.chips .chip').length), first: [...cards[0].querySelectorAll('.chip span')].map(s => s.textContent), sel: cards.filter(k => k.classList.contains('on')).length, inset: getComputedStyle(cards.find(k => k.classList.contains('on')) || cards[0]).boxShadow } });
  must(c.n > 0 && c.chips.every(n => n === Math.min(4, heads.filter(k => /^o\d/.test(k)).length)), `chips per card ${[...new Set(c.chips)]}`);
  must(c.sel === 1 && /inset/.test(c.inset), `selected card: ${c.sel}, ${c.inset}`);
  await page.reload({ waitUntil: 'load' }); await page.waitForSelector('.ct-head'); await settle();
  must(await page.locator('[data-dview] [data-v=cards]').getAttribute('aria-pressed') === 'true', 'Cards not remembered after a reload');
  await page.click('[data-dview] [data-v=table]'); await settle();
  must(await page.locator('#tb').count() === 1, 'Table did not come back');
});
await step('R-V2 the pills\' text is in their middle (within 1 px)', async () => {
  await open(1440, '#/filter/S1'); await page.click('[data-dview] [data-v=cards]'); await settle();
  const off = await page.evaluate(() => { const r = document.createRange(), o = []; for (const c of document.querySelectorAll('.rc .chip')) { const cb = c.getBoundingClientRect(); for (const t of c.children) { r.selectNodeContents(t); const b = r.getBoundingClientRect(); o.push(Math.abs((b.top + b.bottom) / 2 - (cb.top + cb.bottom) / 2)) } } return Math.max(0, ...o) });
  must(off <= 1, `${off.toFixed(1)} px off`);
});

/* ---------- Met ---------- */
await step('Met: All = Fully met + Partly met, each shows only its rows', async () => {
  await open(1440, '#/filter/S1');
  const n = await page.$$eval('[data-dmet] button .mn', x => x.map(s => +s.textContent));
  must(n[0] === n[1] + n[2], `All ${n[0]} ≠ ${n[1]} + ${n[2]}`);
  const rows = async v => { await page.click(`[data-dmet] [data-v=${v}]`); await settle(); return page.evaluate(() => [document.querySelectorAll('#tb tbody tr[data-s]:not(.nm)').length, document.querySelectorAll('#tb tbody tr.nm').length]) };
  const f = await rows('full'), p = await rows('part'), a = await rows('all');
  must(f[0] === n[1] && f[1] === 0 && p[0] === 0 && p[1] === n[2] && a[0] + a[1] === n[0], `full ${f} part ${p} all ${a}`);
});

/* ---------- the column-head sort ---------- */
await step('sort: click sorts by the measure, again reverses, a third time removes; levels; Clear sort only', async () => {
  await open(1440, '#/filter/S1');
  const vals = k => page.evaluate(k => { const ths = [...document.querySelectorAll('#tb thead th')], i = ths.findIndex(t => t.dataset.k === k); return [...document.querySelectorAll('#tb tbody tr[data-s]:not(.nm)')].map(r => r.children[i].textContent.trim()) }, k);
  const n = s => s === '—' ? null : parseFloat(s.replace(/−/g, '-').replace(/[^0-9.-]/g, ''));
  await page.click('#tb th[data-k=o1]'); await settle();
  let v = (await vals('o1')).map(n).filter(x => x != null);
  must(v.every((x, i) => !i || v[i - 1] >= x), `not descending: ${v.slice(0, 6)}`);
  await page.click('#tb th[data-k=o1]'); await settle();
  v = (await vals('o1')).map(n).filter(x => x != null);
  must(v.every((x, i) => !i || v[i - 1] <= x), `not ascending: ${v.slice(0, 6)}`);
  await page.click('#tb th[data-k=o3]'); await settle();
  const two = await page.evaluate(() => [document.querySelector('#tb th[data-k=o1] sup')?.textContent, document.querySelector('#tb th[data-k=o3] sup')?.textContent, document.querySelector('.ct-head .mss')?.textContent.trim()]);
  must(two[0] === '1' && two[1] === '2' && two[2] === 'Clear sort', `levels ${JSON.stringify(two)}`);
  await page.click('#tb th[data-k=o1]'); await settle();
  must(!(await page.locator('#tb th[data-k=o1] .sk').count()), 'a third click did not remove the level');
  await page.click('.ct-head .mss .rsr'); await settle();
  must(!(await page.locator('#tb th .sk').count()) && !(await page.locator('.ct-head .mss').count()), 'Clear sort left a level');
});

/* ---------- the frozen head ---------- */
for (const w of [1440, 1152, 390]) await step(`the frozen head: the head, its conditions and the column heads at the top once the charts are gone (${w})`, async () => {
  await open(w, '#/filter/S1');
  const m0 = await page.evaluate(() => ({ stuck: document.querySelector('.ct-head').classList.contains('stuck'), conds: !!document.querySelector('.ct-head .conds') }));
  must(!m0.stuck && m0.conds, `at the top: ${JSON.stringify(m0)}`);
  await page.evaluate(() => { document.querySelector('#view').scrollTop = 2400 }); await settle();
  const m = await page.evaluate(() => {
    const v = document.querySelector('#view').getBoundingClientRect().top, ch = document.querySelector('.ct-head'), box = ch.querySelector('.sth');
    const real = [...document.querySelectorAll('#tb thead th')].map(t => Math.round(t.getBoundingClientRect().width)), copy = [...box.querySelectorAll('th')].map(t => Math.round(t.getBoundingClientRect().width));
    const card = document.querySelector('.ct').getBoundingClientRect(), bb = box.getBoundingClientRect();
    return { top: Math.round(ch.getBoundingClientRect().top - v), stuck: ch.classList.contains('stuck'), shown: getComputedStyle(box).display !== 'none', same: real.join() === copy.join(), edges: [Math.round(bb.left - card.left), Math.round(card.right - bb.right)] };
  });
  must(m.top <= 0 && m.stuck && m.shown, `head ${JSON.stringify(m)}`);
  must(m.same, 'the copied column heads differ from the table\'s widths');
  must(m.edges.every(e => e >= 0 && e <= 2), `the column heads do not span the card: ${m.edges}`);
  await page.click('.ct-head .sth th[data-k=d1]'); await settle();
  must(await page.locator('#tb th[data-k=d1] .sk').count() === 1, 'a click on the frozen column head did not sort');
});

/* ---------- the day's chips box and the Today card ---------- */
await step('the Today card keeps one height on every date; its chips box is 3 rows and scrolls', async () => {
  await open(1440, '#/filter/S1');
  const hs = [];
  for (const i of [0, 1, 30, 60, 100]) {
    await page.evaluate(i => { const r = document.querySelectorAll('#h60 .hb'); r[r.length - 1 - i]?.dispatchEvent(new MouseEvent('click', { bubbles: true })) }, i); await settle(250);
    hs.push(await page.evaluate(() => [Math.round(document.querySelector('#tdy').getBoundingClientRect().height), Math.round(document.querySelector('.dchips').getBoundingClientRect().height), getComputedStyle(document.querySelector('.dchips')).overflowY]));
  }
  must(new Set(hs.map(h => h[0])).size === 1, `Today heights ${hs.map(h => h[0])}`);
  must(hs.every(h => h[1] === 78 && /auto|scroll/.test(h[2])), `chips boxes ${JSON.stringify(hs)}`);
});

/* ---------- the chart's axes ---------- */
await step('the chart: IHSG on the left axis, the stocks found on the right', async () => {
  await open(1440, '#/filter/S1');
  const m = await page.evaluate(() => { const svg = document.querySelector('#h60 svg'), W = +svg.getAttribute('width'); const t = [...svg.querySelectorAll('text')].map(x => ({ x: +x.getAttribute('x'), v: x.textContent })); const big = t.filter(x => /\d,\d{3}/.test(x.v)), small = t.filter(x => /^\d{1,2}$/.test(x.v)); return { big: big.every(x => x.x < W / 2), small: small.every(x => x.x > W / 2), nb: big.length, ns: small.length, lg: document.querySelector('.chart-h').textContent } });
  must(m.nb > 0 && m.ns > 0 && m.big && m.small, JSON.stringify(m));
  must(/Stocks found \(right\)/.test(m.lg) && /IHSG \(left\)/.test(m.lg), `legend: ${m.lg}`);
});

/* ---------- touch words and the touch areas of the new controls ---------- */
await step('a touch screen: the new controls take their tap areas; no page sideways scroll (390)', async () => {
  await open(390, '#/filter/S1', 'light', { touch: true });
  must(await sideways() <= 0, `the page scrolls sideways ${await sideways()} px`);
  const h = await page.evaluate(() => [...document.querySelectorAll('[data-dview] button, [data-dmet] button')].map(b => { const s = getComputedStyle(b, '::after'); return s.content !== 'none' ? Math.round(parseFloat(s.height) || b.getBoundingClientRect().height) : Math.round(b.getBoundingClientRect().height) }));
  must(h.every(x => x >= 30), `tap heights ${h}`);
});

console.log(done.join('\n'));
if (fails.length) { console.error(`\nview: ${fails.length} failed\n` + fails.join('\n')); process.exitCode = 1 } else console.log(`\nview: ${done.length} steps passed`);
await browser.close(); local?.srv.close();
