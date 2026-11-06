/* Top brokers ladder and spacing (1A) and the Regular board default (2A), user 2026-11-06: checks on the built page with
   the snapshot. Usage: node look_check4.mjs DATA OUT */
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { mkdir } from 'node:fs/promises';
import { serve } from './serve.mjs';
const { chromium, devices } = createRequire(import.meta.url)('playwright');

const [DATA, OUT] = process.argv.slice(2);
const { origin, close } = await serve(DATA, 'BBRI');
await mkdir(OUT, { recursive:true });
const browser = await chromium.launch();
const R = {}, errors = [];
const watch = p => { p.on('pageerror', e => errors.push(e.message)); p.on('console', m => { if (m.type() === 'error' && !/404/.test(m.text())) errors.push(m.text()) }) };
const ready = async p => { await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30_000 }); await p.waitForTimeout(1200) };
const addInd = async (p, q, id) => { await p.click('#indBtn'); await p.fill('#imSearch', q); await p.click(`.im-row[data-id="${id}"] .im-add`); await p.keyboard.press('Escape'); await p.waitForTimeout(900) };
const boards = p => p.evaluate(() => Object.fromEntries(['bsBoard', 'accBoard', 'invBoard', 'fdBoard'].map(id => [id, document.getElementById(id)?.value ?? null])));
const ladder = p => p.evaluate(() => { const l = document.querySelector('#accBody .acc-ladder'); if (!l) return null;
  return { on:l.querySelector('.on')?.textContent, steps:[...l.querySelectorAll('.acc-steps > *')].map(s => s.textContent), pin:l.querySelector('.acc-pin')?.getAttribute('style'), lv:[...l.querySelectorAll('.acc-lv > *')].map(s => s.textContent), ratio:document.querySelector('#accBody .acc-ratio')?.textContent } });
try {
  for (const [name, opts] of [['d', { viewport:{ width:1440, height:900 } }], ['p', { ...devices['iPhone 13'] }]]) {
    const ctx = await browser.newContext(opts), p = await ctx.newPage(); watch(p);
    await p.goto(`${origin}/terminal-app/`); await ready(p);
    if (name === 'd' && await p.$eval('#workspace', e => e.classList.contains('right-collapsed')).catch(() => false)) { await p.click('#rpExpand'); await p.waitForTimeout(800) }
    if (name === 'p') { await p.evaluate(() => document.getElementById('rpExpand').click()); await p.waitForTimeout(1500) }
    const r = R[name] = {};
    r.boards = await boards(p);
    r.ladder = await ladder(p);
    r.fd_tip = await p.$eval('.fdm-pt', g => g.dataset.tip).catch(() => null);
    r.acc_hint = await p.$eval('#accHint', e => e.textContent).catch(() => null);
    const sec = p.locator('.st[data-sec="acc"]');
    if (name === 'd') { await sec.scrollIntoViewIfNeeded(); await p.screenshot({ path:join(OUT, 'd_top.png'), clip:await sec.boundingBox() }) }
    else { await p.evaluate(() => document.querySelector('.st[data-sec="acc"]').scrollIntoView()); await p.waitForTimeout(300); await p.screenshot({ path:join(OUT, 'p_top.png') }) }
    r.acc_gaps = await p.evaluate(() => { const kids = [...document.querySelectorAll('.st[data-sec="acc"] .st-body > *, #accBody > *')].filter(e => e.offsetHeight);
      return kids.map(e => [e.className || e.id, Math.round(e.getBoundingClientRect().top), Math.round(e.offsetHeight)]) });
    if (name === 'd') {
      // the map follows its own Board choice; x + y = verdict on that board
      await p.selectOption('#fdBoard', 'All'); await p.waitForTimeout(300);
      r.fd_tip_all = await p.$eval('.fdm-pt', g => g.dataset.tip);
      await p.selectOption('#fdBoard', 'Regular'); await p.waitForTimeout(300);
      const fm = p.locator('.st[data-sec="fdmap"]'); await fm.scrollIntoViewIfNeeded();
      await p.screenshot({ path:join(OUT, 'd_map.png'), clip:await fm.boundingBox() });
      // a Flow indicator the user adds starts on Regular
      await addInd(p, 'Net Buy Persistence', 'FL12');
      r.fl12_board = await p.evaluate(() => JSON.parse(localStorage.getItem('ml.ind.v1')).find(o => o.def === 'FL12')?.params);
      r.fl12_row = await p.$eval('.ind-row[data-def="FL12"]', e => e.textContent.slice(0, 160));
      r.timeline_board = await p.evaluate(() => [...document.querySelectorAll('select')].filter(s => /board/i.test(s.getAttribute('aria-label') || '') && !['bsBoard','accBoard','invBoard','fdBoard'].includes(s.id)).map(s => s.closest('[id]')?.id + '=' + s.value));
    }
    r.overflow = await p.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    await ctx.close();
  }
} catch (e) { errors.push('harness: ' + e.message.split('\n')[0]) }
R.errors = errors;
console.log(JSON.stringify(R, null, 1));
await browser.close(); close();
