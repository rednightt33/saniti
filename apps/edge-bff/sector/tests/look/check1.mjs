/* EXEC-SECTOR-ANALYSIS check 1 (2026-11-27, verification/sector_analysis/check1/FIXES.md): the browser check of the page's
   layout and interactions that the five checkers found broken, on the fixture build (made-up files with the real data's
   edge cases, tests/fixture/make.mjs edgeCases). No beta, no login, no network but this machine.

   Layout, every tab at 1440, 1280 and 1152 px (the page is the shell's frame: 56 px narrower) and 390 and 360 px, light
   and dark: no text of a table, title or legend cut with an ellipsis; every sideways scroller that has more past an edge
   shows a cue; no chart drawn taller than its box or over its legend; no sideways scroll of the page; no console error.
   Interactions (1440 px): the Momentum card's corner names follow the shorter horizon (OR-1); a long Custom range of the
   weekly heatmap opens on its newest week (OR-3); Esc closes a stock popover (OR-4) whose figures keep one line (OR-5);
   the Custom popover refuses a date before the data (RP-1) and prints the range the card then prints (OR-6), the breadth
   line's from its first session (BD-7); the timeline's names do not overlap (RP-2); a map date picked on the strip moves
   Rotation detail (RP-3); the Formula chip reads by keyboard (RP-10); two quick date picks end on the last (BD-5); the
   Show list fits (BD-8); the date menu moves by arrow keys (BD-9) and the date survives a reload (BD-10); the header is
   off while only an error shows (MX-7); a stacked window shows its detail rows (OR-11, RP-11).

   Usage: npm run build:fixture && node tests/look/check1.mjs   (CHECK_BASE=<url of /sector-app/> checks another server,
   CHECK_ONLY=<regex> runs the steps whose name matches). Uses the preinstalled Playwright (PLAYWRIGHT_MODULE_DIR). */
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
  throw new Error('check1: playwright not found (set PLAYWRIGHT_MODULE_DIR)');
})();
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' };
function serve() {
  const dist = join(app, 'dist-fixture'), fonts = join(app, '..', 'static', 'fonts');
  if (!existsSync(join(dist, 'index.html'))) throw new Error('check1: run `npm run build:fixture` first');
  return new Promise(ok => {
    const srv = createServer((req, res) => {
      const p = new URL(req.url, 'http://x').pathname, send = (c, t, b) => { res.writeHead(c, { 'content-type': t }); res.end(b) };
      if (p.startsWith('/fonts/')) { const f = join(fonts, p.slice(7)); return existsSync(f) ? send(200, TYPES[extname(f)] || 'text/css', readFileSync(f)) : send(404, 'text/plain', '') }
      if (p.startsWith('/favicon')) return send(200, 'image/svg+xml', '<svg xmlns="http://www.w3.org/2000/svg"/>');
      if (p.startsWith('/sector-app/')) { let f = join(dist, p.slice(12) || 'index.html'); if (!existsSync(f) || f.endsWith('/')) f = join(dist, 'index.html'); return send(200, TYPES[extname(f)] || 'application/octet-stream', readFileSync(f)) }
      send(404, 'text/plain', '');
    }).listen(0, () => ok({ srv, base: `http://localhost:${srv.address().port}/sector-app/` }));
  });
}
const local = process.env.CHECK_BASE ? null : await serve(), BASE = process.env.CHECK_BASE || local.base;
const ONLY = process.env.CHECK_ONLY ? new RegExp(process.env.CHECK_ONLY) : null;
const browser = await playwright.chromium.launch();
const fails = [], done = [];
let ctx, page, errs = [];
async function open(w, theme = 'light', q = '', keep = false) {
  if (!keep) { await ctx?.close(); ctx = await browser.newContext({ viewport: { width: w >= 1000 ? w - 56 : w, height: w >= 1000 ? (w === 1440 ? 900 : 800) : w === 390 ? 844 : 740 }, deviceScaleFactor: 1 }) }
  await ctx.addInitScript(t => { try { localStorage.setItem('edge-auth-monitor-theme', t) } catch {} }, theme);
  page = await ctx.newPage(); errs = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()) });
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(BASE + q, { waitUntil: 'load' });
  if (!q.includes('fail=1')) { await page.waitForSelector('body[data-ready="1"]', { timeout: 15000 }); await page.evaluate(() => document.fonts.ready) }
}
const step = async (name, fn) => {
  if (ONLY && !ONLY.test(name)) return;
  try { await fn(); if (errs.length) throw new Error('console: ' + errs.join(' | ')); done.push(`ok   ${name}`) } catch (e) { fails.push(`${name}: ${e.message.split('\n')[0]}`); done.push(`FAIL ${name}`) }
};
const must = (ok, msg) => { if (!ok) throw new Error(msg) };
const tab = async t => { await page.click(`#tabs [data-t="${t}"]`); await page.waitForTimeout(500) };
const settle = () => page.waitForTimeout(400);

/* ---------- layout at every width and theme ---------- */
for (const w of [1440, 1280, 1152, 390, 360]) for (const theme of ['light', 'dark']) {
  await step(`layout ${w} ${theme}`, async () => {
    await open(w, theme);
    const bad = [];
    for (const t of ['ov', 'rs', 'rot', 'pm', 'br']) {
      await tab(t); await settle();
      bad.push(...(await page.evaluate(t => {
        const out = [], R = e => e.getBoundingClientRect();
        for (const c of document.querySelectorAll('.tabp:not([hidden]) [data-card]')) {
          const id = c.dataset.card;
          for (const e of c.querySelectorAll('td, th, .h3t, .lgd span, .dvb .r > span, .adr .nm, .cpi b')) {
            const cs = getComputedStyle(e);
            if (cs.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1) out.push(`${t}/${id}: "${e.textContent.trim().slice(0, 30)}" cut`);
          }
          for (const e of c.querySelectorAll('*')) {
            const cs = getComputedStyle(e);
            if (/(auto|scroll)/.test(cs.overflowX) && e.scrollWidth > e.clientWidth + 1 && !/xs-(r|l|sl)/.test(e.className)) out.push(`${t}/${id}: ${e.className} scrolls ${e.scrollWidth}>${e.clientWidth} without a cue`);
          }
          const lg = c.querySelector(':scope > .lgd');
          for (const b of c.querySelectorAll('[data-chart],[data-map],[data-strip]')) {
            const s = b.querySelector(':scope > svg'); if (!s) continue;
            if (R(s).bottom > R(b).bottom + 1 || (lg && R(s).bottom > R(lg).top + 1)) out.push(`${t}/${id}: chart ${Math.round(R(s).height)} px in a box of ${Math.round(R(b).height)} px`);
          }
        }
        const tabs = document.getElementById('tabs');
        if (tabs.scrollWidth > tabs.clientWidth + 1 && !/xs-(r|l)/.test(tabs.className)) out.push('the tab bar scrolls without a cue');
        if (document.documentElement.scrollWidth > innerWidth + 1) out.push(`the page scrolls sideways (${document.documentElement.scrollWidth})`);
        return out;
      }, t)));
    }
    must(!bad.length, bad.join(' | '));
  });
}

/* ---------- interactions at 1440 ---------- */
await step('OR-1 Momentum corners follow the shorter horizon', async () => {
  await open(1440);
  const card = page.locator('[data-card=mmCard]');
  await card.locator('[data-sel=x]').selectOption('1W'); await settle();
  await card.locator('[data-sel=y]').selectOption('1M'); await settle();
  const foot = await card.locator('[data-foot]').textContent();
  must(/bottom right = turning up/.test(foot), `foot reads "${foot}"`);
  const tl = await page.evaluate(() => [...document.querySelectorAll('[data-card=mmCard] text.qd')].map(t => [t.textContent, +t.getAttribute('x'), +t.getAttribute('y')]));
  for (const [t, x, y] of tl) { if (t === 'Turning up') must(x > 200 && y > 100, 'Turning up drawn top left with X = 1W'); }
});
await step('OR-3 a long Custom range of the weekly heatmap opens on its newest week', async () => {
  await open(1440); await tab('rs');
  const card = page.locator('[data-card=rsW]');
  await card.locator('[data-seg=w] [data-v=C]').click();
  const dates = await page.evaluate(() => [...document.querySelectorAll('.sx-rpop input')].map(i => i.max));
  const end = dates[0], d = new Date(end + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() - 175);
  await page.fill('.sx-rpop [data-r=a]', d.toISOString().slice(0, 10)); await page.fill('.sx-rpop [data-r=b]', end);
  await page.click('.sx-rpop [data-r=apply]'); await settle();
  const [l, w, cw] = await card.locator('.rsw-s').evaluate(x => [x.scrollLeft, x.scrollWidth, x.clientWidth]);
  must(w > cw && l + cw >= w - 2, `scrollLeft ${l} of ${w} (${cw} shown)`);
});
await step('OR-4 OR-5 Esc closes the market map popover; its figures keep one line', async () => {
  await open(1440);
  const tile = page.locator('[data-card=mkCard] .mk-t').first(); await tile.click(); await settle();
  const pop = page.locator('[data-card=mkCard] .sx-spop');
  must(await pop.isVisible(), 'the popover did not open');
  const rows = await pop.locator('.kv').evaluateAll(k => k.map(x => [Math.max(...[...x.children].map(e => e.getBoundingClientRect().height)), x.textContent]));
  for (const [h, t] of rows) must(h <= 22, `"${t}" wraps (${h} px)`);
  await page.keyboard.press('Escape'); await settle();
  must(!(await pop.isVisible()), 'Esc left the popover open');
});
await step('RP-1 OR-6 BD-7 the Custom popover: refuses a date before the data, prints the range the card prints', async () => {
  await open(1440);
  const card = page.locator('[data-card=rcCard]');
  await card.locator('[data-seg=w] [data-v=C]').click();
  const min = await page.locator('.sx-rpop [data-r=a]').getAttribute('min');
  const early = new Date(min + 'T00:00:00Z'); early.setUTCDate(early.getUTCDate() - 30);
  await page.fill('.sx-rpop [data-r=a]', early.toISOString().slice(0, 10));
  await page.locator('.sx-rpop [data-r=a]').dispatchEvent('input');
  must(await page.locator('.sx-rpop [data-r=apply]').isDisabled(), 'a start before the data was accepted');
  must(/^Pick dates from/.test(await page.locator('.sx-rpop .rp-n').textContent()), 'no refusal message');
  const max = await page.locator('.sx-rpop [data-r=b]').getAttribute('max'), a = new Date(max + 'T00:00:00Z'); a.setUTCDate(a.getUTCDate() - 90);
  await page.fill('.sx-rpop [data-r=a]', a.toISOString().slice(0, 10)); await page.locator('.sx-rpop [data-r=a]').dispatchEvent('input');
  const note = await page.locator('.sx-rpop .rp-n').textContent();
  await page.click('.sx-rpop [data-r=apply]'); await settle();
  const foot = await card.locator('.lgd > span').first().textContent();
  must(foot.startsWith(note), `popover "${note}" vs card "${foot}"`);
  // the breadth line: a level, shown from the first session of the range
  await tab('br');
  const br = page.locator('[data-card=brH]');
  await br.locator('[data-seg=p] [data-v=C]').click();
  await page.fill('.sx-rpop [data-r=a]', a.toISOString().slice(0, 10)); await page.locator('.sx-rpop [data-r=a]').dispatchEvent('input');
  const n2 = await page.locator('.sx-rpop .rp-n').textContent();
  await page.click('.sx-rpop [data-r=apply]'); await settle();
  const r2 = await br.locator('[data-range]').textContent();
  must(r2 === n2, `popover "${n2}" vs card "${r2}"`);
});
await step('RP-2 the timeline names and its labels do not overlap', async () => {
  await open(1440); await tab('rot');
  await page.locator('[data-card=rotA] [data-seg=v] [data-v=tl]').click(); await settle();
  const boxes = await page.evaluate(() => [...document.querySelectorAll('[data-card=rotA] .rrg text')].map(t => { const r = t.getBoundingClientRect(); return [t.textContent, r.left, r.top, r.right, r.bottom] }));
  const hit = (p, q) => p[1] < q[3] - 0.5 && q[1] < p[3] - 0.5 && p[2] < q[4] - 0.5 && q[2] < p[4] - 0.5;
  const over = []; boxes.forEach((p, i) => boxes.slice(i + 1).forEach(q => { if (hit(p, q)) over.push(`${p[0]}/${q[0]}`) }));
  must(!over.length, 'overlap: ' + over.slice(0, 6).join(', '));
});
await step('RP-3 a map date picked on the strip moves Rotation detail', async () => {
  await open(1440); await tab('rot');
  const s = page.locator('[data-card=rotA] [data-strip]'), b = await s.boundingBox();
  await page.mouse.click(b.x + b.width * 0.5, b.y + b.height * 0.5); await settle();
  const sub = await page.locator('[data-card=rotB] .ttl-s').textContent();
  must(/the map date/.test(sub), `Rotation detail reads "${sub}"`);
});
await step('RP-10 the Formula chip reads by keyboard', async () => {
  await open(1440); await tab('rot');
  await page.locator('[data-card=rotA] .dchip').focus(); await settle();
  must(await page.locator('.sx-tip').isVisible(), 'no read-out on focus');
});
await step('BD-5 two quick date picks end on the last one', async () => {
  const dates = await (async () => { await open(1440); await page.click('#datebtn'); return page.locator('#datepop .menu-item').evaluateAll(b => b.map(x => x.dataset.d)) })();
  await open(1440, 'light', `?slow=${dates[5]}:1500`);
  // both picks in one tick, the first one's file answering late (the checker's probe)
  await page.evaluate(([a, b]) => {
    const pick = d => { document.getElementById('datebtn').click(); document.querySelector(`#datepop [data-d="${d}"]`).click() };
    pick(a); pick(b);
  }, [dates[5], dates[2]]);
  await page.waitForTimeout(2200);
  const lab = await page.locator('#dlab').textContent(), want = await page.evaluate(d => { const x = new Date(d + 'T00:00:00Z'); return String(x.getUTCDate()) }, dates[2]);
  must(lab.includes(' ' + want + ' ') || lab.includes(' ' + want + ' '), `ended on "${lab}", picked ${dates[2]} last`);
});
await step('BD-8 the Show list fits on the screen', async () => {
  await open(1440); await tab('br');
  await page.locator('[data-card=brH] [data-show]').click(); await settle();
  const [sh, ch, bottom] = await page.locator('[data-card=brH] .bxp').evaluate(p => [p.scrollHeight, p.clientHeight, p.getBoundingClientRect().bottom]);
  must(sh <= ch + 1 && bottom <= 900, `list ${sh} px in ${ch} px, bottom ${bottom}`);
  await page.keyboard.press('Escape'); await settle();
  must(!(await page.locator('[data-card=brH] .bxp').isVisible()), 'Esc left the list open');
});
await step('BD-9 BD-10 the date menu moves by arrow keys; the date survives a reload', async () => {
  await open(1440);
  await page.click('#datebtn');
  const first = await page.evaluate(() => document.activeElement.dataset.d);
  await page.keyboard.press('ArrowDown'); await page.keyboard.press('ArrowDown');
  const now = await page.evaluate(() => document.activeElement.dataset.d);
  must(now && now !== first, 'ArrowDown did not move');
  await page.keyboard.press('Enter'); await page.waitForTimeout(600);
  await page.reload({ waitUntil: 'load' }); await page.waitForSelector('body[data-ready="1"]');
  await page.click('#datebtn');
  const on = await page.locator('#datepop .menu-item.on').getAttribute('data-d');
  must(on === now, `after the reload ${on}, picked ${now}`);
});
await step('MX-7 the header is off while only an error shows', async () => {
  await open(1440, 'light', '?fail=1'); await page.waitForTimeout(800);
  must(await page.locator('#datebtn').isDisabled() && await page.locator('#termbtn').isDisabled(), 'the date or Terminal button looks live');
});
await step('OR-11 RP-11 a stacked window shows its detail rows', async () => {
  await open(1440); await tab('rs');
  await page.locator('[data-card=rsD] .fwx').click(); await settle();
  // rows inside the window as it opens (its detail table, under the card's own part)
  const rows = await page.evaluate(() => {
    const fw = document.querySelector('.fw').getBoundingClientRect(), c = document.querySelector('.fw .fw-c').getBoundingClientRect(), tw = document.querySelector('.fw .fw-tw').getBoundingClientRect();
    const top = Math.max(fw.top, c.top, tw.top), bottom = Math.min(fw.bottom, c.bottom, tw.bottom);
    return [...document.querySelectorAll('.fw .fw-tw tbody tr')].filter(x => { const b = x.getBoundingClientRect(); return !x.hidden && b.top >= top - 1 && b.bottom <= bottom + 1 }).length;
  });
  must(rows >= 6, `${rows} stock rows visible`);
  await page.keyboard.press('Escape');
});

await step('OR-2 BD-4 the drill-down fits at 1440 px and the heatmap table at 1152 px', async () => {
  await open(1440); await tab('rs');
  const [a, b] = await page.locator('[data-card=rsD] .tbl-wrap').evaluate(x => [x.scrollWidth, x.clientWidth]);
  must(a <= b + 1, `drill-down ${a} px in ${b} px`);
  await open(1152); await tab('br');
  const [c, d] = await page.locator('[data-card=brT] .tbl-wrap').evaluate(x => [x.scrollWidth, x.clientWidth]);
  must(c <= d + 1, `heatmap table ${c} px in ${d} px`);
});
await step('OR-8 OR-12 the 8 weeks fit at 1280 px; the bottom row\'s legends keep one line at 1440 px', async () => {
  await open(1280); await tab('rs');
  const [a, b] = await page.locator('[data-card=rsW] .rsw-s').evaluate(x => [x.scrollWidth, x.clientWidth]);
  must(a <= b + 1, `8 weeks ${a} px in ${b} px`);
  await open(1440); await tab('rs');
  for (const id of ['rsL', 'rsW', 'rsA']) { const h = await page.locator(`[data-card=${id}] > .lgd`).evaluate(x => x.clientHeight); must(h <= 40, `${id} legend ${h} px`) }
});
await step('RP-4 every row of the pair matrix and the top 7 pairs show at 1440 and 1280 px', async () => {
  for (const w of [1440, 1280]) {
    await open(w); await tab('pm');
    const [a, b] = await page.locator('[data-card=pmM] .pmg-s').evaluate(x => [x.scrollHeight, x.clientHeight]);
    must(a <= b + 1, `${w}: matrix ${a} px in ${b} px`);
    const [c, d] = await page.locator('[data-card=pmS] .tbl-wrap').evaluate(x => [x.scrollHeight, x.clientHeight]);
    must(c <= d + 1, `${w}: top 7 ${c} px in ${d} px`);
  }
});
await step('RP-5 the stock quadrant\'s names are drawn over its dots', async () => {
  await open(1440); await tab('rot');
  const order = await page.evaluate(() => { const k = [...document.querySelectorAll('[data-card=rotC] svg > *')]; return [k.findIndex(e => e.matches('text.qn')), k.map((e, i) => e.matches('g.dt') ? i : -1).filter(i => i >= 0).pop()] });
  must(order[0] > order[1], `names at ${order[0]}, last dot at ${order[1]}`);
});
await step('RP-7 RP-8 Correlation keeps its order whatever the hidden spread period; a Δ beta dash says why', async () => {
  await open(1440); await tab('pm');
  const card = page.locator('[data-card=pmM]'), names = () => card.locator('.pmg .nm').evaluateAll(b => b.map(x => x.dataset.x));
  await card.locator('[data-seg=p] [data-v="3M"]').click(); await settle();
  await card.locator('[data-seg=m] [data-v=co]').click(); await settle();
  const a = await names();
  await card.locator('[data-seg=m] [data-v=sp]').click(); await settle();
  await card.locator('[data-seg=p] [data-v="5D"]').click(); await settle();
  await card.locator('[data-seg=m] [data-v=co]').click(); await settle();
  must(JSON.stringify(a) === JSON.stringify(await names()), 'the order changed with the spread period');
  const t = page.locator('[data-card=pmT]');
  await t.locator('[data-seg=w] [data-v="252"]').click(); await settle();
  const dashes = await t.locator('tbody td:nth-child(4)').evaluateAll(c => c.map(x => !!x.querySelector('.na[data-tip]') || x.textContent !== '—'));
  must(dashes.every(Boolean), 'a Δ beta dash without its reason');
});
await step('BD-11 the stock detail\'s dashes say why', async () => {
  await open(1440); await tab('br');
  await page.locator('[data-card=brH] [data-seg=m] [data-v="200"]').click(); await settle();
  const bare = await page.locator('[data-card=brD] tbody td').evaluateAll(c => c.filter(x => x.textContent.trim() === '—' && !x.querySelector('[data-tip]')).length);
  must(bare === 0, `${bare} bare dashes`);
});
await step('MX-8 a phone\'s Rotation detail window says tap, and no map it does not show', async () => {
  await ctx?.close();
  ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });
  page = await ctx.newPage(); errs = [];
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(BASE, { waitUntil: 'load' }); await page.waitForSelector('body[data-ready="1"]');
  await tab('rot');
  await page.locator('[data-card=rotB] .fwx').tap(); await settle();
  const t = await page.locator('.fw [data-card=rotB] .lgd').textContent();
  must(!/on the map|Ctrl|Click/.test(t), `the window reads "${t}"`);
  const f = await page.locator('.fw .fw-f').evaluate(x => getComputedStyle(x.parentElement).overflowY);
  must(f === 'auto', 'the phone window does not scroll as one');
});

await browser.close(); local?.srv.close();
console.log(done.join('\n'));
if (fails.length) { console.log('\n' + fails.join('\n')); process.exit(1) }
console.log(`\ncheck1: ${done.length} steps passed`);
