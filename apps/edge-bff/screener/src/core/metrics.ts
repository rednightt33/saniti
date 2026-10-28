/* Metric reference -> series: the one series(…) path of the Screener (EXEC-SCREENER; report TARGET ARCHITECTURE 6.7
   "One path"). Every technical number is F[key] through the backtest core's Calc.out(key, resolveParams(...)) on the
   ticker's full published history (report I1; 6.5 History: tails are not exact for recursive and cumulative outputs),
   then cut to a tail of tailLength(SCREENER_WITHIN_MAX) bars plus the first and last valid index. The cache key is
   (price_data, screener_engine, the resolved reference): precomputed and dynamic values are the same call made at two
   times (the snapshot's pre-warm at a publication, or a request), so they cannot differ; a cell reports
   'precomputed' for a pre-warmed hit and 'dynamic' otherwise (report 8.5 `source`; is_default is separate).
   Pure module (no DOM, no Node API); the worker owns the cache's lifetime (dropped on a version swap). */
import { Calc } from '../../../backtest/src/core/conditions.ts';
import { canonicalJson } from '../../../backtest/src/core/hash.ts';
import type { Bars, Num, Params } from '../../../terminal/src/calc/indicators.ts';
import type { HistoryClass, IndicatorRef, MetricKind, MetricRef, PriceField, PriceRef } from './contract.ts';
import { PRICE_FIELDS } from './contract.ts';
import { ScreenerError } from './errors.ts';
import { isDefaultParams, resolveScreenerParams, screenerIndicator, screenerOutput } from './registry.ts';
import type { ParamOptions, ScreenerIndicator, ScreenerOutput, Unit } from './registry.ts';

/* ---- a ticker's data ------------------------------------------------------------------------------------------- */

/** One ticker's bars as the snapshot holds them: datafile.priceSeries (its own sessions, oldest first, a row without
    four finite prices dropped), dates 'YYYY-MM-DD' aligned with the bars. */
export interface TickerBars { ticker: string; dates: readonly string[]; bars: Bars }
/** A ticker with the backtest core's per-ticker memo of indicator outputs. A TickerCalc lives for one ticker's work (one
    pre-warm pass or one request) and is then dropped: Calc keeps every full output it computed. */
export interface TickerCalc extends TickerBars { calc: Calc }
export const tickerCalc = (t: TickerBars): TickerCalc => ({ ...t, calc: new Calc(t.bars) });

/* ---- resolved references --------------------------------------------------------------------------------------- */

/** A metric reference resolved to one numeric series per ticker: its cache key without the versions (canonical JSON
    of the resolved reference, parameters complete) and how to compute its full series on a ticker's bars. Indicators
    and price fields resolve here; transforms (transforms.ts) and pattern signals (0/1 series) resolve to the same shape. */
export interface ResolvedSeries {
  readonly kind: MetricKind;
  readonly key: string;
  readonly unit: Unit | string | null;
  /** The history class of the series (report 6.8): decides the PRICE_BREAK_IN_LOOKBACK rule (report 6.12). null for a
      bar field (it reads one bar). */
  readonly historyClass: HistoryClass | null;
  full(t: TickerCalc): ArrayLike<Num | undefined>;
}
export interface ResolvedIndicator extends ResolvedSeries {
  readonly kind: 'indicator';
  readonly indicator: ScreenerIndicator; readonly output: ScreenerOutput;
  readonly params: Params; readonly isDefault: boolean;
}
export interface ResolvedPrice extends ResolvedSeries { readonly kind: 'price'; readonly field: PriceField }

/** An indicator reference with its parameters checked and completed (registry.ts resolveScreenerParams), or the
    ScreenerError naming `${field}.indicator`, `${field}.output` or `${field}.params.<key>`. */
export function resolveIndicator(ref: IndicatorRef, field: string, opts: ParamOptions): ResolvedIndicator {
  const indicator = screenerIndicator(ref.indicator, `${field}.indicator`);
  const output = screenerOutput(indicator, ref.output, `${field}.output`);
  const params = resolveScreenerParams(indicator, ref.params, `${field}.params`, opts);
  const key = canonicalJson({ kind: 'indicator', indicator: indicator.id, params, output: output.key });
  return {
    kind: 'indicator', key, unit: output.unit, historyClass: output.history_class, indicator, output, params,
    isDefault: isDefaultParams(indicator, params),
    full: t => t.calc.out(indicator.key, params)[output.key],
  };
}

const BAR: Record<PriceField, keyof Bars> = { open: 'O', high: 'H', low: 'L', close: 'C', volume: 'V' };
/** A bar field of the ticker's own bars (unit price, or volume). */
export function resolvePrice(ref: PriceRef, field: string): ResolvedPrice {
  if (!PRICE_FIELDS.includes(ref.field)) throw new ScreenerError('INVALID_CONDITION', `${field}.field must be one of ${PRICE_FIELDS.join(', ')}.`, `${field}.field`, { allowed: [...PRICE_FIELDS] });
  const col = BAR[ref.field];
  return {
    kind: 'price', key: canonicalJson({ kind: 'price', field: ref.field }), field: ref.field,
    unit: ref.field === 'volume' ? 'volume' : 'price', historyClass: null,
    full: t => t.bars[col] as ArrayLike<Num | undefined>,
  };
}

/** Any metric reference that is a numeric series on the ticker's bars. Implemented: indicator, price. transform ->
    transforms.ts resolveTransform; pattern -> a 0/1 series (evaluate.ts patternSignal); flow, xsection and universe
    are not bar series (flowmetrics.ts in Phase 2, xsection.ts, the snapshot's universe attributes) and are refused
    here so a caller cannot read them as one. */
export function resolveSeries(ref: MetricRef, field: string, opts: ParamOptions): ResolvedSeries {
  if (!ref || typeof ref !== 'object') throw new ScreenerError('INVALID_CONDITION', `${field} must be a metric reference.`, field);
  switch (ref.kind) {
    case 'indicator': return resolveIndicator(ref, field, opts);
    case 'price': return resolvePrice(ref, field);
    case 'transform': case 'pattern': throw new Error(`not implemented: resolveSeries(${ref.kind})`);
    default: throw new ScreenerError('INVALID_CONDITION', `${field}.kind ${JSON.stringify((ref as { kind?: unknown }).kind)} is not a series on the ticker's bars here.`, `${field}.kind`);
  }
}

/* ---- tails ------------------------------------------------------------------------------------------------------ */

/** The tail the snapshot keeps per series and ticker (report 6.7, 8.9): the longest `within` plus the previous bar a
    cross reads, derived from the one limit SCREENER_WITHIN_MAX, never written separately. */
export const tailLength = (withinMax: number): number => {
  if (!(Number.isInteger(withinMax) && withinMax >= 1)) throw new RangeError(`tailLength: within_max must be a whole number of at least 1, not ${withinMax}`);
  return withinMax + 1;
};
/** The last bars of one ticker's series: values[i - from] is bar i (NaN for no value); n = the ticker's bar count;
    firstValid / lastValid = the first and last bar of the FULL series with a value (-1 when none), so a reader can tell
    INSUFFICIENT_HISTORY (no value up to the evaluation bar) from NULL_AT_EVALUATION. */
export interface Tail { readonly n: number; readonly from: number; readonly values: Float64Array; readonly firstValid: number; readonly lastValid: number }
export function tailOf(s: ArrayLike<Num | undefined>, length: number): Tail {
  const n = s.length, from = Math.max(0, n - length), values = new Float64Array(n - from);
  let firstValid = -1, lastValid = -1;
  for (let i = 0; i < n; i++) {
    const v = s[i], ok = typeof v === 'number' && Number.isFinite(v);
    if (ok) { if (firstValid < 0) firstValid = i; lastValid = i }
    if (i >= from) values[i - from] = ok ? v as number : NaN;
  }
  return { n, from, values, firstValid, lastValid };
}
const TAIL_OVERHEAD = 64;
export const tailBytes = (t: Tail): number => t.values.byteLength + TAIL_OVERHEAD;

/* ---- the cache and the one path --------------------------------------------------------------------------------- */

export interface DataVersions { price_data: string; screener_engine: string }
/** The full cache key of report 6.7: (price_data, screener_engine, resolved reference); the ticker is the second level. */
export const seriesKey = (v: DataVersions, r: ResolvedSeries): string => canonicalJson([v.price_data, v.screener_engine, r.key]);

interface Entry { pinned: boolean; tails: Map<string, Tail>; bytes: number }
/** Series tails per (key, ticker). Pinned entries are the publication's snapshot (pre-warmed at a publication, report 6.7)
    and never evicted; the others form the custom-parameter LRU bounded by maxBytes (SCREENER_CACHE_BYTES), whole keys
    evicted least recently used first. A version swap drops everything (clear). Partial per-ticker entries are allowed
    (only the planner's survivors are computed). */
export class SeriesCache {
  private entries = new Map<string, Entry>();
  private lruBytes = 0;
  readonly maxBytes: number;
  constructor(maxBytes: number) {
    if (!(Number.isFinite(maxBytes) && maxBytes >= 0)) throw new RangeError(`SeriesCache: maxBytes must be a number of at least 0, not ${maxBytes}`);
    this.maxBytes = maxBytes;
  }
  get(key: string, ticker: string): { tail: Tail; pinned: boolean } | undefined {
    const e = this.entries.get(key), tail = e?.tails.get(ticker);
    if (!e || !tail) return undefined;
    if (!e.pinned) { this.entries.delete(key); this.entries.set(key, e) }       // most recently used last
    return { tail, pinned: e.pinned };
  }
  set(key: string, ticker: string, tail: Tail, pinned: boolean): void {
    let e = this.entries.get(key);
    if (!e) { e = { pinned, tails: new Map(), bytes: 0 }; this.entries.set(key, e) }
    else if (pinned && !e.pinned) { this.lruBytes -= e.bytes; e.pinned = true }
    const old = e.tails.get(ticker), delta = tailBytes(tail) - (old ? tailBytes(old) : 0);
    e.tails.set(ticker, tail); e.bytes += delta;
    if (!e.pinned) { this.lruBytes += delta; this.evict(key) }
  }
  private evict(keep: string): void {
    for (const [k, e] of this.entries) {
      if (this.lruBytes <= this.maxBytes) return;
      if (e.pinned || k === keep) continue;
      this.entries.delete(k); this.lruBytes -= e.bytes;
    }
  }
  clear(): void { this.entries.clear(); this.lruBytes = 0 }
  /** Bytes of the LRU part (pinned snapshot entries not counted) and of everything. */
  get bytes(): { lru: number; total: number } {
    let total = 0; for (const e of this.entries.values()) total += e.bytes;
    return { lru: this.lruBytes, total };
  }
}

export interface SeriesContext { versions: DataVersions; tailLength: number; cache: SeriesCache }
export type SeriesSource = 'precomputed' | 'dynamic';
/** THE series path (report 6.7): the cached tail of `r` on ticker `t`, or on a miss its full series through Calc,
    tailed and cached. `prewarm` pins the entry as part of the publication's snapshot. source: 'precomputed' when the
    tail comes from a pinned (pre-warmed) entry, else 'dynamic'. */
export function series(ctx: SeriesContext, t: TickerCalc, r: ResolvedSeries, prewarm = false): { tail: Tail; source: SeriesSource } {
  const key = seriesKey(ctx.versions, r), hit = ctx.cache.get(key, t.ticker);
  if (hit) return { tail: hit.tail, source: hit.pinned ? 'precomputed' : 'dynamic' };
  const tail = tailOf(r.full(t), ctx.tailLength);
  ctx.cache.set(key, t.ticker, tail, prewarm);
  return { tail, source: prewarm ? 'precomputed' : 'dynamic' };
}
