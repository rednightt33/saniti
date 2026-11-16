/* EXEC-BACKTEST-REVAMP Tahap D (user 2026-11-15 "1 setuju, 2a": the design file is the 1:1 reference; 2026-11-16 "Opsi C"):
   the design's signal chart under the price pane ("Signals chart v3"): one Gantt row per entry condition (its letter,
   colour and name; the days it is true as a solid bar, the days it still counts for the entry rule's window as hatching),
   a row for the entry signal and one for the trades of the last run, a switch per row that hides or shows it, the trades
   shaded on the price pane, a crosshair tooltip that says which conditions were met on that day and how long ago, and the
   trade table after a run (values on each trade's signal bar). The design's xsig, xsLanes, xsHover and xsTable. */
import type * as L from 'lightweight-charts';
import { $, COLORS, cls, esc, nf, pct, rp, toast } from './format.ts';
import { S } from './state.ts';
import { catOf } from './reg.ts';
import type { Card } from './api/types.ts';
import { exportCsv } from './results/list.ts';
import { condName, refreshSignals } from './signals.ts';

interface Bars { dates: string[]; o: ArrayLike<number>; h: ArrayLike<number>; l: ArrayLike<number>; c: ArrayLike<number> }
interface SigLike { series: { c: Card; s: Uint8Array }[]; entry: Uint8Array }
interface Row { c: Card; raw: Uint8Array; w: Uint8Array; L: string; col: string; off: boolean; wait: boolean }
interface Tr { k: number; i: number; s: number; j: number; r: number; why: string }

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'], DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
/** "Mon 2 Jan 2026" */
export const dayName = (s: string) => { const d = new Date(s + 'T00:00:00Z'); return `${DOW[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}` };
/** a condition's letter in the formula bar, the lanes and the trade table (A, B, C, ...) */
export const letterOf = (k: number) => String.fromCharCode(65 + k);

/** the lanes' state: the chart's data (null: nothing drawn), the selected trade (-1: none), the crosshair */
export const LANES: { a: { bars: Bars; idx: number[]; sig: SigLike; tk: string; wait: boolean } | null; sel: number; cx: number | null;
  rows: Row[]; tr: Tr[]; pos: Map<number, number> } = { a: null, sel: -1, cx: null, rows: [], tr: [], pos: new Map() };

let chart: L.IChartApi | null = null;
/** the price chart the lanes follow (signals.ts initPriceChart) */
export const initLanes = (pc: L.IChartApi) => { chart = pc; pc.subscribeCrosshairMove(p => laneHover(p)) };
const redraw = () => refreshSignals();

const pending = (c: Card, wait: boolean) => wait && catOf(c).group === 'flow';
/** a phone (decision 2a): the chart has no left gutter, the left header sits above it and each lane's name is on its
    own line over the lane (the design's 200px gutter left a chart 130px wide there) */
export const NARROW = matchMedia('(max-width:600px)');

/** new data for the lanes (undefined: keep the last), then draw them and the trade table */
export function laneSignals(bars?: Bars | null, idx?: number[], sig?: SigLike, tk?: string, wait = false) {
  if (bars !== undefined) LANES.a = bars && idx && sig && tk ? { bars, idx, sig, tk, wait } : null;
  const A = LANES.a;
  if (!A || !A.idx.length) { $('xsig').innerHTML = ''; $('xsShade').innerHTML = ''; tradeTable(); return }
  const res = S.result, at = new Map(A.bars.dates.map((d, k) => [d, k])), ix = (k: number) => res ? at.get(res.days[k]) ?? -1 : -1;
  LANES.tr = res && !S.hidden.__trades ? res.trades.filter(t => t.tk === A.tk).map((t, k) => ({ k, i: ix(t.ei), s: ix(t.sig), j: ix(t.xi), r: t.ret, why: t.why }))
    .filter(t => t.i >= 0 && t.j >= 0) : [];
  const win = Math.max(1, S.window | 0);
  LANES.rows = A.sig.series.map((q, k) => {
    const raw = q.s, w = new Uint8Array(raw.length);
    let last = -1e9;
    for (let i = 0; i < raw.length; i++) { if (raw[i]) last = i; w[i] = i - last < win ? 1 : 0 }
    const wait = pending(q.c, A.wait);
    return { c: q.c, raw, w, L: letterOf(k), col: COLORS[S.conds.indexOf(q.c) % COLORS.length], off: !!S.hidden[q.c.id] || wait, wait };
  });
  LANES.pos = new Map(A.idx.map((d, k) => [d, k]));
  drawSignalLanes();
  tradeTable(LANES.tr, LANES.rows, A.bars, A.tk);
}

/** the Gantt rows under the price pane and the trades shaded on it, on the chart's visible range */
export function drawSignalLanes() {
  const A = LANES.a, host = $('xsig'), shade = $('xsShade');
  if (!A || !host || !chart) return;
  const ts = chart.timeScale(), LW = chart.priceScale('left').width(), PW = ts.width(), bw = Math.max(1, ts.options().barSpacing), vr = ts.getVisibleLogicalRange();
  if (!vr || !PW) return;
  const all = A.idx, sig = A.sig, from = Math.max(0, Math.floor(vr.from) - 1), to = Math.min(all.length - 1, Math.ceil(vr.to) + 1);
  const X = (l: number) => LW + (ts.logicalToCoordinate(l as L.Logical) ?? 0), rows = LANES.rows, TR = LANES.tr, narrow = NARROW.matches;
  const rh = narrow ? 16 : 22, gap = 5, lh = narrow ? 20 : 0;   // a phone: the name's line (lh) over each lane
  const lanes: [string, Row | null][] = [...rows.map(r => [r.L, r] as [string, Row]), ['∩', null], ['T', null]];
  const H = lanes.length * (lh + rh + gap) + 6, W = host.clientWidth;
  host.style.height = H + 'px';
  const out: string[] = [], add = (s: string) => out.push(s), Y = (k: number) => 4 + k * (lh + rh + gap) + lh, LY = (k: number) => Y(k) - lh;
  add(`<defs><pattern id="xsHatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="var(--surface-2)"/><line x1="0" y1="0" x2="0" y2="5" stroke="var(--text-3)" stroke-opacity=".55" stroke-width="1.6"/></pattern><clipPath id="xsClip"><rect x="${LW}" y="0" width="${PW}" height="${H}"/></clipPath></defs>`);
  const spans = (arr: ArrayLike<number>, y: number, hh: number, fill: string, ex = '') => {
    let s: number | null = null;
    for (let l = from; l <= to + 1; l++) {
      const on = l <= to && arr[all[l]];
      if (on && s === null) s = l;
      if (!on && s !== null) { add(`<rect x="${X(s) - bw / 2}" y="${y}" width="${(l - s) * bw}" height="${hh}" fill="${fill}" ${ex}/>`); s = null }
    }
  };
  add('<g clip-path="url(#xsClip)">');
  lanes.forEach(([, r], k) => {
    const y = Y(k);
    add(`<rect x="${LW}" y="${y}" width="${PW}" height="${rh}" fill="var(--surface-2)"/>`);
    if (r && !r.off) { spans(r.w, y + 3, rh - 6, 'url(#xsHatch)', 'rx="3"'); spans(r.raw, y + 3, rh - 6, 'var(--gray-700,#4d4d4d)', 'rx="3"') }
  });
  if (!S.hidden.__entry && !A.wait) spans(sig.entry, Y(lanes.length - 2) + 3, rh - 6, 'var(--up)', 'rx="3" opacity=".85"');
  { const y = Y(lanes.length - 1);
    TR.forEach(t => {
      const a = LANES.pos.get(t.i), b = LANES.pos.get(t.j);
      if (a == null || b == null || b < from || a > to) return;
      const xa = X(a), ww = Math.max(4, X(b) - xa);
      add(`<rect x="${xa}" y="${y + 3}" width="${ww}" height="${rh - 6}" rx="${(rh - 6) / 2}" fill="${t.r >= 0 ? 'var(--up)' : 'var(--down)'}" ${t.k === LANES.sel ? 'stroke="var(--text)" stroke-width="1.5"' : ''}/>`
        + (ww > 40 ? `<text x="${xa + ww / 2}" y="${y + rh / 2 + 4}" text-anchor="middle" font-size="10" font-weight="600" fill="#fff">${pct(t.r, 1)}</text>` : ''));
    }) }
  if (LANES.cx != null) add(`<line x1="${LW + LANES.cx}" x2="${LW + LANES.cx}" y1="0" y2="${H}" stroke="var(--text-3)" stroke-dasharray="3 3"/>`);
  add('</g>');
  // EXEC-BACKTEST-LOAD (user 2026-10-27): a flow lane and the entry lane wait for the broker data: labelled
  // "loading" with the small ring in place of their switch, not filled
  const waits = (r: Row | null, l: string) => r ? r.wait : l === '∩' && A.wait;
  lanes.forEach(([l, r], k) => {
    const y = narrow ? LY(k) : Y(k) + (rh - 18) / 2, dark = !r, t = (r ? catOf(r.c).label : l === '∩' ? 'Entry signal' : 'Trades') + (waits(r, l) ? ' · loading' : '');
    const room = narrow ? Math.floor((W - 90) / 6.5) : 17;
    add(`<g opacity="${r && r.off ? 0.45 : 1}"><rect x="8" y="${y}" width="18" height="18" rx="3" fill="${dark ? 'var(--text)' : 'var(--sel)'}"/><text x="17" y="${y + 13}" text-anchor="middle" font-size="10.5" font-weight="700" fill="${dark ? 'var(--surface)' : 'var(--text-2)'}">${l}</text>${r ? `<rect x="33" y="${y + 5}" width="8" height="8" rx="2" fill="${r.col}"/>` : ''}<text x="${r ? 47 : 34}" y="${y + 13}" font-size="11.5" font-weight="600" fill="var(--text)">${esc(t.length > room ? t.slice(0, room - 1) + '…' : t)}</text></g>`);
  });
  host.innerHTML = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">${out.join('')}</svg>` + lanes.map(([l, r], k) => {
    const id = r ? r.c.id : l === '∩' ? '__entry' : '__trades', on = !S.hidden[id], name = r ? catOf(r.c).label : l === '∩' ? 'Entry signal' : 'Trades';
    if (waits(r, l)) return `<b class="ml-spin sm xs-wait" role="status" aria-label="${esc(name)}: loading broker data" title="Loading broker data" style="top:${narrow ? LY(k) + 3 : Y(k) + (rh - 14) / 2}px;left:${narrow ? W - 22 : LW - 32}px"></b>`;
    return `<button type="button" class="xs-tg ${on ? 'on' : ''}" role="switch" aria-checked="${on}" aria-label="${on ? 'Hide' : 'Show'} ${esc(name)}" title="${on ? 'Hide' : 'Show'} ${esc(name)} on the chart" data-xh="${id}" style="top:${narrow ? LY(k) + 1 : Y(k) + (rh - 16) / 2}px;left:${narrow ? W - 30 : LW - 38}px"><span></span></button>`;
  }).join('');
  host.querySelectorAll('[data-xh]').forEach((b: HTMLElement) => b.onclick = () => { S.hidden[b.dataset.xh!] = !S.hidden[b.dataset.xh!]; redraw() });
  const pcEl = $('priceChart'), ph = pcEl.clientHeight - ts.height();
  shade.setAttribute('width', pcEl.clientWidth); shade.setAttribute('height', ph); shade.style.top = pcEl.offsetTop + 'px';
  shade.innerHTML = `<clipPath id="xsShClip"><rect x="${LW}" y="0" width="${PW}" height="${ph}"/></clipPath><g clip-path="url(#xsShClip)">` + TR.map(t => {
    const a = LANES.pos.get(t.i), b = LANES.pos.get(t.j);
    if (a == null || b == null || b < from || a > to) return '';
    const xa = X(a);
    return `<rect x="${xa}" y="0" width="${Math.max(1, X(b) - xa)}" height="${ph}" fill="${t.r >= 0 ? 'var(--green-bg)' : 'var(--red-bg)'}"/>` + (t.k === LANES.sel ? `<line x1="${xa}" x2="${xa}" y1="0" y2="${ph}" stroke="var(--blue)"/>` : '');
  }).join('') + '</g>';
}

/** the crosshair's tooltip: the day's bar, the trade state, and each condition met today or how many bars ago */
function laneHover(p: L.MouseEventParams) {
  const tip = $('xsTip'), A = LANES.a;
  LANES.cx = p && p.point ? p.point.x : null;
  requestAnimationFrame(drawSignalLanes);
  if (!A || !p || !p.point || p.logical == null) { tip.hidden = true; return }
  const l = Math.round(p.logical);
  if (l < 0 || l >= A.idx.length) { tip.hidden = true; return }
  const i = A.idx[l], bars = A.bars, sig = A.sig, win = Math.max(1, S.window | 0), rows = LANES.rows, TR = LANES.tr;
  const ago = (r: Row) => { for (let j = 0; j < win; j++) if (r.raw[i - j]) return j; return null };
  const ent = TR.find(t => t.i === i), ext = TR.find(t => t.j === i), inT = TR.find(t => i > t.i && i < t.j);
  const state = ent ? `<span class="pill pos">Entry ${ent.k + 1}</span>` : ext ? `<span class="pill neg">Exit ${ext.k + 1} · ${esc(ext.why)}</span>`
    : inT ? `<span class="pill info">In trade ${inT.k + 1} · day ${i - inT.i}</span>` : sig.entry[i] ? '<span class="pill pos">Entry rule met</span>'
    : `<span class="pill">${rows.filter(r => ago(r) != null).length} of ${rows.length} met</span>`;
  const t2 = ent || ext;
  tip.innerHTML = `<div class="th"><b>${dayName(bars.dates[i])}</b><span>O ${nf(bars.o[i], 0)} · H ${nf(bars.h[i], 0)} · L ${nf(bars.l[i], 0)} · C ${nf(bars.c[i], 0)}</span></div><div class="st">${state}</div>`
    + rows.map(r => { const a = ago(r);
      return `<div class="r"><span><i class="${a != null ? 'ok' : 'no'}">${a != null ? '✓' : '·'}</i><b class="bd">${r.L}</b>${esc(condName(r.c))}</span><b>${r.off ? 'hidden' : a == null ? 'not met' : a === 0 ? 'today' : a + ' bar' + (a > 1 ? 's' : '') + ' ago'}</b></div>` }).join('')
    + (t2 ? `<div class="fw"><span>${ent ? 'Trade' : 'Held ' + (ext!.j - ext!.i) + ' bars'}</span><b class="${cls(t2.r)}">${pct(t2.r, 2)}</b></div>` : '');
  tip.hidden = false;
  const LW = chart!.priceScale('left').width(), x = LW + p.point.x, pcEl = $('priceChart'), Wp = pcEl.clientWidth, tw = tip.offsetWidth || 300;
  tip.style.left = Math.max(4, x + 20 + tw > Wp ? x - 20 - tw : x + 20) + 'px';
  tip.style.top = (pcEl.offsetTop + 10) + 'px';
}


/** after a run: the stock's trades with each condition's state on the signal bar, forward returns and drawdown */
function tradeTable(TR?: Tr[], rows?: Row[], bars?: Bars, tk?: string) {
  const box = $('sigTrades');
  if (!box) return;
  const res = S.result;
  if (!res || !TR || !rows || !bars || !tk) { box.hidden = true; box.innerHTML = ''; return }
  const all = res.trades.filter(t => t.tk === tk), at = new Map(bars.dates.map((d, k) => [d, k])), ix = (k: number) => at.get(res.days[k]) ?? -1;
  const win = Math.max(1, S.window | 0), c = bars.c;
  const fwd = (i: number, k: number) => i >= 0 && i + k < c.length ? c[i + k] / c[i] - 1 : null;
  const mdd = (i: number) => { let v = 0; for (let k = 1; k <= 20 && i + k < c.length; k++) v = Math.min(v, bars.l[i + k] / c[i] - 1); return v };
  const pc2 = (v: number | null, d = 2) => v == null ? '<td class="mut">—</td>' : `<td class="${cls(v)}">${pct(v, d)}</td>`;
  const ago = (r: Row, i: number) => { for (let j = 0; j < win; j++) if (r.raw[i - j]) return j; return null };
  box.hidden = false;
  box.innerHTML = `<div class="card-h xt-h"><h3>Trades</h3><span class="hint">${esc(tk)} · ${all.length} trade${all.length === 1 ? '' : 's'} · values on the signal bar; each condition may have been met up to ${win} bar${win > 1 ? 's' : ''} earlier${S.stale ? ' · <b class="stale-t">settings changed, run again to update</b>' : ''}</span><span class="sp"></span><button class="btn sm" id="xtCsv">Export CSV</button><button class="btn sm" id="xtTerm">Send to Terminal</button></div>
 <div class="xt-wrap"><table class="xtbl"><thead><tr><th class="l">#</th><th class="l">Signal date</th><th>Close</th>${rows.map(r => `<th title="${esc(condName(r.c))}"><span class="bd">${r.L}</span>${esc(catOf(r.c).label)}</th>`).join('')}<th class="l">Entry</th><th class="l">Exit</th><th class="l">Reason</th><th>Days</th><th>Return</th><th>P&amp;L</th><th>+5D</th><th>+10D</th><th>+20D</th><th>Max drawdown 20D</th></tr></thead><tbody>`
    + all.map((t, k) => {
      const s = ix(t.sig), ei = ix(t.ei), xi = ix(t.xi);
      return `<tr class="${k === LANES.sel ? 'on' : ''}" data-k="${k}"><td class="l"><span class="n">${k + 1}</span></td><td class="l">${s >= 0 ? dayName(bars.dates[s]) : '—'}</td><td>${s >= 0 ? nf(c[s], 0) : '—'}</td>${rows.map(r => {
        const a = s >= 0 ? ago(r, s) : null;
        return `<td class="${a == null ? 'mut' : ''}">${a == null ? '—' : a === 0 ? 'on bar' : a + ' bar' + (a > 1 ? 's' : '') + ' ago'}</td>` }).join('')}<td class="l">${ei >= 0 ? dayName(bars.dates[ei]).slice(4) : '—'} · ${nf(t.entry, 0)}</td><td class="l">${xi >= 0 ? dayName(bars.dates[xi]).slice(4) : '—'} · ${nf(t.exit, 0)}</td><td class="l">${esc(t.why)}</td><td>${t.bars}</td>${pc2(t.ret)}<td class="${cls(t.pnl)}">${rp(t.pnl)}</td>${pc2(fwd(s, 5))}${pc2(fwd(s, 10))}${pc2(fwd(s, 20))}${s >= 0 ? pc2(mdd(s)) : '<td class="mut">—</td>'}</tr>`;
    }).join('') + '</tbody></table></div>';
  box.querySelectorAll('tr[data-k]').forEach((r: HTMLElement) => r.onclick = () => { const k = +r.dataset.k!; LANES.sel = LANES.sel === k ? -1 : k; redraw() });
  $('xtCsv').onclick = () => exportCsv();
  // the Terminal reads its symbol from ml.symbol at boot; the EDGE shell takes edge-nav from its own frame (the Screener's way)
  $('xtTerm').onclick = () => {
    try { localStorage.setItem('ml.symbol', tk) } catch { /* storage off: the Terminal opens on its own symbol */ }
    try { parent.postMessage({ type: 'edge-nav', route: 'terminal' }, location.origin) } catch { /* not framed */ }
    toast(`${tk} opens in the Terminal`);
  };
}
