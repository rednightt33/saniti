/* ==========================================================================
   Flow indicators FL01-FL39 of the EDGE terminal (EXEC-TERMINAL-FLOW-IND, user go 2026-10-30).
   Pure calculations, no DOM, like calc/indicators.ts: `FLOW[id](ctx, params)` returns `{ output: (number|null)[] }`
   aligned with the chart's candles (null = no value; a candle without broker data is never 0).

   Contract: verification/terminal_api/flow_indicators/FLOW_INDICATORS_SPEC.xlsx (names, parameters, defaults: the
   generated registry src/data/flowRegistry.json) and FORMULAS.md next to it (every formula and the shared conventions:
   filter, window, ratio and null rules, Top-N cohort, bandar, mid-rank percentile). Checked against an independent
   recomputation from Feature 05 (verification/terminal_api/flow_indicators/oracle/).

   One shape of raw data for every caller (FlowRows): the published broker rows with the candle they belong to. The
   Terminal builds it in its worker (data/worker.ts flowRows); the Screener and the Backtest can build the same from
   backtest/src/core/datafile.ts brokerRows, so the three show the same numbers.
   ========================================================================== */

export type Num = number | null;
export type Series = Num[];
export type FlowParams = Record<string, any>;
export type FlowOut = Record<string, Series>;

export const BOARDS = ['Regular', 'Nego', 'Cash'] as const;
export const INVESTORS = ['Foreign', 'Domestic'] as const;

/** The broker rows of one ticker, columnar. bf/sf NaN = the source has no transaction count for the row. */
export interface FlowRows {
  n: number;                // rows
  N: number;                // candles
  t: Int32Array;            // the row's candle
  b: Uint16Array;           // index into brokers
  inv: Uint8Array;          // index into INVESTORS
  brd: Uint8Array;          // index into BOARDS
  bv: Float64Array; sv: Float64Array; bl: Float64Array; sl: Float64Array; bf: Float64Array; sf: Float64Array;
  brokers: string[];
  has: Uint8Array;          // 1 when the candle has at least one broker row
}
export interface InsiderRow { t: number; value: number }  // candle, signed value (BUY +, SELL -)
export interface FlowContext {
  rows: FlowRows;
  dates: string[];          // the candles' first session dates
  close: Series;
  volume: Series;
  insider: InsiderRow[];
  classification: Record<string, string>;  // broker code -> Institutional-heavy | Retail-heavy | Mixed | Niche
}

const BOARD_INDEX: Record<string, number> = { Regular:0, Nego:1, Cash:2, Tunai:2 };
const INVESTOR_INDEX: Record<string, number> = { Foreign:0, Domestic:1 };
export const boardIndex = (m: string) => BOARD_INDEX[m] ?? (/nego/i.test(m) ? 1 : /cash|tunai/i.test(m) ? 2 : 0);
export const investorIndex = (i: string) => INVESTOR_INDEX[i] ?? 1;

/** FlowRows from plain rows (tests, and callers with row objects). `candleOf` maps a date to its candle (or -1). */
export function flowRows(rows: { d: string; b: string; i: string; m: string; bv: number; sv: number; bl: number; sl: number; bf?: number | null; sf?: number | null }[],
  N: number, candleOf: (d: string) => number): FlowRows {
  const keep = rows.filter(r => candleOf(r.d) >= 0), n = keep.length, brokers = [...new Set(keep.map(r => r.b))].sort();
  const at = new Map(brokers.map((b, k) => [b, k]));
  const out: FlowRows = { n, N, t:new Int32Array(n), b:new Uint16Array(n), inv:new Uint8Array(n), brd:new Uint8Array(n),
    bv:new Float64Array(n), sv:new Float64Array(n), bl:new Float64Array(n), sl:new Float64Array(n), bf:new Float64Array(n), sf:new Float64Array(n),
    brokers, has:new Uint8Array(N) };
  keep.forEach((r, k) => {
    const t = candleOf(r.d);
    out.t[k] = t; out.b[k] = at.get(r.b)!; out.inv[k] = investorIndex(r.i); out.brd[k] = boardIndex(r.m);
    out.bv[k] = r.bv || 0; out.sv[k] = r.sv || 0; out.bl[k] = r.bl || 0; out.sl[k] = r.sl || 0;
    out.bf[k] = r.bf == null ? NaN : r.bf; out.sf[k] = r.sf == null ? NaN : r.sf;
    out.has[t] = 1;
  });
  return out;
}

/* ---- per-filter grid: per broker prefix sums over the candles (a window sum is two lookups) ----
   A prefix difference P[t+1] - P[a] carries the rounding of the cumulative total, not of the window: on a measure with
   fractions (lots: odd lots, and lots adjusted for corporate actions such as BRPT 2016) a broker's running total of
   1e8 lots leaves about 1e-8 lot of noise in a one-candle sum (BBCA 0.26 lot read as 0.2599999905, checked against the
   oracle 2026-10-30). So a measure keeps a second, compensated array (`lo`, the running rounding error) whenever its
   cells are not all integers or its total passes 2^53; the window sum is then exact to the last digit. Whole-number
   measures below 2^53 (rupiah, transaction counts on today's data) need no second array: their prefix sums are exact. */
const MEASURES = ['bv', 'sv', 'bl', 'sl', 'bf', 'sf'] as const;
type Measure = typeof MEASURES[number];
type Col = Measure | 'miss';                     // miss: rows without bf/sf
interface Grid {
  R: FlowRows; B: number; N: number;
  keep: Int32Array;                              // the rows that pass the filter
  pre: Partial<Record<Col, Float64Array>>;       // per broker prefix over candles: [b * (N + 1) + t + 1]
  lo: Partial<Record<Col, Float64Array>>;        // its compensation, when the measure needs one
  tot: Partial<Record<Col, Float64Array>>;       // all brokers prefix: [t + 1]
  totLo: Partial<Record<Col, Float64Array>>;
  cohorts: Map<string, Map<number, number[]>>;   // cohorts by rule, then by window (cohort)
}
/* a few filters per ticker are in use at once (up to about 15 MB each on the largest tickers, only the measures an
   indicator reads are built): the last GRIDS are kept */
const GRIDS = 4;
const gridCache = new WeakMap<FlowRows, Map<string, Grid>>();

/** running sums of `arr` in place over [o+1 .. o+n]; with `lo`, compensated (TwoSum) so hi + lo is the exact sum */
function runSum(arr: Float64Array, lo: Float64Array | undefined, o: number, n: number) {
  if (!lo) { for (let t = o + 1; t <= o + n; t++) arr[t] += arr[t - 1]; return }
  let hi = 0, err = 0;
  for (let t = o + 1; t <= o + n; t++) {
    const x = arr[t], s = hi + x, bb = s - hi;
    err += (hi - (s - bb)) + (x - bb); hi = s;
    arr[t] = hi; lo[t] = err;
  }
}
/** hi[j] + lo[j] - (hi[i] + lo[i]), exact before the final rounding */
function diff(hi: Float64Array, lo: Float64Array | undefined, j: number, i: number): number {
  const a = hi[j], b = hi[i], s = a - b;
  if (!lo) return s;
  const bb = s - a, e = (a - (s - bb)) + (-b - bb);
  return s + (e + (lo[j] - lo[i]));
}

function grid(R: FlowRows, boards: readonly string[] | null, investors: readonly string[] | null): Grid {
  const bs = new Set((boards ?? BOARDS).map(boardIndex)), is = new Set((investors ?? INVESTORS).map(investorIndex));
  const key = [...bs].sort().join() + '|' + [...is].sort().join();
  let per = gridCache.get(R); if (!per) gridCache.set(R, per = new Map());
  const hit = per.get(key); if (hit) { per.delete(key); per.set(key, hit); return hit }
  const okB = [0, 1, 2].map(x => bs.has(x)), okI = [0, 1].map(x => is.has(x)), keep = new Int32Array(R.n);
  let n = 0;
  for (let k = 0; k < R.n; k++) if (okB[R.brd[k]] && okI[R.inv[k]]) keep[n++] = k;
  const g: Grid = { R, B:R.brokers.length, N:R.N, keep:keep.slice(0, n), pre:{}, lo:{}, tot:{}, totLo:{}, cohorts:new Map() };
  per.set(key, g);
  while (per.size > GRIDS) per.delete(per.keys().next().value!);
  return g;
}
/** build measure m of a grid on first use: cell sums (slot t + 1), then running sums per broker and over all brokers */
function build(g: Grid, m: Col): Float64Array {
  const { R, B, N, keep } = g, stride = N + 1, arr = new Float64Array(B * stride), t2 = new Float64Array(stride);
  const { t, b, bf, sf } = R, col = m === 'miss' ? null : R[m], counts = m === 'bf' || m === 'sf';
  for (let j = 0; j < keep.length; j++) {
    const k = keep[j], at = b[k] * stride + t[k] + 1, gap = Number.isNaN(bf[k]) || Number.isNaN(sf[k]);
    if (!col) { if (gap) arr[at] += 1 }
    else if (!counts || !gap) arr[at] += col[k];
  }
  let exact = true, sum = 0;
  for (let j = 0; j < arr.length; j++) { const x = arr[j]; if (x) { if (exact && !Number.isInteger(x)) exact = false; sum += Math.abs(x) } }
  for (let k = 0; k < B; k++) { const o = k * stride; for (let i = 1; i <= N; i++) t2[i] += arr[o + i] }
  const lo = !exact || sum >= 2 ** 53 ? new Float64Array(B * stride) : undefined, totLo = lo ? new Float64Array(stride) : undefined;
  for (let k = 0; k < B; k++) runSum(arr, lo, k * stride, N);
  runSum(t2, totLo, 0, N);
  g.pre[m] = arr; g.tot[m] = t2; g.lo[m] = lo; g.totLo[m] = totLo;
  return arr;
}
/** sum of measure m of broker b over candles a..t (inclusive) */
const bw = (g: Grid, m: Col, b: number, a: number, t: number) => {
  const o = b * (g.N + 1), hi = g.pre[m] ?? build(g, m);
  return diff(hi, g.lo[m], o + t + 1, o + a);
};
/** sum over every broker of measure m over candles a..t */
const aw = (g: Grid, m: Col, a: number, t: number) => {
  if (!g.tot[m]) build(g, m);
  return diff(g.tot[m]!, g.totLo[m], t + 1, a);
};

const div = (a: number, b: number): Num => b !== 0 && Number.isFinite(a) && Number.isFinite(b) ? a / b : null;
const firsts = new WeakMap<FlowRows, number>();
const firstData = (R: FlowRows) => {
  let f = firsts.get(R);
  if (f === undefined) { f = R.N; for (let t = 0; t < R.N; t++) if (R.has[t]) { f = t; break } firsts.set(R, f) }
  return f;
};
const lastData = (R: FlowRows) => { for (let t = R.N - 1; t >= 0; t--) if (R.has[t]) return t; return -1 };
/** the window a..t of length W ending at t, or null when t has no data or the window starts before the first data */
function win(R: FlowRows, t: number, W: number): number | null {
  const a = t - W + 1;
  return R.has[t] && W >= 1 && a >= firstData(R) ? a : null;
}
const series = (N: number): Series => new Array(N).fill(null);
const int = (v: any, d: number) => { const n = Math.floor(Number(v)); return Number.isFinite(n) && n >= 1 ? n : d };

/* ---- a figure against the user's threshold ----
   The figures are computed in floating point from exact data, so a value that equals the threshold exactly can land a
   hair either side of it (DAYA 2025-10-02: 1000 -> 1030 is a 3% move, computed 3.0000000000000027, which failed
   "move <= 3%"; checked against the oracle 2026-10-30). A difference below 1e-12 of the larger magnitude is equality,
   so ">=" and "<=" hold and ">" does not. A threshold of 0 stays exact. */
const near = (x: number, th: number) => Math.abs(x - th) <= 1e-12 * Math.max(Math.abs(x), Math.abs(th));
export const atLeast = (x: number, th: number) => x >= th || near(x, th);
export const atMost = (x: number, th: number) => x <= th || near(x, th);
export const above = (x: number, th: number) => x > th && !near(x, th);

/* ---- cohorts ---- */
const SCORE: Record<string, (g: Grid, b: number, a: number, t: number) => number> = {
  net_buy:(g, b, a, t) => bw(g, 'bv', b, a, t) - bw(g, 'sv', b, a, t),
  gross_buy:(g, b, a, t) => bw(g, 'bv', b, a, t),
  net_sell:(g, b, a, t) => bw(g, 'sv', b, a, t) - bw(g, 'bv', b, a, t),
  gross_buy_lots:(g, b, a, t) => bw(g, 'bl', b, a, t),
};
/** the top `n` brokers by score over a..t (score > 0; ties by broker code). A selection, not a sort: N is small. */
function topBrokers(g: Grid, R: FlowRows, a: number, t: number, n: number, basis: string): number[] {
  const f = SCORE[basis] || SCORE.net_buy;
  return topOf(R, n, b => f(g, b, a, t));
}
/** the top `n` of score(b) over every broker (score > 0; ties by broker code) */
function topOf(R: FlowRows, n: number, score: (b: number) => number): number[] {
  const ids: number[] = [], sc: number[] = [];
  for (let b = 0; b < R.brokers.length; b++) {
    const s = score(b);
    if (!(s > 0) || ids.length === n && s <= sc[n - 1] && !(s === sc[n - 1] && R.brokers[b] < R.brokers[ids[n - 1]])) continue;
    let j = ids.length;
    while (j > 0 && (sc[j - 1] < s || sc[j - 1] === s && R.brokers[b] < R.brokers[ids[j - 1]])) j--;
    ids.splice(j, 0, b); sc.splice(j, 0, s);
    if (ids.length > n) { ids.pop(); sc.pop() }
  }
  return ids;
}
/** the cohort at t for window a..t: null = every broker. Kept per grid, so the parts of one indicator (FL09 reads four
    others) and a recompute with the same rule rank each window once. */
function cohort(g: Grid, R: FlowRows, p: FlowParams, a: number, t: number): number[] | null {
  const scope = p.scope ?? 'topn';
  if (scope === 'all') return null;
  const sel = scope === 'selected', key = sel ? 'sel|' + [...(p.brokers || [])].sort().join() : `top|${int(p.top, 3)}|${p.rank || 'net_buy'}`;
  let memo = g.cohorts.get(key); if (!memo) g.cohorts.set(key, memo = new Map());
  const at = sel ? -1 : a * (g.N + 1) + t;
  let C = memo.get(at);
  if (C === undefined) {
    if (sel) { const want = new Set<string>(p.brokers || []); C = R.brokers.map((b, k) => want.has(b) ? k : -1).filter(k => k >= 0) }
    else C = topBrokers(g, R, a, t, int(p.top, 3), p.rank || 'net_buy');
    memo.set(at, C);
  }
  return C;
}
/** sum of measure m over the cohort and window */
const cw = (g: Grid, C: number[] | null, m: Measure, a: number, t: number) => C ? C.reduce((s, b) => s + bw(g, m, b, a, t), 0) : aw(g, m, a, t);
/** the cohort's rows in the window lack transaction counts */
const cmiss = (g: Grid, C: number[] | null, a: number, t: number) => (C ? C.reduce((s, b) => s + bw(g, 'miss', b, a, t), 0) : aw(g, 'miss', a, t)) > 0;
/** one candle's sum of measure m over the cohort */
const cc = (g: Grid, C: number[] | null, m: Measure, k: number) => C ? C.reduce((s, b) => s + bw(g, m, b, k, k), 0) : aw(g, m, k, k);

const boardOnly = (p: FlowParams) => grid0(p, true);
let ctxRows: FlowRows;                                    // set by each call (the functions below are synchronous)
function grid0(p: FlowParams, boardsOnly = false) { return grid(ctxRows, p.boards ?? null, boardsOnly ? null : p.investors ?? null) }

/** For every candle: fn(window start, candle) when the window is valid, else null. */
function each(R: FlowRows, W: number, fn: (a: number, t: number) => Num): Series {
  const out = series(R.N);
  for (let t = 0; t < R.N; t++) { const a = win(R, t, W); if (a !== null) out[t] = fn(a, t) }
  return out;
}

/* ---- side indicators (FL01-FL05, FL13): Buy, Sell or Both ---- */
function sided(p: FlowParams, buy: () => Series, sell: () => Series): FlowOut {
  const side = p.side || 'buy';
  return side === 'both' ? { buy:buy(), sell:sell() } : side === 'sell' ? { sell:sell() } : { buy:buy() };
}

/* ---- percentile (mid-rank, prior-only) ---- */
export function percentile(x: Series, baseline: number): Series {
  const out = series(x.length);
  let first = -1;
  for (let t = 0; t < x.length; t++) if (x[t] !== null) { first = t; break }
  if (first < 0) return out;
  for (let t = 0; t < x.length; t++) {
    const v = x[t];
    if (v === null || t - baseline < first) continue;
    let lt = 0, eq = 0, n = 0;
    for (let k = t - baseline; k < t; k++) { const w = x[k]; if (w === null) continue; n++; if (w < v) lt++; else if (w === v) eq++ }
    if (n) out[t] = 100 * (lt + 0.5 * eq) / n;
  }
  return out;
}

/* ---- the indicators ---- */
type Fn = (ctx: FlowContext, p: FlowParams) => FlowOut;
const W = (p: FlowParams, d = 1) => int(p.window, d);

function sizeLot(ctx: FlowContext, p: FlowParams, side: 'buy' | 'sell'): Series {
  const R = ctx.rows, g = grid0(p), [l, f] = side === 'buy' ? ['bl', 'bf'] as const : ['sl', 'sf'] as const;
  return each(R, W(p), (a, t) => { const C = cohort(g, R, p, a, t); return cmiss(g, C, a, t) ? null : div(cw(g, C, l, a, t), cw(g, C, f, a, t)) });
}
function sizeVsMarket(ctx: FlowContext, p: FlowParams, side: 'buy' | 'sell'): Series {
  const R = ctx.rows, g = grid0(p), [l, f] = side === 'buy' ? ['bl', 'bf'] as const : ['sl', 'sf'] as const;
  return each(R, W(p), (a, t) => {
    const C = cohort(g, R, p, a, t);
    if (cmiss(g, C, a, t) || cmiss(g, null, a, t)) return null;
    const vs = div(cw(g, C, l, a, t), aw(g, l, a, t)), fs = div(cw(g, C, f, a, t), aw(g, f, a, t));
    return vs === null || fs === null ? null : div(vs, fs);
  });
}
function marketShare(ctx: FlowContext, p: FlowParams): Series {        // FL07
  const R = ctx.rows, g = grid0(p), d = p.denom === 'filter' ? g : boardOnly(p);
  return each(R, W(p), (a, t) => { const C = cohort(g, R, p, a, t), v = div(cw(g, C, 'bl', a, t), aw(d, 'bl', a, t)); return v === null ? null : 100 * v });
}
function flowTurnover(ctx: FlowContext, p: FlowParams): Series {       // FL11
  const R = ctx.rows, g = grid0(p), d = p.denom === 'filter' ? g : boardOnly(p);
  return each(R, W(p), (a, t) => { const C = cohort(g, R, p, a, t), v = div(cw(g, C, 'bv', a, t) - cw(g, C, 'sv', a, t), aw(d, 'bv', a, t)); return v === null ? null : 100 * v });
}
function imbalance(ctx: FlowContext, p: FlowParams): Series {          // FL10
  const R = ctx.rows, g = grid0(p);
  return each(R, W(p), (a, t) => { const C = cohort(g, R, p, a, t); if (cmiss(g, C, a, t)) return null; const bf = cw(g, C, 'bf', a, t), sf = cw(g, C, 'sf', a, t); return div(bf - sf, bf + sf) });
}
function hhi(ctx: FlowContext, p: FlowParams, m: 'bl' | 'sl'): Series {  // FL13
  const R = ctx.rows, g = grid0(p);
  return each(R, W(p), (a, t) => {
    const tot = aw(g, m, a, t); if (!tot) return null;
    let s = 0; for (let b = 0; b < g.B; b++) { const x = bw(g, m, b, a, t) / tot; s += x * x }
    return s;
  });
}
/** bandar: the N largest net buyers and net sellers over a..t; [sum of buyers' net, sum of sellers' net (negative)] */
function bandar(g: Grid, R: FlowRows, a: number, t: number, n: number): [number, number] {
  const nets = new Float64Array(g.B);                    // each broker's net once, for both sides
  for (let b = 0; b < g.B; b++) nets[b] = bw(g, 'bv', b, a, t) - bw(g, 'sv', b, a, t);
  const buy = topOf(R, n, b => nets[b]), sell = topOf(R, n, b => -nets[b]);
  return [buy.reduce((s, b) => s + nets[b], 0), sell.reduce((s, b) => s + nets[b], 0)];
}
function balancePct(ctx: FlowContext, p: FlowParams, Wd: number): Series {  // FL24
  const R = ctx.rows, g = grid0(p);
  return each(R, W(p, Wd), (a, t) => { const [nb, ns] = bandar(g, R, a, t, int(p.top, 3)), v = div(nb + ns, aw(g, 'bv', a, t)); return v === null ? null : 100 * v });
}
function rollingVwap(ctx: FlowContext, p: FlowParams, Wd: number): Series {  // FL17
  const R = ctx.rows, g = grid0(p);
  return each(R, W(p, Wd), (a, t) => { const C = cohort(g, R, p, a, t); return div(cw(g, C, 'bv', a, t), 100 * cw(g, C, 'bl', a, t)) });
}
/** the anchor candle: the first candle on or after the anchor date */
function anchorAt(ctx: FlowContext, anchor: any): number {
  const d = typeof anchor === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(anchor) ? anchor : ctx.dates[0];
  const i = ctx.dates.findIndex(x => x >= d);
  return i < 0 ? ctx.rows.N : i;
}
/** the frozen cohort of FL18-FL20: ranked once from the anchor to the last candle with data */
function frozen(ctx: FlowContext, p: FlowParams, g: Grid, a: number): number[] | null {
  const R = ctx.rows, scope = p.scope ?? 'topn';
  if (scope !== 'topn') return cohort(g, R, p, a, a);
  const last = lastData(R);
  return last < a ? [] : topBrokers(g, R, a, last, int(p.top, 3), p.rank || 'net_buy');
}
function anchoredVwap(ctx: FlowContext, p: FlowParams): Series {        // FL18
  const R = ctx.rows, g = grid0(p), a = anchorAt(ctx, p.anchor), C = frozen(ctx, p, g, a), out = series(R.N);
  for (let t = a; t < R.N; t++) if (R.has[t]) out[t] = div(cw(g, C, 'bv', a, t), 100 * cw(g, C, 'bl', a, t));
  return out;
}
function impliedCost(ctx: FlowContext, p: FlowParams): Series {         // FL19
  const R = ctx.rows, g = grid0(p), a = anchorAt(ctx, p.anchor), C = frozen(ctx, p, g, a), out = series(R.N);
  let Q = 0, K = 0;
  for (let k = a; k < R.N; k++) {
    if (!R.has[k]) continue;
    const bl = cc(g, C, 'bl', k), sl = cc(g, C, 'sl', k), bv = cc(g, C, 'bv', k), q = bl - sl;
    if (q > 0) { const price = bv / bl; K = Q <= 0 ? Math.max(Q + q, 0) * price : K + q * price }
    else if (q < 0 && Q > 0) K = K * Math.max(Q + q, 0) / Q;
    Q += q;
    out[k] = Q > 0 ? K / (100 * Q) : null;
  }
  return out;
}
const distance = (close: Series, ref: Series): Series => ref.map((r, t) => { const c = close[t]; return r === null || c === null || !r ? null : 100 * (c / r - 1) });

/** FL23 default brokers: the three largest net buyers (all boards and investors) over the last 20 candles with data */
export function defaultInventoryBrokers(R: FlowRows): string[] {
  const g = grid(R, null, null), idx: number[] = [];
  for (let t = R.N - 1; t >= 0 && idx.length < 20; t--) if (R.has[t]) idx.push(t);
  if (!idx.length) return [];
  return topBrokers(g, R, idx[idx.length - 1], idx[0], 3, 'net_buy').map(b => R.brokers[b]);
}
/** FL34 default lists: the brokers of a classification */
export const classBrokers = (ctx: FlowContext, cls: string) => Object.keys(ctx.classification).filter(b => ctx.classification[b] === cls).sort();
const resolveBrokers = (ctx: FlowContext, v: any, fallback: () => string[]): string[] =>
  Array.isArray(v) ? v : typeof v === 'string' && v.startsWith('class:') ? classBrokers(ctx, v.slice(6)) : fallback();

export const FLOW: Record<string, Fn> = {
  FL01:(c, p) => sided(p, () => sizeLot(c, p, 'buy'), () => sizeLot(c, p, 'sell')),
  FL02:(c, p) => {
    const R = c.rows, g = grid0(p), one = (v: Measure, f: Measure) => each(R, W(p), (a, t) => { const C = cohort(g, R, p, a, t); return cmiss(g, C, a, t) ? null : div(cw(g, C, v, a, t), cw(g, C, f, a, t)) });
    return sided(p, () => one('bv', 'bf'), () => one('sv', 'sf'));
  },
  FL03:(c, p) => {
    const R = c.rows, g = grid0(p), one = (m: Measure) => each(R, W(p), (a, t) => { const v = div(cw(g, cohort(g, R, p, a, t), m, a, t), aw(g, m, a, t)); return v === null ? null : 100 * v });
    return sided(p, () => one('bl'), () => one('sl'));
  },
  FL04:(c, p) => {
    const R = c.rows, g = grid0(p), one = (m: Measure) => each(R, W(p), (a, t) => { const C = cohort(g, R, p, a, t); if (cmiss(g, null, a, t)) return null; const v = div(cw(g, C, m, a, t), aw(g, m, a, t)); return v === null ? null : 100 * v });
    return sided(p, () => one('bf'), () => one('sf'));
  },
  FL05:(c, p) => sided(p, () => sizeVsMarket(c, p, 'buy'), () => sizeVsMarket(c, p, 'sell')),
  FL06:(c, p) => {
    const R = c.rows, g = grid0(p);
    return { ratio:each(R, W(p), (a, t) => {
      const C = cohort(g, R, p, a, t); if (cmiss(g, C, a, t)) return null;
      const b = div(cw(g, C, 'bl', a, t), cw(g, C, 'bf', a, t)), s = div(cw(g, C, 'sl', a, t), cw(g, C, 'sf', a, t));
      return b === null || s === null ? null : div(b, s);
    }) };
  },
  FL07:(c, p) => ({ value:marketShare(c, p) }),
  FL08:(c, p) => ({ value:percentile(sizeLot(c, p, p.side === 'sell' ? 'sell' : 'buy'), int(p.baseline, 250)) }),
  FL09:(c, p) => {
    const pct = percentile(sizeLot(c, p, 'buy'), int(p.baseline, 250)), ratio = sizeVsMarket(c, p, 'buy');
    const part = marketShare(c, { ...p, denom:'board' }), flow = flowTurnover(c, { ...p, denom:'board' }), imb = p.use_imb ? imbalance(c, p) : null;
    return { value:pct.map((x, t) => {
      const ins = [x, ratio[t], part[t], flow[t], ...(imb ? [imb[t]] : [])];
      if (ins.some(v => v === null)) return null;
      const ok = atLeast(x!, Number(p.pct_min)) && atLeast(ratio[t]!, Number(p.ratio_min)) && atLeast(part[t]!, Number(p.part_min))
        && above(flow[t]!, Number(p.flow_min)) && (!imb || atLeast(imb[t]!, Number(p.imb_min)));
      return ok ? 1 : 0;
    }) };
  },
  FL10:(c, p) => ({ value:imbalance(c, p) }),
  FL11:(c, p) => ({ value:flowTurnover(c, p) }),
  FL12:(c, p) => {
    const R = c.rows, g = grid0(p), w = W(p, 5);
    return { value:each(R, w, (a, t) => { const C = cohort(g, R, p, a, t); let n = 0; for (let k = a; k <= t; k++) if (cc(g, C, 'bv', k) - cc(g, C, 'sv', k) > 0) n++; return 100 * n / w }) };
  },
  FL13:(c, p) => sided(p, () => hhi(c, p, 'bl'), () => hhi(c, p, 'sl')),
  FL14:(c, p) => { const b = hhi(c, p, 'bl'), s = hhi(c, p, 'sl'); return { asym:b.map((x, t) => x === null || s[t] === null ? null : x - s[t]!) } },
  FL15:(c, p) => {
    const R = c.rows, g = grid0(p);
    return { value:each(R, W(p), (a, t) => { const top = topBrokers(g, R, a, t, int(p.top, 3), 'gross_buy_lots'), v = div(top.reduce((s, b) => s + bw(g, 'bl', b, a, t), 0), aw(g, 'bl', a, t)); return v === null ? null : 100 * v }) };
  },
  FL16:(c, p) => {
    const R = c.rows, g = grid0(p);
    return { value:each(R, W(p), (a, t) => {
      const pos: number[] = [];
      for (let b = 0; b < g.B; b++) { const n = bw(g, 'bv', b, a, t) - bw(g, 'sv', b, a, t); if (n > 0) pos.push(n) }
      pos.sort((x, y) => y - x);
      const all = pos.reduce((s, x) => s + x, 0), top = pos.slice(0, int(p.top, 3)).reduce((s, x) => s + x, 0), v = div(top, all);
      return v === null ? null : 100 * v;
    }) };
  },
  FL17:(c, p) => ({ value:rollingVwap(c, p, 20) }),
  FL18:(c, p) => ({ value:anchoredVwap(c, p) }),
  FL19:(c, p) => ({ value:impliedCost(c, p) }),
  FL20:(c, p) => ({ value:distance(c.close, impliedCost(c, p)) }),
  FL21:(c, p) => ({ value:percentile(flowTurnover(c, p), int(p.baseline, 250)) }),
  FL22:(c, p) => {
    const R = c.rows, g = grid0(p);
    return { value:each(R, W(p), (a, t) => {
      let active = 0, buyers = 0;
      for (let b = 0; b < g.B; b++) { const bv = bw(g, 'bv', b, a, t), sv = bw(g, 'sv', b, a, t); if (bv > 0 || sv > 0) { active++; if (bv - sv > 0) buyers++ } }
      return active ? 100 * buyers / active : null;
    }) };
  },
  FL23:(c, p) => {
    const R = c.rows, g = grid0(p), brokers = resolveBrokers(c, p.brokers, () => defaultInventoryBrokers(R)).slice(0, 5);
    const s = anchorAt(c, p.start), value = p.unit === 'value', daily = p.view === 'daily', out: FlowOut = {};
    const lines = brokers.map(code => {
      const b = R.brokers.indexOf(code), o = series(R.N); let acc = 0;
      for (let k = s; k < R.N; k++) {
        if (!R.has[k]) continue;
        const d = b < 0 ? 0 : value ? bw(g, 'bv', b, k, k) - bw(g, 'sv', b, k, k) : bw(g, 'bl', b, k, k) - bw(g, 'sl', b, k, k);
        acc += d; o[k] = daily ? d : acc;
      }
      out[code] = o;
      return o;
    });
    if (p.total) out.total = series(R.N).map((_, k) => lines.length && lines.every(l => l[k] !== null) ? lines.reduce((x, l) => x + (l[k] as number), 0) : null);
    return out;
  },
  FL24:(c, p) => ({ value:balancePct(c, p, 10) }),
  FL25:(c, p) => {
    const R = c.rows, g = grid0(p);
    return { value:each(R, W(p, 10), (a, t) => { const [nb, ns] = bandar(g, R, a, t, int(p.top, 3)); return nb + ns }) };
  },
  FL26:(c, p) => {
    const R = c.rows, g = grid0(p), L = W(p, 60), out = series(R.N);
    let prev = 0;
    for (let t = 0; t < R.N; t++) {
      let C: number[] | null = null;
      if ((p.scope ?? 'all') === 'topn') { const a = win(R, t, L); if (a === null) { prev = 0; continue } C = cohort(g, R, p, a, t) }
      else if (!R.has[t]) { prev = 0; continue }
      else C = cohort(g, R, p, t, t);
      const n = cc(g, C, 'bv', t) - cc(g, C, 'sv', t);
      const s = n > 0 ? (prev > 0 ? prev + 1 : 1) : n < 0 ? (prev < 0 ? prev - 1 : -1) : 0;
      prev = Math.max(-L, Math.min(L, s));
      out[t] = prev;
    }
    return { value:out };
  },
  FL27:(c, p) => {
    const r = int(p.recent, 5), bsl = int(p.baseline, 20), volx = Number(p.volx), move = Number(p.move), out = series(c.rows.N);
    const mean = (a: number, b: number) => { let s = 0; for (let k = a; k <= b; k++) { const v = c.volume[k]; if (v === null) return null; s += v } return s / (b - a + 1) };
    for (let t = r + bsl - 1; t < c.rows.N; t++) {
      const s1 = mean(t - r + 1, t), s0 = mean(t - r - bsl + 1, t - r), c1 = c.close[t], c0 = c.close[t - r];
      if (s1 === null || s0 === null || c1 === null || c0 === null || !s0 || !c0) continue;
      out[t] = atLeast(s1 / s0, volx) && atMost(100 * Math.abs(c1 / c0 - 1), move) ? 1 : 0;
    }
    return { value:out };
  },
  FL28:(c, p) => {
    const n = int(p.window, 20), out = series(c.rows.N);
    for (let t = n - 1; t < c.rows.N; t++) {
      let s = 0, ok = true;
      for (let k = t - n + 1; k <= t; k++) { const cl = c.close[k], v = c.volume[k]; if (cl === null || v === null) { ok = false; break } s += cl * v }
      if (ok) out[t] = s / n;
    }
    return { value:out };
  },
  FL29:(c, p) => {
    const R = c.rows, g = grid0(p), n = int(p.top, 3), D = W(p, 20), th = Number(p.threshold) || 0;
    const bal = series(R.N).map((_, k) => { if (!R.has[k]) return null; const [nb, ns] = bandar(g, R, k, k, n), v = div(nb + ns, aw(g, 'bv', k, k)); return v === null ? null : 100 * v });
    return { value:each(R, D, (a, t) => { let k2 = 0; for (let k = a; k <= t; k++) if (bal[k] !== null && above(bal[k]!, th)) k2++; return 100 * k2 / D }) };
  },
  FL30:(c, p) => {
    const R = c.rows, all = grid(R, null, p.investors ?? null), cross = grid(R, ['Nego', 'Cash'], p.investors ?? null);
    return { value:each(R, W(p, 20), (a, t) => { const v = div(aw(cross, 'bv', a, t), aw(all, 'bv', a, t)); return v === null ? null : 100 * v }) };
  },
  FL31:(c, p) => {
    const N = c.rows.N, w = W(p, 20), per = new Float64Array(N);
    for (const r of c.insider) if (r.t >= 0 && r.t < N) per[r.t] += r.value;
    const out = series(N);
    for (let t = w - 1; t < N; t++) { let s = 0; for (let k = t - w + 1; k <= t; k++) s += per[k]; out[t] = s }
    return { value:out };
  },
  FL32:(c, p) => {
    const R = c.rows, g = grid0(p), bsl = int(p.baseline, 20);
    return { value:each(R, bsl + 1, (a, t) => {
      if (aw(g, 'miss', a, t) > 0) return null;
      return div(aw(g, 'bf', t, t), aw(g, 'bf', a, t - 1) / bsl);
    }) };
  },
  FL33:(c, p) => {
    const R = c.rows, g = grid0(p), r = int(p.recent, 5), bsl = int(p.baseline, 20);
    return { value:each(R, r + bsl, (a, t) => {
      if (aw(g, 'miss', a, t) > 0) return null;
      const now = div(aw(g, 'bv', t - r + 1, t), aw(g, 'bf', t - r + 1, t)), before = div(aw(g, 'bv', a, t - r), aw(g, 'bf', a, t - r));
      return now === null || before === null || !before ? null : 100 * (now / before - 1);
    }) };
  },
  FL34:(c, p) => {
    const R = c.rows, g = grid0(p);
    const inst = new Set(resolveBrokers(c, p.inst, () => classBrokers(c, 'Institutional-heavy'))), retail = new Set(resolveBrokers(c, p.retail, () => classBrokers(c, 'Retail-heavy')));
    /* no list (the classification has not arrived) or a broker in both lists: no value, never a 0 */
    if (!inst.size && !retail.size || [...inst].some(b => retail.has(b))) return { value:series(R.N) };
    const idx = (s: Set<string>) => R.brokers.map((b, k) => s.has(b) ? k : -1).filter(k => k >= 0), I = idx(inst), Rt = idx(retail);
    return { value:each(R, W(p, 20), (a, t) => {
      const net = (C: number[]) => cw(g, C, 'bv', a, t) - cw(g, C, 'sv', a, t), v = div(net(I) - net(Rt), aw(g, 'bv', a, t));
      return v === null ? null : 100 * v;
    }) };
  },
  FL35:(c, p) => {
    const R = c.rows, g = grid0(p), D = W(p, 20);
    return { value:each(R, D, (a, t) => {
      const [b] = topBrokers(g, R, a, t, 1, 'net_buy'); if (b === undefined) return null;
      let n = 0; for (let k = a; k <= t; k++) if (bw(g, 'bv', b, k, k) - bw(g, 'sv', b, k, k) > 0) n++;
      return 100 * n / D;
    }) };
  },
  FL36:(c, p) => {
    const R = c.rows, g = grid0(p), d = boardOnly(p);
    return { value:each(R, W(p, 20), (a, t) => { const C = cohort(g, R, p, a, t), v = div(cw(g, C, 'bv', a, t) + cw(g, C, 'sv', a, t), 2 * aw(d, 'bv', a, t)); return v === null ? null : 100 * v }) };
  },
  FL37:(c, p) => {
    const R = c.rows, g = grid0(p);
    const x = each(R, W(p, 20), (a, t) => { const C = cohort(g, R, p, a, t); return cw(g, C, 'bv', a, t) - cw(g, C, 'sv', a, t) });
    return { value:percentile(x, int(p.baseline, 250)) };
  },
  FL38:(c, p) => {
    const R = c.rows, g = grid0(p);
    return { value:each(R, W(p, 20), (a, t) => {
      const pos: number[] = [];
      for (let b = 0; b < g.B; b++) { const n = bw(g, 'bv', b, a, t) - bw(g, 'sv', b, a, t); if (n > 0) pos.push(n) }
      const all = pos.reduce((s, x) => s + x, 0); if (!all) return null;
      return pos.reduce((s, x) => s + (x / all) ** 2, 0);
    }) };
  },
  FL39:(c, p) => ({ value:distance(c.close, rollingVwap(c, p, 10)) }),
};

for (const id of Object.keys(FLOW)) { const fn = FLOW[id]; FLOW[id] = (c, p) => { ctxRows = c.rows; return fn(c, p) } }

/** Run one indicator; an unknown id answers no output. */
export function computeFlow(id: string, ctx: FlowContext, params: FlowParams): FlowOut {
  const fn = FLOW[id];
  return fn ? fn(ctx, params) : {};
}
