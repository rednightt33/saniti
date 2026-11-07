/* EXEC-PANE-ORDER (user 2026-11-07: "panah naik dan turun mirip trading view ... untuk mengatur secara lokasi"; "bisa di
   taruh di screenshot yang saya kotakin merah") and ERRORS M386 (the white gap after a row's value):
   1. a pane's Move up / Move down show while the pointer is in the pane, at its top left in the left axis's room, centred
      on the title's line; Move up is off for the first pane, Move down for the last;
   2. Move up swaps the panes (and the saved order); a reload keeps it; Undo puts it back; the pane's drawing goes with it;
   3. after the pointer comes from the chart (a longer crosshair value) onto a row, no gap before its buttons.
   Writes look13_*.png to the scratchpad; exits 1 on a failed step. */
import { createRequire } from 'node:module';
import { serve } from '/home/user/saniti/verification/terminal_api/terminal_look/serve.mjs';
const { chromium, devices } = createRequire('/home/user/saniti/verification/terminal_api/terminal_look/')('playwright');
const SP = '/tmp/claude-0/-home-user-saniti/5abac1e8-94e8-5166-9d5b-02bb4e4273bc/scratchpad';
const { origin, close, drawings } = await serve(SP + '/look', 'BBRI');
const b = await chromium.launch(); const errs = [], R = {}, bad = [];
const check = (name, ok, got) => { R[name] = got; if (!ok) bad.push(`${name}: ${JSON.stringify(got)}`) };
for (const [nm, opt] of [['d1440', { viewport:{ width:1440, height:900 } }], ['phone', devices['iPhone 13']]]) {
  const ctx = await b.newContext(opt), p = await ctx.newPage(); p.on('pageerror', e => errs.push(nm + ' ' + e.message));
  await p.addInitScript(() => { if (!sessionStorage.getItem('s')) { sessionStorage.setItem('s', '1'); localStorage.setItem('ml.ind.filters', '0'); localStorage.setItem('ml.ind.v1', JSON.stringify(['FL23', 'FL03'].map(d => ({ def:d, params:{} })))) } });
  const boot = async () => { await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(2500) };
  await p.goto(origin + '/terminal-app/'); await boot();
  const order = () => p.evaluate(() => JSON.parse(localStorage.getItem('ml.ind.v1')).map(o => o.def).join(','));
  const tops = () => p.evaluate(() => Object.fromEntries(['FL23', 'FL03'].map(d => [d, Math.round(document.querySelector(`.ind-row.in-pane[data-def="${d}"]`).getBoundingClientRect().top)])));
  const box = d => p.evaluate(dd => { const r = document.querySelector(`.ind-row.in-pane[data-def="${dd}"]`), m = [...document.querySelectorAll('.ind-move')].find(x => x.getAttribute('aria-label').includes(dd === 'FL03' ? 'Share' : 'Broker Inventory'));
    const k = r.querySelector('.ind-k').getBoundingClientRect(), mb = m.getBoundingClientRect(), rr = r.getBoundingClientRect();
    const bar = document.querySelector('.dr-bar')?.getBoundingClientRect();
    return { shown:getComputedStyle(m).opacity === '1', up:!m.children[0].disabled, down:!m.children[1].disabled, dy:+((mb.top + mb.height / 2) - (k.top + k.height / 2)).toFixed(1), clear:+(rr.left - mb.right).toFixed(1), clearBar:bar ? +(mb.left - bar.right).toFixed(1) : null, left:Math.round(mb.left) } }, d);
  if (nm === 'd1440') {
    const t0 = await tops();
    await p.mouse.move(700, t0.FL03 + 50); await p.waitForTimeout(200);
    const b3 = await box('FL03'), b23 = await box('FL23');
    check('shown in its pane only', b3.shown && !b23.shown, { FL03:b3.shown, FL23:b23.shown });
    check('ends disabled', b3.up && !b3.down && !b23.up && b23.down, { FL03:[b3.up, b3.down], FL23:[b23.up, b23.down] });
    check('centred on the title, between the toolbar and the row', Math.abs(b3.dy) <= 1 && b3.clear >= 0 && b3.clearBar >= 0, b3);
    await p.screenshot({ path:`${SP}/look13_before.png`, clip:{ x:40, y:t0.FL23 - 20, width:1100, height:290 } });
    // a line in FL03's pane goes with it
    await p.mouse.move(700, t0.FL03 + 60); await p.mouse.move(701, t0.FL03 + 60); await p.keyboard.press('Alt+KeyH'); await p.waitForTimeout(800);
    const pid = await p.evaluate(() => JSON.parse(localStorage.getItem('ml.ind.v1')).find(o => o.def === 'FL03').pid), key = `BBRI/pane_${pid}`;
    await p.mouse.move(700, t0.FL03 + 50); await p.waitForTimeout(200);
    const upBtn = p.locator('.ind-move[aria-label*="Share"] button[data-dir="-1"]');
    await upBtn.click(); await p.waitForTimeout(600);
    const t1 = await tops();
    check('moved up', (await order()) === 'FL03,FL23' && t1.FL03 < t1.FL23, { order:await order(), tops:t1 });
    check('drawing went with it', (drawings.rows.get(key)?.drawings || []).length === 1, (drawings.rows.get(key)?.drawings || []).length);
    await p.screenshot({ path:`${SP}/look13_after.png`, clip:{ x:40, y:t1.FL03 - 20, width:1100, height:290 } });
    await p.reload(); await boot();
    const t2 = await tops();
    check('order kept after a reload', (await order()) === 'FL03,FL23' && t2.FL03 < t2.FL23, { order:await order(), tops:t2 });
    await p.mouse.move(700, t2.FL03 + 50); await p.waitForTimeout(200);
    await p.locator('.ind-move[aria-label*="Share"] button[data-dir="1"]').click(); await p.waitForTimeout(500);
    await p.keyboard.press('Control+KeyZ'); await p.waitForTimeout(600);
    const t3 = await tops();
    check('undo puts it back', (await order()) === 'FL03,FL23' && t3.FL03 < t3.FL23, { order:await order(), tops:t3 });
    // M386: from the chart onto the row: no gap before the buttons
    const k = await p.locator('.ind-row[data-def="FL03"] .ind-k').boundingBox();
    await p.mouse.move(180, k.y + 70); await p.waitForTimeout(200); await p.mouse.move(k.x + 30, k.y + k.height / 2, { steps:4 }); await p.waitForTimeout(300);
    const gap = await p.$eval('.ind-row[data-def="FL03"]', r => { const v = r.querySelector(':scope > b'), e = r.querySelector('.ind-eye'); return Math.round(e.getBoundingClientRect().left - v.getBoundingClientRect().left - v.scrollWidth) });
    check('no gap before the buttons', gap <= 8, gap);
  } else {
    const b3 = await box('FL03');
    check('phone: shown, between the toolbar and the row', b3.shown && b3.clear >= 0 && b3.clearBar >= 0 && Math.abs(b3.dy) <= 1, b3);
    await p.screenshot({ path:`${SP}/look13_phone.png` });
  }
  await ctx.close();
}
console.log(JSON.stringify(R)); console.log('errs', errs); console.log(bad.length ? 'FAIL\n' + bad.join('\n') : 'PASS');
await b.close(); close(); process.exit(bad.length || errs.length ? 1 : 0);
