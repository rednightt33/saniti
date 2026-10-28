/* The universe the page shows before any run (report 6c.4 S5: an empty screen's rows are the universe rows after the
   universe filter; 9.2 "In universe X of N" computed in the page on every edit), through the core's applyUniverse:
   the same function the worker runs in stage S0 (report 9.1; core/universe.ts imports only contract types, so the
   page bundle stays free of formula code). A metric filter that needs a formula is left pending by applyUniverse:
   the page's count is then not exact and the table comes from a run (run.ts). A run's own `universe` counts (the
   worker's) always win over these once it answers. Pure: no DOM. */
import type { UniverseCounts, UniverseDef, UniverseRow } from './core/contract.ts';
import { applyUniverse, hasPriceBreak } from './core/universe.ts';

export interface UniverseView { rows: UniverseRow[]; counts: UniverseCounts; exact: boolean }

export function universeView(all: UniverseRow[], u: UniverseDef): UniverseView {
  const r = applyUniverse(all, u);
  return { rows:r.eligible, counts:r.counts, exact:r.pending.length === 0 };
}

/** how many tickers each P4 chip hides on the whole universe (the chip's count, report 9.2): a row both stale and
    broken counts once, as stale (applyUniverse applies the chips in that order) */
export const hiddenCounts = (all: UniverseRow[]) => ({ stale:all.filter(r => r.stale).length, breaks:all.filter(r => !r.stale && hasPriceBreak(r)).length });
