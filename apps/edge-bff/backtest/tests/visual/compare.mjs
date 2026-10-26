/* 1:1 check of the TypeScript backtest page against the reference page (backtest.html). Both pages run on the same
   synthetic market and mock-up engine (/backtest-app/?fixture=reference, tests/fixture), each in a fresh browser
   context, at the same viewports; the script saves full-page screenshots, the text of every panel, the markup the page
   builds and its localStorage, at load and after each scenario step (scenarios.mjs). Pixel comparison: diff.py.
   Deterministic conditions on both sides:
   - fonts: no network; the Google Fonts stylesheet is answered empty, so both pages render with the installed Inter;
   - clock: performance.now() is 0, so the run note and "Last run" read "0 ms" (the run's real duration otherwise);
   - Math.random (card ids only) is a fixed sequence.
   Usage: BACKTEST_REFERENCE_HTML=<file> node tests/visual/compare.mjs [out dir] [scenario]
   BACKTEST_COMPARE_SELF=1 runs the reference against itself: the noise floor of the method. */
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');   // the preinstalled Playwright (global NODE_PATH)
import { access, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { serve } from './serve.mjs';
import { SCENARIOS } from './scenarios.mjs';

/* the reference page is the user's backtest.html, which is not kept in the repository */
const reference = process.env.BACKTEST_REFERENCE_HTML;
if (!reference) { console.error('set BACKTEST_REFERENCE_HTML to the reference page (backtest.html)'); process.exit(2) }
try { await access(reference) } catch { console.error(`reference page not found: ${reference}`); process.exit(2) }
const out = process.argv[2] || process.env.BACKTEST_VISUAL_OUT || join(tmpdir(), 'backtest-visual');
const only = process.argv[3];
const VIEWPORTS = [[1600, 1000], [1280, 800], [390, 844]];
const PANELS = ['#rail', '#sumbox', '#builder', '#runNote', '.viewbar', '#sigChips', '#laneLabels', '#portSig', '#resCard', '#ews', '#menu', '#tip', '#toast'];
const MARKUP = ['#rail', '#sumbox', '#builder', '.viewbar', '#sigChips', '#laneLabels', '#portSig', '#resCard', '#wsTabs', '#wsRule', '#wsStats', '#wsCats',
  '#wsList', '#wsTable', '#wsDet', '#menu', '#tip', '#toast'];

async function snap(page, dir, name) {
  await page.waitForTimeout(900);              // past the 30 ms run delay, the charts' first frames and the CSS transitions
  await page.screenshot({ path:`${dir}/${name}.png`, fullPage:true });
  const text = await page.evaluate(sel => Object.fromEntries(sel.map(s => [s, document.querySelector(s)?.innerText ?? null])), PANELS);
  /* the markup of every panel and overlay the page builds (canvas pixels are compared in the screenshot) */
  const html = await page.evaluate(sel => Object.fromEntries(sel.map(s => [s, [...document.querySelectorAll(s)].map(e => e.outerHTML).join('\n')])), MARKUP);
  const storage = await page.evaluate(() => Object.fromEntries(Object.keys(localStorage).sort().map(k => [k, localStorage.getItem(k)])));
  await writeFile(`${dir}/${name}.json`, JSON.stringify({ text, html, storage }, null, 1));
  /* a toast stays 2.2 s: the next step starts after it, so no snapshot depends on how long a step took */
  await page.waitForFunction(() => document.getElementById('toast').hidden, null, { timeout:5000 });
}

const { server, origin } = await serve(reference);
const browser = await chromium.launch();
const errors = [];
try {
  for (const [w, h] of VIEWPORTS) {
    const tsUrl = process.env.BACKTEST_COMPARE_SELF ? `${origin}/ref/` : `${origin}/backtest-app/?fixture=reference`;
    for (const [side, url] of [['ref', `${origin}/ref/`], ['ts', tsUrl]]) {
      const dir = `${out}/${w}x${h}/${side}`; await mkdir(dir, { recursive:true });
      const context = await browser.newContext({ viewport:{ width:w, height:h }, deviceScaleFactor:1 });
      await context.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.fulfill({ status:200, contentType:'text/css', body:'' }));
      await context.addInitScript(() => {
        performance.now = () => 0;
        let s = 20261026; Math.random = () => (s = s * 16807 % 2147483647) / 2147483647;
      });
      const page = await context.newPage();
      page.on('pageerror', e => errors.push(`${side} ${w}x${h}: ${e.message}`));
      page.on('console', m => { if (m.type() === 'error') errors.push(`${side} ${w}x${h} console: ${m.text()}`) });
      await page.goto(url, { waitUntil:'networkidle' });
      await page.evaluate(() => document.fonts.ready);
      await page.waitForFunction(() => /^Done in/.test(document.getElementById('runNote').textContent), null, { timeout:60_000 });
      await page.mouse.move(1, 1);
      await snap(page, dir, '00-boot');
      for (const [name, steps] of Object.entries(SCENARIOS)) {
        if (only && name !== only) continue;
        if (w < 600 && name.startsWith('d-')) continue;           // desktop-only steps
        try { await steps(page) }
        catch (e) { errors.push(`${side} ${w}x${h} ${name}: ${e.message.split('\n')[0]}`); continue }
        await snap(page, dir, name);
      }
      await context.close();
    }
    console.log(`${w}x${h} done`);
  }
} finally {
  await browser.close(); server.close();
}
await writeFile(`${out}/errors.json`, JSON.stringify(errors, null, 1));
console.log(`done; page errors: ${errors.length}${errors.length ? '\n' + errors.join('\n') : ''}`);
