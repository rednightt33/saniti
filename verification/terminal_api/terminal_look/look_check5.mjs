/* EXEC-TERMINAL-LAYOUTS (user 2026-11-06): chart layouts saved on the EDGE account (stand-in API in serve.mjs) and the
   lower-pane collapse, on the built page with the snapshot. Usage: node look_check5.mjs DATA OUT */
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
const watch = p => { p.on('pageerror', e => errors.push(e.message)); p.on('console', m => { if (m.type() === 'error' && !/404|409/.test(m.text())) errors.push(m.text()) }) };
const ready = async p => { await p.waitForFunction(() => !document.querySelector('.ml-boot') && document.getElementById('layoutBtn'), null, { timeout:30_000 }); await p.waitForTimeout(1200) };
const addInd = async (p, q, id) => { await p.click('#indBtn'); await p.fill('#imSearch', q); await p.click(`.im-row[data-id="${id}"] .im-add`); await p.keyboard.press('Escape'); await p.waitForTimeout(900) };
const inds = p => p.evaluate(() => JSON.parse(localStorage.getItem('ml.ind.v1') || '[]').map(o => o.def + (o.fold ? ':fold' : '')));
const btnText = p => p.$eval('#layoutBtn', b => b.textContent.trim() + (b.querySelector('.lay-dirty') ? ' •' : ''));
const menu = async p => { await p.click('#layoutBtn'); await p.waitForTimeout(350) };
const nameDlg = async (p, name) => { await p.waitForSelector('.lay-dlg input'); await p.fill('.lay-dlg input', name); await p.click('.lay-dlg [data-ok]'); await p.waitForTimeout(500) };
try {
  const ctx = await browser.newContext({ viewport:{ width:1440, height:900 } }), p = await ctx.newPage(); watch(p);
  await p.goto(`${origin}/terminal-app/`); await ready(p);
  R.start = { btn:await btnText(p), place:await p.evaluate(() => document.getElementById('layoutBtn').previousElementSibling.previousElementSibling.id) };
  // 1. Save layout with no layout yet asks for a name and creates one
  await addInd(p, 'Net Buy Persistence', 'FL12');
  await menu(p); R.menu_items = await p.$$eval('.lay-menu .lay-mi, .lay-menu .lay-head', es => es.map(e => e.textContent.trim()));
  await p.screenshot({ path:join(OUT, 'd_menu_empty.png') });
  await p.click('.lay-menu [data-act="save"]'); await nameDlg(p, 'Swing');
  R.saved = { btn:await btnText(p), rows:[...layouts.rows.values()].map(r => [r.name, r.summary, r.revision]) };
  // 2. autosave: a change is saved without asking
  await addInd(p, 'Broker Inventory', 'FL23'); await p.waitForTimeout(2200);
  R.autosave = { rows:[...layouts.rows.values()].map(r => [r.name, r.summary, r.revision]), btn:await btnText(p) };
  // 3. fold a pane: part of the layout
  await p.click('.ind-row[data-def="FL23"] .ind-fold'); await p.waitForTimeout(2200);
  R.fold_saved = JSON.parse([...layouts.rows.values()][0].state['ml.ind.v1']).map(o => o.def + (o.fold ? ':fold' : ''));
  // 4. autosave off: a change shows the unsaved mark; Ctrl+S saves it
  await menu(p); await p.click('.lay-menu .lay-switch'); await p.keyboard.press('Escape');
  await p.click('#styleGroup [data-style="line"]'); await p.waitForTimeout(2200);
  R.manual = { btn:await btnText(p), rev:[...layouts.rows.values()][0].revision };
  await p.keyboard.press('Control+s'); await p.waitForTimeout(800);
  R.manual.after = { btn:await btnText(p), rev:[...layouts.rows.values()][0].revision, style:[...layouts.rows.values()][0].state['ml.chart.style'] };
  // 5. Make a copy and Rename
  await menu(p); await p.click('.lay-menu [data-act="copy"]'); await nameDlg(p, 'Swing copy');
  await menu(p); await p.click('.lay-menu [data-act="rename"]'); await nameDlg(p, 'Swing');      // taken by the first one
  R.rename_taken = await p.$eval('.lay-dlg .lay-err', e => e.textContent).catch(() => null);
  await p.fill('.lay-dlg input', 'Momentum'); await p.click('.lay-dlg [data-ok]'); await p.waitForTimeout(500);
  R.after_copy = { btn:await btnText(p), names:[...layouts.rows.values()].map(r => r.name) };
  await menu(p); R.recent = await p.$$eval('.lay-menu .lay-item', es => es.map(e => e.querySelector('b').textContent + (e.classList.contains('on') ? ' (on)' : '')));
  await p.click('.lay-menu .lay-item:not(.on) .lay-star'); await p.waitForTimeout(400);
  R.star = [...layouts.rows.values()].map(r => [r.name, r.favorite]);
  await p.screenshot({ path:join(OUT, 'd_menu.png') }); await p.keyboard.press('Escape');
  // 6. Create new layout: a blank chart on the same ticker
  await menu(p); await p.click('.lay-menu [data-act="new"]'); await nameDlg(p, 'Blank');
  await ready(p);
  R.new = { btn:await btnText(p), inds:await inds(p), symbol:await p.evaluate(() => localStorage.getItem('ml.symbol')), style:await p.evaluate(() => localStorage.getItem('ml.chart.style')) };
  // 7. "." opens the list; opening "Swing" brings its indicators, fold and chart type back on the same ticker
  await p.mouse.click(700, 300); await p.keyboard.press('.'); await p.waitForSelector('.lay-orow');
  R.open_rows = await p.$$eval('.lay-orow', es => es.map(e => e.querySelector('b').textContent));
  await p.screenshot({ path:join(OUT, 'd_open.png') });
  await p.click('.lay-orow:has-text("Swing")'); await ready(p); await p.waitForTimeout(2500);
  R.opened = { btn:await btnText(p), inds:await inds(p), folded:await p.$eval('.ind-row[data-def="FL23"]', r => r.classList.contains('folded')).catch(() => null),
    style:await p.evaluate(() => document.querySelector('#styleGroup [aria-pressed="true"]')?.dataset.style), dirty:await p.evaluate(() => window.marketLabLayouts.dirty()) };
  // 8. delete a layout from the list (two clicks)
  await p.keyboard.press('.'); await p.waitForSelector('.lay-orow');
  await p.click('.lay-orow:has-text("Blank") .lay-del'); await p.click('.lay-orow:has-text("Blank") .lay-del'); await p.waitForTimeout(400);
  R.deleted = [...layouts.rows.values()].map(r => r.name); await p.keyboard.press('Escape');
  R.calls = layouts.calls.length;
  await p.screenshot({ path:join(OUT, 'd_chart.png') });
  await ctx.close();
  // phone: the button fits and the menu stays on screen
  const ph = await browser.newContext({ ...devices['iPhone 13'] }), q = await ph.newPage(); watch(q);
  await q.goto(`${origin}/terminal-app/`); await ready(q);
  const b = await q.$eval('#layoutBtn', e => { const r = e.getBoundingClientRect(); return { left:Math.round(r.left), right:Math.round(r.right), vis:r.width > 0 } });
  await q.evaluate(() => document.getElementById('layoutBtn').scrollIntoView({ inline:'center' })); await q.tap('#layoutBtn'); await q.waitForTimeout(500);
  R.phone = { btn:b, menu:await q.$eval('.lay-menu', m => { const r = m.getBoundingClientRect(); return { left:Math.round(r.left), right:Math.round(r.right), top:Math.round(r.top), bottom:Math.round(r.bottom), vw:innerWidth, vh:innerHeight } }),
    overflow:await q.evaluate(() => document.documentElement.scrollWidth - innerWidth) };
  await q.screenshot({ path:join(OUT, 'p_menu.png') });
  await ph.close();
} catch (e) { errors.push('harness: ' + e.message.split('\n')[0]) }
R.errors = errors;
console.log(JSON.stringify(R, null, 1));
await browser.close(); close();
