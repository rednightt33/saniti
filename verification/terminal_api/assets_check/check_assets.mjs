// Browser check of EXEC-TERMINAL-ASSETS against mock_server.py. Usage: node check_assets.mjs <port> <out dir>
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const [port, out] = [process.argv[2], process.argv[3]];
const url = `http://127.0.0.1:${port}/terminal-app/`;
const b = await chromium.launch();
const page = await b.newPage({ viewport:{ width:1600, height:960 } });
const errs = [];
page.on('pageerror', e => errs.push('pageerror: ' + e.message));
page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()) });
await page.addInitScript(() => { if (!sessionStorage.getItem('init')) { localStorage.clear(); localStorage.setItem('ml.symbol', 'MAPI'); sessionStorage.setItem('init', '1') } });
const R = {};
const step = async (name, fn) => { try { R[name] = await fn() } catch (e) { R[name] = 'FAIL ' + e.message.split('\n')[0] } };
const shot = n => page.screenshot({ path:`${out}/${n}.png` });
await page.goto(url); await page.waitForSelector('#chart canvas'); await page.waitForTimeout(1500);

const addAsset = async t => {
  await page.click('#toggleAddPanel'); await page.waitForSelector('.gp-dialog');
  const label = await page.textContent('.gp-label');
  await page.keyboard.type(t); await page.keyboard.press('Enter'); await page.waitForTimeout(1200);
  return label;
};
await step('add panel stays closed, search opens', async () => { const l = await addAsset('BBCA'); return { label:l, addPanelOpen:await page.$eval('#addPanel', e => e.classList.contains('open')) } });
await step('legend after BBCA', () => page.$$eval('.as-row', rs => rs.map(r => r.innerText.replace(/\s+/g, ' '))));
await step('panes after BBCA', () => page.$$eval('.bottom.af', s => s.map(x => x.getAttribute('aria-label'))));
await page.waitForTimeout(1500);
await step('BBCA pane summary', () => page.$eval('.bottom.af .flow-summary', e => e.innerText.replace(/\s+/g, ' ')));
await step('main flow badge', () => page.$eval('#flowHead .af-badge', e => e.innerText));
await step('search tags', async () => { await page.click('#toggleAddPanel'); await page.keyboard.type('B'); await page.waitForTimeout(200);
  const tags = await page.$$eval('.gp-row', rs => rs.map(r => r.querySelector('.gp-ticker').innerText.replace(/\s+/g, ' ')));
  await page.keyboard.press('Escape'); return tags });
await addAsset('BBRI'); await page.waitForTimeout(1500);
await step('two assets, + full', async () => ({ rows:await page.$$eval('.as-row .as-name', r => r.map(x => x.textContent)), full:await page.$eval('#toggleAddPanel', e => e.getAttribute('aria-disabled')), title:await page.$eval('#toggleAddPanel', e => e.title) }));
await step('+ when full opens nothing', async () => { await page.click('#toggleAddPanel', { force:true }); await page.waitForTimeout(200); return !!(await page.$('.gp-dialog')) });
await step('scales', () => page.evaluate(() => JSON.parse(localStorage.getItem('ml.assets.v1')).map(a => a.ticker + ':' + a.opts.scale + ':' + a.opts.color)));
await shot('1-two-assets');

// hover the chart: legend values and the asset panes follow
await step('hover', async () => { const box = await page.$eval('#chart', e => { const r = e.getBoundingClientRect(); return { x:r.x + r.width * .6, y:r.y + r.height * .5 } });
  await page.mouse.move(box.x, box.y); await page.waitForTimeout(300);
  return { legend:await page.$$eval('.as-row .as-chg', r => r.map(x => x.textContent)), tips:await page.$$eval('.af-tip', r => r.map(x => x.innerText.replace(/\s+/g, ' '))) } });
await shot('2-hover');
// hover an asset pane: the main chart's tooltip follows
await step('hover asset pane', async () => { const box = await page.$eval('.bottom.af .af-chart', e => { const r = e.getBoundingClientRect(); return { x:r.x + r.width * .4, y:r.y + r.height * .5 } });
  await page.mouse.move(box.x, box.y); await page.waitForTimeout(300); return page.$eval('#flowTip', e => e.innerText.replace(/\s+/g, ' ')) });

// settings dialog
await step('settings', async () => {
  await page.hover('.as-row'); await page.click('.as-row [data-act="cfg"]'); await page.waitForSelector('.idlg-back:not([hidden]) .idlg');
  const head = await page.textContent('.idlg-back:not([hidden]) h2');
  const tabs = await page.$$eval('.idlg-back:not([hidden]) [data-tab]', t => t.map(x => x.textContent));
  await page.click('.idlg-back:not([hidden]) [data-tab="Style"]');
  const labels = await page.$$eval('.idlg-back:not([hidden]) .idlg-row span:first-child', t => t.map(x => x.textContent));
  await page.screenshot({ path:`${out}/3-style.png` });
  await page.selectOption('.idlg-back:not([hidden]) .idlg-row:nth-child(1) select', 'area'); await page.waitForTimeout(300);
  const srcDisabledForCandles = await (async () => { await page.selectOption('.idlg-back:not([hidden]) .idlg-row:nth-child(1) select', 'candles'); await page.waitForTimeout(200);
    return page.$eval('.idlg-back:not([hidden]) .idlg-row:nth-child(2) select', s => s.disabled) })();
  await page.click('.idlg-back:not([hidden]) [data-tab="Visibility"]');
  await page.click('.idlg-back:not([hidden]) .idlg-row:nth-child(2) .toggle'); await page.waitForTimeout(300);
  const panesWhileOff = await page.$$eval('.bottom.af', s => s.map(x => x.getAttribute('aria-label')));
  await page.screenshot({ path:`${out}/4-visibility.png` });
  await page.click('.idlg-back:not([hidden]) [data-act="cancel"]'); await page.waitForTimeout(500);
  const panesAfterCancel = await page.$$eval('.bottom.af', s => s.map(x => x.getAttribute('aria-label')));
  const style = await page.evaluate(() => JSON.parse(localStorage.getItem('ml.assets.v1'))[0].opts.style);
  return { head, tabs, labels, srcDisabledForCandles, panesWhileOff, panesAfterCancel, styleAfterCancel:style };
});
await step('settings ok keeps area', async () => {
  await page.hover('.as-row'); await page.click('.as-row [data-act="cfg"]'); await page.click('.idlg-back:not([hidden]) [data-tab="Style"]');
  await page.selectOption('.idlg-back:not([hidden]) .idlg-row:nth-child(1) select', 'area');
  await page.click('.idlg-back:not([hidden]) [data-act="ok"]'); await page.waitForTimeout(300);
  return page.evaluate(() => JSON.parse(localStorage.getItem('ml.assets.v1'))[0].opts.style);
});
await step('return mode legend', async () => { await page.click('#modeGroup [data-mode="return"]'); await page.waitForTimeout(400);
  const v = await page.$$eval('.as-row .as-chg', r => r.map(x => x.textContent + ' (' + x.title + ')')); await page.click('#modeGroup [data-mode="price"]'); return v });

// drawing: Brush on the BBCA pane, Text on the chart's own Flow
const drag = async (sel, fx0, fx1) => { const r = await page.$eval(sel, e => { const b = e.getBoundingClientRect(); return { x:b.x, y:b.y, w:b.width, h:b.height } });
  await page.mouse.move(r.x + r.w * fx0, r.y + r.h * .5); await page.mouse.down();
  for (let k = 1; k <= 12; k++) await page.mouse.move(r.x + r.w * (fx0 + (fx1 - fx0) * k / 12), r.y + r.h * (.5 + .2 * Math.sin(k)));
  await page.mouse.up(); await page.waitForTimeout(300) };
await step('brush on asset pane', async () => {
  await page.click('.dr-btn[data-tool="brush"]');
  await drag('.bottom.af .af-chart', .4, .6);
  return page.evaluate(() => JSON.parse(localStorage.getItem('ml.drawings.flow.BBCA') || '[]').map(d => d.type || d.kind));
});
await step('brush on main flow', async () => {
  await page.click('.dr-btn[data-tool="brush"]');
  await drag('#flowChart', .3, .5);
  return page.evaluate(() => JSON.parse(localStorage.getItem('ml.drawings.flow.MAPI') || '[]').map(d => d.type || d.kind));
});
await step('text on main flow', async () => {
  await page.click('.dr-btn[data-tool="text"]');
  const r = await page.$eval('#flowChart', e => { const b = e.getBoundingClientRect(); return { x:b.x + b.width * .7, y:b.y + b.height * .6 } });
  await page.mouse.click(r.x, r.y); await page.waitForTimeout(300);
  const editorShown = await page.$$eval('.flow-wrap .dr-text', es => es.some(e => !e.hidden));
  await page.keyboard.type('akumulasi'); await page.keyboard.press('Enter'); await page.waitForTimeout(300);
  return { editorShown, saved:await page.evaluate(() => JSON.parse(localStorage.getItem('ml.drawings.flow.MAPI') || '[]').map(d => (d.type || d.kind) + (d.text ? ':' + d.text : ''))) };
});
await step('undo', async () => { await page.keyboard.press('Control+z'); await page.waitForTimeout(300);
  return page.evaluate(() => JSON.parse(localStorage.getItem('ml.drawings.flow.MAPI') || '[]').length) });
await shot('5-drawings');

// collapse a pane, remove BBRI
await step('collapse BBCA pane', async () => { await page.click('.bottom.af .flow-collapse'); await page.waitForTimeout(400);
  return page.$eval('.bottom.af', e => Math.round(e.getBoundingClientRect().height)) });
await step('remove BBRI', async () => { const rows = await page.$$('.as-row'); await rows[1].hover(); await (await rows[1].$('[data-act="del"]')).click(); await page.waitForTimeout(300);
  return { rows:await page.$$eval('.as-row .as-name', r => r.map(x => x.textContent)), panes:await page.$$eval('.bottom.af', s => s.length), plusFull:await page.$eval('#toggleAddPanel', e => e.getAttribute('aria-disabled')) } });
await step('layout heights', () => page.evaluate(() => {
  const h = s => Math.round(document.querySelector(s).getBoundingClientRect().height);
  return { mainCol:h('.main-col'), chart:h('.chart-wrap'), flow:h('#flowPanel'), panes:[...document.querySelectorAll('.bottom.af')].map(e => Math.round(e.getBoundingClientRect().height)) } }));
await step('reload restores', async () => { await page.reload(); await page.waitForSelector('#chart canvas'); await page.waitForTimeout(2500);
  return { rows:await page.$$eval('.as-row .as-name', r => r.map(x => x.textContent)), panes:await page.$$eval('.bottom.af', s => s.map(x => x.getAttribute('aria-label') + (x.classList.contains('collapsed') ? ' (collapsed)' : ''))), style:await page.evaluate(() => JSON.parse(localStorage.getItem('ml.assets.v1'))[0].opts.style) } });
await shot('6-reloaded');
await step('axis alignment', () => page.evaluate(() => {
  const plot = el => { const c = [...el.querySelectorAll('canvas')]; return c.length ? Math.round(el.getBoundingClientRect().width) : 0 };
  const lefts = ['#chart', '#flowChart', ...[...document.querySelectorAll('.af-chart')].map((_, k) => `.bottom.af:nth-of-type(${k + 1}) .af-chart`)];
  return [...document.querySelectorAll('#chart table td:first-child, #flowChart table td:first-child, .af-chart table td:first-child')].map(td => Math.round(td.getBoundingClientRect().width));
}));
R.errors = errs;
console.log(JSON.stringify(R, null, 1));
await b.close();
