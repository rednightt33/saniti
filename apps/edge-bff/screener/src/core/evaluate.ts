/* VALUE, STATE and EVENT at the evaluation bar, per ticker and per condition (EXEC-SCREENER; report TARGET
   ARCHITECTURE 6.9 "Tests", "NA reason codes", "Remarks"; as-of policy 6.5). The rules, exactly:
   - evaluation bar: each ticker is evaluated at its own last bar on or before E = price_through (evaluationBar); a
     stale ticker (last bar before E) is evaluated there too and carries the row remark STALE, never NA (P4);
   - VALUE: the metric at the evaluation bar; gt and lt strict; between inclusive (value <= x <= value2), one condition;
   - STATE: compare(lhs, op, rhs)[at] with the backtest core's rules: bar 0 never true, a missing side is false
     (compareAt reuses core compare itself); a pattern state is the pattern's 0/1 signal at `at`;
   - EVENT: a cross through core compare (both sides finite on the bar and the bar before) or a pattern signal, on the
     ticker's OWN bars, within the last `within` bars ending at `at`: j = the largest i in [at-within+1, at] where the
     signal is 1; event_date = dates[j], bars_ago = at - j (own bars), market_sessions_ago on the IHSG calendar
     (informational: the 2026-09-17/18 sessions are missing for every stock, ERRORS M238), last_event_date = the last
     event within within_max bars. within is per condition, never one shared window; an event is never reduced to a
     state, and core combineEntry is deliberately not used (its window turns states into "true on any of the last W
     bars", conditions.ts:269-292);
   - NA: a cell is NA only with a reason (I5): INSUFFICIENT_HISTORY when the series has no value on any bar up to
     `at`, NULL_AT_EVALUATION when it has values earlier but none at `at` (naReason); the flow, applicability and
     integrity reasons come from their own modules. NA never fails the whole screen;
   - remarks: a cell on a PRICE_BREAK row whose lookback contains an ex-date keeps its value and its pass or fail and
     carries PRICE_BREAK_IN_LOOKBACK (P4.1 A; user 2026-10-28; where the TEST PLAN still says NA, P4.1 A wins).
   Evaluating on a tail (metrics.ts Tail, within_max + 1 bars) equals evaluating on the full series at every tail bar:
   compare reads only bars i and i-1 (report 6.7 verification). A side read at the output's price_compare_lag 1
   (Donchian's prior band, report 6.8) is therefore its own series, transform lag(output, 1) resolved through
   metrics.ts (computed on the full series, then tailed), never a view shifted over the unlagged tail: a shifted read
   of a cross at the window's first bar (at - within_max + 1) would need bar at - within_max - 1, one bar before the
   tail, and would silently miss that event.
   Pure module (no DOM, no Node API). Implemented here: the bar views, compareAt, crossSignal, naReason,
   evaluationBar, round12. The evaluators are typed stubs for the core-logic agent. */
import { compare } from '../../../backtest/src/core/conditions.ts';
import type { Op } from '../../../backtest/src/core/conditions.ts';
import type { Num } from '../../../terminal/src/calc/indicators.ts';
import type { Cell, CellRemark, HistoryClass, NaReason, ValueTest } from './contract.ts';
import type { Tail } from './metrics.ts';

/* ---- views of a series by bar index ------------------------------------------------------------------------------ */

/** A metric's values on one ticker's bars, read by the ticker's bar index: a full series or a tail. get(i) is NaN for a
    missing value and for a bar the view does not hold (i < from or i >= n). firstValid / lastValid: the first and last
    bar of the full series with a value (-1 when none). */
export interface BarView { readonly n: number; readonly from: number; readonly firstValid: number; readonly lastValid: number; get(i: number): number }
export function viewOfTail(t: Tail): BarView {
  return { n: t.n, from: t.from, firstValid: t.firstValid, lastValid: t.lastValid, get: i => (i >= t.from && i < t.n ? t.values[i - t.from] : NaN) };
}
export function viewOfSeries(s: ArrayLike<Num | undefined>): BarView {
  let firstValid = -1, lastValid = -1;
  for (let i = 0; i < s.length; i++) if (typeof s[i] === 'number' && Number.isFinite(s[i])) { if (firstValid < 0) firstValid = i; lastValid = i }
  return { n: s.length, from: 0, firstValid, lastValid, get: i => { const v = s[i]; return typeof v === 'number' && Number.isFinite(v) ? v : NaN } };
}
/** One side of a comparison: a series view, or a constant (contract.ts ValueSide). */
export type Operand = BarView | number;
export const valueAt = (x: Operand, i: number): number => typeof x === 'number' ? x : x.get(i);

/** compare(lhs, op, rhs)[i] of the backtest core at one bar, computed by core compare itself over the two bars i-1 and
    i, so the rule cannot drift from the Backtest's: bar 0 never true; NaN on either side false; a cross needs both
    sides finite on bar i-1 as well. */
export function compareAt(lhs: Operand, op: Op, rhs: Operand, i: number): boolean {
  if (!(i >= 1)) return false;
  const a = [valueAt(lhs, i - 1), valueAt(lhs, i)];
  const b = typeof rhs === 'number' ? null : [rhs.get(i - 1), rhs.get(i)];
  return compare(a, op, b, typeof rhs === 'number' ? rhs : 0, 2)[1] === 1;
}
/** The cross of EventCross as a signal by bar (compareAt with crosses_above / crosses_below). */
export const crossSignal = (lhs: Operand, op: 'crosses_above' | 'crosses_below', rhs: Operand) => (i: number): boolean => compareAt(lhs, op, rhs, i);

/** Why a series has no value at `at` (null when it has one): INSUFFICIENT_HISTORY when it has no value on any bar up to
    `at` (the core's INDICATOR_OUTPUT_EMPTY, per ticker); NULL_AT_EVALUATION when it had values before. */
export function naReason(v: BarView, at: number): NaReason | null {
  if (Number.isFinite(v.get(at))) return null;
  return v.firstValid < 0 || v.firstValid > at ? 'INSUFFICIENT_HISTORY' : 'NULL_AT_EVALUATION';
}

/** The ticker's evaluation bar: its last bar on or before E (dates ascending). -1 when it has none (a ticker listed
    after E cannot be evaluated; the universe never holds one, since E = price_through covers every published bar). */
export function evaluationBar(dates: readonly string[], evaluationDate: string): number {
  let lo = 0, hi = dates.length - 1, j = -1;
  while (lo <= hi) { const mid = (lo + hi) >> 1; if (dates[mid] <= evaluationDate) { j = mid; lo = mid + 1 } else hi = mid - 1 }
  return j;
}

/** A wire number (report 8.5): the raw double rounded to 12 significant digits; null for a missing or non-finite value
    (no NaN or Infinity on the wire, I5). */
export const round12 = (x: number | null | undefined): number | null => typeof x === 'number' && Number.isFinite(x) ? Number(x.toPrecision(12)) : null;

/* ---- one condition on one ticker ---------------------------------------------------------------------------------- */

/** One condition on one ticker by bar index, before dates and remarks are attached (toCell). status 'na' iff reason. */
export interface Evaluation {
  status: 'pass' | 'fail' | 'na';
  reason: NaReason | null;
  value?: number | null;             // VALUE: the metric at `at`
  lhs?: number | null; rhs?: number | null;   // STATE and EVENT: the current values at `at` (null when missing)
  eventBar?: number | null;          // EVENT: j, the latest bar in [at-within+1, at] with the signal (null: none)
  barsAgo?: number | null;           // EVENT: at - j
  lastEventBar?: number | null;      // EVENT: the latest bar in [at-withinMax+1, at] with the signal (null: none)
}

/** VALUE (report 6.9): NA with naReason(v, at) when the metric has no value at `at`; else pass iff x > value (gt),
    x < value (lt) or value <= x <= value2 (between, inclusive; value > value2 is refused by validate.ts with field
    value2, never reordered here; value = value2 is accepted). value: x. */
export function evaluateValue(v: BarView, test: Pick<ValueTest, 'op' | 'value' | 'value2'>, at: number): Evaluation {
  throw new Error('not implemented: evaluateValue');
}

/** STATE compare (report 6.9): pass iff compareAt(lhs, op, rhs, at). lhs and rhs: the current values (null for a
    missing value; a constant side is its value). NA only when a series side has no value at `at`: the reason of the
    lhs first, then of the rhs (naReason); otherwise pass or fail. */
export function evaluateState(lhs: Operand, op: 'gt' | 'lt', rhs: Operand, at: number): Evaluation {
  throw new Error('not implemented: evaluateState');
}

/** STATE pattern (report 6.9): pass iff signal[at] === 1, else fail (a pattern signal is 0 where its inputs are missing,
    as the core's PRICE_ACTION conditions are; it is never NA). */
export function evaluateStatePattern(signal: ArrayLike<number>, at: number): Evaluation {
  throw new Error('not implemented: evaluateStatePattern');
}

/** EVENT (report 6.9): signalAt(i) for i in [at-within+1, at]; j = the largest such i where it is true -> pass with
    eventBar j and barsAgo at - j; lastEventBar = the largest i in [at-withinMax+1, at] where it is true (null if none).
    current: the sides of a cross, whose values at `at` are returned as lhs and rhs. When no event is found: NA with the
    first side's naReason at `at` if a side of the cross is INSUFFICIENT_HISTORY there (it could never cross), else fail
    (a side without a value only at `at` cannot hide an earlier cross; a pattern event is never NA).
    within: 1..withinMax (validate.ts refuses others; RangeError here). Reads bars at-withinMax..at only, so a tail of
    withinMax + 1 bars suffices. */
export function evaluateEvent(signalAt: (i: number) => boolean, within: number, withinMax: number, at: number, current?: { lhs: Operand; rhs: Operand }): Evaluation {
  throw new Error('not implemented: evaluateEvent');
}

/* ---- remarks and the wire cell -------------------------------------------------------------------------------------- */

/** The first bar a series' value at `at` depends on (report 6.12 lookback): window class -> at - window + 1, where window
    = the series' firstValid + 1 on this ticker (its first full window), plus `extra` bars before (an EVENT searches
    `within` bars back, so its sides' lookback extends by within); recursive, cumulative and calendar -> null (they read
    the whole history); a bar field (historyClass null) -> at - extra. */
export function lookbackStart(historyClass: HistoryClass | null, firstValid: number, at: number, extra = 0): number | null {
  throw new Error('not implemented: lookbackStart');
}

/** PRICE_BREAK_IN_LOOKBACK (P4.1 A; report 6.9 Remarks, 6.12): for a ticker with PRICE_BREAK remarks, the cell remark
    when any side's lookback contains an ex-date: with d = the index of the ticker's first bar on or after the ex-date,
    the lookback [start, at] contains it iff start < d <= at (start null: d <= at), i.e. the values mix bars from both
    sides of the break. Never for flow cells, ADV20 or universe attributes (their callers pass no start). The value,
    pass and fail are unchanged; this only marks them. */
export function priceBreakRemark(starts: readonly (number | null)[], dates: readonly string[], at: number, exDates: readonly string[]): CellRemark | null {
  throw new Error('not implemented: priceBreakRemark');
}

/** The wire cell of one evaluation (report 8.5): dates from the ticker's bars (eval_date = dates[at], event_date =
    dates[eventBar], last_event_date = dates[lastEventBar]), market_sessions_ago = the number of IHSG calendar dates d
    with event_date < d <= eval_date, numbers through round12, unit from the resolved metric, reason exactly when
    status is 'na', remark as priceBreakRemark gave it. A condition the planner did not evaluate for a ticker is
    status 'not_evaluated' with reason null (never shown on a displayed row: S4 completes them, report 6.10). */
export function toCell(id: string, e: Evaluation, ctx: { dates: readonly string[]; at: number; ihsgCalendar: readonly string[]; unit: string | null; remark: CellRemark | null }): Cell {
  throw new Error('not implemented: toCell');
}
