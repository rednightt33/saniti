// pixel colours of the Domestic and Foreign parts of Top brokers bars (panel and window)
import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const b = await chromium.launch(); const p = await b.newPage({ viewport:{ width:1600, height:960 } });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.addInitScript(() => { localStorage.clear(); localStorage.setItem('ml.symbol','MAPI'); localStorage.setItem('ml.broker.collapsed','0'); localStorage.setItem('ml.win.open', JSON.stringify(['acc'])) });
await p.goto('http://127.0.0.1:18901/terminal-app/'); await p.waitForSelector('#chart canvas'); await p.waitForTimeout(4500);
const out = {};
for (const [name, sel] of [['panel', '#accBody'], ['window', '.pw-acc']]) {
  const parts = await p.$$eval(`${sel} .fill.split i`, is => is.map(i => { const r = i.getBoundingClientRect(); return { k:i.className, x:r.x + r.width / 2, y:r.y + r.height / 2, w:r.width, side:i.closest('.trk').classList.contains('buy') ? 'buy' : 'sell' } }).filter(q => q.w >= 3));
  const shot = await p.screenshot();
  const pick = async (q) => p.evaluate(async ([png, x, y]) => { const img = new Image(); img.src = 'data:image/png;base64,' + png; await img.decode(); const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; const g = c.getContext('2d'); g.drawImage(img, 0, 0); return [...g.getImageData(Math.round(x), Math.round(y), 1, 1).data].slice(0, 3).join(',') }, [shot.toString('base64'), q.x, q.y]);
  const seen = {};
  for (const q of parts) { const key = q.side + ' ' + q.k; if (!seen[key]) seen[key] = await pick(q) }
  out[name] = seen;
}
console.log(JSON.stringify({ ...out, errors:errs })); await b.close();
