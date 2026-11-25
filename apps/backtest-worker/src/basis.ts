/* EXEC-BACKTEST-REVAMP P9 (option A; user 2026-11-16: "A dulu", then "opsi A"; ERRORS M450, M458 item 2), and
   EXEC-PRICE-DISTORTION (user 2026-11-24, UD41 A: "value harus tetap ditampilkan as is dengan badge"; ERRORS M561):
   where a Flow value reads across a basis the data up to its own bar leaves unsettled. The value is used as computed;
   this rule only marks it (the trade it opens carries flags.distortions, the run FLOW_BASIS_CHANGE). Before
   EXEC-PRICE-DISTORTION the value was left empty, and an empty value failed its condition, so those days opened no
   trade. The broker lots are on the published prices' basis already (datafile.ts onPriceBasis, the factors the
   publisher measured per corporate action: the adjusted history, K4 a, as the look-ahead gate holds it). A value at bar
   i that reads the bars [start, i] is distorted when
   - one of those bars is off the price basis by its own data: its Regular-board broker VWAP lies outside that bar's
     range (low and high, RANGE_TOLERANCE either way). Broker prices of one session lie inside its range; a VWAP outside
     it is a broker day on another scale (a range re-downloaded after a split without a marker, PBSA; a factor not
     measured). Measured 2026-11-16 (verification/backtest/basis, real_data.ts): BBRI, GOTO and ALKA 0 of 891-916
     sessions outside, COCO every session before its rights issue of 2026-07-09 before the factor and none after it;
   - an action falls inside (start, i] whose basis is not settled across it: pending, unresolved, or a published close
     not reloaded after it (price raw: the prices and the lots both jump there);
   - Stage C2 (user 2026-11-16 "A", ERRORS M459 items 1, 9): an action falls inside (start, i] and bar i is before its
     `decided` date (ex + the publisher's window): the publisher's decision reads the sessions up to that date, so on an
     earlier bar the action counts as undecided whatever its published status. The status only marks; the value itself
     reads the published columns, the same whatever the status (the look-ahead gate, lookahead.test.ts Stage C2).
   The caller applies the actions to every Flow value (Stage C2: the lots of every family mix scales across an unsettled
   action, not the broker prices only) and the per-day guard to the values that compare a broker price with the close.
   A value's mark on day t depends on days up to t only. */
import type { Calc } from '../../edge-bff/backtest/src/core/conditions.ts';

export const RANGE_TOLERANCE = 0.01;

interface Blocks { off: Int32Array; actions: { ex: string; settled: boolean; decided: string }[] }
const MEMO = new WeakMap<Calc, Blocks>();

function blocks(c: Calc): Blocks {
  let b = MEMO.get(c);
  if (b) return b;
  const meta = c.meta.broker, dates = c.meta.dates ?? [], n = dates.length, off = new Int32Array(n + 1);
  if (meta) {
    const cols = meta.columns, regular = cols.boards.indexOf('Regular'), at = new Map(dates.map((d, k) => [d, k]));
    const value = new Float64Array(n), lots = new Float64Array(n);
    for (let k = 0; k < cols.rows; k++) {
      if (cols.M[k] !== regular) continue;
      const i = at.get(cols.dates[cols.D[k]]);
      if (i === undefined) continue;
      value[i] += cols.BV[k] + cols.SV[k]; lots[i] += cols.BL[k] + cols.SL[k];
    }
    const H = c.bars.H as ArrayLike<number | null>, L = c.bars.L as ArrayLike<number | null>;
    for (let i = 0; i < n; i++) {
      const v = lots[i] > 0 ? value[i] / (100 * lots[i]) : NaN, h = H[i], l = L[i];
      const outside = Number.isFinite(v) && typeof h === 'number' && typeof l === 'number' && (v > h * (1 + RANGE_TOLERANCE) || v < l * (1 - RANGE_TOLERANCE));
      off[i + 1] = off[i] + (outside ? 1 : 0);
    }
  }
  const actions = (meta?.basis ?? []).map(a => ({ ex: a.ex, decided: a.decided ?? a.ex,
    settled: !(a.status === 'pending' || a.status === 'unresolved' || a.price === 'raw') }));
  MEMO.set(c, b = { off, actions });
  return b;
}

/** Whether a Flow value at bar `i` that reads the bars [start, i] is distorted (see the header). `offDays`: the
    per-day guard applies too (a broker price compared with the close; the actions apply to every Flow value, user "A"). */
export function basisDistorted(c: Calc, start: number, i: number, offDays = true): boolean {
  const b = blocks(c), dates = c.meta.dates ?? [], s = Math.max(0, start);
  if (offDays && b.off[i + 1] - b.off[s] > 0) return true;
  const from = dates[s], to = dates[i];
  return b.actions.some(a => from < a.ex && a.ex <= to && (!a.settled || to < a.decided));
}

/** How many bars are off the price basis by their own data (verification: real_data.ts reports it per ticker). */
export const offBasisCount = (c: Calc): number => { const off = blocks(c).off; return off[off.length - 1] };
