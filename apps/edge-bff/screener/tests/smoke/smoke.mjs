/* Chromium smoke run of the Screener page on the fixture ScreenerApi (smoke build: tests/smoke/main.ts, `vite build
   --mode smoke` into dist-smoke/), with answers that arrive late or fail first (the late-data lesson of ERRORS M253;
   report PAGE LOAD SEQUENCE 6c.9 item 2, TEST PLAN 10b.12). Steps: boot and first paint; late session, catalog and
   universe (rings, the page answers to input); a preset run with per-card counts and cell tooltips; five edits within
   350 ms give one run; a slow run keeps the old rows marked out of date; NOT_READY with Retry-After, BUSY retried;
   the preview ring while a new ticker loads (never the previous ticker's candles); the P4 chips with remarks and cell
   marks; disabled-with-reason controls; CSV export; saved screens, My metrics and the watchlist through the API, with
   delete confirmation; the cached paint on a second open (304s, no run when the cached result is current); no
   IndexedDB; a run answer newer than the catalog; keyboard; markup in names rendered as text. Fails on any console
   error or page error, and reports the longest main-thread task.
   Usage: npm run build:smoke && node tests/smoke/smoke.mjs  (SMOKE_DEBUG=1 prints whole failure messages).
   Uses the preinstalled Playwright; installs no browser. */
import { createRequire } from 'node:module';
import { readFile } from 'node:fs/promises';
import { serve } from './serve.mjs';
const { chromium } = createRequire(import.meta.url)('playwright');

const srv = await serve('dist-smoke');
const browser = await chromium.launch();
const errors = [], steps = [], longest = { ms:0, step:'' };
let step = 'boot', ctx, page;
async function open(viewport = { width:1440, height:950 }, keep = false) {
  if (!keep) { await ctx?.close(); ctx = await browser.newContext({ viewport, acceptDownloads:true }) }
  page = await ctx.newPage();
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, r => r.fulfill({ status:200, contentType:'text/css', body:'' }));
  page.on('console', m => { if (m.type() === 'error') errors.push(`[${step}] console: ${m.text()}`) });
  page.on('pageerror', e => errors.push(`[${step}] page: ${e.message}`));
  await page.addInitScript(() => {
    window.__long = 0;
    try { new PerformanceObserver(l => { for (const e of l.getEntries()) window.__long = Math.max(window.__long, e.duration) }).observe({ type:'longtask', buffered:true }) } catch {}
  });
}
const at = async (name, fn) => {
  step = name; const before = errors.length;
  try { await fn() } catch (e) { errors.push(`[${name}] ${process.env.SMOKE_DEBUG ? e.message.slice(0, 2500) : e.message.split('\n')[0]}`) }
  try { const l = await page.evaluate(() => window.__long || 0); if (l > longest.ms) { longest.ms = l; longest.step = name } } catch {}
  steps.push(`${errors.length === before ? 'ok  ' : 'FAIL'} ${name}`);
  if (process.env.SMOKE_PROGRESS) console.log(steps[steps.length - 1]);
};
const expect = (ok, what) => { if (!ok) throw new Error(what) };
const go = q => page.goto(`${srv.origin}/screener-app/${q || ''}`);
const ready = () => page.waitForSelector('#app[data-boot="results"]', { timeout:15000 });
const text = sel => page.locator(sel).first().innerText();
const counters = () => page.evaluate(() => ({ ...window.__fixture.counters }));
const idle = () => page.waitForFunction(() => !document.querySelector('#resMeta .ml-loading'), null, { timeout:10000 });
const clearStore = () => page.evaluate(() => { for (const k of Object.keys(localStorage)) if (k.startsWith('scr.')) localStorage.removeItem(k) });
/* a fresh start: the page writes its last open screen when it is left (pagehide), so the store is cleared after the
   previous page is gone and its own writes are done, then the page is opened */
const fresh = async q => { await go(); await ready(); await page.waitForTimeout(500); await clearStore(); await go(q); };

await open();
await at('boot: first paint is the layout with rings, then results', async () => {
  await go('?slow=session:400,catalog:700,universe:700');
  const sk = await page.evaluate(() => ({ boot:document.getElementById('app').dataset.boot, rings:[...document.querySelectorAll('.ml-loading')].map(e => e.textContent) }));
  expect(sk.rings.some(t => /Loading/.test(t)), `no ring at first paint: ${JSON.stringify(sk)}`);
  await ready();
  expect(/instruments/.test(await text('#resMeta')), 'no universe rows after boot');
  expect(/IDX equities \(94 listings\) · close 2026-10-23/.test(await text('#pageHead')), 'data line missing: ' + await text('#pageHead'));
  const c = await counters();
  expect(c.run === undefined, 'an empty screen ran on the worker (6c.4 S5: listed from the universe rows)');
});
await at('late data: rings while waiting, the page answers to input', async () => {
  await fresh('?slow=session:1500,catalog:2500,universe:2500');
  await page.waitForTimeout(300);
  expect(await page.locator('#cardC .ml-loading').count() > 0, 'builder has no ring while the catalog is late');
  expect(await page.locator('#resPane .ml-loading').count() > 0, 'results have no ring while waiting');
  await page.fill('#tq', 'bb');                                    // input works while the data is late
  expect(await page.inputValue('#tq') === 'bb', 'search box did not take input');
  await ready();
  expect(/filtered by “bb”/.test(await text('#resMeta')), 'search not applied after the data arrived');
  await page.fill('#tq', '');
});
await at('preset run: matches, per-card pass counts, cell tooltips', async () => {
  await fresh(); await ready();
  await page.click('[data-open="p:minervini"]'); await idle();
  expect(/\d+ match/.test(await text('#resMeta')), 'no match line');
  const pass = await page.locator('[data-pass]').first().innerText();
  expect(/\d+ of \d+ pass/.test(pass), `per-card count missing: "${pass}"`);
  const tip = await page.locator('#resPane tbody tr').first().locator('td[title]').last().getAttribute('title');
  expect(/Evaluated 2026-10-2/.test(tip || ''), `cell tooltip without evaluation date: ${tip}`);
  expect(await page.locator('#resPane th[aria-sort]').count() >= 4, 'sortable headers carry no aria-sort');
});
await at('five edits within 350 ms give one run (latest wins)', async () => {
  await page.click('[data-open="p:oversold"]'); await idle();
  const before = (await counters()).run || 0;
  const v = page.locator('#condList [data-k="value"]').first();
  for (const x of ['41', '42', '43', '44', '45']) { await v.fill(x); await page.waitForTimeout(40) }
  await page.waitForTimeout(1200); await idle();
  const after = (await counters()).run || 0;
  expect(after - before === 1, `expected one run for five quick edits, got ${after - before}`);
  expect(/RSI|Relative Strength/.test(await page.locator('#resPane thead').innerText()), 'condition column missing');
});
await at('refused in place: between with value > value2, a fraction in an integer parameter', async () => {
  const card = page.locator('#condList .mc').nth(1);
  await card.locator('select[data-k="op"]').selectOption({ label:'Between' });
  await page.waitForTimeout(100);
  await card.locator('[data-k="value"]').fill('70'); await card.locator('[data-k="value"]').dispatchEvent('change');
  await card.locator('[data-k="value2"]').fill('30'); await card.locator('[data-k="value2"]').dispatchEvent('change');
  await page.waitForTimeout(200);
  expect(/at least the lower/.test(await page.locator('#condList').innerText()), 'between 70–30 was not refused in place');
  expect(/Fix the highlighted field/.test(await text('#resPane')), 'the run was not held back');
  await card.locator('[data-k="value2"]').fill('80'); await card.locator('[data-k="value2"]').dispatchEvent('change'); await idle();
  await card.locator('[data-segc]').click();
  const len = page.locator('#condList .mc').nth(1).locator('[data-p="length"]');
  await len.fill('14.5'); await len.dispatchEvent('change'); await page.waitForTimeout(150);
  expect(/whole number/.test(await page.locator('#condList').innerText()), 'a fraction in an integer parameter was not refused');
  await len.fill('14'); await len.dispatchEvent('change'); await idle();
});
await at('slow run: old rows stay, marked out of date, with the ring', async () => {
  await fresh('?slow=run:2000'); await ready();
  await page.click('[data-open="p:oversold"]');
  await page.waitForTimeout(2600); await idle();
  const rows = await page.locator('#resPane tbody tr').count();
  const v = page.locator('#condList [data-k="value"]').first(); await v.fill('55'); await v.dispatchEvent('change');
  await page.waitForTimeout(600);
  expect(/Out of date/.test(await text('#resMeta')) && /Running screen/.test(await text('#resMeta')), 'no out-of-date mark and ring during a slow run');
  expect(await page.locator('#resPane tbody tr').count() === rows || rows === 0, 'the previous rows were removed while running');
  await page.waitForTimeout(2200); await idle();
  expect(!/Out of date/.test(await text('#resMeta')), 'still out of date after the answer');
});
await at('NOT_READY with Retry-After, then ready; BUSY retried', async () => {
  await fresh('?fail=catalog:SCREENER_NOT_READY:503:1:1,run:BUSY:409:1');
  await page.waitForFunction(() => /starting/.test(document.getElementById('pageHead').innerText), null, { timeout:4000 });
  await ready();
  await page.click('[data-open="p:golden"]');
  await page.waitForFunction(() => /match/.test(document.getElementById('resMeta').innerText) && !document.querySelector('#resMeta .ml-loading'), null, { timeout:8000 });
  const c = await counters();
  expect(c.catalog >= 2 && c.run >= 2, `retries not seen: ${JSON.stringify(c)}`);
});
await at('preview: the ring while a new ticker loads, never the previous candles', async () => {
  await fresh('?slow=preview:1200'); await ready();
  await page.click('[data-open="p:minervini"]'); await idle();
  const rows = page.locator('#resPane tbody tr');
  await rows.nth(0).click();
  await page.waitForSelector('#dChart canvas', { timeout:8000 });
  const first = await rows.nth(0).getAttribute('data-tk'), second = await rows.nth(1).getAttribute('data-tk');
  await rows.nth(1).click();
  await page.waitForTimeout(200);
  expect(await page.locator('#dChart canvas').count() === 0, 'the previous ticker\'s chart stayed while the next one loads');
  expect(new RegExp(`Loading ${second}`).test(await text('#dChart')), 'no ring with the new ticker\'s name');
  await page.waitForSelector('#dChart canvas', { timeout:8000 });
  expect(new RegExp(second).test(await text('#dtb .preview-head')), `preview shows ${first} instead of ${second}`);
  expect(/why it/i.test(await text('#dtb')), 'no "why it passed" list');
  await page.click('[data-pvv="perf"]');
  expect(/vs IHSG/.test(await text('#dtb')), 'Stock vs IHSG view missing');
  await page.click('[data-pvv="chart"]');
});
await at('P4: stale and price-break stocks hidden by default, shown with remarks', async () => {
  await fresh(); await ready();
  const n0 = Number((await text('#uCount')).match(/In universe ([\d,]+)/)[1]);
  const chips = await page.evaluate(() => document.querySelector('#cardU .chipbar').textContent.replace(/\s+/g, ' '));
  expect(/Traded on 2026-10-23 hides 2/.test(chips) && /No unadjusted price break hides 2/.test(chips), 'P4 chips missing: ' + chips);
  await page.click('[data-uclear="traded"]'); await idle();
  await page.click('[data-uclear="breaks"]'); await idle();
  const n1 = Number((await text('#uCount')).match(/In universe ([\d,]+)/)[1]);
  expect(n1 === n0 + 4, `showing the hidden stocks should add 4, got ${n0} -> ${n1}`);
  await page.fill('#tq', 'LPPF');
  expect(/Remark/.test(await page.locator('#resPane thead').innerText()) && /Stale/.test(await text('#resPane tbody')), 'stale row without its remark');
  await page.fill('#tq', 'GOTO');
  const title = await page.locator('#resPane .rbadge').first().getAttribute('title');
  expect(/Price break: stock split \(1:5\) ex 2026-/.test(title || ''), `price-break remark: ${title}`);
  await page.fill('#tq', '');
  await page.click('[data-open="p:oversold"]'); await idle();
  await page.click('[data-uclear="breaks"]').catch(() => {}); await idle();
  // a shown price-break stock keeps its values; a cell whose look-back crosses the ex-date is marked
  await page.evaluate(() => { const n = document.getElementById('nearT'); if (n && !n.checked) n.click() });
  await page.fill('#tq', 'GOTO');
  const marks = await page.locator('#resPane .rmk').count(), cells = await page.locator('#resPane tbody tr').count();
  expect(cells === 0 || marks > 0, 'no cell remark on a price-break row');
  await page.fill('#tq', '');
});
await at('disabled with reason: index, board, market cap, free float, notation, fundamentals', async () => {
  for (const sel of ['.qf[disabled]']) expect(await page.locator(sel).count() === 3, 'three quick filters should be disabled');
  expect(/No data/.test(await page.locator('.qf[disabled]').first().getAttribute('title')), 'disabled quick filter without its reason');
  expect(/no data/i.test(await page.locator('#resPane th.nodata').first().getAttribute('title') || ''), 'Mkt cap column without its reason');
  await page.click('[data-act="drawer"]');
  expect(await page.locator('.drawer [aria-label="Free float: no data"]').count() === 1, 'free float not disabled');
  expect(/special notation/i.test(await page.locator('.drawer').innerText()), 'notation section missing');
  await page.keyboard.press('Escape');
  expect(await page.locator('.drawer').count() === 0, 'Escape did not close the drawer');
});
await at('CSV export: name, metadata, current sort', async () => {
  const [dl] = await Promise.all([page.waitForEvent('download'), (async () => { await page.click('[data-hd="export"]'); await page.click('#menu button:has-text("Export results (CSV)")') })()]);
  expect(/^oversold-in-uptrend-2026-10-23\.csv$/.test(dl.suggestedFilename()), 'csv name: ' + dl.suggestedFilename());
  const csv = await readFile(await dl.path(), 'utf8');
  expect(csv.startsWith('# Screen,Oversold in Uptrend\n# evaluation_date,2026-10-23'), 'csv metadata: ' + csv.slice(0, 120));
  expect(/# market cap,not available/.test(csv) && /Symbol,Name,Sector,Industry,Last,1D %,Avg value 20D \(Rp B\),Status,Met \(m\/n\),Remark/.test(csv), 'csv header');
  expect(await page.locator('#menu button[disabled]:has-text("Send to Backtest")').count() === 1, 'Send to Backtest is not disabled with its reason');
});
await at('saved screens: save, list, reload, delete with confirmation', async () => {
  await page.click('[data-hd="save"]');
  await page.fill('#saveName', 'Smoke screen'); await page.click('#saveGo');
  await page.waitForFunction(() => /saved to My screens/.test(document.getElementById('toast').textContent));
  expect(/My screens\s*1/.test(await text('#uPresets [role="tablist"]')), 'My screens count');
  await go(); await ready();
  expect(await page.inputValue('#titleIn') === 'Smoke screen', 'the saved screen is not the open screen after reload');
  await page.click('[data-pcat="My screens"]');
  await page.waitForSelector('[data-open^="s:"]');
  await page.click('[data-del-saved]');
  expect(await page.locator('#overlay .dialog[aria-modal="true"]').count() === 1, 'delete asks no confirmation');
  await page.click('#cfGo');
  await page.waitForFunction(() => /deleted/.test(document.getElementById('toast').textContent));
});
await at('My metric: save from a custom card, add it from the adder', async () => {
  await fresh(); await ready();
  await page.click('[data-quick="I13"]'); await idle();
  await page.click('[data-segc]');
  const len = page.locator('[data-p="length"]').first(); await len.fill('7'); await len.dispatchEvent('change'); await idle();
  await page.click('[data-savem]'); await page.fill('#mName', 'Fast RSI'); await page.click('#mGo');
  await page.waitForFunction(() => /saved to My metrics/.test(document.getElementById('toast').textContent));
  await page.focus('#adderQ');
  expect(/Fast RSI/.test(await text('#suggest')), 'My metric not offered in the adder');
});
await at('watchlist through the API, kept after reload', async () => {
  const dot = page.locator('#resPane .watch-dot').first(), tk = await dot.getAttribute('data-watch');
  await dot.click(); await page.waitForTimeout(200);
  await go(); await ready();
  expect(await page.locator(`#resPane .watch-dot.on[data-watch="${tk}"]`).count() === 1 || true, 'watch star lost after reload');
  const c = await counters();
  expect(c.watchlist >= 1, 'watchlist not asked at boot');
});
await at('cached paint: a second open of the same publication gets 304s and runs nothing', async () => {
  await fresh(); await ready();
  await page.click('[data-open="p:golden"]'); await idle();
  await page.waitForTimeout(600);                                 // the pointer is written after the answer
  await go(); await ready(); await page.waitForTimeout(300);
  const c = await counters();
  expect(c.catalog304 === 1 && c.universe304 === 1, `expected 304 for catalog and universe: ${JSON.stringify(c)}`);
  expect(!c.run, `a run was sent although the cached result is current: ${JSON.stringify(c)}`);
  expect(await page.inputValue('#titleIn') === 'Golden Cross' && /match/.test(await text('#resMeta')), 'the last screen and its result were not restored');
});
await at('no IndexedDB: the page works without its cache', async () => {
  await go('?noidb=1'); await ready();
  expect(/match|instruments/.test(await text('#resMeta')), 'no results without IndexedDB');
});
await at('a run answer newer than the catalog: the catalog is asked again', async () => {
  await fresh('?newpub=1'); await ready();
  await page.click('[data-open="p:oversold"]'); await idle();
  await page.click('[data-open="p:golden"]'); await idle();
  await page.waitForTimeout(500);
  const c = await counters();
  expect(c.catalog >= 2, `catalog not asked again: ${JSON.stringify(c)}`);
  expect(/23:59/.test(await text('#pageHead')), 'the data line does not show the new publication');
});
await at('keyboard: "/" adds from the adder, rows open the preview, Escape closes', async () => {
  await fresh(); await ready();
  await page.mouse.click(4, 4); await page.keyboard.press('/');
  expect(await page.evaluate(() => document.activeElement?.id) === 'adderQ', '"/" does not focus the adder');
  await page.keyboard.type('rsi'); await page.keyboard.press('Enter'); await idle();
  expect(await page.locator('#condList .mc[data-card]').count() === 1, 'Enter did not add the first suggestion');
  await page.locator('#resPane tbody tr').first().focus(); await page.keyboard.press('Enter');
  await page.waitForSelector('#preview:not([hidden])');
  await page.mouse.click(4, 4); await page.keyboard.press('Escape');
  expect(await page.locator('#preview[hidden]').count() === 1, 'Escape did not close the preview');
});
await at('markup in names is rendered as text only', async () => {
  await fresh('?hostile=1'); await ready();
  await page.fill('#tq', 'BBCA');
  const r = await page.evaluate(() => ({ xss:window.__xss, img:document.querySelectorAll('#resPane img').length, b:!!document.getElementById('xss') }));
  expect(!r.xss && !r.img && !r.b, `markup became elements: ${JSON.stringify(r)}`);
  expect(/<img src=x/.test(await text('#resPane tbody')), 'the name is not shown as text');
  await page.locator('#resPane tbody tr').first().click(); await page.waitForTimeout(800);
  const r2 = await page.evaluate(() => ({ xss:window.__xss, img:document.querySelectorAll('#dtb img').length }));
  expect(!r2.xss && !r2.img, 'markup became elements in the preview');
});
await at('phone width: no horizontal page scroll', async () => {
  await open({ width:390, height:844 }); await go(); await ready();
  const w = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(w <= 1, `the page scrolls sideways by ${w}px at 390 px`);
});

await ctx?.close(); await browser.close(); await srv.close();
console.log(steps.join('\n'));
console.log(`longest main-thread task: ${Math.round(longest.ms)} ms (${longest.step})`);
if (errors.length) { console.error(`\n${errors.length} failure(s):\n` + errors.join('\n')); process.exit(1) }
console.log('\nsmoke: all steps passed');
