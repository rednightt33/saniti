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
     `at`, NULL_AT_EVALUATION when it has values earlier but none at `at`, or when the ticker lacks a bar field the
     series needs (IHSG volume; naReason); the flow, applicability and integrity reasons come from their own modules.
     NA never fails the whole screen;
   - remarks: a cell on a PRICE_BREAK row whose lookback contains an ex-date keeps its value and its pass or fail and
     carries PRICE_BREAK_IN_LOOKBACK (P4.1 A; user 2026-10-28; where the TEST PLAN still says NA, P4.1 A wins).
   Evaluating on a tail (metrics.ts Tail, within_max + 1 bars) equals evaluating on the full series at every tail bar:
   compare reads only bars i and i-1 (report 6.7 verification). A side read at the output's price_compare_lag 1
   (Donchian's prior band, report 6.8) is therefore its own series, transform lag(output, 1) resolved through
   metrics.ts (computed on the full series, then tailed), never a view shifted over the unlagged tail: a shifted read
   of a cross at the window's first bar (at - within_max + 1) would need bar at - within_max - 1, one bar before the
   tail, and would silently miss that event.
   Pure module (no DOM, no Node API). */
import { compare } from '../../../backtest/src/core/conditions.ts';
import type { Op } from '../../../backtest/src/core/conditions.ts';
import type { Num } from '../../../terminal/src/calc/indicators.ts';
import type { Cell, CellRemark, HistoryClass, NaReason, ValueTest } from './contract.ts';
import type { Tail } from './metrics.ts';

/* ---- views of a series by bar index ------------------------------------------------------------------------------ */

/** A metric's values on one ticker's bars, read by the ticker's bar index: a full series or a tail. get(i) is NaN for a
    missing value and for a bar the view does not hold (i < from or i >= n). firstValid / lastValid: the first and last
    bar of the full series with a value (-1 when none). inputMissing: the ticker lacks a bar field the series needs
    (metrics.ts missingInput over ResolvedSeries.inputs: volume on IHSG for an I27 VWMA basis), so a missing value is
    NULL_AT_EVALUATION, never INSUFFICIENT_HISTORY (naReason; TEST PLAN 10b.3). */
export interface BarView { readonly n: number; readonly from: number; readonly firstValid: number; readonly lastValid: number; readonly inputMissing: boolean; get(i: number): number }
export function viewOfTail(t: Tail, inputMissing = false): BarView {
  return { n: t.n, from: t.from, firstValid: t.firstValid, lastValid: t.lastValid, inputMissing, get: i => (i >= t.from && i < t.n ? t.values[i - t.from] : NaN) };
}
export function viewOfSeries(s: ArrayLike<Num | undefined>, inputMissing = false): BarView {
  let firstValid = -1, lastValid = -1;
  for (let i = 0; i < s.length; i++) if (typeof s[i] === 'number' && Number.isFinite(s[i])) { if (firstValid < 0) firstValid = i; lastValid = i }
  return { n: s.length, from: 0, firstValid, lastValid, inputMissing, get: i => { const v = s[i]; return typeof v === 'number' && Number.isFinite(v) ? v : NaN } };
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

/** Why a series has no value at `at` (null when it has one), report 6.9 NA reason codes and TEST PLAN 10b.3:
    NULL_AT_EVALUATION when the ticker lacks a bar field the series needs (v.inputMissing: "an option that needs volume
    on an instrument without volume (IHSG)", whatever its history); else INSUFFICIENT_HISTORY when it has no value on
    any bar up to `at` (the core's INDICATOR_OUTPUT_EMPTY, per ticker: too few bars, RANS with 74); NULL_AT_EVALUATION
    when it had values before (zero band width, flat window, zero volume on the bar). */
export function naReason(v: BarView, at: number): NaReason | null {
  if (Number.isFinite(v.get(at))) return null;
  if (v.inputMissing) return 'NULL_AT_EVALUATION';
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
  const x = v.get(at);
  if (!Number.isFinite(x)) return { status: 'na', reason: naReason(v, at) ?? 'NULL_AT_EVALUATION', value: null };
  return { status: valuePasses(x, test) ? 'pass' : 'fail', reason: null, value: x };
}
/** The VALUE rule on one number (gt, lt strict; between inclusive); universe.ts applies the same rule to row attributes. */
export function valuePasses(x: number, test: Pick<ValueTest, 'op' | 'value' | 'value2'>): boolean {
  switch (test.op) {
    case 'gt': return x > test.value;
    case 'lt': return x < test.value;
    case 'between': return x >= test.value && x <= (test.value2 as number);
  }
  throw new RangeError(`evaluateValue: op ${JSON.stringify(test.op)} is not gt, lt or between`);
}

/** STATE compare (report 6.9): pass iff compareAt(lhs, op, rhs, at). lhs and rhs: the current values (null for a
    missing value; a constant side is its value). NA only when a series side has no value at `at`: the reason of the
    lhs first, then of the rhs (naReason); otherwise pass or fail. */
export function evaluateState(lhs: Operand, op: 'gt' | 'lt', rhs: Operand, at: number): Evaluation {
  const a = valueAt(lhs, at), b = valueAt(rhs, at);
  const reason = (typeof lhs === 'number' ? null : naReason(lhs, at)) ?? (typeof rhs === 'number' ? null : naReason(rhs, at));
  if (reason) return { status: 'na', reason, lhs: num(a), rhs: num(b) };
  return { status: compareAt(lhs, op, rhs, at) ? 'pass' : 'fail', reason: null, lhs: a, rhs: b };
}
const num = (x: number): number | null => Number.isFinite(x) ? x : null;

/** STATE pattern (report 6.9): pass iff signal[at] === 1, else fail (a pattern signal is 0 where its inputs are missing,
    as the core's PRICE_ACTION conditions are; it is never NA). */
export function evaluateStatePattern(signal: ArrayLike<number> | BarView, at: number): Evaluation {
  return { status: signalAt(signal, at) ? 'pass' : 'fail', reason: null };
}
/** A 0/1 signal at bar i, from an array indexed by bar or a view (a cached tail of the pattern series); a bar it does
    not hold, or a missing value, is 0. */
export const signalAt = (signal: ArrayLike<number> | BarView, i: number): boolean =>
  i >= 0 && ('get' in signal && typeof (signal as BarView).get === 'function' ? (signal as BarView).get(i) === 1 : (signal as ArrayLike<number>)[i] === 1);

/** EVENT (report 6.9): signalAt(i) for i in [at-within+1, at]; j = the largest such i where it is true -> pass with
    eventBar j and barsAgo at - j; lastEventBar = the largest i in [at-withinMax+1, at] where it is true (null if none).
    current: the sides of a cross, whose values at `at` are returned as lhs and rhs. When no event is found: NA if a side
    of the cross could never have crossed (no value on any bar up to `at`: INSUFFICIENT_HISTORY, or NULL_AT_EVALUATION
    when its input is missing, naReason of that side, lhs first), else fail (a side without a value only at `at` cannot
    hide an earlier cross; a pattern event is never NA).
    within: 1..withinMax (validate.ts refuses others; RangeError here). Reads bars at-withinMax..at only, so a tail of
    withinMax + 1 bars suffices. */
export function evaluateEvent(signalAt: (i: number) => boolean, within: number, withinMax: number, at: number, current?: { lhs: Operand; rhs: Operand }): Evaluation {
  if (!(Number.isInteger(withinMax) && withinMax >= 1)) throw new RangeError(`evaluateEvent: withinMax must be a whole number of at least 1, not ${withinMax}`);
  if (!(Number.isInteger(within) && within >= 1 && within <= withinMax)) throw new RangeError(`evaluateEvent: within must be a whole number from 1 to ${withinMax}, not ${within}`);
  let eventBar: number | null = null, lastEventBar: number | null = null;
  for (let i = at; i > at - withinMax && i >= 0; i--) if (signalAt(i)) { lastEventBar = i; if (i > at - within) eventBar = i; break }
  const sides = current ? { lhs: num(valueAt(current.lhs, at)), rhs: num(valueAt(current.rhs, at)) } : {};
  if (eventBar !== null) return { status: 'pass', reason: null, ...sides, eventBar, barsAgo: at - eventBar, lastEventBar };
  if (current) for (const s of [current.lhs, current.rhs]) {
    if (typeof s === 'number') continue;
    const never = s.inputMissing || s.firstValid < 0 || s.firstValid > at;      // no value on any bar up to `at`
    if (never) return { status: 'na', reason: s.inputMissing ? 'NULL_AT_EVALUATION' : 'INSUFFICIENT_HISTORY', ...sides, eventBar: null, barsAgo: null, lastEventBar };
  }
  return { status: 'fail', reason: null, ...sides, eventBar: null, barsAgo: null, lastEventBar };
}

/* ---- remarks and the wire cell -------------------------------------------------------------------------------------- */

/** The first bar a series' value at `at` depends on (report 6.12 lookback): window class -> at - window + 1, where window
    = the series' firstValid + 1 on this ticker (its first full window), plus `extra` bars before (an EVENT searches
    `within` bars back, so its sides' lookback extends by within); recursive, cumulative and calendar -> null (they read
    the whole history, report 6.12); a bar field (historyClass null) -> at - extra. On a ticker whose early bars lack an
    input, firstValid comes later than the window needs and the lookback is overstated: the remark may then be set where
    the window is already clear of the ex-date, never left out where it is not (a remark never changes a result). */
export function lookbackStart(historyClass: HistoryClass | null, firstValid: number, at: number, extra = 0): number | null {
  if (historyClass === null) return at - extra;
  if (historyClass !== 'window' || firstValid < 0) return null;            // the whole history (or no value: no window to bound)
  return at - firstValid - extra;                                           // window = firstValid + 1 bars ending at `at`
}
/** lookbackStart with the window a reference states exactly (a pattern's, metrics.ts ResolvedSeries.window): the
    value at `at` reads bars [at - window + 1, at]; an infinite window (a recursive pattern) reads the whole history. */
export const lookbackStartOfWindow = (window: number, at: number, extra = 0): number | null => Number.isFinite(window) ? at - window + 1 - extra : null;

/** PRICE_BREAK_IN_LOOKBACK (P4.1 A; report 6.9 Remarks, 6.12): for a ticker with PRICE_BREAK remarks, the cell remark
    when any side's lookback contains an ex-date: with d = the index of the ticker's first bar on or after the ex-date,
    the lookback [start, at] contains it iff start < d <= at (start null: d <= at), i.e. the values mix bars from both
    sides of the break. Never for flow cells, ADV20 or universe attributes (their callers pass no start). The value,
    pass and fail are unchanged; this only marks them. */
export function priceBreakRemark(starts: readonly (number | null)[], dates: readonly string[], at: number, exDates: readonly string[]): CellRemark | null {
  if (!starts.length || !exDates.length) return null;
  for (const ex of exDates) {
    const d = firstOnOrAfter(dates, ex);
    if (d < 0 || d > at) continue;                                          // the ex-date is not in the ticker's bars up to `at`
    for (const s of starts) if (s === null ? d <= at : s < d) return 'PRICE_BREAK_IN_LOOKBACK';
  }
  return null;
}
/** Index of the first date on or after `date` (dates ascending), -1 when none. */
function firstOnOrAfter(dates: readonly string[], date: string): number {
  let lo = 0, hi = dates.length - 1, j = -1;
  while (lo <= hi) { const mid = (lo + hi) >> 1; if (dates[mid] >= date) { j = mid; hi = mid - 1 } else lo = mid + 1 }
  return j;
}
/** The number of calendar dates d with from < d <= to (the IHSG calendar, ascending): market_sessions_ago. */
export function sessionsBetween(calendar: readonly string[], from: string, to: string): number {
  const upper = (x: string) => { let lo = 0, hi = calendar.length; while (lo < hi) { const m = (lo + hi) >> 1; if (calendar[m] <= x) lo = m + 1; else hi = m } return lo };
  return Math.max(0, upper(to) - upper(from));
}

/** The wire cell of one evaluation (report 8.5): dates from the ticker's bars (eval_date = dates[at], event_date =
    dates[eventBar], last_event_date = dates[lastEventBar]), market_sessions_ago = the number of IHSG calendar dates d
    with event_date < d <= eval_date, numbers through round12, unit from the resolved metric, reason exactly when
    status is 'na', remark as priceBreakRemark gave it. A condition the planner did not evaluate for a ticker is
    status 'not_evaluated' with reason null (never shown on a displayed row: S4 completes them, report 6.10). */
export function toCell(id: string, e: Evaluation, ctx: { dates: readonly string[]; at: number; ihsgCalendar: readonly string[]; unit: string | null; remark: CellRemark | null }): Cell {
  const evalDate = ctx.dates[ctx.at] ?? null;
  const cell: Cell = { id, status: e.status, eval_date: evalDate, unit: ctx.unit, reason: e.status === 'na' ? e.reason ?? 'NULL_AT_EVALUATION' : null, remark: ctx.remark };
  if (e.value !== undefined) cell.value = e.status === 'na' ? null : round12(e.value);
  if (e.lhs !== undefined) cell.lhs = round12(e.lhs);
  if (e.rhs !== undefined) cell.rhs = round12(e.rhs);
  if (e.eventBar !== undefined) {
    const j = e.eventBar, k = e.lastEventBar ?? null;
    cell.event_date = j === null ? null : ctx.dates[j] ?? null;
    cell.bars_ago = j === null ? null : ctx.at - j;
    cell.market_sessions_ago = j === null || evalDate === null ? null : sessionsBetween(ctx.ihsgCalendar, ctx.dates[j], evalDate);
    cell.last_event_date = k === null ? null : ctx.dates[k] ?? null;
  }
  return cell;
}
/** The cell of a condition the planner did not evaluate for a ticker (report 8.5 status not_evaluated; never on a
    displayed row: S4 completes them, report 6.10). */
export const notEvaluatedCell = (id: string, evalDate: string | null): Cell => ({ id, status: 'not_evaluated', eval_date: evalDate, reason: null, remark: null });
