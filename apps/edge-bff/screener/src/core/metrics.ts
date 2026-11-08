/* Metric reference -> series: the one series(…) path of the Screener (EXEC-SCREENER; report TARGET ARCHITECTURE 6.7
   "One path"). Every technical number is F[key] through the backtest core's Calc.out(key, resolveParams(...)) on the
   ticker's full published history (report I1; 6.5 History: tails are not exact for recursive and cumulative outputs),
   then cut to a tail of tailLength(SCREENER_WITHIN_MAX) bars plus the first and last valid index. The cache key is
   (price_data, screener_engine, the resolved reference): precomputed and dynamic values are the same call made at two
   times (the snapshot's pre-warm at a publication, or a request), so they cannot differ; a cell reports
   'precomputed' for a pre-warmed hit and 'dynamic' otherwise (report 8.5 `source`; is_default is separate). The
   snapshot pre-warms each of the 53 indicators at registry.ts startParams (the registry defaults, except I43 at anchor
   Week: P17 a does not offer its registry default Session, report 6.7), every preset configuration and the declared
   derived series, with series(..., true).
   Pure module (no DOM, no Node API); the worker owns the cache's lifetime (dropped on a version swap). */
import { Calc } from '../../../backtest/src/core/conditions.ts';
import { canonicalJson } from '../../../backtest/src/core/hash.ts';
import { liquidity } from '../../../backtest/src/core/signals.ts';
import type { Bars, Num, Params } from '../../../terminal/src/calc/indicators.ts';
import type { HistoryClass, IndicatorRef, MetricKind, MetricRef, ParamMap, PriceField, PriceRef } from './contract.ts';
import { PRICE_FIELDS } from './contract.ts';
import { ScreenerError } from './errors.ts';
import { inputsOf, isDefaultParams, resolveScreenerParams, screenerIndicator, screenerOutput } from './registry.ts';
import type { BarField, ParamOptions, ScreenerIndicator, ScreenerOutput, Unit } from './registry.ts';
import { resolveTransform } from './transforms.ts';
import { resolveFlow } from './flowmetrics.ts';
import type { FlowBindContext, TickerFlow } from './flowmetrics.ts';

/* ---- a ticker's data ------------------------------------------------------------------------------------------- */

/** One ticker's bars as the snapshot holds them: datafile.priceSeries (its own sessions, oldest first, a row without
    four finite prices dropped), dates 'YYYY-MM-DD' aligned with the bars. `missing` (optional, the worker's snapshot):
    missingInput's answer without reading the bar columns; it must equal scanMissingInput on the same bars. */
export interface TickerBars {
  ticker: string; dates: readonly string[]; bars: Bars; missing?(inputs: readonly BarField[], at: number): BarField | null;
  /** EXEC-SCREENER-FLOW-CANDLES P5a: the ticker's broker rows in the loaded window, its classification and the memo of
      computeFlow answers (the worker's TickerView); a flow series is computed from it (flowmetrics.ts) */
  flow?: TickerFlow;
}
/** A ticker with the backtest core's per-ticker memo of indicator outputs. A TickerCalc lives for one ticker's work (one
    pre-warm pass or one request) and is then dropped: Calc keeps every full output it computed. */
export interface TickerCalc extends TickerBars { calc: Calc }
export const tickerCalc = (t: TickerBars): TickerCalc => ({ ...t, calc: new Calc(t.bars) });

/* ---- resolved references --------------------------------------------------------------------------------------- */

/** A metric reference resolved to one numeric series per ticker: its cache key without the versions (canonical JSON
    of the resolved reference, parameters complete) and how to compute its full series on a ticker's bars. Indicators
    and price fields resolve here; transforms (transforms.ts resolveTransform) and pattern signals (0/1 series,
    transforms.ts resolveSignal) resolve to the same shape, so every series goes through the one series() path. */
export interface ResolvedSeries {
  readonly kind: MetricKind;
  /** canonicalJson(ref): the series' identity in the cache (report 6.7), the versions aside */
  readonly key: string;
  /** the reference as normalized: every parameter and argument complete (validate.ts builds the normalized definition
      from it, so its hash is the same whether a default was sent or left out) */
  readonly ref: MetricRef;
  /** a short name for summaries and logs: 'I13.rsi', 'close', 'pct_distance(I01.sma, ...)' */
  readonly label: string;
  readonly unit: Unit | string | null;
  /** The history class of the series (report 6.8): decides the PRICE_BREAK_IN_LOOKBACK rule (report 6.12). null for a
      bar field (it reads one bar). */
  readonly historyClass: HistoryClass | null;
  /** The bar fields the series needs (registry.ts inputsOf for an indicator; the field itself for a bar field; the
      union of its operands' for a transform): a ticker that lacks one (missingInput) is NA NULL_AT_EVALUATION, not
      INSUFFICIENT_HISTORY (report 6.8, 6.9; TEST PLAN 10b.3 IHSG volume). [] only for an output the chosen options
      leave without any value, which validate.ts refuses before any compute. */
  readonly inputs: readonly BarField[];
  /** What a level of this series compares with (report 6.8 scaling probe): 'close' for a price level, 'volume' for a
      volume level, null when it is not a level (an oscillator, a percent distance). A STATE or EVENT between a bar field
      and this series is offered only when they match. */
  readonly comparableWith: 'close' | 'volume' | null;
  /** price_compare_lag as the right side of a bar-field comparison (report 6.8 lag probe): 1 means the comparison reads
      the series' previous bar (Donchian's prior band; rolling_max(high, n)); the condition then reads the lagged series
      transform lag(x, 1), never a shifted view of the tail (evaluate.ts header). */
  readonly compareLag: { readonly gt: 0 | 1; readonly lt: 0 | 1 };
  /** The bars a value depends on when the reference states it exactly (a pattern: breakout(N) reads N + 1 bars);
      otherwise evaluate.ts lookbackStart derives it from the series' first valid bar. */
  readonly window?: number;
  /** True when every value is a whole number (a count: rising_run). "=" and "!=" are offered only on such a series
      (K7, OPERATORS.md operator 1); a series without the flag is read as continuous. */
  readonly integer?: boolean;
  /** EXEC-SCREENER-FLOW-CANDLES P5a, set exactly on a series that reads a flow indicator (directly or through operators):
      the sessions of broker data it reads (the indicator's own window, flowmetrics.ts indicatorDepth, plus the operators'
      N), null when the probe gives no value; flowOwn the flow indicator's own part. A condition on it is evaluated at
      the stock's last candle with broker data (P10 a) and may read at most the loaded window (K1). */
  readonly flowDepth?: number | null;
  readonly flowOwn?: number | null;
  /** P5b cost: the sessions before the evaluated candle its reader reads, when the series was resolved for a screen
      (condition.ts BindContext.flowLazy): an anchored flow series under it is computed there only. null: every candle
      (an operator that reads the whole history); absent: not resolved for a screen. The worker's cost units read it. */
  readonly flowReach?: number | null;
  /** The output type of OPERATORS.md section 4 the series has when it is a flow output (K, P, Rp, L, H, D, F, B) or a
      transform that keeps its operand's level (lag, ma, rolling_max, rolling_min); absent otherwise (transforms.ts
      outputType then reads the transform). */
  readonly outputKind?: string;
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
  const norm: IndicatorRef = { kind: 'indicator', indicator: indicator.id, params: params as ParamMap, output: output.key };
  return {
    kind: 'indicator', key: canonicalJson(norm), ref: norm, label: `${indicator.id}.${output.key}`,
    unit: output.unit, historyClass: output.history_class, inputs: inputsOf(output, params),
    comparableWith: output.comparable_with, compareLag: output.price_compare_lag,
    indicator, output, params, isDefault: isDefaultParams(indicator, params),
    full: t => t.calc.out(indicator.key, params)[output.key],
  };
}

const BAR: Record<PriceField, BarField> = { open: 'O', high: 'H', low: 'L', close: 'C', volume: 'V' };
/** A bar field of the ticker's own bars (unit price, or volume). */
export function resolvePrice(ref: PriceRef, field: string): ResolvedPrice {
  if (!PRICE_FIELDS.includes(ref.field)) throw new ScreenerError('INVALID_CONDITION', `${field}.field must be one of ${PRICE_FIELDS.join(', ')}.`, `${field}.field`, { allowed: [...PRICE_FIELDS] });
  const col = BAR[ref.field], norm: PriceRef = { kind: 'price', field: ref.field };
  return {
    kind: 'price', key: canonicalJson(norm), ref: norm, label: ref.field, field: ref.field,
    unit: ref.field === 'volume' ? 'volume' : 'price', historyClass: null, inputs: [col],
    comparableWith: ref.field === 'volume' ? 'volume' : 'close', compareLag: { gt: 0, lt: 0 },
    full: t => t.bars[col] as ArrayLike<Num | undefined>,
  };
}

/** The first field of `inputs` the ticker lacks up to bar `at` (no finite non-zero value on bars 0..at: IHSG's volume,
    which is null), or null when it has them all (rows without four finite prices are already dropped by
    datafile.priceSeries, so in practice only volume can be missing). A cell on a series that needs it is NA
    NULL_AT_EVALUATION (evaluate.ts BarView.inputMissing; report 6.8 "each option's volume need"). The worker holds the
    answer per ticker and field in its snapshot (TickerBars.missing), so a lookup of a pre-warmed series reads no bar
    column; otherwise the bars are scanned (scanMissingInput). */
export function missingInput(t: TickerBars, inputs: readonly BarField[], at: number): BarField | null {
  return t.missing ? t.missing(inputs, at) : scanMissingInput(t, inputs, at);
}
/** missingInput by reading the bars (the rule itself). */
export function scanMissingInput(t: TickerBars, inputs: readonly BarField[], at: number): BarField | null {
  for (const f of inputs) {
    const xs = t.bars[f] as ArrayLike<number | null | undefined>;
    let has = false;
    for (let i = 0; i <= at && i < xs.length && !has; i++) { const v = xs[i]; has = typeof v === 'number' && Number.isFinite(v) && v !== 0 }
    if (!has) return f;
  }
  return null;
}

/** What resolving a reference reads besides it: the parameter options (caps), IHSG's bars (vs_index), the loaded broker
    window (P5a) and, for a screen (P5b), the reach of its reader: the sessions before the evaluated candle the reader
    reads (condition.ts sets it from the test, transforms.ts adds its operators' N; null: the whole history). */
export type SeriesResolveContext = ParamOptions & { index?: TickerBars; flow?: FlowBindContext; flowReach?: number | null };
/** Any metric reference that is a numeric series on the ticker's bars: indicator and price here, transform through
    transforms.ts resolveTransform (which resolves its `of` back through this function; `index` = IHSG's bars, read by
    vs_index when it computes, so validation needs none). A pattern is a 0/1 signal, not a value (transforms.ts
    resolveSignal, read by STATE and EVENT tests only); flow, xsection and universe values are per ticker at E, not bar
    series (flowmetrics.ts in Phase 2, xsection.ts, the snapshot's universe attributes); pattern, flow, xsection and
    universe are refused here so no caller reads them as a series. P5a: a flow indicator output is a series of the
    ticker's bars too (flowmetrics.ts resolveFlow: computed by the Terminal's flow.ts on the window's candles, aligned;
    `flow` = the loaded broker window, checked when given). */
export function resolveSeries(ref: MetricRef, field: string, ctx: SeriesResolveContext): ResolvedSeries {
  if (!ref || typeof ref !== 'object' || Array.isArray(ref)) throw new ScreenerError('INVALID_CONDITION', `${field} must be a metric reference.`, field);
  let r: ResolvedSeries;
  switch (ref.kind) {
    case 'indicator': r = resolveIndicator(ref, field, ctx); break;
    case 'price': r = resolvePrice(ref, field); break;
    case 'transform': r = resolveTransform(ref, field, ctx); break;
    case 'flow': r = resolveFlow(ref, field, ctx); break;
    default: throw new ScreenerError('INVALID_CONDITION', `${field}: a ${JSON.stringify((ref as { kind?: unknown }).kind)} reference is not a series on the ticker's bars; use it where its test form allows it.`, `${field}.kind`);
  }
  // P5b cost: a flow-reading series resolved for a screen carries the reach it was resolved under (its cost units)
  return r.flowDepth !== undefined && ctx.flowReach !== undefined ? { ...r, flowReach: ctx.flowReach } : r;
}

/** The series `r` read one bar earlier: transform lag(r, 1), resolved like any transform (computed on the full series,
    then tailed; same key as a lag written in a request). A bar-field comparison reads it where the series' compareLag
    says so (Donchian's prior band, report 6.8). */
export const laggedSeries = (r: ResolvedSeries, field: string, ctx: SeriesResolveContext): ResolvedSeries =>
  resolveTransform({ kind: 'transform', fn: 'lag', of: r.ref, args: { bars: 1 } }, field, ctx);

/* ---- universe attributes (report 6.7 "universe attributes", 6.12; API CONTRACT 8.4 universe body) ------------------ */

/** The attributes of one ticker's universe row at its evaluation bar `at` (its last bar on or before E): last close,
    the 1-day change in percent, ADV20 = the backtest core's liquidity() (SMA20 of close x volume, signals.ts:174) at
    `at`, first and last bar, bar count and the stale flag (last bar before E). Values through no rounding here (the
    wire rounds); null where the bars cannot give them (fewer than 2 bars for the change, fewer than 20 for ADV20). */
export function universeAttributes(t: TickerCalc, evaluationDate: string): { last: number | null; chg_1d_pct: number | null; adv20_idr: number | null; first_bar: string; last_bar: string; bars: number; stale: boolean; at: number } {
  let at = t.dates.length - 1;
  while (at >= 0 && t.dates[at] > evaluationDate) at--;
  const C = t.bars.C, c = at >= 0 ? C[at] : null, c0 = at >= 1 ? C[at - 1] : null;
  const ok = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
  const adv = at >= 0 ? liquidity(t.calc)[at] : null;
  return {
    last: ok(c) ? c : null,
    chg_1d_pct: ok(c) && ok(c0) && c0 !== 0 ? (c / c0 - 1) * 100 : null,
    adv20_idr: ok(adv) ? adv : null,
    first_bar: t.dates[0], last_bar: at >= 0 ? t.dates[at] : t.dates[0], bars: at + 1,
    stale: at >= 0 && t.dates[at] < evaluationDate, at,
  };
}

/* ---- tails ------------------------------------------------------------------------------------------------------ */

/** The tail the snapshot keeps per series and ticker (report 6.7, 8.9): the longest `within` plus the previous bar a
    cross reads, derived from the one limit SCREENER_WITHIN_MAX, never written separately. It holds no spare bar, so a
    lagged side (price_compare_lag 1) must be the lagged series itself (transform lag, tailed after the shift), not a
    shifted read of this tail (evaluate.ts header). */
export const tailLength = (withinMax: number): number => {
  if (!(Number.isInteger(withinMax) && withinMax >= 1)) throw new RangeError(`tailLength: within_max must be a whole number of at least 1, not ${withinMax}`);
  return withinMax + 1;
};
/** The last bars of one ticker's series (`length` of them, or, with everyValue, from its first value if that is
    earlier): values[i - from] is bar i (NaN for no value); n = the ticker's bar count;
    firstValid / lastValid = the first and last bar of the FULL series with a value (-1 when none), so a reader can tell
    INSUFFICIENT_HISTORY (no value up to the evaluation bar) from NULL_AT_EVALUATION. */
export interface Tail { readonly n: number; readonly from: number; readonly values: Float64Array; readonly firstValid: number; readonly lastValid: number }
export function tailOf(s: ArrayLike<Num | undefined>, length: number, everyValue = false): Tail {
  const n = s.length, ok = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
  let firstValid = -1, lastValid = -1;
  for (let i = 0; i < n; i++) if (ok(s[i])) { if (firstValid < 0) firstValid = i; lastValid = i }
  // everyValue: the tail starts no later than the first value (a flow series: its values are the loaded window's, read
  // at the last candle with broker data, however far behind the prices that is; condition.ts read)
  const from = Math.max(0, everyValue && firstValid >= 0 ? Math.min(n - length, firstValid) : n - length), values = new Float64Array(n - from);
  for (let i = from; i < n; i++) { const v = s[i]; values[i - from] = ok(v) ? v : NaN }
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
    tailed (a flow-reading series from its first value at the latest, so a test at the last candle with broker data
    reads it whole however far the broker data is behind the prices) and cached. `prewarm` pins the entry as part of the publication's snapshot. source: 'precomputed' when the
    tail comes from a pinned (pre-warmed) entry, else 'dynamic'. */
export function series(ctx: SeriesContext, t: TickerCalc, r: ResolvedSeries, prewarm = false): { tail: Tail; source: SeriesSource } {
  const key = seriesKey(ctx.versions, r), hit = ctx.cache.get(key, t.ticker);
  if (hit) return { tail: hit.tail, source: hit.pinned ? 'precomputed' : 'dynamic' };
  // a flow-reading series keeps every value in its tail (it is read at the stock's last candle with broker data, P10 a)
  const tail = tailOf(r.full(t), ctx.tailLength, r.flowDepth !== undefined);
  ctx.cache.set(key, t.ticker, tail, prewarm);
  return { tail, source: prewarm ? 'precomputed' : 'dynamic' };
}
