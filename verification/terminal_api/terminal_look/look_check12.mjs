/* EXEC-DRAW-PANES (user 2026-11-07: lines in the indicator panes, "1A", "2A"; "semua gambar harus di simpan di akun EDGE";
   "3 jalankan dulu"): on the stand-in account API (serve.mjs DRAWINGS):
   1. the account away: a line on the price chart stays in this browser and says so; back: it moves to the account once;
   2. a pane's id is kept with the indicator; Alt+H in a pane draws there; a trend line by press-drag-release; Undo, Redo;
   3. FL23's series are rebuilt when a broker is picked: its drawings stay and a new one can be drawn;
   4. a reload brings every set back from the account without writing;
   5. removing the pane removes its set; Undo brings it back.
   Writes look12_*.png to the scratchpad; exits 1 on a failed step. */
import { createRequire } from 'node:module';
import { serve } from '/home/user/saniti/verification/terminal_api/terminal_look/serve.mjs';
const { chromium } = createRequire('/home/user/saniti/verification/terminal_api/terminal_look/')('playwright');
const SP = '/tmp/claude-0/-home-user-saniti/5abac1e8-94e8-5166-9d5b-02bb4e4273bc/scratchpad';
const { origin, close, drawings } = await serve(SP + '/look', 'BBRI');
const b = await chromium.launch(); const errs = [], R = {}, bad = [];
const check = (name, ok, got) => { R[name] = got; if (!ok) bad.push(`${name}: ${JSON.stringify(got)}`) };
const ctx = await b.newContext({ viewport:{ width:1440, height:900 } }), p = await ctx.newPage();
p.on('pageerror', e => errs.push(e.message));
await p.addInitScript(() => { if (!sessionStorage.getItem('s')) { sessionStorage.setItem('s', '1'); localStorage.setItem('ml.broker.collapsed', '0'); localStorage.setItem('ml.ind.v1', JSON.stringify(['FL03', 'FL23'].map(d => ({ def:d, params:{} })))) } });
const boot = async () => { await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(2500) };
const count = key => (drawings.rows.get(key)?.drawings || []).length;
const pids = () => p.evaluate(() => Object.fromEntries(JSON.parse(localStorage.getItem('ml.ind.v1')).map(o => [o.def, o.pid])));
// a point in the pane's plot, below its row (the row and its filters sit over the pane's top)
const paneBox = def => p.evaluate(d => { const r = document.querySelector(`.ind-row.in-pane[data-def="${d}"]`).getBoundingClientRect(); return { x:700, y:r.bottom + 30 } }, def);
const altH = async (x, y) => { await p.mouse.move(x, y); await p.mouse.move(x + 1, y); await p.keyboard.press('Alt+KeyH'); await p.waitForTimeout(800) };

// 1. the account away, then back
drawings.down = true;
await p.goto(origin + '/terminal-app/'); await boot();
await altH(700, 180);
check('away: kept in this browser', (await p.evaluate(() => JSON.parse(localStorage.getItem('ml.drawings.BBRI') || '[]').length)) === 1, await p.evaluate(() => localStorage.getItem('ml.drawings.BBRI')?.slice(0, 80)));
check('away: said so', /could not be saved to your EDGE account/.test(await p.$eval('.lay-toast.top', e => e.textContent).catch(() => '')), await p.$eval('.lay-toast.top', e => e.textContent).catch(() => null));
drawings.down = false;
await p.reload(); await boot();
check('back: moved to the account once', count('BBRI/chart') === 1 && (await p.evaluate(() => localStorage.getItem('ml.drawings.BBRI'))) === null, { account:count('BBRI/chart'), local:await p.evaluate(() => localStorage.getItem('ml.drawings.BBRI')) });

// 2. pane ids; Alt+H in FL03's pane; a trend line by press-drag-release; Undo, Redo
const ids = await pids();
check('pane ids kept', /^[0-9a-f]{16}$/.test(ids.FL03 || '') && /^[0-9a-f]{16}$/.test(ids.FL23 || '') && ids.FL03 !== ids.FL23, ids);
const k3 = `BBRI/pane_${ids.FL03}`, k23 = `BBRI/pane_${ids.FL23}`;
const at3 = await paneBox('FL03');
await altH(at3.x, at3.y);
check('Alt+H in the pane', count(k3) === 1 && count('BBRI/chart') === 1, { pane:count(k3), chart:count('BBRI/chart') });
await p.keyboard.press('Alt+KeyT'); await p.mouse.move(500, at3.y + 10); await p.mouse.down(); await p.mouse.move(650, at3.y - 2, { steps:8 }); await p.mouse.move(800, at3.y - 10, { steps:8 }); await p.mouse.up(); await p.waitForTimeout(800);
check('trend line by drag-release', count(k3) === 2, count(k3));
await p.keyboard.press('Control+KeyZ'); await p.waitForTimeout(800); const afterUndo = count(k3);
await p.keyboard.press('Control+KeyY'); await p.waitForTimeout(800);
check('undo, redo', afterUndo === 1 && count(k3) === 2, [afterUndo, count(k3)]);
await p.screenshot({ path:`${SP}/look12_panes.png` });

// 3. FL23's series rebuilt by a broker pick: its drawings stay, and a new one is drawn after the rebuild
const at23 = await paneBox('FL23');
await altH(at23.x, at23.y);
const before = count(k23);
const picks = await p.$$('#accBody .pa-b[data-b]');
if (picks[0]) { await picks[0].click(); await p.waitForTimeout(600) }
const at23b = await paneBox('FL23');
await altH(at23b.x, at23b.y + 15);
const lines = await p.$eval('.ind-row[data-def="FL23"]', e => e.textContent.slice(0, 120));
check('rebuilt series: kept and drawable', !!picks[0] && before === 1 && count(k23) === 2, { before, after:count(k23), picked:!!picks[0], lines });

// 4. a reload brings the sets back without writing
const writes = drawings.calls.filter(c => /^(PUT|DELETE)/.test(c)).length;
await p.reload(); await boot();
check('reload: nothing written', drawings.calls.filter(c => /^(PUT|DELETE)/.test(c)).length === writes, drawings.calls.slice(-6));
const before5 = await p.evaluate(() => [...document.querySelectorAll('#chart canvas')].length);
await p.screenshot({ path:`${SP}/look12_reload.png` });

// 5. the user removes FL03's pane: its set goes; Undo brings it back
await p.$eval('.ind-row[data-def="FL03"] .ind-eye[data-act="del"]', e => e.click()); await p.waitForTimeout(800);
check('removed: set gone', !drawings.rows.has(k3), drawings.calls.slice(-3));
await p.keyboard.press('Control+KeyZ'); await p.waitForTimeout(1200);
check('undo: set back', count(k3) === 2 && (await pids()).FL03 === ids.FL03, { n:count(k3), pid:(await pids()).FL03 });
await p.screenshot({ path:`${SP}/look12_undo.png` });
void before5;
await ctx.close();
console.log(JSON.stringify(R)); console.log('errs', errs); console.log(bad.length ? 'FAIL\n' + bad.join('\n') : 'PASS');
await b.close(); close(); process.exit(bad.length || errs.length ? 1 : 0);
