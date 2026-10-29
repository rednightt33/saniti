/* The lookback a value reads, which decides PRICE_BREAK_IN_LOOKBACK (semantic review, EXEC-SCREENER; report TARGET
   ARCHITECTURE 6.9 Remarks, 6.12 "a window-class output only while its window contains the ex-date"; TEST PLAN 10b.4
   "an SMA(20) cell whose window has moved past the ex-date carries no remark"):
   - every window-class pattern's stated window (transforms.ts PatternImpl.window, ResolvedSeries.window) is exact, by a
     cut probe: computed on only its last `window` bars the signal at the last bar equals the full-history signal
     (sufficient), and on `window - 1` bars it can never fire (no shorter window would do);
   - on a PRICE_BREAK row, for each condition form, an ex-date whose first bar is the first bar the value reads leaves
     the cell unmarked (every bar it reads is after the break), and one bar later marks it (the first bar it reads is
     before the break): bar field, window series, a lagged side (the Donchian prior band, rolling_max), crosses within
     W, patterns as STATE and as EVENT within W, the cross-section return and an indicator over the bars. */
import { describe, expect, it } from 'vitest';
import type { Definition, ParamMap, UniverseRow } from '../../src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { tickerCalc } from '../../src/core/metrics.ts';
import { previewCells } from '../../src/core/screen.ts';
import { IMPLEMENTED_PATTERNS, patternSignal, resolveSignal } from '../../src/core/transforms.ts';
import { validateDefinition } from '../../src/core/validate.ts';
import { OPTS, memoryEnv, rng, rowOf, synth, tailBars, vctx } from './helpers.ts';

/* ---- pattern windows ------------------------------------------------------------------------------------------- */

const PARAMS: Record<string, ParamMap[]> = {
  breakout: [{ length: 1 }, { length: 7 }, { length: 40 }],
  breakdown: [{ length: 1 }, { length: 9 }, { length: 33 }],
  volspike: [{ length: 1, threshold: 1.2 }, { length: 10, threshold: 1.5 }, { length: 25, threshold: 1.1 }],
  macross: [{ fast_length: 3, slow_length: 9 }, { fast_length: 20, slow_length: 50 }, { fast_length: 30, slow_length: 10 }],
  squeeze: [{ length: 2, std_dev: 2, lookback: 1 }, { length: 10, std_dev: 2, lookback: 15 }, { length: 20, std_dev: 1.5, lookback: 40 }],
  stoch_cross_in_zone: [{ k_length: 1, smooth_k: 1, d_length: 1, zone_max: 60 }, { k_length: 5, smooth_k: 3, d_length: 3, zone_max: 50 }, { k_length: 14, smooth_k: 3, d_length: 3, zone_max: 40 }],
  new_high: [{ of: 'close', length: 1 }, { of: 'close', length: 12 }, { of: 'volume', length: 8 }, { of: 'I40.obv', length: 15 }, { of: 'I41.pvt', length: 6 }, { of: 'I44.adl', length: 10 }, { of: 'I50.nvi', length: 9 }],
  silent: [{ days: 1, length: 1, volx: 1, move: 50 }, { days: 5, length: 20, volx: 0.8, move: 10 }, { days: 3, length: 12, volx: 0.5, move: 20 }],
};

describe('a window-class pattern reads exactly its stated window', () => {
  const tickers = Array.from({ length: 12 }, (_, k) => synth(`W${k}`, 700 + k, 360));
  for (const type of IMPLEMENTED_PATTERNS) {
    const spec = resolveSignal({ kind: 'pattern', type }, 'p', OPTS);
    if (!Number.isFinite(spec.window)) continue;                                       // recursive (macd_divergence): the whole history
    it(`${type}: the last-bar signal on its last window bars equals the full one; on window - 1 bars it never fires`, () => {
      expect(PARAMS[type], `add parameter cases for ${type}`).toBeDefined();
      let fired = 0;
      for (const params of PARAMS[type]) {
        const ref = { kind: 'pattern' as const, type, params }, w = resolveSignal(ref, 'p', OPTS).window;
        for (const t of tickers) {
          const full = patternSignal(tickerCalc(t), ref, 'p', OPTS);
          for (const at of [w + 5, 150, 233, 359]) {
            const cut = patternSignal(tickerCalc(tailBars({ ...t, dates: t.dates.slice(0, at + 1), bars: cutTo(t.bars, at + 1) }, w)), ref, 'p', OPTS);
            expect([type, params, t.ticker, at, cut[cut.length - 1]]).toEqual([type, params, t.ticker, at, full[at]]);
          }
          for (let at = w - 1; at < 360; at++) {
            const short = patternSignal(tickerCalc(tailBars({ ...t, dates: t.dates.slice(0, at + 1), bars: cutTo(t.bars, at + 1) }, w - 1)), ref, 'p', OPTS);
            if (short.some(x => x === 1)) throw new Error(`${type} ${JSON.stringify(params)} fires on ${w - 1} bars (${t.ticker} at ${at}): its window ${w} is not the shortest`);
            if (at > 300) break;
          }
          fired += full.reduce((s, x) => s + x, 0);
        }
      }
      expect(fired).toBeGreaterThan(0);                                                 // the probe saw signals
    });
  }
});
function cutTo(b: any, n: number) { return { O: b.O.slice(0, n), H: b.H.slice(0, n), L: b.L.slice(0, n), C: b.C.slice(0, n), V: b.V.slice(0, n), T: b.T.slice(0, n) } }

/* ---- the remark at the edge of each lookback -------------------------------------------------------------------- */

const IX = (() => { const t = synth('IHSG', 3, 400, '2024-06-03'); return { ...t, bars: { ...t.bars, V: t.bars.V.map(() => null) } } })();
const E = IX.dates[IX.dates.length - 1];
const T0 = synth('PBSA', 902, 400, '2024-06-03'), AT = T0.dates.length - 1;
const POP = Array.from({ length: 8 }, (_, k) => synth(`P${k}`, 40 + k, 400, '2024-06-03'));
const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null, exclude_price_breaks: false } as Definition['universe'];
const CTX = vctx(['PBSA', ...POP.map(t => t.ticker)]);
const close = { kind: 'price', field: 'close' } as const, high = { kind: 'price', field: 'high' } as const;
const ind = (indicator: string, output: string, params?: Record<string, unknown>) => ({ kind: 'indicator' as const, indicator, output, ...(params ? { params } : {}) });
/** The remark of the one cell of `test` on PBSA with its ex-date on bar d. */
function remarkAt(test: unknown, d: number): string | null {
  const rows: UniverseRow[] = [rowOf(T0, E, {}, [{ code: 'PRICE_BREAK', action: 'STOCK_SPLIT', ex_date: T0.dates[d], ratio_old: 1, ratio_new: 2, close_ratio: 0.5 }]), ...POP.map(t => rowOf(t, E))];
  const def = validateDefinition({ universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test }] }, CTX);
  return previewCells(def, memoryEnv([T0, ...POP], IX, rows, E), 'PBSA').cells[0].remark;
}
/** [condition, the first bar the value at AT reads]: the ex-date on that bar leaves the cell unmarked, one later marks it. */
const W = 7, N = 20;
const FORMS: [string, unknown, number][] = [
  ['STATE close vs a value (one bar)', { kind: 'state', lhs: close, op: 'gt', rhs: { value: 1 } }, AT],
  ['VALUE distance to SMA(20) (window)', { kind: 'value', op: 'gt', value: -1000, metric: { kind: 'transform', fn: 'pct_distance', of: ind('I01', 'sma', { length: N }) } }, AT - N + 1],
  ['STATE close vs SMA(20)', { kind: 'state', lhs: close, op: 'gt', rhs: ind('I01', 'sma', { length: N }) }, AT - N + 1],
  ['STATE close vs the prior Donchian(20) band (lag 1)', { kind: 'state', lhs: close, op: 'gt', rhs: ind('I10', 'upper', { length: N }) }, AT - N],
  ['STATE close vs the prior 20-session high (rolling_max, lag 1)', { kind: 'state', lhs: close, op: 'gt', rhs: { kind: 'transform', fn: 'rolling_max', of: high, args: { length: N } } }, AT - N],
  ['VALUE ROC(20)', { kind: 'value', op: 'gt', value: -1000, metric: ind('I17', 'roc', { length: N }) }, AT - N],
  ['VALUE vs IHSG over 20', { kind: 'value', op: 'gt', value: -1000, metric: { kind: 'transform', fn: 'vs_index', of: close, args: { window: N } } }, AT - N],
  ['EVENT close crosses a value within 7', { kind: 'event', within: W, signal: { lhs: close, op: 'crosses_above', rhs: { value: 1 } } }, AT - W],
  ['EVENT close crosses SMA(20) within 7', { kind: 'event', within: W, signal: { lhs: close, op: 'crosses_above', rhs: ind('I01', 'sma', { length: N }) } }, AT - W - N + 1],
  ['EVENT close crosses the prior Donchian band within 7', { kind: 'event', within: W, signal: { lhs: close, op: 'crosses_above', rhs: ind('I10', 'upper', { length: N }) } }, AT - W - N],
  ['STATE breakout(20)', { kind: 'state', pattern: { kind: 'pattern', type: 'breakout', params: { length: N } } }, AT - N],
  ['EVENT breakout(20) within 7', { kind: 'event', within: W, signal: { pattern: { kind: 'pattern', type: 'breakout', params: { length: N } } } }, AT - W + 1 - N],
  ['EVENT volspike(20) within 7', { kind: 'event', within: W, signal: { pattern: { kind: 'pattern', type: 'volspike', params: { length: N, threshold: 1.5 } } } }, AT - W + 1 - N],
  ['EVENT new_high(close, 20) within 7', { kind: 'event', within: W, signal: { pattern: { kind: 'pattern', type: 'new_high', params: { of: 'close', length: N } } } }, AT - W + 1 - N],
  ['VALUE return_rank(20)', { kind: 'value', op: 'gt', value: -1, metric: { kind: 'xsection', metric: 'return_rank', params: { window: N } } }, AT - N],
];

describe('PRICE_BREAK_IN_LOOKBACK at the edge of each lookback', () => {
  for (const [name, test, lo] of FORMS) {
    it(`${name}: an ex-date on the first bar read leaves the cell unmarked, one bar later marks it`, () => {
      expect([name, remarkAt(test, lo)]).toEqual([name, null]);
      if (lo < AT) expect([name, remarkAt(test, lo + 1)]).toEqual([name, 'PRICE_BREAK_IN_LOOKBACK']);
      if (lo < AT) expect([name, remarkAt(test, AT)]).toEqual([name, 'PRICE_BREAK_IN_LOOKBACK']);
      if (lo > 0) expect([name, remarkAt(test, lo - 1)]).toEqual([name, null]);
    });
  }
  it('a recursive output (RSI) and a universe attribute: always marked after the ex-date / never marked', () => {
    const r = rng(5);
    for (let k = 0; k < 5; k++) {
      const d = 1 + Math.floor(r() * AT);
      expect(remarkAt({ kind: 'value', op: 'gt', value: -1, metric: ind('I13', 'rsi') }, d)).toBe('PRICE_BREAK_IN_LOOKBACK');
      expect(remarkAt({ kind: 'value', op: 'gt', value: -1e9, metric: { kind: 'universe', attr: 'chg_1d_pct' } }, d)).toBe(null);
    }
  });
});
