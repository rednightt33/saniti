/* EXEC-SECTOR-ANALYSIS visual round 2 (2026-11-27; the user's decisions V1-V10 and UD76-UD79 in EXEC.md; the record:
   verification/sector_analysis/round2/CHANGES.md): the browser check of the layout and the clicks of each item, on the
   fixture build (made-up files) or on another server (CHECK_BASE, e.g. the published files of a date served locally).
   No beta, no login, no network but this machine.

   1 heat (V6, UD77 2A): every heat cell of the page is one of the Overview's seven solid steps, the same in both themes,
     and no heat cell is dimmed while a sector is locked or a pair chosen; the locked row's name cell is marked.
   2 window alignment (V3 V4, UD76 2a, 3A): in the seven windows the user named, side by side, the chart and the detail
     table end level, the detail table shows every row without scrolling and the chart keeps its least height.
   3 Cumulative return (V2): its list rows are 22-36 px, the chart is as tall as the list, the bars have room.
   4 stock momentum quadrant (V9): no legend under the chart; the x-axis title clears the card's edge at every width.
   5 Rotation detail window (C1): one 52 px band and one row grid on both sides, a list that does not scroll sideways,
     Ctrl click adds, Clear returns to one, "All columns" has the card's five columns; chips on a phone.
   6 Stretched pairs window: only "Spread across horizons", its headers, Rank by / filter / Show driving it.
   7 drill-down and Beta windows: every column edge of the lower table on a column edge of the upper one, nothing cut.
   8 pair unselect (V10, UD79 1A): opens with no pair chosen (automatic pair, said), a second click unselects.
   9 Rotation map (V8): Map with the strip above a wide plot and its readings; Timeline over the whole window with square
     cells, the strip on the week columns, the dates under the grid.
   Widths: 1440, 1280 and 1152 px (the shell's frame: 56 px narrower), 390 and 360 px; light and dark where it matters.

   Usage: npm run build:fixture && node tests/look/round2.mjs   (CHECK_BASE=<url of /sector-app/> checks another server,
   CHECK_ONLY=<regex> runs the steps whose name matches, SHOTS=<folder> saves a screenshot of each window checked). Uses the
   preinstalled Playwright (PLAYWRIGHT_MODULE_DIR). */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url)), app = join(here, '..', '..');
const playwright = (() => {
  for (const f of [process.env.PLAYWRIGHT_MODULE_DIR, '/opt/node-tools/node_modules', import.meta.url].filter(Boolean)) {
    try { return createRequire(f.startsWith('file:') ? f : join(f, 'noop.js'))('playwright') } catch { /* next */ }
  }
  throw new Error('round2: playwright not found (set PLAYWRIGHT_MODULE_DIR)');
})();
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' };
function serve() {
  const dist = join(app, 'dist-fixture'), fonts = join(app, '..', 'static', 'fonts');
  if (!existsSync(join(dist, 'index.html'))) throw new Error('round2: run `npm run build:fixture` first');
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
const ONLY = process.env.CHECK_ONLY ? new RegExp(process.env.CHECK_ONLY) : null, SHOTS = process.env.SHOTS || '';
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
const browser = await playwright.chromium.launch();
const fails = [], done = [];
let ctx, page, errs = [];
const WIDTHS = [1440, 1280, 1152, 390, 360];
async function open(w, theme = 'light', o = {}) {
  await ctx?.close();
  ctx = await browser.newContext({ viewport: { width: w >= 1000 ? w - 56 : w, height: w >= 1000 ? (w === 1440 ? 900 : 800) : w === 390 ? 844 : 740 }, deviceScaleFactor: 1, ...(o.touch ? { hasTouch: true, isMobile: true } : {}) });
  await ctx.addInitScript(t => { try { localStorage.setItem('edge-auth-monitor-theme', t) } catch {} }, theme);
  page = await ctx.newPage(); errs = [];
  page.on('console', m => { if (m.type() === 'error') errs.push(m.text()) });
  page.on('pageerror', e => errs.push(e.message));
  await page.goto(BASE + (theme === 'dark' ? '?theme=dark' : ''), { waitUntil: 'load' });
  await page.waitForSelector('body[data-ready="1"]', { timeout: 15000 }); await page.evaluate(() => document.fonts.ready);
}
const step = async (name, fn) => {
  if (ONLY && !ONLY.test(name)) return;
  try { await fn(); if (errs.length) throw new Error('console: ' + errs.join(' | ')); done.push(`ok   ${name}`) } catch (e) { fails.push(`${name}: ${e.message.split('\n')[0]}`); done.push(`FAIL ${name}`) }
};
const must = (ok, msg) => { if (!ok) throw new Error(msg) };
const tab = async t => { await page.click(`#tabs [data-t="${t}"]`); await page.waitForTimeout(450) };
const settle = (ms = 400) => page.waitForTimeout(ms);
const win = async (card, w, tag = '') => {
  await page.locator(`[data-card=${card}] .fwx`).first().click(); await settle(700);
  if (SHOTS) await page.screenshot({ path: join(SHOTS, `${card}${tag}-${w}.png`) });
};
const closeWin = async () => { await page.keyboard.press('Escape'); await settle(250) };
/** the window's frame: no part outside the screen, no sideways page scroll, no cut text in its tables */
const winFrame = () => page.evaluate(() => {
  const out = [], fw = document.querySelector('.fw'), r = fw.getBoundingClientRect();
  if (r.left < -1 || r.right > innerWidth + 1 || r.top < -1 || r.bottom > innerHeight + 1) out.push(`window ${Math.round(r.left)},${Math.round(r.top)}-${Math.round(r.right)},${Math.round(r.bottom)} outside ${innerWidth}x${innerHeight}`);
  if (document.documentElement.scrollWidth > innerWidth + 1) out.push('the page scrolls sideways');
  for (const e of fw.querySelectorAll('td, th, .c1-band *, .fw-dt b')) { const cs = getComputedStyle(e); if (cs.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1) out.push(`"${e.textContent.trim().slice(0, 24)}" cut`) }
  return out;
});

/* the seven steps as the browser paints them, per theme */
const STEPVARS = ['--red-600', '--red-500', '--red-300', '--sx-flat', '--green-300', '--green-500', '--green-600'];
const NAVYVARS = ['--navy-300', '--navy-500', '--navy-600', '--red-300', '--red-500', '--red-600', '--sx-flat'];
const painted = vars => page.evaluate(v => v.map(x => { const d = document.createElement('i'); d.style.background = `var(${x})`; document.body.appendChild(d); const c = getComputedStyle(d).backgroundColor; d.remove(); return c }), vars);

/* ---------- 1 heat ---------- */
for (const theme of ['light', 'dark']) await step(`1 heat cells are the seven steps and are never dimmed (${theme})`, async () => {
  await open(1440, theme);
  const steps = new Set(await painted(STEPVARS)), navy = new Set(await painted(NAVYVARS)), bad = [];
  const look = async (sel, set, what) => {
    await page.mouse.move(2, 2); await settle(200);                      // a cell under the pointer fades the others: not a lock
    const v = await page.$$eval(sel, (cs) => cs.map(c => [getComputedStyle(c).backgroundColor, +getComputedStyle(c).opacity, c.textContent.trim()]));
    if (!v.length) bad.push(`${what}: no cell`);
    for (const [bg, op, t] of v) { if (!set.has(bg)) bad.push(`${what} "${t}" ${bg}`); if (op < 0.99) bad.push(`${what} "${t}" opacity ${op}`) }
  };
  await look('[data-card=hxCard] .ovx-hm .c', steps, 'Sector × horizon');
  await look('[data-card=mkCard] .mk-t', steps, 'market map');
  const leg = await page.$$eval('[data-card=mkCard] .ovx-scl i', x => x.map(i => getComputedStyle(i).backgroundColor));
  must(leg.length === 7 && leg.every((c, k) => c === [...steps][k] || steps.has(c)), `market map legend ${leg.length} swatches`);
  // a locked sector: its name cell marked, nothing dimmed
  await page.locator('[data-card=hxCard] .nm[data-n]').nth(2).click(); await settle();
  await look('[data-card=hxCard] .ovx-hm .c', steps, 'Sector × horizon, locked');
  must(await page.locator('[data-card=hxCard] .nm.hl').count() === 1, 'the locked name cell is not marked');
  await tab('rs');
  await look('[data-card=rsW] .rsw .c[data-tip]', steps, 'weekly excess return, locked');
  await tab('br');
  await look('[data-card=brT] td.hc[style]', steps, 'breadth table');
  await page.locator('[data-card=brT] tbody tr[data-n]').nth(3).click(); await settle();
  await look('[data-card=brT] td.hc[style]', steps, 'breadth table, a sector chosen');
  await tab('pm');
  await look('[data-card=pmM] .pmg .c[data-a]', steps, 'pair matrix spread');
  await page.locator('[data-card=pmM] .pmg .c[data-a]').nth(5).click(); await settle();
  await look('[data-card=pmM] .pmg .c[data-a]', steps, 'pair matrix spread, a pair chosen');
  await page.click('[data-card=pmM] [data-seg=m] [data-v=co]'); await settle();
  await look('[data-card=pmM] .pmg .c[data-a]', navy, 'pair matrix correlation');
  must(!bad.length, bad.slice(0, 6).join(' | '));
});
await step('1 heat: the steps are the same colours in the light and the dark theme', async () => {
  await open(1440, 'light'); const a = await painted(STEPVARS.filter(x => x !== '--sx-flat'));
  await open(1440, 'dark'); const b = await painted(STEPVARS.filter(x => x !== '--sx-flat'));
  must(JSON.stringify(a) === JSON.stringify(b), `${a} vs ${b}`);
});

/* ---------- 2 the seven windows end level ---------- */
const FIT = [['ov', 'rcCard', '.ovx-cr'], ['ov', 'mmCard', '.ovx-cv'], ['ov', 'hxCard', '.hm-s'], ['rs', 'rsA', '.dvb'], ['rs', 'rsB', '.slope'], ['rs', 'rsW', '.rsw-s'], ['rs', 'rsL', '.rlc']];
for (const w of [1440, 1280]) for (const theme of ['light', 'dark']) await step(`2 the seven side-by-side windows end level at ${w} (${theme})`, async () => {
  await open(w, theme); const bad = [];
  for (const [t, card, grow] of FIT) {
    await tab(t); await win(card, w, `-${theme}`);
    const m = await page.evaluate(g => {
      const fw = document.querySelector('.fw'), l = fw.querySelector('.fw-l'), r = fw.querySelector('.fw-r'), tw = r.querySelector('.fw-tw');
      const rows = [...tw.querySelectorAll('tbody tr:not([hidden])')], last = rows[rows.length - 1].getBoundingClientRect().bottom, lg = l.querySelector(':scope > .lgd');
      const lb = (lg || l.lastElementChild).getBoundingClientRect().bottom, pane = r.getBoundingClientRect().bottom, gr = l.querySelector(g).getBoundingClientRect();
      return { stk: fw.classList.contains('stk'), last, lb, pane, scroll: tw.scrollHeight - tw.clientHeight, grow: gr.height, min: parseFloat(getComputedStyle(l.querySelector(g)).minHeight) || 0, svg: [...l.querySelectorAll('[data-chart] > svg')].map(s => s.getBoundingClientRect().bottom - s.parentElement.getBoundingClientRect().bottom) };
    }, grow);
    if (m.stk) { bad.push(`${card}: stacked`); await closeWin(); continue }
    if (Math.abs(m.last - m.lb) > 16) bad.push(`${card}: table ends ${Math.round(m.last)}, card ends ${Math.round(m.lb)}`);
    if (m.pane - m.last > 16) bad.push(`${card}: ${Math.round(m.pane - m.last)} px under the table`);
    if (m.scroll > 1) bad.push(`${card}: the table scrolls ${m.scroll} px`);
    if (m.grow + 1 < m.min) bad.push(`${card}: chart ${Math.round(m.grow)} < its least ${m.min}`);
    if (m.svg.some(x => x > 1)) bad.push(`${card}: chart drawn past its box`);
    bad.push(...(await winFrame()).map(x => `${card}: ${x}`));
    await closeWin();
  }
  must(!bad.length, bad.join(' | '));
});
await step('2 a window the viewer resized keeps the viewer\'s height', async () => {
  await open(1440); await win('mmCard', 1440);
  const h = await page.evaluate(() => { const fw = document.querySelector('.fw'); fw.style.height = '760px'; return fw.offsetHeight });
  await page.locator('.fw [data-sel=x]').selectOption('1W'); await settle(500);
  must(await page.evaluate(() => document.querySelector('.fw').offsetHeight) === h, 'the fit overrode the viewer\'s height');
});

/* ---------- 3 Cumulative return ---------- */
for (const w of WIDTHS) await step(`3 Cumulative return list: close rows, wide bars, the chart as tall as the list (${w})`, async () => {
  await open(w);
  const chk = async (root, what) => {
    const m = await page.evaluate(r => {
      const el = document.querySelector(r), bl = el.querySelector('.ovx-bl'), cv = el.querySelector('.ovx-cv'), rows = [...bl.querySelectorAll('.r')];
      const b = bl.getBoundingClientRect(), c = cv.getBoundingClientRect(), one = getComputedStyle(el.querySelector('.ovx-cr')).gridTemplateColumns.split(' ').length === 1;
      return { h: rows.map(x => x.getBoundingClientRect().height), bt: b.top, bb: b.bottom, ct: c.top, cb: c.bottom, bar: rows[0].querySelector('.tr').getBoundingClientRect().width, one };
    }, root);
    if (Math.min(...m.h) < 21.5 || Math.max(...m.h) > 36.5) throw new Error(`${what}: rows ${Math.round(Math.min(...m.h))}-${Math.round(Math.max(...m.h))} px`);
    if (!m.one && (Math.abs(m.bt - m.ct) > 2 || Math.abs(m.bb - m.cb) > 2)) throw new Error(`${what}: chart ${Math.round(m.ct)}-${Math.round(m.cb)}, list ${Math.round(m.bt)}-${Math.round(m.bb)}`);
    if (m.bar < 100) throw new Error(`${what}: bars ${Math.round(m.bar)} px`);
  };
  await chk('[data-slot=rcCard]', 'card');
  await win('rcCard', w); await chk('.fw [data-card=rcCard]', 'window');
});

/* ---------- 4 the stock momentum quadrant ---------- */
for (const w of WIDTHS) await step(`4 stock momentum quadrant: no legend, the x-axis title clear of the edge (${w})`, async () => {
  await open(w); await tab('rot');
  const chk = async (root, what) => {
    const m = await page.evaluate(r => {
      const el = document.querySelector(r), t = [...el.querySelectorAll('[data-chart] text.ax.t')].find(x => !x.getAttribute('transform')), box = el.closest('.fw') ? el.closest('.fw').querySelector('.fw-c') : el;
      const tb = t.getBoundingClientRect(), eb = box.getBoundingClientRect(), after = [...el.querySelectorAll('[data-chart] ~ *, .tb ~ *')].map(x => x.getBoundingClientRect().top);
      return { lgd: !!el.querySelector('.lgd'), gap: eb.bottom - tb.bottom, next: after.length ? Math.min(...after) - tb.bottom : 99 };
    }, root);
    if (m.lgd) throw new Error(`${what}: a legend is drawn`);
    if (m.gap < 6 || m.next < 4) throw new Error(`${what}: the x-axis title is ${Math.round(Math.min(m.gap, m.next))} px from the edge`);
  };
  await chk('[data-slot=rotC]', 'card');
  await win('rotC', w); await chk('.fw [data-card=rotC]', 'window');
});

/* ---------- 5 Rotation detail window (C1) ---------- */
for (const w of [1440, 1280, 1152]) await step(`5 Rotation detail window: one band, one row grid, Ctrl adds, Clear, All columns (${w})`, async () => {
  await open(w); await tab('rot'); await win('rotB', w);
  const m = await page.evaluate(() => {
    const fw = document.querySelector('.fw'), lb = fw.querySelector('.c1-band').getBoundingClientRect(), rb = fw.querySelector('.fw-dh').getBoundingClientRect();
    const lh = fw.querySelector('.c1-list thead th').getBoundingClientRect(), rh = fw.querySelector('.fw-tb thead th').getBoundingClientRect();
    const lr = [...fw.querySelectorAll('.c1-list tbody tr')].slice(0, 4).map(x => x.getBoundingClientRect()), rr = [...fw.querySelectorAll('.fw-tb tbody tr')].slice(0, 4).map(x => x.getBoundingClientRect());
    const list = fw.querySelector('.c1-list'), ctl = fw.querySelector('.fw-l > .card-h');
    return { lb: [lb.top, lb.height], rb: [rb.top, rb.height], lh: [lh.top, lh.height], rh: [rh.top, rh.height], lr: lr.map(x => [x.top, x.height]), rr: rr.map(x => [x.top, x.height]), side: list.scrollWidth - list.clientWidth, prev: !!ctl.querySelector('[data-seg=p]'), ctlTop: ctl.getBoundingClientRect().bottom <= Math.min(lb.top, rb.top) + 1 };
  });
  const near = (a, b, d = 1) => Math.abs(a - b) <= d;
  must(near(m.lb[0], m.rb[0]) && near(m.lb[1], 52) && near(m.rb[1], 52), `bands ${m.lb} vs ${m.rb}`);
  must(near(m.lh[0], m.rh[0]) && near(m.lh[1], m.rh[1]), `headers ${m.lh} vs ${m.rh}`);
  m.rr.forEach((r, k) => must(near(r[0], m.lr[k][0]) && near(r[1], 36) && near(m.lr[k][1], 36), `row ${k}: ${m.lr[k]} vs ${r}`));
  must(m.side <= 1, `the list scrolls sideways ${m.side} px`);
  must(m.prev && m.ctlTop, 'the Previous control is not in the row above both sides');
  const names = await page.$$eval('.fw .c1-list tbody tr', t => t.map(x => x.dataset.n));
  await page.locator(`.fw .c1-list tbody tr[data-n="${names[0]}"]`).click(); await settle();
  await page.locator(`.fw .c1-list tbody tr[data-n="${names[2]}"]`).click({ modifiers: ['Control'] }); await settle();
  must(await page.locator('.fw .c1-list tbody tr.on').count() === 2, 'Ctrl click did not add');
  const sub = await page.locator('.fw .fw-dt span').first().textContent();
  must(await page.$$eval('.fw .fw-tb tbody tr[data-i], .fw .fw-tb tbody tr:not(.fw-qn)', r => r.length) >= 1 && /,/.test(sub), `the changes of two sectors: "${sub}"`);
  await page.click('.fw [data-clear]'); await settle();
  must(await page.locator('.fw .c1-list tbody tr.on').count() === 1, 'Clear did not return to one');
  await page.click('.fw .fw-dh [data-seg=rv] [data-v=all]'); await settle();
  const heads = await page.$$eval('.fw .fw-tb thead th', t => t.map(x => x.textContent.replace(/[↑↓\d]+$/, '').trim()));
  must(heads.length === 5 && heads[1] === 'Current quadrant' && /^Previous/.test(heads[2]), `All columns: ${heads}`);
  const bad = await winFrame(); must(!bad.length, bad.join(' | '));
});
for (const w of [390, 360]) await step(`5 Rotation detail window on a phone: a row of sector chips above (${w})`, async () => {
  await open(w, 'light', { touch: true }); await tab('rot');
  await page.locator('[data-card=rotB] .fwx').tap(); await settle(700);
  const m = await page.evaluate(() => { const fw = document.querySelector('.fw'), c = fw.querySelector('.c1-chips'), b = c.querySelector('.c1-chip').getBoundingClientRect(); return { shown: getComputedStyle(c).display !== 'none', list: getComputedStyle(fw.querySelector('.c1-l')).display, h: b.height, above: c.getBoundingClientRect().bottom <= fw.querySelector('.fw-r').getBoundingClientRect().top + 1 } });
  must(m.shown && m.list === 'none' && m.h >= 32 && m.above, JSON.stringify(m));
  await page.locator('.fw .c1-chip').nth(3).tap(); await settle();
  must(await page.locator('.fw .c1-chip.on').count() === 1, 'a chip did not choose its sector');
  const bad = await winFrame(); must(!bad.length, bad.join(' | '));
});

/* ---------- 6 Stretched pairs window ---------- */
for (const w of [1440, 1152, 390]) await step(`6 Stretched pairs window: only Spread across horizons, driven by the card's controls (${w})`, async () => {
  await open(w); await tab('pm'); await win('pmS', w);
  must(!(await page.locator('.fw .fw-l table').count()), 'the window still shows the top table');
  const heads = await page.$$eval('.fw .fw-tb thead th', t => t.map(x => x.textContent.replace(/[↑↓]/g, '').trim()));
  must(JSON.stringify(heads) === JSON.stringify(['Pair', 'Spread 1D', 'Spread 3D', 'Spread 1W', 'Spread 2W', 'Spread 1M', 'Spread 3M']), `headers ${heads}`);
  const rows = () => page.$$eval('.fw .fw-tb tbody tr:not(.fw-qn):not([hidden])', t => t.map(r => [...r.children].map(c => c.textContent)));
  must((await rows()).length === 7, 'Top 7 does not show 7 rows');
  await page.click('.fw [data-seg=n] [data-v=all]'); await settle();
  const all = (await rows()).length; must(all > 7, `All shows ${all} rows`);
  await page.click('.fw [data-seg=h] [data-v="3D"]'); await settle();
  const v = (await rows()).map(r => Math.abs(parseFloat(r[2].replace('−', '-'))));
  must(v.every((x, i) => !i || v[i - 1] + 1e-9 >= x), 'not ranked by |Spread 3D|');
  must((await page.$$eval('.fw .fw-tb thead th.hc', t => t.map(x => x.textContent)))[0].startsWith('Spread 3D'), 'the ranking column is not marked');
  await page.click('.fw [data-seg=f] [data-v=up]'); await settle();
  must((await rows()).every(r => !r[2].startsWith('−')), 'Leader still ahead keeps a pair behind over 3D');
  const bad = await winFrame(); must(!bad.length, bad.join(' | '));
});

/* ---------- 7 drill-down and Beta: one column grid ---------- */
for (const w of [1440, 1280, 1152, 390]) await step(`7 drill-down and Beta windows: the two tables share their column edges (${w})`, async () => {
  await open(w); const bad = [];
  for (const [t, card, open2] of [['rs', 'rsD', false], ['rs', 'rsD', true], ['pm', 'pmT', false]]) {
    await tab(t); await win(card, w, open2 ? '-open' : '');
    if (open2) { await page.click('.fw [data-all]'); await settle(500) }
    const m = await page.evaluate(() => {
      const e = t => [...t.querySelector('thead tr').children].flatMap(c => { const b = c.getBoundingClientRect(); return [b.left, b.right] });
      const top = document.querySelector('.fw .fw-l table'), bot = document.querySelector('.fw .fw-tb');
      return { top: e(top), bot: e(bot), cut: [...document.querySelectorAll('.fw td, .fw th')].filter(x => getComputedStyle(x).textOverflow === 'ellipsis' && x.scrollWidth > x.clientWidth + 1).length, gut: [top.parentElement.clientWidth, bot.parentElement.clientWidth] };
    });
    const off = m.bot.filter(x => !m.top.some(y => Math.abs(x - y) <= 1));
    if (off.length) bad.push(`${card}${open2 ? ' open' : ''}: ${off.length} edges off the grid`);
    if (m.cut) bad.push(`${card}: ${m.cut} cells cut`);
    if (m.gut[0] !== m.gut[1]) bad.push(`${card}: scrollers ${m.gut[0]} vs ${m.gut[1]} px`);
    bad.push(...(await winFrame()).map(x => `${card}: ${x}`));
    await closeWin();
  }
  must(!bad.length, bad.join(' | '));
});

/* ---------- 8 pair unselect ---------- */
await step('8 the pair matrix opens with no pair chosen; a second click on a cell, a name, a pair or a Beta row unselects', async () => {
  await open(1440); await tab('pm');
  const none = async what => {
    await page.mouse.move(2, 2); await settle(200);
    const m = await page.evaluate(() => ({ on: document.querySelectorAll('[data-card=pmM] .pmg .nm.on, [data-card=pmM] .pmg .c.sel, [data-card=pmS] tbody tr.on, [data-card=pmT] tbody tr.on').length, auto: !!document.querySelector('[data-card=pmR] .pmauto'), sub: document.querySelector('[data-card=pmR] .ttl-s').textContent, dim: [...document.querySelectorAll('[data-card=pmM] .pmg > *')].some(x => +getComputedStyle(x).opacity < 0.99), hash: location.hash }));
    must(!m.on && m.auto && /^Automatic pair/.test(m.sub) && !m.dim && !/pmA/.test(decodeURIComponent(m.hash)), `${what}: ${JSON.stringify(m)}`);
  };
  await none('on opening');
  const cell = page.locator('[data-card=pmM] .pmg .c[data-a]').nth(7), a = await cell.getAttribute('data-a'), b = await cell.getAttribute('data-b');
  await cell.click(); await settle();
  must(await page.locator('[data-card=pmM] .pmg .c.sel').count() === 1 && await page.locator(`[data-card=pmM] .pmg .nm.on[data-x="${a}"]`).count() === 1, 'a cell did not choose its pair');
  must(!(await page.locator('[data-card=pmR] .pmauto').count()), 'the chosen pair still says automatic');
  await page.locator(`[data-card=pmM] .pmg .c[data-a="${a}"][data-b="${b}"]`).click(); await settle(); await none('the same cell again');
  await page.locator(`[data-card=pmM] .pmg .nm[data-x="${a}"]`).click(); await settle();
  must(await page.locator(`[data-card=pmM] .pmg .nm.on[data-x="${a}"]`).count() === 1, 'a name did not make A');
  await page.locator(`[data-card=pmM] .pmg .nm[data-x="${a}"]`).click(); await settle(); await none('the same name again');
  await page.locator('[data-card=pmS] tbody tr').first().click(); await settle();
  must(await page.locator('[data-card=pmS] tbody tr.on').count() === 1, 'a stretched pair did not choose');
  await page.locator('[data-card=pmS] tbody tr').first().click(); await settle(); await none('the same stretched pair again');
  const br = page.locator('[data-card=pmT] tbody tr').nth(2); await br.click(); await settle();
  must(await page.locator('[data-card=pmT] tbody tr.on').count() >= 1, 'a Beta row did not choose');
  await page.locator(`[data-card=pmT] tbody tr[data-n="${await br.getAttribute('data-n')}"]`).click(); await settle(); await none('the same Beta row again');
  // the Stretched pairs window: a row chosen there and again
  await win('pmS', 1440);
  await page.locator('.fw .fw-tb tbody tr[data-i]').first().click(); await settle();
  must(await page.locator('.fw .fw-tb tbody tr.on').count() === 1, 'a window row did not choose');
  await page.locator('.fw .fw-tb tbody tr[data-i]').first().click(); await settle();
  must(!(await page.locator('.fw .fw-tb tbody tr.on').count()), 'the same window row again did not unselect');
});

/* ---------- 9 Rotation map ---------- */
for (const w of [1440, 1280, 1152]) for (const theme of ['light', 'dark']) await step(`9 Rotation map window: the Map with its strip and readings, the Timeline over the whole window (${w} ${theme})`, async () => {
  await open(w, theme); await tab('rot'); await win('rotA', w, `-map-${theme}`);
  const m = await page.evaluate(() => {
    const fw = document.querySelector('.fw'), s = fw.querySelector('[data-strip]').getBoundingClientRect(), p = fw.querySelector('.rrg').getBoundingClientRect(), r = fw.querySelector('.fw-r');
    return { strip: s.height, above: s.bottom <= p.top + 1, ratio: p.width / p.height, readings: !!r && !r.hidden && r.getBoundingClientRect().width > 300, side: !fw.classList.contains('stk') };
  });
  must(m.strip > 60 && m.above, `the strip ${JSON.stringify(m)}`);
  must(m.readings, 'the readings table is not on the right');
  if (m.side) must(m.ratio >= 1.3, `the plot is ${m.ratio.toFixed(2)}:1 (the prototype's is wide)`);
  await page.click('.fw [data-seg=v] [data-v=tl]'); await settle(700);
  if (SHOTS) await page.screenshot({ path: join(SHOTS, `rotA-timeline-${theme}-${w}.png`) });
  const t = await page.evaluate(() => {
    const fw = document.querySelector('.fw'), r = fw.querySelector('.fw-r'), f = fw.querySelector('.fw-f'), box = fw.querySelector('.rrg');
    const cells = [...box.querySelectorAll('.tlr rect')].slice(0, 52).map(x => x.getBoundingClientRect());
    const strip = fw.querySelector('[data-strip] svg path:nth-of-type(2)'), d = strip?.getAttribute('d') || '', x0 = parseFloat(d.slice(1)), sb = fw.querySelector('[data-strip]').getBoundingClientRect();
    const rows = [...box.querySelectorAll('.tlr')].map(g => g.getBoundingClientRect().bottom), dates = [...box.querySelectorAll('svg > text.ax')].map(x => x.getBoundingClientRect());
    return { hidden: (!r || r.hidden || getComputedStyle(r).display === 'none') && (!f || getComputedStyle(f).display === 'none'), w: box.getBoundingClientRect().width, fw: fw.querySelector('.fw-c').getBoundingClientRect().width, sq: cells.map(c => c.width - c.height), x0: sb.left + x0, c0: cells[0].left + cells[0].width / 2, below: dates.every(x => x.top >= Math.max(...rows) - 1), dates: dates.map(x => [x.left, x.right]) };
  });
  must(t.hidden, 'the readings or their footer still show with the Timeline');
  must(t.w > t.fw - 80, `the Timeline is ${Math.round(t.w)} px of ${Math.round(t.fw)}`);
  must(t.sq.every(x => Math.abs(x) <= 0.6), 'cells are not square');
  must(Math.abs(t.x0 - t.c0) <= 1, `the strip starts at ${t.x0.toFixed(1)}, the first week's column at ${t.c0.toFixed(1)}`);
  must(t.below, 'the dates are not under the grid');
  for (let i = 1; i < t.dates.length; i++) for (let j = 0; j < i; j++) { const p = t.dates[i], q = t.dates[j]; must(!(p[0] < q[1] - 0.5 && q[0] < p[1] - 0.5), 'labels under the grid overlap') }
  const bad = await winFrame(); must(!bad.length, bad.join(' | '));
});
for (const w of [390, 360]) await step(`9 Rotation map on a phone: the Timeline's names and labels are whole (${w})`, async () => {
  await open(w); await tab('rot');
  await page.click('[data-card=rotA] [data-seg=v] [data-v=tl]'); await settle(600);
  const m = await page.evaluate(() => {
    const card = document.querySelector('[data-slot=rotA]'), b = card.getBoundingClientRect();
    const out = [...card.querySelectorAll('svg text')].map(t => t.getBoundingClientRect()).filter(r => r.left < b.left - 0.5 || r.right > b.right + 0.5).length;
    const strip = card.querySelector('[data-strip] svg text.dl')?.getBoundingClientRect(), ax = [...card.querySelectorAll('[data-strip] svg text.ax')].map(t => t.getBoundingClientRect());
    return { out, over: strip ? ax.filter(a => strip.left < a.right - 0.5 && a.left < strip.right - 0.5 && strip.top < a.bottom - 0.5 && a.top < strip.bottom - 0.5).length : 0 };
  });
  must(!m.out && !m.over, JSON.stringify(m));
});

await browser.close(); local?.srv.close();
console.log(done.join('\n'));
if (fails.length) { console.log('\n' + fails.join('\n')); process.exit(1) }
console.log(`\nround2: ${done.length} steps passed`);
