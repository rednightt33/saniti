/* 1:1 check of the TypeScript terminal against the reference page (FRONTEND_ARCHITECTURE.md section 4).
   Both pages run on the same synthetic data (/terminal-app/?fixture=reference), each in a fresh browser context, at
   the same viewports; the script saves full-page screenshots and the text of every panel, then scenario steps
   (interactions) after which it saves both again. Pixel comparison: diff.py.
   Usage: TERMINAL_REFERENCE_HTML=<file> node tests/visual/compare.mjs <out dir> [scenario] */
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');   // the preinstalled Playwright (global NODE_PATH)
import { mkdir, writeFile } from 'node:fs/promises';
import { serve } from './serve.mjs';
import { SCENARIOS } from './scenarios.mjs';

const reference = process.env.TERMINAL_REFERENCE_HTML;
if (!reference) { console.error('TERMINAL_REFERENCE_HTML is required'); process.exit(2) }
const out = process.argv[2] || 'visual-out';
const only = process.argv[3];
const VIEWPORTS = [[1600, 1000], [1280, 800], [390, 844]];
const MARKUP = ['#statsPanel', '#brokerPanel', '.tvbar', '#addPanel', '.chart-legend', '.flow-head', '.flow-legend', '#indPop', '#evPop',
  '.ev-layer', '.ev-tip', '.dr-bar', '.dr-menu', '.idlg-back', '.gp-backdrop', '.cs-pop', '.st-tip', '.ind-tip', '.ind-row'];
const PANELS = ['#statsPanel', '#brokerPanel', '#flowSummary', '#flowTip', '.chart-legend', '#seriesTabs', '#evList', '#indList', '.tvbar'];

async function snap(page, dir, name) {
  await page.waitForTimeout(900);              // past the reference's 300 ms layout poll (event markers, right axis) and its CSS transitions
  await page.screenshot({ path:`${dir}/${name}.png`, fullPage:true });
  const text = await page.evaluate(sel => Object.fromEntries(sel.map(s => [s, document.querySelector(s)?.innerText ?? null])), PANELS);
  /* the markup of every panel and overlay the page builds (canvas pixels are compared in the screenshot) */
  const html = await page.evaluate(sel => Object.fromEntries(sel.map(s => [s, [...document.querySelectorAll(s)].map(e => e.outerHTML).join('\n')])), MARKUP);
  const storage = await page.evaluate(() => Object.fromEntries(Object.keys(localStorage).sort().map(k => [k, localStorage.getItem(k)])));
  await writeFile(`${dir}/${name}.json`, JSON.stringify({ text, html, storage }, null, 1));
}

const { server, origin } = await serve(reference);
const browser = await chromium.launch();
const errors = [];
/* web fonts: every browser context has its own HTTP cache, so a font download would land at a different moment on each
   page and move the opening view by a bar (the chart meets the font earlier or later). The fonts are fetched once and
   then served from memory to every page, so both pages meet the same conditions. */
const fontCache = new Map();
async function fonts(context) {
  await context.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, async route => {
    const url = route.request().url();
    if (!fontCache.has(url)) {
      const r = await route.fetch();
      fontCache.set(url, { status:r.status(), headers:r.headers(), body:await r.body() });
    }
    await route.fulfill(fontCache.get(url));
  });
}
{
  const warm = await browser.newContext(); await fonts(warm); const p = await warm.newPage();
  await p.goto(`${origin}/ref/`, { waitUntil:'networkidle' }); await p.evaluate(() => document.fonts.ready); await warm.close();
}
try {
  for (const [w, h] of VIEWPORTS) {
    // TERMINAL_COMPARE_SELF=1 runs the reference against itself: the noise floor of the method
    const tsUrl = process.env.TERMINAL_COMPARE_SELF ? `${origin}/ref/` : `${origin}/terminal-app/?fixture=reference`;
    for (const [side, url] of [['ref', `${origin}/ref/`], ['ts', tsUrl]]) {
      const dir = `${out}/${w}x${h}/${side}`; await mkdir(dir, { recursive:true });
      const context = await browser.newContext({ viewport:{ width:w, height:h }, deviceScaleFactor:1 });
      await fonts(context);
      const page = await context.newPage();
      page.on('pageerror', e => errors.push(`${side} ${w}x${h}: ${e.message}`));
      page.on('console', m => { if (m.type() === 'error') errors.push(`${side} ${w}x${h} console: ${m.text()}`) });
      await page.goto(url, { waitUntil:'networkidle' });
      await page.evaluate(() => document.fonts.ready);
      await page.waitForTimeout(1600);
      await page.mouse.move(1, 1);
      await snap(page, dir, '00-initial');
      for (const [name, steps] of Object.entries(SCENARIOS)) {
        if (only && name !== only) continue;
        if (w < 600 && name.startsWith('d-')) continue;           // desktop-only steps (side panels are stacked on a phone)
        await steps(page);
        await snap(page, dir, name);
      }
      await context.close();
    }
  }
} finally {
  await browser.close(); server.close();
}
await writeFile(`${out}/errors.json`, JSON.stringify(errors, null, 1));
console.log(`done; page errors: ${errors.length}`);
