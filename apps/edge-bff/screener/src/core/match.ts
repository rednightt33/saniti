/* Match, near miss and counts (EXEC-SCREENER; report TARGET ARCHITECTURE 6.9 "Match and near miss", 6.10). One rule
   for the result table, the preview's status pill and the CSV, so they can never disagree (the prototype had a second
   near rule at its line 1599, audit/html_ui.md §3.15):
   - need = entryNeed(logic, at_least, active) of the backtest core (conditions.ts:263; equal to the prototype's
     needOf): all -> active, any -> 1, at_least -> min(at_least, active) (above the active count it means all);
   - met counts PASS cells only (FAIL, NA and not_evaluated never add);
   - match = met >= need (need 0, no active condition: every eligible ticker is a match row with met 0, the
     universe listed in mode 'universe_only', report 8.5);
   - near = !match && need >= 2 && met == need - 1. With need 1 there is no near miss (a miss by one is no condition).
   na_count is returned beside them; it never changes match or near.
   Pure module (no DOM, no Node API): the worker imports it; the page reads `status`, `met` and `need` from the answer
   and never recomputes them. */
import { entryNeed } from '../../../backtest/src/core/conditions.ts';
import type { Cell, Logic, PreviewStatus, RowStatus } from './contract.ts';

/** need of a definition with `active` enabled conditions (core entryNeed; validate.ts has already refused a logic
    other than all / any / at_least and an at_least that is not a whole number of at least 1). 0 when no condition is
    active (mode 'universe_only': the universe is listed, report 8.5). */
export const needOf = (logic: Logic, atLeast: number | undefined, active: number): number => active > 0 ? entryNeed(logic, atLeast, active) : 0;

export const isMatch = (met: number, need: number): boolean => met >= need;
/** THE near rule (report 6.9): not a match, need >= 2, and exactly one condition short. */
export const isNear = (met: number, need: number): boolean => !isMatch(met, need) && need >= 2 && met === need - 1;
/** A result row's status, or null when the ticker is neither a match nor near (it is not a row of the answer). */
export const rowStatus = (met: number, need: number): RowStatus | null => isMatch(met, need) ? 'match' : isNear(met, need) ? 'near' : null;
/** The preview's status (report 8.6): outside_universe when the ticker fails S0 (its cells are still returned). */
export const previewStatus = (inUniverse: boolean, met: number, need: number): PreviewStatus =>
  !inUniverse ? 'outside_universe' : rowStatus(met, need) ?? 'fail';

/** met (PASS cells) and na_count (NA cells) of one ticker's cells. */
export function countCells(cells: readonly Pick<Cell, 'status'>[]): { met: number; na_count: number } {
  let met = 0, na = 0;
  for (const c of cells) { if (c.status === 'pass') met++; else if (c.status === 'na') na++ }
  return { met, na_count: na };
}
