/* Condition arithmetic over F outputs and bar fields, and the pattern signals (EXEC-SCREENER; report TARGET
   ARCHITECTURE 6.9 "Metric references", 6.9.1 operator mapping). These are not formulas: a transform combines series
   that F or the bars already give, with the exported reference helpers of indicators.ts (sma, ema) where it needs an
   average, and a pattern reuses the backtest core's PRICE_ACTION / priceActionCondition / bullishDivergence
   (conditions.ts:124-190) or a registry output where one exists. A screener file never defines an indicator kernel
   (report I1); a new indicator is a registry release (P6), never a transform.
   Every transform runs on the FULL series and is then tailed by metrics.ts series() (report 6.7: "contract-declared
   derived series, computed on the full series and then tailed"), so a recursive input (an EMA of OBV) is exact.
   The valid `fn` and pattern `type` values, their arguments and ranges come from screener-metrics.json (catalog.ts),
   never from a list in code; the functions below are what each id computes (catalog.ts catalogProblems fails when the
   two disagree: IMPLEMENTED). Output arrays are aligned with the bars; null where an input is missing (the
   indicators.ts convention). Worker-side module. */
import { compare, priceActionCondition } from '../../../backtest/src/core/conditions.ts';
import type { PriceActionCondition } from '../../../backtest/src/core/conditions.ts';
import { asOf } from '../../../backtest/src/core/datafile.ts';
import { canonicalJson } from '../../../backtest/src/core/hash.ts';
import { ema, isN, sma } from '../../../terminal/src/calc/indicators.ts';
import type { Num } from '../../../terminal/src/calc/indicators.ts';
import type { HistoryClass, IndicatorRef, MetricRef, ParamMap, PatternRef, PriceField, TransformRef } from './contract.ts';
import { ScreenerError } from './errors.ts';
import { METRICS_CATALOG, metricSpec, resolveCatalogParams, transformSpec } from './catalog.ts';
import { BAR_FIELDS, screenerIndicator, screenerOutput } from './registry.ts';
import type { BarField, ParamOptions } from './registry.ts';
import { resolveIndicator, resolveSeries } from './metrics.ts';
import type { ResolvedSeries, TickerBars, TickerCalc } from './metrics.ts';
import type { FlowBindContext } from './flowmetrics.ts';

type In = ArrayLike<Num | undefined>;
export type Series = Num[];
const nul = (n: number): Series => new Array(n).fill(null);
const at = (x: In, i: number): number | null => { const v = x[i]; return isN(v) ? v : null };
const whole = (n: number, what: string, min = 0) => { if (!(Number.isInteger(n) && n >= min)) throw new RangeError(`${what} must be a whole number of at least ${min}, not ${n}`) };

/* ---- the arithmetic ------------------------------------------------------------------------------------------------ */

/** pct_distance(of, base = close): (base / of - 1) x 100 per bar (the prototype's line rule, report 6.9.1); null where
    either is missing or of is 0. */
export function pctDistance(base: In, of: In): Series {
  const n = base.length, o = nul(n);
  for (let i = 0; i < n; i++) { const b = at(base, i), x = at(of, i); if (b !== null && x !== null && x !== 0) o[i] = (b / x - 1) * 100 }
  return o;
}

/** band_position(close, upper, lower): (close - lower) / (upper - lower) x 100 per bar; null at zero width (raw
    doubles, no epsilon: report 6.9.1 band row, NA NULL_AT_EVALUATION only at zero width) or a missing input. */
export function bandPosition(close: In, upper: In, lower: In): Series {
  const n = close.length, o = nul(n);
  for (let i = 0; i < n; i++) {
    const c = at(close, i), u = at(upper, i), l = at(lower, i);
    if (c === null || u === null || l === null || u - l === 0) continue;
    o[i] = (c - l) / (u - l) * 100;
  }
  return o;
}

/** lag(x, bars): x[i - bars] (null before). The prototype's "rising" is STATE x gt lag(x, 5) for the line shape, 21 for
    price_ma, 20 for the cumulative lines (report 6.9.1). */
export function lag(x: In, bars: number): Series {
  whole(bars, 'lag: bars');
  const n = x.length, o = nul(n);
  for (let i = bars; i < n; i++) o[i] = at(x, i - bars);
  return o;
}

/** change(x, bars): x[i] - x[i - bars] (absolute; null when either is missing). */
export function change(x: In, bars: number): Series {
  whole(bars, 'change: bars', 1);
  const n = x.length, o = nul(n);
  for (let i = bars; i < n; i++) { const a = at(x, i), b = at(x, i - bars); if (a !== null && b !== null) o[i] = a - b }
  return o;
}

/** The roll rule of indicators.ts (`roll`, `highest`, `lowest`): a value over the last n valid consecutive values,
    null until n of them; a missing value restarts the window. Computed with a monotonic deque, O(N) whatever n. */
function rollingExtreme(x: In, n: number, max: boolean): Series {
  whole(n, 'rolling window', 1);
  const N = x.length, o = nul(N), dq = new Int32Array(N);
  let head = 0, tail = 0, run = 0;
  for (let i = 0; i < N; i++) {
    const v = at(x, i);
    if (v === null) { head = tail = 0; run = 0; continue }
    run++;
    while (tail > head && (max ? (x[dq[tail - 1]] as number) <= v : (x[dq[tail - 1]] as number) >= v)) tail--;
    dq[tail++] = i;
    while (dq[head] <= i - n) head++;
    if (run >= n) o[i] = x[dq[head]] as number;
  }
  return o;
}
/** rolling_max(x, n) / rolling_min(x, n): the maximum / minimum over [i - n + 1, i], today included (hi52 / lo52, report
    6.9.1); a missing value restarts the window (the indicators.ts roll rule). As the rhs of a bar-field comparison its
    lag comes from the lag probe (catalog compare_lag: `close > rolling_max(high, n)` reads the previous bar, so it equals
    core breakout); as a VALUE (pct_distance) it has no lag. */
export const rollingMax = (x: In, n: number): Series => rollingExtreme(x, n, true);
export const rollingMin = (x: In, n: number): Series => rollingExtreme(x, n, false);

/** rising_run(x): the number of consecutive bars ending at i with x[t] > x[t - 1]; 0 when x[i] <= x[i - 1]; null when
    x[i] or x[i - 1] is missing. The legacy MACD "hup" is STATE rising_run(histogram) gt 2 (report 6.9.1). */
export function risingRun(x: In): Series {
  const n = x.length, o = nul(n);
  for (let i = 1; i < n; i++) {
    const a = at(x, i), b = at(x, i - 1);
    if (a === null || b === null) continue;
    o[i] = a > b ? (o[i - 1] ?? 0) + 1 : 0;
  }
  return o;
}

/** ma(x, type, n): indicators.ts sma (type 'SMA') or ema (type 'EMA', seeded with the SMA of its first n valid values),
    the reference helpers, never a copy. The cumulative lines' "above average" is EMA as the prototype computes it
    (report 6.9.1 cum row: label changed from "average" to "EMA"). */
export function ma(x: In, type: 'SMA' | 'EMA', n: number): Series {
  whole(n, 'ma: length', 1);
  const xs = Array.from(x as ArrayLike<number | null | undefined>);
  return type === 'SMA' ? sma(xs, n) : ema(xs, n);
}

/** ratio(a, b): a / b; null where b is 0 or either is missing (volspike as a VALUE: ratio(volume, lag(ma(volume, SMA,
    len), 1)), report 6.9.1). */
export function ratio(a: In, b: In): Series {
  const n = a.length, o = nul(n);
  for (let i = 0; i < n; i++) { const x = at(a, i), y = at(b, i); if (x !== null && y !== null && y !== 0) o[i] = x / y }
  return o;
}

/** vs_index(close, index, d): (close[i] / close[i - d] - index[i] / index[i - d]) x 100, the prototype's `rs` (equal to
    (close return - index return) in percentage points), on the ticker's own bars with IHSG's close aligned to the
    ticker's dates by datafile.asOf (report 6.9 rs_rank note); null where an input is missing or a base is 0. */
export function vsIndex(close: In, indexAligned: In, d: number): Series {
  whole(d, 'vs_index: window', 1);
  const n = close.length, o = nul(n);
  for (let i = d; i < n; i++) {
    const c = at(close, i), c0 = at(close, i - d), x = at(indexAligned, i), x0 = at(indexAligned, i - d);
    if (c === null || c0 === null || x === null || x0 === null || c0 === 0 || x0 === 0) continue;
    o[i] = (c / c0 - x / x0) * 100;
  }
  return o;
}

/* ---- the universal operators (EXEC-SCREENER-FLOW-CANDLES P2; verification/screener/OPERATORS.md, approved by the user
   2026-11-07, K4). Each one is a series of the same bars, computed on the full series and then tailed like every
   transform, so a chain (a percentile of a change of an indicator) is exact. A window "before t" is t-N .. t-1 (today
   excluded: today is compared with its own past and never dilutes it, OPERATORS.md 1); a window "ending at t" is
   t-N+1 .. t. A missing value is never read as 0. ---------------------------------------------------------------- */

/** The index of the first bar with a value (-1 when none). */
function firstValue(x: In): number { for (let i = 0; i < x.length; i++) if (at(x, i) !== null) return i; return -1 }
/** The number of consecutive bars ending at i whose values are all exactly equal (0 where x[i] is missing). A window
    lying inside such a run is flat: its spread and slope are exactly 0, whatever the floating-point arithmetic of the
    formula gives for a constant that is not a binary fraction (QA1 2026-11-07, D1/D2: z-scores and slopes of about
    1e-17 instead of "no value" and 0). */
function equalRun(x: In): Int32Array {
  const N = x.length, r = new Int32Array(N);
  for (let i = 0; i < N; i++) { const v = at(x, i); if (v === null) continue; r[i] = i > 0 && at(x, i - 1) === v ? r[i - 1] + 1 : 1 }
  return r;
}

/** Operator 2 (Historical Average): x against its own average over the N sessions before t. A_t = SMA or EMA of x as
    indicators.ts computes it (ma above), read one session back: lag(ma(x), 1), the average of t-N .. t-1. difference
    x_t - A_t; ratio x_t / A_t; percent 100 x (x_t / A_t - 1). null where x_t or A_t is missing; ratio and percent also
    where A_t <= 0 (a ratio to a zero or negative average has no meaning). */
export function vsAverage(x: In, type: 'SMA' | 'EMA', n: number, form: 'difference' | 'ratio' | 'percent'): Series {
  const a = lag(ma(x, type, n), 1), N = x.length, o = nul(N), run = equalRun(x);
  for (let i = 0; i < N; i++) {
    const v = at(x, i);
    let m = at(a, i);
    if (v === null || m === null) continue;
    // a flat window (today and the N sessions before it all equal): the average IS today's value. The SMA of a constant
    // that is not a binary fraction can come out an ulp off (QA1 D1 class: a degenerate window must read exactly
    // degenerate), which would make "above its average" pass on a flat series; the EMA keeps its own seeded value
    if (type === 'SMA' && run[i] > n) m = v;
    if (form === 'difference') o[i] = v - m;
    else if (m > 0) o[i] = form === 'ratio' ? v / m : (v / m - 1) * 100;
  }
  return o;
}

/** Operator 3 (Historical Percentile, own history), mid-rank: 100 x (#(v < x_t) + 0.5 x #(v = x_t)) / #v, v = the
    non-missing values of x in the N sessions before t. null where x_t is missing, where t - N is before the first value
    of x (fewer than N sessions of history), or where the window holds no value. */
export function percentileOwn(x: In, n: number): Series {
  whole(n, 'percentile: length', 1);
  const N = x.length, o = nul(N), first = firstValue(x);
  if (first < 0) return o;
  for (let t = first + n; t < N; t++) {
    const v = at(x, t);
    if (v === null) continue;
    let below = 0, equal = 0, count = 0;
    for (let j = t - n; j < t; j++) { const w = at(x, j); if (w === null) continue; count++; if (w < v) below++; else if (w === v) equal++ }
    if (count) o[t] = 100 * (below + 0.5 * equal) / count;
  }
  return o;
}

/** Operator 6 (Z-Score): (x_t - M) / SD, M the mean and SD the sample standard deviation (n - 1) of the non-missing
    values of x in the N sessions before t (two passes per window, no running sums: the value equals a brute-force
    reading). null as percentileOwn, and where the window holds fewer than 2 values or SD is 0. */
export function zScore(x: In, n: number): Series {
  whole(n, 'zscore: length', 2);
  const N = x.length, o = nul(N), first = firstValue(x);
  if (first < 0) return o;
  for (let t = first + n; t < N; t++) {
    const v = at(x, t);
    if (v === null) continue;
    let sum = 0, count = 0, lo = Infinity, hi = -Infinity;
    for (let j = t - n; j < t; j++) { const w = at(x, j); if (w !== null) { sum += w; count++; if (w < lo) lo = w; if (w > hi) hi = w } }
    if (count < 2 || lo === hi) continue;                     // a flat window: SD is exactly 0 (equalRun note)
    const mean = sum / count;
    let sq = 0;
    for (let j = t - n; j < t; j++) { const w = at(x, j); if (w !== null) sq += (w - mean) * (w - mean) }
    const sd = Math.sqrt(sq / (count - 1));
    if (sd > 0) o[t] = (v - mean) / sd;
  }
  return o;
}

/** Operator 4 (Change), percent form: 100 x (x_t / x_(t-N) - 1); null where either is missing or x_(t-N) <= 0. The
    absolute form is `change` above. */
export function pctChange(x: In, bars: number): Series {
  whole(bars, 'change_pct: bars', 1);
  const N = x.length, o = nul(N);
  for (let i = bars; i < N; i++) { const a = at(x, i), b = at(x, i - bars); if (a !== null && b !== null && b > 0) o[i] = (a / b - 1) * 100 }
  return o;
}

/** Operator 7 (Relative Comparison): difference a_t - b_t, or ratio a_t / b_t (null where b_t <= 0); null where either
    is missing. The two series must have the same unit (resolveTransform refuses others, naming both units). */
export function relative(a: In, b: In, form: 'difference' | 'ratio'): Series {
  const N = a.length, o = nul(N);
  for (let i = 0; i < N; i++) {
    const x = at(a, i), y = at(b, i);
    if (x === null || y === null) continue;
    if (form === 'difference') o[i] = x - y; else if (y > 0) o[i] = x / y;
  }
  return o;
}

/** Operator 12 (Trend / Slope): the ordinary least-squares slope of x over the N sessions ending at t against the
    session index 0 .. N-1: sum((k - k̄) x_k) / sum((k - k̄)^2), k̄ = (N - 1) / 2, sum((k - k̄)^2) = N (N^2 - 1) / 12. In
    the unit of x per session; null where any value of the window is missing. */
export function slope(x: In, n: number): Series {
  whole(n, 'slope: length', 2);
  const N = x.length, o = nul(N), kbar = (n - 1) / 2, sxx = n * (n * n - 1) / 12;
  for (let t = n - 1; t < N; t++) {
    let s = 0, ok = true, lo = Infinity, hi = -Infinity;
    for (let k = 0; k < n; k++) { const v = at(x, t - n + 1 + k); if (v === null) { ok = false; break } s += (k - kbar) * v; if (v < lo) lo = v; if (v > hi) hi = v }
    if (ok) o[t] = lo === hi ? 0 : s / sxx;                   // a flat window: exactly 0 (equalRun note)
  }
  return o;
}

/** Operator 13 (Acceleration): slope_N(t) - slope_N(t - N), the slope of the last N sessions minus the slope of the N
    sessions before them; null where either slope is missing. */
export function acceleration(x: In, n: number): Series {
  const s = slope(x, n), N = x.length, o = nul(N);
  for (let t = n; t < N; t++) { const a = s[t], b = s[t - n]; if (isN(a) && isN(b)) o[t] = a - b }
  return o;
}

/** Operator 14 (Distance to Extreme): x_t against the highest (or lowest) x of the N sessions ending at t, today
    included (rollingMax / rollingMin above: a missing value restarts the window). absolute x_t - H (0 or below; x_t - L
    0 or above for the lowest); percent 100 x (x_t / extreme - 1), null where the extreme is <= 0. */
export function distanceToExtreme(x: In, extreme: 'highest' | 'lowest', n: number, form: 'absolute' | 'percent'): Series {
  const e = extreme === 'highest' ? rollingMax(x, n) : rollingMin(x, n), N = x.length, o = nul(N);
  for (let i = 0; i < N; i++) {
    const v = at(x, i), m = e[i];
    if (v === null || !isN(m)) continue;
    if (form === 'absolute') o[i] = v - m; else if (m > 0) o[i] = (v / m - 1) * 100;
  }
  return o;
}

/* ---- transform references ------------------------------------------------------------------------------------------ */

const ORDER: (HistoryClass | null)[] = [null, 'window', 'calendar', 'recursive', 'cumulative'];
const worst = (...cs: (HistoryClass | null)[]): HistoryClass => cs.reduce<HistoryClass>((w, c) => ORDER.indexOf(c) > ORDER.indexOf(w) ? c as HistoryClass : w, 'window');
const windowed = (c: HistoryClass | null): HistoryClass => c === null ? 'window' : c;
const unionInputs = (...rs: ResolvedSeries[]): BarField[] => BAR_FIELDS.filter(f => rs.some(r => r.inputs.includes(f)));
const BAR: Record<PriceField, BarField> = { open: 'O', high: 'H', low: 'L', close: 'C', volume: 'V' };
const MAX_DEPTH = 4;
const BAND_PAIRS = [['upper', 'lower'], ['upper1', 'lower1']] as const;
const isObj = (x: unknown): x is Record<string, unknown> => !!x && typeof x === 'object' && !Array.isArray(x);
const NO_LAG = Object.freeze({ gt: 0, lt: 0 }) as { gt: 0 | 1; lt: 0 | 1 };

/** The transform functions this module computes (catalog.ts catalogProblems checks the catalog lists exactly these). */
export const IMPLEMENTED_TRANSFORMS: readonly string[] = ['pct_distance', 'band_position', 'lag', 'change', 'rolling_max', 'rolling_min', 'rising_run', 'ma', 'ratio', 'vs_index',
  'vs_average', 'percentile', 'zscore', 'change_pct', 'relative', 'slope', 'acceleration', 'distance_to_extreme'];

/** The transform reference resolved to a series (metrics.ts ResolvedSeries): fn and args checked against
    screener-metrics.json (unknown fn -> INVALID_CONDITION with the allowed ids; a range -> PARAM_OUT_OF_RANGE), `of`
    (and a reference argument such as ratio's denominator `by`) resolved through metrics.ts resolveSeries, key =
    canonical JSON of the resolved transform (args complete), historyClass: 'window' for rolling_max / rolling_min /
    ma SMA / lag / change over a window-class or bar input, else the inner series' class, 'recursive' for an EMA and for
    rising_run (its run has no fixed length), the worst operand for ratio (the PRICE_BREAK_IN_LOOKBACK rule reads it);
    inputs: the union of its operands' inputs (vs_index adds nothing: the index is IHSG's close). `of` must be a price
    level for pct_distance, a band instance's output for band_position (its upper and lower outputs of the same
    parameters are read) and the close for vs_index. `index` (IHSG's bars) serves vs_index when it computes (validation
    needs none). Nesting deeper than
    MAX_DEPTH transforms is refused. */
export function resolveTransform(ref: TransformRef, field: string, ctx: ParamOptions & { index?: TickerBars; flow?: FlowBindContext }): ResolvedSeries {
  const operands: ResolvedSeries[] = [];
  const r = resolveTransformCore(ref, field, ctx, operands);
  return withFlow(r, (r.ref as TransformRef).fn, ((r.ref as TransformRef).args || {}) as Record<string, unknown>, operands);
}
/** K1 (OPERATORS.md section 3): the sessions an operator reads before its operand's own: N for 2, 3, 4, 6, 12 and 14
    (and the lag, moving average and rolling windows), 2N for 13 (acceleration); a relative comparison or a ratio reads
    none. */
function operatorSessions(fn: string, args: Record<string, unknown>): number {
  const n = typeof args.length === 'number' ? args.length : typeof args.bars === 'number' ? args.bars : 0;
  return fn === 'acceleration' ? 2 * n : n;
}
/** Transforms that keep their operand's level (and so its output type): a lag, an average, a rolling extreme. */
const KEEPS_LEVEL = ['lag', 'ma', 'rolling_max', 'rolling_min'];
/** The transform's series with what it inherits from a flow operand (P5a): flowDepth = the deepest flow operand's
    sessions plus the operator's own (operatorSessions; null when an operand's is not known), flowOwn the flow
    indicator's own, and the operand's output type where the transform keeps its level. Without a flow operand only
    the kept output type is added. */
function withFlow(r: ResolvedSeries, fn: string, args: Record<string, unknown>, operands: readonly ResolvedSeries[]): ResolvedSeries {
  const kind = KEEPS_LEVEL.includes(fn) && operands[0]?.outputKind ? { outputKind: operands[0].outputKind } : {};
  const flows = operands.filter(o => o.flowDepth !== undefined);
  if (!flows.length) return { ...r, ...kind };
  const known = flows.every(o => typeof o.flowDepth === 'number');
  const depth = known ? Math.max(...flows.map(o => o.flowDepth as number)) + operatorSessions(fn, args) : null;
  const owns = flows.map(o => o.flowOwn === undefined ? o.flowDepth : o.flowOwn);
  const own = owns.every(x => typeof x === 'number') ? Math.max(...owns as number[]) : null;
  return { ...r, ...kind, flowDepth: depth, flowOwn: own };
}
function resolveTransformCore(ref: TransformRef, field: string, ctx: ParamOptions & { index?: TickerBars; flow?: FlowBindContext }, operands: ResolvedSeries[]): ResolvedSeries {
  if (field.split('.of').length - 1 + field.split('.args.').length - 1 >= MAX_DEPTH)
    throw new ScreenerError('INVALID_CONDITION', `${field}: transforms nest at most ${MAX_DEPTH} deep; simplify the reference.`, field);
  const spec = transformSpec(ref.fn, `${field}.fn`);
  if (ref.args !== undefined && !isObj(ref.args)) throw new ScreenerError('INVALID_CONDITION', `${field}.args must be an object.`, `${field}.args`);
  const refKeys = spec.ref_args.map(a => a.key), given = (ref.args || {}) as Record<string, unknown>;
  const scalar = resolveCatalogParams(spec.args, Object.fromEntries(Object.entries(given).filter(([k]) => !refKeys.includes(k))), `${field}.args`, refKeys);
  const refArgs: Record<string, ResolvedSeries> = {};
  for (const k of refKeys) {
    if (!isObj(given[k])) throw new ScreenerError('INVALID_CONDITION', `${field}.args.${k} must be a metric reference (${spec.ref_args.find(a => a.key === k)!.label}).`, `${field}.args.${k}`);
    refArgs[k] = resolveSeries(given[k] as unknown as MetricRef, `${field}.args.${k}`, ctx);
  }
  if (!isObj(ref.of)) throw new ScreenerError('INVALID_CONDITION', `${field}.of must be a metric reference.`, `${field}.of`);
  const of = resolveSeries(ref.of, `${field}.of`, ctx);
  operands.push(of, ...refKeys.map(k => refArgs[k]));
  const args: Record<string, unknown> = { ...scalar };
  for (const k of refKeys) args[k] = refArgs[k].ref;
  const norm = { kind: 'transform', fn: spec.fn, of: of.ref, args } as unknown as TransformRef;
  const base = { kind: 'transform' as const, key: canonicalJson(norm), ref: norm as MetricRef };
  const label = `${spec.fn}(${[of.label, ...Object.entries(scalar).map(([, v]) => String(v)), ...refKeys.map(k => refArgs[k].label)].join(', ')})`;
  const num = (k: string) => scalar[k] as number;
  switch (spec.fn) {
    case 'pct_distance':
      if (of.comparableWith !== 'close') throw new ScreenerError('INVALID_CONDITION', `${field}.of: pct_distance needs a price level (a series comparable with close), not ${of.label}.`, `${field}.of`);
      return { ...base, label, unit: 'dimensionless', historyClass: windowed(of.historyClass), inputs: unionInputs(of, closeSeries()), comparableWith: null, compareLag: NO_LAG,
        full: t => pctDistance(t.bars.C, of.full(t)) };
    case 'band_position': {
      const band = bandOf(ref.of, `${field}.of`, ctx);
      return { ...base, label: `band_position(${band.upper.indicator.id})`, unit: 'dimensionless', historyClass: worst(band.upper.historyClass, band.lower.historyClass),
        inputs: unionInputs(band.upper, band.lower, closeSeries()), comparableWith: null, compareLag: NO_LAG,
        full: t => bandPosition(t.bars.C, band.upper.full(t), band.lower.full(t)) };
    }
    case 'lag':
      return { ...base, label, unit: of.unit, historyClass: windowed(of.historyClass), inputs: of.inputs, comparableWith: of.comparableWith, compareLag: NO_LAG,
        full: t => lag(of.full(t), num('bars')) };
    case 'change':
      return { ...base, label, unit: of.unit === 'price' ? 'price_change' : of.unit, historyClass: windowed(of.historyClass), inputs: of.inputs, comparableWith: null, compareLag: NO_LAG,
        full: t => change(of.full(t), num('bars')) };
    case 'rolling_max': case 'rolling_min': {
      const lagOf = of.kind === 'price' ? spec.compare_lag?.[(of.ref as { field: PriceField }).field] : undefined;
      const f = spec.fn === 'rolling_max' ? rollingMax : rollingMin;
      return { ...base, label, unit: of.unit, historyClass: windowed(of.historyClass), inputs: of.inputs, comparableWith: of.comparableWith, compareLag: lagOf ?? NO_LAG,
        full: t => f(of.full(t), num('length')) };
    }
    case 'rising_run':
      return { ...base, label, unit: 'dimensionless', historyClass: worst(of.historyClass, 'recursive'), inputs: of.inputs, comparableWith: null, compareLag: NO_LAG, integer: true,
        full: t => risingRun(of.full(t)) };
    case 'ma': {
      const type = scalar.ma as 'SMA' | 'EMA';
      return { ...base, label, unit: of.unit, historyClass: type === 'SMA' ? windowed(of.historyClass) : worst(of.historyClass, 'recursive'), inputs: of.inputs,
        comparableWith: of.comparableWith, compareLag: NO_LAG, full: t => ma(of.full(t), type, num('length')) };
    }
    case 'ratio': {
      const by = refArgs.by;
      return { ...base, label, unit: 'dimensionless', historyClass: worst(of.historyClass, by.historyClass), inputs: unionInputs(of, by), comparableWith: null, compareLag: NO_LAG,
        full: t => ratio(of.full(t), by.full(t)) };
    }
    case 'vs_index': {
      if (of.kind !== 'price' || (of.ref as { field: string }).field !== 'close') throw new ScreenerError('INVALID_CONDITION', `${field}.of: vs_index compares the close with IHSG; use {"kind":"price","field":"close"}.`, `${field}.of`);
      const index = ctx.index;
      return { ...base, label, unit: 'dimensionless', historyClass: 'window', inputs: of.inputs, comparableWith: null, compareLag: NO_LAG,
        full: t => {
          if (!index) throw new RangeError('vs_index: the series context has no IHSG bars (ctx.index)');
          return vsIndex(t.bars.C, asOf(index.dates, index.bars.C as ArrayLike<number | null>, t.dates), num('window'));
        } };
    }
    // the universal operators (OPERATORS.md 2-4, 6, 7, 12-14)
    case 'vs_average': {
      operatorTakes(spec.fn, of, `${field}.of`);
      const type = scalar.ma as 'SMA' | 'EMA', form = scalar.form as 'difference' | 'ratio' | 'percent';
      return { ...base, label, unit: form === 'difference' ? differenceUnit(of) : form, historyClass: type === 'SMA' ? windowed(of.historyClass) : worst(of.historyClass, 'recursive'),
        inputs: of.inputs, comparableWith: null, compareLag: NO_LAG, full: t => vsAverage(of.full(t), type, num('length'), form) };
    }
    case 'percentile':
      operatorTakes(spec.fn, of, `${field}.of`);
      return { ...base, label, unit: 'percentile', historyClass: windowed(of.historyClass), inputs: of.inputs, comparableWith: null, compareLag: NO_LAG,
        full: t => percentileOwn(of.full(t), num('length')) };
    case 'zscore':
      operatorTakes(spec.fn, of, `${field}.of`);
      return { ...base, label, unit: 'sd', historyClass: windowed(of.historyClass), inputs: of.inputs, comparableWith: null, compareLag: NO_LAG,
        full: t => zScore(of.full(t), num('length')) };
    case 'change_pct':
      operatorTakes(spec.fn, of, `${field}.of`);
      return { ...base, label, unit: 'percent', historyClass: windowed(of.historyClass), inputs: of.inputs, comparableWith: null, compareLag: NO_LAG,
        full: t => pctChange(of.full(t), num('bars')) };
    case 'relative': {
      const by = refArgs.by, form = scalar.form as 'difference' | 'ratio';
      if (of.unit === null || of.unit === 'other' || of.unit !== by.unit || of.comparableWith !== by.comparableWith)
        throw new ScreenerError('INVALID_CONDITION', `${field}.args.by: a relative comparison needs two series of the same unit; ${of.label} is ${unitWords(of)} and ${by.label} is ${unitWords(by)}. Compare a price with a price, a percent with a percent, a volume with a volume (right: close vs its SMA; wrong: RSI vs close).`, `${field}.args.by`, { allowed: [String(of.unit)] });
      return { ...base, label, unit: form === 'ratio' ? 'ratio' : differenceUnit(of), historyClass: worst(of.historyClass, by.historyClass), inputs: unionInputs(of, by), comparableWith: null, compareLag: NO_LAG,
        full: t => relative(of.full(t), by.full(t), form) };
    }
    case 'slope':
      operatorTakes(spec.fn, of, `${field}.of`);
      return { ...base, label, unit: differenceUnit(of), historyClass: windowed(of.historyClass), inputs: of.inputs, comparableWith: null, compareLag: NO_LAG,
        full: t => slope(of.full(t), num('length')) };
    case 'acceleration':
      operatorTakes(spec.fn, of, `${field}.of`);
      return { ...base, label, unit: differenceUnit(of), historyClass: windowed(of.historyClass), inputs: of.inputs, comparableWith: null, compareLag: NO_LAG,
        full: t => acceleration(of.full(t), num('length')) };
    case 'distance_to_extreme': {
      operatorTakes(spec.fn, of, `${field}.of`);
      const extreme = scalar.extreme as 'highest' | 'lowest', form = scalar.form as 'absolute' | 'percent';
      return { ...base, label, unit: form === 'percent' ? 'percent' : differenceUnit(of), historyClass: windowed(of.historyClass), inputs: of.inputs, comparableWith: null, compareLag: NO_LAG,
        full: t => distanceToExtreme(of.full(t), extreme, num('length'), form) };
    }
  }
  throw new ScreenerError('INVALID_CONDITION', `${field}.fn: ${spec.fn} is listed in the catalog but not computed here.`, `${field}.fn`);
}
/** The unit of a difference of x (x_t - something of x): a price difference for a price level, else the unit of x. */
const differenceUnit = (x: ResolvedSeries): string | null => x.unit === 'price' ? 'price_change' : x.unit as string | null;
/** A unit in words for a refusal. */
const unitWords = (x: ResolvedSeries): string => x.unit === null ? 'without a unit' : x.comparableWith ? `a ${x.comparableWith === 'close' ? 'price' : 'volume'} level (${x.unit})` : `in ${x.unit}`;
/** Which universal operators an output type takes (OPERATORS.md section 4), from the catalog's operators block (one
    source with the page): a series made by a transform of a type (P: percentile, zscore, already set against its own
    history; D: rising_run, a count of consecutive sessions) is not offered the measures whose not_on names that type;
    every other series takes every measure. */
const OPS = METRICS_CATALOG.operators;
const NOT_OFFERED: Record<string, readonly string[]> = Object.fromEntries(Object.keys(OPS.types).map(k => [k, OPS.measures.filter(m => m.not_on.includes(k)).map(m => m.fn)]));
const OPERATOR_NAMES: Record<string, string> = Object.fromEntries(OPS.measures.map(m => [m.fn, m.label]));
/** The output type of OPERATORS.md section 4 a series has: a flow output's kind (flow-kinds.json: K, P, Rp, L, H, D,
    F, B), kept through a transform that keeps its operand's level (lag, ma, rolling_max, rolling_min); else P or D from
    the transform that made it (percentile, zscore, rising_run); null for any other (an indicator output takes every
    operator). */
export function outputType(x: ResolvedSeries): string | null {
  if (x.outputKind) return x.outputKind;
  const fn = x.kind === 'transform' ? (x.ref as TransformRef).fn : null;
  return Object.entries(OPS.types).find(([, t]) => fn !== null && t.fns.includes(fn))?.[0] ?? null;
}
function operatorTakes(fn: string, of: ResolvedSeries, field: string): void {
  const type = outputType(of);
  if (!type || !NOT_OFFERED[type].includes(fn)) return;
  const takes = [...new Set(OPS.measures.filter(m => !NOT_OFFERED[type].includes(m.fn)).map(m => m.label))];
  const wrong = OPS.types[type].fns.length ? OPS.types[type].fns.join(' or ') : of.label;
  throw new ScreenerError('INVALID_CONDITION', `${field}: ${of.label} ${OPS.types[type].words}, so ${OPERATOR_NAMES[fn]} is not offered on it; it takes ${takes.length ? takes.join(', ') : 'no measure'}${OPS.types[type].fns.length ? ', a value test, a range or a cross. Apply the operator to the series itself instead' : ''} (right: ${OPERATOR_NAMES[fn]} of RSI; wrong: ${OPERATOR_NAMES[fn]} of ${wrong}).`, field, { allowed: takes });
}
const closeSeries = (): ResolvedSeries => ({ kind: 'price', key: '', ref: { kind: 'price', field: 'close' }, label: 'close', unit: 'price', historyClass: null, inputs: ['C'], comparableWith: 'close', compareLag: NO_LAG, full: t => t.bars.C });

/** The upper and lower outputs of the band instance `of` names (any of its outputs, usually basis): the instance's
    upper / lower pair, or upper1 / lower1 (VWAP), at the same parameters. */
function bandOf(of: MetricRef, field: string, opts: ParamOptions) {
  if (!of || of.kind !== 'indicator') throw new ScreenerError('INVALID_CONDITION', `${field}: band_position needs an output of a band indicator (Bollinger, Keltner, Donchian, VWAP).`, field);
  const ind = screenerIndicator(of.indicator, `${field}.indicator`);
  screenerOutput(ind, of.output, `${field}.output`);
  const pair = BAND_PAIRS.find(([u, l]) => ind.outputs.some(o => o.key === u) && ind.outputs.some(o => o.key === l));
  if (!pair || !ind.outputs.filter(o => (pair as readonly string[]).includes(o.key)).every(o => o.comparable_with === 'close'))
    throw new ScreenerError('INVALID_CONDITION', `${field}: ${ind.id} ${ind.name} has no upper and lower price band; band_position needs a band indicator.`, field);
  const r = (output: string) => resolveIndicator({ ...(of as IndicatorRef), output }, field, opts);
  return { upper: r(pair[0]), lower: r(pair[1]) };
}

/* ---- pattern signals ------------------------------------------------------------------------------------------------ */

interface PatternImpl {
  /** the 0/1 signal on the ticker's bars (bar 0 never true) */
  signal(t: TickerCalc, p: ParamMap, opts: ParamOptions): Uint8Array;
  /** the bars a signal at i depends on, from its parameters (the PRICE_BREAK_IN_LOOKBACK window, report 6.12) */
  window(p: ParamMap): number;
  historyClass: HistoryClass;
  inputs(p: ParamMap): BarField[];
}
const pa = (t: TickerCalc, type: string, params: ParamMap, value?: number, op?: string): Uint8Array =>
  priceActionCondition(t.calc, { id: 'p', kind: 'price_action', type, params, ...(op ? { op } : {}), ...(value !== undefined ? { value } : {}) } as PriceActionCondition, 'pattern');
const zeroBar0 = (s: Uint8Array) => { if (s.length) s[0] = 0; return s };
const lineOf = (t: TickerCalc, of: string, opts: ParamOptions): ArrayLike<Num | undefined> => {
  if (of === 'close') return t.bars.C; if (of === 'volume') return t.bars.V;
  const [id, output] = of.split('.');
  return resolveIndicator({ kind: 'indicator', indicator: id, output, params: screenerIndicator(id).start_params }, 'pattern.params.of', opts).full(t);
};
const lineInputs = (of: string): BarField[] => of === 'close' ? ['C'] : of === 'volume' ? ['V'] : ['C', 'V'];
/** What each pattern type of the catalog computes (report 6.9, 6.9.1). */
const PATTERNS: Record<string, PatternImpl> = {
  /** close > the highest high of the previous N bars: core PRICE_ACTION breakout */
  breakout: { signal: (t, p) => pa(t, 'breakout', { length: p.length }), window: p => (p.length as number) + 1, historyClass: 'window', inputs: () => ['H', 'C'] },
  /** close < the lowest low of the previous N bars: the Donchian lower band (I10) read on the previous bar, the lag the
      probe derives (report 6.8; I10 lower price_compare_lag.lt = 1) */
  breakdown: {
    signal: (t, p) => {
      const lower = t.calc.out('donchian', { length: p.length }).lower;
      return compare(t.bars.C as ArrayLike<Num>  as Num[], 'lt', lag(lower, 1), 0, t.calc.n);
    },
    window: p => (p.length as number) + 1, historyClass: 'window', inputs: () => ['H', 'L', 'C'],
  },
  /** volume / SMA(volume, N) of the previous bar > threshold: core PRICE_ACTION volspike */
  volspike: { signal: (t, p) => pa(t, 'volspike', { length: p.length }, p.threshold as number), window: p => (p.length as number) + 1, historyClass: 'window', inputs: () => ['V'] },
  /** SMA(fast) crosses above SMA(slow): core PRICE_ACTION macross golden_cross */
  macross: {
    signal: (t, p) => pa(t, 'macross', { fast_length: p.fast_length, slow_length: p.slow_length }, undefined, 'golden_cross'),
    window: p => Math.max(p.fast_length as number, p.slow_length as number) + 1, historyClass: 'window', inputs: () => ['C'],
  },
  /** core bullishDivergence on the low and the MACD line (PRICE_ACTION macd bullish_divergence) */
  macd_divergence: {
    signal: (t, p) => pa(t, 'macd', { fast_length: p.fast_length, slow_length: p.slow_length, signal_length: p.signal_length }, undefined, 'bullish_divergence'),
    window: () => Infinity, historyClass: 'recursive', inputs: () => ['L', 'C'],
  },
  /** I29 bandwidth <= its rolling minimum over `lookback` bars, today included */
  squeeze: {
    signal: (t, p) => {
      const bw = t.calc.out('bollinger_width', { length: p.length, source: 'close', std_dev: p.std_dev, basis_ma_type: 'SMA' }).bandwidth, lo = rollingMin(bw, p.lookback as number);
      const s = new Uint8Array(t.calc.n);
      for (let i = 1; i < s.length; i++) { const b = bw[i], m = lo[i]; s[i] = +(isN(b) && isN(m) && b <= m) }
      return s;
    },
    window: p => (p.length as number) + (p.lookback as number) - 1, historyClass: 'window', inputs: () => ['C'],
  },
  /** I15 %K crosses above %D on a bar where %K < zone_max. Window: %D at i reads [i - k - s - d + 3, i] (raw %K over
      k_length, smoothed over smooth_k, %D over d_length) and the cross reads bar i - 1 too: k + s + d - 1 bars */
  stoch_cross_in_zone: {
    signal: (t, p) => {
      const o = t.calc.out('stochastic', { k_length: p.k_length, smooth_k: p.smooth_k, d_length: p.d_length }), x = compare(o.k, 'crosses_above', o.d, 0, t.calc.n);
      for (let i = 0; i < x.length; i++) if (x[i] && !((o.k[i] as number) < (p.zone_max as number))) x[i] = 0;
      return x;
    },
    window: p => (p.k_length as number) + (p.smooth_k as number) + (p.d_length as number) - 1, historyClass: 'window', inputs: () => ['H', 'L', 'C'],
  },
  /** x > the highest x of the previous `length` bars, on every such bar. Window: bars [i - length, i], length + 1 (for
      the cumulative lines too: x[i] > x[j] depends only on the increments over (j, i], each reading its bar and the one
      before, so the line's start never matters) */
  new_high: {
    signal: (t, p, opts) => { const x = lineOf(t, p.of as string, opts); return compare(x as Num[], 'gt', lag(rollingMax(x, p.length as number), 1), 0, t.calc.n) },
    window: p => (p.length as number) + 1, historyClass: 'window', inputs: p => lineInputs(p.of as string),
  },
  /** SMA(volume, days)[t] / SMA(volume, length)[t - days] >= volx and |close[t] / close[t - days] - 1| x 100 <= move */
  silent: {
    signal: (t, p) => {
      const d = p.days as number, recent = sma(t.bars.V, d), base = sma(t.bars.V, p.length as number), C = t.bars.C, s = new Uint8Array(t.calc.n);
      for (let i = Math.max(1, d); i < s.length; i++) {
        const r = recent[i], b = base[i - d], c = at(C, i), c0 = at(C, i - d);
        if (!isN(r) || !isN(b) || b === 0 || c === null || c0 === null || c0 === 0) continue;
        s[i] = +(r / b >= (p.volx as number) && Math.abs(c / c0 - 1) * 100 <= (p.move as number));
      }
      return s;
    },
    window: p => (p.days as number) + (p.length as number), historyClass: 'window', inputs: () => ['C', 'V'],
  },
};
/** The pattern types this module computes (catalog.ts catalogProblems: every offered pattern type must be here). */
export const IMPLEMENTED_PATTERNS: readonly string[] = Object.keys(PATTERNS);

/** A pattern resolved to a 0/1 series (metrics.ts ResolvedSeries, kind 'pattern'), so its tail goes through the one
    series() path and cache like any other series (report 6.7). params checked and completed from screener-metrics.json;
    a catalog pattern without an implementation (Ichimoku, which waits for a registry release, P6) is METRIC_UNAVAILABLE
    with its decision. window: the bars a signal at a bar depends on (report 6.12 lookback). */
export function resolveSignal(ref: PatternRef, field: string, opts: ParamOptions): ResolvedSeries & { window: number } {
  if (!isObj(ref)) throw new ScreenerError('INVALID_CONDITION', `${field} must be a pattern reference.`, field);
  const spec = metricSpec('pattern', ref.type, `${field}.type`, METRICS_CATALOG), impl = PATTERNS[spec.id];
  if (!impl || spec.decision) throw new ScreenerError('METRIC_UNAVAILABLE', `${field}.type: ${spec.id} is not available: ${(spec.decision || spec.unavailable_reason || 'it has no implementation yet').replace(/\.$/, '')}.`, `${field}.type`, { metric: spec.id, availability: 'REQUIRES_DECISION', reason: spec.decision || spec.unavailable_reason || '' });
  const params = resolveCatalogParams(spec.params, ref.params, `${field}.params`);
  const norm = { kind: 'pattern', type: spec.id, params } as PatternRef;
  return {
    kind: 'pattern', key: canonicalJson(norm), ref: norm, label: `${spec.id}(${Object.values(params).join(', ')})`, unit: null,
    historyClass: impl.historyClass, inputs: impl.inputs(params), comparableWith: null, compareLag: NO_LAG, window: impl.window(params),
    full: t => Array.from(zeroBar0(impl.signal(t as TickerCalc, params, opts))),
  };
}

/** A pattern's 0/1 signal on the ticker's bars (report 6.9, 6.9.1), from screener-metrics.json's pattern entries:
    breakout = core PRICE_ACTION breakout (close > the highest high of the previous N bars); breakdown = close < the
    lowest low of the previous N bars (the Donchian lower band at the lag the probe derives); volspike = core
    volspike (volume / SMA(volume, N) of the previous bar > threshold); macross = core macross golden cross;
    macd_divergence = core bullishDivergence (flagged k bars after the swing low); squeeze {length, std_dev, lookback} =
    I29 bandwidth <= its rolling_min over lookback bars, today included; stoch_cross_in_zone {zone_max, default 25 as
    coded} = I15 K crosses above D on a bar where K < zone_max; new_high {of, length} = x > the maximum of the previous
    `length` bars, on every such bar; silent {days, length, volx, move} = volume ratio >= volx while |move| <= move %.
    Bar 0 is never true. */
export function patternSignal(t: TickerCalc, ref: PatternRef, field: string, ctx: ParamOptions): Uint8Array {
  return Uint8Array.from(resolveSignal(ref, field, ctx).full(t) as ArrayLike<number>);
}
