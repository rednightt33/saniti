/* EXEC-OVERVIEW O5: the Overview files as the publisher writes them (apps/terminal-publisher/overview.py). */
export interface FileEntry { sha256: string; bytes: number; rows: number; as_of: string | null }
export interface OverviewIndex { finished_at: string | null; files: Record<string, FileEntry> }
export interface Meta {
  schema: number; market: string; benchmark: string;
  stocks: { ticker: string[]; name: string[]; sector: string[] };
  sectors: { name: string; index: string | null }[];
  lists: { key: string; kind: string; code: string; name: string; members: string[] }[];
  dates: string[]; size_basis: string | null; prices_through: string; broker_through: string | null;
  periods: { flow: string[] };
}
export interface Series {
  schema: number; dates: string[];
  index: Record<string, (number | null)[]>; sector: Record<string, (number | null)[]>;
  above_ema50: (number | null)[]; above_ema200: (number | null)[]; breadth_n: ([number, number] | null)[];
  flow: { dates: string[]; foreign_buy: (number | null)[]; foreign_sell: (number | null)[]; turnover: (number | null)[] };
}
export interface Ohlc { open?: number | null; high?: number | null; low?: number | null; close?: number | null; prior_close: number | null }
export interface FlowPeriod { buy: number; sell: number; net: number; from: string }
export interface Day {
  schema: number; date: string; prior_date: string | null; size_basis: string | null;
  index: Record<string, Ohlc>;
  volatility: { window: number; value: number | null; rank_1y: number | null };
  breadth: { advancers: number; decliners: number; unchanged: number };
  market: null | { date: string; turnover: number; turnover_avg20: number | null; turnover_ratio: number | null;
                   foreign_net_1d: number; foreign_net_10d: number | null; periods: Record<string, FlowPeriod | null> };
  stocks: { i: number[]; close: (number | null)[]; r1d: (number | null)[]; r5d: (number | null)[]; r1m: (number | null)[];
            size: (number | null)[]; above_ema50: (0 | 1 | null)[]; above_ema200: (0 | 1 | null)[];
            fnet_1d: (number | null)[]; fnet_5d: (number | null)[]; fnet_1m: (number | null)[]; fnet_3m: (number | null)[] };
  intraday: Record<string, { t: number[]; c: (number | null)[] }>;
}
export interface OverviewApi {
  index(): Promise<OverviewIndex>;
  file<T>(name: string, sha: string): Promise<T>;
}
/** F1 (user 2026-11-15 "1A ... 2 A"): overview-stocks, every stock's daily close (series dates) and Regular foreign net
    (broker dates), its own ticker list so the page aligns by ticker. */
export interface StocksFile {
  schema: number; ticker: string[]; dates: string[]; fnet_dates: string[];
  close: (number | null)[][]; fnet: (number | null)[][];
}

