/* EXEC-SECTOR-ANALYSIS check 2 (2026-11-27, verification/sector_analysis/check2/FIXES.md): the browser check of the
   findings of the second check that the page's layout, colours, words and focus decide, each step named by its finding,
   on the fixture build (made-up files) or on another server (CHECK_BASE, e.g. the published files of a date served
   locally). No beta, no login, no network but this machine. The drill-down window's width and the aligned tables' texts
   (OV2-1, RP2-4) are tests/look/round2.mjs step 7; the touch areas on every page (MX2-4, MX2-5, EW2-5, EW2-6) and the keyboard
   ring on every tab (BD2-1) verification/edge_states/round2_focus_contrast.mjs.

   Usage: npm run build:fixture && node tests/look/check2.mjs   (CHECK_BASE=<url of /sector-app/>, CHECK_ONLY=<regex>).
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
  throw new Error('check2: playwright not found (set PLAYWRIGHT_MODULE_DIR)');
})();
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml' };
function serve() {
  const dist = join(app, 'dist-fixture'), fonts = join(app, '..', 'static', 'fonts');
  if (!existsSync(join(dist, 'index.html'))) throw new Error('check2: run `npm run build:fixture` first');
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
const tab = async t => { await page.click(`#tabs [data-t="${t}"]`); await page.waitForTimeout(500) };
const settle = (ms = 400) => page.waitForTimeout(ms);
const win = async card => { await page.locator(`[data-card=${card}] .fwx`).first().click(); await settle(800) };
const closeWin = async () => { await page.keyboard.press('Escape'); await settle(250) };
const TABS = ['ov', 'rs', 'rot', 'pm', 'br'];
/* the contrast of an element's text on what is behind it */
const LIB = () => {
  const W = window;
  W.__rgba = s => { const m = String(s).match(/rgba?\(([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:[ ,/]+([\d.]+%?))?\)/); if (!m) return null; const a = m[4] === undefined ? 1 : m[4].endsWith('%') ? parseFloat(m[4]) / 100 : +m[4]; return [+m[1], +m[2], +m[3], a] };
  W.__lum = c => { const f = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]) };
  W.__ratio = (a, b) => { const x = W.__lum(a), y = W.__lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) };
  W.__over = (top, base) => [0, 1, 2].map(i => top[3] * top[i] + (1 - top[3]) * base[i]);
  W.__behind = el => { const layers = []; for (let e = el; e; e = e.parentElement) { const c = W.__rgba(getComputedStyle(e).backgroundColor); if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break } }
    let base = [255, 255, 255]; const root = W.__rgba(getComputedStyle(document.body).backgroundColor); if (root && root[3] >= 1) base = root.slice(0, 3);
    for (let i = layers.length - 1; i >= 0; i--) base = W.__over(layers[i], base); return base };
  // the colour an element's text paints with its own and its ancestors' opacity
  W.__ink = el => { let c = W.__rgba(getComputedStyle(el).color), op = 1; for (let e = el; e; e = e.parentElement) op *= +getComputedStyle(e).opacity; return [c[0], c[1], c[2], c[3] * op] };
};

/* ---------- OV2-3: the Custom popover's start ---------- */
await step('OV2-3 the Custom popover names the close a return starts from, and follows the dates typed', async () => {
  await open(1440);
  await page.locator('[data-card=rcCard] [data-seg=w] [data-v=C]').click(); await settle();
  const sp = t => t.replace(/\u00a0/g, ' ');
  const a = await page.evaluate(() => ({ from: document.querySelector('.sx-rpop [data-r=a]').value, note: document.querySelector('.sx-rpop .rp-x').textContent, msg: document.querySelector('.sx-rpop .rp-n').textContent }));
  a.note = sp(a.note); a.msg = sp(a.msg);
  const d = new Date(a.from + 'T00:00:00Z'), from = `${d.getUTCDate()} ${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getUTCMonth()]}`;
  const base = a.msg.split(' – ')[0];
  must(a.note.includes(`the ${base} close`) && a.note.includes(`(${from})`), `From ${a.from}, printed ${a.msg}, note "${a.note}"`);
  // a date typed: the note follows it
  await page.fill('.sx-rpop [data-r=a]', '2026-06-02'); await page.dispatchEvent('.sx-rpop [data-r=a]', 'input'); await settle(150);
  const b = await page.evaluate(() => ({ note: document.querySelector('.sx-rpop .rp-x').textContent, msg: document.querySelector('.sx-rpop .rp-n').textContent }));
  b.note = sp(b.note); b.msg = sp(b.msg);
  if (!/^Pick/.test(b.msg)) must(b.note.includes(`the ${b.msg.split(' – ')[0]} close`), `after typing: "${b.msg}" / "${b.note}"`);
});

/* ---------- RP2-1 / RP2-5: the Timeline ends where its legend is ---------- */
const tlGap = scope => page.evaluate(scope => {
  const root = document.querySelector(scope), svg = root.querySelector('.rrg > svg'), lg = root.querySelector('.lgd');
  const s = svg.getBoundingClientRect(), l = lg.getBoundingClientRect(), fw = root.closest('.fw'), c = fw ? fw.querySelector('.fw-c').getBoundingClientRect() : root.getBoundingClientRect();
  return { blank: Math.round(l.top - s.bottom), below: Math.round(c.bottom - l.bottom), rows: svg.querySelectorAll('.tlr').length };
}, scope);
for (const w of [1440, 1280, 1152]) for (const way of ['switched in the window', 'set on the card first']) await step(`RP2-1 the Timeline window ends under its legend (${w}, ${way})`, async () => {
  await open(w); await tab('rot');
  if (way === 'set on the card first') { await page.click('[data-card=rotA] [data-seg=v] [data-v=tl]'); await settle(600); await win('rotA') }
  else { await win('rotA'); await page.click('.fw [data-seg=v] [data-v=tl]'); await settle(900) }
  await settle(400);
  const g = await tlGap('.fw .fw-l');
  must(g.rows > 0, 'no timeline drawn');
  must(g.blank <= 16, `${g.blank} px of blank between the dates and the legend`);
  must(g.below <= 2, `the legend ends ${g.below} px above the window's bottom`);
  // and back to the Map: its readings and the window fitted to them
  await page.click('.fw [data-seg=v] [data-v=map]'); await settle(900);
  must(await page.evaluate(() => !document.querySelector('.fw .fw-r').hidden), 'the readings did not come back with the Map');
});
for (const w of [1440, 1152, 390]) await step(`RP2-5 the Timeline card: no blank band under the dates (${w})`, async () => {
  await open(w); await tab('rot');
  await page.click('[data-card=rotA] [data-seg=v] [data-v=tl]'); await settle(900);
  const g = await tlGap('[data-slot=rotA]');
  must(g.blank <= 16, `${g.blank} px of blank between the dates and the legend`);
});

/* ---------- RP2-2: the stock quadrant's names and labels ---------- */
for (const w of [1440, 1152, 390, 360]) await step(`RP2-2 the stock quadrant: stock names apart, never on a quadrant's name (${w})`, async () => {
  await open(w); await tab('rot');
  const m = await page.evaluate(() => {
    const box = document.querySelector('[data-card=rotC] .qdp'), r = e => e.getBoundingClientRect();
    const lb = [...box.querySelectorAll('text.lb')].map(r), qn = [...box.querySelectorAll('text.qn')].map(r), bad = [];
    const hit = (a, b, m) => a.left < b.right + m && b.left < a.right + m && a.top < b.bottom && b.top < a.bottom;
    for (let i = 0; i < lb.length; i++) { for (let j = 0; j < i; j++) if (hit(lb[i], lb[j], 1)) bad.push('label on label'); for (const q of qn) if (hit(lb[i], q, 0)) bad.push('label on a quadrant name') }
    return { bad, n: lb.length, names: qn.length };
  });
  must(m.names === 4 && !m.bad.length, JSON.stringify(m));
});

/* ---------- RP2-3 / MX2-2: the Rotation detail band on a phone ---------- */
for (const w of [390, 360]) await step(`RP2-3 MX2-2 the Rotation detail window on a phone: its switch on one line, its band's texts whole (${w})`, async () => {
  await open(w); await tab('rot'); await win('rotB');
  const m = await page.evaluate(() => {
    const dh = document.querySelector('.fw .fw-dh'), tops = [...dh.querySelectorAll('.seg button')].map(b => Math.round(b.getBoundingClientRect().top));
    const cut = [...dh.querySelectorAll('.fw-dt b, .fw-dt span')].filter(e => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1).map(e => e.textContent.slice(0, 20));
    return { tops, cut, seg: Math.round(dh.querySelector('.seg').getBoundingClientRect().height) };
  });
  must(new Set(m.tops).size === 1, `the switch's buttons on ${new Set(m.tops).size} lines`);
  must(!m.cut.length, `cut: ${m.cut.join(', ')}`);
});

/* ---------- MX2-1: every sideways scroller with more past an edge shows its cue ---------- */
const uncued = () => page.evaluate(() => [...document.querySelectorAll('*')].filter(e => {
  const s = getComputedStyle(e); if (!/auto|scroll/.test(s.overflowX) || e.scrollWidth <= e.clientWidth + 1) return false;
  const b = e.getBoundingClientRect(); if (!b.width || !b.height || e.closest('[hidden]') || s.visibility === 'hidden' || e === document.scrollingElement) return false;
  if (document.querySelector('.fw') && !e.closest('.fw')) return false;
  const right = e.scrollLeft + e.clientWidth < e.scrollWidth - 1, left = e.scrollLeft > 1;
  return (right && !e.classList.contains('xs-r')) || (left && !e.classList.contains('xs-l') && !e.classList.contains('xs-sl'));
}).map(e => `${e.tagName.toLowerCase()}.${[...e.classList].join('.')} ${e.scrollWidth}>${e.clientWidth}`));
for (const w of [390, 360]) await step(`MX2-1 every sideways scroller with more past an edge shows its cue, on every tab and in its windows (${w})`, async () => {
  await open(w); const bad = [];
  for (const t of TABS) {
    await tab(t); await settle(400); bad.push(...(await uncued()).map(x => `${t}: ${x}`));
    const cards = await page.$$eval(`.tabp[data-tab="${t}"] [data-card] .fwx`, b => b.map(x => x.dataset.fw));
    for (const c of cards) { await win(c); bad.push(...(await uncued()).map(x => `${c} window: ${x}`)); await closeWin() }
  }
  must(!bad.length, [...new Set(bad)].slice(0, 6).join(' | '));
});

/* ---------- MX2-6: a label with its control; a placeholder whole ---------- */
for (const w of [390, 360, 1440]) await step(`MX2-6 a label stays on its control's line; every search shows its whole placeholder (${w})`, async () => {
  await open(w); const bad = [];
  const look = where => page.evaluate(where => {
    const out = [];
    for (const g of document.querySelectorAll('.sgrp')) { const b = g.getBoundingClientRect(); if (!b.width) continue; const [l, c] = [...g.children].map(x => x.getBoundingClientRect()); if (l && c && Math.abs((l.top + l.bottom) / 2 - (c.top + c.bottom) / 2) > 4) out.push(`${where}: "${g.textContent.slice(0, 12)}" off its control`) }
    const cv = document.createElement('canvas').getContext('2d');
    for (const i of document.querySelectorAll('input[placeholder]')) { const b = i.getBoundingClientRect(); if (!b.width) continue; const cs = getComputedStyle(i); cv.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`; const need = cv.measureText(i.placeholder).width; if (need > i.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) + 0.5) out.push(`${where}: placeholder "${i.placeholder}" ${Math.round(need)} px in ${i.clientWidth}`) }
    return out;
  }, where);
  for (const t of TABS) {
    await tab(t); bad.push(...await look(t));
    const cards = await page.$$eval(`.tabp[data-tab="${t}"] [data-card] .fwx`, b => b.map(x => x.dataset.fw));
    for (const c of cards) { await win(c); bad.push(...await look(c + ' window')); await closeWin() }
  }
  must(!bad.length, [...new Set(bad)].slice(0, 6).join(' | '));
});

/* ---------- MX2-7: the sort arrows ---------- */
for (const theme of ['light', 'dark']) await step(`MX2-7 every sort arrow reads 4.5:1 on its background (${theme})`, async () => {
  await open(1440, theme); await page.evaluate(LIB); const bad = []; let n = 0;
  for (const t of TABS) {
    await tab(t);
    const r = await page.evaluate(() => [...document.querySelectorAll('.tabp:not([hidden]) .sk')].filter(e => e.getBoundingClientRect().width).map(e => +window.__ratio(window.__ink(e), window.__behind(e)).toFixed(2)));
    n += r.length; for (const x of r) if (x < 4.5) bad.push(`${t} ${x}:1`);
  }
  must(n > 3, `only ${n} arrows found`);
  must(!bad.length, bad.slice(0, 6).join(', '));
});

/* ---------- MX2-8: touch words ---------- */
await step('MX2-8 a touch screen reads "tap": no click, hover, point at or Ctrl on any tab or window (390)', async () => {
  await open(390, 'light', { touch: true }); const bad = [];
  const words = where => page.evaluate(where => {
    const out = [], re = /\b(click|clicks|hover|point at|Ctrl)\b/i;
    for (const e of document.querySelectorAll('body *')) {
      if (e.closest('[hidden]') || e.matches('script,style')) continue;
      const own = [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ');
      for (const [k, v] of [['text', own], ['title', e.getAttribute('title')], ['tip', e.getAttribute('data-tip')], ['aria', e.getAttribute('aria-label')]]) if (v && re.test(v)) out.push(`${where} ${k}: "${v.replace(/<[^>]+>/g, '').slice(0, 60)}"`);
    }
    return out;
  }, where);
  for (const t of TABS) {
    await tab(t); bad.push(...await words(t));
    const cards = await page.$$eval(`.tabp[data-tab="${t}"] [data-card] .fwx`, b => b.map(x => x.dataset.fw));
    for (const c of cards.slice(0, 3)) { await win(c); bad.push(...await words(c + ' window')); await closeWin() }
  }
  must(!bad.length, [...new Set(bad)].slice(0, 5).join(' | '));
});

/* ---------- MX2-9: the market map's group names ---------- */
for (const w of [360, 390, 1440]) await step(`MX2-9 the market map window: a group's name is whole where its group has room for its lines (${w})`, async () => {
  await open(w); await win('mkCard');
  const m = await page.evaluate(() => [...document.querySelectorAll('.fw .mk-g')].map(g => {
    const l = g.querySelector('.mk-gl'), gb = g.getBoundingClientRect(); if (!l || !l.textContent.trim()) return null;
    const cut = l.scrollWidth > l.clientWidth + 1 || l.scrollHeight > l.clientHeight + 1, lines = Math.round(l.clientHeight / 14), room = Math.min(3, Math.floor((gb.height * 0.45) / 14));
    return { t: l.textContent.trim().slice(0, 30), cut, lines, room };
  }).filter(Boolean));
  const bad = m.filter(x => x.cut && x.lines < x.room);
  must(m.length, 'no group label');
  must(!bad.length, bad.map(x => `"${x.t}" cut at ${x.lines} of ${x.room} lines`).join(' | '));
});

/* ---------- BD2-3: the Stock detail's tips ---------- */
await step('BD2-3 the Stock detail\'s row tips read as sentences, a status older than the data too (EMA200)', async () => {
  await open(1440); await tab('br');
  // the Stock detail follows the Breadth card's EMA (its "Above" switch)
  await page.locator('[data-card=brH] [data-seg=m] [data-v="200"]').click(); await settle(600);
  const tips = await page.$$eval('[data-card=brD] tbody tr[data-tip]', r => r.map(x => x.dataset.tip));
  must(tips.length, 'no row');
  const bad = tips.filter(t => /since The|since —|since\s*$/.test(t.replace(/<[^>]+>/g, ' ')));
  must(!bad.length, bad[0]);
  // 300+ sessions with no first session in the data (AYAM, MKAP, JRPT on 26 Nov): the sentence says the status is older
  const old = tips.filter(t => t.includes('300+') && !/, since /.test(t));
  for (const t of old) must(t.includes('began before the 300 sessions of data'), t);
  done.push(`     ${tips.length} tips, ${old.length} with a status older than the data`);
});

/* ---------- BD2-4: a heat cell's colour follows its text ---------- */
for (const theme of ['light', 'dark']) await step(`BD2-4 in every heat table, the same text has the same colour (${theme})`, async () => {
  await open(1440, theme); const bad = [];
  const look = where => page.evaluate(where => {
    // a column has its own scale (Sector × horizon: each horizon's cap): the same text in the same column
    const out = [], by = new Map();
    for (const c of document.querySelectorAll('.tabp:not([hidden]) :is(.ovx-hm .c, .rsw .c[data-tip], .pmg .c[data-a], .br-t td.hc[style]), .fw :is(.ovx-hm .c, .br-t td.hc[style])')) {
      const t = c.textContent.trim(), card = c.closest('[data-card]')?.dataset.card; if (!t || t === '—') continue;
      const k = card + '|' + Math.round(c.getBoundingClientRect().left) + '|' + t, bg = getComputedStyle(c).backgroundColor;
      if (by.has(k) && by.get(k) !== bg) out.push(`${where} ${card} "${t}": ${by.get(k)} and ${bg}`); else by.set(k, bg);
    }
    return out;
  }, where);
  for (const t of TABS) { await tab(t); bad.push(...await look(t)) }
  await tab('br'); await win('brT'); bad.push(...await look('brT window')); await closeWin();
  must(!bad.length, [...new Set(bad)].slice(0, 4).join(' | '));
});

/* ---------- BD2-1 / MX2-3: the ring of the slope rows and the map dots, painted ---------- */
for (const theme of ['light', 'dark']) await step(`BD2-1 MX2-3 a slope row and a rotation map dot show the grey ring by the keyboard (${theme})`, async () => {
  await open(1440, theme);
  for (const [t, sel] of [['rs', '[data-card=rsB] g.sl'], ['rot', '[data-card=rotA] g.pt']]) {
    await tab(t);
    const el = page.locator(sel).first(); await el.scrollIntoViewIfNeeded(); const b = await el.boundingBox();
    const clip = { x: b.x - 4, y: b.y - 4, width: b.width + 8, height: b.height + 8 }, before = await page.screenshot({ clip });
    await page.keyboard.press('Shift'); await el.evaluate(e => e.focus()); await settle(100);
    const s = await el.evaluate(e => { const c = getComputedStyle(e); return [c.outlineStyle, c.outlineWidth, c.outlineColor] });
    must(s[0] === 'solid' && s[1] === '2px', `${sel}: ${s.join(' ')}`);
    must(!before.equals(await page.screenshot({ clip })), `${sel}: no pixel of a ring`);
  }
});

await browser.close(); local?.srv.close();
console.log(done.join('\n'));
if (fails.length) { console.log('\n' + fails.join('\n')); process.exit(1) }
console.log(`\ncheck2: ${done.filter(d => d.startsWith('ok')).length} steps passed`);
