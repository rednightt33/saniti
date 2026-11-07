/* The Screener's versions of flow indicators and its own flow entries (EXEC-SCREENER-FLOW-CANDLES P5b; the contract is
   verification/screener/P5_FLOW.md section 3; decisions in EXEC.md: B the FL23 screener version, D and E the anchor N
   sessions back, "Rumus lama" the old formulas kept as screener entries). Every Terminal figure here is still the
   Terminal's flow.ts computeFlow, called on the candles the version names; what the Terminal does not compute is a small
   pure function below with its formula, each tested against a brute-force recomputation
   (tests/core/flow-screener.test.ts). The candles, the window rule and the null rule are the Terminal's
   (verification/terminal_api/flow_indicators/FORMULAS.md section 2): a value needs its candle to have broker data and
   its sessions to start at or after the first candle with broker data.
   Pure module (no DOM, no Node API); flowmetrics.ts calls it on the window's context and on its depth probe. */
import { atLeast, atMost, boardIndex, computeFlow, investorIndex } from '../../../terminal/src/calc/flow.ts';
import type { FlowContext, FlowOut, FlowRows, Num } from '../../../terminal/src/calc/flow.ts';

type Series = Num[];
/** computeFlow, or the caller's memoized computeFlow on the same context (flowmetrics.ts: one call per ticker, id and
    parameters). */
export type FlowCall = (id: string, ctx: FlowContext, params: Record<string, unknown>) => FlowOut;

const firsts = new WeakMap<FlowRows, number>();
/** The first candle with broker data (flow.ts firstData), R.N when none. */
export function firstCandle(R: FlowRows): number {
  let f = firsts.get(R);
  if (f === undefined) { f = R.N; for (let t = 0; t < R.N; t++) if (R.has[t]) { f = t; break } firsts.set(R, f) }
  return f;
}

const ordered = new WeakMap<FlowRows, boolean>();
/** The rows a..b (b exclusive) that can hold candles lo..hi: found by bisection when the rows are in candle order (as
    the worker's store and flowRows of dated rows give them), else every row. */
function rowRange(R: FlowRows, lo: number, hi: number): [number, number] {
  let o = ordered.get(R);
  if (o === undefined) { o = true; for (let k = 1; k < R.n && o; k++) if (R.t[k] < R.t[k - 1]) o = false; ordered.set(R, o) }
  if (!o) return [0, R.n];
  const bound = (x: number) => { let a = 0, b = R.n; while (a < b) { const h = (a + b) >>> 1; if (R.t[h] < x) a = h + 1; else b = h } return a };
  return [bound(lo), bound(hi + 1)];
}
/** The context of candles lo..hi of `c`, as flow.ts flowRows builds it from the rows of those candles only: the rows in
    their order with their candle less lo, the brokers the sorted codes of those rows (R.brokers is sorted, so a filter
    keeps the order), the same values, has from the rows; dates, close and volume of those candles; the same
    classification. It equals flowRows on the same rows (tests/core/flow-screener.test.ts). */
export function sliceContext(c: FlowContext, lo: number, hi: number): FlowContext {
  const R = c.rows, N = hi - lo + 1, used = new Uint8Array(R.brokers.length), [k0, k1] = rowRange(R, lo, hi);
  let n = 0;
  for (let k = k0; k < k1; k++) if (R.t[k] >= lo && R.t[k] <= hi) { n++; used[R.b[k]] = 1 }
  const map = new Int32Array(R.brokers.length).fill(-1), brokers: string[] = [];
  for (let j = 0; j < R.brokers.length; j++) if (used[j]) { map[j] = brokers.length; brokers.push(R.brokers[j]) }
  const S: FlowRows = { n, N, t: new Int32Array(n), b: new Uint16Array(n), inv: new Uint8Array(n), brd: new Uint8Array(n),
    bv: new Float64Array(n), sv: new Float64Array(n), bl: new Float64Array(n), sl: new Float64Array(n), bf: new Float64Array(n), sf: new Float64Array(n),
    brokers, has: new Uint8Array(N) };
  let j = 0;
  for (let k = k0; k < k1; k++) {
    const t = R.t[k];
    if (t < lo || t > hi) continue;
    S.t[j] = t - lo; S.b[j] = map[R.b[k]]; S.inv[j] = R.inv[k]; S.brd[j] = R.brd[k];
    S.bv[j] = R.bv[k]; S.sv[j] = R.sv[k]; S.bl[j] = R.bl[k]; S.sl[j] = R.sl[k]; S.bf[j] = R.bf[k]; S.sf[j] = R.sf[k];
    S.has[t - lo] = 1; j++;
  }
  return { rows: S, dates: c.dates.slice(lo, hi + 1), close: c.close.slice(lo, hi + 1), volume: c.volume.slice(lo, hi + 1),
    insider: c.insider.filter(r => r.t >= lo && r.t <= hi).map(r => ({ t: r.t - lo, value: r.value })), classification: c.classification,
    ...(c.index ? { index: true } : {}) };
}

/* ---- FL18, FL19, FL20, FL44, FL45 with the anchor N sessions back (decisions D, E) ---------------------------------- */

/** The anchored indicator `id` with its anchor `n` sessions before each candle: at candle s, flow.ts computeFlow on the
    candles s - n .. s (sliceContext) with the anchor date of candle s - n, read at s. So the frozen Top-N cohort is
    ranked on the candles up to s only, as the Terminal ranks it when its last candle is s (no look-ahead, FORMULAS.md
    Reviewer A, A8); nothing before the anchor is read by these indicators, so the value equals computeFlow on every
    candle up to s with that anchor (the test holds the two equal). Missing on a candle without broker data and when
    s - n is before the first candle with broker data (the window rule). It is anchoredAt on every candle (flowmetrics.ts
    goes through its memo of anchoredAt, one per ticker, indicator, parameters and candle, so the full series and the
    lazy one share their computeFlow calls). */
export function anchoredSeries(id: string, c: FlowContext, params: Record<string, unknown>, n: number, output: string): Series {
  return Array.from({ length: c.rows.N }, (_, s) => anchoredAt(id, c, params, n, output, s));
}
/** The anchored value at candle s alone: computeFlow on the candles s - n .. s (sliceContext) with the anchor date of
    candle s - n, read at s; null without a computeFlow call on a candle without broker data or before n sessions of
    data. Each slice is its own computeFlow (never a memo keyed by the anchor date: two anchors can name one date on
    different slices). */
export function anchoredAt(id: string, c: FlowContext, params: Record<string, unknown>, n: number, output: string, s: number): Num {
  const R = c.rows;
  if (s < n || s >= R.N || !R.has[s] || s - n < firstCandle(R)) return null;
  const v = computeFlow(id, sliceContext(c, s - n, s), { ...params, anchor: c.dates[s - n] })[output];
  return v && typeof v[n] === 'number' ? v[n] : null;
}
/** The anchored series where a condition reads it (P5b cost; flowmetrics.ts resolveFlow with a reach): the candles
    last - reach .. last, last = the last candle with broker data (a condition on a flow series is evaluated there, P10
    a, and reads `reach` sessions before it: its window test's length, an event's within, its operators' N), each value
    the full series' (anchoredAt); every other candle is left out (null). When a computed candle with broker data has no
    value, the series' first value is found too (scanning from the first candle that can have one), so a cell that is
    n/a there names the same reason as on the full series (evaluate.ts naReason reads the first valid bar). */
export function anchoredLazy(c: FlowContext, n: number, reach: number, at: (s: number) => Num): Series {
  const R = c.rows, out: Series = new Array(R.N).fill(null);
  let last = R.N - 1;
  while (last >= 0 && !R.has[last]) last--;
  let gap = false;
  for (let s = Math.max(0, last - reach); s <= last; s++) { out[s] = at(s); if (out[s] === null && R.has[s]) gap = true }
  if (gap) for (let s = firstCandle(R) + n; s < R.N; s++) { const v = at(s); if (v !== null) { out[s] = v; break } }
  return out;
}

/* ---- FL23 screener version (decision B) ------------------------------------------------------------------------------ */

/** The parameters of the Screener's Broker Inventory (flow-kinds.json FL23 screener). */
export interface InventorySetup {
  holders: 'top' | 'selected' | 'all'; brokers: readonly string[]; top: number; unit: 'lot' | 'value';
  series: 'cum' | 'daily' | 'norm'; lookback: number; boards: readonly string[]; investors: readonly string[];
  move: 'up' | 'down'; move_min: number;
}
/** Every investor's traded value (gross buy, unit value) or traded lots (bought lots, unit lot) of each candle on the
    boards: flow.ts TBV ("every investor's gross buy on the chosen boards", FORMULAS.md section 3) of one candle. */
export function tradedPerCandle(R: FlowRows, boards: readonly string[], unit: 'lot' | 'value'): Float64Array {
  const ok = new Set(boards.map(boardIndex)), col = unit === 'value' ? R.bv : R.bl, out = new Float64Array(R.N);
  for (let k = 0; k < R.n; k++) if (ok.has(R.brd[k])) out[R.t[k]] += col[k];
  return out;
}
/** The `k` codes with the largest positive score, the largest first, ties by broker code A-Z (flow.ts topOf's rule). */
export function topHolders(codes: readonly string[], score: ArrayLike<number>, k: number): number[] {
  const ids: number[] = [];
  for (let j = 0; j < codes.length; j++) if (score[j] > 0) ids.push(j);
  ids.sort((x, y) => score[y] - score[x] || (codes[x] < codes[y] ? -1 : codes[x] > codes[y] ? 1 : 0));
  return ids.slice(0, k);
}
/** Whether a holder's series moved by at least X in the direction: rose: above 0 and at least X; fell: below 0 and at
    most -X (flow.ts atLeast / atMost, the Terminal's threshold rule). */
const moved = (x: number, p: InventorySetup) => p.move === 'up' ? x > 0 && atLeast(x, p.move_min) : x < 0 && atMost(x, -p.move_min);
/** The Screener's Broker Inventory (decision B; OPERATORS.md section 4 row B) on a context, for every candle s:
    - per candidate broker b (the brokers named, or every broker of the context), d_b the Terminal's FL23 daily net (lots
      or rupiah, flow.ts FL23 view daily, five brokers per call as the Terminal draws them);
    - a_b(s) = d_b(s-L+1) + ... + d_b(s) in candle order over the candles with data: the Terminal's FL23 cumulative line
      started at candle s-L+1 (flow.ts FL23 adds the same daily nets in the same order, `acc += d`), the inventory over
      the lookback L;
    - c_b(s) = 100 x (a_b(s) / TV(s)), TV(s) = the traded value (or lots) of the L candles (tradedPerCandle);
    - the holders H(s): the K brokers with the largest positive a_b(s) (topHolders), the brokers named in their order, or
      every broker in code order;
    - value(s) = the sum over H(s) of a_b(s) (series a), of d_b(s) (series b), or 100 x (sum of a_b(s) / TV(s))
      (series c), each sum in holder order from 0 (flow.ts FL23 total);
    - count(s) = how many holders' series (a, b or c) moved by at least move_min in the direction (moved).
    Missing on a candle without broker data, when the lookback is read (series a and c, and Top-K holders) and s-L+1 is
    before the first candle with data, when no holder is left, and (series c) when TV(s) is 0. */
export function inventory(c: FlowContext, p: InventorySetup, call: FlowCall = computeFlow): { value: Series; count: Series } {
  const R = c.rows, N = R.N, L = p.lookback, first = firstCandle(R);
  const codes = p.holders === 'selected' ? [...p.brokers] : [...R.brokers];
  const daily: Series[] = [];
  for (let k = 0; k < codes.length; k += 5) {
    const batch = codes.slice(k, k + 5), out = call('FL23', c, { brokers: batch, unit: p.unit, view: 'daily', total: false, boards: [...p.boards], investors: [...p.investors] });
    for (const b of batch) daily.push(out[b]);
  }
  const tv = p.series === 'norm' ? tradedPerCandle(R, p.boards, p.unit) : null;
  const value: Series = new Array(N).fill(null), count: Series = new Array(N).fill(null), inv = new Float64Array(codes.length);
  const lookback = p.series !== 'daily' || p.holders === 'top';
  for (let s = 0; s < N; s++) {
    const a = s - L + 1;
    if (!R.has[s] || (lookback && a < first)) continue;
    if (lookback) for (let j = 0; j < codes.length; j++) {
      let acc = 0;
      for (let k = a; k <= s; k++) { const d = daily[j][k]; if (d !== null) acc += d }
      inv[j] = acc;
    }
    let T = 0;
    if (tv) { for (let k = a; k <= s; k++) T += tv[k]; if (T === 0) continue }
    const H = p.holders === 'top' ? topHolders(codes, inv, p.top) : codes.map((_, j) => j);
    if (!H.length) continue;
    const x = (j: number): number => p.series === 'daily' ? daily[j][s] as number : p.series === 'cum' ? inv[j] : 100 * (inv[j] / T);
    let v = 0, n = 0;
    for (const j of H) { v += p.series === 'daily' ? daily[j][s] as number : inv[j]; if (moved(x(j), p)) n++ }
    value[s] = p.series === 'norm' ? 100 * (v / T) : v;
    count[s] = n;
  }
  return { value, count };
}

/* ---- fnet: the foreign net in rupiah (old FL01, kept as a screener entry) ---------------------------------------------- */

/** fnet(t) = sum over the D candles t-D+1 .. t of (sum of bv) - (sum of sv) of the rows with investor type Foreign on the
    chosen boards (every board by default): the foreign investors' net buying in rupiah over D sessions (old FL01,
    AUDIT.md 16.5; no Terminal output gives it: FL37 holds it only before its percentile). Missing on a candle without
    broker data and when t-D+1 is before the first candle with data (the window rule); a candle with broker data but no
    foreign row adds 0. */
export function foreignNet(R: FlowRows, boards: readonly string[], D: number): Series {
  const foreign = investorIndex('Foreign'), ok = new Set(boards.map(boardIndex)), B = new Float64Array(R.N), S = new Float64Array(R.N);
  for (let k = 0; k < R.n; k++) if (R.inv[k] === foreign && ok.has(R.brd[k])) { B[R.t[k]] += R.bv[k]; S[R.t[k]] += R.sv[k] }
  const out: Series = new Array(R.N).fill(null), first = firstCandle(R);
  for (let t = 0; t < R.N; t++) {
    const a = t - D + 1;
    if (!R.has[t] || a < first) continue;
    let b = 0, s = 0;
    for (let k = a; k <= t; k++) { b += B[k]; s += S[k] }
    out[t] = b - s;
  }
  return out;
}
