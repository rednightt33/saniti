/* The 1:1 visual check of the port (report FRONTEND INTEGRATION 9.1, TEST PLAN 10b.12): the fixture build (the
   prototype's synthetic market, `vite build --mode fixture` into dist-fixture/) is opened in Chromium in the
   prototype's states and screenshotted, light and dark, at 1440 and 390 px, for a side-by-side comparison with the
   prototype (screener EDGE layout.html, the user's upload, never executed by the tests: it is untrusted input). Each
   state also checks that the prototype's structure is there (its containers and classes, report 9.2 KEEP rows), so a
   layout regression fails without a human looking.
   Usage: npm run build:fixture && node tests/visual/shots.mjs <out-dir>   (default: ./visual-out, not kept in git) */
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import { serve } from '../smoke/serve.mjs';
const { chromium } = createRequire(import.meta.url)('playwright');

const OUT = process.argv[2] || 'visual-out';
await mkdir(OUT, { recursive:true });
const srv = await serve('dist-fixture');
const browser = await chromium.launch();
const fails = [], shots = [];
const STRUCTURE = ['main.page .page-head h1', '#pageActs .btn', '#cardU .toolbar .qf', '#cardU .chipbar .fchip', '#cardU .presets .seg', '#cardU .chips-row .pchip',
  '#cardC .builder-h .tgl', '#cardC .adder .searchbox', '#cardR .tbl-meta', '#cardR table.res thead th', '#cardR .tbl-foot'];

for (const theme of ['light', 'dark']) for (const vp of [{ width:1440, height:950 }, { width:390, height:844 }]) {
  const ctx = await browser.newContext({ viewport:vp });
  const page = await ctx.newPage();
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, r => r.fulfill({ status:200, contentType:'text/css', body:'' }));
  await page.addInitScript(t => { try { localStorage.setItem('edge-auth-monitor-theme', t) } catch {} }, theme);
  page.on('pageerror', e => fails.push(`${theme} ${vp.width}: ${e.message}`));
  await page.goto(`${srv.origin}/screener-app/`);
  await page.waitForSelector('#app[data-boot="results"]');
  const shot = async name => { const f = `${OUT}/${name}-${theme}-${vp.width}.png`; await page.screenshot({ path:f, fullPage:true }); shots.push(f) };
  for (const sel of STRUCTURE) if (!await page.locator(sel).count()) fails.push(`${theme} ${vp.width}: missing ${sel}`);
  await shot('01-empty');
  await page.click('[data-open="p:minervini"]');
  await page.waitForFunction(() => !document.querySelector('#resMeta .ml-loading') && /match/.test(document.getElementById('resMeta').innerText));
  if (!await page.locator('#condList .mc[data-card]').count()) fails.push(`${theme} ${vp.width}: no condition cards`);
  await shot('02-preset');
  await page.locator('#resPane tbody tr').first().click();
  await page.waitForSelector('#dChart canvas');
  await page.waitForTimeout(300);
  await shot('03-preview');
  if (vp.width > 900) {
    await page.click('[data-act="drawer"]'); await page.waitForTimeout(150); await shot('04-drawer'); await page.keyboard.press('Escape');
    await page.click('[data-act="browse"]'); await page.waitForTimeout(150); await shot('05-browser'); await page.keyboard.press('Escape');
    await page.click('[data-qf="sector"]'); await page.waitForTimeout(150); await shot('06-sector-popover'); await page.keyboard.press('Escape');
  }
  await ctx.close();
}
await browser.close(); await srv.close();
console.log(shots.join('\n'));
if (fails.length) { console.error(fails.join('\n')); process.exit(1) }
console.log(`\nvisual: ${shots.length} screenshots in ${OUT}`);
