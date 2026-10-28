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
   Pure module (no DOM, no Node API). */
import type { UniverseRow } from './contract.ts';

/** The fixed rank population at E (rows of the snapshot's universe, every listed stock, hidden ones included): a row
    that is not stale (its last bar is E), carries no PRICE_BREAK remark and has a finite value. */
export function rankPopulation(rows: readonly UniverseRow[], values: ReadonlyMap<string, number | null>, evaluationDate: string): Set<string> {
  const out = new Set<string>();
  for (const r of rows) {
    if (r.stale || r.last_bar !== evaluationDate || r.remarks.some(x => x.code === 'PRICE_BREAK')) continue;
    const v = values.get(r.ticker);
    if (typeof v === 'number' && Number.isFinite(v)) out.add(r.ticker);
  }
  return out;
}

/** Percent rank of every ticker in `values` against the population (rule above): 100 x #(population values strictly
    lower) / the number of OTHER members it is compared with (P - 1 for a member, P for a ticker outside the
    population), so a rank is always in [0, 100]; null for a ticker without a finite value, when P < 2, or when it has
    no other member to be compared with. */
export function percentRank(values: ReadonlyMap<string, number | null>, population: ReadonlySet<string>): Map<string, number | null> {
  const pop: number[] = [];
  for (const t of population) { const v = values.get(t); if (typeof v === 'number' && Number.isFinite(v)) pop.push(v) }
  pop.sort((a, b) => a - b);
  const P = pop.length, out = new Map<string, number | null>();
  const lower = (x: number) => { let lo = 0, hi = P; while (lo < hi) { const m = (lo + hi) >> 1; if (pop[m] < x) lo = m + 1; else hi = m } return lo };
  for (const [t, v] of values) {
    const member = population.has(t), denom = member ? P - 1 : P;
    out.set(t, typeof v === 'number' && Number.isFinite(v) && P >= 2 && denom >= 1 ? 100 * lower(v) / denom : null);
  }
  return out;
}

/** return_rank {window}: each ticker's return over `window` of its own bars at its evaluation bar,
    (close[at] / close[at - window] - 1) x 100, ranked with percentRank on the population. The default windows are
    pre-warmed per publication (report 6.7); the window's range comes from screener-metrics.json. It is price-derived
    with a window (not a flow cell, ADV20 or universe attribute), so on a PRICE_BREAK row shown through the chip its cell
    carries PRICE_BREAK_IN_LOOKBACK when the ex-date falls in (at - window, at] (evaluate.ts priceBreakRemark with start
    at - window); the rank is shown (P4.1 A), and the ticker stays outside the population, so no other rank moves. */
export function returnRank(closes: ReadonlyMap<string, { at: number; close: ArrayLike<number | null> }>, window: number, population: ReadonlySet<string>): Map<string, number | null> {
  return percentRank(returnsOf(closes, window), population);
}
/** Each ticker's return over `window` of its own bars at its evaluation bar, (close[at] / close[at - window] - 1) x 100;
    null with fewer bars, a missing close or a zero base. */
export function returnsOf(closes: ReadonlyMap<string, { at: number; close: ArrayLike<number | null | undefined> }>, window: number): Map<string, number | null> {
  if (!(Number.isInteger(window) && window >= 1)) throw new RangeError(`returnsOf: window must be a whole number of at least 1, not ${window}`);
  const out = new Map<string, number | null>(), ok = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
  for (const [t, { at, close }] of closes) {
    const c = at >= 0 ? close[at] : null, c0 = at - window >= 0 ? close[at - window] : null;
    out.set(t, ok(c) && ok(c0) && c0 !== 0 ? (c / c0 - 1) * 100 : null);
  }
  return out;
}
/** return_rank {window} of every ticker in `closes` (rows: the snapshot's universe rows, hidden ones included): the
    returns, the fixed population at E (rankPopulation over the returns) and the ranks against it. Population-level
    (stage S1): it never depends on the user's filters, so the planner never prunes it and editing a filter moves no rank. */
export function returnRankAll(rows: readonly UniverseRow[], closes: ReadonlyMap<string, { at: number; close: ArrayLike<number | null | undefined> }>, window: number, evaluationDate: string): { returns: Map<string, number | null>; population: Set<string>; ranks: Map<string, number | null> } {
  const returns = returnsOf(closes, window), population = rankPopulation(rows, returns, evaluationDate);
  return { returns, population, ranks: percentRank(returns, population) };
}
