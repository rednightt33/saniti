/* EXEC-RADAR R7: from the Radar files to what the board and the detail show. Pure functions (tests/model.test.ts).
   The page decides nothing about a stock: hit, near, left, the met conditions, the run of days, the sort key and the
   outlier note are Feature 07's rows (radar-board-*); the page picks the rows of the chosen level and gate, narrows
   them to the chosen universe and search, and formats them. */
import type { Board, Days, FilterFile, FilterMeta, Gate, Level, Meta, Rule, Status } from './types.ts';

export const LEVELS: Level[] = ['loose', 'standard', 'strict'];
export const LEVEL_LABEL = ['Loose', 'Standard', 'Strict'];
export const COND_KEYS = 'ABCD';

export interface Row {
  filter: string; t: string; status: Status; met: number | null; cond_n: number; run: number | null; why: string | null;
  strong: boolean | null; sort: number | null; flag: string | null;
}

/** The board's columns, in order: one per column id; a column with variants (S6Δ) lists them, default first. */
export interface Column { id: string; label: string; variants: FilterMeta[] }
export function columns(meta: Meta): Column[] {
  const out: Column[] = [];
  for (const f of [...meta.filters].sort((a, b) => a.position - b.position)) {
    let c = out.find(x => x.id === f.column);
    if (!c) out.push(c = { id: f.column, label: f.column_label, variants: [] });
    c.variants.push(f);
  }
  for (const c of out) c.variants.sort((a, b) => Number(b.default_variant) - Number(a.default_variant) || a.position - b.position);
  return out;
}

/** The level a filter is read at: its own levels (S8) are stored once, as standard. */
export const levelOf = (f: FilterMeta, lv: number): Level => (f.own_levels ? 'standard' : LEVELS[lv]);

/** The conditions of a filter at a level, A first, with their labels as the rules table holds them. */
export function conditions(meta: Meta, f: FilterMeta, lv: number): Rule[] {
  const level = levelOf(f, lv);
  return meta.rules.filter(r => r.filter === f.id && r.level === level).sort((a, b) => a.cond.localeCompare(b.cond));
}

export const metBits = (met: number | null, n: number): boolean[] => Array.from({ length: n }, (_, k) => !!((met || 0) & (1 << k)));

/** The rows of one filter at one level and gate, by status. */
export function rowsOf(board: Board, filter: string, level: Level, gate: Gate): Row[] {
  const r = board.rows, out: Row[] = [];
  for (let i = 0; i < r.filter.length; i++) {
    if (r.filter[i] !== filter || r.level[i] !== level || r.gate[i] !== gate) continue;
    out.push({ filter, t: board.stocks.ticker[r.stock[i]], status: r.status[i], met: r.met[i], cond_n: r.cond_n[i],
               run: r.run_day[i], why: r.left_reason[i], strong: r.strong[i], sort: r.sort_value[i], flag: r.flag[i] });
  }
  return out;
}

const bySort = (a: Row, b: Row) => (b.sort ?? -Infinity) - (a.sort ?? -Infinity) || (a.t < b.t ? -1 : 1);

export interface Lists { hits: Row[]; near: Row[]; left: Row[] }
export function lists(board: Board, f: FilterMeta, lv: number, gate: Gate, keep: (t: string) => boolean = () => true): Lists {
  const all = rowsOf(board, f.id, levelOf(f, lv), gate).filter(r => keep(r.t));
  return { hits: all.filter(r => r.status === 'hit').sort(bySort), near: all.filter(r => r.status === 'near').sort(bySort),
           left: all.filter(r => r.status === 'left').sort((a, b) => (a.t < b.t ? -1 : 1)) };
}

/** Universe: every stock, or the current members of one stock list (index or group). */
export function inUniverse(meta: Meta, uni: string): (t: string) => boolean {
  if (uni === 'all') return () => true;
  const members = new Set(meta.lists.find(l => l.key === uni)?.members || []);
  return t => members.has(t);
}

/** Stock facts on the board date: name, close, 1D change, the 20-session price line, a measure. */
export function stockFacts(meta: Meta, board: Board) {
  const at = new Map(board.stocks.ticker.map((t, i) => [t, i] as [string, number]));
  const col = new Map(board.measures.columns.map((c, i) => [c, i] as [string, number]));
  return {
    has: (t: string) => at.has(t),
    name: (t: string) => meta.names[t] || t,
    close: (t: string) => (at.has(t) ? board.stocks.close[at.get(t)] : null),
    chg: (t: string) => (at.has(t) ? board.stocks.chg_1d[at.get(t)] : null),
    spark: (t: string) => (at.has(t) ? board.stocks.spark[at.get(t)] : []),
    measure: (t: string, name: string): number | null => {
      const v = at.has(t) ? board.measures.values[at.get(t)] : null;
      return v && col.has(name) ? v[col.get(name)] : null;
    },
  };
}

/** Daily hit counts of a filter at a setting, up to and including the date index `upto`. */
export function counts(days: Days, f: FilterMeta, lv: number, gate: Gate, upto: number, len: number): number[] {
  const a = days.counts[f.id]?.[`${levelOf(f, lv)}/${gate}`] || [];
  return a.slice(Math.max(0, upto - len + 1), upto + 1);
}

/** The members of a filter on one date of its file, at a setting: {ticker: run_day}. */
export function membersOn(file: FilterFile, f: FilterMeta, lv: number, gate: Gate, dateIndex: number): Map<string, number> {
  const out = new Map<string, number>(), level = levelOf(f, lv), h = file.hits;
  for (let i = 0; i < h.date.length; i++)
    if (h.date[i] === dateIndex && h.level[i] === level && h.gate[i] === gate) out.set(file.stocks.ticker[h.stock[i]], h.run_day[i]);
  return out;
}

/** A stock's runs in a filter at a setting, as [first, last] date indexes of consecutive hit dates. */
export function runs(file: FilterFile, f: FilterMeta, lv: number, gate: Gate, t: string): [number, number][] {
  const s = file.stocks.ticker.indexOf(t);
  if (s < 0) return [];
  const level = levelOf(f, lv), h = file.hits, ds: number[] = [];
  for (let i = 0; i < h.date.length; i++) if (h.stock[i] === s && h.level[i] === level && h.gate[i] === gate) ds.push(h.date[i]);
  ds.sort((a, b) => a - b);
  const out: [number, number][] = [];
  for (const d of ds) {
    const last = out[out.length - 1];
    if (last && d === last[1] + 1) last[1] = d; else out.push([d, d]);
  }
  return out;
}

/** A stock's close on every date of a filter file (null where it has no final price). */
export function closesOf(file: FilterFile, t: string): (number | null)[] {
  const s = file.stocks.ticker.indexOf(t);
  return s < 0 ? [] : file.stocks.close[s];
}

const MONS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DOWS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
export const dayLabel = (iso: string | null, withDow = true) => {
  if (!iso) return '—';
  const d = new Date(iso + 'T00:00:00Z');
  return `${withDow ? DOWS[d.getUTCDay()] + ' ' : ''}${d.getUTCDate()} ${MONS[d.getUTCMonth()]}`;
};
export const monthOf = (iso: string) => MONS[new Date(iso + 'T00:00:00Z').getUTCMonth()];
