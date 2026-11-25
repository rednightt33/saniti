// EXEC-TERMINAL-SESSION-TOGGLE item 2: the page built again in place must equal a fresh load: listeners on window and
// document (CDP DOMDebugger), chart canvases, legend rows, and the controls answer once. Run on the local harness.
// ERRORS M563 re-check: also the state the page puts on <html> and <body> (their attributes: full screen's ml-full, the
// indicator filters' ind-filters-off, ind-narrow, the axis widths, the embedding's edge-rail): each case sets one, switches
// the timeframe in place and compares the page with a reload of the same stored state (`htmlCases`, exit 1 on a
// difference). Usage: node tf_switch_parity.mjs DATA [ml.ind.v1 JSON] (TERMINAL_BUILD for another build folder).
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
    charts:await p.evaluate(() => document.querySelectorAll('.tv-lightweight-charts').length), attrs:await attrs(p) };
}
/* <html>'s and <body>'s attributes (class, style with the axis widths, lang ...) */
const attrs = f => f.evaluate(() => ({ html:[...document.documentElement.attributes].map(a => `${a.name}=${a.value}`).sort(),
  body:[...document.body.attributes].map(a => `${a.name}=${a.value}`).sort() }));
/* what those states show: full screen's button and what it hides, the side panels, the indicator filters */
const shows = f => f.evaluate(() => ({ full:document.getElementById('fullBtn')?.getAttribute('aria-pressed') ?? null,
  flow:!!document.getElementById('flowPanel')?.offsetHeight, foot:!!document.querySelector('.foot')?.offsetHeight,
  ws:document.getElementById('workspace')?.className, filters:document.querySelector('[data-label$="indicator filters"]')?.getAttribute('aria-pressed') ?? null }));
const drawnOnce = (f, n) => f.waitForFunction(n => performance.getEntriesByName('terminal:timeframe drawn').length > n, n, { timeout:60000 });
const flowIn = f => f.waitForFunction(() => window.__flowAll === true, null, { timeout:60000 });
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
/* ERRORS M563 re-check: one state on <html> per case, a switch in place, then a reload of the same stored state */
const htmlCases = {}, bad = [];
async function htmlCase(name, extra, act, tf = '1h') {
  const { p, errs } = await page({ ...seed, ...extra });
  await act(p); await p.waitForTimeout(300);
  const set = { ...(await attrs(p)), ...(await shows(p)) };
  const n = await p.evaluate(() => performance.getEntriesByName('terminal:timeframe drawn').length);
  await p.click(`#timeframeGroup button[data-timeframe="${tf}"]`); await drawnOnce(p, n); await flowIn(p); await p.waitForTimeout(800);
  const switched = { ...(await attrs(p)), ...(await shows(p)) };
  await p.reload(); await flowIn(p); await p.waitForTimeout(800);
  const reloaded = { ...(await attrs(p)), ...(await shows(p)) };
  const same = JSON.stringify(switched) === JSON.stringify(reloaded);
  htmlCases[name] = { set, switched, ...(same ? {} : { reloaded }), same, errs:errs.slice(0, 5) };
  if (!same) bad.push(name);
  await p.close();
}
const OPEN = { 'ml.stats.collapsed':'0', 'ml.broker.collapsed':'0' };
await htmlCase('full screen on', OPEN, p => p.click('#fullBtn'));
await htmlCase('full screen on, then off', OPEN, async p => { await p.click('#fullBtn'); await p.waitForTimeout(200); await p.click('#fullBtn') }, 'W');
await htmlCase('indicator filters hidden', {}, p => p.click('[data-label="Hide indicator filters"]'));
await htmlCase('chart narrowed (both side panels opened)', {}, async p => { await p.click('#statsExpand').catch(() => {}); await p.click('#rpExpand').catch(() => {}) });
/* inside EDGE: its frame (edge-app.js: src /terminal-app/?in=edge; hello at the frame's load and every second until the
   Terminal answers with its Statistics state). The switch keeps edge-rail and the Terminal tells EDGE its Statistics
   state again (EDGE's Statistics button stays in step), as after a reload of the frame. With EDGE's hello alone (no
   ?in=edge) the class is carried over the switch; a reload of such a frame keeps it only if a hello comes after the
   Terminal listens (EDGE stops after the first answer), so that variant is not compared with a reload. */
async function edgeCase(name, src, compare) {
  const p = await b.newPage({ viewport:{ width:1440, height:900 } }), errs = [];
  p.on('pageerror', e => errs.push(String(e)));
  await p.addInitScript(s => { if (!sessionStorage.getItem('seeded')) { sessionStorage.setItem('seeded', '1'); for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v) } }, seed);
  await p.route(origin + '/edge-host/', r => r.fulfill({ contentType:'text/html', body:`<!doctype html><body style="margin:0">
    <iframe class="terminal-frame" src="${src}" style="width:1400px;height:860px;border:0"></iframe><script>
    const f = document.querySelector('iframe'); let again = 0; window.__answers = 0;
    const hello = () => f.contentWindow && f.contentWindow.postMessage({ source:'edge', type:'rail' }, location.origin);
    addEventListener('message', e => { if (e.source === f.contentWindow && e.data && e.data.source === 'terminal' && e.data.type === 'stats') { clearInterval(again); window.__answers++ } });
    f.addEventListener('load', hello); hello(); again = setInterval(hello, 1000);</script></body>` }));
  await p.goto(origin + '/edge-host/');
  const fr = () => p.frames().find(x => x.url().includes('/terminal-app/'));
  await p.waitForFunction(() => window.__answers > 0, null, { timeout:60000 }); await flowIn(fr()); await p.waitForTimeout(600);
  const set = { ...(await attrs(fr())), ...(await shows(fr())) }, told = await p.evaluate(() => window.__answers);
  const n = await fr().evaluate(() => performance.getEntriesByName('terminal:timeframe drawn').length);
  await fr().click('#timeframeGroup button[data-timeframe="W"]'); await drawnOnce(fr(), n); await flowIn(fr()); await p.waitForTimeout(1500);
  const switched = { ...(await attrs(fr())), ...(await shows(fr())) }, toldAgain = await p.evaluate(t => window.__answers > t, told);
  await fr().evaluate(() => location.reload()); await p.waitForTimeout(500); await flowIn(fr()); await p.waitForTimeout(1500);
  const reloaded = { ...(await attrs(fr())), ...(await shows(fr())) };
  const rail = switched.html.some(a => /^class=.*\bedge-rail\b/.test(a));
  const same = rail && toldAgain && (!compare || JSON.stringify(switched) === JSON.stringify(reloaded));
  htmlCases[name] = { set, switched, reloaded, rail, toldAgain, compared:compare, same, errs:errs.slice(0, 5) };
  if (!same) bad.push(name);
  await p.close();
}
await edgeCase('inside EDGE', '/terminal-app/?in=edge', true);
await edgeCase('inside EDGE, its hello alone', '/terminal-app/', false);
const attrsSame = JSON.stringify(fresh.attrs) === JSON.stringify(after.attrs);
if (!attrsSame) bad.push('six switches: <html>/<body> attributes differ from a fresh load');
console.log(JSON.stringify({ times, fresh, after, attrsSame, freshCtl, afterCtl, pillOff, pillKept, htmlCases, bad, errsFresh:A.errs.slice(0, 5), errsSwitched:B.errs.slice(0, 8) }, null, 1));
await b.close(); close();
if (bad.length) { console.error('tf_switch_parity: differs from a reload:', bad.join('; ')); process.exit(1) }
