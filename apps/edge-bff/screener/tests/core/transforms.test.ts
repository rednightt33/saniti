/* Condition arithmetic and pattern signals (report TARGET ARCHITECTURE 6.9, 6.9.1; TEST PLAN 10b.3 "Same-bar
   comparison lag", "Operator mapping"): each transform equals a brute-force reading of its rule; rolling windows follow
   the indicators.ts roll rule and equal F's Donchian channel; ma is indicators.ts sma / ema; the patterns equal the
   backtest core where it has them (breakout, volspike, golden cross, bullish divergence) and the prototype's rules
   elsewhere (breakdown, squeeze, stoch_cross_in_zone, new_high, silent, hup); references resolve to canonical keys and
   refuse what the catalog does not allow, naming the field. */
import { describe, expect, it } from 'vitest';
import { bullishDivergence, compare, priceActionCondition } from '../../../backtest/src/core/conditions.ts';
import { asOf } from '../../../backtest/src/core/datafile.ts';
import { F, ema, sma } from '../../../terminal/src/calc/indicators.ts';
import * as G from '../../scripts/build-screener-registry.mjs';
import { ScreenerError } from '../../src/core/errors.ts';
import { resolveSeries, tickerCalc } from '../../src/core/metrics.ts';
import {
  IMPLEMENTED_PATTERNS, bandPosition, change, lag, ma, patternSignal, pctDistance, ratio, resolveSignal, resolveTransform,
  risingRun, rollingMax, rollingMin, vsIndex,
} from '../../src/core/transforms.ts';
import { OPTS, synth } from './helpers.ts';

const B = G.fixture({ bars: 900 });
const T = tickerCalc({ ticker: 'SYN', dates: B.T as string[], bars: B });
const isN = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const refusal = (fn: () => unknown): ScreenerError => { try { fn() } catch (e) { if (e instanceof ScreenerError) return e; throw e } throw new Error('expected a ScreenerError') };
const close = { kind: 'price', field: 'close' } as const;

describe('arithmetic', () => {
  it('pct_distance, band_position, lag, change, ratio and rising_run follow their rules, null where an input is missing', () => {
    expect(pctDistance([110, 90, null, 5], [100, 100, 100, 0])).toEqual([expect.closeTo(10, 12), expect.closeTo(-10, 12), null, null]);
    expect(bandPosition([5, 10, 7, 3], [10, 10, 7, 5], [0, 0, 7, 1])).toEqual([50, 100, null, 50]);      // zero width -> null
    expect(lag([1, 2, null, 4], 1)).toEqual([null, 1, 2, null]);
    expect(change([1, 3, null, 10, 12], 1)).toEqual([null, 2, null, null, 2]);
    expect(ratio([4, 4, null, 1], [2, 0, 1, 4])).toEqual([2, null, null, 0.25]);
    expect(risingRun([1, 2, 3, 3, 4, 5, 6, 5, null, 7, 8])).toEqual([null, 1, 2, 0, 1, 2, 3, 0, null, null, 1]);
  });
  it('rolling_max and rolling_min restart after a missing value and equal a brute-force window, today included', () => {
    const x = Array.from({ length: 300 }, (_, i) => i % 37 === 5 ? null : Math.sin(i / 7) * 100 + (i % 11));
    for (const n of [1, 2, 5, 20]) {
      const mx = rollingMax(x, n), mn = rollingMin(x, n);
      for (let i = 0; i < x.length; i++) {
        let run = 0; for (let j = i; j >= 0 && isN(x[j]); j--) run++;
        const w = run >= n ? (x.slice(i - n + 1, i + 1) as number[]) : null;
        expect([mx[i], mn[i]]).toEqual(w ? [Math.max(...w), Math.min(...w)] : [null, null]);
      }
    }
  });
  it('rolling_max(high, n) and rolling_min(low, n) equal F\'s Donchian channel bit for bit', () => {
    for (const n of [5, 20, 55]) {
      const d = F.donchian(B, { length: n });
      expect(rollingMax(B.H, n)).toEqual(d.upper);
      expect(rollingMin(B.L, n)).toEqual(d.lower);
    }
  });
  it('ma is indicators.ts sma / ema, never a copy', () => {
    const obv = F.obv(B, {}).obv;
    expect(ma(obv, 'SMA', 20)).toEqual(sma(obv, 20));
    expect(ma(obv, 'EMA', 20)).toEqual(ema(obv, 20));
  });
  it('vs_index is the prototype\'s rs: (c / c[t-d] - IHSG / IHSG[t-d]) x 100 on the ticker\'s own bars', () => {
    const c = [100, 110, 121, null, 133.1], ix = [1000, 1000, 1100, 1100, 1210];
    expect(vsIndex(c, ix, 1)).toEqual([null, expect.closeTo(10, 12), expect.closeTo(0, 12), null, null]);
    expect(vsIndex(c, ix, 2)[2]).toBeCloseTo((121 / 100 - 1100 / 1000) * 100, 12);
  });
  it('refuses a window that is not a whole number of at least 1', () => {
    expect(() => rollingMax([1], 0)).toThrow(RangeError);
    expect(() => lag([1], 1.5)).toThrow(RangeError);
  });
});

describe('transform references', () => {
  it('resolves to a canonical key with every argument, so an explicit default equals a missing one', () => {
    const a = resolveTransform({ kind: 'transform', fn: 'ma', of: { kind: 'indicator', indicator: 'I40', output: 'obv' } }, 'm', OPTS);
    const b = resolveTransform({ kind: 'transform', fn: 'ma', of: { kind: 'indicator', indicator: 'I40', output: 'obv', params: {} }, args: { ma: 'EMA', length: 20 } }, 'm', OPTS);
    expect(a.key).toBe(b.key);
    expect(a.ref).toEqual({ kind: 'transform', fn: 'ma', of: { kind: 'indicator', indicator: 'I40', params: {}, output: 'obv' }, args: { ma: 'EMA', length: 20 } });
    expect([a.historyClass, a.comparableWith, a.unit]).toEqual(['cumulative', null, 'volume']);   // OBV is a volume quantity, not a level (scaling probe)
  });
  it('computes on the full series: hi52 = pct_distance(rolling_max(high, 252)) equals (close / 252-bar high - 1) x 100', () => {
    const r = resolveSeries({ kind: 'transform', fn: 'pct_distance', of: { kind: 'transform', fn: 'rolling_max', of: { kind: 'price', field: 'high' }, args: { length: 252 } } }, 'm', OPTS);
    const full = r.full(T);
    for (const i of [251, 400, 899]) expect(full[i]).toBeCloseTo((B.C[i] / Math.max(...B.H.slice(i - 251, i + 1)) - 1) * 100, 10);
    expect(full[250]).toBe(null);
    expect([r.historyClass, r.inputs]).toEqual(['window', ['H', 'C']]);
  });
  it('band_position reads the band instance\'s upper and lower at the same parameters', () => {
    const r = resolveSeries({ kind: 'transform', fn: 'band_position', of: { kind: 'indicator', indicator: 'I27', params: { length: 30 }, output: 'basis' } }, 'm', OPTS);
    const bb = F.bollinger(B, { length: 30 });
    expect(r.full(T)).toEqual(bandPosition(B.C, bb.upper, bb.lower));
    expect(refusal(() => resolveSeries({ kind: 'transform', fn: 'band_position', of: { kind: 'indicator', indicator: 'I13', output: 'rsi' } }, 'm', OPTS)).field).toBe('m.of');
  });
  it('vs_index aligns IHSG to the ticker\'s dates (asOf) and needs the index only when it computes', () => {
    const IX = synth('IHSG', 7, 900, '2016-01-04');
    const r = resolveTransform({ kind: 'transform', fn: 'vs_index', of: close, args: { window: 63 } }, 'm', { ...OPTS, index: IX });
    expect(r.full(T)).toEqual(vsIndex(B.C, asOf(IX.dates, IX.bars.C as number[], T.dates), 63));
    const noIndex = resolveTransform({ kind: 'transform', fn: 'vs_index', of: close }, 'm', OPTS);      // validation: no bars needed
    expect(() => noIndex.full(T)).toThrow(RangeError);
  });
  it('refuses an unknown fn, an argument out of range, an unknown argument and a non-level for pct_distance, naming the field', () => {
    const e1 = refusal(() => resolveSeries({ kind: 'transform', fn: 'zscore', of: close } as any, 'definition.conditions[0].test.metric', OPTS));
    expect([e1.code, e1.field, (e1.details as any).allowed]).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.metric.fn', expect.arrayContaining(['pct_distance', 'vs_index'])]);
    const e2 = refusal(() => resolveSeries({ kind: 'transform', fn: 'lag', of: close, args: { bars: 0 } }, 'm', OPTS));
    expect([e2.code, e2.field, e2.details]).toEqual(['PARAM_OUT_OF_RANGE', 'm.args.bars', { field: 'm.args.bars', min: 1, max: 260, exclusive_min: false, integer: true }]);
    expect(refusal(() => resolveSeries({ kind: 'transform', fn: 'lag', of: close, args: { bars: 2.5 } }, 'm', OPTS)).code).toBe('PARAM_OUT_OF_RANGE');
    expect(refusal(() => resolveSeries({ kind: 'transform', fn: 'lag', of: close, args: { n: 2 } } as any, 'm', OPTS)).field).toBe('m.args.n');
    const e3 = refusal(() => resolveSeries({ kind: 'transform', fn: 'pct_distance', of: { kind: 'indicator', indicator: 'I13', output: 'rsi' } }, 'm', OPTS));
    expect([e3.code, e3.field]).toEqual(['INVALID_CONDITION', 'm.of']);
    expect(refusal(() => resolveSeries({ kind: 'transform', fn: 'vs_index', of: { kind: 'price', field: 'high' } }, 'm', OPTS)).field).toBe('m.of');
  });
  it('a rolling window over a bar field carries the lag the probe derives; over an output it does not', () => {
    const rm = (field: string, fn = 'rolling_max') => resolveSeries({ kind: 'transform', fn, of: { kind: 'price', field }, args: { length: 20 } } as any, 'm', OPTS).compareLag;
    expect([rm('high'), rm('close'), rm('low', 'rolling_min')]).toEqual([{ gt: 1, lt: 0 }, { gt: 1, lt: 0 }, { gt: 0, lt: 1 }]);
    expect(resolveSeries({ kind: 'transform', fn: 'rolling_max', of: { kind: 'indicator', indicator: 'I01', output: 'sma' }, args: { length: 20 } }, 'm', OPTS).compareLag).toEqual({ gt: 0, lt: 0 });
  });
  it('refuses nesting deeper than 4 transforms', () => {
    let ref: any = close;
    for (let i = 0; i < 5; i++) ref = { kind: 'transform', fn: 'lag', of: ref, args: { bars: 1 } };
    expect(refusal(() => resolveSeries(ref, 'm', OPTS)).code).toBe('INVALID_CONDITION');
  });
});

describe('pattern signals', () => {
  const core = (type: string, params: Record<string, unknown>, value?: number, op?: string) => priceActionCondition(T.calc, { id: 'x', kind: 'price_action', type, params, ...(value !== undefined ? { value } : {}), ...(op ? { op } : {}) } as any, 'x');
  it('breakout, volspike, macross and macd_divergence are the backtest core\'s, bit for bit', () => {
    expect(patternSignal(T, { kind: 'pattern', type: 'breakout', params: { length: 30 } }, 'p', OPTS)).toEqual(core('breakout', { length: 30 }));
    expect(patternSignal(T, { kind: 'pattern', type: 'volspike', params: { length: 20, threshold: 1.5 } }, 'p', OPTS)).toEqual(core('volspike', { length: 20 }, 1.5));
    expect(patternSignal(T, { kind: 'pattern', type: 'macross' }, 'p', OPTS)).toEqual(core('macross', { fast_length: 20, slow_length: 50 }, undefined, 'golden_cross'));
    const m = F.macd(B, {}).macd;
    expect(patternSignal(T, { kind: 'pattern', type: 'macd_divergence' }, 'p', OPTS)).toEqual(bullishDivergence(B.L, m));
  });
  it('breakdown is close below the lowest low of the previous N bars (Donchian lower, read on the previous bar)', () => {
    const s = patternSignal(T, { kind: 'pattern', type: 'breakdown', params: { length: 20 } }, 'p', OPTS);
    for (let i = 0; i < B.C.length; i++) expect(s[i]).toBe(i >= 20 ? +(B.C[i] < Math.min(...B.L.slice(i - 20, i))) : 0);
    expect(s.reduce((a: number, b: number) => a + b, 0)).toBeGreaterThan(0);
  });
  it('squeeze: I29 bandwidth at its lowest of the look-back, today included', () => {
    const s = patternSignal(T, { kind: 'pattern', type: 'squeeze', params: { length: 20, std_dev: 2, lookback: 120 } }, 'p', OPTS);
    const bw = F.bollinger_width(B, { length: 20, std_dev: 2 }).bandwidth;
    for (let i = 1; i < bw.length; i++) {
      const w = bw.slice(i - 119, i + 1);
      expect(s[i]).toBe(i >= 138 && w.every(isN) ? +(bw[i]! <= Math.min(...(w as number[]))) : 0);
    }
  });
  it('stoch_cross_in_zone: %K crosses above %D on a bar where %K is below the zone (25 as coded)', () => {
    const s = patternSignal(T, { kind: 'pattern', type: 'stoch_cross_in_zone' }, 'p', OPTS);
    const o = F.stochastic(B, {}), x = compare(o.k, 'crosses_above', o.d, 0, B.C.length);
    for (let i = 0; i < x.length; i++) expect(s[i]).toBe(+(x[i] === 1 && (o.k[i] as number) < 25));
  });
  it('new_high: the line above the highest of its previous N bars, on every such bar (offset-invariant on OBV)', () => {
    const s = patternSignal(T, { kind: 'pattern', type: 'new_high', params: { of: 'I40.obv', length: 20 } }, 'p', OPTS);
    const obv = F.obv(B, {}).obv as number[];
    for (let i = 0; i < obv.length; i++) expect(s[i]).toBe(i >= 21 ? +(obv[i] > Math.max(...obv.slice(i - 20, i))) : 0);
    const shifted = tickerCalc({ ticker: 'S', dates: B.T as string[], bars: { ...B, V: B.V } });
    expect(patternSignal(shifted, { kind: 'pattern', type: 'new_high', params: { of: 'I40.obv', length: 20 } }, 'p', OPTS)).toEqual(s);
  });
  it('silent: SMA(v, days) / SMA(v, length)[t - days] >= volx while |move over days| <= move %', () => {
    const p = { days: 5, length: 20, volx: 1.1, move: 3 };
    const s = patternSignal(T, { kind: 'pattern', type: 'silent', params: p }, 'p', OPTS);
    const r = sma(B.V, 5), b = sma(B.V, 20);
    let hits = 0;
    for (let i = 5; i < B.C.length; i++) {
      const want = isN(r[i]) && isN(b[i - 5]) && r[i]! / b[i - 5]! >= 1.1 && Math.abs(B.C[i] / B.C[i - 5] - 1) * 100 <= 3;
      expect(s[i]).toBe(+want); hits += +want;
    }
    expect(hits).toBeGreaterThan(0);
  });
  it('a signal is a 0/1 series through the series path, never true on bar 0, and states the window it reads', () => {
    for (const type of IMPLEMENTED_PATTERNS) {
      const r = resolveSignal({ kind: 'pattern', type }, 'p', OPTS), full = r.full(T);
      expect(full[0]).toBe(0);
      expect(Array.from(full).every(v => v === 0 || v === 1)).toBe(true);
      expect(r.window).toBeGreaterThan(0);
    }
    expect(resolveSignal({ kind: 'pattern', type: 'breakout', params: { length: 250 } }, 'p', OPTS).window).toBe(251);
  });
  it('refuses an unknown pattern with the allowed types, and one that waits for a decision (Ichimoku, P6) as METRIC_UNAVAILABLE', () => {
    const e = refusal(() => resolveSignal({ kind: 'pattern', type: 'cup_handle' }, 'definition.conditions[0].test.pattern', OPTS));
    expect([e.code, e.field, (e.details as any).allowed]).toEqual(['INVALID_CONDITION', 'definition.conditions[0].test.pattern.type', expect.arrayContaining(['breakout', 'silent'])]);
    const i = refusal(() => resolveSignal({ kind: 'pattern', type: 'ichimoku_above' }, 'p', OPTS));
    expect([i.code, (i.details as any).availability]).toEqual(['METRIC_UNAVAILABLE', 'REQUIRES_DECISION']);
    expect(refusal(() => resolveSignal({ kind: 'pattern', type: 'breakout', params: { length: 0 } }, 'p', OPTS)).field).toBe('p.params.length');
  });
});
