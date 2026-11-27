/* EXEC-SECTOR-ANALYSIS S4, the Pair Matrix tab (final/click_inventory.md section 8; formulas.md section 5): the pair
   matrix, the pair ratio, beta and correlation to the benchmark (the stocks' beta from their real closes, G9) and the
   stretched pairs. */
import * as M from '../model.ts';
import { calc, customSpan, type Card, type Ctx, type Detail } from '../ctx.ts';
import { $, $$, DOT, H3, SEG, corrHeat, esc, heat, msNote, msTh, msWire, na, onSeg, tipHide, tipShow, xHide, xShow, xTag } from '../ui.ts';
import { customRange, periodOpts, rangeNote } from './ov.ts';
import { W } from '../words.ts';

const zMemo = new WeakMap<M.Data, [string, string]>();
/** the pair the viewer chose; without one (the page opens so, and a second click on the chosen sector, cell or pair
    returns to it: user decision UD79 1A, visual round 2 V10) the automatic pair, the ordered pair whose ratio is
    furthest from its 60-session mean (logic.js L580). The automatic pair is never written into the state: nothing is
    selected while it shows. */
export interface Pair { a: string; b: string; auto: boolean }
export function pair(c: Ctx): Pair {
  const D = c.D, S = c.S;
  if (S.pmA && S.pmB && S.pmA !== S.pmB && D.names.includes(S.pmA) && D.names.includes(S.pmB)) return { a: S.pmA, b: S.pmB, auto: false };
  let p = zMemo.get(D);
  if (!p) {
    let best: [string, string, number] | null = null;
    D.names.forEach(x => D.names.forEach(y => { if (x !== y) { const z = M.pairZ(D.sec(x), D.sec(y), 60, D.E); if (z != null && (!best || Math.abs(z) > Math.abs(best[2]))) best = [x, y, z] } }));
    p = best ? [best[0], best[1]] : [D.names[0], D.names[1]];
    zMemo.set(D, p);
  }
  return { a: p[0], b: p[1], auto: true };
}
/** whether the viewer chose this pair (a row of pairs: either order; a cell of the matrix: `ordered`) */
const isChosen = (p: Pair, a: string, b: string, ordered = false) => !p.auto && ((p.a === a && p.b === b) || (!ordered && p.a === b && p.b === a));
/** no pair chosen: the cards show the automatic pair again */
export function clearPair(c: Ctx) { c.S.pmA = null; c.S.pmB = null; c.redraw() }
/** choose a pair; the chosen one clicked again clears the choice (`toggle`; the selects and the swap only choose) */
export function setPair(c: Ctx, a: string, b: string, o: { toggle?: boolean; ordered?: boolean } = {}) {
  if (a === b) return;
  if (o.toggle !== false && isChosen(pair(c), a, b, o.ordered)) { clearPair(c); return }
  c.S.pmA = a; c.S.pmB = b; c.redraw();
}
const corrW = (c: Ctx, a: string, b: string, w: number) => M.corr(M.dailyRets(c.D.sec(a), c.D.E - w, c.D.E), M.dailyRets(c.D.sec(b), c.D.E - w, c.D.E));

/* ===================== the pair matrix (logic.js L579-605) ===================== */
export const pmM: Card = {
  id: 'pmM', tab: 'pm', cls: 'pm-m',
  render(el, c) {
    const D = c.D, S = c.S, K = calc(D), P0 = pair(c), A = P0.auto ? null : P0.a, B = P0.auto ? null : P0.b, Md = S.pqM, P = S.pqP, CW = S.pqW, sp = K.span(P, S.pqR, '1M');
    const rs: Record<string, M.N> = {}; D.names.forEach(n => (rs[n] = M.retAt(D.sec(n), sp.b, sp.e)));
    const SR: Record<string, M.N[]> = {}; if (Md === 'co') D.names.forEach(n => (SR[n] = M.dailyRets(D.sec(n), D.E - CW, D.E)));
    const val = (x: string, y: string): M.N => (Md === 'sp' ? M.minus(rs[x], rs[y]) : M.corr(SR[x], SR[y]));
    const avg: Record<string, number> = {};
    if (Md === 'co') D.names.forEach(x => { const v = D.names.filter(y => y !== x).map(y => val(x, y)).filter((z): z is number => z != null); avg[x] = v.length ? v.reduce((a, b) => a + b, 0) / v.length : -Infinity });
    const byRet = Md === 'co' ? (x: string, y: string) => avg[y] - avg[x] : (x: string, y: string) => (rs[y] ?? -Infinity) - (rs[x] ?? -Infinity);
    let ord = [...D.names].sort(byRet);
    const SK = M.msKeep(S.pqS, k => D.names.includes(k));
    if (SK.length) { const R = ord.map(x => { const r: any = { x }; SK.forEach(([cc]) => (r[cc] = x === cc ? null : val(x, cc))); return r }); M.msSort(R, SK); ord = R.map(r => r.x) }
    const cols = [...D.names].sort(byRet), all: number[] = [];
    ord.forEach(x => cols.forEach(y => { if (x !== y) { const v = val(x, y); if (v != null) all.push(Math.abs(v)) } }));
    const cap = Md === 'co' ? 1 : Math.max(...all) || 1, fmt = (v: number) => (Md === 'sp' ? M.ppx(v, 1) : M.fnum(v, 2));
    const style = (v: M.N) => {
      if (v == null) return '';
      return Md === 'co' ? corrHeat(v, 2) : heat(v, cap, 0, 1);               // coloured as printed (fmt; check 2 BD2-4)
    };
    const hz = K.plabel(sp);
    const sub = Md === 'sp' ? W.pmM.subSp(hz) : W.pmM.subCo(CW);
    el.innerHTML = H3(W.pmM.title, sub, SEG('m', '', [['sp', W.pmM.spread], ['co', W.pmM.corr]], Md) + (Md === 'sp' ? SEG('p', '', periodOpts(['5D', '1M', '3M', 'C']).map(([v, l]) => [v, l]), sp.key) : SEG('w', '', [[20, '20D'], [60, '60D'], [120, '120D']], CW)), c.win ? null : 'pmM')
      + `<div class="pmg-s" data-scroll="x" data-sticky="1"><div class="pmg" style="grid-template-columns:88px repeat(${cols.length},minmax(34px,1fr));grid-template-rows:20px repeat(${ord.length},minmax(18px,1fr))"><div></div>`
      + cols.map(y => msTh(SK, y, esc(D.abbr(y)), 'hd', W.pmM.sortBy(y), { tag: 'button' })).join('')
      // the chosen sector A is marked by its name cell, the chosen cell by its outline; nothing is dimmed (UD77, UD79)
      + ord.map(x => `<button type="button" class="nm${x === A ? ' on' : ''}${x === B ? ' nb' : ''}" data-x="${esc(x)}" aria-pressed="${x === A}" title="${esc(x === A ? W.pmM.unA(D.short(x)) : x === B ? W.pmM.isB(D.short(x)) : W.pmM.makeA(D.short(x)))}"${x === B ? ' aria-disabled="true"' : ''}><span>${esc(D.short(x))}</span></button>` + cols.map(y => {
        if (x === y) return '<div class="dg">—</div>';
        const v = val(x, y), sel = x === A && y === B, co = Md === 'co' ? v : corrW(c, x, y, CW);
        return `<button type="button" class="c${sel ? ' sel' : ''}" data-a="${esc(x)}" data-b="${esc(y)}" aria-pressed="${sel}" style="${style(v)}" data-tip="${esc(`<b>${esc(D.short(x))} / ${esc(D.short(y))}</b><br>${Md === 'sp' ? `${esc(W.pmM.spread)} ${esc(hz)} ${M.pp(M.minus(rs[x], rs[y]))}<br>` : ''}${esc(W.pmM.corrW(CW))} ${M.fnum(co)}<br><span class="muted">${esc(sel ? W.pmM.unPair : W.pmM.open)}</span>`)}">${v == null ? '—' : fmt(v)}</button>`;
      }).join('')).join('') + `</div></div>`
      + `<div class="lgd">${msNote(SK, Object.fromEntries(D.names.map(n => [n, D.short(n)])))}<span>${esc(Md === 'sp' ? W.pmM.footSp : W.pmM.footCo)}</span>${Md === 'sp' ? rangeNote(sp.note) : ''}<span class="sp"></span><span>${esc(Md === 'sp' ? M.rangeLabel(D.dates[sp.b], D.dates[sp.e], D.ref) : M.rangeLabel(D.dates[D.E - CW], D.dates[D.E], D.ref))}</span></div>`;
    onSeg(el, 'm', v => { S.pqM = v; c.redraw() });
    onSeg(el, 'p', (v, btn) => { if (v === 'C') { customRange(c, btn, S.pqR, r => { S.pqP = 'C'; S.pqR = r }); return } S.pqP = v; c.redraw() });
    onSeg(el, 'w', v => { S.pqW = +v; c.redraw() });
    $$('.pmg .c', el).forEach(b => (b.onclick = () => setPair(c, b.dataset.a as string, b.dataset.b as string, { ordered: true })));
    // a name makes its sector A of the pair (B stays, or the automatic pair's B); the chosen A again: no pair chosen
    $$('.pmg .nm', el).forEach(b => (b.onclick = () => {
      const x = b.dataset.x as string;
      if (x === A) clearPair(c); else if (x !== B) setPair(c, x, x === P0.b ? P0.a : P0.b, { toggle: false });
    }));
    msWire(el, SK, () => c.redraw(), null, '.hd[data-k]');
  },
  detail(c): Detail {
    const D = c.D, K = calc(D), sp = K.span(c.S.pqP, c.S.pqR, '1M'), rows: any[] = [], P0 = pair(c);
    D.names.forEach((a, i) => D.names.forEach((b, j) => {
      if (j <= i) return;
      const ra = M.retAt(D.sec(a), sp.b, sp.e), rb = M.retAt(D.sec(b), sp.b, sp.e), s = M.minus(ra, rb), x = (s ?? 0) >= 0 ? [a, b, ra, rb] : [b, a, rb, ra];
      rows.push({ name: `${D.short(x[0] as string)} / ${D.short(x[1] as string)}`, pa: x[0], pb: x[1], s: s == null ? null : Math.abs(s), ra: x[2], rb: x[3], c: corrW(c, a, b, 60) });
    }));
    return {
      title: W.pmM.dTitle(rows.length), sub: `${K.plabel(sp)}${DOT}${W.pmM.leaderFirst}`, search: W.search.pair,
      cols: [{ k: 'name', l: W.col.pair }, { k: 's', l: W.pmM.spread, num: true, tone: true, f: v => M.pp(v) }, { k: 'ra', l: W.col.aheadRet, num: true, tone: true, f: v => M.pct(v, 1) }, { k: 'rb', l: W.col.behindRet, num: true, tone: true, f: v => M.pct(v, 1) }, { k: 'c', l: W.pmM.corrW(60), num: true, f: v => M.fnum(v) }],
      rows, sort: ['s', 1], onRow: r => setPair(c, r.pa, r.pb), isSel: r => isChosen(P0, r.pa, r.pb),
      read: W.pmM.read, ex: r => W.pmM.ex(D.short(r.pa), r.ra, D.short(r.pb), r.rb, r.s, r.c),
    };
  },
};

/* ===================== the pair ratio (logic.js L608-645) ===================== */
function ratioSpan(c: Ctx) {
  const D = c.D, S = c.S, MA = S.prMA, sp = calc(D).span(S.prP, S.prR, '6M');
  const b = Math.max(MA, sp.b);
  return { i0: b, i1: sp.e, moved: b > sp.b ? D.dates[b] : null, custom: sp.custom, key: sp.key, note: sp.note };
}
export const pmR: Card = {
  id: 'pmR', tab: 'pm', cls: 'pm-r',
  render(el, c) {
    const D = c.D, S = c.S, P0 = pair(c), a = P0.a, b = P0.b, MA = S.prMA, { i0, i1, moved, custom, key, note } = ratioSpan(c), band = M.ratioBand(D.sec(a), D.sec(b), i0, i1, MA);
    const { v, m, up, dn } = band, nL = v.length - 1, spr = M.minus(M.retAt(D.sec(a), i0, i1), M.retAt(D.sec(b), i0, i1));
    const last = v[nL], pos = last == null || up[nL] == null || dn[nL] == null ? null : last > (up[nL] as number) ? 'up' : last < (dn[nL] as number) ? 'dn' : 'in';
    const pb = pos === 'in' ? (((last as number) - (dn[nL] as number)) / (((up[nL] as number) - (dn[nL] as number)) || 1)) * 100 : null;
    const opt = (x: string, other: string) => D.names.map(n => `<option value="${esc(n)}"${n === x ? ' selected' : ''}>${esc(D.short(n))}${n === other ? ' ⇄' : ''}</option>`).join('');
    const pl = custom ? W.pmR.period : key;
    el.innerHTML = H3(`${D.short(a)} / ${D.short(b)}`, P0.auto ? W.pmR.subAuto : W.pmR.sub, SEG('p', '', periodOpts(['3M', '6M', '1Y', 'C']), key), c.win ? null : 'pmR')
      + `<div class="pmbar">${P0.auto ? `<span class="tg pmauto" data-tip="${esc(esc(W.pmR.autoTip))}" tabindex="0" aria-label="${esc(W.pmR.auto + ': ' + W.pmR.autoTip)}">${esc(W.pmR.auto)}</span>` : ''}<span class="sxw"><select class="sx-sel" data-ab="a" aria-label="${esc(W.pmR.a)}">${opt(a, b)}</select></span><button class="sw" type="button" data-swap title="${esc(W.pmR.swap)}" aria-label="${esc(W.pmR.swap)}">⇄</button><span class="sxw"><select class="sx-sel" data-ab="b" aria-label="${esc(W.pmR.b)}">${opt(b, a)}</select></span><span class="sp"></span>${SEG('ma', 'MA', [[20, '20'], [50, '50']], MA)}</div>`
      + `<div class="pmk one"><div><span>${esc(W.pmR.spreadK(pl))}</span><b class="${M.cls(spr, 1)}">${M.pp(spr, 1)}</b></div><div class="bst ${pos || ''}"><span>${esc(W.pmR.band)}</span><b>${esc(pos == null ? '—' : W.pmR.pos(pos, pb))}</b></div></div>`
      + `<div class="pmc" data-chart></div><div class="lgd"><span class="sw"><i style="background:var(--navy)"></i>${esc(W.pmR.lineA)}</span><span class="sw"><i style="background:var(--text-3)"></i>MA${MA}</span><span class="sw"><i style="background:color-mix(in srgb,var(--navy) 15%,transparent);height:8px"></i>${esc(W.pmR.bandL)}</span>${moved ? `<span class="warnx">${esc(W.pmR.moved(M.dateLabel(moved, false, true), MA))}</span>` : ''}${rangeNote(note)}<span class="sp"></span><span>${esc(M.rangeLabel(D.dates[i0], D.dates[i1], D.ref))}</span></div>`;
    onSeg(el, 'p', (x, btn) => { if (x === 'C') { customRange(c, btn, S.prR, r => { S.prP = 'C'; S.prR = r }); return } S.prP = x; c.redraw() });
    onSeg(el, 'ma', x => { S.prMA = +x; c.redraw() });
    ($('[data-ab=a]', el) as HTMLSelectElement).onchange = e => { const n = (e.target as HTMLSelectElement).value; n === b ? setPair(c, n, a, { toggle: false }) : setPair(c, n, b, { toggle: false }) };
    ($('[data-ab=b]', el) as HTMLSelectElement).onchange = e => { const n = (e.target as HTMLSelectElement).value; n === a ? setPair(c, b, n, { toggle: false }) : setPair(c, a, n, { toggle: false }) };
    ($('[data-swap]', el) as HTMLElement).onclick = () => setPair(c, b, a, { toggle: false });
    const box = $('[data-chart]', el);
    requestAnimationFrame(() => {
      const Wd = box.clientWidth - 32, H = box.clientHeight; if (Wd <= 0 || !H) return;
      const allv = [...v, ...m, ...up, ...dn].filter((x): x is number => x != null);
      if (!allv.length) { box.innerHTML = `<div class="cv-empty">${esc(W.pmR.none)}</div>`; return }
      const lo = Math.min(...allv), hi = Math.max(...allv), pd = (hi - lo) * 0.08 || 1, tk = M.ticks(lo - pd, hi + pd, 4), y0 = Math.min(lo - pd, tk[0]), y1 = Math.max(hi + pd, tk[tk.length - 1]);
      const L = 36, R = Wd - 4, T = 6, B = H - 18, n = v.length, X = (i: number) => L + (i / (n - 1)) * (R - L), Y = (x: number) => T + ((y1 - x) / (y1 - y0)) * (B - T);
      const pth = (arr: M.N[]) => { let s = '', pen = false; arr.forEach((x, i) => { if (x == null) { pen = false; return } s += (pen ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(x).toFixed(1); pen = true }); return s };
      const ok = up.map((x, i) => (x != null && dn[i] != null ? i : -1)).filter(i => i >= 0);
      const picks = [0, Math.round((n - 1) / 2), n - 1], labs = M.axisDates(D.dates.slice(i0, i1 + 1), picks);
      let o = tk.map(t => `<line x1="${L}" x2="${R}" y1="${Y(t)}" y2="${Y(t)}" stroke="${t === 100 ? 'var(--chart-base)' : 'var(--chart-grid)'}"/><text class="ax" x="${L - 6}" y="${Y(t) + 3.5}" text-anchor="end">${t}</text>`).join('')
        + picks.map((i, k) => `<text class="ax" x="${X(i)}" y="${H - 3}" text-anchor="${k === 0 ? 'start' : k === 2 ? 'end' : 'middle'}">${esc(labs[k])}</text>`).join('')
        + (ok.length > 1 ? `<path d="${ok.map((i, k) => (k ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(up[i] as number).toFixed(1)).join('')}L${[...ok].reverse().map(i => X(i).toFixed(1) + ' ' + Y(dn[i] as number).toFixed(1)).join('L')}Z" fill="color-mix(in srgb,var(--navy) 8%,transparent)"/>` : '')
        + `<path d="${pth(up)}" fill="none" stroke="color-mix(in srgb,var(--navy) 35%,transparent)" stroke-width="1"/><path d="${pth(dn)}" fill="none" stroke="color-mix(in srgb,var(--navy) 35%,transparent)" stroke-width="1"/>`
        + `<path d="${pth(m)}" fill="none" stroke="var(--text-3)" stroke-width="1.2" stroke-dasharray="4 3"/><path d="${pth(v)}" fill="none" stroke="var(--navy)" stroke-width="1.8" stroke-linejoin="round"/>`
        + v.map((x, i) => (x == null || up[i] == null ? '' : x > (up[i] as number) ? `<circle cx="${X(i).toFixed(1)}" cy="${Y(x).toFixed(1)}" r="2.2" fill="var(--up)"/>` : x < (dn[i] as number) ? `<circle cx="${X(i).toFixed(1)}" cy="${Y(x).toFixed(1)}" r="2.2" fill="var(--down)"/>` : '')).join('');
      const mk = S.prMk ? D.dates.indexOf(S.prMk) : -1;
      if (mk >= i0 && mk <= i1 && v[mk - i0] != null) {
        const k = mk - i0, x = X(k), y = Y(v[k] as number), lb = M.dateIn(D.dates[mk], D.ref), tw = lb.length * 6.4 + 12, lx = Math.max(L, Math.min(R - tw, x - tw / 2));
        o += `<line x1="${x}" x2="${x}" y1="${T}" y2="${B}" stroke="var(--text)"/><line x1="${L}" x2="${R}" y1="${y}" y2="${y}" stroke="var(--text)" stroke-dasharray="3 3"/><circle cx="${x}" cy="${y}" r="4.5" fill="var(--navy)" stroke="var(--surface)" stroke-width="1.5"/><g class="xtg"><rect x="${lx}" y="${T}" width="${tw}" height="17" rx="3"/><text x="${lx + tw / 2}" y="${T + 12}" text-anchor="middle">${esc(lb)}</text></g><text class="ax" x="${R}" y="${y - 5}" text-anchor="end" style="fill:var(--text);font-weight:600">${(v[k] as number).toFixed(1)}</text>`;
      }
      if (last != null) o += `<circle cx="${X(n - 1)}" cy="${Y(last)}" r="3" fill="var(--navy)"/>`;
      o += `<line class="hv" y1="${T}" y2="${B}" stroke="var(--text-3)" stroke-dasharray="2 3" display="none"/><circle class="hd" r="4" fill="var(--navy)" stroke="var(--surface)" stroke-width="1.5" display="none"/>`;
      box.innerHTML = `<svg width="${Wd}" height="${H}" role="img" aria-label="${esc(W.pmR.aria(D.short(a), D.short(b)))}">${o}</svg>`;
      box.dataset.ownTip = '';
      const vx = $('line.hv', box) as unknown as SVGLineElement, vd = $('circle.hd', box);
      box.onpointermove = box.onpointerdown = e => {
        const r = box.getBoundingClientRect(), mx = e.clientX - r.left - 16;
        if (mx < L || mx > R) { xHide(vx); vd.setAttribute('display', 'none'); tipHide(); return }
        const i = Math.round(((mx - L) / (R - L)) * (n - 1)); if (v[i] == null) return;
        xShow(vx, X(i)); xTag(vx, M.tagDate(D.dates[i0 + i])); vd.setAttribute('cx', String(X(i))); vd.setAttribute('cy', String(Y(v[i] as number))); vd.removeAttribute('display');
        const ra = M.retAt(D.sec(a), i0, i0 + i), rb = M.retAt(D.sec(b), i0, i0 + i), up2 = up[i], dn2 = dn[i];
        tipShow(`<span class="d">${esc(M.dateLabel(D.dates[i0 + i], true, true))}</span><div class="r"><span>${esc(W.pmR.ratio)}</span><b>${(v[i] as number).toFixed(1)}</b></div><div class="r"><span>MA${MA}</span><b>${m[i] == null ? '—' : (m[i] as number).toFixed(1)}</b></div><div class="r"><span>${esc(W.pmR.band)}</span><b>${up2 == null || dn2 == null ? '—' : `${dn2.toFixed(1)} – ${up2.toFixed(1)}`}</b></div><div class="r"><span>${esc(D.short(a))}</span><b class="${M.cls(ra, 1)}">${M.pct(ra, 1)}</b></div><div class="r"><span>${esc(D.short(b))}</span><b class="${M.cls(rb, 1)}">${M.pct(rb, 1)}</b></div>`, e);
      };
      box.onpointerleave = () => { xHide(vx); vd.setAttribute('display', 'none'); tipHide() };
    });
  },
  detail(c): Detail {
    const D = c.D, { a, b } = pair(c), MA = c.S.prMA, { i0, i1 } = ratioSpan(c), band = M.ratioBand(D.sec(a), D.sec(b), i0, i1, MA), rows: any[] = [];
    for (let i = i1; i > Math.max(i0, i1 - 60); i--) {
      const k = i - i0, r1 = M.retAt(D.sec(a), i - 1, i), r2 = M.retAt(D.sec(b), i - 1, i), mu = band.m[k], q = band.v[k];
      rows.push({ i, name: M.dateLabel(D.dates[i], false, true), ra: r1, rb: r2, sp: M.minus(r1, r2), cum: M.minus(M.retAt(D.sec(a), i0, i), M.retAt(D.sec(b), i0, i)), vm: mu != null && q != null ? (q / mu - 1) * 100 : null, z: band.z[k] });
    }
    return {
      title: W.pmR.dTitle(D.short(a), D.short(b)), sub: W.pmR.dSub(rows.length, MA),
      cols: [{ k: 'i', l: W.col.date, num: true, f: (_v, r) => r.name }, { k: 'ra', l: D.short(a), num: true, tone: true, f: v => M.pct(v) }, { k: 'rb', l: D.short(b), num: true, tone: true, f: v => M.pct(v) },
             { k: 'sp', l: W.pmM.spread, num: true, tone: true, f: v => M.pp(v) }, { k: 'cum', l: W.col.cumSpread, num: true, tone: true, f: v => M.pp(v, 1) }, { k: 'vm', l: `vs MA${MA}`, num: true, tone: true, f: v => M.pct(v) }, { k: 'z', l: W.col.bandSd, num: true, tone: true, f: v => M.fnum(v) }],
      rows, sort: ['i', 1], onRow: r => { c.S.prMk = c.S.prMk === D.dates[r.i] ? null : D.dates[r.i]; c.redraw() }, isSel: r => D.dates[r.i] === c.S.prMk,
      read: W.pmR.read, ex: r => W.pmR.ex(r.name, D.short(a), r.ra, D.short(b), r.rb, r.sp, r.z),
    };
  },
};

/* ===================== beta and correlation to the benchmark (logic.js L648-669) ===================== */
const BETA_W: [string, string][] = [['20', '20D'], ['60', '60D'], ['120', '120D'], ['252', '1Y'], ['C', 'Custom']];
function betaSpan(c: Ctx): { j0: number; j1: number; label: string; key: string; note: string | null } {
  const D = c.D, S = c.S;
  let note: string | null = null;
  if (S.btW === 'C' && S.btR) {
    const r = customSpan(D, S.btR, '120D'); note = r.note;
    if (r.s) return { j0: r.s.base, j1: r.s.last, label: `${r.s.n}D`, key: 'C', note };
  }
  const k = S.btW === 'C' ? '120' : S.btW, w = Math.min(+k, D.E);
  return { j0: D.E - w, j1: D.E, label: (BETA_W.find(x => x[0] === k) || ['', `${w}D`])[1], key: k, note };
}
const benchOf = (c: Ctx) => (c.D.series.index[c.S.btB] ? c.S.btB : c.D.market);
export const pmT: Card = {
  id: 'pmT', tab: 'pm', cls: 'pm-t', stack: true, align: true,
  render(el, c) {
    const D = c.D, S = c.S, P0 = pair(c), A = P0.auto ? null : P0.a, B = P0.auto ? null : P0.b, { j0, j1, label, key, note } = betaSpan(c), W0 = j1 - j0, BM = benchOf(c), bx = D.series.index[BM], br = M.dailyRets(bx, j0, j1), bret = M.retAt(bx, j0, j1);
    const rows = D.names.map(nm => {
      const a = D.sec(nm), r = M.dailyRets(a, j0, j1), be = M.beta(r, br), rt = M.retAt(a, j0, j1);
      let db: M.N = null;
      if (j0 - W0 >= 1 && be != null) { const bp = M.beta(M.dailyRets(a, j0 - W0, j0), M.dailyRets(bx, j0 - W0, j0)); db = bp == null ? null : be - bp }
      return { nm, n: D.short(nm), b: be, c: M.corr(r, br), rt, ex: M.minus(rt, bret), al: rt != null && be != null && bret != null ? rt - be * bret : null, db };
    });
    const SK = M.msKeep(S.btS, k => ['n', 'b', 'db', 'c', 'rt', 'ex', 'al'].includes(k)), DEF: M.Level = ['b', 1];
    M.msSort(rows, SK, { n: 1 }, DEF);
    const mxb = Math.max(1.6, ...rows.map(r => r.b ?? 0)), th = (k: string, l: string, cl = '', t = '') => msTh(SK, k, esc(l), cl, t, { def: DEF, txt: k === 'n' });
    const LAB = { n: W.col.sector, b: W.pmT.beta, db: W.pmT.dBeta, c: W.pmT.corr, rt: W.col.ret, ex: W.vs(BM), al: W.pmT.alpha };
    const benches = (D.meta.benchmarks?.length ? D.meta.benchmarks : [D.market]).filter(x => D.series.index[x]);
    el.innerHTML = H3(W.pmT.title(BM), W.pmT.sub(BM, label), SEG('w', W.pmT.window, BETA_W.map(([v, l]) => [v, v === 'C' ? W.range.custom : l] as [string, string]), key) + (benches.length > 1 ? SEG('b', W.pmT.vs, benches.map(x => [x, x] as [string, string]), BM) : ''), c.win ? null : 'pmT')
      + `<div class="tbl-wrap" data-scroll="y" data-sticky="1"><table class="tbl padat"><thead><tr>${th('n', LAB.n, 'l')}${th('b', `${W.pmT.beta} ${label}`)}<th class="l bcol"></th>${th('db', LAB.db, '', W.pmT.dBetaTip)}${th('c', LAB.c)}${th('rt', LAB.rt, '', W.pmT.retTip)}${th('ex', LAB.ex, '', W.pmT.exTip(BM))}${th('al', LAB.al, '', W.pmT.alTip(BM))}</tr></thead><tbody>`
      + rows.map(r => `<tr class="${r.nm === A || r.nm === B ? 'on' : ''}" data-n="${esc(r.nm)}" role="button" tabindex="0" aria-pressed="${r.nm === A}" title="${esc(r.nm === A ? W.pmT.rowUnTip(r.n) : W.pmT.rowTip(r.n))}"><td class="l"><b>${esc(r.n)}</b>${r.nm === A ? '<span class="pab">A</span>' : r.nm === B ? '<span class="pab">B</span>' : ''}</td><td><b>${M.fnum(r.b)}</b></td><td class="l bcol"><div class="bbar"><b style="width:${Math.min(100, ((r.b ?? 0) / mxb) * 100).toFixed(1)}%;background:${(r.b ?? 0) >= 1 ? 'var(--navy)' : 'var(--gray-400)'}"></b><i style="left:${(100 / mxb).toFixed(1)}%"></i></div></td><td class="${r.db == null ? '' : r.db > 0.05 ? 'down' : r.db < -0.05 ? 'up' : ''}">${r.db == null ? na(W.pmT.dBetaNa(label)) : M.ppx(r.db, 2)}</td><td>${M.fnum(r.c)}</td><td class="${M.cls(r.rt, 1)}">${M.pct(r.rt, 1)}</td><td class="${M.cls(r.ex, 1)}">${M.pp(r.ex, 1)}</td><td class="${M.cls(r.al, 1)}">${M.pp(r.al, 1)}</td></tr>`).join('')
      + `</tbody></table></div><div class="lgd">${msNote(SK, LAB, { n: 1 })}<span>${esc(W.pmT.foot(BM, M.pct(bret, 1)))}</span>${rangeNote(note)}<span class="sp"></span><span>${esc(M.rangeLabel(D.dates[j0], D.dates[j1], D.ref))}</span></div>`;
    onSeg(el, 'w', (v, btn) => { if (v === 'C') { customRange(c, btn, S.btR, r => { S.btW = 'C'; S.btR = r }, { min: 10 }); return } S.btW = v; c.redraw() });
    onSeg(el, 'b', v => { S.btB = v; c.redraw() });
    msWire(el, SK, () => c.redraw(), DEF, 'th[data-k]');
    $$('tbody tr', el).forEach(r => {
      const go = () => {
        const n = r.dataset.n as string;
        // the chosen A again: no pair chosen and its lock ended (UD79); another row: A, the pair's B kept
        if (n === A) { if (S.pin === n) S.pin = null; clearPair(c); return }
        S.pmA = n; S.pmB = n === P0.b ? P0.a : P0.b; S.pin = n; c.redraw();
      };
      r.onclick = go; r.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === r) { e.preventDefault(); go() } };
    });
  },
  detail(c): Detail {
    const D = c.D, P0 = pair(c), A = P0.a, { j0, j1, label } = betaSpan(c), BM = benchOf(c), bx = D.series.index[BM], br = M.dailyRets(bx, j0, j1), mo = D.P('1M'), b1 = M.ret(bx, D.E, mo);
    const sb = M.beta(M.dailyRets(D.sec(A), j0, j1), br), st = c.stocks(A);
    let note = '';
    const at = st.state === 'ready' ? new Map(st.file.dates.map((d, i) => [d, i] as [string, number])) : null, col = st.state === 'ready' ? new Map(st.file.ticker.map((t, i) => [t, i] as [string, number])) : null;
    if (st.state !== 'ready') note = st.state === 'loading' ? W.pmT.loading : W.pmT.missing;
    // the stocks' beta and correlation from their own closes on the window's sessions (G9: real, not seeded)
    const rows = D.members(A).map(x => {
      let b: M.N = null, cr: M.N = null;
      if (at && col && st.state === 'ready' && col.has(x.t)) {
        const k = col.get(x.t) as number, cl = D.dates.map(d => { const i = at.get(d); return i == null ? null : st.file.close[k][i] ?? null }), rs = M.dailyRets(cl, j0, j1);
        b = M.beta(rs, br); cr = M.corr(rs, br);
      }
      return { ...x, name: x.t, b, c: cr, x1m: M.minus(x.r1m, b1) };
    });
    return {
      title: W.pmT.dTitle(D.short(A)), sub: W.pmT.dSub(label, BM, M.fnum(sb)) + (P0.auto ? DOT + W.pmT.autoA : ''), search: W.search.stock, note,
      cols: [{ k: 'name', l: W.col.ticker, b: true, term: true }, { k: 'ind', l: W.col.industry }, { k: 'b', l: W.pmT.beta, num: true, f: v => M.fnum(v) }, { k: 'c', l: W.pmT.corr, num: true, f: v => M.fnum(v) },
             { k: 'r1m', l: '1M', num: true, tone: true, f: v => M.pct(v) }, { k: 'x1m', l: `1M ${W.vs(BM)}`, num: true, tone: true, f: v => M.pp(v) }, { k: 'w', l: W.col.weight, num: true, f: v => M.weightText(D.weightBasis, v), tip: D.weightLabel }],
      rows, sort: ['b', 1], read: W.pmT.read, ex: r => W.pmT.ex(r.name, r.b, r.c),
    };
  },
};

/* ===================== stretched pairs (logic.js L672-690); a pair reads leader first over 1M (defect D19) ===================== */
const RANK_H = (D: M.Data): Record<string, number> => ({ '3D': 3, '1W': D.P('1W'), '1M': D.P('1M') });
/** every pair, its 1M leader first, with its spread over each horizon (pp) and the card's ranking and filter: ranked by
    the |spread| over the "Rank by" horizon; "Leader still ahead" / "Leader behind" keep the pairs whose spread over that
    horizon is above / below 0 (all pairs when ranked by 1M, where every leader is ahead by its definition) */
function stretched(c: Ctx, hz: [number, string][]) {
  const D = c.D, S = c.S, K = calc(D), mo = D.P('1M'), RK = RANK_H(D)[S.stH] ? S.stH : '1M', F = RK === '1M' ? 'all' : S.stF;
  let rows: any[] = [];
  D.names.forEach((x, i) => D.names.forEach((y, j) => {
    if (j <= i) return;
    const m = M.minus(K.rr(x, mo), K.rr(y, mo)), [a, b] = (m ?? 0) >= 0 ? [x, y] : [y, x], o: any = { a, b, n: `${D.short(a)} / ${D.short(b)}` };
    hz.forEach(([n, l]) => (o['s' + l] = M.minus(K.rr(a, n), K.rr(b, n))));
    const sh = M.minus(K.rr(a, RANK_H(D)[RK]), K.rr(b, RANK_H(D)[RK]));
    o.sh = sh; o.ak = sh == null ? null : Math.abs(sh);
    rows.push(o);
  }));
  const all = rows.length;
  if (F === 'up') rows = rows.filter(r => (r.sh ?? 0) > 0);
  if (F === 'dn') rows = rows.filter(r => (r.sh ?? 0) < 0);
  return { rows, all, RK, F };
}
export const pmS: Card = {
  id: 'pmS', tab: 'pm', cls: 'pm-s', stack: true,
  render(el, c) {
    const D = c.D, S = c.S, P0 = pair(c), N = S.stN;
    const { rows: R, RK, F } = stretched(c, [[3, '3D'], [D.P('1W'), '1W'], [D.P('1M'), '1M']]);
    let rows = R;
    const SK = M.msKeep(S.stS, k => ['n', 'ak', 's3D', 's1W', 's1M'].includes(k)), DEF: M.Level = ['ak', 1];
    M.msSort(rows, SK, { n: 1 }, DEF);
    const tot = rows.length; rows = N === 'all' ? rows : rows.slice(0, +N);
    const LAB = { n: W.col.pair, ak: W.pmS.abs(RK), s3D: W.pmS.sp('3D'), s1W: W.pmS.sp('1W'), s1M: W.pmS.sp('1M') };
    const th = (k: string, l: string, cl = '') => msTh(SK, k, esc(l), cl, '', { def: DEF, txt: k === 'n' }), td = (v: M.N, k: string) => `<td class="${M.cls(v, 1)}${k === 's' + RK ? ' hz' : ''}">${M.pp(v, 1)}</td>`;
    const ctl = H3(W.pmS.title, W.pmS.sub(RK), SEG('h', W.pmS.rank, [['3D', '3D'], ['1W', '1W'], ['1M', '1M']], RK), c.win ? null : 'pmS')
      + `<div class="pmbar">${SEG('f', '', [['all', W.pmS.all], ['up', W.pmS.still], ['dn', W.pmS.turning]], F, RK === '1M' ? { up: W.pmS.disabled, dn: W.pmS.disabled } : {})}<span class="sp"></span>${SEG('n', W.pmS.show, [['7', W.pmS.top(7)], ['all', W.pmS.allRows]], N)}</div>`;
    // the window shows only "Spread across horizons": the card's controls rank, filter and limit it (user 2026-11-27, V7)
    el.classList.toggle('ctlo', c.win);
    el.innerHTML = c.win ? ctl : ctl
      + `<div class="tbl-wrap" data-scroll="y"><table class="tbl padat"><thead><tr>${th('n', LAB.n, 'l')}${th('s3D', LAB.s3D)}${th('s1W', LAB.s1W)}${th('s1M', LAB.s1M)}</tr></thead><tbody>`
      + rows.map(r => { const on = isChosen(P0, r.a, r.b); return `<tr class="${on ? 'on' : ''}" data-a="${esc(r.a)}" data-b="${esc(r.b)}" role="button" tabindex="0" aria-pressed="${on}" title="${esc(on ? W.pmS.rowUnTip : W.pmS.rowTip)}"><td class="l"><b>${esc(r.n)}</b></td>${td(r.s3D, 's3D')}${td(r.s1W, 's1W')}${td(r.s1M, 's1M')}</tr>` }).join('')
      + `</tbody></table></div><div class="lgd">${msNote(SK, LAB, { n: 1 }, W.pmS.defOrder(RK))}<span>${esc(W.pmS.foot(N === 'all' ? null : Math.min(+N, tot), tot))}</span><span class="sp"></span><span>${esc(M.dateIn(D.dates[D.E], D.ref))}</span></div>`;
    // a new ranking horizon ranks the window's table too (its own column sort set back)
    onSeg(el, 'h', v => { S.stH = v; S.stS = []; if (c.win) S.dS = []; c.redraw() });
    onSeg(el, 'f', v => { S.stF = v; c.redraw() });
    onSeg(el, 'n', v => { S.stN = v; c.redraw() });
    if (c.win) return;
    msWire(el, SK, () => c.redraw(), DEF, 'th[data-k]');
    $$('tbody tr', el).forEach(r => {
      const go = () => setPair(c, r.dataset.a as string, r.dataset.b as string);
      r.onclick = go; r.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === r) { e.preventDefault(); go() } };
    });
  },
  /** Spread across horizons: every horizon of each pair, ranked, filtered and limited by the card's controls above it */
  detail(c): Detail {
    const D = c.D, S = c.S, P0 = pair(c), H: [number, string][] = [[1, '1D'], [3, '3D'], [D.P('1W'), '1W'], [D.P('2W'), '2W'], [D.P('1M'), '1M'], [D.P('3M'), '3M']];
    const { rows, all, RK, F } = stretched(c, H), N = S.stN === 'all' ? null : +S.stN;
    rows.forEach(r => { r.name = r.n; r.pa = r.a; r.pb = r.b });
    return {
      title: W.pmS.dTitle, sub: W.pmS.dSubWin(N == null ? rows.length : Math.min(N, rows.length), rows.length, all, RK, F !== 'all'), search: W.search.pair,
      cols: [{ k: 'name', l: W.col.pair }, ...H.map(([, l]) => ({ k: 's' + l, l: W.pmS.sp(l), num: true, tone: true, hl: l === RK, f: (v: number) => M.pp(v, 1) }))],
      rows, sort: ['ak', 1], limit: N ?? undefined, limitNone: q => W.pmS.noneTop(q, N as number),
      onRow: r => setPair(c, r.pa, r.pb), isSel: r => isChosen(P0, r.pa, r.pb),
      read: W.pmS.read, ex: r => W.pmS.ex(D.short(r.pa), D.short(r.pb), r.s1M, r.s1D),
    };
  },
};
