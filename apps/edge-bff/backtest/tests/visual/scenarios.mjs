/* The scripted interaction scenario run on both pages (the user's design file and /backtest-app/?fixture=design). Steps
   are cumulative: each one starts from the state the previous left; both pages start the way the design does (no run at
   load, the Signals view, builder step 2). Names starting with "d-" need the desktop layout. A step gets the side it runs
   on ('ref' or 'ts'). The design was built on a compiled copy of the page, so both have the stock picker (PF7) and the
   condition window, and every step runs on both (TS_ONLY is kept for a step the design has no control for). */
const click = (page, sel) => page.locator(sel).first().click();
/* the builder's step tabs (design "Builder v2"; the strategy summary rows are hidden in the design) */
const step = (page, n) => click(page, `#rail [data-st="${n}"]`);

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
  /* the condition window (condwin.ts): opened from the builder, a search, a category, Customize, the exit side, closed */
  'b1-condwin-entry': async page => { await step(page, 2); await click(page, '#wsOpen') },
  'b2-condwin-search': async page => { await page.fill('#cwQ', 'stochastic') },
  'b3-condwin-category': async page => { await page.fill('#cwQ', ''); await click(page, '#cwRail [data-cwv="Trend"]') },
  'b4-condwin-customize': async page => { await click(page, '#cwList [data-cwcus]') },
  'b5-condwin-exit-side': async page => { await page.keyboard.press('Escape'); await click(page, '#cwSide [data-cwside="exit"]') },
  'b6-condwin-closed': async page => { await click(page, '#cw .qwin-f [data-cwclose]') },
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
  'e4-portfolio-banks': async page => {
    await click(page, '#viewSeg [data-v="signals"]');
    // the picker: the fixture's default portfolio is the reference's Demo 10; its chips other than the banks removed
    for (const t of await page.locator('#pkChips [data-pk-del]').evaluateAll(bs => bs.map(b => b.dataset.pkDel)))
      if (!['BBCA', 'BBRI', 'BMRI'].includes(t)) await click(page, `#pkChips [data-pk-del="${t}"]`);
  },
  'e5-portfolio-banks-run': async page => { await run(page) },
  /* layout: the setup panel hidden, the results full screen, both back */
  'f1-panel-collapsed': async page => { await click(page, '#panelTg') },
  // (a hidden builder opens again from its rail, #bRail: its own hide button is hidden with it)
  'f2-results-fullscreen': async page => { await click(page, '#bRail'); await click(page, '#fsBtn') },
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
  /* the stock picker: the search list, the keyboard's add, a group with its list, add all at the limit */
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
export const TS_ONLY = new Set();
