/* The visual check of the port (report FRONTEND INTEGRATION 9.1, TEST PLAN 10b.12), on the "Type A three-panel v21"
   page (EXEC-SCREENER-V21): the fixture build (the prototype's synthetic market, `vite build --mode fixture` into
   dist-fixture/) is opened in Chromium in the design's states and screenshotted, light and dark, at 1440, 1100 and
   390 px, for a side-by-side comparison with the design reference (the user's upload, never executed by the tests: it
   is untrusted input; the comparison runs from a scratch folder, see the phase C report). Each state also checks that
   the v21 structure is there (panes, rails, gutters, builder tabs, the Screen now controls, More filters with its group
   list, the Add a condition window, the column picker), so a layout regression fails without a human looking, and the
   checks a picture cannot make: no horizontal page scroll, Tab kept inside a modal window, Escape closing it with the
   focus back on its opener, the pane borders on the keyboard, and no animation left under prefers-reduced-motion.
   The table follows the explicit Screen now gate: a preset only marks the table out of date (shot 02-pending), Screen
   now runs it (shot 03-preset).
   Usage: npm run build:fixture && node tests/visual/shots.mjs <out-dir>   (default: ./visual-out, not kept in git;
   VISUAL_DIR=<build dir under the app root> to shoot another build) */
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import { serve } from '../smoke/serve.mjs';
const { chromium } = createRequire(import.meta.url)('playwright');

const OUT = process.argv[2] || 'visual-out';
await mkdir(OUT, { recursive:true });
const srv = await serve(process.env.VISUAL_DIR || 'dist-fixture');
const browser = await chromium.launch();
const fails = [], shots = [];
/* the v21 structure, in every viewport (index.html, src/layout/, src/screen-gate.ts) */
const STRUCTURE = ['main.page .page-head h1', '#pageActs .top-screen[data-screen]', '#pageActs [data-hd="add"]', '#pageActs [data-hd="export"]',
  '#cardU .toolbar .qf', '#cardU .toolbar .qf-static', '#cardU .chipbar .fchip', '#cardU .presets .seg', '#cardU .chips-row .pchip', '#cardU .na-btn',
  '#cardC .builder-h .tgl', '#cardC .adder .searchbox', '#cardC #screenBar .screen-bar [data-screen]', '#screenHint',
  '#center #pendBar', '#cardR .tbl-meta', '#cardR table.res thead th', '#cardR .tbl-foot', '#resTools [data-act="cols"]', '#preview', '#colPop', '#naPop'];
/* only where the three panes stand side by side (above 900 px): rails, pane borders, builder tabs */
const WIDE = ['#lRail.rail', '#rRail.rail', '#uRail.rail', '.gutter[data-k="lw"][role="separator"]', '.gutter[data-k="rw"][role="separator"]',
  '#cardC .btabs[role="tablist"] [role="tab"][data-btab]'];
const VIEWPORTS = [{ width:1440, height:950 }, { width:1100, height:900 }, { width:390, height:844 }];
const check = async (page, where, sels) => { for (const sel of sels) if (!await page.locator(sel).count()) fails.push(`${where}: missing ${sel}`) };
const noSideScroll = async (page, where) => {
  const w = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (w > 1) fails.push(`${where}: the page scrolls sideways by ${w}px`);
};
const idle = page => page.waitForFunction(() => !document.querySelector('#resMeta .ml-loading') && !document.querySelector('#pageActs .top-screen[aria-busy]'), null, { timeout:15000 });
/** Tab and Shift+Tab stay inside `box`; Escape closes it and puts the focus back on the element that opened it */
async function trap(page, where, box, opener) {
  let out = 0;
  for (let i = 0; i < 40; i++) { await page.keyboard.press('Tab'); if (!await page.evaluate(b => !!document.activeElement?.closest(b), box)) out++ }
  for (let i = 0; i < 5; i++) { await page.keyboard.press('Shift+Tab'); if (!await page.evaluate(b => !!document.activeElement?.closest(b), box)) out++ }
  if (out) fails.push(`${where}: Tab left ${box} ${out} times`);
  await page.keyboard.press('Escape'); await page.waitForTimeout(150);
  if (await page.locator(box).count() && await page.locator(box).first().isVisible()) fails.push(`${where}: Escape did not close ${box}`);
  if (opener && !await page.evaluate(o => !!document.activeElement?.closest(o), opener)) fails.push(`${where}: the focus did not return to ${opener} (${await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 80))})`);
}

for (const theme of ['light', 'dark']) for (const vp of VIEWPORTS) {
  const ctx = await browser.newContext({ viewport:vp });
  const page = await ctx.newPage();
  page.setDefaultTimeout(10000);
  const tag = `${theme} ${vp.width}`, wide = vp.width > 900;
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, r => r.fulfill({ status:200, contentType:'text/css', body:'' }));
  await page.addInitScript(t => { try { localStorage.setItem('edge-auth-monitor-theme', t) } catch {} }, theme);
  page.on('pageerror', e => fails.push(`${tag}: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') fails.push(`${tag} console: ${m.text()}`) });
  await page.goto(`${srv.origin}/screener-app/`);
  await page.waitForSelector('#app[data-boot="results"]');
  await page.waitForTimeout(300);
  const shot = async name => { const f = `${OUT}/${name}-${theme}-${vp.width}.png`; await page.screenshot({ path:f, fullPage:true }); shots.push(f) };
  try {
    await check(page, tag, STRUCTURE); if (wide) await check(page, tag, WIDE);
    await noSideScroll(page, `${tag} empty`);
    await shot('01-empty');
    // a preset marks the table out of date and sends nothing (product decision 6); Screen now runs it
    await page.click('[data-open="p:minervini"]'); await page.waitForTimeout(300);
    if (!await page.locator('#pendBar:not([hidden])').count() || !/90 instruments/.test(await page.locator('#resMeta').textContent())) fails.push(`${tag}: the preset did not leave the previous table marked out of date`);
    await shot('02-pending');
    await page.click('#pageActs .top-screen'); await idle(page);
    if (!/match/.test(await page.locator('#resMeta').textContent())) fails.push(`${tag}: Screen now gave no match line`);
    if (!await page.locator('#condList .mc[data-card]').count()) fails.push(`${tag}: no condition cards`);
    if (!await page.locator('#pendBar[hidden]').count()) fails.push(`${tag}: the out-of-date bar stayed after Screen now`);
    await noSideScroll(page, `${tag} preset`);
    await page.waitForTimeout(400);
    await shot('03-preset');
    // the chart pane: open by default above 1100 px with the top result (layout/index.ts autoPick); else a row opens it
    if (!await page.locator('#dChart canvas').count()) await page.locator('#resPane tbody tr').first().click();
    await page.waitForSelector('#dChart canvas');
    await page.waitForTimeout(300);
    await shot('04-preview');
    if (vp.width > 1100 && !await page.locator('body.has-pv').count()) fails.push(`${tag}: the chart pane is not a column of its own above 1100 px`);
    // where the chart pane slides over the table (1100 px and below), Escape closes it
    if (await page.evaluate(() => getComputedStyle(document.getElementById('preview')).position === 'fixed')) {
      await page.mouse.click(4, 4); await page.keyboard.press('Escape'); await page.waitForTimeout(250);
      if (!await page.locator('#preview[hidden]').count()) fails.push(`${tag}: Escape did not close the chart pane over the table`);
    }
    if (wide) {
      // More filters: a modal dialog with its group list; Tab stays inside; Escape returns to the opener
      await page.click('[data-act="drawer"]'); await page.waitForTimeout(200);
      await check(page, `${tag} More filters`, ['.drawer[role="dialog"][aria-modal="true"] .fnav [data-fk]', '.drawer .drawer-b .dsec']);
      await shot('05-filters');
      await trap(page, `${tag} More filters`, '.drawer', '[data-act="drawer"]');
      // Add a condition, the one way to add (EXEC-SCREENER-ADD): groups, rows with timeframe, condition, threshold, Add;
      // no detailed browser
      await page.click('#pageActs [data-hd="add"]'); await page.waitForTimeout(250);
      await check(page, `${tag} Add a condition`, ['.dialog.qwin[role="dialog"]', '#acg [data-ag="__on"]', '#acl .qcols', '#acl .qrow .tf-add select.tf-sel', '#acl .qrow [data-af="opt"]', '#acl .qrow [data-qact]']);
      if (await page.locator('.qwin [data-qbrowse], .dialog.ib').count()) fails.push(`${tag}: the detailed Indicators browser is still reachable`);
      await shot('06-add-condition');
      await trap(page, `${tag} Add a condition`, '.dialog.qwin', '#pageActs [data-hd="add"]');
      // the column picker: two columns added, then shown in the table
      await page.click('#resTools [data-act="cols"]'); await page.waitForTimeout(150);
      if (!await page.evaluate(() => !!document.activeElement?.closest('#colPop'))) fails.push(`${tag}: the column picker did not take the focus`);
      await page.check('#colPop [data-col="ret_1m"]'); await page.check('#colPop [data-col="rvol"]'); await page.waitForTimeout(150);
      await shot('07-columns');
      await page.keyboard.press('Escape'); await page.waitForTimeout(600);
      if (!await page.evaluate(() => document.activeElement?.matches('#resTools [data-act="cols"]'))) fails.push(`${tag}: Escape did not return the focus to Add column`);
      await check(page, `${tag} extra columns`, ['#resPane th[data-xid="ret_1m"] .xcol-x', '#resPane th[data-xid="rvol"]']);
      const cells = await page.locator('#resPane tbody tr').first().evaluate(tr => { const ths = [...document.querySelectorAll('#resPane thead th')]; return ['ret_1m', 'rvol'].map(id => tr.children[ths.findIndex(t => t.dataset.xid === id)]?.textContent?.trim()) });
      if (!/^([+−]\d[\d,.]*%|n\/a|…)$/.test(cells[0] || '') || !/^(\d[\d,.]*×|n\/a|…)$/.test(cells[1] || '')) fails.push(`${tag}: extra column cells not in their catalog format: ${JSON.stringify(cells)}`);
      await shot('08-extra-columns');
      // the pane border on the keyboard: arrows resize, Home resets, Enter folds the builder to its rail
      const g = page.locator('.gutter[data-k="lw"]'); await g.focus();
      const w0 = Number(await g.getAttribute('aria-valuenow')); await page.keyboard.press('ArrowRight'); await page.waitForTimeout(100);
      const w1 = Number(await g.getAttribute('aria-valuenow'));
      if (!(w1 > w0)) fails.push(`${tag}: ArrowRight on the builder border did not widen it (${w0} -> ${w1})`);
      await page.keyboard.press('Home'); await page.keyboard.press('Enter'); await page.waitForTimeout(200);
      if (!await page.evaluate(() => document.body.classList.contains('lcol') && document.activeElement?.id === 'lRail')) fails.push(`${tag}: Enter on the border did not fold the builder to its rail`);
      await page.click('#rRail').catch(() => {}); await page.waitForTimeout(100);
      await shot('09-rails');
      await page.click('#lRail'); await page.waitForTimeout(200);
      if (await page.evaluate(() => document.body.classList.contains('lcol'))) fails.push(`${tag}: the builder rail did not reopen the builder`);
      await page.evaluate(() => { for (const k of Object.keys(localStorage)) if (k.startsWith('scr.')) localStorage.removeItem(k) });
    } else {
      // stacked: the sector popover below 900 px
      await page.click('[data-qf="sector"]'); await page.waitForTimeout(150); await shot('05-sector-popover'); await page.keyboard.press('Escape');
    }
    await noSideScroll(page, `${tag} end`);
  } catch (e) { fails.push(`${tag}: ${e.message.split('\n')[0]}`) }
  await ctx.close();
}

/* prefers-reduced-motion: nothing moves on the v21 page: no animation and no transition of position or size (colour and
   opacity fades are listed in the output, not failed); the loading ring aside (a status, not motion for its own sake) */
{
  const ctx = await browser.newContext({ viewport:{ width:1440, height:950 }, reducedMotion:'reduce' });
  const page = await ctx.newPage();
  await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, r => r.fulfill({ status:200, contentType:'text/css', body:'' }));
  await page.goto(`${srv.origin}/screener-app/`); await page.waitForSelector('#app[data-boot="results"]');
  await page.click('[data-open="p:minervini"]'); await page.click('#pageActs .top-screen'); await idle(page);
  await page.click('[data-act="drawer"]'); await page.waitForTimeout(200);
  const moving = await page.evaluate(() => {
    const out = [], secs = s => Math.max(0, ...s.split(',').map(x => parseFloat(x) * (x.trim().endsWith('ms') ? 0.001 : 1)));
    for (const el of document.querySelectorAll('body *')) {
      if (el.closest('.ml-spin,.ml-loading')) continue;
      const cs = getComputedStyle(el), a = cs.animationName !== 'none' ? secs(cs.animationDuration) : 0;
      const props = cs.transitionProperty.split(',').map(x => x.trim()), durs = cs.transitionDuration.split(',');
      const move = props.filter((p, i) => secs(durs[i % durs.length]) > 0.01 && /^(all|transform|translate|scale|rotate|left|top|right|bottom|width|height|max-height|max-width|margin.*|inset.*)$/.test(p));
      const fade = props.filter((p, i) => secs(durs[i % durs.length]) > 0.01 && !move.includes(p));
      const name = `${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''}`;
      if (a > 0.01) out.push(['move', `${name} animation ${cs.animationName} ${cs.animationDuration}`]);
      if (move.length) out.push(['move', `${name} transition ${move.join('/')}`]);
      if (fade.length) out.push(['fade', `${name} transition ${fade.join('/')}`]);
    }
    return out.map(x => x.join(' ')).filter((v, i, all) => all.indexOf(v) === i);
  });
  const moves = moving.filter(x => x.startsWith('move ')), fades = moving.filter(x => x.startsWith('fade '));
  console.log(`reduced motion: ${fades.length} colour/opacity fades kept: ${fades.slice(0, 20).join('; ')}`);
  if (moves.length) fails.push(`reduced motion: ${moves.length} element kinds still move: ${moves.slice(0, 15).join('; ')}`);
  await ctx.close();
}

await browser.close(); await srv.close();
console.log(shots.join('\n'));
if (fails.length) { console.error(`\n${fails.length} failure(s):\n` + fails.join('\n')); process.exit(1) }
console.log(`\nvisual: ${shots.length} screenshots in ${OUT}`);
