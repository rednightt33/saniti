/* 1:1 check of the TypeScript backtest page against the reference: the user's design file (EXEC-BACKTEST-REVAMP Tahap D,
   user 2026-11-15 "1 setuju, 2a": it replaces backtest.html as the 1:1 reference; it was built on a compiled copy of the
   page, so it runs the same synthetic market and mock-up engine as /backtest-app/?fixture=reference, tests/fixture).
   Each page runs in a fresh browser context, at the same viewports (1440, 1024 and 390 px, as Agent 10's review) and in
   both themes; the script saves full-page screenshots, the text of every panel, the markup the page builds and its
   localStorage, at load and after each scenario step (scenarios.mjs). Pixel comparison: diff.py.
   Deterministic conditions on both sides:
   - fonts: no network; the Google Fonts stylesheet is answered empty, so both pages render with the installed Inter;
   - clock: performance.now() is 0, so the run note and "Last run" read "0 ms" (the run's real duration otherwise);
   - Math.random (card ids only) is a fixed sequence;
   - theme: the page follows EDGE's key (edge-auth-monitor-theme, decision 2a), set before load; the design keeps its own
     theme button, pressed once for dark.
   Usage: BACKTEST_REFERENCE_HTML=<design file> node tests/visual/compare.mjs [out dir] [scenario]
   BACKTEST_VISUAL_THEMES=light (or dark) runs one theme; BACKTEST_COMPARE_SELF=1 runs the reference against itself: the
   noise floor of the method. */
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright');   // the preinstalled Playwright (global NODE_PATH)
import { access, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { serve } from './serve.mjs';
import { SCENARIOS, TS_ONLY } from './scenarios.mjs';

/* the reference is the user's design file, which is not kept in the repository */
const reference = process.env.BACKTEST_REFERENCE_HTML;
if (!reference) { console.error('set BACKTEST_REFERENCE_HTML to the reference page (the user\'s design file)'); process.exit(2) }
try { await access(reference) } catch { console.error(`reference page not found: ${reference}`); process.exit(2) }
const out = process.argv[2] || process.env.BACKTEST_VISUAL_OUT || join(tmpdir(), 'backtest-visual');
const only = process.argv[3];
const VIEWPORTS = [[1440, 900], [1024, 768], [390, 844]];
const THEMES = (process.env.BACKTEST_VISUAL_THEMES || 'light,dark').split(',');
const PANELS = ['#xsHd', '#rail', '#sumbox', '#builder', '#runNote', '.viewbar', '#xfb', '#sigChips', '#laneLabels', '#xsig', '#portSig', '#resCard', '#cw', '#cwPop',
  '#menu', '#tip', '#toast'];
const MARKUP = ['#xsHd', '#rail', '#sumbox', '#builder', '.viewbar', '#xfb', '#sigChips', '#laneLabels', '#xsig', '#portSig', '#resCard', '#cwSide', '#cwRail',
  '#cwList', '#cwStrat', '#cwPop', '#menu', '#tip', '#toast'];

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
  for (const [w, h] of VIEWPORTS) for (const theme of THEMES) {
    const tsUrl = process.env.BACKTEST_COMPARE_SELF ? `${origin}/ref/` : `${origin}/backtest-app/?fixture=design`;
    const at = `${w}x${h}${theme === 'light' ? '' : '-' + theme}`;
    for (const [side, url] of [['ref', `${origin}/ref/`], ['ts', tsUrl]]) {
      const dir = `${out}/${at}/${side}`; await mkdir(dir, { recursive:true });
      const context = await browser.newContext({ viewport:{ width:w, height:h }, deviceScaleFactor:1 });
      await context.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.fulfill({ status:200, contentType:'text/css', body:'' }));
      await context.addInitScript(t => {
        performance.now = () => 0;
        let s = 20261026; Math.random = () => (s = s * 16807 % 2147483647) / 2147483647;
        try { localStorage.setItem('edge-auth-monitor-theme', t) } catch { /* storage off: light */ }
      }, theme);
      const page = await context.newPage();
      page.on('pageerror', e => errors.push(`${side} ${at}: ${e.message}`));
      page.on('console', m => { if (m.type() === 'error') errors.push(`${side} ${at} console: ${m.text()}`) });
      await page.goto(url, { waitUntil:'networkidle' });
      await page.evaluate(() => document.fonts.ready);
      // the design keeps its own theme button (hidden on the page, which follows EDGE)
      if (theme === 'dark') await page.evaluate(() => { const b = document.getElementById('themeBtn'); if (b && document.documentElement.dataset.theme !== 'dark') b.click() });
      // both start without a run (the design's own start, D-no-autorun): ready once the builder shows its step
      await page.waitForSelector('#builder .bs.on', { timeout:60_000 });
      await page.mouse.move(1, 1);
      await snap(page, dir, '00-boot');
      for (const [name, steps] of Object.entries(SCENARIOS)) {
        if (only && name !== only) continue;
        if (w < 600 && name.startsWith('d-')) continue;           // desktop-only steps
        if (side === 'ref' && TS_ONLY.has(name)) continue;        // the picker's own steps (no reference to compare)
        try { await steps(page, side) }
        catch (e) { errors.push(`${side} ${at} ${name}: ${e.message.split('\n')[0]}`); continue }
        await snap(page, dir, name);
      }
      await context.close();
    }
    console.log(`${at} done`);
  }
} finally {
  await browser.close(); server.close();
}
await writeFile(`${out}/errors.json`, JSON.stringify(errors, null, 1));
console.log(`done; page errors: ${errors.length}${errors.length ? '\n' + errors.join('\n') : ''}`);
