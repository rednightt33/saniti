/* EXEC-IND-HOVER (user 2026-11-06: "Kalau mouse kita geser sedikit ... langsung keempat indikator tersebut hilang";
   "Opsi 2"): a pane row's buttons stay while the pointer is within 8px of the row, and 0.5 s after it leaves; a click
   on a button after a slip works; one row active at a time; the title still takes the pointer; the price-pane legend row
   keeps the grace; the on-hover filters (filter toggle off) follow the same rule. Writes look10_*.png to the scratchpad. */
import { createRequire } from 'node:module';
import { serve } from '/home/user/saniti/verification/terminal_api/terminal_look/serve.mjs';
const { chromium, devices } = createRequire('/home/user/saniti/verification/terminal_api/terminal_look/')('playwright');
const SP = '/tmp/claude-0/-home-user-saniti/5abac1e8-94e8-5166-9d5b-02bb4e4273bc/scratchpad';
const { origin, close } = await serve(SP + '/look', 'BBRI');
const b = await chromium.launch(); const errs = [], R = {};
const vis = (p, row) => p.evaluate(r => { const e = document.querySelector(r), x = e.querySelector('.ind-eye[data-act="cfg"]');
  return { btn:getComputedStyle(x).opacity === '1' && getComputedStyle(x).display !== 'none', flt:[...e.querySelectorAll('.ind-flt')].some(f => f.offsetWidth > 0), hov:e.classList.contains('hov') } }, row);
for (const [nm, opt, filters] of [['d1440', { viewport:{ width:1440, height:900 } }, '1'], ['d1100off', { viewport:{ width:1100, height:800 } }, '0']]) {
  const ctx = await b.newContext(opt), p = await ctx.newPage(); p.on('pageerror', e => errs.push(nm + ' ' + e.message));
  await p.addInitScript(f => { if (!sessionStorage.getItem('s')) { sessionStorage.setItem('s', '1'); localStorage.setItem('ml.ind.filters', f); localStorage.setItem('ml.ind.v1', JSON.stringify(['sma', 'FL03', 'FL12'].map(d => ({ def:d, params:{} })))) } }, filters);
  await p.goto(origin + '/terminal-app/'); await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(2500);
  const row = '.ind-row[data-def="FL03"]', r = {};
  const k = await p.locator(row + ' .ind-k').boundingBox(), rb = await p.locator(row).boundingBox();
  r.before = await vis(p, row);
  await p.mouse.move(k.x + 30, k.y + k.height / 2); await p.waitForTimeout(200); r.on = await vis(p, row);
  // each probe starts on the title; a point within 8px of the row keeps the buttons (the pane separator's resize handle,
  // about 5px under a pane's top edge, stays the chart's: the first pane row is probed 6-7px above for that reason)
  const home = async () => { await p.mouse.move(k.x + 30, k.y + k.height / 2); await p.waitForTimeout(150) };
  r.sep = await p.evaluate(y => { const e = document.elementFromPoint(300, y); return e ? getComputedStyle(e).zIndex : null }, rb.y - 3);
  for (const [nmP, x, y] of [['above7', k.x + 30, rb.y - 7], ['below3', k.x + 30, rb.y + rb.height + 3], ['below7', k.x + 30, rb.y + rb.height + 7], ['left6', rb.x - 6, k.y + k.height / 2]]) {
    await home(); await p.mouse.move(x, y); await p.waitForTimeout(800); r[nmP] = await vis(p, row) }
  await home(); await p.mouse.move(k.x + 30, rb.y + rb.height + 40); await p.waitForTimeout(250); r.away_250ms = await vis(p, row);
  await p.waitForTimeout(500); r.away_750ms = await vis(p, row);
  // a slip then a click on Settings within the grace: the Settings dialog opens
  await p.mouse.move(k.x + 30, k.y + k.height / 2); await p.waitForTimeout(150);
  await p.mouse.move(k.x + 30, rb.y + rb.height + 40); await p.waitForTimeout(200);
  const cfg = await p.locator(row + ' .ind-eye[data-act="cfg"]').boundingBox();
  if (cfg) { await p.mouse.click(cfg.x + cfg.width / 2, cfg.y + cfg.height / 2); await p.waitForTimeout(400) }
  r.click_after_slip = await p.evaluate(() => document.querySelector('.idlg-back')?.hidden === false);
  await p.keyboard.press('Escape'); await p.waitForTimeout(300);
  // the buttons stay where they are while the pointer slips onto the chart, whose crosshair value is longer or shorter
  await p.mouse.move(k.x + 30, k.y + k.height / 2); await p.waitForTimeout(150);
  const cx = () => p.$eval(row + ' .ind-eye[data-act="cfg"]', e => Math.round(e.getBoundingClientRect().x));
  const vt = () => p.$eval(row + ' > b', e => e.textContent);
  r.stable = [await cx()];
  for (const x of [opt.viewport.width * 0.12, opt.viewport.width * 0.6]) { await p.mouse.move(x, rb.y + rb.height + 30); await p.waitForTimeout(150); r.stable.push(await cx(), await vt()) }
  await p.waitForTimeout(600);
  // the title still takes the pointer while the row is active
  await p.mouse.move(k.x + 30, k.y + k.height / 2); await p.waitForTimeout(150);
  r.title_hit = await p.evaluate(([x, y]) => document.elementFromPoint(x, y)?.className, [k.x + 30, k.y + k.height / 2]);
  // one active row at a time
  const k2 = await p.locator('.ind-row[data-def="FL12"] .ind-k').boundingBox();
  await p.mouse.move(k2.x + 30, k2.y + k2.height / 2); await p.waitForTimeout(100);
  r.one_active = await p.$$eval('.ind-row.hov', es => es.map(e => e.dataset.def));
  // the price-pane legend row keeps the grace, without the band
  const lk = await p.locator('.ind-row[data-def="sma"] .ind-k').boundingBox();
  await p.mouse.move(lk.x + 20, lk.y + lk.height / 2); await p.waitForTimeout(150);
  await p.mouse.move(lk.x + 20, lk.y + lk.height + 40); await p.waitForTimeout(250); r.legend_250ms = await vis(p, '.ind-row[data-def="sma"]');
  await p.waitForTimeout(500); r.legend_750ms = await vis(p, '.ind-row[data-def="sma"]');
  await p.mouse.move(k.x + 30, k.y + k.height / 2); await p.waitForTimeout(150); await p.mouse.move(k.x + 30, rb.y + rb.height + 6); await p.waitForTimeout(300);
  await p.screenshot({ path:`${SP}/look10_${nm}.png`, clip:{ x:Math.max(0, rb.x - 20), y:Math.max(0, rb.y - 50), width:Math.min(opt.viewport.width - rb.x + 20, 1000), height:rb.height + 80 } });
  R[nm] = r; await ctx.close();
}
console.log(JSON.stringify(R, null, 1)); console.log('errs', errs); await b.close(); close();
