/* EXEC-BACKTEST-REVAMP P9 (option A; user 2026-11-16: "A dulu", then "opsi A"; ERRORS M450, M458 item 2): where a
   broker-price Flow value (a broker VWAP, an implied cost, a distance from one) stays empty, decided on the bars up to
   its own bar only. The broker lots are on the published prices' basis already (datafile.ts onPriceBasis, the factors the
   publisher measured per corporate action), so the value is kept wherever both are known to be on one basis. A value at
   bar i that reads the bars [start, i] stays empty when
   - one of those bars is off the price basis by its own data: its Regular-board broker VWAP lies outside that bar's
     range (low and high, RANGE_TOLERANCE either way). Broker prices of one session lie inside its range; a VWAP outside
     it is a broker day on another scale (a range re-downloaded after a split without a marker, PBSA; a factor not
     measured). Measured 2026-11-16 (verification/backtest/basis, real_data.ts): BBRI, GOTO and ALKA 0 of 891-916
     sessions outside, COCO every session before its rights issue of 2026-07-09 before the factor and none after it;
   - an action falls inside (start, i] whose basis is not settled across it: pending (too few sessions after its ex date
     yet), unresolved, or a published close not reloaded after it (price raw: the prices and the lots both jump there).
   Before P9 the rule also emptied every bar before an action dated on or before 2026-09-12, which read the action's
   date before it happened (M458 item 2); a value's availability on day t now depends on days up to t only. */
import type { Calc } from '../../edge-bff/backtest/src/core/conditions.ts';

export const RANGE_TOLERANCE = 0.01;

interface Blocks { off: Int32Array; actions: string[] }
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
  const actions = (meta?.basis ?? []).filter(a => a.status === 'pending' || a.status === 'unresolved' || a.price === 'raw').map(a => a.ex);
  MEMO.set(c, b = { off, actions });
  return b;
}

/** Whether a broker-price value at bar `i` that reads the bars [start, i] stays empty (see the header). */
export function basisBlocked(c: Calc, start: number, i: number): boolean {
  const b = blocks(c), dates = c.meta.dates ?? [], s = Math.max(0, start);
  if (b.off[i + 1] - b.off[s] > 0) return true;
  const from = dates[s], to = dates[i];
  return b.actions.some(d => from < d && d <= to);
}

/** How many bars are off the price basis by their own data (verification: real_data.ts reports it per ticker). */
export const offBasisCount = (c: Calc): number => { const off = blocks(c).off; return off[off.length - 1] };
