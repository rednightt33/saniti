/* The browser check of the EDGE round of 2026-11-27 (EXEC.md EXEC-DESIGN-SYSTEM; the design system's canonical layer,
   decisions 12-14; the user's "1a" + "1A", "4A", "3A" and "tambah satu aturan tampilan saja"), on every EDGE page but the
   Terminal (the user's "Terminal jangan disentuh"): the Overview, Watchlist, Radar, Sector Analysis, Screener, Backtest and
   Admin pages on their fixture builds (made-up files; the Overview and the Radar have no committed fixture data, so they
   show their error box and are checked on its controls), and the shell (static/index.html on a server that answers no
   API, so it draws its sign-in page). No beta, no login, no network but this machine.

   Per page, light and dark:
   - focus (UD75): a button clicked with the mouse shows no ring, nor a <select> opened with the mouse; a button given the
     focus by script after a mouse action (a window closed with the mouse) shows none; Tab shows a ring on the controls
     it reaches, every one of them neutral grey (the page's --text-3), none blue; a field reached by Tab shows no outline.
     On the Sector page the real case: a card's expand button, its window closed with the mouse (no ring on the button
     the focus returns to) and with Esc (the grey ring);
   - contrast (UD73): --text-3 on --surface, --bg, --surface-2, --hover and --sel, and the four tag pairs (the tag ink on
     its tint, over --surface, --bg and --surface-2), from the rendered colours, at least 4.5:1; every element the page
     draws with one of the four tints behind its own text, at least 4.5:1 too;
   - touch (UD72), at 390 x 844 with a touch screen (hasTouch, isMobile): the media feature pointer switched between fine
     and coarse (DevTools emulation) moves no element by more than 0.5 px; each small shared control (.seg button, .tog,
     .iconbtn, .btn.sm, .btn.xs, button.pill, .switch, .hit) in view is at least 44 px high and wide to a tap, or reaches
     the cap its row sets (--hit-x / --hit-y: halfway to its neighbour), measured with elementFromPoint; and no control's
     own centre is taken by another control's enlarged area;
   - names (UD71): a made-up name rewritten "Pt …" in the served fixture script shows as "PT …" and never as "Pt …".

   Usage: build each page's fixture (npm run build:fixture in apps/edge-bff/<page>), then
          node verification/edge_states/round2_focus_contrast.mjs        (CHECK_ONLY=<regex> runs the steps whose name matches;
          CHECK_PAGES=a,b checks those pages only; CHECK_EDGE=<dir> checks another copy of apps/edge-bff, e.g. an older one)
   Uses the preinstalled Playwright (PLAYWRIGHT_MODULE_DIR, else /opt/node-tools/node_modules). */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { existsSync, readFileSync } from 'node:fs';
import { extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = fileURLToPath(new URL('.', import.meta.url)), EDGE = process.env.CHECK_EDGE || join(here, '..', '..', 'apps', 'edge-bff');
const playwright = (() => {
  for (const f of [process.env.PLAYWRIGHT_MODULE_DIR, '/opt/node-tools/node_modules'].filter(Boolean)) {
    try { return createRequire(join(f, 'noop.js'))('playwright') } catch { /* next */ }
  }
  throw new Error('round2: playwright not found (set PLAYWRIGHT_MODULE_DIR)');
})();
const PAGES = (process.env.CHECK_PAGES || 'overview,watchlist,radar,sector,screener,backtest,admin').split(',');
/* made-up names of the fixtures, served as the source would write the three real ones ("Pt …"):
   [text in the fixture script, its replacement, the name as served, the name the page must show] */
const NAMES = {
  watchlist: ['"PT Gala Ritel Digital Tbk"', '"Pt Gala Ritel Digital Tbk"', 'Pt Gala Ritel Digital Tbk', 'PT Gala Ritel Digital Tbk'],
  sector: ['PT Contoh ', 'Pt Contoh ', 'Pt Contoh ', 'PT Contoh '],
  screener: ['|Bank Central Asia|', '|Pt Bank Central Asia|', 'Pt Bank Central Asia', 'PT Bank Central Asia'],
  backtest: ['name:null,type:"stock"', 'name:"Pt Contoh Tbk",type:"stock"', 'Pt Contoh Tbk', 'PT Contoh Tbk'],
};
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.png': 'image/png', '.json': 'application/json' };
for (const p of PAGES) if (!existsSync(join(EDGE, p, 'dist-fixture', 'index.html'))) throw new Error(`round2: run npm run build:fixture in apps/edge-bff/${p} first`);
const srv = await new Promise(ok => { const s = createServer((req, res) => {
  const p = decodeURIComponent(new URL(req.url, 'http://x').pathname), send = (c, t, b) => { res.writeHead(c, { 'content-type': t }); res.end(b) };
  if (p.startsWith('/fonts/')) { const f = join(EDGE, 'static', 'fonts', p.slice(7)); return existsSync(f) ? send(200, TYPES[extname(f)] || 'text/css', readFileSync(f)) : send(404, 'text/plain', '') }
  if (p.startsWith('/api/')) return send(404, 'application/json', '{}');
  const m = p.match(/^\/(\w+)-app\/(.*)$/);
  if (m && PAGES.includes(m[1])) {
    const dist = join(EDGE, m[1], 'dist-fixture'); let f = join(dist, m[2] || 'index.html');
    if (!existsSync(f) || f.endsWith('/')) f = join(dist, 'index.html');
    let body = readFileSync(f);
    const n = NAMES[m[1]];
    if (n && f.endsWith('.js')) body = Buffer.from(body.toString('utf8').split(n[0]).join(n[1]));
    return send(200, TYPES[extname(f)] || 'application/octet-stream', body);
  }
  // the shell: its static files, and index.html for a page path
  const f = join(EDGE, 'static', p.slice(1));
  if (p !== '/' && existsSync(f) && !f.endsWith('/')) return send(200, TYPES[extname(f)] || 'application/octet-stream', readFileSync(f));
  send(200, 'text/html', readFileSync(join(EDGE, 'static', 'index.html')));
}).listen(0, () => ok(s)) });
const BASE = `http://localhost:${srv.address().port}`;
const ONLY = process.env.CHECK_ONLY ? new RegExp(process.env.CHECK_ONLY) : null;
const browser = await playwright.chromium.launch();
const fails = [], done = [];
const must = (ok, msg) => { if (!ok) throw new Error(msg) };
let errs = [];
const step = async (name, fn) => {
  if (ONLY && !ONLY.test(name)) return;
  try { await fn(); if (errs.length) throw new Error('console: ' + errs.slice(0, 3).join(' | ')); done.push(`ok   ${name}`) } catch (e) { fails.push(`${name}: ${e.message.split('\n')[0]}`); done.push(`FAIL ${name}`) }
};
const url = app => (app === 'shell' ? `${BASE}/monitor` : `${BASE}/${app}-app/`);
async function open(app, theme, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1384, height: 900 }, deviceScaleFactor: 1, ...opts });
  await ctx.addInitScript(t => { try { localStorage.setItem('edge-auth-monitor-theme', t) } catch { /* off */ } }, theme);
  const page = await ctx.newPage(); errs = [];
  page.on('pageerror', e => errs.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource|404/.test(m.text())) errs.push(m.text()) });
  await page.goto(url(app) + (theme === 'dark' && app !== 'shell' ? '?theme=dark' : ''), { waitUntil: 'load' });
  await page.waitForTimeout(app === 'shell' ? 1500 : 2200);
  await page.evaluate(() => document.fonts.ready);
  if (app === 'shell' && theme === 'dark') await page.evaluate(() => document.documentElement.classList.add('dark'));
  return { ctx, page };
}

/* ---------- the page side: colours, rings, contrast ---------- */
const LIB = () => {
  const W = window;
  W.__rgba = s => { const m = String(s).match(/rgba?\(([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:[ ,/]+([\d.]+%?))?\)/); if (!m) return null; let a = m[4] === undefined ? 1 : m[4].endsWith('%') ? parseFloat(m[4]) / 100 : +m[4]; return [+m[1], +m[2], +m[3], a] };
  W.__lum = c => { const f = v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]) };
  W.__ratio = (a, b) => { const x = W.__lum(a), y = W.__lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) };
  W.__over = (top, base) => [0, 1, 2].map(i => top[3] * top[i] + (1 - top[3]) * base[i]);
  // the colour a CSS value renders as, through a probe element
  W.__color = (v, prop = 'color') => { const s = document.createElement('span'); s.style[prop] = v; document.body.appendChild(s); const c = getComputedStyle(s)[prop]; s.remove(); return W.__rgba(c) };
  // the opaque colour behind an element (its own background and its ancestors', composited)
  W.__behind = el => { const layers = []; for (let e = el; e; e = e.parentElement) { const c = W.__rgba(getComputedStyle(e).backgroundColor); if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break } }
    let base = [255, 255, 255]; const root = W.__rgba(getComputedStyle(document.body).backgroundColor); if (root && root[3] >= 1) base = root.slice(0, 3);
    for (let i = layers.length - 1; i >= 0; i--) base = W.__over(layers[i], base); return base };
  // the ring an element draws now: its outline, or a box-shadow with no blur and a spread of 2 px or more (a ring; the
  // selected segment's 1 px raise of decision 3 is not one), when visible
  W.__ring = el => { const cs = getComputedStyle(el); const o = cs.outlineStyle !== 'none' && parseFloat(cs.outlineWidth) > 0 ? W.__rgba(cs.outlineColor) : null;
    if (o && o[3] > 0) return { kind: 'outline', c: o, w: cs.outlineWidth };
    const sh = cs.boxShadow === 'none' ? [] : cs.boxShadow.split(/,(?![^(]*\))/);
    for (const s of sh) { const c = W.__rgba(s), nums = s.replace(/rgba?\([^)]*\)/, '').trim().split(/\s+/).filter(x => x !== 'inset').map(parseFloat);
      if (c && c[3] > 0 && nums.length >= 4 && nums[2] === 0 && nums[3] >= 2) return { kind: 'shadow', c, w: nums[3] + 'px' } }
    return null };
  W.__isField = el => el.matches('input:not([type=checkbox],[type=radio],[type=range],[type=color],[type=file],[type=button],[type=submit],[type=reset],[type=image]),select,textarea');
  W.__name = el => el ? el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.classList.length ? '.' + [...el.classList].slice(0, 3).join('.') : '') : 'null';
  W.__grey = c => Math.max(Math.abs(c[0] - c[1]), Math.abs(c[1] - c[2]), Math.abs(c[0] - c[2])) <= 3;
};
const grey = page => page.evaluate(() => { const app = document.createElement('div'); app.className = 'app'; document.body.appendChild(app);
  const s = document.createElement('span'); s.style.color = 'var(--text-3)'; (document.querySelector('#root .app') || (document.querySelector('.auth-page') ? app : document.body)).appendChild(s);
  const c = window.__rgba(getComputedStyle(s).color); s.remove(); app.remove(); return c });
const ringNow = page => page.evaluate(() => { const el = document.activeElement; return { el: window.__name(el), ring: el && el !== document.body ? window.__ring(el) : null, field: el ? window.__isField(el) : false } });
const visibleButtons = (page, sel) => page.$$eval(sel, (els) => els.map((e, i) => { const b = e.getBoundingClientRect(); const cs = getComputedStyle(e);
  return b.width > 4 && b.height > 4 && b.top >= 0 && b.left >= 0 && b.bottom <= innerHeight && b.right <= innerWidth && cs.visibility !== 'hidden' && !e.disabled && !e.closest('[aria-hidden=true]') ? i : -1 }).filter(i => i >= 0));

async function pickButton(page) {
  for (const sel of ['.seg button:not(.on):not([aria-pressed=true])', '[role=tab]:not([aria-selected=true])', '.tabs button', '.seg button', 'button.btn', 'button']) {
    const ok = await visibleButtons(page, sel);
    if (ok.length) return (await page.$$(sel))[ok[0]];
  }
  return null;
}
async function clickAt(page, el) { const b = await el.boundingBox(); await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2) }

for (const app of [...PAGES, 'shell']) for (const theme of ['light', 'dark']) {
  await step(`${app} ${theme}: focus by mouse shows no ring, by Tab the grey ring`, async () => {
    const { ctx, page } = await open(app, theme);
    try {
      await page.evaluate(LIB);
      const g = await grey(page);
      // a button clicked with the mouse
      const b = await pickButton(page);
      must(b, 'no visible button to click');
      await clickAt(page, b);
      await page.waitForTimeout(150);
      if (!(await page.evaluate(e => document.activeElement === e, b))) await b.evaluate(e => e.focus());
      let r = await ringNow(page);
      must(await page.evaluate(() => document.documentElement.dataset.modality === 'pointer'), 'data-modality is not "pointer" after a click');
      must(!r.ring, `clicked ${r.el} draws a ring ${JSON.stringify(r.ring)}`);
      // focus given back by script after a mouse action (the window's own button gone first): no ring
      const b2 = await pickButton(page);
      await b2.evaluate(e => { document.activeElement?.blur(); e.focus() });
      r = await ringNow(page);
      must(!r.ring, `${r.el} focused by script after a click draws a ring ${JSON.stringify(r.ring)}`);
      // a select opened with the mouse, then Esc: no outline either way (decision 8's state)
      const sel = (await visibleButtons(page, 'select')).length ? (await page.$$('select'))[(await visibleButtons(page, 'select'))[0]] : null;
      if (sel) {
        await clickAt(page, sel); await page.waitForTimeout(100);
        r = await ringNow(page);
        must(r.field && !(r.ring && r.ring.kind === 'outline'), `select clicked: ${JSON.stringify(r)}`);
        await page.keyboard.press('Escape');
        r = await ringNow(page);
        must(!(r.ring && r.ring.kind === 'outline'), `select after Esc: ${JSON.stringify(r)}`);
      }
      // the same button focused by script after a key press: the grey ring (the self-test: the check sees a ring)
      await page.keyboard.press('Shift');
      const b3 = await pickButton(page);
      await b3.evaluate(e => { document.activeElement?.blur(); e.focus() });
      r = await ringNow(page);
      must(r.ring && r.ring.c.slice(0, 3).every((v, k) => Math.abs(v - g[k]) <= 2), `${r.el} focused by script after a key press: ring ${JSON.stringify(r.ring)}, not the grey ${g}`);
      // Tab: every control it reaches that draws a ring draws the grey one; at least one does; no field an outline
      await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0) });
      const seen = [];
      for (let i = 0; i < 24; i++) {
        await page.keyboard.press('Tab');
        const t = await ringNow(page);
        if (t.el === 'body' || t.el === 'null') continue;
        seen.push(t);
      }
      const rings = seen.filter(t => t.ring && !t.field);
      must(rings.length, `Tab reached ${seen.length} controls, none with a ring: ${seen.slice(0, 4).map(t => t.el).join(', ')}`);
      for (const t of rings) must(t.ring.c.slice(0, 3).every((v, k) => Math.abs(v - g[k]) <= 2), `${t.el}: ring ${t.ring.c} is not the grey ${g}`);
      for (const t of seen.filter(t => t.field)) must(!(t.ring && t.ring.kind === 'outline'), `field ${t.el} takes an outline`);
      done.push(`     ${app} ${theme}: Tab reached ${seen.length}, ${rings.length} grey rings (${[...new Set(rings.map(t => t.ring.w))].join('/')}), select: ${sel ? 'yes' : 'none'}`);
    } finally { await ctx.close() }
  });

  await step(`${app} ${theme}: --text-3 and the tag pairs read 4.5:1`, async () => {
    const { ctx, page } = await open(app, theme);
    try {
      await page.evaluate(LIB);
      const out = await page.evaluate((app) => {
        const W = window, C = v => W.__color(v, 'backgroundColor'), T = v => W.__color(v);
        let root = document.documentElement;
        if (app === 'shell') { root = document.createElement('div'); root.className = 'app'; document.body.appendChild(root) }   // the shell's tokens sit on .app
        const probe = (prop, v) => { const s = document.createElement('span'); s.style[prop] = v; root.appendChild(s); const c = W.__rgba(getComputedStyle(s)[prop]); s.remove(); return c };
        const surf = {}; for (const k of ['surface', 'bg', 'surface-2', 'hover', 'sel']) surf[k] = probe('backgroundColor', `var(--${k})`);
        const t3 = probe('color', 'var(--text-3)'), res = { t3: t3.slice(0, 3).join(','), text3: {}, tags: {}, page: [] };
        for (const [k, c] of Object.entries(surf)) if (c) res.text3[k] = +W.__ratio(t3, c[3] < 1 ? W.__over(c, [255, 255, 255]) : c).toFixed(2);
        if (app !== 'shell') for (const h of ['green', 'red', 'blue', 'amber']) {
          const ink = probe('color', `var(--${h}-tag)`), tint = probe('backgroundColor', `var(--${h}-bg)`);
          if (!ink || !tint) { res.tags[h] = 'missing'; continue }
          res.tags[h] = Object.fromEntries(['surface', 'bg', 'surface-2'].map(k => [k, +W.__ratio(ink, W.__over(tint, surf[k])).toFixed(2)]));
        }
        // every element drawn with one of the four tints behind its own text
        const tints = ['green', 'red', 'blue', 'amber'].map(h => probe('backgroundColor', `var(--${h}-bg)`)).filter(Boolean).map(c => c.join(','));
        for (const el of document.querySelectorAll('body *')) {
          const cs = getComputedStyle(el), bg = W.__rgba(cs.backgroundColor);
          if (!bg || !tints.includes(bg.join(','))) continue;
          const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
          const b = el.getBoundingClientRect(); if (!own || !b.width || cs.visibility === 'hidden') continue;
          res.page.push({ el: W.__name(el), r: +W.__ratio(W.__rgba(cs.color), W.__behind(el)).toFixed(2) });
        }
        return res;
      }, app);
      for (const [k, r] of Object.entries(out.text3)) must(r >= 4.5, `--text-3 (${out.t3}) on --${k}: ${r}:1`);
      for (const [h, v] of Object.entries(out.tags)) { must(v !== 'missing', `--${h}-tag or --${h}-bg missing`); for (const [k, r] of Object.entries(v)) must(r >= 4.5, `${h} tag on --${k}: ${r}:1`) }
      for (const x of out.page) must(x.r >= 4.5, `${x.el}: its text on its tint reads ${x.r}:1`);
      done.push(`     ${app} ${theme}: --text-3 rgb(${out.t3}) ${Object.entries(out.text3).map(([k, r]) => `${k} ${r}`).join(', ')}; tags ${Object.entries(out.tags).map(([h, v]) => `${h} ${Math.min(...Object.values(v))}`).join(', ')}; ${out.page.length} tinted elements on the page`);
    } finally { await ctx.close() }
  });
}

/* ---------- the real case: the Sector page's window, closed with the mouse and with Esc ---------- */
for (const theme of ['light', 'dark']) await step(`sector ${theme}: the expand button after its window closes`, async () => {
  const { ctx, page } = await open('sector', theme);
  try {
    await page.evaluate(LIB);
    const g = await grey(page);
    const fwx = (await page.$$('.fwx'))[(await visibleButtons(page, '.fwx'))[0]];
    must(fwx, 'no expand button in view');
    await clickAt(page, fwx); await page.waitForSelector('.fw .fw-x', { timeout: 5000 });
    await clickAt(page, await page.$('.fw .fw-x')); await page.waitForTimeout(200);
    let r = await ringNow(page);
    must(r.el.includes('fwx'), `the focus went to ${r.el}, not back to the expand button`);
    must(!r.ring, `the expand button draws a ring after the window closed with the mouse: ${JSON.stringify(r.ring)}`);
    // with the keyboard: Enter opens, Esc closes, the ring shows (grey)
    await fwx.evaluate(e => e.focus()); await page.keyboard.press('Enter'); await page.waitForSelector('.fw .fw-x', { timeout: 5000 });
    await page.keyboard.press('Escape'); await page.waitForTimeout(200);
    r = await ringNow(page);
    must(r.el.includes('fwx') && r.ring && r.ring.c.slice(0, 3).every((v, k) => Math.abs(v - g[k]) <= 2), `after Esc: ${JSON.stringify(r)} (grey ${g})`);
  } finally { await ctx.close() }
});

/* ---------- touch hit areas ---------- */
const SMALL = '.seg button, .tog, .iconbtn, .btn.sm, .btn.xs, button.pill, .switch, .hit';
for (const app of [...PAGES, 'shell']) await step(`${app}: touch hit areas, no layout change`, async () => {
  const { ctx, page } = await open(app, 'light', { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  try {
    const cdp = await ctx.newCDPSession(page);
    const media = async v => { await cdp.send('Emulation.setEmulatedMedia', { features: [{ name: 'pointer', value: v }, { name: 'any-pointer', value: v }] }); await page.waitForTimeout(250) };
    const rects = () => page.evaluate(() => [...document.querySelectorAll('body *')].map(e => { const b = e.getBoundingClientRect(); return [b.x, b.y, b.width, b.height].map(v => Math.round(v * 2) / 2) }));
    await media('fine'); const fine = await rects();
    await media('coarse'); const coarse = await rects();
    must(fine.length === coarse.length, `the element count changed: ${fine.length} → ${coarse.length}`);
    let moved = 0; fine.forEach((r, i) => { if (r.some((v, k) => Math.abs(v - coarse[i][k]) > 0.5)) moved++ });
    must(!moved, `${moved} elements moved or resized between pointer fine and coarse`);
    // the page's main scroller (the window or the page's own box), read at up to 8 positions down the page
    const scrollTo = k => page.evaluate(k => { const all = [document.scrollingElement, ...document.querySelectorAll('*')].filter(e => e && e.scrollHeight - e.clientHeight > 40 && (e === document.scrollingElement || /auto|scroll/.test(getComputedStyle(e).overflowY)));
      const s = all.sort((a, b) => (b.clientHeight * b.clientWidth) - (a.clientHeight * a.clientWidth))[0]; if (!s) return k === 0;
      const top = Math.round(k * s.clientHeight * 0.8); if (k && top >= s.scrollHeight - s.clientHeight + s.clientHeight * 0.8) return false; s.scrollTop = top; return true }, k);
    const res = { small: [], short: [], stolen: [], clipped: [] };
    for (let k = 0; k < 8 && await scrollTo(k); k++) {
    await page.waitForTimeout(120);
    const part = await page.evaluate((SMALL) => {
      const own = (el, x, y) => { const h = document.elementFromPoint(x, y); return !!h && (h === el || el.contains(h)) };
      const who = (x, y) => { const h = document.elementFromPoint(x, y); return h ? `${h.tagName.toLowerCase()}.${[...h.classList].slice(0, 2).join('.')}` : 'none' };
      const span = (el, axis) => { const b = el.getBoundingClientRect(), cx = b.x + b.width / 2, cy = b.y + b.height / 2; let lo = 0, hi = 0;
        if (axis === 'y') { while (lo < 40 && own(el, cx, b.y - lo - 1)) lo++; while (hi < 40 && own(el, cx, b.bottom + hi)) hi++; return [b.height + lo + hi, `above ${who(cx, b.y - lo - 1)}, below ${who(cx, b.bottom + hi)}`] }
        while (lo < 40 && own(el, b.x - lo - 1, cy)) lo++; while (hi < 40 && own(el, b.right + hi, cy)) hi++; return [b.width + lo + hi, `left ${who(b.x - lo - 1, cy)}, right ${who(b.right + hi, cy)}`] };
      const out = { small: [], short: [], stolen: [], clipped: [] };
      const inView = b => b.width > 0 && b.height > 0 && b.top >= 0 && b.left >= 0 && b.bottom <= innerHeight && b.right <= innerWidth;
      for (const el of document.querySelectorAll(SMALL)) {
        const b = el.getBoundingClientRect(), cs = getComputedStyle(el); if (!inView(b) || cs.visibility === 'hidden' || !own(el, b.x + b.width / 2, b.y + b.height / 2)) continue;
        const capX = parseFloat(cs.getPropertyValue('--hit-x')), capY = parseFloat(cs.getPropertyValue('--hit-y'));
        let needW = Math.min(44, b.width + 2 * (isNaN(capX) ? 22 : capX)), needH = Math.min(44, b.height + 2 * (isNaN(capY) ? 22 : capY));
        // the box a tap needs, inside the view (the page scrolls a control near an edge into it first)
        if (b.top - (needH - b.height) / 2 < 0 || b.bottom + (needH - b.height) / 2 > innerHeight || b.left - (needW - b.width) / 2 < 0 || b.right + (needW - b.width) / 2 > innerWidth) continue;
        // an ancestor that scrolls (or clips) its content cuts the area at its edge: the control's own scroller, never
        // a neighbour; such a control is listed apart, its size there the most its scroller allows
        let clip = null;
        for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
          const s = getComputedStyle(a); if (s.overflowX === 'visible' && s.overflowY === 'visible') continue;
          const r = a.getBoundingClientRect(), top = r.top + a.clientTop, left = r.left + a.clientLeft;
          const h0 = Math.min(b.bottom + (needH - b.height) / 2, top + a.clientHeight) - Math.max(b.top - (needH - b.height) / 2, top);
          const w0 = Math.min(b.right + (needW - b.width) / 2, left + a.clientWidth) - Math.max(b.left - (needW - b.width) / 2, left);
          if (h0 < needH - 0.5 || w0 < needW - 0.5) { clip = `${a.tagName.toLowerCase()}.${[...a.classList].slice(0, 2).join('.')}`; needH = Math.min(needH, h0); needW = Math.min(needW, w0) }
        }
        if (clip) out.clipped.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} ${Math.round(b.width)}x${Math.round(b.height)} in ${clip}: ${Math.round(needW)}x${Math.round(needH)}`);
        const [w, wBy] = span(el, 'x'), [h, hBy] = span(el, 'y');
        out.small.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} ${Math.round(b.width)}x${Math.round(b.height)} → ${Math.round(w)}x${Math.round(h)}`);
        // the area may stop short where another element lies over it (a neighbour, a sticky head, the frame's edge)
        if (w < needW - 1.5 || h < needH - 1.5) out.short.push({ el: `${el.tagName.toLowerCase()}.${[...el.classList].join('.')}`, size: `${Math.round(b.width)}x${Math.round(b.height)}`, hit: `${Math.round(w)}x${Math.round(h)}`, need: `${Math.round(needW)}x${Math.round(needH)}`, by: h < needH - 1.5 ? hBy : wBy });
      }
      for (const el of document.querySelectorAll('button, a[href], input, select, textarea, [role=button], [role=tab], [tabindex]:not([tabindex="-1"])')) {
        const b = el.getBoundingClientRect(); if (!inView(b) || getComputedStyle(el).visibility === 'hidden') continue;
        const h = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2);
        if (h && h !== el && !el.contains(h) && !h.contains(el) && h.closest(SMALL) && h.closest(SMALL) !== el.closest(SMALL)) out.stolen.push(`${el.tagName.toLowerCase()}.${[...el.classList].slice(0, 2).join('.')} ← ${h.tagName.toLowerCase()}.${[...h.classList].slice(0, 2).join('.')}`);
      }
      return out;
    }, SMALL);
    for (const key of Object.keys(res)) res[key].push(...part[key]);
    }
    for (const key of ['small', 'clipped', 'stolen']) res[key] = [...new Set(res[key])];
    res.short = [...new Map(res.short.map(x => [JSON.stringify(x), x])).values()];
    await scrollTo(0);
    // a stolen centre is the enlarged area's fault only when it is not stolen at pointer fine too
    await media('fine');
    const fineStolen = await page.evaluate((SMALL) => [...document.querySelectorAll('button, a[href], input, select, textarea, [role=button], [role=tab]')].filter(el => { const b = el.getBoundingClientRect(); if (!b.width) return false; const h = document.elementFromPoint(b.x + b.width / 2, b.y + b.height / 2); return h && h !== el && !el.contains(h) && !h.contains(el) && h.closest(SMALL) }).length, SMALL);
    must(!res.stolen.length || fineStolen >= res.stolen.length, `a control's centre is taken by an enlarged area: ${res.stolen.slice(0, 4).join('; ')}`);
    must(!res.short.length, `below 44 px to a tap: ${res.short.slice(0, 4).map(x => `${x.el} ${x.size} hit ${x.hit} (need ${x.need}; stopped by ${x.by})`).join('; ')}`);
    done.push(`     ${app}: ${res.small.length} kinds of small control down the page${res.small.length ? ': ' + [...new Set(res.small)].slice(0, 6).join('; ') : ''}${res.clipped.length ? `; cut by their own scroller: ${[...new Set(res.clipped)].slice(0, 3).join('; ')}` : ''}`);
  } finally { await ctx.close() }
});

/* ---------- company names ---------- */
for (const [app, [, , raw, shown]] of Object.entries(NAMES).filter(([a]) => PAGES.includes(a))) await step(`${app}: a name the source writes "Pt …" shows "PT …"`, async () => {
  const { ctx, page } = await open(app, 'light');
  try {
    // where the page shows names: the Sector page's Breadth tab (its stock table's rows), the Backtest's portfolio picker
    if (app === 'sector') { await page.click('#tabs [data-t="br"]'); await page.waitForTimeout(1500) }
    if (app === 'backtest') { await page.click('#btab1'); await page.waitForTimeout(300); await page.click('#modeSeg [data-m="portfolio"]'); await page.waitForTimeout(800) }
    const html = await page.evaluate(() => document.body.innerHTML);
    must(html.includes(shown), `"${shown}" is not on the page`);
    must(!html.includes(raw), `the source's "${raw.trim()}" is on the page`);
    done.push(`     ${app}: "${raw.trim()}" served, "${shown.trim()}" shown ${html.split(shown).length - 1} times, "${raw.trim()}" none`);
  } finally { await ctx.close() }
});

await browser.close(); srv.close();
console.log(done.join('\n'));
console.log(fails.length ? `\n${fails.length} FAILED:\n${fails.join('\n')}` : `\nall ${done.filter(d => d.startsWith('ok')).length} steps passed`);
process.exit(fails.length ? 1 : 0);
