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
  /* EXEC-QA5-FIX (QA 2026-11-07, S-05): in Gross a side's share is of its own side, the buyers' buy value over the period's
     buy value and the sellers' sell value over its sell value (each side sums to 100%); "buy + sell over buy + sell" put
     every broker on both sides and the two totals added up to 199.8% */
  const sideTot = (left: boolean) => list.reduce((t, x) => t + (left ? x.bv : x.sv), 0);
  const side = (left: boolean): SumSide => {
    const rows = all.filter(r => key(r, left) > 0).sort((a, b) => key(b, left) - key(a, left) || a.b.localeCompare(b.b));
    const tot = sideTot(left), own = (r: SumRow): SumRow => net ? r : { ...r, share:tot ? (left ? r.bv : r.sv) / tot * 100 : 0 };
    const kept = (o.limit == null ? rows : rows.slice(0, o.limit)).map(own);
    return { rows:kept, count:rows.length, total:own(sumRow('Total', rows, gross)) };
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
/* EXEC-QA5-FIX (S-07): a number keeps at most 6 decimals, so a sum of fractional lots reads 418352.84, not
   418352.83999999997; a context line (what the table is: ticker, period, filters) may lead the header */
export function toCsv(head: string[], rows: (string | number | null)[][], context?: string): string {
  const cell = (v: string | number | null) => { const s = v == null ? '' : typeof v === 'number' ? String(+v.toFixed(6)) : String(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s };
  return [...(context ? [[context]] : []), head, ...rows].map(r => r.map(cell).join(',')).join('\n');
}

/** EXEC-TERMINAL-TOPSPLIT (user 2026-10-29: "pakai versi ini saja, tapi di balik ya, yang tebal = domestic"): the parts of a
    Top brokers bar. The bar's length stays the broker's net; inside it, the investor types that go the net's way, in
    proportion, Domestic first (beside the middle line, solid) then Foreign (faded). A type that went the other way is not
    drawn (the hover says it). */
export function splitParts(foreign: number, domestic: number, side: 'buy' | 'sell'): { k: 'D' | 'F'; share: number }[] {
  const same = ([['D', domestic], ['F', foreign]] as ['D' | 'F', number][]).filter(([, v]) => side === 'buy' ? v > 0 : v < 0);
  const tot = same.reduce((s, [, v]) => s + Math.abs(v), 0);
  return tot ? same.map(([k, v]) => ({ k, share:Math.abs(v) / tot })) : [];
}
/** the bar's fill: `width` % of the track, split as splitParts */
export const splitFill = (width: number, foreign: number, domestic: number, side: 'buy' | 'sell') =>
  `<div class="fill split" style="width:${width.toFixed(1)}%">${splitParts(foreign, domestic, side)
    .map(p => `<i class="${p.k === 'F' ? 'f' : 'd'}" style="width:${(p.share * 100).toFixed(1)}%"></i>`).join('')}</div>`;
export const SPLIT_LEGEND = '<span class="split-leg"><span><i class="d"></i>Domestic</span><span><i class="f"></i>Foreign</span></span>';

/** EXEC-INV-SYNC (user 2026-11-01: "user ngeklik di panel broker, let's say dia klik KZ ... otomatis broker inventory juga
    display broker inventory untuk broker tersebut"): a broker list after a broker is picked, by the panel's own rule (the
    Broker inventory panel, broker.ts pick): a broker already in it changes nothing; otherwise it is added at the end and
    the oldest leaves when the list is past `max`. The same array back when nothing changes. */
export function withPicked(list: string[], code: string, max: number): string[] {
  if (list.includes(code)) return list;
  const out = [...list, code];
  return out.length > max ? out.slice(out.length - max) : out;
}

/* ---- EXEC-BROKER-INV-PANEL (user 2026-11-06: "untuk top brokers bisa pakai HTML terlampir dan tambahkan juga 2x
   domestic foreign map"): the Top N groups split by investor type ---- */
export interface SidePart { t: number; d: number; f: number }
export interface FdSplit { buy: SidePart; sell: SidePart; net: SidePart; total: number; ratio: number; rf: number; rd: number }
/** the Top N buyers' and sellers' net split into domestic and foreign transactions. `buyers` and `sellers` are the codes
    of the Top N groups (all investors, as the verdict), `part` each broker's net by investor type, `total` the period's
    total buy value (the verdict's denominator). buy = the buyers' net (positive = buying), sell = the sellers' net sale
    (positive = selling); net = buy − sell, so net.d + net.f = net.t and rd + rf = the verdict's ratio. */
export function fdSplit(buyers: string[], sellers: string[], part: Map<string, { d: number; f: number }>, total: number): FdSplit {
  const sum = (codes: string[], k: 'd' | 'f') => codes.reduce((s, b) => s + (part.get(b)?.[k] || 0), 0);
  const bd = sum(buyers, 'd'), bf = sum(buyers, 'f'), sd = -sum(sellers, 'd'), sf = -sum(sellers, 'f');
  const buy = { t:bd + bf, d:bd, f:bf }, sell = { t:sd + sf, d:sd, f:sf };
  const net = { t:buy.t - sell.t, d:buy.d - sell.d, f:buy.f - sell.f };
  return { buy, sell, net, total, ratio:total > 0 ? net.t / total : 0, rf:total > 0 ? net.f / total : 0, rd:total > 0 ? net.d / total : 0 };
}
/** the map's four quadrants by the signs of the foreign (x) and domestic (y) contributions; 0 counts as the positive side */
/* QA round 3 (agent 5 M4, the open Low "quadrant names without a minimum"): a part that shows as 0.00% (under FD_FLAT
   percentage points either way) is flat, not a direction; both flat is "No net flow", one flat names the other side only.
   x foreign, y domestic, in % of total buy value. EXEC-QA5-FIX (QA 2026-11-07, F1-F3): the map shows two decimals, as Top
   brokers' verdict, and the flat band is derived from that precision */
export const FD_DP = 2;
/** EXEC-RP-LOOK-2 A1 (user 2026-11-08: "boleh ditambahkan nominal?"): the F×D parts in Rupiah as shown, in one unit for a
    whole table (billions, or millions when every part is under Rp 1B) with FD_DP decimals and thousands separators, so a
    column compares at one precision (Rp 0.60T hid Rp 10B); the verdict is the sum of the shown parts, so a row adds up */
export const FD_NOM_UNITS: [number, string][] = [[1e9, 'B'], [1e6, 'M'], [1, '']];
export const fdNomUnit = (vals: number[]): [number, string] => { const m = Math.max(0, ...vals.map(v => Math.abs(v))); return FD_NOM_UNITS.find(([u]) => m >= u) ?? [1, ''] };
const NOM_NF = new Intl.NumberFormat('en-US', { minimumFractionDigits:FD_DP, maximumFractionDigits:FD_DP });
/** a Rupiah amount in the table's unit, without a sign (the total buy value beside the parts) */
export const fdNomText = (v: number, [u, k]: [number, string]) => `Rp ${NOM_NF.format(Math.abs(+(v / u).toFixed(FD_DP)))}${k}`;
export function fdNomShown(nf: number, nd: number, [u, k]: [number, string]) {
  const r = (v: number) => +(v / u).toFixed(FD_DP) || 0, f = r(nf), d = r(nd), v = +(f + d).toFixed(FD_DP) || 0;
  const t = (x: number) => `${x > 0 ? '+' : x < 0 ? '−' : ''}Rp ${NOM_NF.format(Math.abs(x))}${k}`;
  return { f, d, v, text:{ f:t(f), d:t(d), v:t(v) } };
}
export const FD_FLAT = 0.5 / 10 ** FD_DP;
const rd = (v: number) => { const r = Math.round(v * 10 ** FD_DP) / 10 ** FD_DP; return r === 0 ? 0 : r };
/** the figures as shown: each rounded to FD_DP decimals, the verdict as Top brokers rounds it, and the two parts adjusted
    by the largest remainder so that Foreign + Domestic = Verdict on screen too (a rounding never changes a sum) */
export function fdShown(x: number, y: number, r = x + y): { x: number; y: number; r: number } {
  const R = rd(r); let X = rd(x), Y = rd(y);
  const gap = Math.round((R - X - Y) * 10 ** FD_DP);           // whole steps of 0.01 still missing (−1, 0 or +1)
  if (gap) { const ex = x - X, ey = y - Y, step = gap / 10 ** FD_DP;   // give the step to the part rounded furthest the other way
    if ((gap > 0 ? ex >= ey : ex <= ey)) X = rd(X + step); else Y = rd(Y + step) }
  return { x:X, y:Y, r:R };
}
export const FD_QUADRANTS = ['Both accumulating', 'Domestic absorbing, foreign leaving', 'Foreign absorbing, domestic leaving', 'Both distributing',
  'No net flow', 'Domestic accumulating, foreign flat', 'Domestic distributing, foreign flat', 'Foreign accumulating, domestic flat',
  'Foreign distributing, domestic flat'] as const;
export const fdQuadrant = (x: number, y: number) => {
  const fx = Math.abs(x) < FD_FLAT, fy = Math.abs(y) < FD_FLAT;
  if(fx && fy) return 4;
  if(fx) return y > 0 ? 5 : 6;
  if(fy) return x > 0 ? 7 : 8;
  return x > 0 && y > 0 ? 0 : x < 0 && y > 0 ? 1 : x > 0 ? 2 : 3;
};
