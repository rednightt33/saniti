/* QA round 4 fixes (user 2026-11-06: "1 dan 2, jalankan"): one check per round-4 finding, on the built page with the
   snapshot and the stand-in layouts API. Usage: node look_check7.mjs DATA OUT */
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { mkdir } from 'node:fs/promises';
import { serve } from './serve.mjs';
const { chromium, devices } = createRequire(import.meta.url)('playwright');

const [DATA, OUT] = process.argv.slice(2);
const { origin, close, layouts } = await serve(DATA, 'BBRI');
await mkdir(OUT, { recursive:true });
const browser = await chromium.launch();
const R = {}, errors = [];
const watch = p => { p.on('pageerror', e => errors.push(e.message)); p.on('console', m => { if (m.type() === 'error' && !/404|409|503|500/.test(m.text())) errors.push(m.text()) }) };
const ready = async p => { await p.waitForFunction(() => !document.querySelector('.ml-boot') && document.getElementById('layoutBtn'), null, { timeout:30_000 }); await p.waitForTimeout(1200) };
const seedOnce = (p, kv) => p.addInitScript(kv => { if (sessionStorage.getItem('seeded')) return; sessionStorage.setItem('seeded', '1'); for (const [k, v] of Object.entries(kv)) localStorage.setItem(k, v) }, kv);
const mk = (id, name, state = { 'ml.tf':'D' }) => { const now = new Date().toISOString(); layouts.rows.set(id, { layout_id:id, name, summary:'D · 0 indicators', schema_version:1, favorite:false, revision:1, created_at:now, updated_at:now, opened_at:now, state }) };
const D = { viewport:{ width:1440, height:900 } };
const A = 'lay_' + 'a'.repeat(32), B = 'lay_' + 'b'.repeat(32);
const openByDot = async (p, name, nav = true) => { await p.evaluate(() => document.body.focus()); await p.keyboard.press('.'); await p.waitForSelector('.lay-orow');
  await Promise.all([nav ? p.waitForNavigation({ timeout:30_000 }) : null, p.click(`.lay-orow:has-text("${name}")`)]) };   // opening a layout reloads the page
const puts = () => layouts.calls.filter(c => c.startsWith('PUT')).length;
try {
  // Q4-M1: a new (empty) layout is not "unsaved" once the page settles, and autosave writes nothing
  { const ctx = await browser.newContext(D), p = await ctx.newPage(); watch(p);
    await p.goto(`${origin}/terminal-app/`); await ready(p);
    await p.click('#layoutBtn'); await p.waitForTimeout(300); await p.click('.lay-menu [data-act="new"]'); await p.waitForSelector('.lay-dlg input'); await p.click('.lay-dlg [data-ok]');
    await ready(p); const n0 = puts(); await p.waitForTimeout(9500);
    R.m1 = { dirty:await p.evaluate(() => window.marketLabLayouts.dirty()), puts_after_settle:puts() - n0 };
    await ctx.close() }
  // Q4-M2: a change made while the opened layout restores itself is saved by Ctrl+S
  mk(A, 'Alpha'); mk(B, 'Beta', { 'ml.tf':'D', 'ml.chart.style':'line' });
  { const ctx = await browser.newContext(D), p = await ctx.newPage(); watch(p); await seedOnce(p, { 'ml.layout.autosave':'0' });
    await p.goto(`${origin}/terminal-app/`); await ready(p); await openByDot(p, 'Alpha');
    await p.waitForFunction(() => !document.querySelector('.ml-boot') && document.getElementById('layoutBtn'), null, { timeout:30000 });
    await p.click('#styleGroup [data-style="line"]'); await p.waitForTimeout(200);
    const n0 = puts(); await p.keyboard.press('Control+s'); await p.waitForTimeout(800);
    R.m2 = { puts:puts() - n0, style:layouts.rows.get(A).state['ml.chart.style'], toast:await p.$eval('.lay-toast', t => t.textContent) };
    await ctx.close() }
  // Q4-M3: Autosave on, the save fails, then Open layout asks instead of dropping the change
  { const ctx = await browser.newContext(D), p = await ctx.newPage(); watch(p);
    await p.goto(`${origin}/terminal-app/`); await ready(p); await openByDot(p, 'Alpha'); await ready(p); await p.waitForTimeout(9000);
    await p.route('**/api/v1/terminal/layouts/' + A, r => r.request().method() === 'PUT' ? r.fulfill({ status:500, body:'x' }) : r.continue());
    await p.click('#styleGroup [data-style="candle"]'); await p.waitForTimeout(2500);
    await openByDot(p, 'Beta', false); await p.waitForTimeout(800);   // a question, not a reload
    R.m3 = { confirm:await p.$eval('.lay-dlg p', e => e.textContent).catch(() => null) };
    await ctx.close() }
  // Q4-M4: two tabs of one browser: tab A no longer saves once tab B opened another layout
  { const ctx = await browser.newContext(D), a = await ctx.newPage(), b = await ctx.newPage(); watch(a); watch(b);
    await a.goto(`${origin}/terminal-app/`); await ready(a); await openByDot(a, 'Alpha'); await ready(a); await a.waitForTimeout(9000);
    await b.goto(`${origin}/terminal-app/`); await ready(b); await openByDot(b, 'Beta'); await ready(b); await b.waitForTimeout(1500);
    const before = JSON.stringify(layouts.rows.get(A).state), n0 = puts();
    await a.bringToFront(); await a.click('#styleGroup [data-style="line"]'); await a.waitForTimeout(2500);
    R.m4 = { alpha_unchanged:JSON.stringify(layouts.rows.get(A).state) === before, puts:puts() - n0, toast:await a.$eval('.lay-toast', t => t.textContent) };
    await ctx.close() }
  // Q4-L1: a first change sent on the way out (keepalive) reaches the server
  { const ctx = await browser.newContext(D), p = await ctx.newPage(); watch(p);
    await p.goto(`${origin}/terminal-app/`); await ready(p); await openByDot(p, 'Alpha'); await ready(p); await p.waitForTimeout(9000);
    const n0 = puts(); await p.click('#modeGroup [data-mode="return"]'); await p.waitForTimeout(200); await p.goto('about:blank'); await new Promise(r => setTimeout(r, 1000));
    R.l1 = { puts_on_leave:puts() - n0, mode:layouts.rows.get(A).state['ml.chart.mode'] };
    await ctx.close() }
  // Q4-L3: "Loading…" while a slow list is read
  { const ctx = await browser.newContext(D), p = await ctx.newPage(); watch(p);
    await p.goto(`${origin}/terminal-app/`); await ready(p);
    await p.route('**/api/v1/terminal/layouts', async r => { await new Promise(x => setTimeout(x, 1500)); r.continue() });
    await p.click('#layoutBtn'); await p.waitForTimeout(300); R.l3 = await p.$eval('.lay-menu .lay-msg', e => e.textContent).catch(() => null);
    await ctx.close() }
  // collapse M1: folding two of five panes gives the price pane more room, never less
  { const ctx = await browser.newContext(D), p = await ctx.newPage(); watch(p);
    await seedOnce(p, { 'ml.ind.v1':JSON.stringify(['FL12', 'FL23', 'FL21', 'FL11', 'FL24'].map(d => ({ def:d, params:{} }))) });
    await p.goto(`${origin}/terminal-app/`); await ready(p); await p.waitForTimeout(1200);
    const price = () => p.evaluate(() => { const c = document.querySelector('#chart canvas'); const t = [...document.querySelectorAll('#chart table tr')]; return t.length ? Math.round(t[0].getBoundingClientRect().height) : 0 });
    const h0 = await price();
    for (const d of ['FL21', 'FL11']) await p.evaluate(d => document.querySelector(`.ind-fold[data-def="${d}"]`).click(), d);
    await p.waitForTimeout(800); const h2 = await price();
    R.c_m1 = { price_open:h0, price_two_folded:h2 };
    // L1: pointing at a folded pane row does not grow it
    const hb = await p.$eval('.ind-row[data-def="FL21"]', r => Math.round(r.getBoundingClientRect().height));
    await p.hover('.ind-row[data-def="FL21"] .ind-k'); await p.waitForTimeout(300);
    R.c_l1 = { before:hb, hover:await p.$eval('.ind-row[data-def="FL21"]', r => Math.round(r.getBoundingClientRect().height)) };
    await ctx.close() }
  // collapse M2 and panel M3/L3: 1280 px with both side panels open
  { const ctx = await browser.newContext({ viewport:{ width:1280, height:800 } }), p = await ctx.newPage(); watch(p);
    await seedOnce(p, { 'ml.broker.collapsed':'0', 'ml.stats.collapsed':'0', 'ml.ind.v1':JSON.stringify(['FL12', 'FL23', 'FL21'].map(d => ({ def:d, params:{}, fold:true }))) });
    await p.goto(`${origin}/terminal-app/`); await ready(p); await p.waitForTimeout(1500);
    R.c_m2 = await p.$$eval('.ind-row.in-pane', rs => rs.map(r => Math.round(r.getBoundingClientRect().height)));
    R.c_m3 = await p.$$eval('#brokerPanel .st-head > span:first-child', ss => ss.filter(s => s.offsetWidth).map(s => [s.textContent, s.scrollWidth > s.clientWidth]));
    R.c_l3_plus0 = await p.$$eval('#accBody .nv', ns => ns.map(n => n.textContent).filter(t => t === '+0').length);
    await p.selectOption('#fdBoard', 'Nego'); await p.waitForTimeout(400);
    R.c_l3_labels = await p.$$eval('.fdm-svg text.fdm-p', ts => ts.map(t => t.textContent + '@' + t.getAttribute('y')));
    await p.click('.ind-row[data-def="FL12"] .ind-fltbtn'); await p.waitForTimeout(300);
    R.c_l2 = await p.$eval('.ind-row[data-def="FL12"] .ind-fltnote', e => e.textContent);
    await p.screenshot({ path:join(OUT, 'w1280_both.png') });
    await ctx.close() }
  // L4: failed broker files: the empty Flow Timeline shows no invented scale
  { const ctx = await browser.newContext(D), p = await ctx.newPage(); watch(p);
    await p.route('**/bucket/broker/**', r => r.fulfill({ status:500, body:'x' }));
    await p.goto(`${origin}/terminal-app/`); await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(4000);
    await p.screenshot({ path:join(OUT, 'flow_failed.png'), clip:await p.locator('#flowChart').boundingBox() });
    await ctx.close() }
} catch (e) { errors.push('harness: ' + e.message.split('\n')[0]) }
R.errors = errors;
console.log(JSON.stringify(R, null, 1));
await browser.close(); close();
