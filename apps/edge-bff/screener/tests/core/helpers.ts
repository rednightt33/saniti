/* Shared test material for the core tests: synthetic tickers from the registry generator's deterministic fixture (a
   random walk with drift regimes, report 6.8), a snapshot environment over them for runScreen (the worker's role, in
   memory), and a validation context. No market data: everything here is a pure function of its seeds. */
import * as G from '../../scripts/build-screener-registry.mjs';      // plain JavaScript: typed any
import type { RowRemark, UniverseRow } from '../../src/core/contract.ts';
import { METRICS_CATALOG } from '../../src/core/catalog.ts';
import { SeriesCache, series, tailLength, tickerCalc, universeAttributes } from '../../src/core/metrics.ts';
import type { ResolvedSeries, SeriesContext, TickerBars, TickerCalc } from '../../src/core/metrics.ts';
import type { ScreenEnv } from '../../src/core/screen.ts';
import { availabilityMap } from '../../src/core/validate.ts';
import type { ValidateContext } from '../../src/core/validate.ts';

export const OPTS = { capBudgetMs: 2000 };
export const WITHIN_MAX = 130;

/** A synthetic ticker: `bars` weekday sessions from `start`, the generator's random walk under `seed`. */
export function synth(ticker: string, seed: number, bars = 400, start = '2024-01-01'): TickerBars {
  const B = G.fixture({ seed, bars, start });
  return { ticker, dates: B.T as string[], bars: { O: B.O, H: B.H, L: B.L, C: B.C, V: B.V, T: B.T } };
}
/** The last `n` bars of a ticker (a shorter history ending on the same date). */
export function tailBars(t: TickerBars, n: number, ticker = t.ticker): TickerBars {
  const k = Math.max(0, t.dates.length - n), cut = (a: ArrayLike<unknown>) => Array.from(a).slice(k) as any;
  return { ticker, dates: t.dates.slice(k), bars: { O: cut(t.bars.O), H: cut(t.bars.H), L: cut(t.bars.L), C: cut(t.bars.C), V: cut(t.bars.V), T: t.dates.slice(k) } };
}
/** The first `n` bars (a stale ticker: its last bar is before the others'). */
export function headBars(t: TickerBars, n: number, ticker = t.ticker): TickerBars {
  const cut = (a: ArrayLike<unknown>) => Array.from(a).slice(0, n) as any;
  return { ticker, dates: t.dates.slice(0, n), bars: { O: cut(t.bars.O), H: cut(t.bars.H), L: cut(t.bars.L), C: cut(t.bars.C), V: cut(t.bars.V), T: t.dates.slice(0, n) } };
}
/** The universe row of a ticker as the worker builds it (metrics.ts universeAttributes), with extra remarks. */
export function rowOf(t: TickerBars, E: string, o: Partial<UniverseRow> = {}, extra: RowRemark[] = []): UniverseRow {
  const u = universeAttributes(tickerCalc(t), E);
  const remarks: RowRemark[] = [...(u.stale ? [{ code: 'STALE' as const, last_bar_date: u.last_bar }] : []), ...extra];
  return { ticker: t.ticker, name: `${t.ticker} Tbk`, sector: 'Industrials', industry: 'Machinery', last: u.last, chg_1d_pct: u.chg_1d_pct, adv20_idr: u.adv20_idr,
    first_bar: u.first_bar, last_bar: u.last_bar, bars: u.bars, stale: u.stale, remarks, ...o };
}

export interface MemoryEnv extends ScreenEnv { cache: SeriesCache; sctx: SeriesContext; prewarm(rs: ResolvedSeries[]): void; computed: number }
/** A ScreenEnv over in-memory tickers: the one series path (metrics.ts series) over a SeriesCache and a Calc per
    ticker, as the worker runs it. `prewarm` pins series in the cache (the snapshot); isPrewarmed tells S2 from S3. */
export function memoryEnv(tickers: TickerBars[], index: TickerBars, rows: UniverseRow[], E: string, o: Partial<ScreenEnv> = {}): MemoryEnv {
  const cache = new SeriesCache(1 << 30), sctx: SeriesContext = { versions: { price_data: 'p'.repeat(64), screener_engine: 'e'.repeat(16) }, tailLength: tailLength(WITHIN_MAX), cache };
  const byTicker = new Map(tickers.map(t => [t.ticker, t])), calcs = new Map<string, TickerCalc>(), pinned = new Set<string>();
  const calc = (t: TickerBars) => { let c = calcs.get(t.ticker); if (!c) { c = tickerCalc(t); calcs.set(t.ticker, c) } return c };
  const env: MemoryEnv = {
    ...OPTS, withinMax: WITHIN_MAX, index, catalog: METRICS_CATALOG, evaluationDate: E, rows, ihsgCalendar: index.dates,
    bars: t => byTicker.get(t), cache, sctx, computed: 0,
    series: (r, t) => { const got = series(sctx, calc(t), r); if (got.source === 'dynamic') env.computed++; return got },
    isPrewarmed: r => pinned.has(r.key),
    prewarm: rs => { for (const r of rs) { pinned.add(r.key); for (const t of tickers) series(sctx, calc(t), r, true) } },
    ...o,
  } as MemoryEnv;
  return env;
}

/** A validation context over a set of tickers and the default catalog, every file of the catalog indexed unless `index`
    says otherwise (Phase 1: none of the flow or fundamental files). */
export function vctx(tickers: Iterable<string>, index: Record<string, { columns?: string[] }> = {}, groupings = GROUPINGS): ValidateContext {
  return { limits: { max_conditions: 20, max_metric_filters: 8, within_max: WITHIN_MAX }, capBudgetMs: OPTS.capBudgetMs, tickers: new Set(tickers),
    groupings, metrics: METRICS_CATALOG, availability: availabilityMap(index) };
}
export const GROUPINGS = [
  { key: 'sector', values: [{ value: 'Financials', tickers: 100 }, { value: 'Industrials', tickers: 60 }, { value: 'Energy', tickers: 70 }], unclassified: 3 },
  { key: 'industry', values: [{ value: 'Banks', tickers: 48 }, { value: 'Machinery', tickers: 10 }, { value: 'Coal', tickers: 20 }], unclassified: 3 },
] as const as any;

/** Deterministic pseudo-random numbers for property tests (mulberry32). */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296 };
}
