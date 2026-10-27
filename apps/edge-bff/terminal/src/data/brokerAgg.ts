/* EXEC-TERMINAL-POPOUT W1 + I2 (user 2026-10-27: "Yes, diperbesar dan ditambahkan fungsi-fungsi lain yang lebih
   detail"; "tanpa frekuensi dulu."): the sums behind the panel windows, from the published broker summary rows
   [broker, investor, board, buyValue, sellValue, buyLots, sellLots] of each session. One lot is 100 shares, so an
   average price is value / (lots × 100). */
import type { BrokerRow } from './types';

export type RowsOf = (d: number) => BrokerRow[];
/** one broker's sums over a period: buy and sell value (Rp), buy and sell lots */
export interface Agg { b: string; bv: number; sv: number; bl: number; sl: number }

const pass = (r: BrokerRow, inv: string, board: string) => (inv === 'All' || r[1] === inv) && (board === 'All' || r[2] === board);

/** sessions f..t (inclusive) summed per broker, for one investor type and board ('All' = every one) */
export function aggregate(rowsOf: RowsOf, f: number, t: number, inv = 'All', board = 'All'): Agg[] {
  const m = new Map<string, Agg>();
  for (let d = f; d <= t; d++) for (const r of rowsOf(d)) {
    if (!pass(r, inv, board)) continue;
    const o = m.get(r[0]) || { b:r[0], bv:0, sv:0, bl:0, sl:0 };
    o.bv += r[3]; o.sv += r[4]; o.bl += r[5]; o.sl += r[6]; m.set(r[0], o);
  }
  return [...m.values()];
}

/** the average price of a value over lots; null when no lot was traded */
export const avgPrice = (value: number, lots: number): number | null => lots ? value / (lots * 100) : null;

/** the broker sessions inside a date span: the first on or after `from`, the last on or before `to`; null when none */
export function sessionSpan(dates: string[], from: string, to: string): [number, number] | null {
  let f = -1, t = -1;
  for (let i = 0; i < dates.length; i++) { if (f < 0 && dates[i] >= from) f = i; if (dates[i] <= to) t = i }
  return f < 0 || t < 0 || f > t ? null : [f, t];
}

/* ---- Broker summary table ---- */
export type SumKey = 'b' | 'bl' | 'bv' | 'ba' | 'sl' | 'sv' | 'sa' | 'nv' | 'nl' | 'share';
export interface SumRow extends Agg { ba: number | null; sa: number | null; nv: number; nl: number; share: number }
export interface SumTable { rows: SumRow[]; split: number; total: SumRow; count: number }

const value = (r: SumRow, k: SumKey): number | string => k === 'b' ? r.b : (r[k] ?? -Infinity);

/** the rows of the Broker summary window. `share` is the broker's buy plus sell value over the period's buy plus sell
    value (the column sums to 100%). Sorted by `sort`; with a `limit` on a net column, the first `limit` rows (net
    buyers) and the last `limit` rows (net sellers) are kept and `split` is where the sellers start (-1: one list). */
export function summaryTable(list: Agg[], o: { sort: SumKey; desc: boolean; limit: number | null; search?: string }): SumTable {
  const gross = list.reduce((s, x) => s + x.bv + x.sv, 0);
  const all: SumRow[] = list.map(x => ({ ...x, ba:avgPrice(x.bv, x.bl), sa:avgPrice(x.sv, x.sl), nv:x.bv - x.sv, nl:x.bl - x.sl,
    share:gross ? (x.bv + x.sv) / gross * 100 : 0 }));
  const sum = (k: 'bv' | 'sv' | 'bl' | 'sl') => all.reduce((s, x) => s + x[k], 0);
  const T = { b:'Total', bv:sum('bv'), sv:sum('sv'), bl:sum('bl'), sl:sum('sl') };
  const total: SumRow = { ...T, ba:avgPrice(T.bv, T.bl), sa:avgPrice(T.sv, T.sl), nv:T.bv - T.sv, nl:T.bl - T.sl, share:gross ? 100 : 0 };
  const q = (o.search || '').trim().toUpperCase();
  const rows = (q ? all.filter(x => x.b.includes(q)) : all).sort((a, b) => {
    const va = value(a, o.sort), vb = value(b, o.sort);
    const c = typeof va === 'string' ? va.localeCompare(vb as string) : (va as number) - (vb as number);
    return (o.desc ? -c : c) || a.b.localeCompare(b.b);
  });
  const count = rows.length;
  if (o.limit == null || rows.length <= o.limit) return { rows, split:-1, total, count };
  if ((o.sort === 'nv' || o.sort === 'nl') && !q) {
    const sign = (r: SumRow) => Math.sign(r[o.sort as 'nv' | 'nl']) * (o.desc ? 1 : -1);
    const head = rows.filter(r => sign(r) > 0).slice(0, o.limit), tail = rows.filter(r => sign(r) < 0).slice(-o.limit);
    return { rows:[...head, ...tail], split:tail.length ? head.length : -1, total, count };
  }
  return { rows:rows.slice(0, o.limit), split:-1, total, count };
}

/* ---- Broker inventory ---- */
export interface InvSeries { b: string; daily: number[]; cum: number[]; agg: Agg }
export interface InvStats { end: number; hi: number; lo: number }

/** each broker's net per session f..t (lots or value) and its running sum from 0, with its period sums */
export function inventory(rowsOf: RowsOf, f: number, t: number, brokers: string[], inv = 'All', board = 'All', unit: 'lot' | 'value' = 'lot'): InvSeries[] {
  const out = brokers.map(b => ({ b, daily:[] as number[], cum:[] as number[], agg:{ b, bv:0, sv:0, bl:0, sl:0 } }));
  const at = new Map(out.map((s, k) => [s.b, k]));
  for (let d = f; d <= t; d++) {
    const day = out.map(() => 0);
    for (const r of rowsOf(d)) {
      const k = at.get(r[0]);
      if (k === undefined || !pass(r, inv, board)) continue;
      const a = out[k].agg; a.bv += r[3]; a.sv += r[4]; a.bl += r[5]; a.sl += r[6];
      day[k] += unit === 'lot' ? r[5] - r[6] : r[3] - r[4];
    }
    out.forEach((s, k) => { s.daily.push(day[k]); s.cum.push((s.cum.at(-1) ?? 0) + day[k]) });
  }
  return out;
}

/** the last, highest and lowest value of a series (0 for an empty one) */
export function invStats(v: number[]): InvStats {
  return v.length ? { end:v[v.length - 1], hi:Math.max(...v), lo:Math.min(...v) } : { end:0, hi:0, lo:0 };
}

/** CSV text: a header line and one line per row; a cell with a comma, quote or line break is quoted */
export function toCsv(head: string[], rows: (string | number | null)[][]): string {
  const cell = (v: string | number | null) => { const s = v == null ? '' : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s };
  return [head, ...rows].map(r => r.map(cell).join(',')).join('\n');
}
