import { createRequire } from 'node:module';
import { serve } from '/home/user/saniti/verification/terminal_api/terminal_look/serve.mjs';
const { chromium } = createRequire('/home/user/saniti/verification/terminal_api/terminal_look/')('playwright');
const SP = process.argv[2];
process.env.EDGE_PAGE = '1';
const { origin, close } = await serve(SP + '/look', 'BBRI');
const b = await chromium.launch(), p = await (await b.newContext({ viewport:{ width:1600, height:900 } })).newPage();
const errs = []; p.on('pageerror', e => errs.push(e.message));
await p.goto(origin + '/'); await p.waitForTimeout(2500);
await p.click('.side-nav button[data-tip="Terminal"]');
// while the Terminal still loads: its own rail must not show (ERRORS M412)
for (const ms of [150, 400, 900]) { await p.waitForTimeout(ms); console.log('loading +' + ms, JSON.stringify(await p.evaluate(() => { const d = document.querySelector('.terminal-page iframe')?.contentDocument; const sp = d?.getElementById('statsPanel'); return d && sp ? { src:document.querySelector('.terminal-page iframe').getAttribute('src'), boot:!!d.querySelector('.ml-boot'), edgeRail:d.documentElement.classList.contains('edge-rail'), railW:Math.round(sp.getBoundingClientRect().width), ready:document.querySelector('.side-stats')?.getAttribute('aria-disabled') } : 'frame not ready' }))) }
// the preview points its frames at itself; here the frame gets the real Terminal of this server
await p.waitForTimeout(7000);
const fr = p.frameLocator('.terminal-page iframe');
const st = async () => ({ edge:await p.evaluate(() => { const b = document.querySelector('.side-stats'); return b && [b.getAttribute('aria-expanded'), b.dataset.tip] }),
  term:await fr.locator('html').evaluate(h => [h.classList.contains('edge-rail'), document.getElementById('workspace').classList.contains('left-collapsed'), Math.round(document.getElementById('statsPanel').getBoundingClientRect().width)]) });
console.log('frame', await p.evaluate(() => { const f = document.querySelector('.terminal-page iframe'); return f ? [f.getAttribute('src'), f.contentDocument?.title, f.contentDocument?.body?.innerText.slice(0, 120)] : 'no frame' }));
console.log('start', JSON.stringify(await st()));
await p.click('.side-stats'); await p.waitForTimeout(800); console.log('open', JSON.stringify(await st()));
await p.screenshot({ path:SP + '/stats_open.png' });
await fr.locator('#statsCollapse').click(); await p.waitForTimeout(600); console.log('closed inside', JSON.stringify(await st()));
await p.hover('.side-nav button[data-tip="Backtest"]'); await p.waitForTimeout(300);
await p.screenshot({ path:SP + '/stats_tip.png', clip:{ x:0, y:0, width:320, height:420 } });
console.log('ERR', errs.slice(0, 3));
await b.close(); close();
