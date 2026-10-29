import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const b = await chromium.launch(); const p = await b.newPage({ viewport:{ width:1600, height:960 } });
const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()) });
await p.addInitScript(() => { localStorage.clear(); localStorage.setItem('ml.symbol','MAPI'); localStorage.setItem('ml.broker.collapsed','0');  });
await p.goto('http://127.0.0.1:18901/terminal-app/'); await p.waitForSelector('#chart canvas'); await p.waitForTimeout(4500);
await p.$eval('#invBody svg.rp-inv', e => e.scrollIntoView({ block:'center' })); await p.waitForTimeout(300); const svg = await p.$('#invBody svg.rp-inv'); const r = await svg.boundingBox();
await p.mouse.move(r.x + r.width * .6, r.y + r.height * .5); await p.waitForTimeout(250);
const R = { panelLine: await p.$eval('#invBody .inv-xh', e => e.getAttribute('visibility')), panelDate: await p.$eval('#invBody .rp-invdate', e => e.hidden ? 'hidden' : e.textContent),
  chartTip: await p.$eval('#flowTip', e => e.innerText.slice(0, 30)) };
await p.mouse.move(r.x - 300, r.y); await p.waitForTimeout(200);
R.afterLeave = await p.$eval('#invBody .inv-xh', e => e.getAttribute('visibility'));
const w = await p.$('.pw-chart svg'); if (w) { const q = await w.boundingBox(); await p.mouse.move(q.x + q.width * .5, q.y + q.height * .5); await p.waitForTimeout(250);
  R.windowLine = await p.$eval('.pw-chart .inv-xh', e => e.getAttribute('visibility')); } else R.windowLine = 'no window';
await p.screenshot({ path:'shots/invhover.png' });
R.errors = errs; console.log(JSON.stringify(R)); await b.close();
