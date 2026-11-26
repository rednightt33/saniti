/* EXEC-SECTOR-ANALYSIS S4, the Breadth tab (final/click_inventory.md section 9; formulas.md section 6). One selection (the
   market or one sector) drives the five cards. Every share is real now: the sectors' breadth history is
   Feature_08_Group_Daily (sector-series breadth, G4), the stocks' distance from their EMAs and days in status are the day
   file's (G6, G7), and their close and volume too (G8). EMA50 and EMA200 only (decision C1). */
import * as M from '../model.ts';
import { type Card, type Ctx, type Detail } from '../ctx.ts';
import { $, $$, DOT, H3, SEG, esc, heat, msNote, msTh, msWire, onSeg, tipHide, tipShow, xHide, xShow, xTag } from '../ui.ts';
import { customRange, periodOpts, SEL_SECTOR } from './ov.ts';
import { W } from '../words.ts';

/** the tab's selection: the market (every stock) or one sector */
export const brSel = (c: Ctx) => (c.D.names.includes(c.S.bhS) ? c.S.bhS : c.D.market);
const isSel = (c: Ctx, n: string) => brSel(c) === n;
/** choose the market or a sector for the tab; the chosen sector again returns to the market; a sector also locks it */
export function brSet(c: Ctx, v: string) {
  const m = c.D.market, cur = brSel(c);
  v = v === cur && v !== m ? m : v;
  c.S.bhS = v;
  if (v !== m) c.S.pin = v;
  c.redraw();
}
const who = (c: Ctx, n: string) => (n === c.D.market ? W.all(c.D.market) : c.D.short(n));
const BHC = ['var(--c1)', 'var(--c5)', 'var(--c3)', 'var(--c2)'];
const line = (c: Ctx, g: string, ms: 50 | 200) => M.breadthLine(c.D.breadth(g), ms);
const rowsOf = (c: Ctx, g: string) => c.D.members(g);

/* ===================== Breadth vs Price (logic.js L804-878) ===================== */
export const brH: Card = {
  id: 'brH', tab: 'br', cls: 'br-h',
  render(el, c) {
    const D = c.D, S = c.S, E = D.E, MS = S.bhM, SEL = brSel(c), lab = `EMA${MS}`, lo = 30, hi = 70, IH = D.IH;
    const bs = line(c, SEL, MS), FIRST = Math.max(1, bs.findIndex(x => x != null)), MIN = 20;
    const XS = S.bhX.filter(x => x !== SEL && (x === D.market || D.names.includes(x))).slice(0, 4), xs = XS.map(x => line(c, x, MS));
    const HID = new Set(S.bhHid.filter(x => x === '__px' || x === SEL || XS.includes(x)));
    // the visible sessions: a zoom or drag (stored as dates), a Custom range or a preset period
    let v0: number, v1: number;
    const custom = S.bhP === 'C' && S.bhR ? M.rangeIn(D.dates, S.bhR, E) : null;
    if (S.bhV) { v0 = Math.max(FIRST, M.seriesEnd(D.dates, S.bhV[0])); v1 = Math.min(E, M.seriesEnd(D.dates, S.bhV[1])); if (v1 - v0 < MIN) { v0 = Math.max(FIRST, E - D.P('6M')); v1 = E } }
    else if (custom) { v0 = Math.max(FIRST, custom.base); v1 = custom.last }
    else { v0 = Math.max(FIRST, E - D.P(S.bhP === 'C' ? '6M' : S.bhP)); v1 = E }
    const now = bs[E], d5 = M.minus(now, bs[E - 5]);
    const legend = [[SEL, 'var(--text)', W.brH.legTip(who(c, SEL), M.pct(now, 1), lab, M.dateLabel(D.dates[E]))], ...XS.map((x, k) => [x, BHC[k], W.brH.legTip(who(c, x), M.pct(xs[k][E], 1), lab, M.dateLabel(D.dates[E]))]), ['__px', '', W.brH.pxTip(D.market)]];
    el.innerHTML = H3(W.brH.title, W.brH.sub(SEL === D.market ? null : D.short(SEL), lab, D.market),
      `<span class="plab">${esc(W.brH.show)}</span><button class="bms" type="button" data-show aria-haspopup="true" aria-expanded="false" aria-label="${esc(W.brH.showAria([SEL, ...XS].map(x => who(c, x))))}"><span class="bmn">${esc(who(c, SEL))}</span>${XS.length ? `<span class="bmc">+${XS.length}</span>` : ''}<svg class="ic ic-sm"><use href="#i-chev"/></svg></button>`
      + SEG('m', W.brH.above, [[50, 'EMA50'], [200, 'EMA200']], MS) + SEG('p', W.brH.period, periodOpts(['3M', '6M', '1Y', 'C']), presetOn()), c.win ? null : 'brH')
      + `<div class="bhk"><b>${now == null ? '—' : Math.round(now) + '%'}</b><span>${esc(W.brH.head(lab, M.dateLabel(D.dates[E])))}${d5 == null ? '' : ` · <span class="${M.cls(d5)}">${M.ppx(d5, 1)} pp</span> ${esc(W.brH.vs5)}`}</span><span class="bhx">${legend.map(([x, col, t]) => `<button type="button" class="bxl${x === '__px' ? ' ihp' : ''}${HID.has(x) ? ' off' : ''}" data-h="${esc(x)}" aria-pressed="${!HID.has(x)}" title="${esc(W.brH.hideTip(t, HID.has(x)))}"><i${col ? ` style="background:${col}"` : ''}></i>${esc(x === '__px' ? W.brH.price(D.market) : x === D.market ? D.market : D.short(x))}</button>`).join('')}</span></div>`
      + `<div class="bhc bz" data-chart tabindex="0" aria-label="${esc(W.brH.aria(lab))}"></div>`
      + `<div class="lgd"><span>${esc(W.brH.foot(hi, lo, c.example))}</span><span class="sp"></span><span data-range></span></div>`;
    function presetOn() { if (S.bhV) return ''; if (S.bhP === 'C') return custom ? 'C' : '6M'; return S.bhP }
    $$('.bhx .bxl', el).forEach(b => (b.onclick = () => { const h = b.dataset.h as string, s = new Set(HID); s.has(h) ? s.delete(h) : s.add(h); S.bhHid = [...s]; c.redraw() }));
    onSeg(el, 'm', v => { S.bhM = +v as 50 | 200; S.bdS = []; c.redraw() });
    onSeg(el, 'p', (v, btn) => { if (v === 'C') { customRange(c, btn, S.bhR, r => { S.bhP = 'C'; S.bhR = r; S.bhV = null }, { min: MIN }); return } S.bhP = v; S.bhV = null; c.redraw() });
    // Show: one list of the lines on the chart (at most 5); the main line (ink) is the tab's selection
    const all = [SEL, ...XS], full = all.length >= 5, ba = $('[data-show]', el);
    const pop = document.createElement('div');
    pop.className = 'bxp pop'; pop.setAttribute('role', 'group'); pop.setAttribute('aria-label', W.brH.showAria(all.map(x => who(c, x)))); pop.hidden = true;
    pop.innerHTML = `<div class="bxh">${esc(W.brH.showHead(all.length))}</div>${[D.market, ...D.names].map(n => {
      const on = all.includes(n), mn = n === SEL, k = XS.indexOf(n), dis = (!on && full) || (mn && all.length === 1);
      return `<label class="${dis && !on ? 'dis' : ''}${mn ? ' mn' : ''}"><input type="checkbox" value="${esc(n)}"${on ? ' checked' : ''}${dis ? ' disabled' : ''}><span class="bxn">${esc(who(c, n))}</span><span class="bmb">${mn ? `<span class="bmt">${esc(W.brH.main)}</span>` : on ? `<button type="button" class="bmm" data-m="${esc(n)}">${esc(W.brH.setMain)}</button>` : ''}</span><i class="bsw" style="background:${on ? (mn ? 'var(--text)' : BHC[k]) : 'transparent'}"></i></label>`;
    }).join('')}<div class="bxf">${esc(W.brH.showFoot)}</div>`;
    el.appendChild(pop);
    const place = () => { const cr = el.getBoundingClientRect(), r = ba.getBoundingClientRect(); pop.style.top = r.bottom - cr.top + 6 + 'px'; pop.style.left = Math.max(8, Math.min(r.left - cr.left, cr.width - 280)) + 'px' };
    const open = (o: boolean) => { pop.hidden = !o; ba.setAttribute('aria-expanded', String(o)); if (o) place() };
    if ((c as any)._showOpen) { open(true); (c as any)._showOpen = false }
    ba.onclick = e => { e.stopPropagation(); open(pop.hidden) };
    const reopen = () => { (c as any)._showOpen = true };
    $$('input', pop).forEach(i => (i.onchange = () => {
      const n = (i as HTMLInputElement).value;
      reopen();
      if ((i as HTMLInputElement).checked) { S.bhX = [...XS, n]; c.redraw(); return }
      if (n === SEL) { const nx = XS[0] || D.market; S.bhX = XS.slice(1); brSet(c, nx); return }
      S.bhX = XS.filter(x => x !== n); c.redraw();
    }));
    $$('.bmm', pop).forEach(b => (b.onclick = e => { e.preventDefault(); e.stopPropagation(); const n = b.dataset.m as string; S.bhX = [SEL, ...XS.filter(x => x !== n)]; reopen(); brSet(c, n) }));
    pop.onkeydown = e => { if (e.key === 'Escape') { e.stopPropagation(); open(false); ba.focus() } };
    el.addEventListener('pointerdown', e => { if (!pop.hidden && !pop.contains(e.target as Node) && !ba.contains(e.target as Node)) open(false) });
    const box = $('[data-chart]', el), rng = $('[data-range]', el);
    let g: { L: number; R: number; n: number; X(i: number): number; Y(v: number): number; B: number } | null = null;
    const draw = () => {
      const Wd = box.clientWidth - 32, H = box.clientHeight; if (Wd <= 0 || H <= 0) return;
      const n = v1 - v0 + 1, L = 40, R = Wd - 52, B = H - 18, X = (i: number) => L + ((i - v0) / Math.max(1, n - 1)) * (R - L), Y = (y: number) => 4 + ((100 - y) / 100) * (B - 4);
      let plo = Infinity, phi = -Infinity;
      for (let i = v0; i <= v1; i++) if (IH[i] != null) { plo = Math.min(plo, IH[i] as number); phi = Math.max(phi, IH[i] as number) }
      const ppd = (phi - plo) * 0.06 || 1, ptk = M.ticks(plo - ppd, phi + ppd, 4), q0 = Math.min(plo - ppd, ptk[0]), q1 = Math.max(phi + ppd, ptk[ptk.length - 1]), YP = (v: number) => 4 + ((q1 - v) / (q1 - q0)) * (B - 4);
      const pth = (a: M.N[], y: (v: number) => number) => { let s = '', pen = false; for (let i = v0; i <= v1; i++) { const v = a[i]; if (v == null) { pen = false; continue } s += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + y(v).toFixed(1); pen = true } return s };
      const picks = [0, 1, 2, 3].map(k => Math.round(v0 + (k / 3) * (n - 1))), labs = M.axisDates(D.dates.slice(v0, v1 + 1), picks.map(i => i - v0));
      let o = `<rect x="${L}" y="${Y(100)}" width="${R - L}" height="${Y(hi) - Y(100)}" fill="color-mix(in srgb,var(--up) 7%,transparent)"/><rect x="${L}" y="${Y(lo)}" width="${R - L}" height="${Y(0) - Y(lo)}" fill="color-mix(in srgb,var(--down) 7%,transparent)"/>`
        + [0, 25, 50, 75, 100].map(y => `<line x1="${L}" x2="${R}" y1="${Y(y)}" y2="${Y(y)}" stroke="${y === 50 ? 'var(--chart-base)' : 'var(--chart-grid)'}"/><text class="ax" x="${L - 6}" y="${Y(y) + 3.5}" text-anchor="end">${y}%</text>`).join('')
        + (Number.isFinite(plo) ? ptk.filter(t => t >= q0 && t <= q1).map(t => `<text class="ax" x="${R + 6}" y="${YP(t) + 3.5}">${t.toLocaleString('en-US', { maximumFractionDigits: 0 })}</text>`).join('') : '') + `<line x1="${R}" x2="${R}" y1="4" y2="${B}" stroke="var(--border)"/>`
        + (HID.has('__px') || !Number.isFinite(plo) ? '' : `<path d="${pth(IH, YP)}" fill="none" stroke="var(--text-3)" stroke-width="1.2" stroke-dasharray="4 3" stroke-linejoin="round"/>`);
      const mk = S.bhMk ? D.dates.indexOf(S.bhMk) : -1;
      if (mk >= v0 && mk <= v1 && bs[mk] != null) { const x = X(mk), y = Y(bs[mk] as number); o += `<line x1="${x}" x2="${x}" y1="4" y2="${B}" stroke="var(--text)"/><line x1="${L}" x2="${R}" y1="${y}" y2="${y}" stroke="var(--text)" stroke-dasharray="3 3"/><circle cx="${x}" cy="${y}" r="4.5" fill="var(--text)" stroke="var(--surface)" stroke-width="1.5"/><text class="ax" x="${L + 4}" y="${y - 5}" style="fill:var(--text);font-weight:700">${(bs[mk] as number).toFixed(1)}%</text>` }
      o += xs.map((a, k) => (HID.has(XS[k]) ? '' : `<path d="${pth(a, Y)}" fill="none" stroke="${BHC[k]}" stroke-width="1.4" stroke-linejoin="round"/>`)).join('')
        + (HID.has(SEL) ? '' : `<path d="${pth(bs, Y)}" fill="none" stroke="var(--text)" stroke-width="1.7" stroke-linejoin="round"/>`)
        + picks.map((i, k) => `<text class="ax" x="${X(i)}" y="${H - 4}" text-anchor="${k === 0 ? 'start' : k === 3 ? 'end' : 'middle'}">${esc(labs[k])}</text>`).join('')
        + `<line class="hv" y1="0" y2="${B}" stroke="var(--text-3)" stroke-dasharray="2 3" display="none"/><circle class="hd" r="3.5" fill="var(--text)" stroke="var(--surface)" stroke-width="1.5" display="none"/>`;
      box.innerHTML = `<svg width="${Wd}" height="${H}" aria-hidden="true">${o}</svg>`;
      g = { L, R, n, X, Y, B };
      rng.textContent = `${M.rangeLabel(D.dates[v0], D.dates[v1])}${DOT}${W.sessions(n - 1)}`;
    };
    box.dataset.ownTip = '';
    const at = (cx: number) => { const r = box.getBoundingClientRect(); return v0 + ((cx - r.left - 16 - (g as any).L) / ((g as any).R - (g as any).L)) * ((g as any).n - 1) };
    const keep = (a: number, b: number) => { S.bhV = [D.dates[a], D.dates[b]] };
    const set = (a: number, b: number, save = true) => {
      const span = Math.max(MIN, Math.min(E - FIRST, b - a)); a = Math.round(a); b = a + Math.round(span);
      if (b > E) { b = E; a = E - Math.round(span) }
      if (a < FIRST) { a = FIRST; b = a + Math.round(span) }
      if (a === v0 && b === v1) return;
      v0 = a; v1 = b; if (save) keep(v0, v1); draw(); $$('[data-seg=p] button', el).forEach(x => { x.classList.remove('on'); x.setAttribute('aria-pressed', 'false') });
    };
    const zoom = (f: number, cx: number) => { const span = v1 - v0, ns = Math.max(MIN, Math.min(E - FIRST, span * f)), t = (cx - v0) / (span || 1); set(cx - t * ns, cx - t * ns + ns) };
    const hide = () => { if (!g) return; xHide($('line.hv', box) as unknown as SVGLineElement); $('circle.hd', box)?.setAttribute('display', 'none'); tipHide() };
    const show = (e: PointerEvent | WheelEvent) => {
      if (!g) return; const i = Math.round(at(e.clientX)); if (i < v0 || i > v1) { hide(); return }
      const vx = $('line.hv', box) as unknown as SVGLineElement, vd = $('circle.hd', box);
      xShow(vx, g.X(i)); xTag(vx, M.tagDate(D.dates[i]));
      if (bs[i] != null) { vd.setAttribute('cx', String(g.X(i))); vd.setAttribute('cy', String(g.Y(bs[i] as number))); vd.removeAttribute('display') }
      const px = SEL === D.market ? IH : D.sec(SEL), chg = M.retAt(px, v0, i);
      tipShow(`<span class="d">${esc(M.dateLabel(D.dates[i], true, true))}</span><div class="r"><i style="background:var(--text)"></i><span>${esc(who(c, SEL))}</span><b>${M.pct(bs[i], 1).replace('+', '')}</b></div>${XS.map((x, k) => `<div class="r"><i style="background:${BHC[k]}"></i><span>${esc(who(c, x))}</span><b>${M.pct(xs[k][i], 1).replace('+', '')}</b></div>`).join('')}<div class="r"><span>${esc(SEL === D.market ? D.market : W.rsL.index(D.short(SEL)))}</span><b>${M.level(px[i])} <span class="${M.cls(chg)}">${M.pct(chg, 1)}</span></b></div>${SEL !== D.market ? `<div class="r"><span>${esc(D.market)}</span><b>${M.level(IH[i])}</b></div>` : ''}<div class="r"><span class="muted">${esc(W.brH.zone(bs[i], hi, lo))}</span></div>`, e);
    };
    if (!c.example) {
      box.addEventListener('wheel', e => { if (!g) return; e.preventDefault(); zoom(e.deltaY < 0 ? 1 / 1.18 : 1.18, Math.max(v0, Math.min(v1, at(e.clientX)))); show(e) }, { passive: false });
      let dr: { x: number; a: number; b: number; per: number } | null = null;
      box.onpointerdown = e => { if (e.pointerType !== 'mouse' || e.button !== 0 || !g) { show(e); return } dr = { x: e.clientX, a: v0, b: v1, per: (g.n - 1) / (g.R - g.L) }; box.setPointerCapture(e.pointerId); box.classList.add('drag'); hide() };
      box.onpointermove = e => { if (dr) { const d = (e.clientX - dr.x) * dr.per; set(dr.a - d, dr.b - d, false) } else show(e) };
      box.onpointerup = box.onpointercancel = () => { if (dr && (v0 !== dr.a || v1 !== dr.b)) keep(v0, v1); dr = null; box.classList.remove('drag') };
      box.onkeydown = e => {
        const cc = (v0 + v1) / 2, sh = Math.max(1, Math.round((v1 - v0) / 10));
        if (e.key === '+' || e.key === '=') zoom(1 / 1.25, cc); else if (e.key === '-' || e.key === '_') zoom(1.25, cc); else if (e.key === 'ArrowLeft') set(v0 - sh, v1 - sh); else if (e.key === 'ArrowRight') set(v0 + sh, v1 + sh); else return;
        e.preventDefault();
      };
    } else box.onpointermove = e => show(e);
    box.onpointerleave = e => { if (e.pointerType === 'mouse') hide() };
    requestAnimationFrame(draw);
  },
  detail(c): Detail {
    const D = c.D, S = c.S, SEL = brSel(c), MS = S.bhM, px = SEL === D.market ? D.IH : D.sec(SEL), bs = line(c, SEL, MS), rows: any[] = [];
    for (let i = D.E; i > Math.max(0, D.E - 60); i--) rows.push({ i, name: M.dateLabel(D.dates[i], false, true), c: px[i], r: M.retAt(px, i - 1, i), b: bs[i], db: M.minus(bs[i], bs[i - 1]), d5: M.minus(bs[i], bs[i - 5]) });
    return {
      title: W.brH.dTitle(who(c, SEL)), sub: W.brH.dSub(rows.length, MS), ctl: SEL_SECTOR(c, SEL, true), onSel: v => brSet(c, v),
      cols: [{ k: 'i', l: W.col.date, num: true, f: (_v, r) => r.name }, { k: 'c', l: W.col.close, num: true, f: v => M.level(v) }, { k: 'r', l: '1D', num: true, tone: true, f: v => M.pct(v) },
             { k: 'b', l: `> EMA${MS}`, num: true, f: v => v.toFixed(1) + '%' }, { k: 'db', l: W.col.d('1D'), num: true, tone: true, f: v => M.pp(v, 1) }, { k: 'd5', l: W.col.d('5D'), num: true, tone: true, f: v => M.pp(v, 1) }],
      rows, sort: ['i', 1], onRow: r => { S.bhMk = S.bhMk === D.dates[r.i] ? null : D.dates[r.i]; c.redraw() }, isSel: r => D.dates[r.i] === S.bhMk,
      read: W.brH.read, ex: r => W.brH.ex(r.name, r.b, MS, r.d5),
    };
  },
};

/* ===================== Breadth Heatmap Table (logic.js L894-925) ===================== */
const EXTRA = ([50, 200] as const).flatMap(ms => ([[3, '3D'], [5, '1W'], [20, '1M']] as [number, string][]).map(([n, hz]) => ({ k: `${ms}_${n}`, ms, n, hz, dup: ms === 50 && n === 5 })));
export const brT: Card = {
  id: 'brT', tab: 'br', cls: 'br-t',
  render(el, c) {
    const D = c.D, S = c.S, CNT = S.btC, E = D.E, DEF: M.Level = ['e50', 1];
    const COLS: [string, string, keyof M.Row | null][] = [['u1', W.col.up('1D'), 'r1d'], ['u5', W.col.up('1W'), 'r5d'], ['u21', W.col.up('1M'), 'r1m'], ['e50', '> EMA50', null], ['e200', '> EMA200', null]];
    const agg = (g: string) => {
      const ms = rowsOf(c, g), o: any = { nm: g, sn: g === D.market ? W.allShort(D.market) : D.short(g), N: ms.length, cnt: {}, den: {} };
      for (const [k, , f] of COLS) {
        if (f) { const a = M.aud(ms.map(x => x[f] as M.N)); o.cnt[k] = a.u; o.den[k] = a.N; o[k] = M.share(a.u, a.N) }
        else { const s = M.flagShare(ms.map(x => (k === 'e50' ? x.e50 : x.e200))); o.cnt[k] = s.a; o.den[k] = s.n; o[k] = s.p }
      }
      const bl = line(c, g, 50); o.dl = M.minus(bl[E], bl[E - 5]);
      EXTRA.forEach(x => { const l = line(c, g, x.ms); o['x_' + x.k] = M.minus(l[E], l[E - x.n]) });
      return o;
    };
    const XS = c.win ? EXTRA.filter(x => S.btX.includes(x.k)) : [];
    const rows = D.names.map(agg), all = agg(D.market);
    const SK = M.msKeep(S.btTS, k => ['sn', 'N', 'dl', ...COLS.map(x => x[0]), ...XS.map(x => 'x_' + x.k)].includes(k));
    M.msSort(rows, SK, { sn: 1 }, DEF);
    const LAB: Record<string, string> = { sn: W.col.sector, N: W.col.stocks, dl: W.brT.dl, ...Object.fromEntries(COLS.map(x => [x[0], x[1]])), ...Object.fromEntries(XS.map(x => ['x_' + x.k, W.brT.dx(x.ms, x.hz)])) };
    const hc = (v: M.N, n: number, N: number, gap: boolean) => (v == null ? `<td class="hc${gap ? ' gap' : ''}">—</td>` : `<td class="hc${gap ? ' gap' : ''}" style="${heat(v, 50, 50)}" data-tip="${esc(W.brT.cellTip(n, N, v))}">${CNT === 'cnt' ? `${n}<small>/${N}</small>` : Math.round(v) + '%'}</td>`);
    const dcell = (v: M.N, gap: boolean) => (v == null ? `<td class="hc${gap ? ' gap' : ''}">—</td>` : `<td class="hc${gap ? ' gap' : ''}" style="${heat(v, 25)}">${M.ppx(v, 0)} pp</td>`);
    const row = (r: any, isAll: boolean) => `<tr class="${isAll ? 'all' : ''}${isSel(c, r.nm) ? ' cur' : ''}" data-n="${esc(r.nm)}" role="button" tabindex="0"><td class="l"><b>${esc(r.sn)}</b></td><td>${r.N}</td>${COLS.map(([k], j) => hc(r[k], r.cnt[k], r.den[k], j === 3)).join('')}${dcell(r.dl, true)}${XS.map((x, j) => dcell(r['x_' + x.k], j === 0)).join('')}</tr>`;
    const th = (k: string, lab: string, cl = '', tip = '') => msTh(SK, k, esc(lab), cl, tip, { def: DEF, txt: k === 'sn' });
    const add = c.win ? `<span class="btx"><button class="btn sm" type="button" data-add aria-haspopup="true" aria-expanded="false">${esc(W.brT.addCol(XS.length))}</button><span class="btxp pop" role="group" aria-label="${esc(W.brT.addAria)}" hidden><span class="btxh">${esc(W.brT.addHead)}</span>${([50, 200] as const).map(ms => `<span class="btxr"><b>EMA${ms}</b>${EXTRA.filter(x => x.ms === ms).map(x => `<label><input type="checkbox" value="${x.k}"${XS.includes(x) ? ' checked' : ''}${x.dup ? ` disabled title="${esc(W.brT.shown)}"` : ''}>${x.hz}</label>`).join('')}</span>`).join('')}</span></span>` : '';
    el.innerHTML = H3(W.brT.title, W.brT.sub, add + SEG('c', W.brT.show, [['pct', '%'], ['cnt', W.brT.count]], CNT), c.win ? null : 'brT')
      + `<div class="tbl-wrap" data-scroll="x"><table class="tbl padat${brSel(c) !== D.market ? ' has' : ''}"><colgroup><col class="c-nm">${'<col>'.repeat(7 + XS.length)}</colgroup><thead><tr>${th('sn', LAB.sn, 'l')}${th('N', LAB.N)}${COLS.map(([k, l], j) => th(k, l, j === 3 ? 'gap' : '', W.brT.colTip(k))).join('')}${th('dl', LAB.dl, 'gap', W.brT.dlTip)}${XS.map((x, j) => th('x_' + x.k, LAB['x_' + x.k], j ? '' : 'gap', W.brT.dxTip(x.ms, x.hz))).join('')}</tr></thead><tbody>${row(all, true)}${rows.map(r => row(r, false)).join('')}</tbody></table></div>`
      + `<div class="lgd">${msNote(SK, LAB, { sn: 1 })}<span>${esc(W.brT.foot)}</span><span class="sp"></span><span>${esc(M.dateLabel(D.dates[E]))}</span></div>`;
    onSeg(el, 'c', v => { S.btC = v; c.redraw() });
    msWire(el, SK, () => c.redraw(), DEF, 'th[data-k]');
    $$('tbody tr[data-n]', el).forEach(r => {
      const go = () => brSet(c, r.dataset.n as string);
      r.onclick = go; r.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === r) { e.preventDefault(); go() } };
    });
    if (c.win) {
      const pop = $('.btxp', el), b = $('[data-add]', el), open = (o: boolean) => { pop.hidden = !o; b.setAttribute('aria-expanded', String(o)) };
      if ((c as any)._addOpen) { open(true); (c as any)._addOpen = false }
      b.onclick = e => { e.stopPropagation(); open(pop.hidden) };
      $$('input', pop).forEach(i => (i.onchange = () => { S.btX = $$<HTMLInputElement>('input:checked', pop).map(x => x.value); (c as any)._addOpen = true; c.redraw() }));
      pop.onkeydown = e => { if (e.key === 'Escape') { e.stopPropagation(); open(false); b.focus() } };
      el.addEventListener('pointerdown', e => { if (!pop.hidden && !(e.target as Element).closest('.btx')) open(false) });
    }
  },
  detail(c): Detail {
    const D = c.D, E = D.E, f = (g: string) => { const a = line(c, g, 50), b = line(c, g, 200); return { a0: a[E], a5: M.minus(a[E], a[E - 5]), a21: M.minus(a[E], a[E - D.P('1M')]), b0: b[E], b5: M.minus(b[E], b[E - 5]), b21: M.minus(b[E], b[E - D.P('1M')]) } };
    const rows = [{ nm: D.market, name: W.all(D.market), ...f(D.market) }, ...D.names.map(nm => ({ nm, name: D.short(nm), ...f(nm) }))];
    const pc = (v: number) => v.toFixed(1) + '%';
    return {
      title: W.brT.dTitle, sub: W.brT.dSub,
      cols: [{ k: 'name', l: W.col.sector }, { k: 'a0', l: '> EMA50', num: true, f: pc }, { k: 'a5', l: W.col.d('1W'), num: true, tone: true, f: v => M.pp(v, 1) }, { k: 'a21', l: W.col.d('1M'), num: true, tone: true, f: v => M.pp(v, 1) },
             { k: 'b0', l: '> EMA200', num: true, f: pc }, { k: 'b5', l: W.col.d('1W'), num: true, tone: true, f: v => M.pp(v, 1) }, { k: 'b21', l: W.col.d('1M'), num: true, tone: true, f: v => M.pp(v, 1) }],
      rows, sort: ['a5', 1], onRow: r => brSet(c, r.nm), isSel: r => r.nm !== D.market && r.nm === brSel(c),
      read: W.brT.read, ex: r => W.brT.ex(r.name, r.a0, r.a5),
    };
  },
};

/* ===================== Breadth by sector (logic.js L735-746) ===================== */
export const brA: Card = {
  id: 'brA', tab: 'br', cls: 'br-a',
  render(el, c) {
    const D = c.D, S = c.S, Md = S.brM, ih5 = M.ret(D.IH, D.E, D.P('1W'));
    const rows = D.names.map(nm => {
      const ms = rowsOf(c, nm);
      if (Md === 'ema') { const s = M.flagShare(ms.map(x => x.e50)); return { nm, a: s.a, n: s.n, v: s.p } }
      const k = ms.filter(x => x.r5d != null), a = Md === 'ihsg' ? k.filter(x => ih5 != null && (x.r5d as number) > ih5).length : k.filter(x => (x.r5d as number) > 0).length;
      return { nm, a, n: k.length, v: M.share(a, k.length) };
    }).filter(r => r.v != null).sort((a, b) => (b.v as number) - (a.v as number)) as { nm: string; a: number; n: number; v: number }[];
    el.innerHTML = H3(W.brA.title, W.brA.sub(Md, M.pct(ih5), D.market, M.dateLabel(D.dates[D.E])), SEG('m', W.brA.measure, [['ema', '% > EMA50'], ['ihsg', `% > ${D.market} 5D`], ['pos', '% > 0% 5D']], Md), c.win ? null : 'brA')
      + `<div class="tb"><div class="dots"><div class="r ax"><span></span><div class="tk"><em style="left:0">0%</em><em style="left:50%">50%</em><em style="left:100%">100%</em></div><b></b></div>`
      + rows.map(r => `<div class="r${isSel(c, r.nm) ? ' pk' : ''}" data-n="${esc(r.nm)}" role="button" tabindex="0" aria-pressed="${isSel(c, r.nm)}" data-tip="${esc(`<b>${esc(r.nm)}</b><br>${esc(W.brA.tip(r.a, r.n, r.v.toFixed(1), Md, M.pct(ih5), D.market))}`)}"><span>${esc(D.short(r.nm))}</span><div class="tk"><i class="fill" style="width:${r.v}%"></i><i class="d${r.v >= 50 ? ' p' : ' n'}" style="left:${r.v}%"></i></div><b>${Math.round(r.v)}%</b></div>`).join('')
      + `</div></div><div class="lgd"><span>${esc(W.brA.foot)}</span></div>`;
    onSeg(el, 'm', v => { S.brM = v; c.redraw() });
    $$('.dots .r[data-n]', el).forEach(r => {
      const go = () => brSet(c, r.dataset.n as string);
      r.onclick = go; r.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go() } };
    });
  },
  detail(c): Detail {
    const D = c.D, SEL = brSel(c), tg = (v: 0 | 1 | null) => (v == null ? '—' : `<span class="tag ${v ? 'pos' : 'neg'}">${esc(v ? W.above : W.below)}</span>`);
    const rows = rowsOf(c, SEL).map(x => ({ ...x, name: x.t, a: x.e50, ah: tg(x.e50), b: x.e200, bh: tg(x.e200) }));
    return {
      title: W.brA.dTitle(who(c, SEL)), sub: W.brA.dSub(rows.filter(r => r.a === 1).length, rows.length, rows.filter(r => r.b === 1).length), ctl: SEL_SECTOR(c, SEL, true), onSel: v => brSet(c, v), search: W.search.stock,
      cols: [{ k: 'name', l: W.col.ticker, b: true, term: true }, { k: 'a', l: '> EMA50', html: 'ah' }, { k: 'b', l: '> EMA200', html: 'bh' }, { k: 'd50', l: W.col.vsEma(50), num: true, tone: true, f: v => M.pct(v, 1) }, { k: 'd200', l: W.col.vsEma(200), num: true, tone: true, f: v => M.pct(v, 1) }, { k: 'r1m', l: '1M', num: true, tone: true, f: v => M.pct(v) }],
      rows, sort: ['d50', 1], read: W.brA.read, ex: r => W.brA.ex(r.name, r.d50),
    };
  },
};

/* ===================== Advancers, unchanged and decliners (logic.js L881-892) ===================== */
export const brN: Card = {
  id: 'brN', tab: 'br', cls: 'br-n',
  render(el, c) {
    const D = c.D, S = c.S, H = S.adH as 'r1d' | 'r5d' | 'r1m', HL = W.brN.hz[H];
    const cnt = (g: string) => M.aud(rowsOf(c, g).map(x => x[H]));
    const rows = D.names.map(nm => ({ nm, ...cnt(nm) })).filter(r => r.N > 0).sort((p, q) => q.u / q.N - p.u / p.N), all = { nm: D.market, ...cnt(D.market) };
    const bar = (r: M.Counts) => { const sg = (v: number, bg: string, fg: string) => (v ? `<span style="width:${((100 * v) / r.N).toFixed(2)}%;background:${bg};color:${fg}" title="${esc(W.stocks(v))}">${(100 * v) / r.N >= 7 ? v : ''}</span>` : ''); return `<div class="bx"><div class="stk">${sg(r.u, 'var(--up)', '#fff')}${sg(r.f, 'var(--gray-300)', 'var(--gray-700)')}${sg(r.d, 'var(--down)', '#fff')}</div><i></i></div>` };
    const line2 = (r: any, isAll: boolean) => `<div class="${isAll ? 'all' : ''}${isSel(c, r.nm) ? ' cur' : ''}" data-n="${esc(r.nm)}" role="button" tabindex="0" data-tip="${esc(`<b>${esc(isAll ? W.allShort(D.market) : D.short(r.nm))}</b> · ${HL}<br>${esc(W.brN.tip(r.u, r.f, r.d, r.N))}`)}"><span class="nm">${esc(isAll ? W.allShort(D.market) : D.short(r.nm))}</span>${bar(r)}<b class="val">${r.u}/${r.N}</b></div>`;
    el.innerHTML = H3(W.brN.title, W.brN.sub(HL), SEG('h', W.brN.period, [['r1d', '1D'], ['r5d', '1W'], ['r1m', '1M']], H), c.win ? null : 'brN')
      + `<div class="adr">${line2(all, true)}${rows.map(r => line2(r, false)).join('')}</div>`
      + `<div class="lgd"><span class="adl"><span><i style="background:var(--up)"></i>${esc(W.brN.up)}</span><span><i style="background:var(--gray-300)"></i>${esc(W.brN.flat)}</span><span><i style="background:var(--down)"></i>${esc(W.brN.down)}</span></span><span>${esc(W.brN.half)}</span><span class="sp"></span><span>${esc(M.dateLabel(D.dates[D.E]))}</span></div>`;
    onSeg(el, 'h', v => { S.adH = v; c.redraw() });
    $$('.adr>div[data-n]', el).forEach(r => {
      const go = () => brSet(c, r.dataset.n as string);
      r.onclick = go; r.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go() } };
    });
  },
  detail(c): Detail {
    const D = c.D, H = c.S.adH as 'r1d' | 'r5d' | 'r1m', HL = W.brN.hz[H], SEL = brSel(c);
    const rows = rowsOf(c, SEL).map(x => { const v = x[H], s = v == null ? null : Math.abs(v) < 1e-9 ? 0 : v > 0 ? 1 : -1; return { ...x, name: x.t, st: s, sth: s == null ? '—' : `<span class="tag ${s > 0 ? 'pos' : s < 0 ? 'neg' : 'neu'}">${esc(s > 0 ? W.brN.adv : s < 0 ? W.brN.dec : W.brN.unch)}</span>`, r: v } });
    return {
      title: W.brN.dTitle(who(c, SEL), HL), sub: W.brN.dSub(rows.filter(r => r.st === 1).length, rows.filter(r => r.st === 0).length, rows.filter(r => r.st === -1).length), ctl: SEL_SECTOR(c, SEL, true), onSel: v => brSet(c, v), search: W.search.stock,
      cols: [{ k: 'name', l: W.col.ticker, b: true, term: true }, { k: 'st', l: W.col.status, html: 'sth' }, { k: 'close', l: W.col.close, num: true, f: v => M.level(v, 0) }, { k: 'r', l: W.col.change(HL), num: true, tone: true, f: v => M.pct(v) }, { k: 'vol', l: W.col.volume, num: true, f: v => M.shares(v) }],
      rows, sort: ['r', 1], read: W.brN.read, ex: r => W.brN.ex(r.name, M.level(r.close, 0), r.r, r.st),
    };
  },
};

/* ===================== Stock detail (logic.js L780-803; the real distances, days and dates, G6) ===================== */
const DAYS_CAP = 300;
export const brD: Card = {
  id: 'brD', tab: 'br', cls: 'br-d',
  render(el, c) {
    const D = c.D, S = c.S, SEL = brSel(c), MS = S.bhM, lab = `EMA${MS}`, F = S.bdF, DEF: M.Level = [MS === 200 ? 'd200' : 'd50', 1];
    const SK = M.msKeep(S.bdS, k => ['t', 'ab', 'd50', 'd200', 'dy', 'since'].includes(k));
    let R = rowsOf(c, SEL).map(x => { const ab = MS === 200 ? x.e200 : x.e50; return { ...x, ab, dy: MS === 200 ? x.days200 : x.days50, since: MS === 200 ? x.since200 : x.since50 } });
    const N = R.filter(r => r.ab != null).length, nA = R.filter(r => r.ab === 1).length, Q = c.win ? S.bdQ.trim().toUpperCase() : '';
    if (F !== 'all') R = R.filter(r => (F === 'up' ? r.ab === 1 : r.ab === 0));
    const hit = (r: typeof R[0]) => !Q || r.t.toUpperCase().includes(Q) || String(r.n || '').toUpperCase().includes(Q);
    M.msSort(R, SK, { t: 1, since: 1 }, DEF);
    const LAB = { t: W.col.ticker, ab: W.col.status, d50: 'EMA50', d200: 'EMA200', dy: W.col.days, since: W.col.since };
    const th = (k: string, t: string, cl = '', tip = '') => msTh(SK, k, esc(t), cl, tip, { def: DEF, txt: k === 't' || k === 'since' });
    const dc = (v: M.N) => `<td class="${M.cls(v)}">${M.pct(v, 1)}</td>`, days = (v: M.N) => (v == null ? '—' : v >= DAYS_CAP ? `${DAYS_CAP}+` : String(v));
    const srch = c.win ? `<label class="bdq"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-search"/></svg><input type="search" placeholder="${esc(W.search.stock)}" aria-label="${esc(W.search.stock)}" value="${esc(S.bdQ)}"></label>` : '';
    const shownN = R.filter(hit).length;
    el.innerHTML = H3(W.brD.title, W.brD.sub(who(c, SEL), nA, N, lab), srch + SEG('f', W.brD.status, [['all', W.brD.all], ['up', W.above], ['dn', W.below]], F), c.win ? null : 'brD')
      + `<div class="tbl-wrap" data-scroll="y"><table class="tbl padat"><colgroup><col class="c-t"><col class="c-s"><col class="c-d"><col class="c-d"><col class="c-n"><col class="c-w"></colgroup>`
      + `<thead><tr class="g"><th class="l" colspan="2"></th><th class="grp" colspan="2">${esc(W.brD.dist)}</th><th colspan="2"></th></tr>`
      + `<tr>${th('t', LAB.t, 'l')}${th('ab', LAB.ab, 'l', W.brD.statusTip(lab))}${th('d50', '50', '', W.brD.distTip(50))}${th('d200', '200', '', W.brD.distTip(200))}${th('dy', LAB.dy, '', W.brD.daysTip(lab))}${th('since', LAB.since, '', W.brD.sinceTip(lab))}</tr></thead><tbody>`
      + R.map(r => `<tr data-t="${esc(r.t)}" role="button" tabindex="0"${hit(r) ? '' : ' hidden'} data-tip="${esc(`<b>${esc(r.t)}</b> · ${esc(r.n)}<br>${esc(D.short(r.sec))}<br>${esc(W.brD.tip(r.ab, lab, days(r.dy), r.since ? M.dateLabel(r.since, false, true) : '—'))}<br>${esc(W.brD.dists(M.pct(r.d50, 1), M.pct(r.d200, 1)))}<br><span class="muted">${esc(W.term.rowTip(r.t))}</span>`)}"><td class="l"><b>${esc(r.t)}</b></td><td class="l">${r.ab == null ? '—' : `<span class="tag ${r.ab ? 'pos' : 'neg'}">${esc(r.ab ? W.above : W.below)}</span>`}</td>${dc(r.d50)}${dc(r.d200)}<td>${days(r.dy)}</td><td>${r.since ? esc(M.dateLabel(r.since, false, r.since.slice(0, 4) !== D.dates[D.E].slice(0, 4))) : '—'}</td></tr>`).join('')
      + `<tr class="bdn"${shownN ? ' hidden' : ''}><td class="l" colspan="6">${esc(R.length ? W.search.none(S.bdQ) : W.brD.empty)}</td></tr></tbody></table></div>`
      + `<div class="lgd">${msNote(SK, LAB, { t: 1 })}<span>${esc(W.brD.foot(lab))}</span><span class="sp"></span><span data-cnt>${esc((Q ? W.search.shown(shownN, R.length) + DOT : '') + M.dateLabel(D.dates[D.E]))}</span></div>`;
    onSeg(el, 'f', v => { S.bdF = v; c.redraw() });
    msWire(el, SK, () => c.redraw(), DEF, 'th[data-k]');
    $$('tbody tr[data-t]', el).forEach(r => {
      r.onclick = () => c.terminal(r.dataset.t as string);
      r.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === r) { e.preventDefault(); c.terminal(r.dataset.t as string) } };
    });
    const q = $('.bdq input', el) as HTMLInputElement | null;
    if (q) q.oninput = () => {
      S.bdQ = q.value; const v = q.value.trim().toUpperCase(); let n = 0;
      $$('tbody tr[data-t]', el).forEach(r => { const s = R.find(x => x.t === r.dataset.t); const on = !v || !!s && (s.t.toUpperCase().includes(v) || String(s.n || '').toUpperCase().includes(v)); r.hidden = !on; if (on) n++ });
      const nn = $('tr.bdn', el); nn.hidden = n > 0; nn.firstElementChild!.textContent = W.search.none(q.value);
      $('[data-cnt]', el).textContent = (v ? W.search.shown(n, R.length) + DOT : '') + M.dateLabel(D.dates[D.E]);
    };
  },
};
