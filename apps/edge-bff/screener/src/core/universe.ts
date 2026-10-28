/* Universe hard filters, stage S0 (EXEC-SCREENER; report TARGET ARCHITECTURE 6.10 S0, 6.12; API CONTRACT 8.4, 8.5;
   contract.ts UniverseDef). ONE function for the page (the "In universe X of N" count and the chip counts, from
   GET /universe rows) and the worker (S0 of every run, on the same rows), so the two can never disagree (TEST PLAN
   10b.5 "Page = worker"). Hence this module imports only contract.ts types: no formula, no backtest core (the page
   bundle carries none, report I1, 9.1). The rules:
   - security type: 'stock' only (P15); IHSG is never in the stock universe (it is the vs_index reference);
   - sectors_in / industries_in: keep a row whose value is in the list; a row without that classification (null:
     the reference file's 'Undefined', counted apart as unclassified, never a value) only when include_unclassified;
     sectors_out / industries_out: drop a row whose value is in the list; never drop an unclassified row (P15);
   - price_min: last >= price_min; adv20_min_idr: adv20_idr >= adv20_min_idr; min_history_bars: bars >= the value;
     a null attribute fails a set bound (it cannot be shown to pass); boundaries inclusive (TEST PLAN 10b.5);
   - traded_on_eval_date (default true, P4): drop stale rows (row.stale, last_bar < E as the worker built the row);
     counted in stale_hidden;
   - exclude_price_breaks (default true, P4): drop rows with a PRICE_BREAK remark; counted in price_break_hidden
     (a row both stale and broken is counted once, as stale: the chips are applied in that order);
   - tickers: keep only the listed tickers (validate.ts has refused unknown ones by name);
   - metric_filters on a universe attribute ({kind: 'universe', attr} naming a numeric field of the row: last,
     chg_1d_pct, adv20_idr, bars) are applied here with the VALUE rule (gt, lt strict; between inclusive; a null value
     fails); every other metric filter needs a formula, so it is left in `pending` (its index): the worker evaluates
     those on `eligible` right after this, through evaluate.ts, and adds the refused rows to filtered_out, while the page
     marks its own count as not exact.
   Counts (contract.ts UniverseCounts): listed = rows.length; eligible = rows kept; stale_hidden and
   price_break_hidden as above (0 when the chip is off); filtered_out = listed - eligible - stale_hidden -
   price_break_hidden.
   Pure module (no DOM, no Node API). Implemented: applyUniverse, isStale, hasPriceBreak; priceBreakRemarks is a typed
   stub (worker-side, at snapshot build). */
import type { PriceBreakRemark, UniverseCounts, UniverseDef, UniverseRow, ValueTest } from './contract.ts';

/** eligible: the rows kept, in row order; pending: indexes into def.metric_filters that need the worker (above). */
export interface UniverseResult { eligible: UniverseRow[]; counts: UniverseCounts; pending: number[] }

const inList = (v: string | null, list: readonly string[] | undefined): boolean => v !== null && !!list && list.includes(v);
/** A classification include filter: a value in the list, or no classification with include_unclassified (P15). */
const included = (v: string | null, list: readonly string[] | undefined, unclassified: boolean): boolean =>
  !list || !list.length || inList(v, list) || (v === null && unclassified);
const atLeast = (v: number | null, bound: number | null | undefined): boolean => bound === null || bound === undefined || (v !== null && Number.isFinite(v) && v >= bound);

/** The VALUE rule on a row attribute (evaluate.ts evaluateValue's rule; a null value fails a filter). */
function valuePasses(v: unknown, t: ValueTest): boolean {
  if (typeof v !== 'number' || !Number.isFinite(v)) return false;
  return t.op === 'gt' ? v > t.value : t.op === 'lt' ? v < t.value : v >= t.value && v <= (t.value2 as number);
}
/** The row field a universe-attribute filter reads, or null when the filter needs the worker. */
function rowAttr(t: ValueTest, sample: UniverseRow | undefined): string | null {
  const m = t.metric;
  if (!m || m.kind !== 'universe' || typeof m.attr !== 'string') return null;
  if (sample && !(m.attr in sample)) return null;
  return ['ticker', 'name', 'sector', 'industry', 'first_bar', 'last_bar', 'stale', 'remarks'].includes(m.attr) ? null : m.attr;
}

/** S0 (rules above), in row order. */
export function applyUniverse(rows: readonly UniverseRow[], def: UniverseDef): UniverseResult {
  const filters = (def.metric_filters || []).map(t => ({ t, attr: rowAttr(t, rows[0]) }));
  const pending = filters.flatMap((f, i) => f.attr === null ? [i] : []);
  const tickers = def.tickers ? new Set(def.tickers) : null, unclassified = def.include_unclassified === true;
  let stale = 0, broken = 0;
  const eligible: UniverseRow[] = [];
  for (const r of rows) {
    if (def.traded_on_eval_date && r.stale) { stale++; continue }
    if (def.exclude_price_breaks && hasPriceBreak(r)) { broken++; continue }
    if (tickers && !tickers.has(r.ticker)) continue;
    if (!included(r.sector, def.sectors_in, unclassified) || inList(r.sector, def.sectors_out)) continue;
    if (!included(r.industry, def.industries_in, unclassified) || inList(r.industry, def.industries_out)) continue;
    if (!atLeast(r.last, def.price_min) || !atLeast(r.adv20_idr, def.adv20_min_idr) || !atLeast(r.bars, def.min_history_bars)) continue;
    if (filters.some(f => f.attr !== null && !valuePasses((r as unknown as Record<string, unknown>)[f.attr], f.t))) continue;
    eligible.push(r);
  }
  return {
    eligible, pending,
    counts: { listed: rows.length, eligible: eligible.length, stale_hidden: stale, price_break_hidden: broken, filtered_out: rows.length - eligible.length - stale - broken },
  };
}

/** STALE (report 6.5): the row's last bar is before E. */
export const isStale = (row: Pick<UniverseRow, 'last_bar'>, evaluationDate: string): boolean => row.last_bar < evaluationDate;
/** The row carries a PRICE_BREAK remark (derived at snapshot build, priceBreakRemarks). */
export const hasPriceBreak = (row: Pick<UniverseRow, 'remarks'>): boolean => row.remarks.some(r => r.code === 'PRICE_BREAK');

/** One price-affecting corporate action of the `actions` xsection file (report 6.5 Phase 1 files). */
export interface ActionRow { ticker: string; type: string; ex_date: string; ratio_old: number | null; ratio_new: number | null }
/** The derived PRICE_BREAK remarks of one ticker (TEMPORARY until the D22 data-layer fix; report 6.12): one per action
    whose type is in `priceActionTypes` (datafile.ts PRICE_ACTION_TYPES) with boundary (engine.ts
    ADJUSTED_HISTORY_BOUNDARY, 2026-09-12) <= ex_date <= the ticker's last bar, oldest first. close_ratio = the close
    of the ticker's first bar on or after the ex-date / the close of the bar before it (null when either is missing).
    An ex-date after the last bar is not flagged until it is in the data (MGLV), an action before the boundary never
    (RAJA, adjusted); a cash dividend is not a price-affecting type. The two constants are passed in, so this module
    stays free of the backtest core for the page. */
export function priceBreakRemarks(actions: readonly ActionRow[], dates: readonly string[], closes: ArrayLike<number | null | undefined>, opts: { boundary: string; priceActionTypes: readonly string[] }): PriceBreakRemark[] {
  throw new Error('not implemented: priceBreakRemarks');
}
