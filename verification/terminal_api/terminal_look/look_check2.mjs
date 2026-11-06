/* EXEC-TERMINAL-LOOK-2 and EXEC-FLOW-PANE-FILTERS (user go 2026-11-06): the second round of interactions on the built
   page with real data, reusing look_check.mjs's stand-in server (imported by spawning it is not possible, so the server
   part is shared through ./serve.mjs). Usage: node look_check2.mjs DATA OUT [WIDTH] */
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { mkdir } from 'node:fs/promises';
import { serve } from './serve.mjs';
const { chromium } = createRequire(import.meta.url)('playwright');

const [DATA, OUT, WIDTH = '1440'] = process.argv.slice(2);
const { origin, close } = await serve(DATA, 'BBRI');
await mkdir(OUT, { recursive:true });
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport:{ width:+WIDTH, height:900 } })).newPage();
const errors = []; page.on('pageerror', e => errors.push(e.message)); page.on('console', m => { if (m.type() === 'error' && !/404/.test(m.text())) errors.push(m.text()) });
const shot = (n, el) => (el ? page.locator(el).first() : page).screenshot({ path:join(OUT, `${n}.png`) });
const R = {};
const rowOf = id => `.ind-row[data-def="${id}"]`;
try {
  await page.goto(`${origin}/terminal-app/`);
  await page.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30_000 });
  await page.waitForTimeout(1200);
  // 1. the one scrolling list: a group click jumps, scrolling marks the group in view
  await page.click('#indBtn'); await page.waitForTimeout(300);
  await page.click('.im-nav [data-g="all"]');
  await page.click('.im-nav [data-g="f:Net Flow"]'); await page.waitForTimeout(500);
  R.jump = await page.evaluate(() => { const l = document.querySelector('.im-list'), h = l.querySelector('.im-sec[data-sec="f:Net Flow"]');
    return { headings:l.querySelectorAll('.im-sec').length, rows:l.querySelectorAll('.im-row[data-id]').length, top:Math.round(h.getBoundingClientRect().top - l.getBoundingClientRect().top),
      on:document.querySelector('.im-nav button.on')?.dataset.g } });
  await page.evaluate(() => { const l = document.querySelector('.im-list'); l.scrollTop = l.querySelector('.im-sec[data-sec="t:Momentum"]').nextElementSibling.offsetTop - l.offsetTop + 30 });
  await page.waitForTimeout(300);
  R.spy = await page.$eval('.im-nav button.on', b => b.dataset.g);
  await shot('11_dialog_scroll', '.im-box');
  // add Net Buy Persistence (FL12) and Broker Inventory (FL23)
  await page.fill('#imSearch', 'Net Buy Persistence'); await page.click('.im-row[data-id="FL12"] .im-add');
  await page.fill('#imSearch', 'Broker Inventory'); await page.click('.im-row[data-id="FL23"] .im-add');
  await page.keyboard.press('Escape'); await page.waitForTimeout(1500);
  // 2. FL12 controls: scope Top-N shows N and Rank by; Selected shows the broker list only
  const ctl = async id => page.$$eval(`${rowOf(id)} .ind-flt > *`, els => els.map(e => ({ k:e.dataset.k, hidden:e.hidden, text:e.textContent.replace(/\s+/g, ' ').trim() })));
  R.fl12_topn = await ctl('FL12');
  await page.fill(`${rowOf('FL12')} .ind-num input`, '5'); await page.press(`${rowOf('FL12')} .ind-num input`, 'Enter');
  await page.selectOption(`${rowOf('FL12')} .ind-sel[data-k="rank"] select`, 'gross_buy'); await page.waitForTimeout(400);
  R.fl12_params = await page.evaluate(() => JSON.parse(localStorage.getItem('ml.ind.v1')).find(o => o.def === 'FL12')?.params);
  R.fl12_title = await page.$eval(`${rowOf('FL12')} .ind-k`, e => e.textContent);
  await page.selectOption(`${rowOf('FL12')} .ind-sel[data-k="scope"] select`, 'selected'); await page.waitForTimeout(400);
  R.fl12_selected = await ctl('FL12');
  R.fl12_note = await page.$eval(`${rowOf('FL12')} > b`, e => e.textContent);
  await shot('12_fl12_selected');
  // 3. Clear on FL23's brokers: no line, the row asks for a broker; the buttons agree
  await page.click(`${rowOf('FL23')} .fl[data-k="brokers"] .fl-btn`); await page.click(`${rowOf('FL23')} .fl[data-k="brokers"] [data-act="none"]`); await page.waitForTimeout(400);
  R.fl23_clear = { button:await page.$eval(`${rowOf('FL23')} .fl[data-k="brokers"] .fl-btn`, e => e.textContent.trim()), value:await page.$eval(`${rowOf('FL23')} > b`, e => e.textContent),
    zero:await page.$$eval('.ind-zero', z => z.length) };
  await page.mouse.click(700, 300); await page.waitForTimeout(200);
  await shot('13_fl23_cleared');
  // 4. the map: no diagonals; hover on a dot grows it and shows the panel tooltip
  if (await page.$eval('#workspace', e => e.classList.contains('right-collapsed')).catch(() => false)) { await page.click('#rpExpand'); await page.waitForTimeout(800) }
  await page.locator('.st[data-sec="fdmap"]').scrollIntoViewIfNeeded();
  R.map_diagonals = await page.$$eval('.fdm-svg line', ls => ls.filter(l => +l.getAttribute('x1') < 0 || +l.getAttribute('x2') > 236).length);
  const dot = page.locator('.fdm-pt').nth(1); await dot.hover(); await page.waitForTimeout(250);
  R.map_tip = await page.$eval('.st-tip', e => e.hidden ? null : e.textContent).catch(() => null);
  R.map_scale = await page.$eval('.fdm-pt:hover .dot', e => getComputedStyle(e).transform).catch(() => null);
  await shot('14_map_hover', '.st[data-sec="fdmap"]');
  // 5. Alt+B with the right panel scrolled down: after the period is chosen, the panel is back at its top
  await page.evaluate(() => { const s = document.getElementById('rightScroll'); s.scrollTop = s.scrollHeight });
  await page.keyboard.press('Alt+KeyB'); await page.waitForTimeout(300);
  const box = await page.locator('#chart').boundingBox();
  await page.mouse.move(box.x + box.width * 0.5, box.y + 200); await page.mouse.down(); await page.mouse.move(box.x + box.width * 0.7, box.y + 200, { steps:8 }); await page.mouse.up();
  await page.waitForTimeout(900);
  R.altb = await page.evaluate(() => { const s = document.getElementById('rightScroll'); return { scrollTop:s.scrollTop, bsHint:document.getElementById('bsHint')?.textContent } });
  await shot('15_altb');
} catch (e) { errors.push('harness: ' + e.message.split('\n')[0]) }
R.errors = errors;
console.log(JSON.stringify(R, null, 1));
await browser.close(); close();
