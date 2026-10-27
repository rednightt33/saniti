/* The scripted interaction scenario run on both pages (the reference and /backtest-app/?fixture=reference). Steps are
   cumulative: each one starts from the state the previous left; both pages start the way the reference does (one run
   at load, the Signals view, builder step 2). Names starting with "d-" need the desktop layout. A step gets the side it
   runs on ('ref' or 'ts'): where the reference has its Universe select the TypeScript page has the stock picker (PF7),
   so a step picks the same stocks with the control each page has. The steps of TS_ONLY run on the TypeScript page
   alone, after the others (snapshots of the picker for review; the reference has no such control to compare). */
const click = (page, sel) => page.locator(sel).first().click();
const step = (page, n) => click(page, `#sumbox [data-st="${n}"]`);

/* Run backtest: both pages disable the run buttons in the click handler and enable them again with the result */
async function run(page) {
  await click(page, '#runTop');
  await page.waitForFunction(() => !document.getElementById('runTop').disabled, null, { timeout:60_000 });
}
const tab = (page, k) => click(page, `#rtabs [data-tab="${k}"]`);
/* every scroll box of the middle column at its end (the part of a tab below the fold) */
const scrollMainToEnd = page => page.evaluate(() => {
  for (const el of [document.getElementById('main'), ...document.querySelectorAll('#main *')]) {
    const o = getComputedStyle(el).overflowY;
    if ((o === 'auto' || o === 'scroll') && el.scrollHeight > el.clientHeight) el.scrollTop = el.scrollHeight;
  }
});
async function hoverAt(page, sel, fx, fy) {
  const el = page.locator(sel).first();
  await el.scrollIntoViewIfNeeded();
  const box = await el.boundingBox();
  await page.mouse.move(box.x + box.width * fx, box.y + box.height * fy, { steps:4 });
}

export const SCENARIOS = {
  /* builder steps 1-5 (the strategy summary rows are the step buttons on every layout) */
  'a1-step1-universe': async page => { await step(page, 1) },
  'a2-step2-entry': async page => { await step(page, 2) },
  'a3-add-condition-menu': async page => { await click(page, '#addCond') },
  'a4-add-condition': async page => { await click(page, '#menu [data-add="volspike"]') },
  'a5-step3-exit': async page => { await step(page, 3) },
  'a6-step4-sizing': async page => { await step(page, 4) },
  'a7-step5-costs': async page => { await step(page, 5) },
  /* the conditions workspace */
  'b1-workspace-entry': async page => { await step(page, 2); await click(page, '#wsOpen') },
  'b2-workspace-search': async page => { await page.fill('#wsQ', 'smoothing') },
  'b3-workspace-category': async page => { await page.fill('#wsQ', ''); await click(page, '#wsCats button:nth-child(3)') },
  'b4-workspace-item': async page => { await click(page, '#wsList .wl-i') },
  'b5-workspace-exit-tab': async page => { await click(page, '#wsTabs [data-wside="exit"]') },
  'b6-workspace-closed': async page => { await click(page, '#wsClose') },
  /* a template, a run and every results tab */
  'c1-template': async page => { await click(page, '#builder [data-tpl="Trend + pullback"]') },
  'c2-run-overview': async page => { await run(page); await tab(page, 'overview') },
  'c3-overview-hover': async page => { await hoverAt(page, '#eqChart', .62, .45) },
  'c3b-compare-ihsg': async page => { await page.mouse.move(2, 2); await page.selectOption('#cmpAdd', 'IHSG') },
  'c4-tab-returns': async page => { await tab(page, 'returns') },
  'c5-returns-hover': async page => { await hoverAt(page, '#rbody .hbin:nth-of-type(9)', .5, .7) },
  'c6-tab-trades': async page => { await page.mouse.move(2, 2); await tab(page, 'trades') },
  'c7-tab-risk': async page => { await tab(page, 'risk') },
  'c8-tab-robust': async page => { await tab(page, 'robust') },
  'c8b-robust-end': async page => { await scrollMainToEnd(page) },
  'c9-tab-list': async page => { await tab(page, 'list') },
  /* portfolio mode: the signals table, then a run */
  'e1-portfolio-signals': async page => {
    await tab(page, 'overview'); await click(page, '#viewSeg [data-v="signals"]'); await step(page, 1); await click(page, '#modeSeg [data-m="portfolio"]');
  },
  'e2-portfolio-row': async page => { await click(page, '#portSig [data-t="BBRI"]') },
  'e3-portfolio-results': async page => { await run(page) },
  'e4-portfolio-banks': async (page, side) => {
    await click(page, '#viewSeg [data-v="signals"]');
    if (side === 'ref') await page.selectOption('#builder [data-k="universe"]', { label:'Banks (BBCA, BBRI, BMRI)' });
    // the picker: the fixture's default portfolio is the reference's Demo 10; its chips other than the banks removed
    else for (const t of await page.locator('#pkChips [data-pk-del]').evaluateAll(bs => bs.map(b => b.dataset.pkDel)))
      if (!['BBCA', 'BBRI', 'BMRI'].includes(t)) await click(page, `#pkChips [data-pk-del="${t}"]`);
  },
  'e5-portfolio-banks-run': async page => { await run(page) },
  /* layout: the setup panel hidden, the results full screen, both back */
  'f1-panel-collapsed': async page => { await click(page, '#panelTg') },
  'f2-results-fullscreen': async page => { await click(page, '#panelTg'); await click(page, '#fsBtn') },
  'f3-fullscreen-closed': async page => { await click(page, '#fsBtn') },
  /* single stock again: an exit-signal template, then each stop mode with its run (robustness grid on the stop axis) */
  'g1-exit-template': async page => {
    await click(page, '#viewSeg [data-v="signals"]'); await step(page, 1); await click(page, '#modeSeg [data-m="single"]');
    await step(page, 3); await click(page, '#builder [data-xtpl]');
  },
  'g2-exit-template-run': async page => { await run(page); await tab(page, 'robust') },
  ...Object.fromEntries(['atr', 'rr', 'line', 'none', 'pct'].flatMap((m, k) => [
    [`h${k + 1}a-stop-${m}`, async page => { await click(page, `#builder [data-mode="exit.stopMode"] [data-v="${m}"]`) }],
    [`h${k + 1}b-stop-${m}-run`, async page => { await run(page) }],
  ])),
  /* the stock picker (TS_ONLY): the search list, the keyboard's add, a group with its list, add all at the limit */
  'p1-picker-search': async page => {
    await click(page, '#viewSeg [data-v="signals"]'); await step(page, 1); await click(page, '#modeSeg [data-m="portfolio"]');
    await click(page, '#pkQ'); await page.keyboard.type('a');
  },
  'p2-picker-added': async page => { await page.keyboard.press('ArrowDown'); await page.keyboard.press('Enter') },
  'p3-picker-group': async page => {
    await page.keyboard.press('Escape'); await page.keyboard.press('Escape');
    await page.locator('#pk label.fld:has(span:text-is("Sector")) select').selectOption({ label:'Banks (3)' });
  },
  'p4-picker-add-all': async page => {
    await page.locator('#pk label.fld:has(span:text-is("Sector")) select').selectOption({ label:'Unclassified (7)' });
    await click(page, '#pkAll');
  },
};
export const TS_ONLY = new Set(['p1-picker-search', 'p2-picker-added', 'p3-picker-group', 'p4-picker-add-all']);
