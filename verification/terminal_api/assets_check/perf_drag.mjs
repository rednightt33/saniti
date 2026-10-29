// drag (pan) the main chart: frame intervals and long tasks, per scenario
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const b = await chromium.launch();
async function run(port, label, store) {
  const p = await b.newPage({ viewport:{ width:1600, height:960 } });
  await p.addInitScript(s => { localStorage.clear(); for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v) }, { 'ml.symbol':'MAPI', ...store });
  await p.goto(`http://127.0.0.1:${port}/terminal-app/`); await p.waitForSelector('#chart canvas'); await p.waitForTimeout(12000);
  await p.evaluate(() => {
    const w = window; w.__lt = []; w.__fr = [];
    new PerformanceObserver(l => l.getEntries().forEach(e => w.__lt.push(e.duration))).observe({ type:'longtask' });
    let last = performance.now(); const tick = t => { w.__fr.push(t - last); last = t; if (w.__on) requestAnimationFrame(tick) }; w.__on = true; requestAnimationFrame(tick);
  });
  const cdp = store.__prof ? await p.context().newCDPSession(p) : null;
  if (cdp) { await cdp.send('Profiler.enable'); await cdp.send('Profiler.setSamplingInterval', { interval:200 }); await cdp.send('Profiler.start') }
  const r = await p.$eval('#chart', e => e.getBoundingClientRect().toJSON());
  await p.mouse.move(r.x + r.width * .7, r.y + r.height * .5); await p.mouse.down();
  const t0 = Date.now();
  for (let k = 0; k < 80; k++) await p.mouse.move(r.x + r.width * (.7 - .4 * Math.sin(k / 80 * Math.PI)), r.y + r.height * .5);
  const ms = Date.now() - t0; await p.mouse.up(); await p.waitForTimeout(300);
  const m = await p.evaluate(() => { const w = window; w.__on = false; const f = w.__fr.slice(2).sort((a, b) => a - b);
    return { frames:f.length, p50:+f[Math.floor(f.length * .5)].toFixed(1), p95:+f[Math.floor(f.length * .95)].toFixed(1), max:+f.at(-1).toFixed(1), longtasks:w.__lt.length, longMs:Math.round(w.__lt.reduce((a, b) => a + b, 0)) } });
  if (cdp) {
    const { profile } = await cdp.send('Profiler.stop'), self = new Map(), dt = profile.timeDeltas, idOf = new Map(profile.nodes.map(n => [n.id, n]));
    const cnt = new Map(); profile.samples.forEach((id, k) => cnt.set(id, (cnt.get(id) || 0) + (dt[k] || 0)));
    for (const [id, us] of cnt) { const n = idOf.get(id), f = n.callFrame, key = `${f.functionName || '(anon)'} ${f.url.split('/').pop()}:${f.lineNumber}`; self.set(key, (self.get(key) || 0) + us) }
    console.log([...self].sort((a, b) => b[1] - a[1]).slice(0, 14).map(([k, us]) => `   ${(us / 1000).toFixed(0).padStart(5)} ms  ${k}`).join('\n'));
  }
  console.log(label.padEnd(44), JSON.stringify({ dragMs:ms, ...m })); await p.close();
}
const assets = JSON.stringify([{ ticker:'BBCA', opts:{} }, { ticker:'BBRI', opts:{} }]);
const [OLD, NEW] = [18904, 18903];
await run(OLD, 'BIG old build (before assets), panel open', { 'ml.broker.collapsed':'0' });
await run(NEW, 'BIG fixed, panel closed', {});
await run(NEW, 'BIG fixed, panel open', { 'ml.broker.collapsed':'0' });
await run(NEW, 'BIG fixed, panel open, 2 assets', { 'ml.broker.collapsed':'0', 'ml.assets.v1':assets });
await run(NEW, 'BIG fixed, panel open, 2 assets (repeat)', { 'ml.broker.collapsed':'0', 'ml.assets.v1':assets });
await b.close();
