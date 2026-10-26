/* What the page runs against: the injected BacktestApi, the catalog it answered, and the bars loaded so far. The
   reference has these as constants (TICKERS, BROKERS, DATA, DAYS); here they come from the API at boot. */
import type { Catalog } from './core/contract.ts';
import type { BacktestApi, TickerBars } from './api/types.ts';

export let API: BacktestApi;
export let CAT: Catalog;
export const setEnv = (api: BacktestApi, catalog: Catalog) => { API = api; CAT = catalog };

/** bars of every ticker loaded so far, and whether its broker data came with it */
export const DATA: Record<string, TickerBars> = {};
const FLOW = new Set<string>();
const PENDING = new Map<string, Promise<void>>();

/** stock tickers of the catalog (the reference's TICKERS) */
export const STOCKS = (): string[] => CAT.tickers.filter(t => t.type === 'stock').map(t => t.ticker);
/** brokers of the published broker files (the reference's BROKERS) */
export const BROKER_CODES = (): string[] => CAT.flow.brokers;

/** the tickers of a catalog universe: 'all' = every stock, 'sector:<name>' = the stocks of that published sector */
export function members(id: string): string[] {
  const stocks = CAT.tickers.filter(t => t.type === 'stock');
  if (id === 'all') return stocks.map(t => t.ticker);
  if (id.startsWith('sector:')) { const s = id.slice(7); return stocks.filter(t => t.sector === s).map(t => t.ticker) }
  return [];
}
/** the short name of a universe (the reference writes "Demo 10" for "Demo 10 (LQ45 sample)"): its label without a
    trailing parenthesis */
export const universeName = (id: string) => { const u = CAT.universes.find(x => x.id === id); return u ? u.label.replace(/\s*\([^)]*\)$/, '') : id };

export const loaded = (tk: string, flow = false) => !!DATA[tk] && (!flow || FLOW.has(tk));

/** load a ticker's bars (and its broker data when a flow card needs it); one request at a time per ticker */
export function load(tk: string, flow = false): Promise<void> {
  if (loaded(tk, flow)) return Promise.resolve();
  const key = tk + (flow ? '|flow' : '');
  let p = PENDING.get(key);
  if (!p) {
    p = API.bars(tk, { flow }).then(b => { DATA[tk] = b; if (flow) FLOW.add(tk) }).finally(() => PENDING.delete(key));
    PENDING.set(key, p);
  }
  return p;
}
