import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const b = await chromium.launch(); const page = await b.newPage({ viewport:{ width:1440, height:860 } });
const errs = []; page.on('pageerror', e => errs.push(e.message)); page.on('console', m => { if (m.type() === 'error') errs.push(m.text()) });
await page.addInitScript(() => { if (!sessionStorage.getItem('i')) { localStorage.clear(); localStorage.setItem('ml.symbol','MAPI'); localStorage.setItem('ml.tf','W');
  localStorage.setItem('ml.assets.v1', JSON.stringify([{ticker:'IHSG',opts:{}},{ticker:'BBCA',opts:{}}])); sessionStorage.setItem('i','1') } });
await page.goto('http://127.0.0.1:18901/terminal-app/'); await page.waitForSelector('#chart canvas'); await page.waitForTimeout(3500);
const R = {};
R.weekly = await page.$$eval('.bottom.af', s => s.map(x => x.getAttribute('aria-label') + ' | ' + x.querySelector('.flow-note').innerText + ' | ' + x.querySelector('.flow-summary').innerText.replace(/\s+/g, ' ')));
R.legend = await page.$$eval('.as-row', r => r.map(x => x.innerText.replace(/\s+/g, ' ')));
const c = await page.$eval('#chart', e => e.getBoundingClientRect().toJSON());
await page.mouse.move(c.x + c.width * .7, c.y + c.height * .5); await page.waitForTimeout(300);
R.weeklyTip = [await page.$eval('#flowTip', e => e.innerText.replace(/\s+/g, ' ')), ...(await page.$$eval('.af-tip', t => t.map(x => x.innerText.replace(/\s+/g, ' '))))];
await page.screenshot({ path:'shots/w-1.png' });
// Inputs → Symbol: IHSG → GOTO (keeps slot 0 and its settings)
await page.hover('.as-row'); await page.click('.as-row [data-act="cfg"]'); await page.click('.idlg-back:not([hidden]) .as-sym');
await page.keyboard.type('GOTO'); await page.keyboard.press('Enter'); await page.waitForTimeout(2500);
R.replaced = { rows:await page.$$eval('.as-row .as-name', r => r.map(x => x.textContent)), dialogHidden:await page.$eval('.idlg-back:last-of-type', e => e.hidden), saved:await page.evaluate(() => JSON.parse(localStorage.getItem('ml.assets.v1')).map(a => a.ticker + ':' + a.opts.color + ':' + a.opts.scale)) };
// right-click on an asset pane, after a trend line drawn there with Alt+T routed from the chart
await page.mouse.move(c.x + c.width * .5, c.y + c.height * .5); await page.keyboard.press('Alt+t');
const p = await page.$eval('.bottom.af .af-chart', e => e.getBoundingClientRect().toJSON());
await page.mouse.move(p.x + p.width * .3, p.y + p.height * .6); await page.mouse.down(); await page.mouse.move(p.x + p.width * .6, p.y + p.height * .3, { steps:8 }); await page.mouse.up(); await page.waitForTimeout(300);
R.trendOnPane = await page.evaluate(() => JSON.parse(localStorage.getItem('ml.drawings.flow.GOTO') || '[]').map(d => d.type || d.kind));
await page.mouse.click(p.x + p.width * .8, p.y + p.height * .5, { button:'right' }); await page.waitForTimeout(200);
R.paneMenu = await page.$$eval('.bottom.af .dr-menu:not([hidden]) .dr-mi', m => m.map(x => x.innerText.trim()));
await page.keyboard.press('Escape'); await page.mouse.click(5, 300);
// fold the chart's own Flow Timeline: the asset panes stay open
await page.click('#flowCollapse'); await page.waitForTimeout(500);
R.mainFolded = await page.evaluate(() => ({ main:Math.round(document.querySelector('#flowPanel').getBoundingClientRect().height), panes:[...document.querySelectorAll('.bottom.af')].map(e => [Math.round(e.getBoundingClientRect().height), getComputedStyle(e.querySelector('.flow-wrap')).display]), chart:Math.round(document.querySelector('.chart-wrap').getBoundingClientRect().height) }));
await page.screenshot({ path:'shots/w-2.png' });
await page.click('#flowCollapse'); await page.waitForTimeout(500);
R.heights = await page.evaluate(() => ({ col:Math.round(document.querySelector('.main-col').getBoundingClientRect().height), chart:Math.round(document.querySelector('.chart-wrap').getBoundingClientRect().height), flow:Math.round(document.querySelector('#flowPanel').getBoundingClientRect().height), panes:[...document.querySelectorAll('.bottom.af')].map(e => Math.round(e.getBoundingClientRect().height)) }));
R.errors = errs; console.log(JSON.stringify(R, null, 1)); await b.close();
