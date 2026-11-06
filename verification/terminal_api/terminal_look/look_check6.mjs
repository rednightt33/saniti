/* QA round 3 fixes (user 2026-11-06: "1 dan 2, jalankan"): one check per finding of QA_REPORT.md section 9, on the built
   page with the snapshot and the stand-in layouts API (failures injected with page.route). Usage: node look_check6.mjs DATA OUT */
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
const seed = (p, kv) => p.addInitScript(kv => { if (sessionStorage.getItem('seeded')) return; sessionStorage.setItem('seeded', '1'); for (const [k, v] of Object.entries(kv)) localStorage.setItem(k, v) }, kv);
const IND = JSON.stringify([{ def:'FL12', params:{} }, { def:'FL23', params:{} }, { def:'FL21', params:{} }]);
const page = async (opts, kv = {}) => { const ctx = await browser.newContext(opts), p = await ctx.newPage(); watch(p); await seed(p, kv); await p.goto(`${origin}/terminal-app/`); await ready(p); return { ctx, p } };
const box = (p, sel) => p.$eval(sel, e => { const r = e.getBoundingClientRect(); return { l:Math.round(r.left), r:Math.round(r.right), t:Math.round(r.top), b:Math.round(r.bottom) } });
const mkLayout = (id, name, state = { 'ml.tf':'D' }) => { const now = new Date().toISOString(); layouts.rows.set(id, { layout_id:id, name, summary:'D · 0 indicators', schema_version:1, favorite:false, revision:1, created_at:now, updated_at:now, opened_at:now, state }) };
const D = { viewport:{ width:1440, height:900 } };
try {
  // H2: the Open dialog stays on a phone screen with a 120-character name
  mkLayout('lay_' + 'a'.repeat(32), 'L'.repeat(120)); mkLayout('lay_' + 'b'.repeat(32), 'Short');
  { const { ctx, p } = await page(devices['iPhone 13']);
    await p.evaluate(() => document.body.focus()); await p.keyboard.press('.'); await p.waitForSelector('.lay-orow');
    R.h2 = { vw:await p.evaluate(() => innerWidth), dlg:await box(p, '.lay-dlg'), close:await box(p, '.lay-dlg [data-x]'), del:await box(p, '.lay-orow .lay-del') };
    await p.screenshot({ path:join(OUT, 'h2_phone_open.png') }); await ctx.close() }
  layouts.rows.clear();
  // M1: the arrow keys walk the whole menu; M2: Tab stays in a dialog, Escape closes it from anywhere, focus returns
  { const { ctx, p } = await page(D);
    mkLayout('lay_' + 'c'.repeat(32), 'One');
    await p.focus('#layoutBtn'); await p.keyboard.press('Enter'); await p.waitForTimeout(500);
    const seen = []; for (let k = 0; k < 9; k++) { seen.push(await p.evaluate(() => { const a = document.activeElement; return a.dataset.act || (a.matches('input') ? 'autosave' : a.dataset.open ? 'recent' : a.className) })); await p.keyboard.press('ArrowDown') }
    R.m1 = seen;
    await p.keyboard.press('Escape'); R.m2_menu_focus = await p.evaluate(() => document.activeElement.id);
    await p.click('#layoutBtn'); await p.waitForTimeout(300); await p.click('.lay-menu [data-act="copy"]'); await p.waitForSelector('.lay-dlg input');
    for (let k = 0; k < 6; k++) await p.keyboard.press('Tab');
    R.m2_trap = await p.evaluate(() => !!document.activeElement.closest('.lay-dlg'));
    await p.keyboard.press('Escape'); await p.waitForTimeout(200);
    R.m2_closed = await p.evaluate(() => !document.querySelector('.lay-back')); R.m2_focus = await p.evaluate(() => document.activeElement.id);
    await ctx.close() }
  layouts.rows.clear();
  // M4: no layout open and an indicator on the chart: opening a layout asks first
  mkLayout('lay_' + 'd'.repeat(32), 'Target');
  { const { ctx, p } = await page(D, { 'ml.ind.v1':IND });
    await p.evaluate(() => document.body.focus()); await p.keyboard.press('.'); await p.waitForSelector('.lay-orow'); await p.click('.lay-orow');
    await p.waitForTimeout(400); R.m4_confirm = await p.$eval('.lay-dlg p', e => e.textContent).catch(() => null);
    await p.click('.lay-dlg [data-x]'); await p.waitForTimeout(300); R.m4_kept = (await p.evaluate(() => JSON.parse(localStorage.getItem('ml.ind.v1')).length));
    await ctx.close() }
  // M3: a change made while an opened layout restores itself is shown as a change once it settles (Autosave off)
  { const { ctx, p } = await page(D, { 'ml.layout.autosave':'0' });
    await p.evaluate(() => document.body.focus()); await p.keyboard.press('.'); await p.waitForSelector('.lay-orow');
    await Promise.all([p.waitForNavigation({ timeout:30000 }), p.click('.lay-orow:has-text("Target")')]);   // opening a layout reloads the page
    await p.waitForFunction(() => !document.querySelector('.ml-boot') && document.getElementById('layoutBtn'), null, { timeout:30000 });
    await p.click('#styleGroup [data-style="line"]'); await p.waitForTimeout(9500);
    R.m3 = { dirty:await p.evaluate(() => window.marketLabLayouts.dirty()), btn:await p.$eval('#layoutBtn', b => b.textContent.trim() + (b.querySelector('.lay-dirty') ? ' •' : '')) };
    // L5: Save with no change sends nothing
    await p.keyboard.press('Control+s'); await p.waitForTimeout(600); const before = layouts.calls.length;
    await p.keyboard.press('Control+s'); await p.waitForTimeout(600);
    R.l5 = { puts_after_clean_save:layouts.calls.slice(before).filter(c => c.startsWith('PUT')).length, toast:await p.$eval('.lay-toast', t => t.textContent) };
    // M5: an autosave after another device renamed the layout keeps the new name
    const row = layouts.rows.get('lay_' + 'd'.repeat(32)); row.name = 'Renamed elsewhere'; row.revision += 1;
    await p.click('#layoutBtn'); await p.waitForTimeout(300); await p.click('.lay-menu .lay-switch'); await p.keyboard.press('Escape');
    await p.click('#styleGroup [data-style="candle"]'); await p.waitForTimeout(2500);
    R.m5 = { server_name:layouts.rows.get('lay_' + 'd'.repeat(32)).name, style:layouts.rows.get('lay_' + 'd'.repeat(32)).state['ml.chart.style'] };
    await ctx.close() }
  // M6: a 503 before the migration and a 500 read as plain sentences; the message wraps on a phone
  { const { ctx, p } = await page(devices['iPhone 13']);
    await p.route('**/api/v1/terminal/layouts**', r => r.fulfill({ status:503, contentType:'application/json', headers:{ 'Retry-After':'30' }, body:JSON.stringify({ error:{ code:'LAYOUTS_NOT_READY', message:'Saved layouts are not available yet on this server. Try again in a few minutes; your chart is unchanged.' } }) }));
    await p.evaluate(() => document.getElementById('layoutBtn').scrollIntoView({ inline:'center' })); await p.tap('#layoutBtn'); await p.waitForTimeout(800);
    R.m6_menu = await p.$eval('.lay-menu .lay-msg', e => e.textContent).catch(() => null); await p.keyboard.press('Escape');
    await p.unroute('**/api/v1/terminal/layouts**');
    await p.route('**/api/v1/terminal/layouts/**', r => r.fulfill({ status:500, contentType:'text/html', body:'<h1>oops</h1>' }));
    await p.evaluate(() => document.dispatchEvent(new KeyboardEvent('keydown', { key:'s', ctrlKey:true, bubbles:true }))); await p.waitForSelector('.lay-dlg input'); await p.fill('.lay-dlg input', 'X'); await p.click('.lay-dlg [data-ok]'); await p.waitForTimeout(500);
    R.m6_500 = await p.$eval('.lay-dlg .lay-err', e => e.textContent).catch(() => null);
    await p.click('.lay-dlg [data-x]');
    await ctx.close() }
  // collapse: three folded Flow panes on a phone and at 1440 do not overlap, and their axes print nothing
  for (const [nm, opts] of [['phone', devices['iPhone 13']], ['d1440', D]]) {
    const { ctx, p } = await page(opts, { 'ml.ind.v1':JSON.stringify([{ def:'FL12', params:{}, fold:true }, { def:'FL23', params:{}, fold:true }, { def:'FL21', params:{}, fold:true }]) });
    await p.waitForTimeout(1500);
    R['fold_' + nm] = await p.evaluate(() => { const rs = [...document.querySelectorAll('.ind-row.in-pane')].map(r => r.getBoundingClientRect()); let ov = 0;
      for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) if (rs[i].bottom > rs[j].top + 0.5 && rs[j].bottom > rs[i].top + 0.5) ov++;
      return { rows:rs.map(r => Math.round(r.height)), overlaps:ov } });
    await p.screenshot({ path:join(OUT, `fold_${nm}.png`) }); await ctx.close() }
  // R2-M3: broker files that fail show "—" at once
  { const ctx = await browser.newContext(D), p = await ctx.newPage(); watch(p);
    await p.route('**/bucket/broker/**', r => r.fulfill({ status:500, body:'x' }));
    await p.goto(`${origin}/terminal-app/`); await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(4000);
    R.r2m3 = await p.$eval('#flowSummary', e => e.textContent.replace(/\s+/g, ' ').trim()); await ctx.close() }
  // right panel: the map at 260 px, Nego "No net flow", hints name the board, toolbar with both panels open
  { const { ctx, p } = await page(D, { 'ml.broker.collapsed':'0', 'ml.stats.collapsed':'0' });
    await p.waitForTimeout(1500);
    R.toolbar = await p.evaluate(() => { const t = document.querySelector('.main-col .tvbar'), f = document.getElementById('symSearch').getBoundingClientRect(), fs = document.querySelector('.tvbar [aria-label*="ull screen" i], .tvbar #fullBtn')?.getBoundingClientRect();
      return { over:t.scrollWidth - t.clientWidth, search:Math.round(f.width), full_right:fs ? Math.round(fs.right) : null, bar_right:Math.round(t.getBoundingClientRect().right) } });
    await p.evaluate(() => document.getElementById('workspace').style.setProperty('--right-w', '260px')); await p.waitForTimeout(600);
    R.panel260 = await p.evaluate(() => { const s = document.getElementById('rightScroll'); return { over:s.scrollWidth - s.clientWidth } });
    await p.selectOption('#fdBoard', 'Nego'); await p.waitForTimeout(400);
    R.nego = await p.$eval('.fdm-now .tag', e => e.textContent);
    R.hints = { bs:await p.$eval('#bsHint', e => e.textContent), acc:await p.$eval('#accHint', e => e.textContent) };
    R.minus = await p.$eval('#flowSummary', e => /−Rp/.test(e.textContent) && !/-Rp/.test(e.textContent));
    await ctx.close() }
  // Flow Timeline: a kept broker list the ticker lacks is kept; Escape in a list gives the focus back to its button
  { const { ctx, p } = await page(D, { 'ml.flow.filters':JSON.stringify({ boards:['Regular'], investors:['Foreign'], brokers:['ZZ1', 'ZZ2'] }) });
    await p.waitForTimeout(2500);
    R.kept = await p.evaluate(() => JSON.parse(localStorage.getItem('ml.flow.filters')).brokers);
    await p.click('#flBoard .fl-btn'); await p.waitForTimeout(200); await p.keyboard.press('Tab'); await p.keyboard.press('Escape'); await p.waitForTimeout(150);
    R.esc_focus = await p.evaluate(() => document.activeElement?.closest('#flBoard') ? 'board button' : document.activeElement?.tagName);
    // Tab reaches the Volume row's buttons
    await p.focus('#indRow'); await p.keyboard.press('Tab'); R.tab_volume = await p.evaluate(() => document.activeElement.id);
    // Undo brings a removed indicator back to its place
    await ctx.close() }
  { const { ctx, p } = await page(D, { 'ml.ind.v1':IND });
    await p.evaluate(() => document.querySelector('.ind-row[data-def="FL23"] > [data-act="del"]').click()); await p.waitForTimeout(500);
    await p.mouse.click(700, 200); await p.keyboard.press('Control+z'); await p.waitForTimeout(900);
    R.undo_order = await p.evaluate(() => JSON.parse(localStorage.getItem('ml.ind.v1')).map(o => o.def));
    await ctx.close() }
} catch (e) { errors.push('harness: ' + e.message.split('\n')[0]) }
R.errors = errors;
console.log(JSON.stringify(R, null, 1));
await browser.close(); close();
