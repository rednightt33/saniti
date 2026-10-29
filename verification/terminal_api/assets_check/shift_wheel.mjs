import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
const b = await chromium.launch(); const p = await b.newPage({ viewport:{ width:1600, height:960 } });
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.addInitScript(() => { localStorage.clear(); localStorage.setItem('ml.symbol','MAPI') });
await p.goto('http://127.0.0.1:18901/terminal-app/'); await p.waitForSelector('#chart canvas'); await p.waitForTimeout(4000);
const tot = () => p.$eval('#flowSummary', e => e.innerText.replace(/\s+/g, ' ').match(/Period net total (\S+ \S+)/)[1]);
const labels = () => p.$$eval('#chart table tr:last-child canvas', c => c.length);
const c = await p.$eval('#chart', e => e.getBoundingClientRect().toJSON());
await p.mouse.move(c.x + c.width * .5, c.y + c.height * .5);
// drag left to have room on the right, so a shift-scroll can move both ways
await p.mouse.down(); await p.mouse.move(c.x + c.width * .8, c.y + c.height * .5, { steps:10 }); await p.mouse.up(); await p.waitForTimeout(300);
const s0 = await tot(); const shot0 = await p.screenshot({ clip:{ x:c.x, y:c.y + c.height - 30, width:c.width, height:28 } });
await p.keyboard.down('Shift'); for (let k = 0; k < 3; k++) { await p.mouse.wheel(0, 120); await p.waitForTimeout(80) } await p.keyboard.up('Shift'); await p.waitForTimeout(400);
const s1 = await tot(); const shot1 = await p.screenshot({ clip:{ x:c.x, y:c.y + c.height - 30, width:c.width, height:28 } });
await p.keyboard.down('Shift'); for (let k = 0; k < 3; k++) { await p.mouse.wheel(0, -120); await p.waitForTimeout(80) } await p.keyboard.up('Shift'); await p.waitForTimeout(400);
const s2 = await tot();
// plain wheel still zooms
await p.mouse.wheel(0, -240); await p.waitForTimeout(400); const s3 = await tot();
console.log(JSON.stringify({ periodTotal:{ start:s0, afterShiftDown:s1, afterShiftUp:s2, afterPlainWheel:s3 }, timeAxisChanged:!shot0.equals(shot1), errors:errs }));
await b.close();
