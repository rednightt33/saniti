/* Playwright smoke run of the page on the stub BacktestApi (stub.ts, built by `vite build --mode smoke` into
   dist-smoke/): boot, every builder step, the entry workspace, a run with every results tab, a sensitivity grid with a
   refused cell, the condition limit, the portfolio mode with its signal table and a second run, the keyboard shortcuts
   and the theme; then the market with markup in its strings (?hostile=1: no element is made from them and none of
   their scripts runs, in every view and tooltip) and the market with flow (?flow=1: the default end and the server's
   FLOW_DATA_THROUGH in the toast). Fails on any console error or page error.
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
let step = 'boot', page;
async function openPage() {
  page = await browser.newPage({ viewport:{ width:1440, height:900 } });
  // the web font is not needed here (and the sandbox may have no network): an empty style sheet
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.fulfill({ status:200, contentType:'text/css', body:'' }));
  page.on('console', m => { if (m.type() === 'error') errors.push(`[${step}] console: ${m.text()}`) });
  page.on('pageerror', e => errors.push(`[${step}] page: ${e.message}`));
}
await openPage();
const at = async (name, fn) => {
  step = name; const before = errors.length;
  try { await fn() } catch (e) { errors.push(`[${name}] ${e.message.split('\n')[0]}`) }
  await page.waitForTimeout(150);
  steps.push(`${errors.length === before ? 'ok  ' : 'FAIL'} ${name}`);
};
const text = sel => page.locator(sel).first().innerText();
const expect = (ok, what) => { if (!ok) throw new Error(what) };

const boot = async (query = '') => {
  await page.goto(`${origin}/backtest-app/${query}`);
  await page.waitForSelector('#builder .bs.on', { timeout:15000 });
  await page.waitForFunction(() => document.querySelectorAll('#laneLabels span').length > 0, null, { timeout:15000 });
};
/* the toast's text once it shows one that matches `re` */
const toastText = async re => {
  await page.waitForFunction(r => { const t = document.getElementById('toast'); return !t.hidden && new RegExp(r).test(t.textContent) }, re.source, { timeout:5000 });
  return text('#toast');
};
await at('boot', async () => {
  await boot();
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
  expect(/variants tried for this strategy$/.test(await text('#runNote')), 'unexpected run note');
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
/* (from here a builder step is opened with its summary row: the rail hides the panel when its step is the current one) */
/* a volspike threshold of 1 makes the grid step to -1, a value the condition refuses: that column was not run */
await at('sensitivity grid with a refused value', async () => {
  await page.click('#sumbox [data-st="2"]');
  await page.click('#builder [data-tpl="Breakout + volume"]');
  const val = page.locator('#builder .cond:has(b:text-is("Volume spike")) [data-p="val"]');
  await val.fill('1'); await val.evaluate(el => el.blur());
  await runAndWait();
  await page.click('#rtabs [data-tab="robust"]');
  const g = await page.evaluate(() => {
    const cells = [...document.querySelectorAll('#rbody table.heat tr')].slice(1).flatMap(r => [...r.querySelectorAll('td:not(.y)')]);
    return { all:cells.length, empty:cells.filter(c => !c.hasAttribute('data-tt') && !c.textContent && !c.getAttribute('style')).length,
             bad:cells.filter(c => /NaN|undefined/.test((c.getAttribute('style') || '') + c.textContent)).length, zeroTrades:cells.filter(c => /Trades<\/span><b class="">0</.test(c.dataset.tt || '') && !c.textContent).length };
  });
  expect(g.all === 25 && g.empty === 5 && !g.bad && !g.zeroTrades, `heat cells ${JSON.stringify(g)}: expected 25 with 5 empty and no NaN`);
});
/* the stub's limit is 4 active conditions per list: the template has 3, one more is added, the next is refused */
await at('condition limit', async () => {
  await page.click('#sumbox [data-st="2"]');
  const active = () => page.evaluate(() => document.querySelectorAll('#builder [data-step="2"] .cond:not(.off)').length);
  const before = await active();
  await page.click('#addCond'); await page.click('#menu [data-add="rsi"]');
  expect(await active() === before + 1, 'the fourth condition was not added');
  await page.click('#addCond'); await page.click('#menu [data-add="adx"]');
  expect(/^Limit reached: at most 4 active conditions per list\.$/.test(await toastText(/^Limit reached/)), 'no limit toast');
  expect(await active() === before + 1, 'a fifth active condition was added');
});
await at('portfolio mode', async () => {
  await page.click('#rail [data-st="1"]');
  await page.click('#modeSeg [data-m="portfolio"]');
  await page.waitForFunction(() => !document.getElementById('portSig').hidden && document.querySelectorAll('#portSig [data-t]').length > 1, null, { timeout:10000 });
});
/* two settings changes before the first preview answers: that preview is aborted and only the second one answers */
await at('preview replaced by newer settings', async () => {
  const count = () => page.evaluate(() => ({ aborted:window.__aborted || 0, answered:window.__previewAnswers || 0 }));
  const before = await count();
  await page.evaluate(() => { const el = document.querySelector('#builder [data-k="from"]'); for (const v of ['2019-03-01', '2019-04-01']) { el.value = v; el.dispatchEvent(new Event('change')) } });
  await page.waitForFunction(n => (window.__previewAnswers || 0) > n, before.answered, { timeout:5000 });
  await page.waitForTimeout(200);
  const after = await count();
  expect(after.aborted === before.aborted + 1 && after.answered === before.answered + 1, `previews: ${JSON.stringify(before)} -> ${JSON.stringify(after)}, expected one aborted and one answered`);
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

/* ---- the market with markup in every string of the server, the catalog and the errors (stub.ts XSS) ---- */
/* no element came from those strings and none of their scripts ran; every tooltip is drawn the way the page draws it
   on hover (#tip from data-tt), so markup inside one is found too */
const markupOption = sel => page.locator(`${sel} option`).evaluateAll(os => os.findIndex(o => o.textContent.includes('onerror=')));
const noMarkup = async () => {
  const found = await page.evaluate(() => {
    const tip = document.getElementById('tip'), keep = tip.innerHTML; let inTips = 0;
    for (const el of document.querySelectorAll('[data-tt]')) { tip.innerHTML = el.dataset.tt; inTips += tip.querySelectorAll('img,[onerror]').length }
    tip.innerHTML = keep;
    return { elements:document.querySelectorAll('img,[onerror]').length, inTips };
  });
  await page.waitForTimeout(100);
  const ran = await page.evaluate(() => window.__xss || []);
  expect(!found.elements && !found.inTips && !ran.length, `${found.elements} element(s) from markup, ${found.inTips} in tooltips, scripts ran: ${ran.join(', ')}`);
};
await page.close(); await openPage();
await at('hostile: boot', async () => {
  await boot('?hostile=1');
  expect((await page.locator('#builder [data-k="ticker"] option').allInnerTexts()).some(t => t.includes('onerror=')), 'the markup ticker is not listed as text');
  await noMarkup();
});
await at('hostile: portfolio preview', async () => {
  await page.click('#sumbox [data-st="1"]');
  await page.click('#modeSeg [data-m="portfolio"]');
  await page.waitForFunction(() => document.querySelectorAll('#portSig [data-t]').length === 6 && document.querySelector('#portSig td[data-tt]'), null, { timeout:10000 });
  expect((await text('#builder [data-k="universe"]')).includes('onerror='), 'the markup sector is not listed as text');
  await toastText(/preview warning/);
  await noMarkup();
});
await at('hostile: portfolio run and results', async () => {
  await runAndWait();
  for (const tab of ['overview', 'returns', 'trades', 'risk', 'robust', 'list']) {
    await page.click(`#rtabs [data-tab="${tab}"]`);
    if (tab === 'overview') await page.locator('#cmpAdd').selectOption({ index:await markupOption('#cmpAdd') });
    await page.waitForTimeout(200);
    if (tab === 'robust') expect((await text('#rbody .warnbox')).includes('onerror='), 'the warning box does not show the markup warning as text');
    await noMarkup();
  }
});
await at('hostile: an error message', async () => {
  await page.click('#viewSeg [data-v="signals"]');
  await page.click('#portSig [data-t="ACES"]');
  await toastText(/error message/);
  await noMarkup();
});
/* the markup sector's universe has only the markup ticker, which the preview leaves out: UNIVERSE_EMPTY, whose message
   names it, in the toast; the strategy summary and the view bar name the universe */
await at('hostile: the markup universe', async () => {
  await page.click('#sumbox [data-st="1"]');
  await page.locator('#builder [data-k="universe"]').selectOption({ index:await markupOption('#builder [data-k="universe"]') });
  await toastText(/^All 1 ticker\(s\) of the universe were left out/);
  expect((await text('#ctxTitle')).includes('onerror='), 'the view bar does not name the markup universe as text');
  await noMarkup();
});
await at('hostile: single run on the markup ticker', async () => {
  await page.click('#sumbox [data-st="1"]');
  await page.click('#modeSeg [data-m="single"]');
  await page.locator('#builder [data-k="ticker"]').selectOption({ index:await markupOption('#builder [data-k="ticker"]') });
  await runAndWait();
  await page.click('#rtabs [data-tab="overview"]');
  await page.waitForTimeout(200);
  await noMarkup();
});

/* ---- the market with flow: the default end is the broker data's day, a later end is the server's refusal ---- */
await page.close(); await openPage();
await at('flow: default end and FLOW_DATA_THROUGH', async () => {
  await boot('?flow=1');
  await page.click('#sumbox [data-st="1"]');
  const to = page.locator('#builder [data-k="to"]'), [value, max] = await to.evaluate(el => [el.value, el.max]);
  expect(value < max, `the default end ${value} is not before the last price day ${max}`);
  await to.fill(max); await to.evaluate(el => el.blur());
  await page.click('#runTop');
  const msg = await toastText(/^The broker data is published through/);
  expect(msg.startsWith(`The broker data is published through ${value}:`), `the toast does not name the default end ${value}: ${msg}`);
  expect(!/^Done in /.test(await text('#runNote')), 'the refused run finished');
});

await browser.close(); server.close();
console.log(steps.join('\n'));
if (errors.length) { console.error(`\n${errors.length} error(s):\n` + errors.join('\n')); process.exit(1) }
console.log('\nsmoke: no console errors');
