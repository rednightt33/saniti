/* What the page runs against: the injected BacktestApi, the catalog it answered, and the bars loaded so far. The
   reference has these as constants (TICKERS, BROKERS, DATA, DAYS); here they come from the API at boot. */
import type { Catalog } from './core/contract.ts';
import type { BacktestApi, TickerBars } from './api/types.ts';
import { MAX_PORTFOLIO_TICKERS, MAX_POSITIONS } from './core/engine.ts';

export let API: BacktestApi;
export let CAT: Catalog;
export const setEnv = (api: BacktestApi, catalog: Catalog) => { API = api; CAT = catalog; READY = catalog !== PROVISIONAL };

/* EXEC-BACKTEST-LOAD (user 2026-10-27: "menu-menu itu yang di sebelah kiri dan di tengah tidak perlu clickable dan bisa
   ready langsung ketika user buka ... Tidak perlu semuanya di loading all at once"): until the catalog answers, the page
   runs on this one. It names no stock, broker or grouping (the parts that list them say they are loading), no date
   (the period keeps the page's defaults) and the core's ceilings as limits (the worker checks the real ones on Run); flow
   is taken as available, so a flow card's broker data starts loading at once (a catalog that turns flow off later
   only leaves those files unused). */
export const PROVISIONAL: Catalog = {
  schema_version: 1, engine_version: '', registry_version: '', data_through: '', first_date: '',
  tickers: [], groupings: [], flow: { available: true, reason: null, brokers: [], data_through: null },
  limits: { max_positions: MAX_POSITIONS, window_bars: { min: 1, max: 20 }, monte_carlo_runs: 1000, max_portfolio_tickers: MAX_PORTFOLIO_TICKERS,
            max_download_bytes: Infinity, max_broker_rows: Infinity, timeout_seconds: Infinity, queued_per_owner: Infinity, max_conditions: Infinity },
};
let READY = false;
/** whether the catalog has answered (else the page runs on PROVISIONAL) */
export const catalogReady = () => READY;
let waiting: Promise<Catalog> | null = null;
/** the catalog once it has answered (Run waits for it: the request needs its limits and dates) */
export const whenCatalog = (): Promise<Catalog> => READY ? Promise.resolve(CAT) : waiting ?? Promise.reject(new Error('The catalog was not asked for.'));
export const setWaiting = (p: Promise<Catalog>) => { waiting = p };

/** bars of every ticker loaded so far, and whether its broker data came with it */
export const DATA: Record<string, TickerBars> = {};
const FLOW = new Set<string>();
const PENDING = new Map<string, Promise<void>>();

/** stock tickers of the catalog (the reference's TICKERS) */
export const STOCKS = (): string[] => CAT.tickers.filter(t => t.type === 'stock').map(t => t.ticker);
/** brokers of the published broker files (the reference's BROKERS) */
export const BROKER_CODES = (): string[] => CAT.flow.brokers;

export const loaded = (tk: string, flow = false) => !!DATA[tk] && (!flow || FLOW.has(tk));

/** load a ticker's bars (and its broker data when a flow card needs it); one request at a time per ticker */
export function load(tk: string, flow = false, soon = false): Promise<void> {   // soon: the broker data follows (one /bundle)
  if (loaded(tk, flow)) return Promise.resolve();
  const key = tk + (flow ? '|flow' : '');
  let p = PENDING.get(key);
  if (!p) {
    p = API.bars(tk, { flow, soon }).then(b => { DATA[tk] = b; if (flow) FLOW.add(tk) }).finally(() => PENDING.delete(key));
    PENDING.set(key, p);
  }
  return p;
}
