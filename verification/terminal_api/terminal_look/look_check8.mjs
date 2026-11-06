/* EXEC-TERMINAL-LOOK-3 (user 2026-11-06): pane filters the Flow Timeline's size, chevron over the y-axis, the filter toggle under the trash, the Top brokers badge and lanes. Writes look8_*.png to the scratchpad given below. */
import { createRequire } from 'node:module';
import { serve } from '/home/user/saniti/verification/terminal_api/terminal_look/serve.mjs';
const { chromium, devices } = createRequire('/home/user/saniti/verification/terminal_api/terminal_look/')('playwright');
const SP = '/tmp/claude-0/-home-user-saniti/5abac1e8-94e8-5166-9d5b-02bb4e4273bc/scratchpad';
const { origin, close } = await serve(SP + '/look', 'BBRI');
const b = await chromium.launch(); const errs = [], R = {};
for (const [nm, opt] of [['d1440', { viewport:{ width:1440, height:900 } }], ['phone', devices['iPhone 13']]]) {
  const ctx = await b.newContext(opt), p = await ctx.newPage(); p.on('pageerror', e => errs.push(nm + ' ' + e.message));
  await p.addInitScript(() => { if (!sessionStorage.getItem('s')) { sessionStorage.setItem('s', '1'); localStorage.setItem('ml.broker.collapsed', '0'); localStorage.setItem('ml.ind.v1', JSON.stringify(['FL12', 'FL23', 'FL46'].map(d => ({ def:d, params:{} })))) } });
  await p.goto(origin + '/terminal-app/'); await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(2500);
  R[nm] = await p.evaluate(() => {
    const flt = document.querySelector('#flBoard .fl-btn').getBoundingClientRect(), pane = document.querySelector('.ind-row[data-def="FL12"] .ind-flt .fl-btn, .ind-row[data-def="FL12"] .ind-fltbtn')?.getBoundingClientRect();
    const fs = e => e ? getComputedStyle(e).fontSize : null;
    const folds = [...document.querySelectorAll('.ind-fold')].map(f => { const r = f.getBoundingClientRect(); return [f.dataset.def, Math.round(r.left), Math.round(r.top)] });
    const rows = [...document.querySelectorAll('.ind-row.in-pane')].map(r => { const x = r.getBoundingClientRect(); return [r.dataset.def, Math.round(x.left), Math.round(x.right), Math.round(x.height)] });
    return { flowBtn:[Math.round(flt.height), fs(document.querySelector('#flBoard .fl-btn'))], paneBtn:pane ? [Math.round(pane.height), fs(document.querySelector('.ind-row[data-def="FL12"] .ind-flt .fl-btn, .ind-row[data-def="FL12"] .ind-fltbtn'))] : null, folds, rows, vw:innerWidth };
  });
  await p.screenshot({ path:`${SP}/look8_${nm}.png` });
  if (nm === 'd1440') {
    await p.click('.dr-btn[aria-label="Hide indicator filters"]'); await p.waitForTimeout(400);
    R.toggle = { stored:await p.evaluate(() => localStorage.getItem('ml.ind.filters')), visibleFilters:await p.$$eval('.ind-flt', es => es.filter(e => e.offsetWidth).length) };
    await p.screenshot({ path:`${SP}/look8_off.png` });
    await p.click('.dr-btn[aria-label="Show indicator filters"]'); await p.waitForTimeout(300);
    const acc = p.locator('.st[data-sec="acc"]'); await acc.scrollIntoViewIfNeeded(); await p.screenshot({ path:`${SP}/look8_acc.png`, clip:await acc.boundingBox() });
    R.lanes = await p.$$eval('.acc-lane', ls => ls.map(l => Math.round(l.getBoundingClientRect().top)));
  }
  await ctx.close();
}
console.log(JSON.stringify(R)); console.log('errs', errs); await b.close(); close();
