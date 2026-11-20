// The live smoke in a browser (EXEC option A; LIVE_PROMOTION.md step 8): the page as a visitor sees it (the rail, the
// Monitor absent, no model list asked, the console). Playwright is preinstalled.
// Usage: node verification/edge_multiuser/live_smoke/browser_smoke.cjs <origin> <png> [start path, e.g. /terminal]
const { chromium } = require('playwright');
(async () => {
const [origin, png, start = '/'] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 })).newPage();
const errors = [], asked = [], failed = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)); });
page.on('pageerror', e => errors.push('pageerror: ' + String(e).slice(0, 200)));
page.on('request', r => asked.push(r.url()));
page.on('response', r => { if (r.status() >= 400) failed.push(`${r.status()} ${r.url().replace(origin, '')}`); });
await page.goto(origin + start, { waitUntil: 'networkidle', timeout: 60000 });
const landed = page.url().replace(origin, '');
let railShown = true;
try { await page.locator('.side-nav').first().waitFor({ timeout: 30000 }); } catch { railShown = false; }
await page.waitForTimeout(4000);
const rail = (await page.locator('.side-nav button, .side-nav a, .topbar button').evaluateAll(ns => ns.map(n =>
  n.getAttribute('aria-label') || n.getAttribute('data-tip') || n.innerText || ''))).map(s => s.trim()).filter(Boolean);
const text = await page.locator('body').innerText();
await page.screenshot({ path: png });
console.log(JSON.stringify({
  landed, title: await page.title(), rail_shown: railShown, rail,
  monitor_in_rail: rail.some(n => n.includes('Monitor') || n === 'Research'),
  shows_bbca: text.includes('BBCA'), asked_models: asked.some(u => u.includes('/api/v1/models')),
  console_errors: errors, failed_requests: failed.slice(0, 12),
}, null, 1));
await browser.close();
})().catch(e => { console.error(String(e)); process.exit(1); });
