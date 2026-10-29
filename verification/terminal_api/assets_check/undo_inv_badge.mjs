import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const b = await chromium.launch(); const p = await b.newPage({ viewport:{ width:1600, height:960 } });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()) });
await p.addInitScript(() => { if (sessionStorage.getItem('i')) return; sessionStorage.setItem('i', '1'); localStorage.clear(); localStorage.setItem('ml.symbol','MAPI'); localStorage.setItem('ml.broker.collapsed','0');
  localStorage.setItem('ml.ind.v1', JSON.stringify([{ def:'netflow', params:{ brokers:null, length:5, boards:['Regular','Nego','Cash'], investors:['Foreign'] }, style:{ type:'Histogram', color:'#089981', colorNeg:'#f23645' }, on:true }])) });
await p.goto('http://127.0.0.1:18901/terminal-app/'); await p.waitForSelector('#chart canvas'); await p.waitForTimeout(4500);
const R = {};
const title = () => p.$eval('.ind-row[data-def="netflow"] .ind-k', e => e.textContent);
R.indBefore = await title();
await p.hover('.ind-row[data-def="netflow"]'); await p.click('.ind-row[data-def="netflow"] [data-act="cfg"]');
const inp = await p.$('.idlg-back:not([hidden]) input[type=number]'); await inp.fill('12'); await inp.press('Tab');
await p.click('.idlg-back:not([hidden]) [data-act="ok"]'); await p.waitForTimeout(200);
R.indAfterOk = await title();
await p.mouse.click(700, 300); await p.keyboard.press('Control+z'); await p.waitForTimeout(200); R.afterUndo = await title();
await p.keyboard.press('Control+y'); await p.waitForTimeout(200); R.afterRedo = await title();
R.saved = await p.evaluate(() => JSON.parse(localStorage.getItem('ml.ind.v1'))[0].params.length);
// inventory chips: three columns
await p.$eval('#invBody', e => e.scrollIntoView({ block:'center' })); await p.waitForTimeout(300);
R.badge = await p.$eval('#invHint .rp-count', e => e.textContent + ' ' + getComputedStyle(e).backgroundColor).catch(() => 'none');
const cols = () => p.$$eval('#invLegend .rp-chip', cs => cs.map(c => Math.round(c.getBoundingClientRect().left) + ',' + Math.round(c.getBoundingClientRect().top)));
R.chips3 = await cols();
await p.screenshot({ path:'shots/inv3.png', clip:await p.$eval('section[data-sec="inv"]', e => { const r = e.getBoundingClientRect(); return { x:r.x, y:r.y, width:r.width, height:Math.min(r.height, 330) } }) });
// add two more brokers through the Broker filter
await p.click('#invFilter .fl-btn'); const vals = await p.$$eval('#invFilter .fl-opt input:not(:checked):not([disabled])', i => i.slice(0, 2).map(x => x.value)); for (const v of vals) { await p.click(`#invFilter input[value="${v}"]`); await p.waitForTimeout(150) } await p.keyboard.press('Escape'); await p.waitForTimeout(300);
R.chips5 = await cols();
R.badge5 = await p.$eval('#invHint .rp-count', e => e.textContent);
await p.screenshot({ path:'shots/inv5.png', clip:await p.$eval('section[data-sec="inv"]', e => { const r = e.getBoundingClientRect(); return { x:r.x, y:r.y, width:r.width, height:Math.min(r.height, 330) } }) });
// shift + wheel on the chart: range moves, width kept
const rg = () => p.evaluate(() => { const c = document.querySelector('#chart'); return null });
const c = await p.$eval('#chart', e => e.getBoundingClientRect().toJSON());
const before = await p.$eval('#flowTip', e => e.innerText.slice(0, 12));
await p.mouse.move(c.x + c.width * .5, c.y + c.height * .5);
const axisBefore = await p.$$eval('#chart table tr:last-child td:nth-child(2) canvas', cs => cs.length);
await p.keyboard.down('Shift'); for (let k = 0; k < 4; k++) await p.mouse.wheel(0, 120); await p.keyboard.up('Shift'); await p.waitForTimeout(300);
const after = await p.$eval('#flowTip', e => e.innerText.slice(0, 12));
R.shiftWheel = { tipBefore:before, tipAfter:after };
R.errors = errs; console.log(JSON.stringify(R, null, 1)); await b.close();
