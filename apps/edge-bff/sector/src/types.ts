/* EXEC-SECTOR-ANALYSIS S4: the sector files as the publisher writes them (verification/sector_analysis/CONTRACT.md section 3,
   apps/terminal-publisher/sector.py). Every list is ordered by the publisher; rows of a day file are aligned by `i`, the
   position in meta.stocks. */
export type N = number | null;
export interface FileEntry { sha256: string; bytes: number; rows: number; as_of: string | null }
export interface SectorIndex { finished_at: string | null; files: Record<string, FileEntry> }
export interface SectorInfo { name: string; short: string; index: string }
/** 3.1 sector-meta */
export interface Meta {
  schema: number; market: string; benchmarks: string[];
  weight_basis: string | null; weight_label: string | null;
  periods: Record<string, number>;
  sectors: SectorInfo[];
  industries: { name: string; sector: string }[];
  stocks: { ticker: string[]; name: string[]; sector: string[]; industry: (string | null)[] };
  dates: string[]; prices_through: string; breadth_through: string | null;
}
/** a group's daily breadth counts (Feature_08_Group_Daily): members, of them with an EMA and above it, and the 1D moves */
export interface Breadth { members: N[]; n50: N[]; a50: N[]; n200: N[]; a200: N[]; adv: N[]; unch: N[]; dec: N[] }
/** 3.2 sector-series: the 300 newest market dates, oldest first */
export interface Series {
  schema: number; dates: string[];
  index: Record<string, N[]>;
  sector: Record<string, N[]>;
  breadth: Record<string, Breadth>;
  industry: Record<string, { level: N[]; members: N[] }>;
}
/** 3.3 sector-day-YYYY-MM-DD */
export interface DayStocks {
  i: number[]; close: N[]; volume: N[]; r1d: N[]; r5d: N[]; r1m: N[]; r3m: N[]; weight: N[];
  above_ema50: (0 | 1 | null)[]; above_ema200: (0 | 1 | null)[];
  d_ema50: N[]; d_ema200: N[]; days50: N[]; days200: N[]; since50: (string | null)[]; since200: (string | null)[];
}
export interface Day { schema: number; date: string; prior_date: string | null; stocks: DayStocks }
/** 3.4 sector-stocks-<index lowercased>: one sector's daily closes on the series dates */
export interface StocksFile { schema: number; sector: string; dates: string[]; ticker: string[]; close: N[][] }
export interface SectorApi {
  index(): Promise<SectorIndex>;
  file<T>(name: string, sha: string): Promise<T>;
}
