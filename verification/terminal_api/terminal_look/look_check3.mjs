/* QA fixes (user go 2026-11-06, QA_REPORT.md): checks of H1-H3, M1-M5, M7-M9 on the built page with the snapshot.
   Usage: node look_check3.mjs DATA OUT */
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { mkdir } from 'node:fs/promises';
import { serve } from './serve.mjs';
const { chromium, devices } = createRequire(import.meta.url)('playwright');

const [DATA, OUT] = process.argv.slice(2);
const { origin, close } = await serve(DATA, 'BBRI');
await mkdir(OUT, { recursive:true });
const browser = await chromium.launch();
const R = {}, errors = [];
const watch = p => { p.on('pageerror', e => errors.push(e.message)); p.on('console', m => { if (m.type() === 'error' && !/404/.test(m.text())) errors.push(m.text()) }) };
const ready = async p => { await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30_000 }); await p.waitForTimeout(1200) };
const addInd = async (p, q, id) => { await p.click('#indBtn'); await p.fill('#imSearch', q); await p.click(`.im-row[data-id="${id}"] .im-add`); await p.keyboard.press('Escape'); await p.waitForTimeout(900) };
const row = id => `.ind-row[data-def="${id}"]`;
try {
  // desktop
  const ctx = await browser.newContext({ viewport:{ width:1440, height:900 } }), p = await ctx.newPage(); watch(p);
  await p.goto(`${origin}/terminal-app/`); await ready(p);
  // M9: search by short name
  await p.click('#indBtn'); await p.fill('#imSearch', 'RSI'); await p.waitForTimeout(150);
  R.m9_first = await p.$eval('.im-row[data-id]', e => e.querySelector('.nmt').textContent); await p.keyboard.press('Escape');
  // M2: All brokers over both investor types
  await addInd(p, 'Net Buy Persistence', 'FL12');
  await p.selectOption(`${row('FL12')} .ind-sel[data-k="scope"] select`, 'all'); await p.waitForTimeout(400);
  R.m2_note = await p.$eval(`${row('FL12')} > b`, e => e.textContent);
  // M1: emptied lists survive a reload; the dialog accepts them
  await addInd(p, 'Broker Inventory', 'FL23');
  await p.click(`${row('FL23')} .fl[data-k="brokers"] .fl-btn`); await p.click(`${row('FL23')} .fl[data-k="brokers"] [data-act="none"]`); await p.mouse.click(700, 300);
  await p.reload(); await ready(p);
  R.m1_reload = { fl23:await p.evaluate(() => JSON.parse(localStorage.getItem('ml.ind.v1')).find(o => o.def === 'FL23')?.params.brokers),
    fl23_row:await p.$eval(`${row('FL23')} > b`, e => e.textContent), fl12_scope:await p.evaluate(() => JSON.parse(localStorage.getItem('ml.ind.v1')).find(o => o.def === 'FL12')?.params.scope) };
  // H3 + M4: map labels inside the SVG, dots reachable, keyboard tooltip
  if (await p.$eval('#workspace', e => e.classList.contains('right-collapsed')).catch(() => false)) { await p.click('#rpExpand'); await p.waitForTimeout(800) }
  await p.locator('.st[data-sec="fdmap"]').scrollIntoViewIfNeeded();
  R.h3_ticks = await p.$$eval('.fdm-svg text.fdm-tk', ts => ts.map(t => ({ t:t.textContent, x:Math.round(t.getBBox().x) })).filter(o => o.x < 0));
  R.m4_points = await p.$$eval('.fdm-pt', gs => gs.map(g => g.getAttribute('aria-label').split(':')[0]));
  const pts = await p.$$('.fdm-pt .dot');
  R.m4_hover = [];
  for (const d of pts) { const b = await d.boundingBox(); await p.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await p.waitForTimeout(120);
    R.m4_hover.push(await p.$eval('.st-tip', e => e.hidden ? null : e.textContent.split('·')[0].trim())) }
  await p.focus('.fdm-pt'); await p.waitForTimeout(120); R.m4_focus = await p.$eval('.st-tip', e => e.hidden ? null : e.textContent.slice(0, 40));
  R.m3_labels = { tag:await p.$eval('.fdm-now .tag', e => e.textContent), ax:await p.$eval('.fdm-x', e => e.textContent), cap:await p.$eval('.acc-cap', e => e.textContent) };
  await p.screenshot({ path:join(OUT, 'd_map.png'), clip:await p.locator('.st[data-sec="fdmap"]').boundingBox() });
  // M7: Top brokers on Nego
  await p.selectOption('#accBoard', 'Nego'); await p.waitForTimeout(300);
  R.m7 = { body:await p.$eval('#accBody', e => e.textContent.trim().slice(0, 80)), hint:await p.$eval('#accHint', e => e.textContent) };
  // M5: Tab reaches a price-chart row and reveals its controls
  await addInd(p, 'Buy VWAP · Rolling', 'FL17');
  await p.focus(row('FL17')); await p.keyboard.press('Tab'); await p.waitForTimeout(150);
  R.m5 = await p.evaluate(() => ({ active:document.activeElement?.closest('.ind-flt') ? document.activeElement.tagName : document.activeElement?.className, shown:getComputedStyle(document.querySelector('.ind-row[data-def="FL17"] .ind-flt')).display }));
  await ctx.close();
  // phone
  const ph = await browser.newContext({ ...devices['iPhone 13'] }), q = await ph.newPage(); watch(q);
  await q.goto(`${origin}/terminal-app/`); await ready(q);
  await addInd(q, 'Net Buy Persistence', 'FL12'); await addInd(q, 'Broker Inventory', 'FL23'); await addInd(q, 'Buy VWAP · Rolling', 'FL17');
  R.h1_rows = await q.$$eval('.ind-row', rs => rs.filter(r => r.querySelector('.ind-fltbtn')).map(r => { const b = r.getBoundingClientRect(); return { def:r.dataset.def, h:Math.round(b.height), right:Math.round(b.right) } }));
  R.h1_vw = await q.evaluate(() => innerWidth);
  R.h1_names = await q.$$eval('.ind-row', rs => rs.map(r => { const k = r.querySelector('.ind-k'); const b = k?.getBoundingClientRect(); return [r.dataset.def, k?.textContent, Math.round(b?.width || 0), getComputedStyle(k).display] }));
  await q.screenshot({ path:join(OUT, 'p_rows.png') });
  await q.tap(`${row('FL12')} .ind-fltbtn`); await q.waitForTimeout(300);
  R.h1_open = await q.$eval(`${row('FL12')} .ind-flt`, e => { const b = e.getBoundingClientRect(); return { left:Math.round(b.left), right:Math.round(b.right), top:Math.round(b.top), h:Math.round(b.height) } });
  await q.screenshot({ path:join(OUT, 'p_filters_open.png') });
  R.overflow = await q.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  await ph.close();
} catch (e) { errors.push('harness: ' + e.message.split('\n')[0]) }
R.errors = errors;
console.log(JSON.stringify(R, null, 1));
await browser.close(); close();
