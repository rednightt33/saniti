/* Playwright smoke run of the page on the stub BacktestApi (stub.ts, built by `vite build --mode smoke` into
   dist-smoke/): boot, every builder step, the entry workspace, a run with every results tab, a sensitivity grid with a
   refused cell, the condition limit, the portfolio mode with its stock picker (PF7: the search box from the keyboard,
   the groupings' filters, add all, the chips), its signal table and a second run, the keyboard shortcuts and the
   theme; then the market with markup in its strings (?hostile=1: no element is made from them and none of their
   scripts runs, in every view and tooltip), the market with stocks every preview and run leaves out (?wide=1, on a
   phone's width: the limit of 12 stocks, the preview's one-line toast, the view bar's title, a left-out row asks no
   events, a stock without price data picked first, every picked stock left out) and the market with flow (?flow=1:
   the default end and the server's FLOW_DATA_THROUGH in the toast). Fails on any console error or page error.
   Usage: npm run smoke (builds dist-smoke first); SMOKE_DEBUG=1 prints each failure's whole message (Playwright's call
   log). Uses the preinstalled Playwright; installs no browser. */
import { createRequire } from 'node:module';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';
const { chromium } = createRequire(import.meta.url)('playwright');   // the preinstalled Playwright (global NODE_PATH)

const BUILD = fileURLToPath(new URL('../../dist-smoke/', import.meta.url));
const STATIC = fileURLToPath(new URL('../../../static/', import.meta.url));     // edge-bff's own files: the EDGE icons
const ICONS = ['/favicon.svg', '/favicon-32.png'];
const TYPES = { '.html':'text/html', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.svg':'image/svg+xml', '.png':'image/png' };
const server = createServer(async (req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const rel = path.startsWith('/backtest-app/') ? normalize(path.slice('/backtest-app/'.length) || 'index.html') : null;
  try {
    if (ICONS.includes(path)) { const file = join(STATIC, path.slice(1)); res.writeHead(200, { 'Content-Type':TYPES[extname(file)] }); res.end(await readFile(file)); return }
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
async function openPage(viewport = { width:1440, height:900 }) {
  page = await browser.newPage({ viewport });
  // the web font is not needed here (and the sandbox may have no network): an empty style sheet
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.fulfill({ status:200, contentType:'text/css', body:'' }));
  page.on('console', m => { if (m.type() === 'error') errors.push(`[${step}] console: ${m.text()}`) });
  page.on('pageerror', e => errors.push(`[${step}] page: ${e.message}`));
}
await openPage();
const at = async (name, fn) => {
  step = name; const before = errors.length;
  try { await fn() } catch (e) { errors.push(`[${name}] ${process.env.SMOKE_DEBUG ? e.message.slice(0, 2500) : e.message.split('\n')[0]}`) }
  await page.waitForTimeout(150);
  steps.push(`${errors.length === before ? 'ok  ' : 'FAIL'} ${name}`);
};
const text = sel => page.locator(sel).first().innerText();
const expect = (ok, what) => { if (!ok) throw new Error(what) };

/* every toast the page shows is kept in window.__toasts (a step can check that none was shown) */
const boot = async (query = '') => {
  await page.goto(`${origin}/backtest-app/${query}`);
  await page.evaluate(() => { const t = document.getElementById('toast'); window.__toasts = [];
    new MutationObserver(() => { if (!t.hidden) window.__toasts.push(t.textContent) }).observe(t, { attributes:true, childList:true, characterData:true, subtree:true }) });
  await page.waitForSelector('#builder .bs.on', { timeout:15000 });
  await page.waitForFunction(() => document.querySelectorAll('#laneLabels span').length > 0, null, { timeout:15000 });
};
/* the toast's text once it shows one that matches `re` */
const toastText = async re => {
  await page.waitForFunction(r => { const t = document.getElementById('toast'); return !t.hidden && new RegExp(r).test(t.textContent) }, re.source, { timeout:5000 });
  return text('#toast');
};
const probe = () => page.evaluate(() => ({ toasts:window.__toasts.length, asks:window.__previewAsks || 0, events:[...(window.__events || [])] }));
const toastsSince = n => page.evaluate(k => window.__toasts.slice(k), n);
/* the picker (picker.ts): the picked stocks as the chips show them, the count, a grouping's select by its label */
const chips = () => page.locator('#pkChips .chip b').allInnerTexts();
const group = (label, value) => page.locator(`#pk label.fld:has(span:text-is("${label}")) select`).selectOption({ label:value });
const options = () => page.locator('#pkList [role="option"] b').allInnerTexts();
const tableRows = () => page.locator('#portSig [data-t]').evaluateAll(rs => rs.map(r => r.dataset.t));
await at('boot', async () => {
  await boot();
  expect((await text('#lastRun')).includes('Not run yet'), 'the page does not open in "Not run yet"');
  expect((await text('#resCard')).includes('No results yet.'), 'the results card is not empty at boot');
  // review finding (b): the EDGE icons are linked and answered
  const icons = await page.evaluate(async () => Promise.all([...document.querySelectorAll('link[rel="icon"]')].map(async l => [l.getAttribute('href'), (await fetch(l.href)).status])));
  expect(JSON.stringify(icons) === '[["/favicon.svg",200],["/favicon-32.png",200]]', `icons ${JSON.stringify(icons)}`);
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
/* the live default portfolio is empty (PF7): the picker, the table and the summary say so, and nothing is previewed */
await at('portfolio mode: no stock picked', async () => {
  const p0 = await probe();
  await page.click('#rail [data-st="1"]');
  await page.click('#modeSeg [data-m="portfolio"]');
  await page.waitForSelector('#pkQ[role="combobox"][aria-controls="pkList"]', { timeout:3000 });
  expect(await text('#pkN') === '0 / 12' && !(await chips()).length, `the picker does not start empty: ${await text('#pkN')}`);
  expect((await text('#portSig')).includes('No stock picked yet.'), 'the signal table does not say that no stock is picked');
  expect((await text('#sumbox .sumrow.on em')).startsWith('No stock picked · max 5'), `step summary: ${await text('#sumbox .sumrow.on em')}`);
  await page.waitForTimeout(300);
  expect((await probe()).asks === p0.asks, 'a preview was asked for no stock');
});
/* review PG-4: outside the picker, step 1 keeps the reference's rows: its first row's Max positions (the Universe
   select it held is the picker's card), then its second row as it is, "Rank candidates by" beside "Min. avg value" */
await at('portfolio mode: the reference\'s rows', async () => {
  const rows = await page.locator('#builder [data-step="1"] .row:not(.pk)').evaluateAll(rs => rs.map(r => [...r.querySelectorAll(':scope > .fld > span')].map(e => e.textContent)));
  expect(JSON.stringify(rows) === JSON.stringify([['Max positions'], ['Rank candidates by', 'Min. avg value'], ['From', 'To', 'Out-of-sample']]), `step 1 rows ${JSON.stringify(rows)}`);
  const tops = await page.locator('#builder [data-step="1"] .row:not(.pk) > .fld').evaluateAll(fs => Object.fromEntries(fs.map(f => [f.firstElementChild.textContent, Math.round(f.getBoundingClientRect().top)])));
  expect(tops['Rank candidates by'] === tops['Min. avg value'] && tops['Max positions'] < tops['Rank candidates by'], `field tops ${JSON.stringify(tops)}`);
});
await at('run with no stock picked', async () => {
  const note = await text('#runNote');
  await page.click('#runTop');
  await toastText(/^Add at least one stock$/);
  expect(await text('#runNote') === note && !(await text('#lastRun')).includes('Running'), 'a run started without a stock');
});
/* the search from the keyboard: ticker prefix matches first, then names; the active option skips the picked ones */
await at('picker: search', async () => {
  await page.click('#pkQ'); await page.keyboard.type('a');
  await page.waitForSelector('#pkQ[aria-expanded="true"]', { timeout:3000 });
  const got = await options();
  expect(JSON.stringify(got) === '["ACES","ASII","MAPI","BBCA","BBRI","TLKM"]', `options ${got}`);
  expect(await page.getAttribute('#pkQ', 'aria-activedescendant') === 'pkO0', 'the first option is not active');
  await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter');                  // ASII
  expect(await page.getAttribute('#pkO1', 'aria-disabled') === 'true', 'the picked option can still be added');
  expect(await page.getAttribute('#pkQ', 'aria-activedescendant') === 'pkO2', 'the next stock is not active after an add');
  await page.keyboard.press('ArrowUp'); await page.keyboard.press('Enter');                    // ACES (ASII is skipped)
  expect(JSON.stringify(await chips()) === '["ASII","ACES"]', `chips ${await chips()}`);
  await page.keyboard.press('Escape');
  expect(await page.getAttribute('#pkQ', 'aria-expanded') === 'false', 'Escape did not close the list');
  await page.keyboard.press('Escape');
  expect(await page.inputValue('#pkQ') === '', 'the second Escape did not clear the search');
  expect(await text('#pkN') === '2 / 12', `count ${await text('#pkN')}`);
});
/* the groupings' filters: values with their counts, unclassified apart, AND across groupings, add all */
await at('picker: groups', async () => {
  const sector = await page.locator('#pk label.fld:has(span:text-is("Sector")) option').allInnerTexts();
  expect(JSON.stringify(sector) === '["Any Sector","Consumer (2)","Finance (2)","Industrials (1)","Infrastructure (1)"]', `sector options ${sector}`);
  const industry = await page.locator('#pk label.fld:has(span:text-is("Industry")) option').allInnerTexts();
  expect(industry.at(-1) === 'Unclassified (1)', `industry options ${industry}`);
  await group('Sector', 'Finance (2)');
  expect((await text('#pkG .pk-gh')).startsWith('2 stocks in this group'), 'the group list does not count its stocks');
  await page.click('#pkAll');
  expect(JSON.stringify(await chips()) === '["ASII","ACES","BBCA","BBRI"]', `chips ${await chips()}`);
  expect(await page.locator('#pkAll').isDisabled(), 'add all stays enabled with every stock of the group picked');
  await group('Industry', 'Unclassified (1)');
  expect((await text('#pkG')).includes('No stock in this group.'), 'Finance AND unclassified industry is not empty');
  await group('Sector', 'Any Sector');
  expect((await page.locator('#pkG .pk-row b').allInnerTexts()).join() === 'ASII' && (await text('#pkG .pk-row')).includes('Picked'), 'the unclassified industry does not list ASII as picked');
  await group('Industry', 'Any Industry');
});
/* a chip removed from the keyboard; the chart's ticker is always a picked stock (review finding (a): the single run's
   MAPI is not picked) */
await at('picker: chips and the chart\'s ticker', async () => {
  await page.focus('#pkChips [data-pk-del="ACES"]'); await page.keyboard.press('Enter');
  expect(JSON.stringify(await chips()) === '["ASII","BBCA","BBRI"]', `chips ${await chips()}`);
  expect(await page.evaluate(() => document.activeElement?.dataset.pkDel) === 'BBCA', 'the focus did not move to the next chip');
  expect(await text('#pkN') === '3 / 12', `count ${await text('#pkN')}`);
  await page.click('#viewSeg [data-v="signals"]');
  await page.waitForFunction(() => { const n = [...document.querySelectorAll('#portSig tbody td:nth-child(2)')]; return n.length === 3 && n.every(td => td.textContent !== '—') }, null, { timeout:10000 });
  expect(JSON.stringify(await tableRows()) === '["ASII","BBCA","BBRI"]', `table rows ${await tableRows()}`);
  const tk = await page.inputValue('#sigTicker');
  expect(['ASII', 'BBCA', 'BBRI'].includes(tk), `the chart shows ${tk}, which is not picked`);
  expect((await text('#ctxTitle')) === 'ASII, BBCA, BBRI · 3 stocks · max 5 positions', `ctx title ${await text('#ctxTitle')}`);
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
/* review PAGE-V3: a preview another tab replaced (409 PREVIEW_REPLACED) shows no toast and is not asked again until the
   user acts on the page */
await at('preview replaced by another tab', async () => {
  const p0 = await probe();
  await page.evaluate(() => { window.__replaceNextPreview = true; const el = document.querySelector('#builder [data-k="from"]'); el.value = '2019-05-01'; el.dispatchEvent(new Event('change')) });
  await page.waitForFunction(n => (window.__previewAsks || 0) > n && !window.__replaceNextPreview, p0.asks, { timeout:5000 });
  await page.waitForTimeout(800);
  const p1 = await probe();
  expect(p1.asks === p0.asks + 1, `previews asked by themselves: ${p1.asks - p0.asks}`);
  expect(p1.toasts === p0.toasts, `toasts: ${await toastsSince(p0.toasts)}`);
  expect((await page.locator('#portSig tbody td:nth-child(2)').allInnerTexts()).every(t => t === '—'), 'the rows of the replaced preview are not the dashes');
  await page.locator('#portSig [data-t="BBCA"]').click();
  await page.waitForFunction(n => (window.__previewAsks || 0) > n, p1.asks, { timeout:5000 });
  await page.waitForFunction(() => !/^—/.test(document.querySelector('#portSig tbody td:nth-child(2)').textContent), null, { timeout:5000 });
});
/* review finding (a) and PAGE-V2: the run asks the events of its own tickers only, and no toast says one is missing */
await at('run (portfolio)', async () => {
  const p0 = await probe();
  await runAndWait();
  await page.click('#viewSeg [data-v="signals"]');
  await page.locator('#portSig [data-t]').nth(1).click();
  await page.waitForTimeout(500);
  const p1 = await probe(), asked = p1.events.slice(p0.events.length);
  expect(asked.length && asked.every(t => ['ASII', 'BBCA', 'BBRI'].includes(t)), `events asked for ${asked}`);
  expect(p1.toasts === p0.toasts, `toasts: ${await toastsSince(p0.toasts)}`);
  const sub = await page.evaluate(() => document.querySelector('#resCard .card-h .sub').textContent);
  expect(sub.startsWith('Portfolio · 3 stocks · max 5 positions · '), `results header ${sub}`);
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
/* every stock picked from the search box, the markup one by the start of its ticker; the preview leaves it out (its
   row's tooltip has the markup reason) */
const pickBySearch = async q => { await page.fill('#pkQ', q); await page.waitForSelector('#pkQ[aria-expanded="true"]', { timeout:3000 }); await page.keyboard.press('Enter') };
await at('hostile: portfolio preview', async () => {
  await page.click('#sumbox [data-st="1"]');
  await page.click('#modeSeg [data-m="portfolio"]');
  for (const q of ['MAPI', 'ACES', 'BBCA', 'BBRI', 'TLKM', '"\'><img']) await pickBySearch(q);
  expect((await chips()).length === 6 && (await chips()).at(-1).includes('onerror='), 'the markup ticker is not a chip with its text');
  await page.fill('#pkQ', '"\'><img'); await page.waitForSelector('#pkQ[aria-expanded="true"]');
  expect((await text('#pkList')).includes('onerror='), 'the search list does not show the markup ticker as text');
  await noMarkup();
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.querySelectorAll('#portSig [data-t]').length === 6 && document.querySelector('#portSig td[data-tt]'), null, { timeout:10000 });
  for (const label of ['Sector', 'Industry'])
    expect((await page.locator(`#pk label.fld:has(span:text-is("${label}")) option`).allInnerTexts()).some(t => t.includes('onerror=')), `the markup ${label} is not listed as text`);
  await toastText(/^2 stocks left out \(see the — rows\)$/);
  await noMarkup();
});
await at('hostile: the markup group', async () => {
  const sel = page.locator('#pk label.fld:has(span:text-is("Sector")) select');
  await sel.selectOption({ index:await markupOption('#pk label.fld:has(span:text-is("Sector")) select') });
  expect((await text('#pkG')).includes('onerror='), 'the markup group does not list its stock as text');
  await noMarkup();
  await sel.selectOption({ index:0 });
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
/* a portfolio of the markup ticker alone, which the preview leaves out: UNIVERSE_EMPTY, the one short line in the
   toast and its message, which names the stock, in the row's tooltip (review PG-2); the strategy summary names the
   picked stock, the view bar's title where it costs no line (review PG-3) */
await at('hostile: the markup stock alone', async () => {
  await page.click('#sumbox [data-st="1"]');
  for (const t of ['MAPI', 'ACES', 'BBCA', 'BBRI', 'TLKM']) await page.click(`#pkChips [data-pk-del="${t}"]`);
  await toastText(/^1 stock left out \(see the — row\)$/);
  const tip = await page.getAttribute('#portSig td[data-tt]', 'data-tt');
  expect(tip.includes('UNIVERSE_EMPTY') && tip.includes('The picked stock was left out because its own data cannot serve the strategy'), `the row's tooltip ${tip}`);
  expect((await text('#sumbox [data-st="1"] em')).includes('onerror='), 'the step summary does not name the markup stock as text');
  const title = await text('#ctxTitle');
  expect(title.includes('onerror=') || title === '1 stock · max 5 positions', `the view bar's title ${title}`);
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

/* ---- the market with eight stocks every preview and run leaves out, on a phone's width (390 px) ---- */
await page.close(); await openPage({ width:390, height:844 });
const noSideScroll = async what => { const w = await page.evaluate(() => [...document.querySelectorAll('#pk, #pk *, #pkList, #pkList *')].filter(e => e.getClientRects().length && e.getBoundingClientRect().right > innerWidth + .5).map(e => e.id || e.className));
  expect(!w.length, `${what}: the picker reaches past the window's width: ${w.slice(0, 5)}`) };
await at('wide: the picker on a phone', async () => {
  await boot('?wide=1');
  await page.click('#sumbox [data-st="1"]');
  await page.click('#modeSeg [data-m="portfolio"]');
  await pickBySearch('BBCA');
  await page.click('#pkQ'); await page.fill('#pkQ', 'w');
  await page.waitForSelector('#pkQ[aria-expanded="true"]');
  const box = await page.evaluate(() => { const q = document.getElementById('pkQ').getBoundingClientRect(), l = document.getElementById('pkList').getBoundingClientRect(); return { below:l.top >= q.bottom, left:l.left, right:l.right, n:document.querySelectorAll('#pkList [role="option"]').length } });
  expect(box.below && box.left >= 0 && box.right <= 390 && box.n > 1, `the search list on a phone: ${JSON.stringify(box)}`);
  await noSideScroll('search list');
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
  // the filters and the group list stack in the panel's width
  const f = await page.locator('#pk .pk-f .fld').evaluateAll(fs => fs.map(e => Math.round(e.getBoundingClientRect().left)));
  expect(new Set(f).size === 1, `the filters do not stack: lefts ${f}`);
});
/* review PAGE-V1: the preview's warning is one short line even with many stocks left out */
await at('wide: the preview toast is one line', async () => {
  const p0 = await probe();
  await group('Sector', 'Wide (8)');
  await page.click('#pkAll');
  expect(await text('#pkN') === '9 / 12', `count ${await text('#pkN')}`);
  const msg = await toastText(/left out/);
  expect(msg === '8 stocks left out (see the — rows)', `toast ${msg}`);
  const lines = await page.evaluate(() => { const r = document.createRange(); r.selectNodeContents(document.getElementById('toast')); return new Set([...r.getClientRects()].map(x => Math.round(x.top))).size });
  const t = await page.evaluate(() => { const b = document.getElementById('toast').getBoundingClientRect(); return [b.left, b.right] });
  expect(lines === 1 && t[0] >= 0 && t[1] <= 390, `the toast takes ${lines} lines, from ${t[0]} to ${t[1]}`);
  expect((await toastsSince(p0.toasts)).length === 1, `toasts: ${await toastsSince(p0.toasts)}`);
  await noSideScroll('group list');
});
/* review PG-3: the view bar's title never takes more lines than the reference's title of the same count in the same
   view bar ("Banks · n stocks · max m positions"): on a phone, here the count alone; wide, three tickers (a resize) */
const titleLines = () => page.evaluate(() => {
  const el = document.getElementById('ctxTitle'), own = el.textContent;
  const lines = () => { const r = document.createRange(); r.selectNodeContents(el); return new Set([...r.getClientRects()].map(x => Math.round(x.top))).size };
  const mine = lines(); el.textContent = 'Banks · ' + own.match(/\d+ stocks? · max \d+ positions$/)[0];
  const ref = lines(); el.textContent = own;
  return { own, mine, ref };
});
await at('wide: the view bar title on a phone', async () => {
  const t = await titleLines();
  expect(t.mine <= t.ref && t.own === '9 stocks · max 5 positions', `the title "${t.own}" takes ${t.mine} lines, the reference's ${t.ref}`);
  await page.setViewportSize({ width:1440, height:900 });
  await page.waitForFunction(() => document.getElementById('ctxTitle').textContent === 'BBCA, WID1, WID2 +6 · 9 stocks · max 5 positions', null, { timeout:3000 });
  await page.setViewportSize({ width:390, height:844 });
  await page.waitForFunction(() => document.getElementById('ctxTitle').textContent === '9 stocks · max 5 positions', null, { timeout:3000 });
  expect((await text('#sumbox [data-st="1"] em')).startsWith('BBCA, WID1, WID2 +6 · max 5'), `step summary ${await text('#sumbox [data-st="1"] em')}`);
});
/* PF2: at most 12 stocks; add all stops at the limit and the next add is the limit toast */
await at('wide: the limit of 12 stocks', async () => {
  await group('Sector', 'Consumer (2)'); await page.click('#pkAll');
  await group('Sector', 'Finance (2)'); await page.click('#pkAll');
  expect(await text('#pkN') === '12 / 12', `count ${await text('#pkN')}`);
  await group('Sector', 'Infrastructure (1)');
  expect(await page.locator('#pkAll').isDisabled(), 'add all is enabled with no room left');
  await pickBySearch('TLKM');
  expect(await toastText(/^Limit reached/) === 'Limit reached: at most 12 stocks per portfolio.', 'no limit toast');
  expect((await chips()).length === 12 && !(await chips()).includes('TLKM'), 'a 13th stock was picked');
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
  await group('Sector', 'Any Sector');
});
/* review PAGE-V2: a left-out stock's row shows its chart without asking its events (edge-bff has none: 404) */
await at('wide: a left-out row after the run', async () => {
  await page.evaluate(() => document.getElementById('runTop').click());
  await page.waitForFunction(() => /^Done in /.test(document.getElementById('runNote').textContent), null, { timeout:30000 });
  await page.evaluate(() => document.querySelector('#viewSeg [data-v="signals"]').click());
  const p0 = await probe();
  await page.locator('#portSig [data-t="WID3"]').click();
  await page.waitForFunction(() => document.getElementById('sigTicker').value === 'WID3', null, { timeout:5000 });
  await page.waitForTimeout(500);
  const p1 = await probe();
  expect(!p1.events.slice(p0.events.length).length, `events asked for ${p1.events.slice(p0.events.length)}`);
  expect(p1.toasts === p0.toasts, `toasts: ${await toastsSince(p0.toasts)}`);
  await page.locator('#portSig [data-t="BBRI"]').click();
  await page.waitForFunction(n => (window.__events || []).length > n && window.__events.at(-1) === 'BBRI', p1.events.length, { timeout:5000 });
});
const unpickAll = async () => {
  await page.evaluate(() => { for (const b of [...document.querySelectorAll('#pkChips [data-pk-del]')]) b.click() });
  expect(await text('#pkN') === '0 / 12', `count ${await text('#pkN')}`);
};
const redraw = async () => {
  for (const z of await page.locator('#zoomSeg [data-z]').all()) await z.click();
  await page.locator('#sigChips [data-h]').first().click();
  await page.waitForTimeout(400);
};
/* review PG-1: a published stock without price files picked first: the chart cannot draw it (its toast once) and shows
   the next picked stock; the ticker select and the table, which asks the preview, are drawn all the same; a redraw
   loads nothing again and its row does not take the chart to it */
await at('wide: a stock without price data picked first', async () => {
  await unpickAll();
  const p0 = await probe();
  for (const q of ['WID0', 'BBCA', 'BBRI']) await pickBySearch(q);
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
  await page.waitForFunction(() => document.querySelectorAll('#portSig [data-t]').length === 3 && document.querySelector('#portSig [data-t="WID0"] td[data-tt]'), null, { timeout:10000 });
  expect(JSON.stringify(await chips()) === '["WID0","BBCA","BBRI"]', `chips ${await chips()}`);
  const opts = await page.locator('#sigTicker option').allInnerTexts();
  expect(JSON.stringify(opts) === '["BBCA","BBRI"]' && await page.inputValue('#sigTicker') === 'BBCA', `ticker select ${opts}, on ${await page.inputValue('#sigTicker')}`);
  expect((await page.getAttribute('#portSig [data-t="WID0"] td[data-tt]', 'data-tt')).includes('DATA_MISSING'), 'the row of WID0 does not give its DATA_MISSING');
  await redraw();
  await page.evaluate(() => document.querySelector('#portSig [data-t="WID0"]').click());
  await page.waitForTimeout(300);
  const p1 = await probe(), missing = (await toastsSince(p0.toasts)).filter(t => t === 'No price data is published for WID0.');
  expect(missing.length === 1, `the toast of the missing price data was shown ${missing.length} times`);
  expect(p1.asks > p0.asks, 'no preview was asked');
  expect(await page.inputValue('#sigTicker') === 'BBCA', `the chart left BBCA for ${await page.inputValue('#sigTicker')}`);
});
/* review PG-2: every picked stock left out (UNIVERSE_EMPTY): the toast is the one short line on a phone, every row "—"
   with that error in its tooltip, and a redraw (the zoom buttons, a legend chip) asks no preview and toasts nothing */
await at('wide: every picked stock left out', async () => {
  await unpickAll();
  for (const q of ['WID1', 'WID2']) await pickBySearch(q);
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
  const msg = await toastText(/^2 stocks left out/);
  expect(msg === '2 stocks left out (see the — rows)', `toast ${msg}`);
  const box = await page.evaluate(() => { const t = document.getElementById('toast'), b = t.getBoundingClientRect(), r = document.createRange(); r.selectNodeContents(t);
    return { lines:new Set([...r.getClientRects()].map(x => Math.round(x.top))).size, left:b.left, right:b.right } });
  expect(box.lines === 1 && box.left >= 0 && box.right <= 390, `the toast ${JSON.stringify(box)}`);
  const tips = await page.locator('#portSig [data-t] td[data-tt]').evaluateAll(ts => ts.map(t => t.dataset.tt.includes('UNIVERSE_EMPTY')));
  expect(tips.length === 2 && tips.every(Boolean), `row tooltips ${tips}`);
  const p0 = await probe();
  await redraw();
  const p1 = await probe();
  expect(p1.asks === p0.asks && p1.toasts === p0.toasts, `a redraw asked ${p1.asks - p0.asks} preview(s) and showed ${await toastsSince(p0.toasts)}`);
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
