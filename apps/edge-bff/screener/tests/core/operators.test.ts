/* The universal operators (EXEC-SCREENER-FLOW-CANDLES P2; verification/screener/OPERATORS.md, approved by the user
   2026-11-07, K4), OPERATORS.md section 7:
   - each operator equals an independent brute-force reading of its rule, value by value, on a real fixture series with
     missing values (operators 2-4, 6, 7, 12-14);
   - condition truth tables at the boundaries (1, 5, 9, 10, 15): equal to the threshold, just above and below, missing
     values, not-ready windows;
   - cross-sectional (11): the population follows the universe filters (a filter change moves the ranks; the old RS rank
     does not move), each rank equals percentRank over the filtered universe;
   - limits and refusals of section 5, each with its field and message;
   - chains: an operator over another operator's result equals the brute-force composition. */
import { describe, expect, it } from 'vitest';
import { F } from '../../../terminal/src/calc/indicators.ts';
import type { Definition, UniverseRow } from '../../src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { bindCondition } from '../../src/core/condition.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { evaluateWindow, valuePasses } from '../../src/core/evaluate.ts';
import { resolveSeries, tickerCalc } from '../../src/core/metrics.ts';
import { previewCells, runScreen } from '../../src/core/screen.ts';
import {
  acceleration, distanceToExtreme, pctChange, percentileOwn, relative, slope, vsAverage, zScore,
} from '../../src/core/transforms.ts';
import { validateDefinition, validateTest } from '../../src/core/validate.ts';
import { OPTS, WITHIN_MAX, memoryEnv, rng, rowOf, synth, vctx } from './helpers.ts';

const isN = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const refusal = (fn: () => unknown): ScreenerError => { try { fn() } catch (e) { if (e instanceof ScreenerError) return e; throw e } throw new Error('expected a ScreenerError') };
const near = (a: (number | null)[], b: (number | null)[]) => {
  expect(a.length).toBe(b.length);
  for (let i = 0; i < a.length; i++) {
    if (b[i] === null) { expect([i, a[i]]).toEqual([i, null]); continue }
    expect(isN(a[i])).toBe(true);
    expect(Math.abs((a[i] as number) - (b[i] as number))).toBeLessThanOrEqual(1e-9 * Math.max(1, Math.abs(b[i] as number)));
  }
};

/* a real fixture series with holes: the RSI of a synthetic ticker (its own warm-up nulls) with some values removed */
const T0 = synth('OPS', 41, 700, '2023-01-02');
const RSI = (() => { const r = F.rsi(T0.bars, { length: 14 }).rsi.slice() as (number | null)[]; for (let i = 0; i < r.length; i++) if (i % 53 === 17) r[i] = null; return r })();
const CLOSE = Array.from(T0.bars.C as ArrayLike<number>);
const firstOf = (x: (number | null)[]) => x.findIndex(isN);

/* ---- brute force, written from OPERATORS.md, never from transforms.ts ---------------------------------------------- */
const bfSma = (x: (number | null)[], i: number, n: number) => {                 // the SMA of n consecutive values ending at i
  if (i - n + 1 < 0) return null;
  const w = x.slice(i - n + 1, i + 1);
  return w.every(isN) ? (w as number[]).reduce((s, v) => s + v, 0) / n : null;
};
const bfPercentile = (x: (number | null)[], n: number) => x.map((v, t) => {
  const f = firstOf(x);
  if (!isN(v) || f < 0 || t - n < f) return null;
  const w = x.slice(t - n, t).filter(isN) as number[];
  if (!w.length) return null;
  return 100 * (w.filter(u => u < v).length + 0.5 * w.filter(u => u === v).length) / w.length;
});
const bfZ = (x: (number | null)[], n: number) => x.map((v, t) => {
  const f = firstOf(x);
  if (!isN(v) || f < 0 || t - n < f) return null;
  const w = x.slice(t - n, t).filter(isN) as number[];
  if (w.length < 2) return null;
  const m = w.reduce((s, u) => s + u, 0) / w.length, sd = Math.sqrt(w.reduce((s, u) => s + (u - m) ** 2, 0) / (w.length - 1));
  return sd > 0 ? (v - m) / sd : null;
});
const bfSlope = (x: (number | null)[], n: number) => x.map((_, t) => {
  if (t - n + 1 < 0) return null;
  const w = x.slice(t - n + 1, t + 1);
  if (!w.every(isN)) return null;
  const ks = w.map((_, k) => k), kb = ks.reduce((s, k) => s + k, 0) / n, xb = (w as number[]).reduce((s, v) => s + v, 0) / n;
  return ks.reduce((s, k) => s + (k - kb) * ((w[k] as number) - xb), 0) / ks.reduce((s, k) => s + (k - kb) ** 2, 0);
});
const bfHigh = (x: (number | null)[], i: number, n: number, max: boolean) => {   // today included, a missing value restarts
  let run = 0; for (let j = i; j >= 0 && isN(x[j]); j--) run++;
  if (run < n) return null;
  const w = x.slice(i - n + 1, i + 1) as number[];
  return max ? Math.max(...w) : Math.min(...w);
};

describe('operators 2-4, 6, 7, 12-14 equal a brute-force reading of OPERATORS.md', () => {
  it('2 Historical Average: SMA over the N sessions before today, three forms; ratio and percent need a positive average', () => {
    for (const n of [1, 5, 20]) {
      const avg = RSI.map((_, i) => i >= 1 ? bfSma(RSI, i - 1, n) : null);
      near(vsAverage(RSI, 'SMA', n, 'difference'), RSI.map((v, i) => isN(v) && isN(avg[i]) ? v - (avg[i] as number) : null));
      near(vsAverage(RSI, 'SMA', n, 'ratio'), RSI.map((v, i) => isN(v) && isN(avg[i]) && (avg[i] as number) > 0 ? v / (avg[i] as number) : null));
      near(vsAverage(RSI, 'SMA', n, 'percent'), RSI.map((v, i) => isN(v) && isN(avg[i]) && (avg[i] as number) > 0 ? 100 * (v / (avg[i] as number) - 1) : null));
    }
    expect(vsAverage([1, -2, -2, 5], 'SMA', 2, 'ratio')).toEqual([null, null, null, null]);        // average 0.5 - 2 < 0
    expect(vsAverage([2, 4, 6, 8], 'SMA', 2, 'difference')).toEqual([null, null, 3, 3]);             // today excluded
  });
  it('3 Historical Percentile (mid-rank), not ready before N sessions of history', () => {
    for (const n of [1, 10, 60, 252]) near(percentileOwn(RSI, n), bfPercentile(RSI, n));
    expect(percentileOwn([5, 5, 5, 5], 3)).toEqual([null, null, null, 50]);                           // ties count half
    expect(percentileOwn([1, 2, 3, 9], 3)).toEqual([null, null, null, 100]);
  });
  it('6 Z-Score with the sample deviation (n - 1) of the N sessions before today; a flat window is missing', () => {
    for (const n of [2, 20, 120]) near(zScore(RSI, n), bfZ(RSI, n));
    expect(zScore([3, 3, 3, 4], 3)).toEqual([null, null, null, null]);                                 // SD 0
  });
  it('4 Change in percent; the base must be positive', () => {
    for (const n of [1, 7, 63]) near(pctChange(CLOSE, n), CLOSE.map((v, i) => i >= n && CLOSE[i - n] > 0 ? 100 * (v / CLOSE[i - n] - 1) : null));
    expect(pctChange([0, 5, -1, 4], 1)).toEqual([null, null, -120, null]);                       // a base of 0 or -1 has no percent
  });
  it('7 Relative Comparison: difference and ratio (the second series must be positive for a ratio)', () => {
    const sma = F.sma(T0.bars, { length: 50 }).sma as (number | null)[];
    near(relative(CLOSE, sma, 'difference'), CLOSE.map((v, i) => isN(sma[i]) ? v - (sma[i] as number) : null));
    near(relative(CLOSE, sma, 'ratio'), CLOSE.map((v, i) => isN(sma[i]) && (sma[i] as number) > 0 ? v / (sma[i] as number) : null));
    expect(relative([1, 1], [0, -1], 'ratio')).toEqual([null, null]);
  });
  it('12 Trend / Slope: least squares over the N sessions ending today; a hole leaves it missing', () => {
    for (const n of [2, 5, 20, 130]) near(slope(RSI, n), bfSlope(RSI, n));
    near(slope([1, 3, 5, 7, 9], 3), [null, null, 2, 2, 2]);
  });
  it('13 Acceleration: slope of the last N minus slope of the N before', () => {
    for (const n of [2, 10, 40]) { const s = bfSlope(RSI, n); near(acceleration(RSI, n), RSI.map((_, t) => t >= n && isN(s[t]) && isN(s[t - n]) ? (s[t] as number) - (s[t - n] as number) : null)) }
    near(acceleration([0, 1, 4, 9, 16, 25], 2), [null, null, null, 4, 4, 4]);                          // x = k^2: slope 2k - 1, so +4 over 2 sessions
  });
  it('14 Distance to Extreme: today included, absolute and percent', () => {
    for (const n of [1, 20, 252]) for (const ext of ['highest', 'lowest'] as const) {
      const m = RSI.map((_, i) => bfHigh(RSI, i, n, ext === 'highest'));
      near(distanceToExtreme(RSI, ext, n, 'absolute'), RSI.map((v, i) => isN(v) && isN(m[i]) ? v - (m[i] as number) : null));
      near(distanceToExtreme(RSI, ext, n, 'percent'), RSI.map((v, i) => isN(v) && isN(m[i]) && (m[i] as number) > 0 ? 100 * (v / (m[i] as number) - 1) : null));
    }
    expect(distanceToExtreme([5, 8, 6], 'highest', 2, 'absolute')).toEqual([null, 0, -2]);
  });
  it('chains: a percentile of a change in percent of the close equals the brute-force composition', () => {
    const r = resolveSeries({ kind: 'transform', fn: 'percentile', of: { kind: 'transform', fn: 'change_pct', of: { kind: 'price', field: 'close' }, args: { bars: 5 } }, args: { length: 60 } }, 'm', OPTS);
    const chg = CLOSE.map((v, i) => i >= 5 && CLOSE[i - 5] > 0 ? 100 * (v / CLOSE[i - 5] - 1) : null);
    near(Array.from(r.full(tickerCalc(T0)) as ArrayLike<number | null>), bfPercentile(chg, 60));
    expect([r.unit, r.historyClass]).toEqual(['percentile', 'window']);
  });
});

describe('operators 1 and 15: the value rule at its boundaries', () => {
  it('gt, lt strict; ge, le inclusive; eq, ne exact; between inclusive; outside exclusive of the bounds', () => {
    const t = (op: string, value: number, value2?: number) => (x: number) => valuePasses(x, { op: op as never, value, value2 });
    expect([9.99, 10, 10.01].map(t('gt', 10))).toEqual([false, false, true]);
    expect([9.99, 10, 10.01].map(t('lt', 10))).toEqual([true, false, false]);
    expect([9.99, 10, 10.01].map(t('ge', 10))).toEqual([false, true, true]);
    expect([9.99, 10, 10.01].map(t('le', 10))).toEqual([true, true, false]);
    expect([2, 3, 4].map(t('eq', 3))).toEqual([false, true, false]);
    expect([2, 3, 4].map(t('ne', 3))).toEqual([true, false, true]);
    expect([1.99, 2, 5, 8, 8.01].map(t('between', 2, 8))).toEqual([false, true, true, true, false]);
    expect([1.99, 2, 5, 8, 8.01].map(t('outside', 2, 8))).toEqual([true, false, false, false, true]);
  });
});

describe('operators 5, 9, 10: the window rule', () => {
  const P = { status: 'pass' } as const, X = { status: 'fail' } as const, N = { status: 'na', reason: 'NULL_AT_EVALUATION' } as const;
  const run = (seq: readonly ({ status: string })[], mode: 'ever' | 'at_least' | 'streak', length: number, count = 1) =>
    evaluateWindow(i => seq[i] as never, mode, length, count, seq.length - 1);
  it('ever: one pass in the window; n/a counts as not passing; n/a only when every session is n/a', () => {
    expect(run([P, X, X, X], 'ever', 3).status).toBe('fail');                // the pass is 3 sessions back, outside 3
    expect(run([P, X, X, X], 'ever', 4)).toMatchObject({ status: 'pass', value: 1, barsAgo: 3 });
    expect(run([X, N, N], 'ever', 2)).toMatchObject({ status: 'na', reason: 'NULL_AT_EVALUATION' });
    expect(run([P, N, X], 'ever', 2).status).toBe('fail');
  });
  it('at_least: K of N, K = N included', () => {
    expect(run([P, X, P, P], 'at_least', 4, 3)).toMatchObject({ status: 'pass', value: 3 });
    expect(run([P, X, P, N], 'at_least', 4, 3)).toMatchObject({ status: 'fail', value: 2 });
    expect(run([P, P, P], 'at_least', 3, 3).status).toBe('pass');
  });
  it('streak: each of the last K sessions; an n/a session breaks the run', () => {
    expect(run([X, P, P, P], 'streak', 3)).toMatchObject({ status: 'pass', value: 3 });
    expect(run([P, P, N, P], 'streak', 3)).toMatchObject({ status: 'fail', value: 1 });
    expect(run([P, P], 'streak', 3)).toMatchObject({ status: 'fail', value: 2 });                     // history shorter than K
  });
  it('a bound window test equals counting the inner test over the last N bars of the full series', () => {
    const IX = synth('IHSG', 3, 520, '2024-06-03'), t = synth('WIN', 77, 520, '2024-06-03'), E = t.dates.at(-1)!;
    const env = memoryEnv([t], IX, [rowOf(t, E)], E);
    const rsi = F.rsi(t.bars, { length: 14 }).rsi as (number | null)[], at = t.dates.length - 1;
    for (const [mode, length, count] of [['ever', 5, 1], ['at_least', 20, 12], ['streak', 3, 1], ['at_least', WITHIN_MAX, 60]] as const) {
      const b = bindCondition({ id: 'w', enabled: true, test: { kind: 'window', mode, length, ...(mode === 'at_least' ? { count } : {}), test: { kind: 'value', metric: { kind: 'indicator', indicator: 'I13', output: 'rsi' }, op: 'gt', value: 55 } } }, 'c', env);
      const cell = b.evaluate({ ticker: 'WIN', dates: t.dates, bars: t.bars, at, row: rowOf(t, E), ihsgCalendar: IX.dates, series: r => env.series(r, t), xsection: () => null }).cell;
      const pass = Array.from({ length }, (_, k) => isN(rsi[at - k]) && (rsi[at - k] as number) > 55);
      let streak = 0; while (streak < length && pass[streak]) streak++;
      const hits = pass.filter(Boolean).length;
      expect([mode, cell.status, cell.value]).toEqual([mode, (mode === 'ever' ? hits >= 1 : mode === 'at_least' ? hits >= count : streak >= length) ? 'pass' : 'fail', mode === 'streak' ? streak : hits]);
    }
  });
});

describe('operator 11: rank across the filtered universe (decision C)', () => {
  const IX = synth('IHSG', 3, 520, '2024-06-03'), E = IX.dates.at(-1)!;
  const tickers = Array.from({ length: 40 }, (_, k) => synth(`R${String(k).padStart(2, '0')}`, 300 + k, 520, '2024-06-03'));
  const R = rng(5);
  const rows: UniverseRow[] = tickers.map((t, k) => rowOf(t, E, { adv20_idr: 1e8 + 1e8 * k, last: 1000, sector: R() < 0.5 ? 'Financials' : 'Energy' }));
  const CTX = vctx(tickers.map(t => t.ticker));
  const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null } as Definition['universe'];
  const rsi = { kind: 'indicator', indicator: 'I13', output: 'rsi' } as const;
  const screen = (u: Definition['universe']) => runScreen(validateDefinition({ universe: u, logic: 'all', conditions: [
    { id: 'k', enabled: true, test: { kind: 'value', op: 'between', value: 0, value2: 100, metric: { kind: 'rank', of: rsi } } },
    { id: 'r', enabled: true, test: { kind: 'value', op: 'between', value: 0, value2: 100, metric: { kind: 'xsection', metric: 'return_rank', params: { window: 60 } } } }] }, CTX),
    memoryEnv(tickers, IX, rows, E));
  const last = new Map(tickers.map(t => [t.ticker, F.rsi(t.bars, { length: 14 }).rsi.at(-1) as number]));
  const bfRank = (members: string[], t: string) => 100 * members.filter(m => last.get(m)! < last.get(t)!).length / (members.length - 1);
  it('each rank is 100 x #(members below) / (P - 1) over the filtered universe, and a filter moves it', () => {
    const all = screen(U), half = screen({ ...U, adv20_min_idr: 2.05e9 });
    const membersAll = tickers.map(t => t.ticker), membersHalf = rows.filter(r => (r.adv20_idr as number) >= 2.05e9).map(r => r.ticker);
    for (const r of all.rows) expect([r.ticker, r.cells[0].value]).toEqual([r.ticker, expect.closeTo(bfRank(membersAll, r.ticker), 9)]);
    for (const r of half.rows) expect([r.ticker, r.cells[0].value]).toEqual([r.ticker, expect.closeTo(bfRank(membersHalf, r.ticker), 9)]);
    expect(all.rows.find(r => r.ticker === 'R39')!.cells[0].value).not.toBe(half.rows.find(r => r.ticker === 'R39')!.cells[0].value);
    // the old RS rank keeps its fixed population (K3): the same value under both universes
    expect(all.rows.find(r => r.ticker === 'R39')!.cells[1].value).toBe(half.rows.find(r => r.ticker === 'R39')!.cells[1].value);
    expect(all.conditions[0]).toMatchObject({ source: 'xsection', unit: 'percentile', metric: 'rank(I13.rsi)' });
  });
  it('a previewed ticker outside the universe is ranked against it (denominator P) without joining it', () => {
    const d = validateDefinition({ universe: { ...U, adv20_min_idr: 2.05e9 }, logic: 'all', conditions: [
      { id: 'k', enabled: true, test: { kind: 'value', op: 'ge', value: 0, metric: { kind: 'rank', of: rsi } } }] }, CTX);
    const members = rows.filter(r => (r.adv20_idr as number) >= 2.05e9).map(r => r.ticker), out = 'R00';
    expect(members).not.toContain(out);
    const p = previewCells(d, memoryEnv(tickers, IX, rows, E), out);
    expect(p.cells[0].value).toBeCloseTo(100 * members.filter(m => last.get(m)! < last.get(out)!).length / members.length, 9);
  });
});

describe('refusals of OPERATORS.md section 5 name the field and the fix', () => {
  const t = synth('REF', 9, 400), CTX = vctx(['REF']);
  const rsi = { kind: 'indicator', indicator: 'I13', output: 'rsi' } as const, close = { kind: 'price', field: 'close' } as const;
  const v = (test: unknown) => refusal(() => validateTest(test, 'definition.conditions[0].test', CTX));
  it('"=" and "!=" only on a whole-number series (K7)', () => {
    const e = v({ kind: 'value', metric: rsi, op: 'eq', value: 30 });
    expect([e.code, e.field]).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.op']);
    expect(e.message).toMatch(/whole-number.*right: rising run = 3; wrong: RSI = 30/);
    expect(() => validateTest({ kind: 'value', metric: { kind: 'transform', fn: 'rising_run', of: close }, op: 'eq', value: 3 }, 'f', CTX)).not.toThrow();
    expect(() => validateTest({ kind: 'value', metric: { kind: 'universe', attr: 'bars' }, op: 'ne', value: 250 }, 'f', CTX)).not.toThrow();
  });
  it('a range takes the lower bound first; outside as between', () => {
    const e = v({ kind: 'value', metric: rsi, op: 'outside', value: 70, value2: 30 });
    expect([e.code, e.field]).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.value2']);
    expect(validateTest({ kind: 'value', metric: rsi, op: 'outside', value: 30, value2: 70 }, 'f', CTX)).toMatchObject({ op: 'outside', value: 30, value2: 70 });
    expect(validateTest({ kind: 'value', metric: rsi, op: 'ge', value: 30 }, 'f', CTX)).toMatchObject({ op: 'ge' });
  });
  it('units must match for a relative comparison, naming both', () => {
    const e = v({ kind: 'value', op: 'gt', value: 0, metric: { kind: 'transform', fn: 'relative', of: rsi, args: { by: close } } });
    expect([e.code, e.field]).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.metric.args.by']);
    expect(e.message).toMatch(/same unit.*I13\.rsi.*close/);
  });
  it('an operator not offered for the output type (OPERATORS.md section 4)', () => {
    const pct = { kind: 'transform', fn: 'percentile', of: rsi, args: { length: 60 } };
    const e = v({ kind: 'value', op: 'gt', value: 0, metric: { kind: 'transform', fn: 'zscore', of: pct, args: { length: 20 } } });
    expect([e.code, e.field]).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.metric.of']);
    expect(e.message).toMatch(/already set against its own history.*it takes/);
    const run = { kind: 'transform', fn: 'rising_run', of: close };
    expect(v({ kind: 'value', op: 'gt', value: 0, metric: { kind: 'transform', fn: 'slope', of: run, args: { length: 5 } } }).message).toMatch(/consecutive sessions/);
  });
  it('a rank of a price level, a rank in a comparison, a rank as a metric filter', () => {
    const e = v({ kind: 'value', op: 'ge', value: 90, metric: { kind: 'rank', of: close } });
    expect([e.code, e.field]).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.metric.of']);
    expect(e.message).toMatch(/right: rank of RSI/);
    expect(v({ kind: 'state', lhs: { kind: 'rank', of: rsi }, op: 'gt', rhs: { value: 50 } }).code).toBe('INVALID_CONDITION');
    const f = refusal(() => validateDefinition({ universe: { ...UNIVERSE_DEFAULTS, metric_filters: [{ kind: 'value', op: 'ge', value: 50, metric: { kind: 'rank', of: rsi } }] }, logic: 'all', conditions: [] }, CTX));
    expect([f.code, f.field]).toEqual(['INVALID_CONDITION', 'definition.universe.metric_filters[0].metric']);
  });
  it('window limits: length 1..within_max (LIMIT_EXCEEDED above), K <= N, no pattern inside', () => {
    const inner = { kind: 'value', metric: rsi, op: 'gt', value: 50 };
    const e = v({ kind: 'window', mode: 'ever', length: WITHIN_MAX + 1, test: inner });
    expect([e.code, e.field, e.details]).toEqual(['LIMIT_EXCEEDED', 'definition.conditions[0].test.length', { limit: 'within_max', allowed: WITHIN_MAX, needed: WITHIN_MAX + 1 }]);
    const k = v({ kind: 'window', mode: 'at_least', length: 5, count: 6, test: inner });
    expect([k.field, k.message]).toEqual(['definition.conditions[0].test.count', expect.stringMatching(/right: 3 of 5; wrong: 6 of 5/)]);
    expect(v({ kind: 'window', mode: 'ever', length: 5, test: { kind: 'state', pattern: { kind: 'pattern', type: 'breakout' } } }).field).toBe('definition.conditions[0].test.test');
    expect(v({ kind: 'window', mode: 'ever', length: 5, count: 2, test: inner }).field).toBe('definition.conditions[0].test.count');
    expect(validateTest({ kind: 'window', mode: 'at_least', length: 5, count: 3, test: inner }, 'f', CTX))
      .toEqual({ kind: 'window', mode: 'at_least', length: 5, count: 3, test: { kind: 'value', metric: { kind: 'indicator', indicator: 'I13', output: 'rsi', params: { length: 14, source: 'close' } }, op: 'gt', value: 50 } });
    expect(t.dates.length).toBe(400);
  });
  it('an operator\'s N out of its catalog range is PARAM_OUT_OF_RANGE naming the argument', () => {
    const e = v({ kind: 'value', op: 'gt', value: 0, metric: { kind: 'transform', fn: 'percentile', of: rsi, args: { length: 300 } } });
    expect([e.code, e.field]).toEqual(['PARAM_OUT_OF_RANGE', 'definition.conditions[0].test.metric.args.length']);
  });
});
