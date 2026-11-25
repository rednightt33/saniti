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
import { INDICATORS, SCREENER_REGISTRY } from '../../src/core/registry.ts';
import { IMPLEMENTED_PATTERNS, resolveSignal } from '../../src/core/transforms.ts';
import { OPTS, synth } from './helpers.ts';
import { changeBars, cutsOf } from './cuts.ts';

const cut = (t: TickerBars, n: number): TickerBars => {
  const c = (a: ArrayLike<unknown>) => Array.from(a).slice(0, n) as any;
  return { ticker: t.ticker, dates: t.dates.slice(0, n), bars: { O: c(t.bars.O), H: c(t.bars.H), L: c(t.bars.L), C: c(t.bars.C), V: c(t.bars.V), T: t.dates.slice(0, n) } };
};
const IX = (() => { const t = synth('IHSG', 3, 420); return { ...t, bars: { ...t.bars, V: t.bars.V.map(() => null) } } })();
// CAUD (re-check of 2026-11-25): Three White Soldiers and Three Black Crows fire on none of the first three at any of
// their settings' limits, so the gate could not see a later bar read in them; on CAUD both fire at their defaults
const TICKERS = [synth('CAUA', 11, 420), synth('CAUB', 12, 420), (() => { const t = synth('CAUC', 13, 420); return { ...t, bars: { ...t.bars, V: t.bars.V.map((v, i) => i % 17 === 3 ? 0 : v) } } })(),
  synth('CAUD', 14, 420)];
const same = (a: unknown, b: unknown) => (typeof a === 'number' && Number.isFinite(a) ? a : null) === (typeof b === 'number' && Number.isFinite(b) ? b : null);

/** The first bar where the series on the first n bars differs from the full one, at each cut: the fixed ones (60, 151,
    263, 400 bars) and the bars where the full series changes (cuts.ts: a read of the next bar shows only there, re-check
    of 2026-11-25, recheck2/NEW-1: on the fixed cuts alone 17 of the 20 candlestick patterns shifted one bar ahead
    passed). `onMove`: called when the series changes after the first cut on a ticker (a series that never does cannot
    show a read of a later bar). */
function causal(r: ResolvedSeries, ctx: { index: TickerBars }, onMove?: () => void): string | null {
  for (const t of TICKERS) {
    const full = r.full(tickerCalc(t));
    if (onMove && changeBars(full).some(j => j >= 59 && j <= t.dates.length - 2)) onMove();
    for (const n of cutsOf(full, t.dates.length, [59, 150, 262, 399]).map(c => c + 1)) {
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
    const moved = new Set<string>(), bad = list.map(r => causal(r, ctx, () => moved.add(r.label))).filter(Boolean);
    expect(bad).toEqual([]);
    // each changes on one of the tickers, so a read of a later bar in it can show (cuts.ts)
    expect(list.map(r => r.label).filter(l => !moved.has(l))).toEqual([]);
  });
  it('every pattern signal at its catalog defaults (a candlestick pattern that fires on no ticker there also at its settings\' limits and options)', () => {
    const bad: string[] = [], moved = new Set<string>();
    // a candlestick pattern's settings in the generated catalog (screener-registry.json candles): each number at its
    // minimum and maximum, each option
    const variants = (type: string): Record<string, unknown>[] => (SCREENER_REGISTRY.candles.find(c => c.id === type)?.params ?? [])
      .flatMap((q): Record<string, unknown>[] => q.type === 'enum' ? (q.options ?? []).map(o => ({ [q.key]: o })) : [q.min, q.max].filter(v => typeof v === 'number').map(v => ({ [q.key]: v })));
    for (const type of IMPLEMENTED_PATTERNS) for (const params of [undefined, ...variants(type)]) {
      if (params && moved.has(type)) break;
      const why = causal(resolveSignal({ kind: 'pattern', type, ...(params ? { params } : {}) } as never, 'p', OPTS), ctx, () => moved.add(type));
      if (why) bad.push(why);
    }
    expect(bad).toEqual([]);
    // each pattern fires on one of the tickers in one of its cases, so a read of a later bar in it can show (cuts.ts)
    expect(IMPLEMENTED_PATTERNS.filter(t => !moved.has(t))).toEqual([]);
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
      // the universal operators (OPERATORS.md 2-4, 6, 7, 12-14): a window "before t" must never read t itself or later
      { kind: 'transform', fn: 'vs_average', of: rsi, args: { ma: 'EMA', length: 20, form: 'difference' } },
      { kind: 'transform', fn: 'vs_average', of: vol, args: { ma: 'SMA', length: 20, form: 'percent' } },
      { kind: 'transform', fn: 'percentile', of: rsi, args: { length: 60 } }, { kind: 'transform', fn: 'zscore', of: obv, args: { length: 40 } },
      { kind: 'transform', fn: 'change_pct', of: close, args: { bars: 10 } },
      { kind: 'transform', fn: 'relative', of: close, args: { form: 'ratio', by: { kind: 'indicator', indicator: 'I01', output: 'sma', params: { length: 50 } } } },
      { kind: 'transform', fn: 'slope', of: rsi, args: { length: 20 } }, { kind: 'transform', fn: 'acceleration', of: close, args: { length: 10 } },
      { kind: 'transform', fn: 'distance_to_extreme', of: { kind: 'price', field: 'high' }, args: { extreme: 'highest', length: 50, form: 'percent' } },
    ] as Record<string, unknown>[];
    // the category transforms (EXEC-PINE-INDICATORS) read an output the registry codes in categories, every category and
    // every change between two of them. The public build's registry holds none (today only a lab indicator has one): the
    // test then codes Supertrend's direction (-1 down, 1 up) in categories for itself, so both transforms are read at
    // every cut on every push (re-check of checker C-6, 2026-11-23: they used to drop out of this test)
    let coded = INDICATORS.flatMap(i => i.outputs.filter(o => o.categories?.length).map(o => ({ of: { kind: 'indicator', indicator: i.id, output: o.key }, keys: o.categories!.map(c => c.key) })))[0];
    const st = INDICATORS.find(i => i.outputs.some(o => o.key === 'direction' && !o.categories)), dirOut = st?.outputs.find(o => o.key === 'direction') as { categories?: unknown } | undefined;
    if (!coded && st && dirOut) {
      dirOut.categories = [{ value: -1, key: 'down', label: 'Down' }, { value: 1, key: 'up', label: 'Up' }];
      coded = { of: { kind: 'indicator', indicator: st.id, output: 'direction' }, keys: ['down', 'up'] };
    }
    try {
      expect(coded, 'an output coded in categories (the registry\'s or the test\'s own)').toBeTruthy();
      // one category of several: every category chosen is 1 wherever the input has a value and would hide a read of a
      // later bar (re-check recheck2/NEW-1)
      refs.push({ kind: 'transform', fn: 'in_categories', of: coded!.of, args: { categories: coded!.keys[0] } },
        { kind: 'transform', fn: 'category_change', of: coded!.of, args: { changes: coded!.keys.flatMap(a => coded!.keys.filter(b => b !== a).map(b => `${a}>${b}`)).join(',') } });
      expect(new Set(refs.map(x => x.fn))).toEqual(new Set(METRICS_CATALOG.transforms.map(x => x.fn)));     // every transform of the catalog
      const moved = new Set<string>(), bad = refs.map(x => causal(resolveSeries(x as unknown as MetricRef, 'x', ctx), ctx, () => moved.add(x.fn as string))).filter(Boolean);
      expect(bad).toEqual([]);
      // each changes on one of the tickers, so a read of a later bar in it can show (cuts.ts)
      expect(refs.map(x => x.fn).filter(fn => !moved.has(fn as string))).toEqual([]);
    } finally { if (dirOut && coded?.of.indicator === st?.id) delete dirOut.categories }
  });
});
