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
   - traded_on_eval_date (default false since EXEC-PRICE-DISTORTION, user 2026-11-24: "value harus tetap ditampilkan as is dengan badge", UD42 A; was true, P4; absent means false: only an explicit true hides
     them): drop stale rows (row.stale, last_bar < E as the worker built the row); counted in stale_hidden;
   - exclude_price_breaks (default false as above; absent means false): drop rows with a PRICE_BREAK remark; counted
     in price_break_hidden (a row both stale and broken is counted once, as stale: the chips are applied in that
     order, so the counts form one funnel: listed = eligible + stale_hidden + price_break_hidden + filtered_out);
   - indices_in / groups_in (EXEC-SCREENER-STOCK-LISTS, user 2026-11-09 option 2): keep a row that is a current member
     of at least one chosen list of that kind (row.indices, row.groups: list codes; a row without them is in no list);
     indices_out / groups_out: drop a row that is a member of any chosen list. Index, Group, sector and industry
     combine with AND. A stock in no list is not unclassified: include_unclassified never keeps it in;
   - tickers: keep only the listed tickers (validate.ts has refused unknown ones by name);
   - metric_filters on a universe attribute ({kind: 'universe', attr} naming a numeric field of the row: last,
     chg_1d_pct, adv20_idr, bars) are applied here with the VALUE rule (gt, lt strict; between inclusive; a null value
     fails); every other metric filter needs a formula, so it is left in `pending` (its index): the worker evaluates
     those on `eligible` right after this, through evaluate.ts, and adds the refused rows to filtered_out, while the page
     marks its own count as not exact.
   Counts (contract.ts UniverseCounts): listed = rows.length; eligible = rows kept; stale_hidden and
   price_break_hidden as above (0 when the chip is off); filtered_out = listed - eligible - stale_hidden -
   price_break_hidden.
   Pure module (no DOM, no Node API). distortionRemarks runs worker-side, at snapshot build. */
import type { PriceBreakRemark, UniverseCounts, UniverseDef, UniverseRow, ValueTest } from './contract.ts';
import { capAnomalies, checkActions, PRICE_ACTIONS } from './pricecheck.ts';

/** eligible: the rows kept, in row order; pending: indexes into def.metric_filters that need the worker (above). */
export interface UniverseResult { eligible: UniverseRow[]; counts: UniverseCounts; pending: number[] }

const inList = (v: string | null, list: readonly string[] | undefined): boolean => v !== null && !!list && list.includes(v);
/** A classification include filter: a value in the list, or no classification with include_unclassified (P15). */
const included = (v: string | null, list: readonly string[] | undefined, unclassified: boolean): boolean =>
  !list || !list.length || inList(v, list) || (v === null && unclassified);
/** A list filter (EXEC-SCREENER-STOCK-LISTS): the row's memberships of one kind against the chosen codes. */
const anyOf = (codes: readonly string[] | undefined, list: readonly string[] | undefined): boolean => !!codes && !!list && codes.some(c => list.includes(c));
const listsPass = (codes: readonly string[] | undefined, inc: readonly string[] | undefined, exc: readonly string[] | undefined): boolean =>
  (!inc || !inc.length || anyOf(codes, inc)) && !anyOf(codes, exc);
const atLeast = (v: number | null, bound: number | null | undefined): boolean => bound === null || bound === undefined || (v !== null && Number.isFinite(v) && v >= bound);

/** THE VALUE rule on one number (OPERATORS.md operators 1 and 15), the one copy every reader uses: evaluate.ts
    (conditions, metric filters through the core) re-exports it, and the attribute filters below (S0, the page's local
    counts) call it. gt, lt strict; ge, le inclusive; eq, ne exact (validate.ts offers them only on whole-number series,
    K7); between inclusive of both bounds; outside below value or above value2. QA3 2026-11-07 D1: a second copy here
    kept only gt / lt / between, so a filter with ge, le, eq, ne or outside silently dropped every stock. */
export function valuePasses(x: number, test: Pick<ValueTest, 'op' | 'value' | 'value2'>): boolean {
  switch (test.op) {
    case 'gt': return x > test.value;
    case 'lt': return x < test.value;
    case 'ge': return x >= test.value;
    case 'le': return x <= test.value;
    case 'eq': return x === test.value;
    case 'ne': return x !== test.value;
    case 'between': return x >= test.value && x <= (test.value2 as number);
    case 'outside': return x < test.value || x > (test.value2 as number);
  }
  throw new RangeError(`valuePasses: op ${JSON.stringify(test.op)} is not one of gt, lt, ge, le, eq, ne, between, outside`);
}
/** The VALUE rule on a row attribute: a null or missing value fails a filter. */
const attrPasses = (v: unknown, t: ValueTest): boolean => typeof v === 'number' && Number.isFinite(v) && valuePasses(v, t);
/** The row field a universe-attribute filter reads, or null when the filter needs the worker. */
function rowAttr(t: ValueTest, sample: UniverseRow | undefined): string | null {
  const m = t.metric;
  if (!m || m.kind !== 'universe' || typeof m.attr !== 'string') return null;
  if (sample && !(m.attr in sample)) return null;
  return ['ticker', 'name', 'sector', 'industry', 'first_bar', 'last_bar', 'stale', 'remarks', 'indices', 'groups'].includes(m.attr) ? null : m.attr;
}

/** S0 (rules above), in row order. */
export function applyUniverse(rows: readonly UniverseRow[], def: UniverseDef): UniverseResult {
  const filters = (def.metric_filters || []).map(t => ({ t, attr: rowAttr(t, rows[0]) }));
  const pending = filters.flatMap((f, i) => f.attr === null ? [i] : []);
  const tickers = def.tickers ? new Set(def.tickers) : null, unclassified = def.include_unclassified === true;
  const hideStale = def.traded_on_eval_date === true, hideBroken = def.exclude_price_breaks === true;   // off unless switched on (EXEC-PRICE-DISTORTION)
  let stale = 0, broken = 0;
  const eligible: UniverseRow[] = [];
  for (const r of rows) {
    if (hideStale && r.stale) { stale++; continue }
    if (hideBroken && hasPriceBreak(r)) { broken++; continue }
    if (tickers && !tickers.has(r.ticker)) continue;
    if (!included(r.sector, def.sectors_in, unclassified) || inList(r.sector, def.sectors_out)) continue;
    if (!included(r.industry, def.industries_in, unclassified) || inList(r.industry, def.industries_out)) continue;
    if (!listsPass(r.indices, def.indices_in, def.indices_out) || !listsPass(r.groups, def.groups_in, def.groups_out)) continue;
    if (!atLeast(r.last, def.price_min) || !atLeast(r.adv20_idr, def.adv20_min_idr) || !atLeast(r.bars, def.min_history_bars)) continue;
    if (filters.some(f => f.attr !== null && !attrPasses((r as unknown as Record<string, unknown>)[f.attr], f.t))) continue;
    eligible.push(r);
  }
  return {
    eligible, pending,
    counts: { listed: rows.length, eligible: eligible.length, stale_hidden: stale, price_break_hidden: broken, filtered_out: rows.length - eligible.length - stale - broken },
  };
}

/** STALE (report 6.5): the row's last bar is before E. */
export const isStale = (row: Pick<UniverseRow, 'last_bar'>, evaluationDate: string): boolean => row.last_bar < evaluationDate;
/** The row carries a PRICE_BREAK remark (derived at snapshot build, distortionRemarks). */
export const hasPriceBreak = (row: Pick<UniverseRow, 'remarks'>): boolean => row.remarks.some(r => r.code === 'PRICE_BREAK');

/** One corporate action of the `actions` xsection file for one ticker (report 6.5 Phase 1 files; the caller passes the
    rows of that ticker). The file holds every action since the first price year and cash dividends too; the boundary
    and type rules below pick the price breaks. */
export interface ActionRow {
  ticker: string; type: string; ex_date: string; ratio_old: number | null; ratio_new: number | null; amount_per_share?: number | null;
  /** EXEC-PRICE-DISTORTION D-5 (R1): the broker lot basis of a price action inside the Screener's broker window, as the
      publisher measured it (the actions file's additive column `basis`: terms, same, pending, unresolved; null for every
      other row); absent when the file has no such column (an older file, R2) */
  basis?: string | null;
}
/** EXEC-PRICE-DISTORTION D-5 (the agent's detail D-5, EXEC.md: "bila jendelanya melewati aksi yang lot-nya belum satu
    basis (status `terms`, `pending`, `unresolved`)"): the ex dates of a ticker's price-affecting actions inside the
    loaded broker window (first < ex <= last: an action on the window's first date or before it leaves every lot of the
    window on one side) whose broker lots before them are not on one basis with the lots after them: every status but
    `same`, no status included (null, or a file without the column, R2: an action the publisher did not measure is
    marked rather than passed over). Ascending, each once; none without a window. condition.ts marks a flow cell whose
    output reads the lots and whose sessions cross one (FLOW_BASIS_IN_LOOKBACK). */
export function flowBasisDates(actions: readonly ActionRow[], first: string | null, last: string | null): string[] {
  if (!first || !last) return [];
  const out = new Set<string>();
  for (const a of actions) if ((PRICE_ACTIONS as readonly string[]).includes(a.type) && a.ex_date > first && a.ex_date <= last && a.basis !== 'same') out.add(a.ex_date);
  return [...out].sort();
}
/** EXEC-PRICE-DISTORTION (user 2026-11-24, ERRORS M559-M562): the PRICE_BREAK remarks of one ticker from the one rule
    (pricecheck.ts; it replaces priceBreakRemarks' date rule, which flagged every action from the boundary on, the six
    stocks pulled again on 2026-10-31 included): an action whose ex-date jump is its own (raw) on any date; one from
    `boundary` on that cannot be measured (small, or no close or term: UD43); a session beyond the 35 % cap with no
    recorded action (UD44). An action before the boundary that cannot be measured reads as adjusted, as the bulk load
    left it. Up to the ticker's last bar; ordered by date, then action. */
export function distortionRemarks(actions: readonly ActionRow[], dates: readonly string[], closes: ArrayLike<number | null | undefined>, opts: { boundary: string }): PriceBreakRemark[] {
  if (!dates.length) return [];
  const last = dates[dates.length - 1], seen = new Set<string>(), out: PriceBreakRemark[] = [];
  // the break's first session on or after its date is the last bar: the 1-day change reads across it
  const before = dates.length > 1 ? dates[dates.length - 2] : '';
  const onLast = (d: string): { last_session?: true } => d > before && d <= last ? { last_session: true } : {};
  const ok = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
  const num = (v: unknown): number | null => ok(v) ? v : null;
  const priced = actions.filter(a => (PRICE_ACTIONS as readonly string[]).includes(a.type) && a.ex_date <= last);
  const checks = checkActions(dates, closes, priced.map(a => ({ ex:a.ex_date, type:a.type, ratio_old:a.ratio_old, ratio_new:a.ratio_new, exercise:a.amount_per_share ?? null })));
  checks.forEach((c, k) => {
    const a = priced[k], kind = c.verdict === 'raw' ? 'unadjusted' : c.verdict === 'adjusted' || a.ex_date < opts.boundary ? null : 'uncertain';
    const id = `${a.type}|${a.ex_date}|${a.ratio_old}|${a.ratio_new}`;
    if (!kind || seen.has(id)) return;                              // the same action listed twice is one remark
    seen.add(id);
    out.push({ code: 'PRICE_BREAK', kind, action: a.type, ex_date: a.ex_date, ratio_old: num(a.ratio_old), ratio_new: num(a.ratio_new),
      close_ratio: c.jump === null ? null : 1 / c.jump, effect: c.factor === null ? null : c.factor - 1, ...onLast(a.ex_date) });
  });
  for (const x of capAnomalies(dates, closes, priced.map(a => a.ex_date)))
    out.push({ code: 'PRICE_BREAK', kind: 'anomaly', action: 'PRICE_ANOMALY', ex_date: x.date, ratio_old: null, ratio_new: null, close_ratio: x.close / x.prev, effect: null, ...onLast(x.date) });
  return out.sort((x, y) => x.ex_date < y.ex_date ? -1 : x.ex_date > y.ex_date ? 1 : x.action < y.action ? -1 : x.action > y.action ? 1 : 0);
}
/** The ex-dates of a row's PRICE_BREAK remarks (the cell remark rule reads them, evaluate.ts priceBreakRemark). */
export const priceBreakDates = (row: Pick<UniverseRow, 'remarks'>): string[] => row.remarks.flatMap(r => r.code === 'PRICE_BREAK' ? [r.ex_date] : []);
