/* An independent oracle for whole screens (semantic review, EXEC-SCREENER; report TARGET ARCHITECTURE 6.5 as-of
   policy, 6.9 tests, NA codes and remarks, 6.10 planner, 6.12 P4; TEST PLAN 10b.3, 10b.4, 10b.6). Random definitions
   (ALL, ANY, AT LEAST; 1-7 conditions over VALUE, STATE and EVENT templates with random parameters, within from 1 to
   within_max, patterns, transforms with a lagged side, cross-sectional ranks and universe attributes; random P4 chips
   and universe bounds) run through core runScreen four ways (cold and pre-warmed, pruned and exhaustive), and every
   answer is compared with a brute-force reading written here from the report's rules alone: F for the indicator
   values (the formula authority), and this file's own comparison, cross, within, NA, remark, rank, universe, near and
   sort rules (no core evaluate, match, plan, xsection or universe code). The data carries what the review attacks:
   the two sessions missing for every stock (M238: bars_ago != market_sessions_ago), stale tickers (one session and
   eighteen before E), a ticker suspended inside the event window, short histories (74, 30, 3 and 1 bars), a flat
   ticker (zero-width bands), a ticker without volume, and price-break rows with ex-dates near and far, between two
   sessions, and on a row that is also stale. */
import { describe, expect, it } from 'vitest';
import { F } from '../../../terminal/src/calc/indicators.ts';
import type { Bars } from '../../../terminal/src/calc/indicators.ts';
import type { Cell, Definition, UniverseRow } from '../../src/core/contract.ts';
import { bindCondition } from '../../src/core/condition.ts';
import { runScreen } from '../../src/core/screen.ts';
import type { TickerBars } from '../../src/core/metrics.ts';
import { validateDefinition } from '../../src/core/validate.ts';
import { WITHIN_MAX, headBars, memoryEnv, rng, rowOf, synth, tailBars, vctx } from './helpers.ts';

/* ---- data ----------------------------------------------------------------------------------------------------- */

const N0 = 330, START = '2024-06-03';
const IX = (() => { const t = synth('IHSG', 3, N0, START); return { ...t, bars: { ...t.bars, V: t.bars.V.map(() => null) } } as TickerBars })();
const E = IX.dates[IX.dates.length - 1];
const MISS = [300, 301];                                                     // missing for every stock (M238)
function drop(t: TickerBars, idx: readonly number[], ticker = t.ticker): TickerBars {
  const gone = new Set(idx), keep = (a: ArrayLike<unknown>) => Array.from(a).filter((_, i) => !gone.has(i)) as any;
  return { ticker, dates: keep(t.dates), bars: { O: keep(t.bars.O), H: keep(t.bars.H), L: keep(t.bars.L), C: keep(t.bars.C), V: keep(t.bars.V), T: keep(t.dates) } };
}
const stock = (ticker: string, seed: number, extra: number[] = []) => drop(synth(ticker, seed, N0, START), [...MISS, ...extra], ticker);
const normal = Array.from({ length: 30 }, (_, k) => stock(`N${String(k).padStart(2, '0')}`, 1000 + k));
const STL1 = headBars(stock('STLA', 2001), N0 - 2 - 18), STL2 = headBars(stock('STLB', 2002), N0 - 2 - 1);
const SUSP = stock('SUSP', 2003, [318, 319, 320, 321, 322, 323]);           // suspended inside the window, trading at E
const SH74 = tailBars(stock('RANS', 2004), 74), SH30 = tailBars(stock('SHRT', 2005), 30), SH3 = tailBars(stock('TINY', 2006), 3), SH1 = tailBars(stock('ONEB', 2007), 1);
const FLAT = (() => { const t = stock('FLAT', 2008), n = t.dates.length, k = (x: number) => new Array(n).fill(x); return { ...t, bars: { ...t.bars, O: k(500), H: k(500), L: k(500), C: k(500), V: k(2e6) } } })();
const ZVOL = (() => { const t = stock('ZVOL', 2009); return { ...t, bars: { ...t.bars, V: t.bars.V.map(() => 0) } } })();
const BRK = [stock('BRKA', 2010), stock('BRKB', 2011), stock('BRKC', 2012), stock('BRKD', 2013)];
const STBR = headBars(stock('STBR', 2014), N0 - 2 - 5);
const TICKERS: TickerBars[] = [...normal, STL1, STL2, SUSP, SH74, SH30, SH3, SH1, FLAT, ZVOL, ...BRK, STBR];
const lastIx = (t: TickerBars) => t.dates.length - 1;
// ex-dates: 4 and 60 bars before the last bar, a date the stock lacks (a missing session: its next bar is the first
// after the break), 200 bars back, and on a stale row
const EXDATES: Record<string, string> = {
  BRKA: BRK[0].dates[lastIx(BRK[0]) - 4], BRKB: BRK[1].dates[lastIx(BRK[1]) - 60], BRKC: IX.dates[MISS[0]], BRKD: BRK[3].dates[lastIx(BRK[3]) - 200],
  STBR: STBR.dates[lastIx(STBR) - 10],
};
const SECTOR: Record<string, string | null> = { N00: null, N01: 'Financials', N02: 'Financials', N03: 'Energy', N04: 'Energy' };
const ROWS: UniverseRow[] = TICKERS.map(t => rowOf(t, E, { sector: t.ticker in SECTOR ? SECTOR[t.ticker] : 'Industrials', industry: t.ticker in SECTOR ? (SECTOR[t.ticker] === null ? null : 'Banks') : 'Machinery' },
  EXDATES[t.ticker] ? [{ code: 'PRICE_BREAK', action: 'STOCK_SPLIT', ex_date: EXDATES[t.ticker], ratio_old: 1, ratio_new: 2, close_ratio: 0.5 }] : []));
const BY = new Map(TICKERS.map(t => [t.ticker, t]));
const CTX = vctx(TICKERS.map(t => t.ticker));

/* ---- the oracle's own reading of F and of the rules --------------------------------------------------------------- */

type S = ArrayLike<number | null | undefined>;
const fin = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x);
const r12 = (x: unknown) => fin(x) ? Number(x.toPrecision(12)) : null;
const memo = new Map<string, S>();
const f = (t: TickerBars, key: string, params: Record<string, unknown>, out: string): S => {
  const k = `${t.ticker}|${key}|${JSON.stringify(params)}|${out}`;
  let s = memo.get(k);
  if (!s) { s = (F[key](t.bars as Bars, params) as Record<string, S>)[out]; memo.set(k, s) }
  return s;
};
const shift = (s: S, k = 1): S => { const o: (number | null)[] = new Array(s.length).fill(null); for (let i = k; i < s.length; i++) o[i] = fin(s[i - k]) ? s[i - k] as number : null; return o };
const bar = (t: TickerBars, field: 'O' | 'H' | 'L' | 'C' | 'V'): S => t.bars[field] as S;
function rollMax(s: S, n: number, max = true): S {
  const o: (number | null)[] = new Array(s.length).fill(null);
  for (let i = n - 1; i < s.length; i++) {
    let m = max ? -Infinity : Infinity, ok = true;
    for (let j = i - n + 1; j <= i; j++) { const v = s[j]; if (!fin(v)) { ok = false; break } m = max ? Math.max(m, v) : Math.min(m, v) }
    if (ok) o[i] = m;
  }
  return o;
}
const anyUpTo = (s: S, at: number) => { for (let i = 0; i <= at; i++) if (fin(s[i])) return true; return false };
const hasField = (s: S, at: number) => { for (let i = 0; i <= at; i++) { const v = s[i]; if (fin(v) && v !== 0) return true } return false };
const gt = (a: S | number, b: S | number, i: number, op: 'gt' | 'lt') => {
  if (i < 1) return false;
  const x = typeof a === 'number' ? a : a[i], y = typeof b === 'number' ? b : b[i];
  return fin(x) && fin(y) && (op === 'gt' ? x > y : x < y);
};
const cross = (a: S | number, b: S | number, i: number, up: boolean) => {
  if (i < 1) return false;
  const g = (s: S | number, k: number) => typeof s === 'number' ? s : s[k];
  const x0 = g(a, i - 1), y0 = g(b, i - 1), x = g(a, i), y = g(b, i);
  return fin(x0) && fin(y0) && fin(x) && fin(y) && (up ? x0 <= y0 && x > y : x0 >= y0 && x < y);
};

/** One side as the oracle reads it: its series, the first bar its value at bar i reads (null: the whole history), and
    whether the ticker lacks a bar field it needs. */
interface Side { s: S | number; lo: ((i: number) => number) | null; needs?: 'V' }
interface OracleCell { status: 'pass' | 'fail' | 'na'; reason: string | null; value?: number | null; lhs?: number | null; rhs?: number | null;
  event_date?: string | null; bars_ago?: number | null; market_sessions_ago?: number | null; last_event_date?: string | null; remark: string | null }
interface Template { test: unknown; cell(t: TickerBars, at: number, row: UniverseRow): OracleCell }

const sessionsBetween = (from: string, to: string) => IX.dates.filter(d => d > from && d <= to).length;
function remarkOf(row: UniverseRow, t: TickerBars, at: number, los: (number | null)[]): string | null {
  for (const r of row.remarks) {
    if (r.code !== 'PRICE_BREAK') continue;
    const d = t.dates.findIndex(x => x >= r.ex_date);
    if (d < 0 || d > at) continue;
    if (los.some(lo => lo === null ? d <= at : lo < d)) return 'PRICE_BREAK_IN_LOOKBACK';
  }
  return null;
}
const missing = (t: TickerBars, sides: Side[], at: number) => sides.some(x => typeof x.s !== 'number' && x.needs === 'V' && !hasField(bar(t, 'V'), at));
function naOf(t: TickerBars, x: Side, at: number): string | null {
  if (typeof x.s === 'number' || fin(x.s[at])) return null;
  if (x.needs === 'V' && !hasField(bar(t, 'V'), at)) return 'NULL_AT_EVALUATION';
  return anyUpTo(x.s, at) ? 'NULL_AT_EVALUATION' : 'INSUFFICIENT_HISTORY';
}
function valueCell(t: TickerBars, at: number, row: UniverseRow, x: Side, pass: (v: number) => boolean): OracleCell {
  const v = (x.s as S)[at], reason = naOf(t, x, at);
  return { status: reason ? 'na' : pass(v as number) ? 'pass' : 'fail', reason, value: reason ? null : r12(v), remark: remarkOf(row, t, at, [x.lo ? x.lo(at) : null]) };
}
function stateCell(t: TickerBars, at: number, row: UniverseRow, a: Side, op: 'gt' | 'lt', b: Side): OracleCell {
  const cur = (x: Side) => typeof x.s === 'number' ? x.s : r12(x.s[at]);
  const reason = naOf(t, a, at) ?? naOf(t, b, at);
  const los = [a, b].filter(x => typeof x.s !== 'number').map(x => x.lo ? x.lo(at) : null);
  return { status: reason ? 'na' : gt(a.s, b.s, at, op) ? 'pass' : 'fail', reason, lhs: cur(a), rhs: cur(b), remark: remarkOf(row, t, at, los) };
}
function eventCell(t: TickerBars, at: number, row: UniverseRow, signal: (i: number) => boolean, within: number, sides: Side[] | null, los: (number | null)[]): OracleCell {
  let j: number | null = null, k: number | null = null;
  for (let i = at; i > at - WITHIN_MAX && i >= 0; i--) if (signal(i)) { k = i; break }
  for (let i = at; i > at - within && i >= 0; i--) if (signal(i)) { j = i; break }
  const cur = sides ? { lhs: typeof sides[0].s === 'number' ? sides[0].s : r12(sides[0].s[at]), rhs: typeof sides[1].s === 'number' ? sides[1].s : r12(sides[1].s[at]) } : {};
  let status: OracleCell['status'] = j !== null ? 'pass' : 'fail', reason: string | null = null;
  if (j === null && sides) for (const x of sides) {
    if (typeof x.s === 'number') continue;
    if (x.needs === 'V' && !hasField(bar(t, 'V'), at)) { status = 'na'; reason = 'NULL_AT_EVALUATION'; break }
    if (!anyUpTo(x.s, at)) { status = 'na'; reason = 'INSUFFICIENT_HISTORY'; break }
  }
  return { status, reason, ...cur, event_date: j === null ? null : t.dates[j], bars_ago: j === null ? null : at - j,
    market_sessions_ago: j === null ? null : sessionsBetween(t.dates[j], t.dates[at]), last_event_date: k === null ? null : t.dates[k], remark: remarkOf(row, t, at, los) };
}
const crossLos = (sides: Side[], at: number, within: number) => sides.filter(x => typeof x.s !== 'number').map(x => x.lo ? x.lo(at - within) : null);

/* ---- templates (random parameters; the oracle's sides) ------------------------------------------------------------- */

const ref = (indicator: string, output: string, params: Record<string, unknown>) => ({ kind: 'indicator', indicator, output, params });
const CLOSE = { kind: 'price', field: 'close' }, HIGH = { kind: 'price', field: 'high' }, VOLUME = { kind: 'price', field: 'volume' };
const closeSide = (t: TickerBars): Side => ({ s: bar(t, 'C'), lo: i => i });
const smaSide = (t: TickerBars, n: number): Side => ({ s: f(t, 'sma', { length: n }, 'sma'), lo: i => i - n + 1 });
const pick = <T,>(r: () => number, xs: readonly T[]): T => xs[Math.floor(r() * xs.length)];
const int = (r: () => number, a: number, b: number) => a + Math.floor(r() * (b - a + 1));

function template(r: () => number): Template {
  const kind = int(r, 0, 22), W = pick(r, [1, 2, 5, int(r, 1, WITHIN_MAX), WITHIN_MAX] as const);
  switch (kind) {
    case 0: {                                                                  // VALUE RSI (recursive)
      const n = int(r, 2, 30), op = pick(r, ['gt', 'lt', 'between'] as const), v = int(r, 20, 70), v2 = v + int(r, 0, 25);
      return { test: { kind: 'value', metric: ref('I13', 'rsi', { length: n }), op, value: v, ...(op === 'between' ? { value2: v2 } : {}) },
        cell: (t, at, row) => valueCell(t, at, row, { s: f(t, 'rsi', { length: n }, 'rsi'), lo: null }, x => op === 'gt' ? x > v : op === 'lt' ? x < v : x >= v && x <= v2) };
    }
    case 1: {                                                                  // STATE close vs SMA (window)
      const n = int(r, 2, 120), op = pick(r, ['gt', 'lt'] as const);
      return { test: { kind: 'state', lhs: CLOSE, op, rhs: ref('I01', 'sma', { length: n }) }, cell: (t, at, row) => stateCell(t, at, row, closeSide(t), op, smaSide(t, n)) };
    }
    case 2: {                                                                  // STATE close vs the prior Donchian band (lag probe)
      const n = int(r, 2, 60), up = r() < 0.5;
      const side = (t: TickerBars): Side => ({ s: shift(f(t, 'donchian', { length: n }, up ? 'upper' : 'lower')), lo: i => i - n });
      return { test: { kind: 'state', lhs: CLOSE, op: up ? 'gt' : 'lt', rhs: ref('I10', up ? 'upper' : 'lower', { length: n }) }, cell: (t, at, row) => stateCell(t, at, row, closeSide(t), up ? 'gt' : 'lt', side(t)) };
    }
    case 3: {                                                                  // STATE MACD above its signal (outputs of one instance)
      const p = { fast_length: int(r, 3, 15), slow_length: int(r, 16, 40), signal_length: int(r, 2, 12) };
      return { test: { kind: 'state', lhs: ref('I06', 'macd', p), op: 'gt', rhs: ref('I06', 'signal', p) },
        cell: (t, at, row) => stateCell(t, at, row, { s: f(t, 'macd', p, 'macd'), lo: null }, 'gt', { s: f(t, 'macd', p, 'signal'), lo: null }) };
    }
    case 4: {                                                                  // STATE SMA(fast) above SMA(slow) (two instances)
      const a = int(r, 2, 40), b = a + int(r, 1, 80);
      return { test: { kind: 'state', lhs: ref('I01', 'sma', { length: a }), op: 'gt', rhs: ref('I01', 'sma', { length: b }) }, cell: (t, at, row) => stateCell(t, at, row, smaSide(t, a), 'gt', smaSide(t, b)) };
    }
    case 5: {                                                                  // EVENT close crosses SMA within W
      const n = int(r, 2, 80), up = r() < 0.5;
      return { test: { kind: 'event', within: W, signal: { lhs: CLOSE, op: up ? 'crosses_above' : 'crosses_below', rhs: ref('I01', 'sma', { length: n }) } },
        cell: (t, at, row) => { const s = [closeSide(t), smaSide(t, n)]; return eventCell(t, at, row, i => cross(s[0].s, s[1].s, i, up), W, s, crossLos(s, at, W)) } };
    }
    case 6: {                                                                  // EVENT MACD crosses its signal
      const p = { fast_length: int(r, 3, 15), slow_length: int(r, 16, 40), signal_length: int(r, 2, 12) }, up = r() < 0.5;
      return { test: { kind: 'event', within: W, signal: { lhs: ref('I06', 'macd', p), op: up ? 'crosses_above' : 'crosses_below', rhs: ref('I06', 'signal', p) } },
        cell: (t, at, row) => { const s: Side[] = [{ s: f(t, 'macd', p, 'macd'), lo: null }, { s: f(t, 'macd', p, 'signal'), lo: null }]; return eventCell(t, at, row, i => cross(s[0].s, s[1].s, i, up), W, s, crossLos(s, at, W)) } };
    }
    case 7: {                                                                  // EVENT RSI crosses a level
      const n = int(r, 2, 30), v = int(r, 25, 75), up = r() < 0.5;
      return { test: { kind: 'event', within: W, signal: { lhs: ref('I13', 'rsi', { length: n }), op: up ? 'crosses_above' : 'crosses_below', rhs: { value: v } } },
        cell: (t, at, row) => { const s: Side[] = [{ s: f(t, 'rsi', { length: n }, 'rsi'), lo: null }, { s: v, lo: null }]; return eventCell(t, at, row, i => cross(s[0].s, v, i, up), W, s, crossLos(s, at, W)) } };
    }
    case 8: {                                                                  // EVENT close crosses the prior Donchian band
      const n = int(r, 2, 60), up = r() < 0.5;
      return { test: { kind: 'event', within: W, signal: { lhs: CLOSE, op: up ? 'crosses_above' : 'crosses_below', rhs: ref('I10', up ? 'upper' : 'lower', { length: n }) } },
        cell: (t, at, row) => { const s: Side[] = [closeSide(t), { s: shift(f(t, 'donchian', { length: n }, up ? 'upper' : 'lower')), lo: i => i - n }]; return eventCell(t, at, row, i => cross(s[0].s, s[1].s, i, up), W, s, crossLos(s, at, W)) } };
    }
    case 9: {                                                                  // VALUE distance to the N-session high (no lag)
      const n = int(r, 5, 252), a = -int(r, 0, 30), b = a + int(r, 0, 30);
      return { test: { kind: 'value', op: 'between', value: a, value2: b, metric: { kind: 'transform', fn: 'pct_distance', of: { kind: 'transform', fn: 'rolling_max', of: HIGH, args: { length: n } } } },
        cell: (t, at, row) => { const m = rollMax(bar(t, 'H'), n), C = bar(t, 'C'), s = Array.from({ length: C.length }, (_, i) => fin(C[i]) && fin(m[i]) && m[i] !== 0 ? ((C[i] as number) / (m[i] as number) - 1) * 100 : null);
          return valueCell(t, at, row, { s, lo: i => i - n + 1 }, x => x >= a && x <= b) } };
    }
    case 10: {                                                                 // VALUE return_rank on the fixed population
      const w = int(r, 1, 200), op = pick(r, ['gt', 'lt'] as const), v = int(r, 10, 90);
      return { test: { kind: 'value', op, value: v, metric: { kind: 'xsection', metric: 'return_rank', params: { window: w } } },
        cell: (t, at, row) => { const x = rankOf(w).get(t.ticker) ?? null; return { status: x === null ? 'na' : (op === 'gt' ? x > v : x < v) ? 'pass' : 'fail', reason: x === null ? 'INSUFFICIENT_HISTORY' : null, value: r12(x), remark: remarkOf(row, t, at, [at - w]) } } };
    }
    case 11: {                                                                 // VALUE universe attribute (no remark)
      const v = (r() - 0.5) * 4, op = pick(r, ['gt', 'lt'] as const);
      return { test: { kind: 'value', op, value: v, metric: { kind: 'universe', attr: 'chg_1d_pct' } },
        cell: (t, at, row) => { const C = bar(t, 'C'), x = at >= 1 && fin(C[at]) && fin(C[at - 1]) && C[at - 1] !== 0 ? r12(((C[at] as number) / (C[at - 1] as number) - 1) * 100) : null;
          return { status: x === null ? 'na' : (op === 'gt' ? x > v : x < v) ? 'pass' : 'fail', reason: x === null ? 'INSUFFICIENT_HISTORY' : null, value: x, remark: null } } };
    }
    case 12: {                                                                 // breakout pattern, STATE or EVENT
      const n = int(r, 2, 60), ev = r() < 0.6;
      const sig = (t: TickerBars) => (i: number) => { if (i < n) return false; const H = bar(t, 'H'), C = bar(t, 'C'); let m = -Infinity; for (let j = i - n; j < i; j++) m = Math.max(m, fin(H[j]) ? H[j] as number : NaN); return fin(C[i]) && (C[i] as number) > m };
      const p = { kind: 'pattern', type: 'breakout', params: { length: n } };
      return ev ? { test: { kind: 'event', within: W, signal: { pattern: p } }, cell: (t, at, row) => eventCell(t, at, row, sig(t), W, null, [at - W + 1 - n]) }
        : { test: { kind: 'state', pattern: p }, cell: (t, at, row) => ({ status: at >= 1 && sig(t)(at) ? 'pass' : 'fail', reason: null, remark: remarkOf(row, t, at, [at - n]) }) };
    }
    case 13: {                                                                 // volspike pattern EVENT
      const n = int(r, 2, 40), th = 1 + r() * 1.5;
      const sig = (t: TickerBars) => { const V = bar(t, 'V'), m = f(t, 'volume_sma', { length: n }, 'volume_sma'); return (i: number) => i >= 1 && fin(V[i]) && fin(m[i - 1]) && (m[i - 1] as number) !== 0 && (V[i] as number) / (m[i - 1] as number) > th };
      return { test: { kind: 'event', within: W, signal: { pattern: { kind: 'pattern', type: 'volspike', params: { length: n, threshold: th } } } }, cell: (t, at, row) => eventCell(t, at, row, sig(t), W, null, [at - W + 1 - n]) };
    }
    case 14: {                                                                 // STATE close above the prior N-session high (transform level, lag)
      const n = int(r, 2, 100);
      return { test: { kind: 'state', lhs: CLOSE, op: 'gt', rhs: { kind: 'transform', fn: 'rolling_max', of: HIGH, args: { length: n } } },
        cell: (t, at, row) => stateCell(t, at, row, closeSide(t), 'gt', { s: shift(rollMax(bar(t, 'H'), n)), lo: i => i - n }) };
    }
    case 15: {                                                                 // STATE SMA rising over k bars
      const n = int(r, 2, 60), k = int(r, 1, 30);
      return { test: { kind: 'state', lhs: ref('I01', 'sma', { length: n }), op: 'gt', rhs: { kind: 'transform', fn: 'lag', of: ref('I01', 'sma', { length: n }), args: { bars: k } } },
        cell: (t, at, row) => stateCell(t, at, row, smaSide(t, n), 'gt', { s: shift(f(t, 'sma', { length: n }, 'sma'), k), lo: i => i - k - n + 1 }) };
    }
    case 16: {                                                                 // VALUE ROC (window)
      const n = int(r, 1, 120), v = (r() - 0.5) * 20;
      return { test: { kind: 'value', op: 'gt', value: v, metric: ref('I17', 'roc', { length: n }) }, cell: (t, at, row) => valueCell(t, at, row, { s: f(t, 'roc', { length: n }, 'roc'), lo: i => i - n }, x => x > v) };
    }
    case 18: case 19: {                                                        // breakdown or new_high(close): close beyond the previous n bars
      const n = int(r, 1, 60), ev = r() < 0.6, down = kind === 18;
      const sig = (t: TickerBars) => (i: number) => {
        if (i < n) return false;
        const X = bar(t, down ? 'L' : 'C'), C = bar(t, 'C');
        let m = down ? Infinity : -Infinity;
        for (let j = i - n; j < i; j++) { if (!fin(X[j])) return false; m = down ? Math.min(m, X[j] as number) : Math.max(m, X[j] as number) }
        return fin(C[i]) && (down ? (C[i] as number) < m : (C[i] as number) > m);
      };
      const p = down ? { kind: 'pattern', type: 'breakdown', params: { length: n } } : { kind: 'pattern', type: 'new_high', params: { of: 'close', length: n } };
      return ev ? { test: { kind: 'event', within: W, signal: { pattern: p } }, cell: (t, at, row) => eventCell(t, at, row, sig(t), W, null, [at - W + 1 - n]) }
        : { test: { kind: 'state', pattern: p }, cell: (t, at, row) => ({ status: at >= 1 && sig(t)(at) ? 'pass' : 'fail', reason: null, remark: remarkOf(row, t, at, [at - n]) }) };
    }
    case 20: {                                                                 // macross: SMA(fast) crosses above SMA(slow)
      const a = int(r, 2, 30), b = a + int(r, 1, 50), ev = r() < 0.6;
      const sig = (t: TickerBars) => { const x = f(t, 'sma', { length: a }, 'sma'), y = f(t, 'sma', { length: b }, 'sma'); return (i: number) => cross(x, y, i, true) };
      const p = { kind: 'pattern', type: 'macross', params: { fast_length: a, slow_length: b } };
      return ev ? { test: { kind: 'event', within: W, signal: { pattern: p } }, cell: (t, at, row) => eventCell(t, at, row, sig(t), W, null, [at - W + 1 - b]) }
        : { test: { kind: 'state', pattern: p }, cell: (t, at, row) => ({ status: sig(t)(at) ? 'pass' : 'fail', reason: null, remark: remarkOf(row, t, at, [at - b]) }) };
    }
    case 21: {                                                                 // VALUE position in the Bollinger band (zero width on FLAT)
      const n = int(r, 2, 40), a = int(r, -20, 60), b = a + int(r, 0, 80);
      return { test: { kind: 'value', op: 'between', value: a, value2: b, metric: { kind: 'transform', fn: 'band_position', of: ref('I27', 'basis', { length: n }) } },
        cell: (t, at, row) => { const u = f(t, 'bollinger', { length: n }, 'upper'), l = f(t, 'bollinger', { length: n }, 'lower'), C = bar(t, 'C');
          const s = Array.from({ length: C.length }, (_, i) => fin(C[i]) && fin(u[i]) && fin(l[i]) && (u[i] as number) - (l[i] as number) !== 0 ? ((C[i] as number) - (l[i] as number)) / ((u[i] as number) - (l[i] as number)) * 100 : null);
          return valueCell(t, at, row, { s, lo: i => i - n + 1 }, x => x >= a && x <= b) } };
    }
    case 22: {                                                                 // VALUE return over d minus IHSG's (IHSG as of each stock date)
      const d = int(r, 1, 120), v = (r() - 0.5) * 30;
      return { test: { kind: 'value', op: 'gt', value: v, metric: { kind: 'transform', fn: 'vs_index', of: CLOSE, args: { window: d } } },
        cell: (t, at, row) => { const C = bar(t, 'C'), X = t.dates.map(day => { let k = -1; for (let i = 0; i < IX.dates.length && IX.dates[i] <= day; i++) k = i; return k < 0 ? null : (IX.bars.C as S)[k] as number });
          const s = Array.from({ length: C.length }, (_, i) => i >= d && fin(C[i]) && fin(C[i - d]) && fin(X[i]) && fin(X[i - d]) && C[i - d] !== 0 && X[i - d] !== 0 ? ((C[i] as number) / (C[i - d] as number) - (X[i] as number) / (X[i - d] as number)) * 100 : null);
          return valueCell(t, at, row, { s, lo: i => i - d }, x => x > v) } };
    }
    default: {                                                                 // STATE volume above its average (a volume level; ZVOL lacks volume)
      const n = int(r, 2, 40);
      return { test: { kind: 'state', lhs: VOLUME, op: 'gt', rhs: ref('I35', 'volume_sma', { length: n }) },
        cell: (t, at, row) => stateCell(t, at, row, { s: bar(t, 'V'), lo: i => i, needs: 'V' }, 'gt', { s: f(t, 'volume_sma', { length: n }, 'volume_sma'), lo: i => i - n + 1, needs: 'V' }) };
    }
  }
}

/* ---- cross-sectional ranks, universe and rows, by the report's rules -------------------------------------------- */

const rankMemo = new Map<number, Map<string, number | null>>();
function rankOf(w: number): Map<string, number | null> {
  let m = rankMemo.get(w);
  if (m) return m;
  const ret = new Map<string, number | null>();
  for (const row of ROWS) { const t = BY.get(row.ticker)!, at = lastIx(t), C = bar(t, 'C'); ret.set(row.ticker, at - w >= 0 && fin(C[at]) && fin(C[at - w]) && C[at - w] !== 0 ? ((C[at] as number) / (C[at - w] as number) - 1) * 100 : null) }
  const pop = ROWS.filter(x => x.last_bar === E && !x.remarks.some(y => y.code === 'PRICE_BREAK') && fin(ret.get(x.ticker))).map(x => x.ticker);
  const vals = pop.map(t => ret.get(t) as number), P = vals.length;
  m = new Map();
  for (const [t, v] of ret) {
    const member = pop.includes(t), denom = member ? P - 1 : P;
    m.set(t, fin(v) && P >= 2 && denom >= 1 ? 100 * vals.filter(x => x < v).length / denom : null);
  }
  rankMemo.set(w, m);
  return m;
}

interface Universe { traded?: boolean; breaks?: boolean; price_min: number | null; min_history_bars: number | null; tickers: string[] | null; sectors_in?: string[]; include_unclassified?: boolean }
function universeOracle(u: Universe) {
  let stale = 0, broken = 0;
  const eligible: UniverseRow[] = [];
  for (const row of ROWS) {
    if (u.traded !== false && row.last_bar < E) { stale++; continue }
    if (u.breaks !== false && row.remarks.some(x => x.code === 'PRICE_BREAK')) { broken++; continue }
    if (u.tickers && !u.tickers.includes(row.ticker)) continue;
    if (u.sectors_in && !(row.sector === null ? u.include_unclassified : u.sectors_in.includes(row.sector))) continue;
    if (u.price_min !== null && !(fin(row.last) && row.last >= u.price_min)) continue;
    if (u.min_history_bars !== null && !(row.bars >= u.min_history_bars)) continue;
    eligible.push(row);
  }
  return { eligible, counts: { listed: ROWS.length, eligible: eligible.length, stale_hidden: stale, price_break_hidden: broken, filtered_out: ROWS.length - eligible.length - stale - broken } };
}

function randomCase(seed: number) {
  const r = rng(seed), K = int(r, 1, 7), templates = Array.from({ length: K }, () => template(r));
  const logic = pick(r, ['all', 'any', 'at_least'] as const), atLeast = int(r, 1, K + 1);
  const u: Universe = { price_min: pick(r, [null, null, 0, 800, 1000, 1200]), min_history_bars: pick(r, [null, null, 1, 74, 200]), tickers: r() < 0.15 ? TICKERS.filter(() => r() < 0.5).map(t => t.ticker) : null };
  if (r() < 0.6) u.traded = r() < 0.4;
  if (r() < 0.6) u.breaks = r() < 0.4;
  if (r() < 0.15) { u.sectors_in = ['Industrials']; u.include_unclassified = r() < 0.5 }
  const enabled = templates.map(() => r() < 0.9);
  const universe: Record<string, unknown> = { price_min: u.price_min, adv20_min_idr: null, min_history_bars: u.min_history_bars, ...(u.tickers ? { tickers: u.tickers } : {}),
    ...(u.traded !== undefined ? { traded_on_eval_date: u.traded } : {}), ...(u.breaks !== undefined ? { exclude_price_breaks: u.breaks } : {}),
    ...(u.sectors_in ? { sectors_in: u.sectors_in, include_unclassified: u.include_unclassified } : {}) };
  const raw = { universe, logic, ...(logic === 'at_least' ? { at_least: atLeast } : {}), conditions: templates.map((x, k) => ({ id: k.toString(36), enabled: enabled[k], test: x.test })) };
  return { raw, templates, enabled, u, logic, atLeast };
}

function oracle(c: ReturnType<typeof randomCase>) {
  const { eligible, counts } = universeOracle(c.u);
  const active = c.templates.filter((_, k) => c.enabled[k]), ids = c.templates.map((_, k) => k.toString(36)).filter((_, k) => c.enabled[k]);
  const K = active.length, need = K === 0 ? 0 : c.logic === 'all' ? K : c.logic === 'any' ? 1 : Math.min(c.atLeast, K);
  const rows: { ticker: string; status: string; met: number; na: number; adv: number | null; cells: OracleCell[] }[] = [];
  const passed = active.map(() => 0), na = active.map(() => 0);
  for (const row of eligible) {
    const t = BY.get(row.ticker)!, at = lastIx(t);
    const cells = active.map(x => x.cell(t, at, row));
    cells.forEach((x, k) => { if (x.status === 'pass') passed[k]++; if (x.status === 'na') na[k]++ });
    const met = cells.filter(x => x.status === 'pass').length;
    const status = met >= need ? 'match' : need >= 2 && met === need - 1 ? 'near' : null;
    if (status) rows.push({ ticker: row.ticker, status, met, na: cells.filter(x => x.status === 'na').length, adv: row.adv20_idr, cells });
  }
  rows.sort((a, b) => (a.status === b.status ? 0 : a.status === 'match' ? -1 : 1) || b.met - a.met || (b.adv ?? -Infinity) - (a.adv ?? -Infinity) || (a.ticker < b.ticker ? -1 : 1));
  return { counts, need, rows, ids, passed, na, eligible: eligible.length };
}

const pickCell = (x: Cell): OracleCell => {
  const o: Record<string, unknown> = { status: x.status, reason: x.reason, remark: x.remark };
  for (const k of ['value', 'lhs', 'rhs', 'event_date', 'bars_ago', 'market_sessions_ago', 'last_event_date'] as const) if (k in x) o[k] = x[k];
  return o as unknown as OracleCell;
};
const strip = (o: OracleCell): OracleCell => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined)) as OracleCell;

describe('whole screens equal an independent brute-force reading of the rules (semantic review oracle)', () => {
  it('the universe rows hold what the rules give: last close, bars, last bar, stale and the STALE remark', () => {
    for (const row of ROWS) {
      const t = BY.get(row.ticker)!, at = lastIx(t), C = bar(t, 'C');
      expect([row.ticker, row.last, row.bars, row.stale, row.last_bar]).toEqual([row.ticker, C[at], at + 1, t.dates[at] < E, t.dates[at]]);
      expect(row.remarks.filter(x => x.code === 'STALE')).toEqual(t.dates[at] < E ? [{ code: 'STALE', last_bar_date: t.dates[at] }] : []);
    }
    expect(ROWS.filter(x => x.stale).map(x => x.ticker).sort()).toEqual(['STBR', 'STLA', 'STLB']);
  });

  // ORACLE_SEEDS widens the run by hand (1,500 seeds take about a minute); the suite runs 240
  const SEEDS = Number((globalThis as { process?: { env?: Record<string, string> } }).process?.env?.ORACLE_SEEDS ?? 240);
  it(`for ${SEEDS} random definitions: cold, pre-warmed, pruned and exhaustive runs all equal the oracle`, () => {
    let matches = 0, nears = 0, remarks = 0, nas = 0, events = 0;
    for (let seed = 1; seed <= SEEDS; seed++) {
      const c = randomCase(seed), def = validateDefinition(c.raw, CTX) as Definition, o = oracle(c);
      const coldEnv = memoryEnv(TICKERS, IX, ROWS, E), warmEnv = memoryEnv(TICKERS, IX, ROWS, E);
      for (const x of def.conditions.filter(y => y.enabled)) warmEnv.prewarm(bindCondition(x, 'c', warmEnv).series);
      const runs = [runScreen(def, coldEnv), runScreen(def, coldEnv, { exhaustive: true }), runScreen(def, warmEnv), runScreen(def, memoryEnv(TICKERS, IX, ROWS, E), { exhaustive: true })];
      for (const [k, res] of runs.entries()) {
        const tag = `seed ${seed} run ${k}`;
        expect([tag, res.universe]).toEqual([tag, o.counts]);
        expect([tag, res.need]).toEqual([tag, o.need]);
        expect([tag, res.rows.map(x => [x.ticker, x.status, x.met, x.na_count])]).toEqual([tag, o.rows.map(x => [x.ticker, x.status, x.met, x.na])]);
        for (const [i, row] of res.rows.entries()) {
          expect(row.cells.map(x => x.id)).toEqual(o.ids);
          expect([tag, row.ticker, row.cells.map(pickCell)]).toEqual([tag, row.ticker, o.rows[i].cells.map(strip)]);
          for (const cell of row.cells) expect(cell.eval_date).toBe(BY.get(row.ticker)!.dates[lastIx(BY.get(row.ticker)!)]);
        }
        if (k === 1 || k === 3) expect([tag, res.conditions.map(x => [x.evaluated, x.passed, x.na, x.exhaustive])]).toEqual([tag, o.ids.map((_, j) => [o.eligible, o.passed[j], o.na[j], true])]);
        for (const s of res.conditions) if (s.exhaustive) expect([tag, s.id, s.evaluated]).toEqual([tag, s.id, o.eligible]);
      }
      matches += o.rows.filter(x => x.status === 'match').length; nears += o.rows.filter(x => x.status === 'near').length;
      for (const row of o.rows) for (const x of row.cells) { if (x.remark) remarks++; if (x.status === 'na') nas++; if (x.event_date) events++ }
    }
    // the cases were exercised, not vacuous
    expect(matches).toBeGreaterThan(300); expect(nears).toBeGreaterThan(100); expect(remarks).toBeGreaterThan(30); expect(nas).toBeGreaterThan(30); expect(events).toBeGreaterThan(100);
  }, 120_000);
});
