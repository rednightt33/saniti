/* The portfolio's picked stocks (user N 2026-10-27, CONTRACT.md PF1-PF7): a portfolio is an explicit list of 1 to
   catalog.limits.max_portfolio_tickers published stocks, found by searching or by the catalog's groupings (sector,
   industry: the columns of terminal-api's ticker reference file). The rules of the picker; picker.ts draws them.
   Pure: no DOM, no page state. */
import type { BacktestResultCore, Catalog } from './core/contract.ts';

export type Stock = Catalog['tickers'][number];
/** the chosen value of each grouping, by key: absent = any value, null = unclassified, a string = that value */
export type Filters = Record<string, string | null>;

/** the published stocks of the catalog (an index is not tradable), in catalog order */
export const stocksOf = (cat: Catalog): Stock[] => cat.tickers.filter(t => t.type === 'stock');

/** a grouping key as its label: the reference file's column name with a capital first letter ('sector' -> 'Sector') */
export const groupLabel = (key: string) => key.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase());

/** The search: every stock whose ticker starts with the query, then every other stock whose name contains it, each
    in catalog order, case-insensitive; the first `limit` of them and how many match in all. A blank query matches
    nothing. */
export function searchMatches(stocks: readonly Stock[], query: string, limit: number): { shown: Stock[]; total: number } {
  const q = query.trim().toLowerCase();
  if (!q) return { shown:[], total:0 };
  const byTicker = stocks.filter(s => s.ticker.toLowerCase().startsWith(q));
  const first = new Set(byTicker);
  const all = [...byTicker, ...stocks.filter(s => !first.has(s) && (s.name || '').toLowerCase().includes(q))];
  return { shown:all.slice(0, Math.max(0, limit)), total:all.length };
}

/** whether any grouping has a chosen value */
export const filtering = (f: Filters) => Object.keys(f).length > 0;

/** The stocks of the chosen groups: a stock is listed when it has the chosen value of every grouping that has one
    (several groupings combine with AND); null chooses the unclassified stocks (the catalog's groups are null there).
    Catalog order; nothing while no grouping has a chosen value. */
export function groupStocks(stocks: readonly Stock[], f: Filters): Stock[] {
  const keys = Object.keys(f);
  if (!keys.length) return [];
  return stocks.filter(s => keys.every(k => (s.groups?.[k] ?? null) === f[k]));
}

/** `picked` with the tickers of `add` that are not picked yet, in their order, while fewer than `max` are picked;
    refused: how many of them did not fit (the page's limit toast). Never more than `max`. */
export function addTickers(picked: readonly string[], add: readonly string[], max: number): { picked: string[]; refused: number } {
  const out = [...picked];
  let refused = 0;
  for (const t of add) {
    if (out.includes(t)) continue;
    if (out.length >= max) { refused++; continue }
    out.push(t);
  }
  return { picked:out, refused };
}

/** The ticker the signal chart shows, always one of the picked stocks: the current one while it is picked; else the
    first picked stock among `ran` (the tickers of the run the chart shows), else the first picked stock; '' when
    none is picked. */
export function chartTicker(current: string, picked: readonly string[], ran: readonly string[] = []): string {
  if (picked.includes(current)) return current;
  return picked.find(t => ran.includes(t)) ?? picked[0] ?? '';
}

/** The tickers of a run: the ones it ran on (meta.tickers) and every one its entry tracks name, which are the tickers
    edge-bff keeps the events of (/events?ticker=; any other is 404 EVENTS_NOT_FOUND, backtest.py split_result). */
export const runTickers = (r: BacktestResultCore): string[] => [...new Set([...r.meta.tickers, ...Object.keys(r.events.entries || {})])];

/** The picked stocks where the reference names its universe (the step summary, the view bar's title): up to three
    tickers, as the reference's own universe label "Banks (BBCA, BBRI, BMRI)" lists three, then "+n" for the others;
    `shown` names fewer. */
export function tickersLabel(list: readonly string[], shown = 3): string {
  return list.slice(0, shown).join(', ') + (list.length > shown ? ` +${list.length - shown}` : '');
}

/** The names the view bar's title may give the picked stocks, longest first, each once: three, two, then one ticker
    with "+n" (builder.ts keeps the first whose title takes no more lines than the reference's; none: the count alone,
    review PG-3). */
export const titleNames = (list: readonly string[]): string[] => [...new Set([3, 2, 1].map(k => tickersLabel(list, k)))];

/** "1 stock", "n stocks" (the core's wording of a count of stocks, core/signals.ts leftOut) */
export const stocksText = (n: number) => n === 1 ? '1 stock' : `${n} stocks`;

/** the toast of a stock refused past the limit, the condition limit's wording ("Limit reached: at most 12 stocks per
    portfolio."; a limit of 1, which BACKTEST_MAX_PORTFOLIO_TICKERS allows, is "1 stock": review PG-5) */
export const limitText = (max: number) => `Limit reached: at most ${stocksText(max)} per portfolio.`;
