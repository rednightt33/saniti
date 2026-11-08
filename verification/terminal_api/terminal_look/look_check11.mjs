/* Alignment check (user 2026-11-07: "Saya pikir masalah alignment seperti ini sudah dicek ... Tapi kenapa masih bisa
   kebobolan?"). Measures what earlier checks did not: where text actually starts and whether its ink sits in the middle of
   its band, read from the rendered pixels, plus every toggle's thumb in its track and the right-panel rows (EXEC-RP-LOOK).
   Fails (exit 1) on: a text start more than 1px off its column, ink more than 1px off its band's middle, a thumb more than
   0.5px off its track's middle, a market choice not at its row's right (the panels and the Foreign × Domestic window,
   EXEC-FD-WINDOW). Writes look11_*.png to the scratchpad. */
import { createRequire } from 'node:module';
import { serve } from '/home/user/saniti/verification/terminal_api/terminal_look/serve.mjs';
const { chromium, devices } = createRequire('/home/user/saniti/verification/terminal_api/terminal_look/')('playwright');
const SP = '/tmp/claude-0/-home-user-saniti/5abac1e8-94e8-5166-9d5b-02bb4e4273bc/scratchpad';
const { origin, close } = await serve(SP + '/look', 'BBRI');
const b = await chromium.launch(); const errs = [], R = {}, bad = [];
const check = (name, ok, got) => { if (!ok) bad.push(`${name}: ${JSON.stringify(got)}`) };

/* the ink of a band: space from its top line to the first dark pixel row and from the last one to its bottom line */
async function ink(p, sel, i = 0) {
  const el = (await p.$$(sel))[i]; if (!el) return null;
  await el.scrollIntoViewIfNeeded().catch(() => {});
  const bb = await el.boundingBox(), vp = p.viewportSize();
  if (!bb || !bb.height || bb.y < 0 || bb.y + bb.height > vp.height) return null;   // a heading out of view is not measured
  const png = await p.screenshot({ clip:bb });
  return p.evaluate(async ([data, h]) => {
    const img = new Image(); img.src = 'data:image/png;base64,' + data; await img.decode();
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height).data, sc = c.height / h;
    const lum = k => 0.3 * d[k] + 0.59 * d[k + 1] + 0.11 * d[k + 2];
    const bg = lum((Math.floor(c.height / 2) * c.width + 2) * 4);
    const rows = [];
    for (let y = 0; y < c.height; y++) { let n = 0; for (let x = 0; x < c.width; x++) if (bg - lum((y * c.width + x) * 4) > 60) n++; rows.push(n) }
    const isLine = n => n > c.width * 0.6;                     // the band's own border lines are not ink
    let top = 0; while (top < rows.length && isLine(rows[top])) top++;
    let bot = rows.length - 1; while (bot > 0 && isLine(rows[bot])) bot--;
    const yy = rows.map((n, y) => n && !isLine(n) ? y : -1).filter(y => y >= 0);
    if (!yy.length) return null;
    return { above:+((yy[0] - top) / sc).toFixed(1), below:+((bot - yy[yy.length - 1]) / sc).toFixed(1) };
  }, [png.toString('base64'), bb.height]);
}

for (const [nm, opt] of [['d1440', { viewport:{ width:1440, height:900 } }], ['phone', devices['iPhone 13']]]) {
  const ctx = await b.newContext(opt), p = await ctx.newPage(); p.on('pageerror', e => errs.push(nm + ' ' + e.message));
  await p.addInitScript(() => { if (!sessionStorage.getItem('s')) { sessionStorage.setItem('s', '1'); localStorage.setItem('ml.broker.collapsed', '0'); localStorage.setItem('ml.ind.v1', JSON.stringify([{ def:'FL03', params:{} }])) } });
  await p.goto(origin + '/terminal-app/'); await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(2500);
  const r = R[nm] = {};

  // 1. Indicators window: one start line for the column header, the group headings and the names; text in the band's middle
  await p.click('#indBtn'); await p.waitForSelector('#indMenu:not([hidden])'); await p.click('#indMenu [data-g="all"]'); await p.waitForTimeout(300);
  r.starts = await p.evaluate(() => {
    const x = el => { if (!el || !el.offsetWidth) return null; const rg = document.createRange(); rg.selectNodeContents(el); const rc = [...rg.getClientRects()][0]; return rc ? Math.round(rc.left * 10) / 10 : null };
    return { col:x(document.querySelector('.im-cols span:nth-child(2)')), sec:[...document.querySelectorAll('.im-list .im-sec')].slice(0, 3).map(x), name:x(document.querySelector('.im-row[data-id] .nmt')) };
  });
  [...r.starts.sec, r.starts.col].filter(v => v !== null).forEach((v, k) => check(`${nm} start ${k}`, Math.abs(v - r.starts.name) <= 1, r.starts));
  r.bands = { cols:await ink(p, '.im-cols'), sec1:await ink(p, '.im-list .im-sec', 0), sec2:await ink(p, '.im-list .im-sec', 1) };
  for (const [k, v] of Object.entries(r.bands)) if (v) check(`${nm} band ${k}`, Math.abs(v.above - v.below) <= 1, v);
  await p.screenshot({ path:`${SP}/look11_${nm}_ind.png`, clip:await p.locator('.im-main').boundingBox() });
  await p.keyboard.press('Escape'); await p.waitForTimeout(200);

  // 1b. EXEC-PANE-ORDER: a pane's Move up / Move down centred on its title's line, between the drawing toolbar and the row
  const paneRow = await p.$('.ind-row.in-pane');
  if (paneRow) {
    const rb = await paneRow.boundingBox(); await p.mouse.move(rb.x + rb.width / 2, rb.y + rb.height + 30); await p.waitForTimeout(250);
    r.move = await p.evaluate(() => { const m = [...document.querySelectorAll('.ind-move')].find(x => getComputedStyle(x).opacity === '1'); if (!m) return null;
      const row = [...document.querySelectorAll('.ind-row.in-pane')].find(x => Math.abs(x.getBoundingClientRect().top - m.getBoundingClientRect().top) < 30), k = row.querySelector('.ind-k').getBoundingClientRect(), mb = m.getBoundingClientRect(), bar = document.querySelector('.dr-bar')?.getBoundingClientRect();
      return { dy:+((mb.top + mb.height / 2) - (k.top + k.height / 2)).toFixed(1), row:+(row.getBoundingClientRect().left - mb.right).toFixed(1), bar:bar ? +(mb.left - bar.right).toFixed(1) : 0 } });
    check(`${nm} pane move buttons`, r.move && Math.abs(r.move.dy) <= 1 && r.move.row >= 0 && r.move.bar >= 0, r.move);
  }
  /* EXEC-QA5-FIX (2026-11-07): an added indicator shows its value on the last candle (a slip once hid every Flow output:
     its "show" flag fell inside a comment, and no other check read the legend's value) */
  r.legend = await p.evaluate(() => [...document.querySelectorAll('.ind-row.in-pane')].map(x => x.querySelector(':scope > b')?.textContent || ''));
  check(`${nm} indicator value shown`, r.legend.length > 0 && r.legend.every(t => /\d/.test(t) && !/^No |^Needs |^Before /.test(t)), r.legend);
  /* EXEC-LEGEND-HIDE (2026-11-08): the legend's last button hides every indicator name (price and panes) and reads its
     count, its text in the middle of the button; a second click brings them back */
  { const shown0 = await p.evaluate(() => [...document.querySelectorAll('.ind-row')].filter(r => r.offsetWidth).length);
    await p.click('.legend-fold'); await p.waitForTimeout(250);
    r.legendHide = await p.evaluate(() => { const b = document.querySelector('.legend-fold'), t = b.querySelector('span'), br = b.getBoundingClientRect(), tr = t?.getBoundingClientRect();
      return { rows:[...document.querySelectorAll('.ind-row')].filter(r => r.offsetWidth).length, n:t?.textContent, dy:tr ? +((tr.top + tr.height / 2) - (br.top + br.height / 2)).toFixed(1) : null } });
    await p.click('.legend-fold'); await p.waitForTimeout(250);
    r.legendHide.back = await p.evaluate(() => [...document.querySelectorAll('.ind-row')].filter(r => r.offsetWidth).length);
    check(`${nm} legend hide`, r.legendHide.rows === 0 && +r.legendHide.n === shown0 && Math.abs(r.legendHide.dy) <= 1 && r.legendHide.back === shown0, { shown0, ...r.legendHide }) }
  // 2. every visible toggle: the thumb in the middle of its track (the Events window open for its master switch)
  await p.click('#evBtn'); await p.waitForTimeout(300);
  r.toggles = await p.evaluate(() => [...document.querySelectorAll('.toggle')].filter(t => t.offsetWidth).map(t => {
    const a = t.querySelector('.track').getBoundingClientRect(), h = t.querySelector('.thumb').getBoundingClientRect();
    return [t.querySelector('input')?.id, +((h.top + h.height / 2) - (a.top + a.height / 2)).toFixed(2)];
  }));
  r.toggles.forEach(([id, dy]) => check(`${nm} toggle ${id}`, Math.abs(dy) <= 0.5, dy));
  await p.screenshot({ path:`${SP}/look11_${nm}_ev.png`, clip:await p.locator('#evPop .ev-head').boundingBox() });
  await p.keyboard.press('Escape'); await p.waitForTimeout(200);

  // 3. right panel (desktop): the period row alone; the market choice at its row's right; Net / Gross first; labels
  if (nm === 'd1440') {
    r.rows = await p.evaluate(() => {
      const right = sel => { const e = document.querySelector(sel); if (!e) return null; const row = e.parentElement.getBoundingClientRect(), x = e.getBoundingClientRect(); return +(row.right - x.right).toFixed(1) };
      return { fd:right('#fdBoard'), acc:right('#accBoard'), bsBoard:right('#bsBoard'), accPeriodHasSelect:!!document.querySelector('#accRange select'),
        bsFirst:document.querySelector('#bsBoard')?.parentElement.firstElementChild.id, accHint:document.querySelector('#accHint').textContent,
        fdLabels:[...document.querySelectorAll('.fdm-eq span, .fdm-row.h span')].map(e => e.textContent).filter(Boolean) };
    });
    for (const k of ['fd', 'acc', 'bsBoard']) check(`row ${k}`, r.rows[k] !== null && Math.abs(r.rows[k]) <= 1, r.rows[k]);
    // and each control row is one line: every child on the same top (the market choice does not drop to a line of its own)
    r.oneLine = await p.evaluate(() => Object.fromEntries(['#fdBoard', '#accBoard', '#bsBoard'].map(s => { const row = document.querySelector(s)?.parentElement;
      return [s, row ? new Set([...row.children].filter(c => c.offsetWidth).map(c => Math.round(c.getBoundingClientRect().top))).size === 1 : null] })));
    for (const [k, v] of Object.entries(r.oneLine)) check(`one line ${k}`, v === true, v);
    check('acc period row', !r.rows.accPeriodHasSelect, r.rows.accPeriodHasSelect);
    // EXEC-RP-LOOK R3/R7: Top brokers' ratio badge on the period row; no tooltip on the map's points
    // R8: no ratio badge; the ladder's marked step carries the ratio in its tooltip
    // R9 (2026-11-08): the ladder's tooltip is the ratio and the verdict's badge only; R10: no level row, no lane caption
    r.accRatio = await p.evaluate(() => ({ badges:document.querySelectorAll('.acc-ratio').length, tip:document.querySelector('.acc-ladder')?.dataset.tip || null,
      lv:document.querySelectorAll('.acc-lv').length, cap:document.querySelectorAll('.acc-cap').length }));
    check('acc ladder tooltip', r.accRatio.badges === 0 && /^[+−]?\d+\.\d{2}% · <span class="tag (acc|dist|neu)( big)?">(Big )?(Acc|Dist|Neutral)<\/span>$/.test(r.accRatio.tip || '') && !r.accRatio.lv && !r.accRatio.cap, r.accRatio);
    r.mapTips = await p.evaluate(() => document.querySelectorAll('.fdm-pt[data-tip], .fdm-pt [data-tip], .fdm-pt[title]').length);
    check('map points without tooltip', r.mapTips === 0, r.mapTips);
    check('bs first', r.rows.bsFirst === 'bsMode', r.rows.bsFirst);
    check('acc hint', !/net|Acc|Dist|Neutral|Regular/.test(r.rows.accHint), r.rows.accHint);
    check('fd labels', !r.rows.fdLabels.some(t => /^[XY] |Top N|X foreign|Y dom/.test(t)), r.rows.fdLabels);
    // the readout folds, stays folded after a reload, and opens again
    const sec = p.locator('.st[data-sec="fdmap"]'); await sec.scrollIntoViewIfNeeded();
    await p.click('.fdm-fold'); await p.waitForTimeout(200);
    r.fold = { stored:await p.evaluate(() => localStorage.getItem('ml.fd.readout')), hidden:await p.$eval('#fdmDetail', e => e.hidden), line:await p.$eval('.fdm-fold', e => e.textContent) };
    await p.screenshot({ path:`${SP}/look11_fd_folded.png`, clip:await sec.boundingBox() });
    await p.reload(); await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(2500);
    r.fold.after_reload = await p.$eval('#fdmDetail', e => e.hidden);
    await p.locator('.fdm-fold').scrollIntoViewIfNeeded(); await p.click('.fdm-fold'); await p.waitForTimeout(200);
    r.fold.reopened = await p.$eval('#fdmDetail', e => !e.hidden);
    check('fold', r.fold.stored === '0' && r.fold.hidden && r.fold.after_reload && r.fold.reopened, r.fold);
    for (const s of ['bs', 'acc', 'fdmap']) { const l = p.locator(`.st[data-sec="${s}"]`); await l.scrollIntoViewIfNeeded(); await p.screenshot({ path:`${SP}/look11_${s}.png`, clip:await l.boundingBox() }) }
    // EXEC-FD-WINDOW: the Foreign × Domestic window's control row is one line with its Board choice at the right, and its
    // table's column header sits in the middle of its band
    const fdPop = p.locator('.st[data-sec="fdmap"] .st-pop'); await fdPop.scrollIntoViewIfNeeded(); await fdPop.click();
    await p.waitForSelector('.fw .pw-fdw'); await p.waitForTimeout(300);
    r.fdWin = await p.evaluate(() => { const row = document.querySelector('.fw:has(.pw-fdw) .pw-ctl'), sel = row.querySelector('select');
      return { oneLine:new Set([...row.children].map(c => Math.round(c.getBoundingClientRect().top))).size === 1, right:+(row.getBoundingClientRect().right - sel.getBoundingClientRect().right).toFixed(1) } });
    check('fd window row', r.fdWin.oneLine && Math.abs(r.fdWin.right) <= 1, r.fdWin);
    r.fdWin.head = await ink(p, '.fw .pw-fdt thead tr');
    if (r.fdWin.head) check('fd window table header', Math.abs(r.fdWin.head.above - r.fdWin.head.below) <= 1, r.fdWin.head);
    await p.screenshot({ path:`${SP}/look11_fd_window.png`, clip:await p.locator('.fw:has(.pw-fdw)').boundingBox() });
  }
  await ctx.close();
}
/* EXEC-QA5-FIX (re-test 2026-11-07, N1): at the right panel's minimum width (260 px) no figure of a panel table runs into
   its neighbour (two decimals once did: "−57.56%+30.44%−27.12%"): every cell's text fits its cell */
{ const ctx = await b.newContext({ viewport:{ width:1440, height:900 } }), p = await ctx.newPage(); p.on('pageerror', e => errs.push('narrow ' + e.message));
  await p.addInitScript(() => { localStorage.setItem('ml.broker.collapsed', '0'); localStorage.setItem('ml.broker.w', '260') });
  await p.goto(origin + '/terminal-app/'); await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(2500);
  R.narrow = await p.evaluate(() => ({ panel:Math.round(document.getElementById('brokerPanel').getBoundingClientRect().width),
    over:[...document.querySelectorAll('.fdm-row span, .rp-t td, .rp-t th')].filter(e => e.offsetWidth && e.scrollWidth > e.clientWidth + 1).map(e => e.textContent).slice(0, 8) }));
  check('narrow panel cells fit', R.narrow.panel <= 270 && !R.narrow.over.length, R.narrow);
  await ctx.close() }
/* EXEC-FLOW-NEW-3 (user 2026-11-08): FL51 Loaders' floating box. Its head (title, period, two buttons) is one line with its
   text in the middle of the band; the box sits inside the chart and stays there after a drag past the chart's edge; the
   table's first column starts where the head's title starts. EXEC-RP-LOOK-2 B: a settings dialog's open control has no
   border line, only the soft shadow of the Indicators window's search box. */
{ const ctx = await b.newContext({ viewport:{ width:1440, height:900 } }), p = await ctx.newPage(); p.on('pageerror', e => errs.push('box ' + e.message));
  await p.addInitScript(() => { if (!sessionStorage.getItem('s')) { sessionStorage.setItem('s', '1'); localStorage.setItem('ml.ind.v1', JSON.stringify([{ def:'FL51', params:{ lines:true } }])) } });
  await p.goto(origin + '/terminal-app/'); await p.waitForFunction(() => !document.querySelector('.ml-boot'), null, { timeout:30000 }); await p.waitForTimeout(3000);
  const geo = () => p.evaluate(() => { const box = document.querySelector('.ind-box'), st = box.parentElement.getBoundingClientRect(), r = box.getBoundingClientRect(), head = box.querySelector('.ldb-head');
    return { inside:r.left >= st.left && r.top >= st.top && r.right <= st.right && r.bottom <= st.bottom,
      headLines:new Set([...head.children].map(c => Math.round(c.getBoundingClientRect().top + c.getBoundingClientRect().height / 2))).size,
      col:(() => { const th = box.querySelector('.ldb-t th'), mk = box.querySelector('.ldb-b'), t0 = head.querySelector('b').getBoundingClientRect().left;
        return [th.getBoundingClientRect().left + parseFloat(getComputedStyle(th).paddingLeft) - t0, mk.getBoundingClientRect().left + parseFloat(getComputedStyle(mk).paddingLeft) - t0].map(v => +v.toFixed(1)) })(), rows:box.querySelectorAll('.ldb-t tbody tr').length } });
  R.box = { first:await geo(), head:await ink(p, '.ldb-head b') };
  const h = await p.locator('.ldb-head b').boundingBox(); await p.mouse.move(h.x + 4, h.y + 4); await p.mouse.down(); await p.mouse.move(h.x + 900, h.y + 900, { steps:5 }); await p.mouse.up();
  R.box.dragged = await geo();
  check('loaders box head one line, inside the chart, rows', R.box.first.headLines === 1 && R.box.first.inside && R.box.dragged.inside && R.box.first.rows >= 1, R.box);
  check('loaders box columns start under the head title', R.box.first.col.every(v => Math.abs(v) <= 1), R.box.first.col);
  check('loaders box head ink centred', !R.box.head || Math.abs(R.box.head.above - R.box.head.below) <= 1, R.box.head);
  // B: the open settings control
  await p.evaluate(() => (document.querySelector('.ind-row[data-def="FL51"] [data-act="cfg"]')).click());
  await p.waitForSelector('.idlg select.idlg-in, .idlg .idlg-cbtn', { timeout:5000 }).catch(() => {});
  R.focus = await p.evaluate(() => { const el = document.querySelector('.idlg select.idlg-in, .idlg .idlg-cbtn'); if (!el) return null; el.focus(); const cs = getComputedStyle(el);
    return { border:cs.borderTopColor, shadow:cs.boxShadow !== 'none', outline:cs.outlineStyle } });
  check('settings open control: no border line, soft shadow', !!R.focus && /rgba\(0, 0, 0, 0\)|transparent/.test(R.focus.border) && R.focus.shadow && R.focus.outline === 'none', R.focus);
  await ctx.close() }
console.log(JSON.stringify(R)); console.log('errs', errs); console.log(bad.length ? 'FAIL\n' + bad.join('\n') : 'PASS');
await b.close(); close(); process.exit(bad.length || errs.length ? 1 : 0);
