/* Playwright smoke run of the page on the stub BacktestApi (stub.ts, built by `vite build --mode smoke` into
   dist-smoke/): boot, every builder step, the entry workspace, a run with every results tab, the portfolio mode with
   its signal table and a second run, the keyboard shortcuts and the theme. Fails on any console error or page error.
   Usage: npm run smoke (builds dist-smoke first). Uses the preinstalled Playwright; installs no browser. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
const { chromium } = createRequire(import.meta.url)('playwright');   // the preinstalled Playwright (global NODE_PATH)

const BUILD = fileURLToPath(new URL('../../dist-smoke/', import.meta.url));
const TYPES = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.svg':'image/svg+xml' };
const server = createServer(async (req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const rel = path.startsWith('/backtest-app/') ? normalize(path.slice('/backtest-app/'.length) || 'index.html') : null;
  try {
    if (!rel || rel.startsWith('..')) throw new Error('not found');
    const file = join(BUILD, rel), body = await readFile(file);
    res.writeHead(200, { 'Content-Type':TYPES[extname(file)] || 'application/octet-stream' }); res.end(body);
  } catch { res.writeHead(404); res.end('not found') }
});
await new Promise(ok => server.listen(0, '127.0.0.1', ok));
const origin = `http://127.0.0.1:${server.address().port}`;

const browser = await chromium.launch();
const errors = [], steps = [];
let step = 'boot';
const page = await browser.newPage({ viewport:{ width:1440, height:900 } });
// the web font is not needed here (and the sandbox may have no network): an empty style sheet
await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.fulfill({ status:200, contentType:'text/css', body:'' }));
page.on('console', m => { if (m.type() === 'error') errors.push(`[${step}] console: ${m.text()}`) });
page.on('pageerror', e => errors.push(`[${step}] page: ${e.message}`));
const at = async (name, fn) => {
  step = name; const before = errors.length;
  try { await fn() } catch (e) { errors.push(`[${name}] ${e.message.split('\n')[0]}`) }
  await page.waitForTimeout(150);
  steps.push(`${errors.length === before ? 'ok  ' : 'FAIL'} ${name}`);
};
const text = sel => page.locator(sel).first().innerText();
const expect = (ok, what) => { if (!ok) throw new Error(what) };

await at('boot', async () => {
  await page.goto(`${origin}/backtest-app/`);
  await page.waitForSelector('#builder .bs.on', { timeout:15000 });
  await page.waitForFunction(() => document.querySelectorAll('#laneLabels span').length > 0, null, { timeout:15000 });
  expect((await text('#lastRun')).includes('Not run yet'), 'the page does not open in "Not run yet"');
  expect((await text('#resCard')).includes('No results yet.'), 'the results card is not empty at boot');
});
for (const n of [1, 3, 4, 5, 2]) await at(`builder step ${n}`, async () => {
  await page.click(`#rail [data-st="${n}"]`);
  await page.waitForSelector(`#builder .bs.on[data-step="${n}"]`, { timeout:3000 });
});
await at('entry workspace', async () => {
  await page.click('#wsOpen');
  await page.waitForSelector('#ews:not([hidden])', { timeout:3000 });
  await page.fill('#wsQ', 'rsi');
  await page.locator('#wsList [data-wi]').first().click();
  await page.fill('#wsQ', '');
  await page.click('#wsTabs [data-wside="exit"]');
  await page.click('#wsTabs [data-wside="entry"]');
  await page.keyboard.press('Escape');
  await page.waitForSelector('#ews[hidden]', { state:'attached', timeout:3000 });
});
const runAndWait = async () => {
  await page.click('#runTop');
  await page.waitForFunction(() => /^Done in /.test(document.getElementById('runNote').textContent), null, { timeout:30000 });
};
await at('run (single)', async () => {
  await runAndWait();
  expect(/variants tried this session$/.test(await text('#runNote')), 'unexpected run note');
});
for (const tab of ['overview', 'returns', 'trades', 'risk', 'robust', 'list']) await at(`results tab ${tab}`, async () => {
  await page.click(`#rtabs [data-tab="${tab}"]`);
  await page.waitForSelector(`#rtabs [data-tab="${tab}"].on`, { timeout:3000 });
  if (tab === 'overview') { const add = page.locator('#cmpAdd'); if (await add.count()) { await add.selectOption('IHSG'); await page.waitForTimeout(300) } }
  if (tab === 'robust') { const m = page.locator('#hm [data-m="cagr"]'); if (await m.count()) await m.click() }
  if (tab === 'list') await page.click('.trtbl [data-s="ret"]');
});
await at('signals view after the run', async () => {
  await page.click('#viewSeg [data-v="signals"]');
  await page.waitForTimeout(300);
});
await at('settings change marks the result stale', async () => {
  await page.click('#rail [data-st="3"]');
  const sl = page.locator('#builder [data-k="exit.sl"]');
  await sl.fill('8');
  await sl.evaluate(el => el.blur());            // the change event, as when the user leaves the field
  await page.waitForSelector('#lastRun.is-stale', { timeout:3000 });
  expect(await page.evaluate(() => !document.getElementById('staleTag').hidden), 'the stale tag is hidden');
});
await at('portfolio mode', async () => {
  await page.click('#rail [data-st="1"]');
  await page.click('#modeSeg [data-m="portfolio"]');
  await page.waitForFunction(() => !document.getElementById('portSig').hidden && document.querySelectorAll('#portSig [data-t]').length > 1, null, { timeout:10000 });
});
await at('run (portfolio)', async () => {
  await runAndWait();
  await page.click('#viewSeg [data-v="signals"]');
  await page.locator('#portSig [data-t]').nth(1).click();
  await page.waitForTimeout(500);
});
for (const tab of ['overview', 'returns', 'trades', 'risk', 'robust', 'list']) await at(`portfolio results tab ${tab}`, async () => {
  await page.click('#viewSeg [data-v="results"]');
  await page.click(`#rtabs [data-tab="${tab}"]`);
  await page.waitForSelector(`#rtabs [data-tab="${tab}"].on`, { timeout:3000 });
});
await at('keyboard shortcuts and theme', async () => {
  await page.locator('body').click({ position:{ x:5, y:5 } }).catch(() => {});
  await page.keyboard.press('f'); expect(await page.evaluate(() => document.body.classList.contains('mainfs')), 'f did not open full screen');
  await page.keyboard.press('Escape'); expect(!(await page.evaluate(() => document.body.classList.contains('mainfs'))), 'Escape did not leave full screen');
  await page.keyboard.press('['); expect(await page.evaluate(() => document.body.classList.contains('bcol')), '[ did not hide the panel');
  await page.keyboard.press('[');
  await page.click('#themeBtn'); await page.click('#themeBtn');
  const keys = await page.evaluate(() => Object.keys(localStorage).sort());
  expect(keys.every(k => k.startsWith('ml.')), `unexpected localStorage keys ${keys}`);
});

await browser.close(); server.close();
console.log(steps.join('\n'));
if (errors.length) { console.error(`\n${errors.length} error(s):\n` + errors.join('\n')); process.exit(1) }
console.log('\nsmoke: no console errors');
