// EXEC-TERMINAL-SESSION-TOGGLE item 2: the page built again in place must equal a fresh load: listeners on window and
// document (CDP DOMDebugger), chart canvases, legend rows, and the controls answer once. Run on the local harness.
import { serve } from './serve.mjs';
import { createRequire } from 'node:module';
const { chromium } = createRequire(process.env.PLAYWRIGHT_MODULE_DIR ? process.env.PLAYWRIGHT_MODULE_DIR + '/' : import.meta.url)('playwright');
const DATA = process.argv[2];
const { origin, close } = await serve(DATA, 'BBRI');
const b = await chromium.launch();
async function page(seed) {
  const p = await b.newPage({ viewport:{ width:1440, height:900 } }); const errs = [];
  p.on('pageerror', e => errs.push(String(e))); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()) });
  await p.addInitScript(s => { if (!sessionStorage.getItem('seeded')) { sessionStorage.setItem('seeded', '1'); for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v) } }, seed);
  await p.goto(origin + '/terminal-app/');
  await p.waitForFunction(() => window.__flowAll === true, null, { timeout:60000 }); await p.waitForTimeout(600);
  return { p, errs };
}
async function census(p) {
  const cdp = await p.context().newCDPSession(p);
  const count = async expr => { const { result } = await cdp.send('Runtime.evaluate', { expression:expr });
    const { listeners } = await cdp.send('DOMDebugger.getEventListeners', { objectId:result.objectId }); return listeners.length };
  return { win:await count('window'), doc:await count('document'), body:await count('document.body'),
    canvases:await p.evaluate(() => document.querySelectorAll('canvas').length), rows:await p.evaluate(() => document.querySelectorAll('.ind-row').length),
    charts:await p.evaluate(() => document.querySelectorAll('.tv-lightweight-charts').length) };
}
async function controls(p) {
  const r = {};
  await p.keyboard.press('Control+k'); await p.waitForTimeout(250);
  r.search = await p.evaluate(() => [...document.querySelectorAll('[role=dialog]')].filter(d => d.offsetWidth).length);
  await p.keyboard.press('Escape'); await p.waitForTimeout(200);
  r.searchClosed = await p.evaluate(() => [...document.querySelectorAll('[role=dialog]')].filter(d => d.offsetWidth).length);
  await p.click('#evBtn'); await p.waitForTimeout(200);
  r.events = await p.evaluate(() => !document.getElementById('evPop')?.hidden);
  await p.keyboard.press('Escape'); await p.waitForTimeout(150);
  r.eventsClosed = await p.evaluate(() => !!document.getElementById('evPop')?.hidden);
  await p.click('#indBtn'); await p.waitForTimeout(300);
  r.indicators = await p.evaluate(() => !document.getElementById('indPop')?.hidden || !!document.querySelector('.idlg-back, .im-body'));
  await p.keyboard.press('Escape'); await p.waitForTimeout(200);
  return r;
}
const seed = { 'ml.symbol':'BBRI', 'ml.tf':'D', ...(process.argv[3] ? { 'ml.ind.v1':process.argv[3] } : {}) };
// a fresh page at D
const A = await page(seed); const fresh = await census(A.p); const freshCtl = await controls(A.p);
// a page switched D -> 15m -> D -> 1h -> D -> 15m -> D in place
const B = await page(seed);
const times = [];
for (const tf of ['15m', 'D', '1h', 'D', '15m', 'D']) {
  await B.p.evaluate(() => { performance.clearMarks(); window.__flowAll = false });
  const t0 = Date.now();
  await B.p.click(`#timeframeGroup button[data-timeframe="${tf}"]`);
  try { await B.p.waitForFunction(() => performance.getEntriesByName('terminal:timeframe drawn').length || performance.getEntriesByName('terminal:chart drawn').length, null, { timeout:15000 }) }
  catch (e) { console.log('STUCK at', tf, await B.p.evaluate(() => ({ marks:performance.getEntriesByType('mark').map(m => m.name), active:document.querySelector('#timeframeGroup .active')?.dataset.timeframe, ring:!!document.querySelector('.ml-switch') })), B.errs.slice(0, 5)); throw e }
  const drawn = Date.now() - t0;
  await B.p.waitForFunction(() => window.__flowAll === true, null, { timeout:60000 });
  const flow = Date.now() - t0;
  const reloaded = await B.p.evaluate(() => performance.getEntriesByType('navigation').length && !performance.getEntriesByName('terminal:timeframe drawn').length);
  const pill = await B.p.evaluate(() => { const e = document.getElementById('sessionPill'); return e ? !!e.offsetWidth : false });
  times.push({ tf, drawn_ms:drawn, flow_ms:flow, in_place:!reloaded, pill });
  await B.p.waitForTimeout(400);
}
await B.p.waitForTimeout(600);
const after = await census(B.p); const afterCtl = await controls(B.p);
// the pill switch on 15m: off hides, kept in storage, on again
await B.p.click('#timeframeGroup button[data-timeframe="15m"]');
await B.p.waitForFunction(() => performance.getEntriesByName('terminal:timeframe drawn').length, null, { timeout:60000 }); await B.p.waitForTimeout(500);
await B.p.click('#sessionPill .toggle'); await B.p.waitForTimeout(200);
const pillOff = await B.p.evaluate(() => ({ checked:document.getElementById('tglSession').checked, stored:localStorage.getItem('ml.session.lines') }));
await B.p.click('#timeframeGroup button[data-timeframe="1h"]');
await B.p.waitForFunction(() => document.getElementById('sessionPill') && performance.getEntriesByName('terminal:timeframe drawn').length, null, { timeout:60000 }); await B.p.waitForTimeout(500);
const pillKept = await B.p.evaluate(() => document.getElementById('tglSession').checked);
console.log(JSON.stringify({ times, fresh, after, freshCtl, afterCtl, pillOff, pillKept, errsFresh:A.errs.slice(0, 5), errsSwitched:B.errs.slice(0, 8) }, null, 1));
await b.close(); close();
