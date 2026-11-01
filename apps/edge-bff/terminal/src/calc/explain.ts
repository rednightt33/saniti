/* ==========================================================================
   EXEC-IND-CARDS (user go 2026-11-01; card design approved the same day: tabs Kalkulator, Grafik, Langkah): how an
   indicator's value at one candle is made, with the numbers of the ticker and the date the Terminal shows (user: "samakan
   dengan bagaimana formula dihitung di terminal ... Dan di display di terminal").

   An explainer returns, for candle t:
     - expr and terms: the last step of the formula as symbols, with each symbol's value at t;
     - combine: that last step as a function of the symbols (the card's calculator moves them);
     - steps: how the symbols come from the data, with the numbers of t;
     - value: the indicator's value at t. It equals the chart's value (calc/flow.ts, calc/indicators.ts): the tests
       compute both on the same data (tests/calc/explain.test.ts).
   Pure, no DOM, like the calculation modules. An indicator without an explainer yet gets none (the card says so).
   ========================================================================== */

import type { FlowContext, FlowParams, FlowRows } from './flow';
import { BOARDS, INVESTORS } from './flow';
import type { Bars, Params } from './indicators';
import { isN } from './indicators';

export type Unit = 'idr' | 'price' | 'pct' | 'lot' | 'count' | 'num';
export interface Term { key: string; label: string; value: number; unit: Unit }
export interface Step { title: string; text: string; table?: { head: string[]; rows: string[][]; note?: string } }
export interface Explanation {
  output: string;                      // the output explained (the indicator's first output unless asked)
  value: number | null;                // the value at t (= the chart)
  expr: string;                        // the last step with the terms' keys, e.g. "100 × (NB + NS) ÷ TBV"
  terms: Term[];
  combine(v: Record<string, number>): number | null;
  steps: Step[];
  span?: { from: string; to: string; candles: number };   // the candles the value reads
}
/** `output`: the output to explain (a multi-output indicator: buy/sell, upper/basis/lower, macd/signal/histogram); left
    out, the indicator's main output (for a Flow indicator with a side parameter, that side) */
export type FlowExplainer = (c: FlowContext, p: FlowParams, t: number, output?: string) => Explanation | null;
export type TechExplainer = (B: Bars, p: Params, t: number, output?: string) => Explanation | null;

/* ---- numbers as the card writes them (Indonesian, as the approved mockup) ---- */
const NF = new Map<number, Intl.NumberFormat>();          // one formatter per decimals (building one costs ~20 µs)
const nf = (d: number) => { let f = NF.get(d); if (!f) NF.set(d, f = new Intl.NumberFormat('id-ID', { minimumFractionDigits:d, maximumFractionDigits:d })); return f };
const sign = (v: number) => (v < 0 ? '−' : '');
export const fmt = {
  num: (v: number | null, d = 2) => v === null || !isFinite(v) ? '–' : sign(v) + nf(d).format(Math.abs(v)),
  pct: (v: number | null, d = 2) => v === null || !isFinite(v) ? '–' : (v > 0 ? '+' : sign(v)) + nf(d).format(Math.abs(v)) + '%',
  /** Rupiah with its size word: T (triliun), M (miliar), jt (juta) */
  idr: (v: number | null) => {
    if (v === null || !isFinite(v)) return '–';
    const a = Math.abs(v), [d, u] = a >= 1e12 ? [1e12, ' T'] : a >= 1e9 ? [1e9, ' M'] : a >= 1e6 ? [1e6, ' jt'] : [1, ''];
    return `${sign(v)}Rp ${nf(d === 1 ? 0 : 2).format(a / d)}${u}`;
  },
  of: (v: number, u: Unit) => u === 'idr' ? fmt.idr(v) : u === 'pct' ? fmt.pct(v) : u === 'count' || u === 'lot' ? fmt.num(v, 0) : fmt.num(v, u === 'price' ? 2 : 4),
};

/* ---- broker rows over a window (the same rules as calc/flow.ts: FORMULAS.md section 2) ---- */
export const intOf = (v: any, d: number) => { const n = Math.floor(Number(v)); return Number.isFinite(n) && n >= 1 ? n : d };
const firstData = (R: FlowRows) => { for (let t = 0; t < R.N; t++) if (R.has[t]) return t; return R.N };
/** the window a..t of W candles ending at t, or null (t without data, or a window before the first data) */
export function flowWindow(R: FlowRows, t: number, W: number): number | null {
  const a = t - W + 1;
  return t >= 0 && t < R.N && R.has[t] && W >= 1 && a >= firstData(R) ? a : null;
}
export interface BrokerSums { code: string; bv: number; sv: number; bl: number; sl: number; bf: number; sf: number }
/** each broker's sums over candles a..t with the board and investor filter (null = all), and the total */
export function windowSums(R: FlowRows, a: number, t: number, boards: string[] | null, investors: string[] | null) {
  const okB = boards ? new Set(boards.map(b => BOARDS.indexOf(b as any))) : null;
  const okI = investors ? new Set(investors.map(i => INVESTORS.indexOf(i as any))) : null;
  const by = new Map<number, BrokerSums>(), total: BrokerSums = { code:'*', bv:0, sv:0, bl:0, sl:0, bf:0, sf:0 };
  for (let k = 0; k < R.n; k++) {
    if (R.t[k] < a || R.t[k] > t || (okB && !okB.has(R.brd[k])) || (okI && !okI.has(R.inv[k]))) continue;
    let s = by.get(R.b[k]);
    if (!s) by.set(R.b[k], s = { code:R.brokers[R.b[k]], bv:0, sv:0, bl:0, sl:0, bf:0, sf:0 });
    for (const f of ['bv', 'sv', 'bl', 'sl', 'bf', 'sf'] as const) { s[f] += R[f][k]; total[f] += R[f][k] }
  }
  return { brokers:[...by.values()], total };
}
/** the n brokers with the highest positive score, ties by code A-Z (calc/flow.ts topOf) */
export function topBy(list: BrokerSums[], n: number, score: (s: BrokerSums) => number): BrokerSums[] {
  return list.filter(s => score(s) > 0).sort((x, y) => score(y) - score(x) || (x.code < y.code ? -1 : 1)).slice(0, n);
}
/** the board or investor filter as calc/flow.ts grid reads it: left out = all; a list (even an empty one: no row) as given */
export const filterOf = (p: FlowParams, key: 'boards' | 'investors') => Array.isArray(p[key]) ? p[key] as string[] : null;
export const filterText = (p: FlowParams) => {
  const b = filterOf(p, 'boards'), i = filterOf(p, 'investors');
  const list = (x: string[] | null, all: number, every: string) => !x || x.length === all ? every : x.length ? x.join(', ') : 'tidak ada';
  return `${b && b.length && b.length < BOARDS.length ? 'papan ' : ''}${list(b, BOARDS.length, 'semua papan')}, ${list(i, INVESTORS.length, 'asing dan domestik')}`;
};
export const spanOf = (c: FlowContext, a: number, t: number) => ({ from:c.dates[a], to:c.dates[t], candles:t - a + 1 });
export const levelsOf = (p: FlowParams) => String(p.levels ?? '').split(/[,;\s]+/).filter(Boolean).map(Number).filter(Number.isFinite);
/** where a value sits against the indicator's reference lines */
export function againstLevels(v: number, levels: number[]): string {
  const up = [...levels].sort((x, y) => x - y), over = up.filter(l => v >= l), under = up.filter(l => v < l);
  if (!up.length) return '';
  if (!over.length) return `di bawah garis acuan terendah (${fmt.num(up[0], 0)})`;
  if (!under.length) return `di atas garis acuan tertinggi (${fmt.num(up[up.length - 1], 0)})`;
  return `di antara garis acuan ${fmt.num(over[over.length - 1], 0)} dan ${fmt.num(under[0], 0)}`;
}
export const brokerRow = (s: BrokerSums) => [s.code, fmt.idr(s.bv), fmt.idr(s.sv), fmt.idr(s.bv - s.sv)];

/* ---- technical explainers (registry keys of indRegistry.json) ---- */
export const SOURCES: Record<string, string> = { open:'open', high:'high', low:'low', close:'close', hl2:'(H + L) / 2', hlc3:'(H + L + C) / 3', ohlc4:'(O + H + L + C) / 4' };
/** the bar price a source names (calc/indicators.ts srcOf) */
export function sourceAt(B: Bars, s: string, i: number): number | null {
  const o = B.O[i], h = B.H[i], l = B.L[i], c = B.C[i];
  const v = s === 'open' ? o : s === 'high' ? h : s === 'low' ? l : s === 'hl2' ? (isN(h) && isN(l) ? (h + l) / 2 : null)
    : s === 'hlc3' ? (isN(h) && isN(l) && isN(c) ? (h + l + c) / 3 : null) : s === 'ohlc4' ? (isN(o) && isN(h) && isN(l) && isN(c) ? (o + h + l + c) / 4 : null) : c;
  return isN(v) ? v : null;
}
export const dateOf = (B: Bars, i: number) => B.T ? B.T[i] : `candle ${i + 1}`;
