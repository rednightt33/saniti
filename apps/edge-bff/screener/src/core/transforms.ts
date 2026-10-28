/* Condition arithmetic over F outputs and bar fields, and the pattern signals (EXEC-SCREENER; report TARGET
   ARCHITECTURE 6.9 "Metric references", 6.9.1 operator mapping). These are not formulas: a transform combines series
   that F or the bars already give, with the exported reference helpers of indicators.ts (sma, ema) where it needs an
   average, and a pattern reuses the backtest core's PRICE_ACTION / priceActionCondition / bullishDivergence
   (conditions.ts:124-190) where one exists. A screener file never defines an indicator kernel (report I1); a new
   indicator is a registry release (P6), never a transform.
   Every transform runs on the FULL series and is then tailed by metrics.ts series() (report 6.7: "contract-declared
   derived series, computed on the full series and then tailed"), so a recursive input (an EMA of OBV) is exact.
   The valid `fn` and pattern `type` values, their arguments and ranges come from screener-metrics.json (validate.ts),
   never from a list in code; the functions below are what each id computes. Output arrays are aligned with the bars;
   null where an input is missing (the indicators.ts convention). Typed stubs for the core-logic agent. */
import type { Num } from '../../../terminal/src/calc/indicators.ts';
import type { PatternRef, TransformRef } from './contract.ts';
import type { ParamOptions } from './registry.ts';
import type { ResolvedSeries, TickerBars, TickerCalc } from './metrics.ts';

type In = ArrayLike<Num | undefined>;
export type Series = Num[];

/** pct_distance(of, base = close): (base / of - 1) x 100 per bar (the prototype's line rule, report 6.9.1); null where
    either is missing or of is 0. */
export function pctDistance(base: In, of: In): Series { throw new Error('not implemented: pctDistance') }

/** band_position(close, upper, lower): (close - lower) / (upper - lower) x 100 per bar; null at zero width (raw
    doubles, no epsilon: report 6.9.1 band row, NA NULL_AT_EVALUATION only at zero width) or a missing input. */
export function bandPosition(close: In, upper: In, lower: In): Series { throw new Error('not implemented: bandPosition') }

/** lag(x, bars): x[i - bars] (null before). The prototype's "rising" is STATE x gt lag(x, 5) for the line shape, 21 for
    price_ma, 20 for the cumulative lines (report 6.9.1). */
export function lag(x: In, bars: number): Series { throw new Error('not implemented: lag') }

/** change(x, bars): x[i] - x[i - bars] (absolute; null when either is missing). */
export function change(x: In, bars: number): Series { throw new Error('not implemented: change') }

/** rolling_max(x, n) / rolling_min(x, n): the maximum / minimum over [i - n + 1, i], today included (hi52 / lo52, report
    6.9.1); a missing value restarts the window (the indicators.ts roll rule). As the rhs of a price comparison its lag
    comes from the lag probe (report 6.8: `close > rolling_max(high, n)` reads the previous bar, so it equals core
    breakout); as a VALUE (pct_distance) it has no lag. */
export function rollingMax(x: In, n: number): Series { throw new Error('not implemented: rollingMax') }
export function rollingMin(x: In, n: number): Series { throw new Error('not implemented: rollingMin') }

/** rising_run(x): the number of consecutive bars ending at i with x[t] > x[t - 1]; 0 when x[i] <= x[i - 1]; null when
    x[i] or x[i - 1] is missing. The legacy MACD "hup" is STATE rising_run(histogram) gt 2 (report 6.9.1). */
export function risingRun(x: In): Series { throw new Error('not implemented: risingRun') }

/** ma(x, type, n): indicators.ts sma (type 'SMA') or ema (type 'EMA', seeded with the SMA of its first n valid values),
    the reference helpers, never a copy. The cumulative lines' "above average" is EMA as the prototype computes it
    (report 6.9.1 cum row: label changed from "average" to "EMA"). */
export function ma(x: In, type: 'SMA' | 'EMA', n: number): Series { throw new Error('not implemented: ma') }

/** ratio(a, b): a / b; null where b is 0 or either is missing (volspike as a VALUE: ratio(volume, lag(ma(volume, SMA,
    len), 1)), report 6.9.1). */
export function ratio(a: In, b: In): Series { throw new Error('not implemented: ratio') }

/** vs_index(close, index, d): (close[i] / close[i - d] - 1) x 100 - (index[i] / index[i - d] - 1) x 100, the prototype's
    `rs`, on the ticker's own bars with IHSG's close aligned to the ticker's dates by datafile.asOf (report 6.9 rs_rank
    note). */
export function vsIndex(close: In, indexAligned: In, d: number): Series { throw new Error('not implemented: vsIndex') }

/** The transform reference resolved to a series (metrics.ts ResolvedSeries): fn and args checked against
    screener-metrics.json (unknown fn -> INVALID_CONDITION with the allowed ids; a range -> PARAM_OUT_OF_RANGE), `of`
    (and a reference argument such as ratio's denominator) resolved through metrics.ts resolveSeries, key = canonical
    JSON of the resolved transform, historyClass: 'window' for rolling_max / rolling_min / ma SMA / lag / change over
    a window-class or bar input, else the inner series' class (the PRICE_BREAK_IN_LOOKBACK rule reads it). `index`
    (IHSG's bars) serves vs_index. */
export function resolveTransform(ref: TransformRef, field: string, ctx: ParamOptions & { index: TickerBars }): ResolvedSeries {
  throw new Error('not implemented: resolveTransform');
}

/** A pattern's 0/1 signal on the ticker's bars (report 6.9, 6.9.1), from screener-metrics.json's pattern entries:
    breakout = core PRICE_ACTION breakout (close > the highest high of the previous N bars); breakdown = close < the
    lowest low of the previous N bars (the Donchian lower band at the lag the probe derives); volspike = core
    volspike (volume / SMA(volume, N) of the previous bar > value); macross = core macross; macd_divergence = core
    bullishDivergence (flagged k bars after the swing low); squeeze {length, std_dev, lookback} = I29 bandwidth <= its
    rolling_min over lookback bars, today included; stoch_cross_in_zone {zone_max, default 25 as coded} = I15 K crosses
    above D on a bar where K < zone_max; new_high {of, length} = x > the maximum of the previous `length` bars, on every
    such bar; silent {days, length, volx, move} = volume ratio >= volx while |move| <= move %. Bar 0 is never true. */
export function patternSignal(t: TickerCalc, ref: PatternRef, field: string, ctx: ParamOptions): Uint8Array {
  throw new Error('not implemented: patternSignal');
}
