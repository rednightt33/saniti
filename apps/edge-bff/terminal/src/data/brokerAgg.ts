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
export interface SumSide { rows: SumRow[]; count: number; total: SumRow }
export interface SumSides { left: SumSide; right: SumSide; total: SumRow }

const sumRow = (b: string, list: Agg[], gross: number): SumRow => {
  const s = (k: 'bv' | 'sv' | 'bl' | 'sl') => list.reduce((t, x) => t + x[k], 0);
  const bv = s('bv'), sv = s('sv'), bl = s('bl'), sl = s('sl');
  return { b, bv, sv, bl, sl, ba:avgPrice(bv, bl), sa:avgPrice(sv, sl), nv:bv - sv, nl:bl - sl, share:gross ? (bv + sv) / gross * 100 : 0 };
};

/** EXEC-TERMINAL-BS-SIDE (user 2026-10-28: "dijajarin aja kiri dan kanan. Kalau semakin scroll down, ya berarti
    value-nya semakin kecil"): the two sides of the Broker summary window, largest first. Net: the net buyers by net
    value (left) and the net sellers by how much they sold net (right); a broker with no net stays on neither side.
    Gross: the buyers by buy value (left) and the sellers by sell value (right); a broker who bought and sold is on
    both. `share` is the broker's buy plus sell value over the period's (the shares of all brokers sum to 100%). Each
    side keeps its first `limit` rows (null: all) of those matching `search`; its `count` and `total` cover every
    matching broker of that side, `total` (outside the sides) every broker of the period. */
export function sidesTable(list: Agg[], o: { mode: 'net' | 'gross'; limit: number | null; search?: string }): SumSides {
  const gross = list.reduce((s, x) => s + x.bv + x.sv, 0);
  const q = (o.search || '').trim().toUpperCase();
  const all = list.filter(x => !q || x.b.includes(q)).map(x => sumRow(x.b, [x], gross));
  const net = o.mode === 'net';
  const key = (r: SumRow, left: boolean) => net ? (left ? r.nv : -r.nv) : (left ? r.bv : r.sv);
  const side = (left: boolean): SumSide => {
    const rows = all.filter(r => key(r, left) > 0).sort((a, b) => key(b, left) - key(a, left) || a.b.localeCompare(b.b));
    return { rows:o.limit == null ? rows : rows.slice(0, o.limit), count:rows.length, total:sumRow('Total', rows, gross) };
  };
  return { left:side(true), right:side(false), total:sumRow('Total', list, gross) };
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
