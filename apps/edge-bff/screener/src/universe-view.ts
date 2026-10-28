/* The universe the page shows before any run (report 6c.4 S5: an empty screen's rows are the universe rows after the
   universe filter; 9.2 "In universe X of N" computed in the page on every edit).
   TEMPORARY (integrator): report 9.1 has the page import the core's universe.ts, the same function the worker runs in
   stage S0. That module was not in the branch while the page was built (screener-page.md, open issue 1), so this file
   holds the S0 rules of report 8.5 for the page's count only, in one place, to be replaced by a call of the core
   function. A run's own `universe` counts (the worker's) always win over these: the page shows them once a run
   answers. Pure: no DOM. */
import type { UniverseCounts, UniverseDef, UniverseRow, ValueTest } from './core/contract.ts';

export interface UniverseView { rows: UniverseRow[]; counts: UniverseCounts; exact: boolean }

const hasBreak = (r: UniverseRow) => r.remarks.some(x => x.code === 'PRICE_BREAK');
const inList = (v: string | null, list?: string[]) => !!list?.length && v != null && list.includes(v);

/** a universe metric filter the page can evaluate on a universe row (kind 'universe' on one of its attributes) */
function localFilter(t: ValueTest): ((r: UniverseRow) => boolean) | null {
  const m = t.metric as any;
  if (m?.kind !== 'universe' || !['last', 'chg_1d_pct', 'adv20_idr', 'bars'].includes(m.attr)) return null;
  return r => {
    const v = (r as any)[m.attr] as number | null;
    if (v == null || !Number.isFinite(v)) return false;
    return t.op === 'gt' ? v > t.value : t.op === 'lt' ? v < t.value : v >= t.value && v <= (t.value2 ?? t.value);
  };
}

/** The S0 filter of report 8.5 on the universe rows (P4: stale and price-break tickers hidden by their chips first;
    P15: an include filter keeps an unclassified stock only with include_unclassified, an exclude filter never drops it). */
export function universeView(all: UniverseRow[], u: UniverseDef): UniverseView {
  let stale = 0, brk = 0, exact = true;
  const filters = (u.metric_filters || []).map(t => { const f = localFilter(t); if (!f) exact = false; return f });
  const rows: UniverseRow[] = [];
  for (const r of all) {
    if (u.traded_on_eval_date && r.stale) { stale++; continue }
    if (u.exclude_price_breaks && hasBreak(r)) { brk++; continue }
    if (u.tickers && !u.tickers.includes(r.ticker)) continue;
    if (u.sectors_in?.length && !(inList(r.sector, u.sectors_in) || (r.sector == null && u.include_unclassified))) continue;
    if (inList(r.sector, u.sectors_out)) continue;
    if (u.industries_in?.length && !(inList(r.industry, u.industries_in) || (r.industry == null && u.include_unclassified))) continue;
    if (inList(r.industry, u.industries_out)) continue;
    if (u.price_min != null && !(r.last != null && r.last >= u.price_min)) continue;
    if (u.adv20_min_idr != null && !(r.adv20_idr != null && r.adv20_idr >= u.adv20_min_idr)) continue;
    if (u.min_history_bars != null && r.bars < u.min_history_bars) continue;
    if (filters.some(f => f && !f(r))) continue;
    rows.push(r);
  }
  return { rows, exact, counts:{ listed:all.length, eligible:rows.length, stale_hidden:stale, price_break_hidden:brk, filtered_out:all.length - rows.length - stale - brk } };
}

/** how many tickers each P4 chip hides on the whole universe (the chip's count, report 9.2) */
export const hiddenCounts = (all: UniverseRow[]) => ({ stale:all.filter(r => r.stale).length, breaks:all.filter(r => !r.stale && hasBreak(r)).length });
