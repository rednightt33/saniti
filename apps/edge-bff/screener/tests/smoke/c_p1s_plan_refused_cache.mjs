/* C-P1S independent check (EXEC-MU-ACCOUNTS, ultracode re-check of Phases 0-3b; CONTRACT.md 8b decision D5 "a lowered
   plan loses read access to old content until it is raised again", 8b "a downgrade takes effect on the next request
   (... the browser cache is per sha and never announced to a capped user)", 13.7 "a free principal is refused on every
   second path to the same content").

   The Screener's cached paint (src/api/boot-cache.ts, report PAGE LOAD SEQUENCE 6c.3-6c.5) keeps the last screen's
   result in the browser (IndexedDB terminal-files + localStorage scr.boot), keyed by the login only. app.ts bootPage
   draws it after the session answer (S3: "only after an authenticated answer"), which every signed-in principal gets
   whatever its plan, and keeps it when the catalog is then refused (S4: `if (!ctx.catalog) bootFailed(...) else
   { ctx.runError = ...; refresh('results') }`; results.ts shows the rows under a note when there are rows). So the same
   login, after its plan lost the Screener (screener.view: the catalog, universe, run and items all answer 403
   CAPABILITY_REQUIRED), still sees the last result's rows (tickers, prices, metric values) from the browser.

   Run (from apps/edge-bff/screener): npx vite build --mode smoke && node tests/smoke/c_p1s_plan_refused_cache.mjs
   Exit 1 while the defect holds. */
import { createRequire } from 'node:module';
import { serve } from './serve.mjs';
const { chromium } = createRequire(import.meta.url)('playwright');

const srv = await serve('dist-smoke');
const browser = await chromium.launch();
const failures = [];
try {
  const ctx = await browser.newContext({ viewport:{ width:1440, height:950 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(15000);
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\/|\/fonts\/[A-Za-z0-9-]+\.css$/, r => r.fulfill({ status:200, contentType:'text/css', body:'' }));
  const go = q => page.goto(`${srv.origin}/screener-app/${q || ''}`);
  const ready = () => page.waitForSelector('#app[data-boot="results"]', { timeout:15000 });
  const idle = () => page.waitForFunction(() => !document.querySelector('#resMeta .ml-loading') && !document.querySelector('#pageActs .top-screen[aria-busy]'), null, { timeout:10000 });
  const rows = () => page.locator('#resPane table.res tbody tr').count();

  // 1. the plan holds the Screener: a preset screen runs and its result is cached for this login
  await go(); await ready(); await page.waitForTimeout(500);
  await page.evaluate(() => { for (const k of Object.keys(localStorage)) if (k.startsWith('scr.')) localStorage.removeItem(k) });
  await go(); await ready();
  await page.click('[data-open="p:golden"]');
  await page.evaluate(() => document.activeElement?.blur?.()); await page.waitForTimeout(30);
  await page.click('#pageActs .top-screen'); await idle();
  await page.waitForTimeout(800);                                  // the pointer is written after the answer
  const before = await rows();
  if (!before) failures.push('setup: the preset screen showed no rows to cache');

  // 2. the same login, now on a plan without the Screener: the server refuses the catalog and every run
  await go('?fail=catalog:CAPABILITY_REQUIRED:403:9,run:CAPABILITY_REQUIRED:403:9');
  await page.waitForTimeout(2500);
  const after = await rows();
  const shown = await page.locator('#resPane').innerText();
  if (after > 0) failures.push(`after the plan refused the Screener (403 CAPABILITY_REQUIRED on the catalog and the run), the page still shows ${after} rows of the cached last result (before: ${before}); first lines: ${JSON.stringify(shown.split('\n').slice(0, 6))}`);
} finally {
  await browser.close(); await srv.close();
}
if (failures.length) { console.log('FAIL\n' + failures.join('\n')); process.exit(1) }
console.log('ok: a refused plan shows nothing of the cached result');
