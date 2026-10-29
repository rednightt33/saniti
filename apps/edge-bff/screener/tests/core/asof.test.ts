/* No look-ahead (semantic review, EXEC-SCREENER; report TARGET ARCHITECTURE 6.5 "Each ticker is evaluated at its own
   last bar on or before E", 6.7 "Always the full published history"): every series the screener reads is causal, so a
   value at bar i depends only on bars 0..i. Checked by a cut probe on every path a condition reads: the 76 registry
   outputs at their start parameters, every declared derived series, every pattern signal and the transforms (lag,
   change, rolling extremes, moving averages, ratio, rising run, vs_index with IHSG aligned by asOf): computed on the
   bars up to a cut, each value equals the full-history value on the same bar, bit for bit (a value read from a later
   bar, such as a pivot confirmed after the fact or a normalisation over the whole series, would differ). The worker
   holds no bar after E (snapshot.ts refuses such a file), so with causal series a ticker's cells read nothing after E. */
import { describe, expect, it } from 'vitest';
import type { MetricRef } from '../../src/core/contract.ts';
import { METRICS_CATALOG } from '../../src/core/catalog.ts';
import { declaredDerivedSeries } from '../../src/core/condition.ts';
import { resolveSeries, tickerCalc } from '../../src/core/metrics.ts';
import type { ResolvedSeries, TickerBars } from '../../src/core/metrics.ts';
import { INDICATORS } from '../../src/core/registry.ts';
import { IMPLEMENTED_PATTERNS, resolveSignal } from '../../src/core/transforms.ts';
import { OPTS, synth } from './helpers.ts';

const cut = (t: TickerBars, n: number): TickerBars => {
  const c = (a: ArrayLike<unknown>) => Array.from(a).slice(0, n) as any;
  return { ticker: t.ticker, dates: t.dates.slice(0, n), bars: { O: c(t.bars.O), H: c(t.bars.H), L: c(t.bars.L), C: c(t.bars.C), V: c(t.bars.V), T: t.dates.slice(0, n) } };
};
const IX = (() => { const t = synth('IHSG', 3, 420); return { ...t, bars: { ...t.bars, V: t.bars.V.map(() => null) } } })();
const TICKERS = [synth('CAUA', 11, 420), synth('CAUB', 12, 420), (() => { const t = synth('CAUC', 13, 420); return { ...t, bars: { ...t.bars, V: t.bars.V.map((v, i) => i % 17 === 3 ? 0 : v) } } })()];
const same = (a: unknown, b: unknown) => (typeof a === 'number' && Number.isFinite(a) ? a : null) === (typeof b === 'number' && Number.isFinite(b) ? b : null);

function causal(r: ResolvedSeries, ctx: { index: TickerBars }): string | null {
  for (const t of TICKERS) {
    const full = r.full(tickerCalc(t));
    for (const n of [60, 151, 263, 400]) {
      const part = resolveAgain(r, { ...ctx, index: cut(ctx.index, n) }).full(tickerCalc(cut(t, n)));        // IHSG cut at the same bar
      for (let i = 0; i < n; i++) if (!same(full[i], part[i])) return `${r.label} on ${t.ticker}: bar ${i} is ${full[i]} on the full history and ${part[i]} on the first ${n} bars`;
    }
  }
  return null;
}
const resolveAgain = (r: ResolvedSeries, ctx: { index: TickerBars }): ResolvedSeries => r.kind === 'pattern' ? resolveSignal(r.ref as never, 'p', OPTS) : resolveSeries(r.ref, 'r', { ...OPTS, ...ctx });

describe('every series a condition reads is causal: its value at a bar never reads a later bar', () => {
  const ctx = { ...OPTS, index: IX };
  it('the 76 registry outputs at their start parameters and the declared derived series', () => {
    const list: ResolvedSeries[] = [];
    for (const ind of INDICATORS) for (const o of ind.outputs) list.push(resolveSeries({ kind: 'indicator', indicator: ind.id, output: o.key, params: { ...ind.start_params } }, 'x', ctx));
    list.push(...declaredDerivedSeries(ctx));
    expect(list.length).toBeGreaterThan(76);
    const bad = list.map(r => causal(r, ctx)).filter(Boolean);
    expect(bad).toEqual([]);
  });
  it('every pattern signal at its catalog defaults', () => {
    const bad: string[] = [];
    for (const type of IMPLEMENTED_PATTERNS) { const why = causal(resolveSignal({ kind: 'pattern', type }, 'p', OPTS), ctx); if (why) bad.push(why) }
    expect(bad).toEqual([]);
  });
  it('the transforms of the catalog, IHSG aligned to each ticker\'s dates', () => {
    const close = { kind: 'price', field: 'close' }, vol = { kind: 'price', field: 'volume' }, rsi = { kind: 'indicator', indicator: 'I13', output: 'rsi' }, obv = { kind: 'indicator', indicator: 'I40', output: 'obv' };
    const refs = [
      { kind: 'transform', fn: 'pct_distance', of: { kind: 'indicator', indicator: 'I02', output: 'ema', params: { length: 50 } } },
      { kind: 'transform', fn: 'band_position', of: { kind: 'indicator', indicator: 'I27', output: 'basis' } },
      { kind: 'transform', fn: 'lag', of: rsi, args: { bars: 7 } }, { kind: 'transform', fn: 'change', of: obv, args: { bars: 20 } },
      { kind: 'transform', fn: 'rolling_max', of: { kind: 'price', field: 'high' }, args: { length: 252 } }, { kind: 'transform', fn: 'rolling_min', of: rsi, args: { length: 30 } },
      { kind: 'transform', fn: 'rising_run', of: { kind: 'indicator', indicator: 'I06', output: 'histogram' } }, { kind: 'transform', fn: 'ma', of: obv, args: { ma: 'EMA', length: 20 } },
      { kind: 'transform', fn: 'ma', of: vol, args: { ma: 'SMA', length: 20 } },
      { kind: 'transform', fn: 'ratio', of: vol, args: { by: { kind: 'transform', fn: 'lag', of: { kind: 'transform', fn: 'ma', of: vol, args: { ma: 'SMA', length: 20 } }, args: { bars: 1 } } } },
      { kind: 'transform', fn: 'vs_index', of: close, args: { window: 63 } },
    ];
    expect(new Set(refs.map(x => x.fn))).toEqual(new Set(METRICS_CATALOG.transforms.map(x => x.fn)));     // every transform of the catalog
    const bad = refs.map(x => causal(resolveSeries(x as unknown as MetricRef, 'x', ctx), ctx)).filter(Boolean);
    expect(bad).toEqual([]);
  });
});
