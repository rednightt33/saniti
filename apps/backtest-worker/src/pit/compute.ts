/* EXEC-BACKTEST-REVAMP P4 (user 2026-11-15: "Kita include saja untuk seluruh indikator D ... indikator D ini akan hanya
   avail untuk admin saja"; "1A": the anchor or start date is required, set by the admin; K2 a for FL23): point-in-time
   versions of the eight Terminal Flow indicators that choose their brokers with the data up to the last candle (ERRORS
   M448: calc/flow.ts frozen, autoInventoryBrokers, defaultInventoryBrokers, loadersTable). Worker-only: no module the
   page imports reaches this folder (tests/worker-only.test.mjs, M456).

   One rule for all of them: on each candle t the brokers are chosen again from the rows from the anchor (or start) to t
   only, with the Terminal's own choice (score > 0, ties by broker code: calc/flow.ts topOf), and the value at t is the
   Terminal's formula for those brokers over the same span. On the last candle with data the choice is the Terminal's,
   so the value is the Terminal's; with brokers the user names there is no choice, so every value is the Terminal's.
   - FL18 / FL44: the cohort's buy (sell) value over 100 x its bought (sold) lots from the anchor to t;
     FL45 / FL20: 100 x (close / FL18 - 1) and 100 x (close / FL19 - 1);
   - FL19: the Terminal's implied cost of the cohort's position (calc/flow.ts impliedCost), walked from the anchor; the
     walk is redone from the anchor when the cohort changes, else it takes one more step;
   - FL23 (K2 a): the two largest net buyers and the largest net seller (value) from the start to t, chosen again each
     day (the Terminal's auto_c), their summed position since the start (or the day's net, view daily); named brokers
     are kept as named;
   - FL51: the top N loaders (net lots from the start to t), their cost (average buy price or the implied cost of the
     position each holds, the Terminal's loadersTable), the lots-weighted cost of all of them, the close's distance
     from it and the loaders' share of the lots added; one loader's cost by its rank as an option.
   Every value is empty before the anchor, on a candle without broker data, and on the first four candles with data
   from the anchor (a choice of brokers from one to four sessions is noise); `cohort_changed` is 1 on a candle whose
   brokers differ from the previous candle with a value. */
import type { FlowRows } from '../../../edge-bff/terminal/src/calc/flow.ts';
import { boardIndex, investorIndex } from '../../../edge-bff/terminal/src/calc/flow.ts';

export type Num = number | null;
export type Out = Record<string, Num[]>;
/** sessions with data from the anchor before the first value */
export const WARM_UP = 5;

/** The rows of the chosen boards and investor types, per candle: for each candle the brokers with a row and their sums. */
interface Days { B: number; N: number; start: Int32Array; b: Int32Array; bv: Float64Array; sv: Float64Array; bl: Float64Array; sl: Float64Array }
function days(R: FlowRows, boards: readonly string[], investors: readonly string[]): Days {
  const okB = new Set(boards.map(boardIndex)), okI = new Set(investors.map(investorIndex)), N = R.N, B = R.brokers.length;
  const per: Map<number, number[]>[] = Array.from({ length: N }, () => new Map());
  for (let k = 0; k < R.n; k++) {
    if (!okB.has(R.brd[k]) || !okI.has(R.inv[k])) continue;
    const m = per[R.t[k]], b = R.b[k];
    let s = m.get(b);
    if (!s) m.set(b, s = [0, 0, 0, 0]);
    s[0] += R.bv[k]; s[1] += R.sv[k]; s[2] += R.bl[k]; s[3] += R.sl[k];
  }
  let n = 0; for (const m of per) n += m.size;
  const d: Days = { B, N, start: new Int32Array(N + 1), b: new Int32Array(n), bv: new Float64Array(n), sv: new Float64Array(n), bl: new Float64Array(n), sl: new Float64Array(n) };
  let j = 0;
  for (let t = 0; t < N; t++) {
    d.start[t] = j;
    for (const [b, s] of [...per[t]].sort((x, y) => x[0] - y[0])) { d.b[j] = b; d.bv[j] = s[0]; d.sv[j] = s[1]; d.bl[j] = s[2]; d.sl[j] = s[3]; j++ }
  }
  d.start[N] = j;
  return d;
}

/** The top n brokers by score (score > 0; ties by broker code), the Terminal's topOf. */
function topOf(brokers: readonly string[], n: number, score: (b: number) => number): number[] {
  const ids: number[] = [], sc: number[] = [];
  for (let b = 0; b < brokers.length; b++) {
    const s = score(b);
    if (!(s > 0) || ids.length === n && s <= sc[n - 1] && !(s === sc[n - 1] && brokers[b] < brokers[ids[n - 1]])) continue;
    let j = ids.length;
    while (j > 0 && (sc[j - 1] < s || sc[j - 1] === s && brokers[b] < brokers[ids[j - 1]])) j--;
    ids.splice(j, 0, b); sc.splice(j, 0, s);
    if (ids.length > n) { ids.pop(); sc.pop() }
  }
  return ids;
}
const div = (a: number, b: number): Num => b !== 0 && Number.isFinite(a) && Number.isFinite(b) ? a / b : null;
const dist = (c: Num, r: Num): Num => r === null || c === null || !r ? null : 100 * (c / r - 1);
const blank = (N: number): Num[] => new Array(N).fill(null);
/** The first candle on or after the date (N when none). */
export function candleAt(dates: readonly string[], date: string): number {
  for (let i = 0; i < dates.length; i++) if (dates[i] >= date) return i;
  return dates.length;
}

/** Running sums per broker from the anchor, one candle at a time. */
class Running {
  bv: Float64Array; sv: Float64Array; bl: Float64Array; sl: Float64Array;
  constructor(B: number) { this.bv = new Float64Array(B); this.sv = new Float64Array(B); this.bl = new Float64Array(B); this.sl = new Float64Array(B) }
  add(d: Days, t: number) { for (let j = d.start[t]; j < d.start[t + 1]; j++) { const b = d.b[j]; this.bv[b] += d.bv[j]; this.sv[b] += d.sv[j]; this.bl[b] += d.bl[j]; this.sl[b] += d.sl[j] } }
}
const SCORE: Record<string, (r: Running, b: number) => number> = {
  net_buy: (r, b) => r.bv[b] - r.sv[b], gross_buy: (r, b) => r.bv[b], net_sell: (r, b) => r.sv[b] - r.bv[b],
};
const same = (a: readonly number[], b: readonly number[]) => a.length === b.length && a.every((x, k) => x === b[k]);

/** The implied cost step of calc/flow.ts impliedCost on one candle's cohort sums. */
function costStep(s: { Q: number; K: number }, bl: number, sl: number, bv: number): void {
  const q = bl - sl;
  if (q > 0) { const price = bv / bl; s.K = s.Q <= 0 ? Math.max(s.Q + q, 0) * price : s.K + q * price }
  else if (q < 0 && s.Q > 0) s.K = s.K * Math.max(s.Q + q, 0) / s.Q;
  s.Q += q;
}
/** One candle's sums over a set of brokers. */
function cohortDay(d: Days, t: number, inC: Uint8Array): [bv: number, sv: number, bl: number, sl: number] {
  let bv = 0, sv = 0, bl = 0, sl = 0;
  for (let j = d.start[t]; j < d.start[t + 1]; j++) if (inC[d.b[j]]) { bv += d.bv[j]; sv += d.sv[j]; bl += d.bl[j]; sl += d.sl[j] }
  return [bv, sv, bl, sl];
}

export interface AnchoredParams { anchor: string; scope: 'topn' | 'selected'; brokers: string[]; top: number; rank: 'net_buy' | 'gross_buy' | 'net_sell'; boards: string[]; investors: string[] }
/** FL18, FL19, FL20, FL44, FL45 and cohort_changed in one pass (one cohort per candle for the five). */
export function anchored(R: FlowRows, dates: readonly string[], close: readonly Num[], p: AnchoredParams): Record<'FL18' | 'FL19' | 'FL20' | 'FL44' | 'FL45' | 'cohort_changed', Num[]> {
  const N = R.N, d = days(R, p.boards, p.investors), a = candleAt(dates, p.anchor), run = new Running(d.B);
  const o = { FL18: blank(N), FL19: blank(N), FL20: blank(N), FL44: blank(N), FL45: blank(N), cohort_changed: blank(N) };
  const named = p.scope === 'selected' ? R.brokers.map((b, k) => p.brokers.includes(b) ? k : -1).filter(k => k >= 0) : null;
  let prev: number[] | null = null, seen = 0;
  const walk = { Q: 0, K: 0 }, inC = new Uint8Array(d.B);
  for (let t = a; t < N; t++) {
    run.add(d, t);
    if (!R.has[t]) continue;
    const C = named ?? topOf(R.brokers, p.top, b => SCORE[p.rank](run, b));
    if (!prev || !same(prev, C)) {
      // the cohort changed (or is the first): its implied cost walked again from the anchor up to t
      inC.fill(0); for (const b of C) inC[b] = 1;
      walk.Q = 0; walk.K = 0;
      for (let k = a; k <= t; k++) if (R.has[k]) { const [bv, , bl, sl] = cohortDay(d, k, inC); costStep(walk, bl, sl, bv) }
    } else { const [bv, , bl, sl] = cohortDay(d, t, inC); costStep(walk, bl, sl, bv) }
    const changed = prev !== null && !same(prev, C);
    prev = C;
    if (++seen < WARM_UP) continue;
    let BV = 0, BL = 0, SV = 0, SL = 0;
    for (const b of C) { BV += run.bv[b]; BL += run.bl[b]; SV += run.sv[b]; SL += run.sl[b] }
    o.FL18[t] = div(BV, 100 * BL); o.FL44[t] = div(SV, 100 * SL); o.FL45[t] = dist(close[t], o.FL18[t]);
    o.FL19[t] = walk.Q > 0 ? walk.K / (100 * walk.Q) : null; o.FL20[t] = dist(close[t], o.FL19[t]);
    o.cohort_changed[t] = +changed;
  }
  return o;
}

export interface InventoryParams { start: string; brokers: string[] | 'auto_c'; unit: 'lot' | 'value'; view: 'cum' | 'daily'; boards: string[]; investors: string[] }
/** FL23 (K2 a): the summed position of the brokers since the start (or the day's net), and cohort_changed. */
export function inventory(R: FlowRows, dates: readonly string[], p: InventoryParams): { total: Num[]; cohort_changed: Num[] } {
  const N = R.N, d = days(R, p.boards, p.investors), s = candleAt(dates, p.start), run = new Running(d.B);
  const total = blank(N), cohort_changed = blank(N);
  const named = Array.isArray(p.brokers) ? p.brokers.slice(0, 5).map(b => R.brokers.indexOf(b)) : null;
  const pos = (b: number) => b < 0 ? 0 : p.unit === 'value' ? run.bv[b] - run.sv[b] : run.bl[b] - run.sl[b];
  let prev: number[] | null = null, seen = 0;
  for (let t = s; t < N; t++) {
    run.add(d, t);
    if (!R.has[t]) continue;
    const C = named ?? [...topOf(R.brokers, 2, b => run.bv[b] - run.sv[b]), ...topOf(R.brokers, 1, b => run.sv[b] - run.bv[b])];
    const changed = prev !== null && !same(prev, C);
    prev = C;
    if (++seen < WARM_UP) continue;
    if (p.view === 'daily') {
      const inC = new Uint8Array(d.B); for (const b of C) if (b >= 0) inC[b] = 1;
      const [bv, sv, bl, sl] = cohortDay(d, t, inC);
      total[t] = C.length ? (p.unit === 'value' ? bv - sv : bl - sl) : null;
    } else total[t] = C.length ? C.reduce((x, b) => x + pos(b), 0) : null;
    cohort_changed[t] = +changed;
  }
  return { total, cohort_changed };
}

export interface LoadersParams { start: string; top: number; cost: 'avg' | 'model'; loader: number; boards: string[]; investors: string[] }
/** FL51: the loaders' cost (lots-weighted, or one loader's by rank), the close's distance from it, their share of the lots
    added, and cohort_changed. */
export function loaders(R: FlowRows, dates: readonly string[], close: readonly Num[], p: LoadersParams): { cost: Num[]; distance: Num[]; share: Num[]; cohort_changed: Num[] } {
  const N = R.N, d = days(R, p.boards, p.investors), s = candleAt(dates, p.start), run = new Running(d.B);
  const o = { cost: blank(N), distance: blank(N), share: blank(N), cohort_changed: blank(N) };
  const own = Array.from({ length: d.B }, () => ({ Q: 0, K: 0 }));             // each broker's implied cost walk (cost 'model')
  let prev: number[] | null = null, seen = 0;
  for (let t = s; t < N; t++) {
    run.add(d, t);
    if (!R.has[t]) continue;
    for (let j = d.start[t]; j < d.start[t + 1]; j++) { const b = d.b[j]; costStep(own[b], d.bl[j], d.sl[j], d.bv[j]) }
    const net = (b: number) => run.bl[b] - run.sl[b];
    const L = topOf(R.brokers, p.top, net);
    const changed = prev !== null && !same(prev, L);
    prev = L;
    if (++seen < WARM_UP) continue;
    const costOf = (b: number): Num => p.cost === 'model' ? (own[b].Q > 0 ? own[b].K / (100 * own[b].Q) : null) : (run.bl[b] > 0 ? run.bv[b] / (100 * run.bl[b]) : null);
    let cost: Num = null;
    if (p.loader >= 1) cost = L[p.loader - 1] === undefined ? null : costOf(L[p.loader - 1]);
    else {
      let w = 0, x = 0;
      for (const b of L) { const c = costOf(b), q = net(b); if (c !== null && q > 0) { w += q; x += q * c } }
      cost = w > 0 ? x / w : null;
    }
    let pos = 0; for (let b = 0; b < d.B; b++) if (net(b) > 0) pos += net(b);
    o.cost[t] = cost; o.distance[t] = dist(close[t], cost);
    o.share[t] = pos > 0 && L.length ? 100 * L.reduce((x, b) => x + net(b), 0) / pos : null;
    o.cohort_changed[t] = +changed;
  }
  return o;
}
