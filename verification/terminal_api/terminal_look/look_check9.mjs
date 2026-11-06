/* EXEC-IND-PRESETS (user 2026-11-06: "men-save indikator beserta dengan filternya"; "Q1 A", "Q2 A"): save from the row and
   from Settings (replace after a question), My presets (add, star, rename, update from chart, delete), search, a preset
   whose indicator is gone, a parameter the indicator no longer has; and the window fixes (search shadow, definition line,
   no Place · Unit, the value right after the title). Writes look9_*.png to the scratchpad given below. */
import { createRequire } from 'node:module';
import { serve } from '/home/user/saniti/verification/terminal_api/terminal_look/serve.mjs';
const { chromium, devices } = createRequire('/home/user/saniti/verification/terminal_api/terminal_look/')('playwright');
const SP = '/tmp/claude-0/-home-user-saniti/5abac1e8-94e8-5166-9d5b-02bb4e4273bc/scratchpad';
const { origin, close, presets } = await serve(SP + '/look', 'BBRI');
const b = await chromium.launch(); const errs = [], R = {};
const seed = (id, name, def_id, config) => { const now = new Date(Date.now() - 1e6).toISOString();
  presets.rows.set(id, { preset_id:id, name, def_id, config, summary:'seeded', schema_version:1, favorite:false, revision:1, created_at:now, updated_at:now, used_at:now }) };
const onChart = p => p.evaluate(() => JSON.parse(localStorage.getItem('ml.ind.v1') || '[]').map(o => o.def + ':' + JSON.stringify(o.params)));
const name = async (p, text) => { await p.waitForSelector('.lay-dlg input'); await p.fill('.lay-dlg input', text); await p.click('.lay-dlg [data-ok]') };
for (const [nm, opt] of [['d1440', { viewport:{ width:1440, height:900 } }], ['phone', devices['iPhone 13']]]) {
  const ctx = await b.newContext(opt), p = await ctx.newPage(); p.on('pageerror', e => errs.push(nm + ' ' + e.message));
  await p.addInitScript(() => { if (!sessionStorage.getItem('s')) { sessionStorage.setItem('s', '1'); localStorage.setItem('ml.ind.v1', JSON.stringify(['FL12', 'FL03'].map(d => ({ def:d, params:{} })))) } });
  await p.goto(origin + '/terminal-app/'); await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(2500);
  if (nm === 'd1440') {
    // the value sits right after the title when the filters are on
    R.order = await p.evaluate(() => [...document.querySelectorAll('.ind-row.in-pane')].map(r => [r.dataset.def,
      [...r.children].filter(c => c.offsetWidth).sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left).map(c => c.tagName.toLowerCase() + (c.className ? '.' + String(c.className).split(' ')[0] : '')).join(' ')]));
    // 1. save from the row
    await p.hover('.ind-row[data-def="FL12"] > b', { force:true }); await p.$eval('.ind-row[data-def="FL12"] [data-act="preset"]', e => e.click());
    await name(p, 'My FL12'); await p.waitForTimeout(400);
    R.saveRow = { n:presets.rows.size, toast:await p.$eval(".lay-toast.top", t => t.textContent), cfg:[...presets.rows.values()][0]?.config };
    // 2. save from Settings under the same name: asked, then replaced
    await p.hover('.ind-row[data-def="FL12"] > b', { force:true }); await p.$eval('.ind-row[data-def="FL12"] [data-act="cfg"]', e => e.click());
    await p.waitForSelector('.idlg [data-act="preset"]'); await p.click('.idlg [data-act="preset"]');
    await name(p, 'My FL12'); await p.waitForSelector('.lay-dlg p'); R.replaceQ = await p.$eval('.lay-dlg p', e => e.textContent);
    R.dlgOnTop = await p.evaluate(() => +getComputedStyle(document.querySelector('.lay-back.top')).zIndex > +getComputedStyle(document.querySelector('.idlg').closest('[class*="back"]') || document.querySelector('.idlg')).zIndex);
    await p.click('.lay-dlg:has(p) [data-ok]'); await p.waitForTimeout(500);
    R.replaced = { n:presets.rows.size, rev:[...presets.rows.values()][0].revision };
    await p.keyboard.press('Escape'); await p.waitForTimeout(300); await p.click('.idlg [data-act="cancel"]').catch(() => {});
    // 3. seeded: an indicator the Terminal no longer has, and a parameter FL12 no longer has
    seed('ipr_' + 'e'.repeat(32), 'Old one', 'ZZ99', { params:{} }); seed('ipr_' + 'f'.repeat(32), 'Stale param', 'FL12', { params:{ bogus:1 } });
    await p.click('#indBtn'); await p.waitForSelector('#indMenu:not([hidden])');
    R.window = await p.evaluate(() => { const s = document.querySelector('.im-search'), r = document.querySelector('.im-row[data-id]');
      return { searchBorderFocus:getComputedStyle(s).borderColor, searchShadow:getComputedStyle(s).boxShadow, line:r.querySelector('.pa').textContent.slice(0, 80), placeUnit:!!document.querySelector('.im-pu,.im-hd .pu') || /Place|PLACE/.test(document.querySelector('#indMenu').innerText) } });
    await p.click('#indMenu [data-g="presets"]'); await p.waitForTimeout(500);
    R.group = await p.$$eval('.im-prow', rs => rs.map(r => [r.querySelector('.nmt').textContent, r.querySelector('small').textContent, r.querySelector('[data-padd]').disabled]));
    R.count = await p.$eval('#indMenu', d => d.querySelector('[class*="count"], .im-count')?.textContent || '');
    await p.screenshot({ path:`${SP}/look9_presets.png` });
    // 4. add, gone, stale parameter
    const before = (await onChart(p)).length;
    await p.click('.im-prow:has-text("My FL12") [data-padd]'); await p.waitForTimeout(400);
    await p.click('.im-prow:has-text("Old one")', { force:true }); await p.waitForTimeout(200); R.goneToast = await p.$eval(".lay-toast.top", t => t.textContent);
    await p.click('.im-prow:has-text("Stale param") [data-padd]'); await p.waitForTimeout(400);
    const after = await onChart(p); R.add = { before, after:after.length, last:after.at(-1), used:presets.calls.filter(c => c.startsWith('PATCH')).length };
    // 5. star (favourites first)
    await p.click('.im-prow:has-text("Stale param") [data-pstar]'); await p.waitForTimeout(400);
    R.star = await p.$$eval('.im-prow .nmt', ns => ns.map(n => n.textContent));
    // 6. rename, update from chart, search, delete
    await p.click('.im-prow:has-text("My FL12") [data-pmenu]'); await p.click('.im-pmenu [data-pm="rename"]'); await name(p, 'Renamed FL12'); await p.waitForTimeout(400);
    R.rename = await p.$$eval('.im-prow .nmt', ns => ns.map(n => n.textContent));
    const rev = [...presets.rows.values()].find(r => r.name === 'Renamed FL12').revision;
    await p.click('.im-prow:has-text("Renamed FL12") [data-pmenu]'); await p.click('.im-pmenu [data-pm="update"]'); await p.waitForSelector('.lay-dlg p');
    R.updateQ = await p.$eval('.lay-dlg p', e => e.textContent); await p.click('.lay-dlg [data-ok]'); await p.waitForTimeout(400);
    R.update = [rev, [...presets.rows.values()].find(r => r.name === 'Renamed FL12').revision];
    await p.click('#indMenu [data-g="all"]'); await p.fill('#indMenu .im-search input', 'renamed'); await p.waitForTimeout(300);
    R.search = await p.$$eval('#indMenu .im-list > *', es => es.slice(0, 4).map(e => (e.querySelector('.nmt') || e).textContent.trim()));
    await p.screenshot({ path:`${SP}/look9_search.png` });
    await p.fill('#indMenu .im-search input', ''); await p.click('#indMenu [data-g="presets"]'); await p.waitForTimeout(300);
    await p.click('.im-prow:has-text("Old one") [data-pmenu]'); await p.click('.im-pmenu [data-pm="delete"]'); await p.waitForSelector('.lay-dlg p'); await p.click('.lay-dlg [data-ok]'); await p.waitForTimeout(400);
    R.del = { rows:presets.rows.size, list:await p.$$eval('.im-prow .nmt', ns => ns.map(n => n.textContent)) };
  } else {
    await p.click('#indBtn'); await p.waitForSelector('#indMenu:not([hidden])'); await p.click('#indMenu [data-g="presets"]'); await p.waitForTimeout(500);
    R.phone = await p.evaluate(() => ({ vw:innerWidth, sw:document.documentElement.scrollWidth, rows:[...document.querySelectorAll('.im-prow')].map(r => { const x = r.getBoundingClientRect(), a = r.querySelector('[data-padd]').getBoundingClientRect(); return [Math.round(x.width), Math.round(a.right), Math.round(a.height)] }) }));
    await p.screenshot({ path:`${SP}/look9_phone.png` });
  }
  await ctx.close();
}
console.log(JSON.stringify(R, null, 1)); console.log('errs', errs); await b.close(); close();
