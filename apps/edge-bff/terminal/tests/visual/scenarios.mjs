/* The scripted interaction scenario run on both pages (FRONTEND_ARCHITECTURE.md section 4, step 3). Steps are
   cumulative: each one starts from the state the previous left. Names starting with "d-" need the desktop layout. */
const click = (page, sel) => page.locator(sel).first().click();

async function chartPoint(page, fx, fy) {
  const box = await page.locator('#chart').boundingBox();
  return [box.x + box.width * fx, box.y + box.height * fy];
}

export const SCENARIOS = {
  'a-line-style': async page => { await click(page, '#styleGroup [data-style="line"]') },
  'b-return-mode': async page => { await click(page, '#modeGroup [data-mode="return"]') },
  'c-back-to-price-candles': async page => {
    await click(page, '#modeGroup [data-mode="price"]'); await click(page, '#styleGroup [data-style="candle"]');
  },
  'd-add-compare-series': async page => {
    await click(page, '#toggleAddPanel'); await click(page, '#catalogGrid [data-quick-add]'); await page.waitForTimeout(150);
  },
  'd-close-add-panel': async page => { await click(page, '#closePanel') },
  'e-indicator-picker-search': async page => { await click(page, '#indBtn'); await page.fill('#indSearch', 'rsi') },
  'f-add-rsi-macd-bollinger': async page => {
    await click(page, '.ind-item[data-ind="Relative Strength Index"]');
    await page.fill('#indSearch', 'macd'); await click(page, '.ind-item[data-ind="MACD"]');
    await page.fill('#indSearch', 'bollinger'); await click(page, '.ind-item[data-ind="Bollinger Bands"]');
    await page.keyboard.press('Escape');
  },
  'g-indicator-settings-style': async page => {
    await click(page, '.ind-row[data-def="rsi"] [data-act="cfg"]'); await click(page, '.idlg [data-tab="Style"]');
  },
  'h-indicator-settings-cancel': async page => { await click(page, '.idlg [data-act="cancel"]') },
  'i-events-popover': async page => { await click(page, '#evBtn'); await click(page, '.ev-row[data-id="dividend"]') },
  'j-events-close': async page => { await page.keyboard.press('Escape') },
  'k-crosshair-hover': async page => { const [x, y] = await chartPoint(page, .62, .4); await page.mouse.move(x, y); await page.waitForTimeout(200) },
  'l-crosshair-leave': async page => { await page.mouse.move(2, 2) },
  'd-stats-accordion-and-collapse': async page => {
    await click(page, '#statsPanel .st[data-sec="dist"] .st-head'); await click(page, '#statsCollapse');
  },
  'd-stats-expand': async page => { await click(page, '#statsExpand') },
  'd-seasonality-weekday': async page => { await click(page, '#seasToggle [data-mode="weekday"]') },
  'd-broker-filters': async page => {
    await page.selectOption('#bsInv', 'Foreign'); await click(page, '#bsMode [data-mode="gross"]');
    await click(page, '#bsRange [data-n="5"]'); await click(page, '#accSide [data-side="sell"]');
  },
  'd-broker-select': async page => { await click(page, '#bsBody tr[data-b]') },
  'd-flow-filter-investor': async page => {
    await click(page, '#flInvestor .fl-btn'); await click(page, '#flInvestor input[value="Domestic"]'); await page.keyboard.press('Escape');
  },
  'd-flow-cumulative-off': async page => { await click(page, '.pill-toggle') },
  'm-line-menu': async page => { await click(page, '.dr-btn[data-tool="trend-line"]') },   // the Trend line button opens the Lines menu
  'm-draw-trend-line': async page => {
    await page.keyboard.press('Escape');
    const [x1, y1] = await chartPoint(page, .45, .35), [x2, y2] = await chartPoint(page, .7, .25);
    await page.mouse.move(x1, y1); await page.keyboard.press('Alt+t');                       // Alt+T arms the trend line
    await page.mouse.down(); await page.mouse.move(x2, y2, { steps:6 }); await page.mouse.up();
    await page.mouse.move(2, 2);
  },
  'm-cursor-menu-dot': async page => { await click(page, '.dr-btn[data-tool=""]'); await click(page, '.dr-menu .dr-mi[data-id="dot"]') },
  'n-context-menu': async page => { const [x, y] = await chartPoint(page, .5, .5); await page.mouse.click(x, y, { button:'right' }) },
  'o-context-menu-close': async page => { await page.keyboard.press('Escape'); await page.mouse.click(2, 2) },
  'p-symbol-search': async page => { await page.keyboard.press('Control+k'); await page.keyboard.type('bb') },
  'q-symbol-search-close': async page => { await page.keyboard.press('Escape') },
};
