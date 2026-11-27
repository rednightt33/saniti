/* EXEC-SECTOR-ANALYSIS S4, the Relative Strength tab (final/click_inventory.md section 6; formulas.md section 3): Sector
   Drill-down with its industries, Rank change, a sector's stock lines, Weekly Excess Return and Relative Return. */
import * as M from '../model.ts';
import { calc, customSpan, shown, type Card, type Ctx, type Detail } from '../ctx.ts';
import { cumChart, cumHover, type Geo, type Line } from '../charts.ts';
import { $, $$, DOT, H3, SEG, esc, heat, msNote, msTh, msWire, na, onSeg, openRange } from '../ui.ts';
import { customRange, periodOpts, rangeNote, SEL_SECTOR } from './ov.ts';
import { W } from '../words.ts';

const QBG: Record<M.Quad, string> = { Leading: 'var(--green-bg)', Weakening: 'var(--amber-bg)', Lagging: 'var(--red-bg)', Improving: 'var(--blue-bg)' };
const QFG: Record<M.Quad, string> = { Leading: 'var(--green)', Weakening: 'var(--amber)', Lagging: 'var(--red)', Improving: 'var(--blue)' };
export const quadTag = (q: M.Quad | null) => (q ? `<span class="tg" style="background:${QBG[q]};color:${QFG[q]}">${esc(W.quad[q])}</span>` : '—');
const stockCols = (c: Ctx) => ({
  t: { k: 'name', l: W.col.ticker, b: true, term: true },
  ind: { k: 'ind', l: W.col.industry },
  w: { k: 'w', l: W.col.weight, num: true, f: (v: number) => M.weightText(c.D.weightBasis, v), tip: c.D.weightLabel },
});

/* ===================== Relative Return (logic.js L188-198) ===================== */
export const rsA: Card = {
  id: 'rsA', tab: 'rs', cls: 'rs-a',
  render(el, c) {
    const D = c.D, S = c.S, K = calc(D), n = S.rsN, rel = S.rsB === 'rel';
    const rows = D.names.map(nm => ({ nm, v: rel ? K.rr(nm, n) : M.ret(D.sec(nm), D.E, n) })).filter(r => r.v != null).sort((a, b) => (b.v as number) - (a.v as number)) as { nm: string; v: number }[];
    const ih = M.ret(D.IH, D.E, n), mx = Math.max(...rows.map(r => Math.abs(r.v)), rel || ih == null ? 0 : Math.abs(ih)) * 1.1 || 1, X = (v: number) => 50 + (v / mx) * 50;
    el.innerHTML = H3(W.rsA.title, W.rsA.sub(rel, n, D.market), SEG('n', W.rsA.window, [[3, '3D'], [5, '5D'], [10, '10D']], n) + SEG('b', '', [['rel', W.vs(D.market)], ['abs', W.rsA.abs]], S.rsB), c.win ? null : 'rsA')
      + `<div class="tb"><div class="dvb">` + rows.map((r, k) => `<div class="r${r.nm === S.pin ? ' pk' : ''}" data-n="${esc(r.nm)}" role="button" tabindex="0" aria-pressed="${r.nm === S.pin}" data-tip="${esc(`<b>${esc(r.nm)}</b> · ${n}D<br>${rel ? `${esc(W.rsA.sector)} ${M.pct(M.ret(D.sec(r.nm), D.E, n))} · ${esc(D.market)} ${M.pct(ih)}<br>${esc(W.rsA.excess)} ${M.pp(r.v)}` : `${esc(W.col.ret)} ${M.pct(r.v)} · ${esc(D.market)} ${M.pct(ih)}`}<br>${esc(W.rsA.rank(k + 1, rows.length))}`)}"><span>${esc(D.short(r.nm))}</span><div class="tr"><span class="z" style="left:50%"></span><span class="bar ${r.v >= 0 ? 'pos' : 'neg'}" style="left:${Math.min(50, X(r.v)).toFixed(2)}%;width:${Math.abs(X(r.v) - 50).toFixed(2)}%"></span>${rel || ih == null ? '' : `<span class="bm" style="left:${X(ih).toFixed(2)}%"></span>`}</div><b class="${M.cls(r.v)}">${rel ? M.pp(r.v) : M.pct(r.v)}</b></div>`).join('')
      + `</div></div><div class="lgd"><span>${esc(W.rsA.foot(rel, n, M.pct(ih), D.market))}</span><span class="sp"></span><span>${esc(M.rangeLabel(D.dates[D.E - n], D.dates[D.E], D.ref))}</span></div>`;
    onSeg(el, 'n', v => { S.rsN = +v; c.redraw() });
    onSeg(el, 'b', v => { S.rsB = v; c.redraw() });
    rowLocks(el, '.dvb .r', c);
  },
  detail(c): Detail {
    const D = c.D, K = calc(D), rel = c.S.rsB === 'rel', N = [1, 3, 5, 10, D.P('1M')], L = ['1D', '3D', '5D', '10D', '1M'];
    const f = (nm: string, n: number) => (rel ? K.rr(nm, n) : M.ret(D.sec(nm), D.E, n));
    const rows = D.names.map(nm => { const o: any = { nm, name: D.short(nm) }; N.forEach(n => (o['w' + n] = f(nm, n))); return o });
    [...rows].filter(r => r['w' + c.S.rsN] != null).sort((p, q) => q['w' + c.S.rsN] - p['w' + c.S.rsN]).forEach((r, i) => (r.rk = i + 1));
    return {
      title: rel ? W.rsA.dTitleRel : W.rsA.dTitleAbs, sub: rel ? W.rsA.dSubRel(D.market) : W.rsA.dSubAbs,
      cols: [{ k: 'name', l: W.col.sector }, ...N.map((n, i) => ({ k: 'w' + n, l: L[i], num: true, tone: true, f: rel ? (v: number) => M.pp(v) : (v: number) => M.pct(v) })), { k: 'rk', l: W.col.rank(`${c.S.rsN}D`), num: true, f: v => String(v) }],
      rows, sort: ['w' + c.S.rsN, 1], onRow: r => c.lock(r.nm), isSel: r => r.nm === c.S.pin,
      read: W.rsA.read(rel, D.market, c.S.rsN), ex: r => W.rsA.ex(r.name, r['w' + c.S.rsN], c.S.rsN, r.rk, rel, D.market),
    };
  },
};
/** rows that lock their sector on a click or Enter */
export function rowLocks(el: HTMLElement, sel: string, c: Ctx, attr = 'n') {
  $$(sel, el).forEach(r => {
    const go = () => c.lock(r.dataset[attr] as string);
    r.onclick = go;
    r.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === r) { e.preventDefault(); go() } };
  });
}

/* ===================== Rank change (logic.js L200-231) ===================== */
/** the compare date's index; a stored Custom date this page date cannot use (after it, or before the data) shows 5D
    and says so, never under a selected "Custom" (the mechanism of check 1 RP-1) */
export function compare(c: Ctx): { i: number; custom: boolean; note: string | null } {
  const D = c.D, n = c.S.rsN;
  if (c.S.rbK === 'C' && c.S.rbD) {
    let i = D.E - 1; while (i > 0 && D.dates[i] > c.S.rbD) i--;
    if (c.S.rbD < D.dates[D.E] && i >= n && D.dates[i] <= c.S.rbD) return { i, custom: true, note: null };
    return { i: Math.max(n, D.E - 5), custom: false, note: W.range.noDate(M.dateLabel(c.S.rbD, false, true)) };
  }
  const k = c.S.rbK === 'C' ? 5 : +c.S.rbK;
  return { i: Math.max(n, D.E - k), custom: false, note: null };
}
const compareIndex = (c: Ctx) => compare(c).i;
export const rsB: Card = {
  id: 'rsB', tab: 'rs', cls: 'rs-b',
  render(el, c) {
    const D = c.D, S = c.S, K = calc(D), n = S.rsN, P0 = compareIndex(c), a = K.rankAt(n, P0), b = K.rankAt(n, D.E), mo = D.P('1M'), dl = (i: number) => M.dateIn(D.dates[i], D.ref);
    const cp = compare(c), on = cp.custom ? 'C' : S.rbK === 'C' ? '5' : S.rbK;
    el.innerHTML = H3(W.rsB.title, W.rsB.sub(n, dl(P0), D.market), SEG('k', '', [['5', '5D'], ['10', '10D'], [String(mo), '1M'], ['C', W.range.custom]], on), c.win ? null : 'rsB')
      + `<div class="tb"><div class="slope" data-chart></div></div><div class="lgd"><span class="sw"><i style="background:var(--up)"></i>${esc(W.rsB.up)}</span><span class="sw"><i style="background:var(--down)"></i>${esc(W.rsB.down)}</span>${rangeNote(cp.note)}<span class="sp"></span><span>${esc(M.rangeLabel(D.dates[P0], D.dates[D.E], D.ref))}</span></div>`;
    onSeg(el, 'k', (v, btn) => {
      if (v === 'C') {
        openRange(btn, { title: W.rsB.popTitle, single: true, min: D.dates[n], max: D.dates[D.E - 1], cur: { a: D.dates[P0], b: D.dates[P0] },
          check: (_a, v2) => {
            if (!v2) return { ok: false, msg: W.rsB.pick };
            if (v2 >= D.dates[D.E]) return { ok: false, msg: W.rsB.before };
            let i = D.E; while (i > 0 && D.dates[i] > v2) i--;
            if (i < n) return { ok: false, msg: W.rsB.starts(M.dateLabel(D.dates[n], false, true)) };
            return { ok: true, msg: W.rsB.note(M.dateLabel(D.dates[i], true, true), D.E - i) };
          },
          apply: r => { S.rbK = 'C'; S.rbD = r.b; c.redraw() } });
        return;
      }
      S.rbK = v; c.redraw();
    });
    const box = $('[data-chart]', el);
    requestAnimationFrame(() => {
      if (!box.isConnected || box.clientHeight < 60) return;
      const Wd = box.clientWidth, H = box.clientHeight, narrow = Wd < 420, top = 22, rowH = (H - top - 6) / D.names.length, L = narrow ? 92 : 118, R = Wd - (narrow ? 104 : 118), Y = (r: number) => top + (r - 0.5) * rowH;
      let o = `<text class="hd" x="${L - 10}" y="12" text-anchor="end">${esc(dl(P0))}</text><text class="hd" x="${R + 10}" y="12">${esc(dl(D.E))}</text>`;
      D.names.forEach(nm => {
        const d = a[nm] - b[nm], pk = nm === S.pin, col = pk ? 'var(--text)' : d >= 3 ? 'var(--up)' : d <= -3 ? 'var(--down)' : 'var(--sx-dim)', w = pk ? 2.2 : Math.abs(d) >= 3 ? 2 : 1.2;
        const tip = `<b>${esc(nm)}</b><br>${esc(W.rsB.tip(a[nm], dl(P0), b[nm], d))}<br>${n}D ${esc(W.vs(D.market))}: ${M.pp(K.rr(nm, n, P0))} → ${M.pp(K.rr(nm, n))}`;
        o += `<g class="sl${pk ? ' pk' : ''}" data-n="${esc(nm)}" role="button" tabindex="0" aria-label="${esc(nm)}" data-tip="${esc(tip)}"><rect class="bg" x="0" y="${(Y(a[nm]) - rowH / 2).toFixed(1)}" width="${L - 2}" height="${rowH.toFixed(1)}" rx="4"/><rect class="bg" x="${R + 2}" y="${(Y(b[nm]) - rowH / 2).toFixed(1)}" width="${Wd - R - 2}" height="${rowH.toFixed(1)}" rx="4"/><line class="hit" x1="${L}" x2="${R}" y1="${Y(a[nm])}" y2="${Y(b[nm])}" stroke="transparent" stroke-width="12"/><line x1="${L}" x2="${R}" y1="${Y(a[nm])}" y2="${Y(b[nm])}" stroke="${col}" stroke-width="${w}"/><circle class="e" cx="${L}" cy="${Y(a[nm])}" r="3.5" fill="${col}"/><circle class="e" cx="${R}" cy="${Y(b[nm])}" r="3.5" fill="${col}"/>`
          + `<g class="rk" style="--rc:${d >= 3 ? 'var(--up)' : d <= -3 ? 'var(--down)' : 'var(--text-2)'}"><circle cx="${L}" cy="${Y(a[nm])}" r="8.5"/><text x="${L}" y="${Y(a[nm]) + 3.5}">${a[nm]}</text><circle cx="${R}" cy="${Y(b[nm])}" r="8.5"/><text x="${R}" y="${Y(b[nm]) + 3.5}">${b[nm]}</text></g>`
          + `<text class="lb${pk ? ' b' : ''}" x="${L - 10}" y="${Y(a[nm]) + 4}" text-anchor="end">${a[nm]}  ${esc(D.short(nm))}</text><text class="lb${pk ? ' b' : ''}" x="${R + 10}" y="${Y(b[nm]) + 4}">${b[nm]}  ${esc(D.short(nm))} <tspan class="${d > 0 ? 'u' : d < 0 ? 'd' : 'n'}">${d > 0 ? '▲' + d : d < 0 ? '▼' + -d : '—'}</tspan></text></g>`;
      });
      box.innerHTML = `<svg width="${Wd}" height="${H}" role="img" aria-label="${esc(W.rsB.aria)}">${o}</svg>`;
      rowLocks(box, '.sl', c);
    });
  },
  detail(c): Detail {
    const D = c.D, K = calc(D), n = c.S.rsN, P0 = compareIndex(c), E = D.E;
    const pts = [...new Set([E - 20, E - 15, E - 10, E - 5, P0, E])].filter(i => i >= n).sort((x, y) => x - y), rk = pts.map(i => K.rankAt(n, i));
    const r0 = K.rankAt(n, P0), rows = D.names.map(nm => { const o: any = { nm, name: D.short(nm), ch: r0[nm] - rk[rk.length - 1][nm], r: K.rr(nm, n) }; pts.forEach((_, j) => (o['p' + j] = rk[j][nm])); o.from = r0[nm]; o.to = rk[rk.length - 1][nm]; return o });
    return {
      title: W.rsB.dTitle, sub: W.rsB.dSub(n, D.market),
      cols: [{ k: 'name', l: W.col.sector }, ...pts.map((i, j) => ({ k: 'p' + j, l: M.dateIn(D.dates[i], D.ref), num: true, hl: i === P0, f: (v: number) => String(v) })),
             { k: 'ch', l: W.col.gained, num: true, tone: true, f: v => (v > 0 ? '▲' + v : v < 0 ? '▼' + Math.abs(v) : '0') }, { k: 'r', l: `${n}D ${W.vs(D.market)}`, num: true, tone: true, f: v => M.pp(v) }],
      rows, sort: ['ch', 1], onRow: r => c.lock(r.nm), isSel: r => r.nm === c.S.pin,
      read: W.rsB.read(n, M.dateIn(D.dates[P0], D.ref), D.market), ex: r => W.rsB.ex(r.name, r.from, M.dateIn(D.dates[P0], D.ref), r.to, M.dateIn(D.dates[E], D.ref), r.ch),
    };
  },
};

/* ===================== Weekly Excess Return (logic.js L250-269) ===================== */
const MAX_WEEKS = 26;
const weeksOf = (s: M.Span) => Math.min(MAX_WEEKS, Math.max(1, Math.floor(s.n / 5)));
function weeks(c: Ctx): { K: number[]; e1: number; custom: boolean; note: string | null } {
  const D = c.D, S = c.S;
  if (S.rsWn === 'C' && S.rsWr) {
    const { s, note } = customSpan(D, S.rsWr, '8W');
    if (s) return { K: M.weekEnds(s.last, weeksOf(s)), e1: s.last, custom: true, note };
    return { K: M.weekEnds(D.E, 8), e1: D.E, custom: false, note };
  }
  return { K: M.weekEnds(D.E, S.rsWn === 'C' ? 8 : +S.rsWn), e1: D.E, custom: false, note: null };
}
/* the week columns fill the card, and when they cannot all show, as many as fit are shown whole: the scroller's edge falls
   between two weeks, under the sticky sector column (check 1 OR-8: 8W at 1280 px showed a sliver of the oldest week) */
const NAME_W = 78, MIN_W = 28, GAP = 2;
function fitWeeks(t: HTMLElement, grid: HTMLElement, n: number) {
  const cs = getComputedStyle(t), inner = t.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  // a narrow card first narrows the sector column and the week columns a little, so that 8 weeks still fit
  for (const [nw, mw] of [[NAME_W, MIN_W], [64, 26]]) {
    const room = inner - nw;
    if (n * (mw + GAP) <= room + 1e-6) { grid.style.gridTemplateColumns = `${nw}px repeat(${n},minmax(${mw}px,1fr))`; grid.classList.toggle('tight', nw < NAME_W); return }
  }
  const room = inner - NAME_W, fits = Math.max(1, Math.floor((room + 1e-6) / (MIN_W + GAP)));
  const w = Math.floor(room / fits) - GAP;
  grid.style.gridTemplateColumns = `${NAME_W}px repeat(${n},${w}px)`; grid.classList.remove('tight');
}
export const rsW: Card = {
  id: 'rsW', tab: 'rs', cls: 'rs-w',
  render(el, c) {
    const D = c.D, S = c.S, Kc = calc(D), { K, e1, custom, note } = weeks(c), mo = D.P('1M');
    const val = (nm: string, e: number) => Kc.rr(nm, 5, e), DEF: M.Level = ['r20', 1];
    const SK = M.msKeep(S.rsWS, k => k === 'sn' || K.some(e => 'w' + e === k)), LAB: Record<string, string> = { sn: W.col.sector, ...Object.fromEntries(K.map(e => ['w' + e, W.rsW.weekTo(M.dateIn(D.dates[e], D.ref))])) };
    const rows = M.msSort(D.names.map(nm => { const r: any = { nm, sn: D.short(nm), r20: Kc.rr(nm, mo, e1) }; K.forEach(e => (r['w' + e] = val(nm, e))); return r }), SK, { sn: 1 }, DEF);
    const cap = Math.max(...rows.flatMap(r => K.map(e => Math.abs(r['w' + e] ?? 0)))) || 1;
    const f = (v: number) => (Math.abs(v) >= 10 ? M.sign(v) + Math.abs(v).toFixed(0) : M.ppx(v, 1));
    const cell = (nm: string, e: number) => {
      const v = val(nm, e); if (v == null) return '<div class="c">—</div>';
      return `<div class="c${nm === S.pin ? ' pk' : ''}" data-tip="${esc(`<b>${esc(D.short(nm))}</b> · ${esc(M.rangeLabel(D.dates[e - 5], D.dates[e], D.ref))}<br>${esc(W.rsA.sector)} ${M.pct(M.ret(D.sec(nm), e, 5))}<br>${esc(D.market)} ${M.pct(M.ret(D.IH, e, 5))}<br>${esc(W.rsA.excess)} ${M.pp(v)}`)}" style="${heat(v, cap)}">${f(v)}</div>`;
    };
    const on = custom ? 'C' : S.rsWn === 'C' ? '8' : S.rsWn;
    el.innerHTML = H3(W.rsW.title, W.rsW.sub(D.market), SEG('w', '', [['4', '4W'], ['8', '8W'], ['C', W.range.custom]], on), c.win ? null : 'rsW')
      + `<div class="tb rsw-s" data-scroll="x" data-sticky="1" data-scroll-key="${K[0]}-${K.length}"><div class="ovx-hm rsw${S.pin ? ' has' : ''}" style="grid-template-columns:${NAME_W}px repeat(${K.length},minmax(${MIN_W}px,1fr))">${msTh(SK, 'sn', esc(W.col.sector), 'hd l', W.sort.byName, { tag: 'div', txt: true })}${K.map((e, j) => {
        const mo2 = M.MON[+D.dates[e].slice(5, 7) - 1], nw = j === 0 || mo2 !== M.MON[+D.dates[K[j - 1]].slice(5, 7) - 1];
        return msTh(SK, 'w' + e, `<i>${nw ? mo2 : ''}</i><b>${+D.dates[e].slice(8, 10)}</b>`, 'hd', W.rsW.headTip(M.dateLabel(D.dates[e], false, true)), { tag: 'div' });
      }).join('')}`
      + rows.map(r => `<button type="button" class="nm${r.nm === S.pin ? ' pk' : ''}" data-n="${esc(r.nm)}" title="${esc(r.nm)}">${esc(r.sn)}</button>` + K.map(e => cell(r.nm, e)).join('')).join('') + `</div></div>`
      + `<div class="lgd">${msNote(SK, LAB, { sn: 1 }, W.rsW.defOrder(D.market))}<span>${esc(W.rsW.foot(K.length))}</span>${rangeNote(note)}<span class="sp"></span><span>${esc(K.length ? M.rangeLabel(D.dates[K[0] - 5], D.dates[e1], D.ref) : '')}</span></div>`;
    onSeg(el, 'w', (v, btn) => {
      // the popover prints the weeks the card will show (check 1 OR-6)
      if (v === 'C') { customRange(c, btn, S.rsWr, r => { S.rsWn = 'C'; S.rsWr = r }, { max: MAX_WEEKS * 5, maxWhy: W.rsW.maxWhy(MAX_WEEKS), min: 5, dflt: 40, label: s => { const k = M.weekEnds(s.last, weeksOf(s)); return W.rsW.label(M.rangeLabel(D.dates[k[0] - 5], D.dates[s.last], D.ref), k.length) } }); return }
      S.rsWn = v; c.redraw();
    });
    msWire(el, SK, () => c.redraw(), DEF, '.hd[data-k]');
    rowLocks(el, '.rsw .nm', c);
    // a new set of weeks opens on the newest week; the viewer's own scroll stays while the weeks are the same (check 1 OR-3)
    const fit = () => { const t = $('.rsw-s', el), g = $('.rsw', el); if (!t || !g) return; fitWeeks(t, g, K.length); if (!t.dataset.kept || t.dataset.atEnd) t.scrollLeft = 1e6 };
    fit(); requestAnimationFrame(fit);
  },
  detail(c): Detail {
    const D = c.D, Kc = calc(D), { K, e1 } = weeks(c);
    const rows = D.names.map(nm => {
      const v = K.map(e => Kc.rr(nm, 5, e)).filter((x): x is number => x != null);
      return { nm, name: D.short(nm), avg: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null, beat: v.filter(x => x > 0).length, best: v.length ? Math.max(...v) : null, worst: v.length ? Math.min(...v) : null, stk: M.streak(v) };
    });
    return {
      title: W.rsW.dTitle, sub: `${W.rsW.weeks(K.length)}${DOT}${K.length ? M.rangeLabel(D.dates[K[0] - 5], D.dates[e1], D.ref) : ''}`,
      cols: [{ k: 'name', l: W.col.sector }, { k: 'avg', l: W.col.avgWeek, num: true, tone: true, f: v => M.pp(v) }, { k: 'beat', l: W.col.ahead, num: true, f: v => `${v} / ${K.length}` },
             { k: 'best', l: W.col.bestWeek, num: true, tone: true, f: v => M.pp(v) }, { k: 'worst', l: W.col.worstWeek, num: true, tone: true, f: v => M.pp(v) },
             { k: 'stk', l: W.col.streak, num: true, tone: true, f: v => (v > 0 ? W.rsW.up(v) : v < 0 ? W.rsW.down(-v) : '—') }],
      rows, sort: ['avg', 1], onRow: r => c.lock(r.nm), isSel: r => r.nm === c.S.pin,
      read: W.rsW.read(D.market), ex: r => W.rsW.ex(r.name, r.avg, r.beat, K.length, r.best, D.market),
    };
  },
};

/* ===================== Sector Drill-down with its industries (logic.js L270-310; the industry rows shown, defect D03) ===================== */
interface DRow { nm: string; sn: string; ind?: boolean; sector?: string; r3d: M.N; r1: M.N; rM: M.N; r3: M.N; ry: M.N; e1: M.N; eM: M.N; e3: M.N; eM4: M.N; quad: M.Quad | null; ema: M.N; rt?: M.N; rt4?: M.N; d4?: M.N; qo?: number; mg?: M.N; k?: number }
export function drillRows(c: Ctx): { SEC: DRow[]; IND: DRow[] } {
  const D = c.D, K = calc(D), E = D.E, w = D.P('1W'), mo = D.P('1M'), q3 = D.P('3M'), yb = D.ytd();
  const ih1 = M.ret(D.IH, E, w), ihM = M.ret(D.IH, E, mo), ih3 = M.ret(D.IH, E, q3);
  const one = (a: M.N[], nm: string, sn: string): DRow => {
    const r1 = M.ret(a, E, w), rM = M.ret(a, E, mo), r3 = M.ret(a, E, q3), g = M.rotation(a, D.IH);
    return { nm, sn, r3d: M.ret(a, E, 3), r1, rM, r3, ry: M.retAt(a, yb, E), e1: M.minus(r1, ih1), eM: M.minus(rM, ihM), e3: M.minus(r3, ih3),
             eM4: M.minus(M.ret(a, E - 20, mo), M.ret(D.IH, E - 20, mo)), quad: M.quad(g.rs[E], g.mom[E]), ema: null };
  };
  const SEC = D.names.map(nm => {
    const r = one(D.sec(nm), nm, D.short(nm)); r.quad = K.q[nm][E];
    const b = D.breadth(nm); r.ema = b ? M.share(b.a50[E], b.n50[E]) : M.flagShare(D.members(nm).map(x => x.e50)).p;
    return r;
  });
  const IND: DRow[] = [];
  for (const nm of D.names) for (const ind of D.industries(nm)) {
    const s = D.series.industry?.[ind]; if (!s) continue;
    const r = one(D.indLevel(ind), ind, ind); r.ind = true; r.sector = nm;
    const ms = D.members(nm).filter(x => x.ind === ind); r.ema = M.flagShare(ms.map(x => x.e50)).p; r.k = ms.length;
    IND.push(r);
  }
  const QO: Record<string, number> = { Leading: 4, Improving: 3, Weakening: 2, Lagging: 1 };
  for (const L of [SEC, IND]) {
    M.rate(L, 'eM', 'rt'); M.rate(L, 'eM4', 'rt4');
    L.forEach(x => { x.d4 = x.rt != null && x.rt4 != null ? x.rt - x.rt4 : null; x.qo = x.quad ? QO[x.quad] : 0; const t = M.momTag(x.e1, x.eM, mo); x.mg = t ? t[1] : null });
  }
  return { SEC, IND };
}
export const rsD: Card = {
  id: 'rsD', tab: 'rs', cls: 'rs-d', stack: true,
  render(el, c) {
    const D = c.D, S = c.S, { SEC, IND } = drillRows(c), mo = D.P('1M'), open = new Set(S.rsOpen);
    const DEF: M.Level = ['rt', 1], SK = M.msKeep(S.rsS, k => COLS.some(x => x[0] === k));
    const COLSx = COLS.map(([k, cl, tip]) => [k, k === 'eM' ? W.col.vsH(D.market, '1M') : k === 'e3' ? W.col.vsH(D.market, '3M') : (W.rsD.cols as Record<string, string>)[k], cl, tip] as string[]);
    const LAB = Object.fromEntries(COLSx.map(x => [x[0], x[1]]));
    const sorted = M.msSort([...SEC], SK, { sn: 1 }, DEF);
    const NA = na(W.rsD.na);
    const pc = (v: M.N) => (v == null ? NA : `<span class="${M.cls(v)}">${M.pct(v, 1)}</span>`), p1 = (v: M.N) => (v == null ? NA : `<span class="${M.cls(v)}">${M.ppx(v, 1)}</span>`);
    const tag = (x: DRow) => { const t = M.momTag(x.e1, x.eM, mo); return t ? `<span class="tg ${t[0]}" title="${esc(W.rsD.momTip(M.ppx(t[1], 2)))}">${esc(W.mom[t[0]])}</span>` : NA };
    const row = (x: DRow) => {
      const kids = !x.ind && IND.some(u => u.sector === x.nm), isOpen = open.has(x.nm);
      return `<tr class="${x.ind ? 'u' : 'g'}${!x.ind && x.nm === S.pin ? ' pk' : ''}"${x.ind ? '' : ` data-n="${esc(x.nm)}" role="button" tabindex="0" aria-pressed="${x.nm === S.pin}"`}><td class="l">${x.ind ? `<span class="nmx" data-tip="${esc(esc(W.rsD.indTip(x.nm, x.k ?? 0)))}">${esc(x.nm)}</span>` : `${kids ? `<button type="button" class="car" data-x="${esc(x.nm)}" aria-expanded="${isOpen}" aria-label="${esc(W.rsD.openInd(x.nm, isOpen))}" title="${esc(W.rsD.openInd(x.nm, isOpen))}"><svg class="ic ic-sm"><use href="#i-${isOpen ? 'chev' : 'chevr'}"/></svg></button>` : '<span class="car"></span>'}<b>${esc(x.sn)}</b>`}</td>`
        + `<td>${pc(x.r3d)}</td><td>${pc(x.r1)}</td><td>${pc(x.rM)}</td><td>${pc(x.r3)}</td><td>${pc(x.ry)}</td><td>${p1(x.eM)}</td><td>${p1(x.e3)}</td>`
        + `<td><b>${x.rt ?? NA}</b></td><td>${x.d4 == null ? NA : `<span class="${M.cls(x.d4)}">${x.d4 === 0 ? '·' : (x.d4 > 0 ? '▲' : '▼') + Math.abs(x.d4)}</span>`}</td>`
        + `<td>${x.ema == null ? NA : x.ema.toFixed(0) + '%'}</td><td class="l">${x.quad ? quadTag(x.quad) : NA}</td><td class="l">${tag(x)}</td></tr>`;
    };
    el.innerHTML = H3(W.rsD.title, W.rsD.sub(D.market), `<button type="button" class="btn sm ghost" data-all>${esc(open.size ? W.rsD.closeAll : W.rsD.openAll)}</button>`, c.win ? null : 'rsD')
      + (open.size ? `<div class="rsd-note">${esc(W.rsD.indNote(D.weightLabel, IND.filter(u => u.rt != null).length))}</div>` : '')
      + `<div class="tbl-wrap" data-scroll="y" data-sticky="1"><table class="tbl padat"><thead><tr>${COLSx.map(([k, t, cl, tip]) => msTh(SK, k, esc(t), cl || '', tip ? W.rsD.tips[tip as keyof typeof W.rsD.tips] : '', { def: DEF, txt: k === 'sn' })).join('')}</tr></thead><tbody>`
      + sorted.map(x => row(x) + (open.has(x.nm) ? M.msSort(IND.filter(u => u.sector === x.nm), SK, { sn: 1 }, DEF).map(row).join('') : '')).join('')
      + `</tbody></table></div><div class="lgd">${msNote(SK, LAB, { sn: 1 })}<span>${esc(W.rsD.foot(D.market))}</span><span class="sp"></span><span>${esc(M.dateIn(D.dates[D.E], D.ref))}</span></div>`;
    $$('[data-x]', el).forEach(b => (b.onclick = e => { e.stopPropagation(); const n = b.dataset.x as string; S.rsOpen = open.has(n) ? S.rsOpen.filter(x => x !== n) : [...S.rsOpen, n]; c.redraw() }));
    ($('[data-all]', el) as HTMLElement).onclick = () => { S.rsOpen = open.size ? [] : [...D.names]; c.redraw() };
    rowLocks(el, 'tr.g', c);
    msWire(el, SK, () => c.redraw(), DEF, 'th[data-k]');
  },
  detail(c): Detail {
    const D = c.D, nm = shown(c), ih5 = M.ret(D.IH, D.E, D.P('1W')), sc = stockCols(c);
    const rows = D.members(nm).map(x => ({ ...x, name: x.t, x5: M.minus(x.r5d, ih5), ema: x.e50 == null ? null : x.e50 ? W.above : W.below }));
    return {
      title: W.rsD.dTitle(D.short(nm)), sub: W.stocks(rows.length), ctl: SEL_SECTOR(c, nm), onSel: v => c.lock(v, false), search: W.search.stock,
      cols: [sc.t, sc.ind, { k: 'r1d', l: '1D', num: true, tone: true, f: v => M.pct(v) }, { k: 'r5d', l: '5D', num: true, tone: true, f: v => M.pct(v) }, { k: 'x5', l: `5D ${W.vs(D.market)}`, num: true, tone: true, f: v => M.pp(v) },
             { k: 'r1m', l: '1M', num: true, tone: true, f: v => M.pct(v) }, { k: 'ema', l: 'EMA50' }, sc.w],
      rows, sort: ['w', 1], read: W.rsD.read(D.market), ex: r => W.rsD.ex(r.name, r.r5d, r.x5, r.e50, D.market),
    };
  },
};
/* the columns: key, class, the key of its header hint (words.ts W.rsD.tips) */
const COLS: string[][] = [['sn', 'l'], ['r3d'], ['r1'], ['rM'], ['r3'], ['ry'], ['eM', '', 'eM'], ['e3', '', 'e3'], ['rt', '', 'rt'], ['d4', '', 'd4'], ['ema', '', 'ema'], ['qo', 'l', 'qo'], ['mg', 'l', 'mg']];

/* ===================== a sector's stock lines (logic.js L313-356; the real closes of sector-stocks-<index>, G1) ===================== */
export const rsL: Card = {
  id: 'rsL', tab: 'rs', cls: 'rs-l',
  render(el, c) {
    const D = c.D, S = c.S, nm = shown(c), K = calc(D), sp = K.span(S.rsLw, S.rsLr), b0 = sp.b, e1 = sp.e, dates = D.dates.slice(b0, e1 + 1);
    const locked = !!S.pin && D.names.includes(S.pin);
    el.innerHTML = H3(W.rsL.title(D.short(nm)), W.rsL.sub(M.dateIn(D.dates[b0], D.ref), locked), SEG('w', '', periodOpts(['1M', '3M', 'YTD', 'C']), sp.key), c.win ? null : 'rsL')
      + `<div class="tb"><div class="rlc" data-chart></div></div><div class="lgd"><span class="sw"><i class="dsh"></i>${esc(W.rsL.index(D.short(nm)))}</span><span>${esc(W.rsL.foot)}</span>${rangeNote(sp.note)}<span class="sp"></span><span>${esc(M.rangeLabel(D.dates[b0], D.dates[e1], D.ref))}</span></div>`;
    onSeg(el, 'w', (v, btn) => {
      if (v === 'C') { customRange(c, btn, S.rsLr, r => { S.rsLw = 'C'; S.rsLr = r; S.rsLh = null }); return }
      S.rsLw = v; S.rsLh = null; c.redraw();
    });
    const box = $('[data-chart]', el), st = c.stocks(nm);
    if (st.state !== 'ready') { box.innerHTML = `<div class="cv-empty">${esc(st.state === 'loading' ? W.rsL.loading : st.state === 'missing' ? W.rsL.missing(c.example) : W.rsL.failed)}</div>`; return }
    const f = st.file, at = new Map(f.dates.map((d, i) => [d, i] as [string, number])), col = new Map(f.ticker.map((t, i) => [t, i] as [string, number]));
    const closes = (t: string) => { const k = col.get(t); if (k == null) return null; return D.dates.map(d => { const i = at.get(d); return i == null ? null : f.close[k][i] ?? null }) };
    const top = D.members(nm).filter(x => (x.w ?? 0) > 0 && col.has(x.t)).sort((p, q) => (q.w as number) - (p.w as number)).slice(0, 10);
    const ser = top.map(x => ({ n: x.t, a: M.path(closes(x.t) as M.N[], b0, e1) })), last = (a: M.N[]) => { for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i] as number; return null };
    const rk = ser.filter(x => last(x.a) != null).sort((p, q) => (last(q.a) as number) - (last(p.a) as number)), PAL = ['var(--c1)', 'var(--c4)', 'var(--c5)', 'var(--c3)'];
    const colr: Record<string, string> = {};
    [rk[0], rk[1], rk[rk.length - 2], rk[rk.length - 1]].forEach((x, k) => { if (x && !colr[x.n]) colr[x.n] = PAL[k] });
    let hover: string | null = null, geo: Geo | null = null, lines: Line[] = [];
    const draw = () => {
      const hl = hover || S.rsLh;
      lines = ser.map(x => ({ n: x.n, label: x.n, a: x.a, c: colr[x.n] || (x.n === hl ? 'var(--text)' : undefined), on: !!colr[x.n] || x.n === hl, strong: x.n === hl, mute: !!hl && x.n !== hl }));
      lines.push({ n: '__ix', label: D.short(nm), a: M.path(D.sec(nm), b0, e1), c: 'var(--text)', on: true, dash: true });
      geo = cumChart(box, lines, dates);
    };
    if (!ser.length) { box.innerHTML = `<div class="cv-empty">${esc(W.rsL.none(D.short(nm)))}</div>`; return }
    cumHover(box, { geo: () => geo, lines: () => lines, dates: () => dates, candidates: () => lines.filter(x => x.n !== '__ix'),
      pick: n => { if (n !== hover) { hover = n; draw() } },
      tip: (n, i, v) => `<span class="d">${esc(M.dateIn(dates[i], D.ref, true))}</span><div class="r"><span>${esc(n)}</span><b class="${M.cls(v)}">${M.pct(v)}</b></div><div class="r"><span>${esc(W.rsL.index(D.short(nm)))}</span><b class="${M.cls(M.retAt(D.sec(nm), b0, b0 + i))}">${M.pct(M.retAt(D.sec(nm), b0, b0 + i))}</b></div>` });
    requestAnimationFrame(draw);
  },
  detail(c): Detail {
    const D = c.D, nm = shown(c), s5 = M.ret(D.sec(nm), D.E, D.P('1W')), sc = stockCols(c);
    const rows = D.members(nm).filter(x => (x.w ?? 0) > 0).sort((p, q) => (q.w as number) - (p.w as number)).slice(0, 10).map(x => ({ ...x, name: x.t, vs: M.minus(x.r5d, s5) }));
    return {
      title: W.rsL.dTitle(D.short(nm)), sub: W.rsL.dSub, ctl: SEL_SECTOR(c, nm), onSel: v => { c.S.rsLh = null; c.lock(v, false) }, search: W.search.stock,
      cols: [sc.t, sc.ind, { k: 'r1d', l: '1D', num: true, tone: true, f: v => M.pct(v) }, { k: 'r5d', l: '5D', num: true, tone: true, f: v => M.pct(v) }, { k: 'vs', l: W.col.vsSector('5D'), num: true, tone: true, f: v => M.pp(v) }, { k: 'r1m', l: '1M', num: true, tone: true, f: v => M.pct(v) }, sc.w],
      rows, sort: ['w', 1], onRow: r => { c.S.rsLh = c.S.rsLh === r.t ? null : r.t; c.redraw() }, isSel: r => r.t === c.S.rsLh,
      read: W.rsL.read, ex: r => W.rsL.ex(r.name, r.r5d, r.vs),
    };
  },
};
