/* EXEC-WATCHLIST L5: the shapes the page reads. The daily file is the publisher's (apps/terminal-publisher/watchlist.py
   build()); the lists are edge-bff's (apps/edge-bff/app/watchlist.py). */
export interface FileEntry { sha256: string; bytes: number; rows: number; as_of: string | null }
export interface WatchlistIndex { finished_at: string | null; files: Record<string, FileEntry> }

export type Unit = 'index' | 'price' | 'pct' | 'ratio' | 'rp' | 'rank';
export interface CatalogItem {
  key: string; name: string; short: string; note: string; family: string; unit: Unit | string;
  date: 'price' | 'broker'; signed: boolean;
}
/** one upcoming corporate action: [action type, date, date role] */
export type EventRow = [string, string, string];
export interface StocksFile {
  schema: number; prices_through: string; broker_through: string | null; radar_date: string | null;
  events_loaded: string | null; event_days: number; radar_board: { level: string; gate: string };
  dates: string[]; catalog: CatalogItem[]; default: string[]; radar_filters: { label: string; name: string }[];
  ticker: string[]; name: string[]; sector: string[];
  last: (number | null)[]; r1d: (number | null)[]; r1m: (number | null)[]; trend: (number | null)[][];
  values: Record<string, (number | null)[]>;
  events: Record<string, EventRow[]>; radar: Record<string, string[]>;
}

export interface ListTicker { ticker: string; position: number }
export interface WList {
  id: string; name: string; position: number; indicators: string[] | null; tickers: ListTicker[];
  created_at?: string; updated_at?: string;
}
export interface Limit { name: string; value: number; unit: string; rule: string; example_ok: string; example_refused: string }
export interface ListsAnswer { lists: WList[]; limits: Limit[] }
export interface CreateBody { name: string; tickers?: string[]; indicators?: string[] | null; position?: number }
export interface AddAnswer { added: string[]; already: string[]; list: WList }

/** Everything the page reads or writes. live (src/api.ts) is edge-bff; the fixture build has its own in-memory one. */
export interface WatchlistApi {
  index(): Promise<WatchlistIndex>;
  file<T>(name: string, sha: string): Promise<T>;
  lists(): Promise<ListsAnswer>;
  create(body: CreateBody): Promise<WList>;
  rename(id: string, name: string): Promise<WList>;
  setIndicators(id: string, indicators: string[] | null): Promise<WList>;
  setIndicatorsAll(indicators: string[] | null): Promise<WList[]>;
  remove(id: string): Promise<void>;
  addTickers(id: string, tickers: string[], position?: number): Promise<AddAnswer>;
  removeTicker(id: string, ticker: string): Promise<void>;
  /** ticker -> logo version (the first 12 hex of its sha256); {} when the logo list cannot be read */
  logos(): Promise<Record<string, string>>;
  logoSrc(ticker: string, version: string): string;
}
