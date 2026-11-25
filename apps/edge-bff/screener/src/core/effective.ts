/* The effective window of a recursive output (EXEC-PRICE-DISTORTION UD55; the user 2026-11-25, "3. Ok boleh": option
   (a), "an effective window per output, measured by the generator (the bars after which cutting the start changes the
   value by less than a tolerance, 0.1 % of its size), used for the cell mark, the row badge (D-1) and the Backtest trade
   flag"). A recursive output (RSI, EMA, MACD) reads its whole history, but the effect of a bar far enough back is below
   the tolerance: the generator (scripts/build-screener-registry.mjs effectiveProbe) measures how many bars that takes,
   and the lookback rule (evaluate.ts seriesLookbackStart, read by the Screener's cell mark and the Backtest's
   Calc.reach) stops there instead of at the first bar.

   The window is counted in moving bars, not in sessions: a recursion such as RSI's average gain over average loss holds
   its value, and with it the effect of an old bar, on a session whose prices do not move (a stock pinned at its floor,
   a session without trades), and starts to forget again only when they move. A bar moves on the fields an output reads
   (its inputs: the poison probe's fields at the chosen options, metrics.ts ResolvedSeries.inputs) when each of them has
   a finite value that differs from the bar before's; bar 0 moves. So on a liquid stock the window spans about as many
   sessions as it has moving bars, and on a stock that often closes unchanged it reaches further back (the generator's
   pinned and floor shapes measure that case). Any other bar only lengthens the window, never shortens it: a remark may
   then be set where the value has already forgotten the date, never left out where it has not.

   Pure module (no DOM, no Node API); the generator imports it, so the registry is rebuilt when it changes (a source of
   screener-registry.json). */
import type { Bars } from '../../../terminal/src/calc/indicators.ts';

/** A bar field an output can read. */
export type MoveField = 'O' | 'H' | 'L' | 'C' | 'V';

type Col = ArrayLike<number | null | undefined>;
const columns = (bars: Bars, fields: readonly MoveField[]): Col[] => fields.map(f => bars[f] as Col);
/** Whether bar i moves on the columns: bar 0 does; a later bar when each column has a finite value there that differs
    from the bar before's. No columns: every bar moves. */
function movesAt(cols: readonly Col[], i: number): boolean {
  if (i === 0) return true;
  for (const x of cols) {
    const a = x[i];
    if (!(typeof a === 'number' && Number.isFinite(a)) || a === x[i - 1]) return false;
  }
  return true;
}
/** Per bar, 1 when the bar moves on `fields`, else 0. */
export function movingBars(bars: Bars, fields: readonly MoveField[]): Uint8Array {
  const n = bars.C.length, out = new Uint8Array(n), cols = columns(bars, fields);
  for (let i = 0; i < n; i++) out[i] = movesAt(cols, i) ? 1 : 0;
  return out;
}
/** effectiveStarts at one bar t, walking back from it (the Screener reads one evaluated bar): the largest s with at
    least `window` bars moving on `fields` in s .. t, or -1 when the bars 0 .. t hold fewer (t < 0: -1). */
export function effectiveStartAt(bars: Bars, fields: readonly MoveField[], window: number, t: number): number {
  if (!(Number.isInteger(window) && window >= 1)) throw new RangeError(`effectiveStartAt: window must be a whole number of at least 1, not ${window}`);
  const cols = columns(bars, fields);
  let count = 0;
  for (let s = Math.min(t, bars.C.length - 1); s >= 0; s--) if (movesAt(cols, s) && ++count >= window) return s;
  return -1;
}

/** For each bar t, the first bar of the effective window of `window` moving bars ending at t: the largest s such that the
    bars s .. t hold at least `window` moving bars, or -1 when the bars 0 .. t hold fewer (the window reaches past the
    first bar: the whole history). One pass (s never moves back as t grows). */
export function effectiveStarts(moving: ArrayLike<number>, window: number): Int32Array {
  if (!(Number.isInteger(window) && window >= 1)) throw new RangeError(`effectiveStarts: window must be a whole number of at least 1, not ${window}`);
  const n = moving.length, out = new Int32Array(n);
  let s = 0, sum = 0;
  for (let t = 0; t < n; t++) {
    sum += moving[t] ? 1 : 0;
    while (s < t && sum - (moving[s] ? 1 : 0) >= window) { sum -= moving[s] ? 1 : 0; s++ }
    out[t] = sum >= window ? s : -1;
  }
  return out;
}
