/* EXEC-RADAR R7: the Radar files as the publisher writes them (apps/terminal-publisher/radar.py;
   verification/radar/FILES.md). Columnar: every array of one block has one entry per row. */

export type Level = 'loose' | 'standard' | 'strict';
export type Gate = 'broad' | 'liquid';
export type Status = 'hit' | 'near' | 'left';

export interface FilterMeta {
  id: string; position: number; column: string; column_label: string; variant: string | null; default_variant: boolean;
  name: string; question: string; warning: string; sort_label: string; own_levels: boolean;
}
export interface Rule { filter: string; cond: string; level: Level; label: string; threshold: number | null; threshold2: number | null; status: string }
export interface StockList { key: string; kind: string; code: string; name: string; members: string[] }
export interface Meta { schema: number; levels: Level[]; gates: Gate[]; filters: FilterMeta[]; rules: Rule[]; names: Record<string, string>; lists: StockList[] }

export interface Days {
  schema: number; dates: string[];
  gate: { universe_n: number[]; broad_cut: (number | null)[]; liquid_cut: (number | null)[]; broad_n: number[]; liquid_n: number[] };
  counts: Record<string, Record<string, number[]>>;       // filter -> "level/gate" -> hits per date
  ihsg: (number | null)[]; broker_through: string | null; prices_through: string | null; boards: string[];
}

export interface Board {
  schema: number; date: string;
  stocks: { ticker: string[]; close: (number | null)[]; chg_1d: (number | null)[]; spark: (number | null)[][] };
  rows: {
    filter: string[]; stock: number[]; level: Level[]; gate: Gate[]; status: Status[]; met: (number | null)[];
    cond_n: number[]; run_day: (number | null)[]; left_reason: (string | null)[]; strong: (boolean | null)[];
    sort_value: (number | null)[]; flag: (string | null)[];
  };
  measures: { columns: string[]; values: ((number | null)[] | null)[] };
}

export interface FilterFile {
  schema: number; filter: string; dates: string[];
  stocks: { ticker: string[]; close: (number | null)[][] };
  hits: { date: number[]; stock: number[]; level: Level[]; gate: Gate[]; run_day: number[] };
  left: { date: number[]; stock: number[]; level: Level[]; gate: Gate[]; left_reason: string[] };
}

export interface IndexEntry { sha256: string; bytes: number; rows: number; as_of: string | null }
export interface RadarIndex { finished_at: string | null; files: Record<string, IndexEntry> }

/** Where the page gets its files: edge-bff in production (api.ts), synthetic or saved documents in the fixture build. */
export interface RadarApi {
  index(): Promise<RadarIndex>;
  file<T>(name: string, sha: string): Promise<T>;
}
