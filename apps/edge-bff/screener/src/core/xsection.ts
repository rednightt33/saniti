/* Cross-sectional values on the fixed population (EXEC-SCREENER; report TARGET ARCHITECTURE 6.9 "rs_rank (P7)",
   6.10 stage S1). Today: return_rank {window}. The population is fixed before any condition and never depends on the
   user's universe filters, so editing a filter moves no rank and the planner can treat S1 as population-level (never
   pruned):
   - population: active, non-stale stocks (last bar = E) without a PRICE_BREAK remark and with a finite value at E
     (P4: hidden tickers are outside it; a ticker the user shows through a chip is ranked AGAINST it, so showing it
     moves no other rank);
   - pct = 100 x #(population values strictly lower than the ticker's value) / (P - 1) for a member (report 6.9: the
     P - 1 others); a NaN value is excluded (fixes the prototype's NaN-in-denominator defect, audit/html_model.md
     section 7 item 9); ties share a rank; P < 2 -> null. A ticker outside the population (shown through a chip) is
     compared with all P members, so its denominator is P (with P - 1 its rank could exceed 100: a value above every
     member would give 100 x P / (P - 1)); every rank stays in [0, 100];
   - IHSG aligned with datafile.asOf where an index value is needed (datafile.ts:259).
   Pure module (no DOM, no Node API). Typed stubs for the core-logic agent. */
import type { UniverseRow } from './contract.ts';

/** The fixed rank population at E (rows of the snapshot's universe, every listed stock, hidden ones included). */
export function rankPopulation(rows: readonly UniverseRow[], values: ReadonlyMap<string, number>, evaluationDate: string): Set<string> {
  throw new Error('not implemented: rankPopulation');
}

/** Percent rank of every ticker in `values` against the population (rule above): 100 x #(population values strictly
    lower) / the number of OTHER members it is compared with (P - 1 for a member, P for a ticker outside the
    population), so a rank is always in [0, 100]; null for a ticker without a finite value, when P < 2, or when it has
    no other member to be compared with. */
export function percentRank(values: ReadonlyMap<string, number>, population: ReadonlySet<string>): Map<string, number | null> {
  throw new Error('not implemented: percentRank');
}

/** return_rank {window}: each ticker's return over `window` of its own bars at its evaluation bar,
    (close[at] / close[at - window] - 1) x 100, ranked with percentRank on the population. The default windows are
    pre-warmed per publication (report 6.7); the window's range comes from screener-metrics.json. It is price-derived
    with a window (not a flow cell, ADV20 or universe attribute), so on a PRICE_BREAK row shown through the chip its cell
    carries PRICE_BREAK_IN_LOOKBACK when the ex-date falls in (at - window, at] (evaluate.ts priceBreakRemark with start
    at - window); the rank is shown (P4.1 A), and the ticker stays outside the population, so no other rank moves. */
export function returnRank(closes: ReadonlyMap<string, { at: number; close: ArrayLike<number | null> }>, window: number, population: ReadonlySet<string>): Map<string, number | null> {
  throw new Error('not implemented: returnRank');
}
