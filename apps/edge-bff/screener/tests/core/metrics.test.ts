/* The one series path (report TARGET ARCHITECTURE 6.7; TEST PLAN 10b.2 "Precomputed vs dynamic"): explicit registry
   defaults give the same key and bit-identical tails as no parameters, for all 53; a custom length is computed by F
   through Calc and equals a direct F call bit for bit; a tail holds exactly the full series' last bars; pre-warmed
   entries report 'precomputed' and survive the LRU, custom ones report 'dynamic' and are evicted by bytes. */
import { describe, expect, it } from 'vitest';
import { F } from '../../../terminal/src/calc/indicators.ts';
import * as G from '../../scripts/build-screener-registry.mjs';      // the generator's deterministic fixture
import { INDICATORS, defaultParams, capOf, screenerIndicator } from '../../src/core/registry.ts';
import { SeriesCache, resolveIndicator, resolvePrice, resolveSeries, series, seriesKey, tailLength, tailOf, tickerCalc } from '../../src/core/metrics.ts';
import { ScreenerError } from '../../src/core/errors.ts';

const OPTS = { capBudgetMs: 2000 };
const B = G.fixture({ bars: 700 });
const T = { ticker: 'SYN', dates: B.T as string[], bars: B };
const V = { price_data: 'p'.repeat(64), screener_engine: 'e'.repeat(16) };
const ctx = (maxBytes = 1 << 30) => ({ versions: V, tailLength: tailLength(130), cache: new SeriesCache(maxBytes) });
const same = (a: Float64Array, b: Float64Array) => a.length === b.length && a.every((v, i) => Object.is(v, b[i]));

describe('series()', () => {
  it('explicit defaults hit the same key and give bit-identical tails, for all 53 indicators and 76 outputs', () => {
    const c = ctx();
    let outputs = 0;
    for (const r of INDICATORS) for (const o of r.outputs) {
      const implicit = resolveIndicator({ kind: 'indicator', indicator: r.id, output: o.key }, 'm', OPTS);
      const explicit = resolveIndicator({ kind: 'indicator', indicator: r.id, output: o.key, params: defaultParams(r) as Record<string, number | string | boolean> }, 'm', OPTS);
      expect(explicit.key).toBe(implicit.key);
      expect(seriesKey(V, explicit)).toBe(seriesKey(V, implicit));
      expect([implicit.isDefault, explicit.isDefault]).toEqual([true, true]);
      const warm = series(c, tickerCalc(T), implicit, true);
      const hit = series(c, tickerCalc(T), explicit);
      expect(hit.source).toBe('precomputed');
      expect(hit.tail).toBe(warm.tail);
      const fresh = series(ctx(), tickerCalc(T), explicit);                 // another cache: computed again, same doubles
      expect(fresh.source).toBe('dynamic');
      expect(same(fresh.tail.values, warm.tail.values)).toBe(true);
      outputs++;
    }
    expect(outputs).toBe(76);
  });

  it('RSI(7) is dynamic, not default, and equals F.rsi with length 7 bit for bit', () => {
    const r = resolveIndicator({ kind: 'indicator', indicator: 'I13', params: { length: 7 }, output: 'rsi' }, 'm', OPTS);
    expect([r.isDefault, r.params]).toEqual([false, { length: 7, source: 'close' }]);
    const got = series(ctx(), tickerCalc(T), r);
    expect(got.source).toBe('dynamic');
    const direct = F.rsi(B, { length: 7, source: 'close' }).rsi;
    expect(same(got.tail.values, tailOf(direct, 131).values)).toBe(true);
    expect(got.tail.values.length).toBe(131);
  });

  it('refuses a custom length above the derived cap with PARAM_OUT_OF_RANGE', () => {
    const cap = capOf(screenerIndicator('I19').params[0], OPTS.capBudgetMs)!;
    let e: unknown;
    try { resolveIndicator({ kind: 'indicator', indicator: 'I19', params: { length: cap + 1 }, output: 'cci' }, 'definition.conditions[0].test.metric', OPTS) } catch (x) { e = x }
    expect(e).toBeInstanceOf(ScreenerError);
    expect([(e as ScreenerError).code, (e as ScreenerError).field]).toEqual(['PARAM_OUT_OF_RANGE', 'definition.conditions[0].test.metric.params.length']);
  });

  it('a tail is the full series\' last bars, with the first and last valid bar of the full series', () => {
    const full = F.sma(B, { length: 20, source: 'close' }).sma;
    const t = tailOf(full, 131);
    expect([t.n, t.from, t.firstValid, t.lastValid]).toEqual([700, 569, 19, 699]);
    for (let i = t.from; i < t.n; i++) expect(Object.is(t.values[i - t.from], full[i] as number)).toBe(true);
    const short = tailOf([null, null, 3, null], 131);
    expect([short.from, short.firstValid, short.lastValid, Number.isNaN(short.values[3])]).toEqual([0, 2, 2, true]);
    expect(() => tailLength(0)).toThrow(RangeError);
  });

  it('price fields are series of the bars; flow, xsection and universe values are refused as series', () => {
    const close = resolvePrice({ kind: 'price', field: 'close' }, 'm');
    expect(same(series(ctx(), tickerCalc(T), close).tail.values, tailOf(B.C, 131).values)).toBe(true);
    for (const ref of [{ kind: 'universe', attr: 'last' }, { kind: 'xsection', metric: 'return_rank' }] as const) {
      let e: unknown;
      try { resolveSeries(ref, 'm', OPTS) } catch (x) { e = x }
      expect((e as ScreenerError).code).toBe('INVALID_CONDITION');
    }
  });
});

describe('SeriesCache', () => {
  it('keeps pinned snapshot entries, evicts the least recently used custom ones by bytes, and clears on a swap', () => {
    const one = tailOf(new Array(131).fill(1), 131), bytes = one.values.byteLength + 64;
    const c = new SeriesCache(2 * bytes);
    c.set('snap', 'A', one, true);
    c.set('k1', 'A', one, false); c.set('k2', 'A', one, false);
    c.get('k1', 'A');                                                       // k1 is now the most recent
    c.set('k3', 'A', one, false);                                           // over budget: k2 goes
    expect([!!c.get('snap', 'A'), !!c.get('k1', 'A'), !!c.get('k2', 'A'), !!c.get('k3', 'A')]).toEqual([true, true, false, true]);
    expect(c.bytes.lru).toBe(2 * bytes);
    c.clear();
    expect([c.get('snap', 'A'), c.bytes.total]).toEqual([undefined, 0]);
  });
});
