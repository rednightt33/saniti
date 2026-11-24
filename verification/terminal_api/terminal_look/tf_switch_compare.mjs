// The old path (store the timeframe and reload, as the click did before) against the new one (the click, in place), in
// one build, with a network delay per request (CDP latency). Time from the action to the candles drawn and to the
// Flow Timeline's whole history; 3 rounds each way, median.
import { serve } from './serve.mjs';
import { createRequire } from 'node:module';
const { chromium } = createRequire(process.env.PLAYWRIGHT_MODULE_DIR ? process.env.PLAYWRIGHT_MODULE_DIR + '/' : import.meta.url)('playwright');
const LAT = +(process.argv[3] || 150);
const { origin, close } = await serve(process.argv[2], 'BBRI');
const b = await chromium.launch();
const p = await b.newPage({ viewport:{ width:1440, height:900 } });
await p.addInitScript(() => { if (!sessionStorage.getItem('s')) { sessionStorage.setItem('s', '1'); localStorage.setItem('ml.symbol', 'BBRI'); localStorage.setItem('ml.tf', 'D') } });
const cdp = await p.context().newCDPSession(p);
await cdp.send('Network.enable');
await cdp.send('Network.emulateNetworkConditions', { offline:false, latency:LAT, downloadThroughput:5e6 / 8 * 8, uploadThroughput:2e6 / 8 * 8 });
await p.goto(origin + '/terminal-app/');
await p.waitForFunction(() => window.__flowAll === true, null, { timeout:90000 }); await p.waitForTimeout(800);
const poll = async (fn, ms = 90000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await p.evaluate(fn).catch(() => false)) return; await p.waitForTimeout(15) } throw new Error('timeout') };
const med = a => [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)];
const R = { reload:{ drawn:[], flow:[] }, inplace:{ drawn:[], flow:[] } };
for (let round = 0; round < 3; round++) for (const tf of ['15m', 'D']) {
  // old path
  let t0 = Date.now();
  await p.evaluate(t => { localStorage.setItem('ml.tf', t); location.reload() }, tf);
  await p.waitForLoadState('domcontentloaded');
  await poll(() => performance.getEntriesByName('terminal:chart drawn').length > 0); R.reload.drawn.push(Date.now() - t0);
  await poll(() => window.__flowAll === true); R.reload.flow.push(Date.now() - t0);
  await p.waitForTimeout(500);
  // new path: back to the other timeframe by the click, then to this one by the click
  const other = tf === 'D' ? '15m' : 'D';
  await p.evaluate(() => { performance.clearMarks(); window.__flowAll = false });
  await p.click(`#timeframeGroup button[data-timeframe="${other}"]`);
  await poll(() => performance.getEntriesByName('terminal:timeframe drawn').length > 0); await poll(() => window.__flowAll === true); await p.waitForTimeout(500);
  await p.evaluate(() => { performance.clearMarks(); window.__flowAll = false });
  t0 = Date.now();
  await p.click(`#timeframeGroup button[data-timeframe="${tf}"]`);
  await poll(() => performance.getEntriesByName('terminal:timeframe drawn').length > 0); R.inplace.drawn.push(Date.now() - t0);
  await poll(() => window.__flowAll === true); R.inplace.flow.push(Date.now() - t0);
  await p.waitForTimeout(500);
}
console.log(JSON.stringify({ latency_ms:LAT, reload:{ drawn_median:med(R.reload.drawn), flow_median:med(R.reload.flow), drawn:R.reload.drawn, flow:R.reload.flow },
  inplace:{ drawn_median:med(R.inplace.drawn), flow_median:med(R.inplace.flow), drawn:R.inplace.drawn, flow:R.inplace.flow } }));
await b.close(); close();
