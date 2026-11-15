/* EXEC-OVERVIEW O5: what the page arranges from the three Overview files. Every figure is the publisher's
   (apps/terminal-publisher/overview.py, OVERVIEW_FORMULAS.md); this module only picks the rows of the user's universe,
   period and metric, sums or weights them, and orders them. Pure functions, tested in tests/model.test.ts. */
import type { Day, Meta, Series, StocksFile } from './types.ts';

export const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const utc = (iso: string) => new Date(iso + 'T00:00:00Z');
const NB = '\u00a0';   // a date never breaks over two lines (QA 2026-11-15: "Turnover (9 / Nov)")
/** "13 Nov"; with the weekday "Fri 13 Nov"; with the year "13 Nov 2026" (no-break spaces). */
export const dateLabel = (iso: string | null | undefined, weekday = false, year = false) => {
  if (!iso) return '—';
  const d = utc(iso);
  return (weekday ? WD[d.getUTCDay()] + NB : '') + d.getUTCDate() + NB + MON[d.getUTCMonth()] + (year ? NB + d.getUTCFullYear() : '');
};
/** "20 Aug – 13 Nov"; both ends carry their year when the range crosses a year (QA 2026-11-15: a 1Y range read
    "27 Oct – 13 Nov"). */
export const rangeLabel = (a: string, b: string) => {
  const y = !!a && !!b && a.slice(0, 4) !== b.slice(0, 4);
  return a === b ? dateLabel(b, false, y) : `${dateLabel(a, false, y)} – ${dateLabel(b, false, y)}`;
};
/** WIB (UTC+7) clock time of an epoch second, "10:35". */
export const wibTime = (t: number) => {
  const d = new Date((t + 7 * 3600) * 1000);
  return String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0');
};
/** WIB calendar date of an epoch second, ISO. */
export const wibDate = (t: number) => new Date((t + 7 * 3600) * 1000).toISOString().slice(0, 10);

/* ---------- numbers ---------- */
const MINUS = '−';
export const sign = (v: number) => (v > 0 ? '+' : v < 0 ? MINUS : '');
export const num = (v: number, d = 2) => v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
export const pct = (v: number | null | undefined, d = 2) => (v == null ? '—' : sign(v) + Math.abs(v).toFixed(d) + '%');
/** The unit of an amount is chosen after rounding (QA 2026-11-15: 999.6 million read "1000M"): the largest of T, B and
    M whose rounded value is at least 1. decimals(unit, value) gives the digits. */
function scaled(a: number, decimals: (unit: string, x: number) => number): string | null {
  for (const [u, f] of [['T', 1e12], ['B', 1e9], ['M', 1e6]] as const) {
    const x = a / f, d = decimals(u, x), r = Number(x.toFixed(d));
    if (r >= 1) return r.toFixed(d) + u;
  }
  return null;
}
/** Rupiah in trillions (T, 2 decimals), billions (B) or millions (M, 1 decimal): "Rp 8.15T", "Rp 111.70T", "Rp 116.6B". */
export function rp(v: number | null | undefined, signed = false) {
  if (v == null) return '—';
  const a = Math.abs(v), s = signed ? sign(v) : v < 0 ? MINUS : '';
  return s + 'Rp ' + (scaled(a, u => (u === 'T' ? 2 : 1)) ?? Math.round(a).toLocaleString('en-US'));
}
/** The short form inside a tile or a bar row: "+1.23T", "+12.3T", "−523B", "+1B"; under Rp 1 million "0" without a sign. */
export function amount(v: number | null | undefined) {
  if (v == null) return '—';
  const a = Math.abs(v);
  if (a < 1e6) return '0';                          // the gray tile's rule (user 2026-11-15): under Rp 1 million reads 0
  return sign(v) + scaled(a, (u, x) => (u === 'T' ? (x >= 9.995 ? 1 : 2) : 0));
}
export const cls = (v: number | null | undefined) => (v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '');

/** The tile size's basis as the publisher names it (overview_stock_size, decision 2: replaceable by market cap). */
export const SIZE_BASIS: Record<string, string> = { adv20_value: '20-day average value traded', market_cap: 'market cap' };
export const sizeLabel = (basis: string | null) => (basis ? SIZE_BASIS[basis] || basis.replace(/_/g, ' ') : 'size');
export const sizeText = (basis: string | null, v: number | null) => (v == null ? '—' : rp(v) + (basis === 'adv20_value' ? '/day' : ''));

/* ---------- colours: the design's seven steps ---------- */
/** signed (user 2026-11-15, choice 3: "Hanya return persis 0% yang abu-abu"; then "Foreign buy samakan juga"): any
    value above 0 takes at least the light green step and any below 0 at least the light red one; only 0 itself stays
    neutral. Without it, the design's band (-0.5, 0.5) is neutral. */
export function colorOf(c: number, signed = false): [string, string] {
  if (c >= 3) return ['var(--green-600)', '#fff'];
  if (c >= 1.5) return ['var(--green-500)', '#fff'];
  if (c >= 0.5 || (signed && c > 0)) return ['var(--green-300)', 'var(--gray-900)'];
  if (c > -0.5 && !(signed && c < 0)) return ['var(--ov-flat)', 'var(--ov-flat-fg)'];   // the design's gray-200 (a token: dark theme)
  if (c > -1.5) return ['var(--red-300)', 'var(--gray-900)'];
  if (c > -3) return ['var(--red-500)', '#fff'];
  return ['var(--red-600)', '#fff'];
}
/* the design's scale per period: a return is divided by it before the steps (1M: ±2/6/12%) and a foreign net in
   Rp billion by 120 x sqrt(sessions) (1D: ±60/180/360 bn) */
export const PERF_SCALE: Record<string, number> = { '1D': 1, '5D': 2, '1M': 4 };
export const SESSIONS: Record<string, number> = { '1D': 1, '5D': 5, '1M': 20, '3M': 60 };
/* a Custom range of n sessions (F1) takes the same families: a return is divided by sqrt(n) (1D 1, 5D 2.24, 1M 4.47,
   next to the fixed 1 / 2 / 4) and a foreign net by Rp 120 bn x sqrt(n) */
export const perfScale = (p: TilePeriod, n?: number) => (p === 'C' ? Math.sqrt(Math.max(1, n || 1)) : PERF_SCALE[p]);
export const foreignScale = (p: TilePeriod, n?: number) => 120e9 * Math.sqrt(p === 'C' ? Math.max(1, n || 1) : SESSIONS[p]);

/* ---------- stocks of a day ---------- */
export type TilePeriod = '1D' | '5D' | '1M' | 'C';          // 'C': a Custom range (F1)
export type FlowPeriod = '1D' | '5D' | '1M' | '3M' | 'C';
export interface Row {
  t: string; name: string; sector: string; close: number | null; size: number | null;
  ret: Partial<Record<TilePeriod, number | null>>; fnet: Partial<Record<FlowPeriod, number | null>>;
  ema50: 0 | 1 | null; ema200: 0 | 1 | null;
}
export function rows(meta: Meta, day: Day): Row[] {
  const s = day.stocks, out: Row[] = [];
  for (let k = 0; k < s.i.length; k++) {
    const i = s.i[k];
    if (meta.stocks.ticker[i] == null) continue;   // a position another publication's meta does not hold: no row
    out.push({ t: meta.stocks.ticker[i], name: meta.stocks.name[i], sector: meta.stocks.sector[i], close: s.close[k], size: s.size[k],
               ret: { '1D': s.r1d[k], '5D': s.r5d[k], '1M': s.r1m[k] },
               fnet: { '1D': s.fnet_1d[k], '5D': s.fnet_5d[k], '1M': s.fnet_1m[k], '3M': s.fnet_3m[k] },
               ema50: s.above_ema50[k], ema200: s.above_ema200[k] });
  }
  return out;
}

/* ---------- universe: every stock, or a Stockbit index or group list ---------- */
export const ALL = 'all';
export interface Universe { key: string; label: string; kind: string; members: Set<string> | null }
export function universes(meta: Meta): Universe[] {
  return [{ key: ALL, label: 'All stocks', kind: 'Market', members: null },
          ...meta.lists.map(l => ({ key: l.key, label: l.name || l.code, kind: l.kind === 'INDEX' ? 'Index' : 'Group', members: new Set(l.members) }))];
}
/** The default universe: the benchmark index's list (LQ45), else every stock. */
export const defaultUniverse = (meta: Meta) => meta.lists.find(l => l.kind === 'INDEX' && l.code === meta.benchmark)?.key || ALL;
export const inUniverse = (u: Universe | undefined) => (r: Row) => !u || !u.members || u.members.has(r.t);

/* ---------- market map ---------- */
export type MapMetric = 'perf' | 'fb';
export interface Tile { r: Row; v: number | null; text: string; col: [string, string] }
export function tile(r: Row, metric: MapMetric, p: TilePeriod, n?: number): Tile {
  if (metric === 'fb') {
    // as Performance: gray exactly when the tile reads 0 (a net under Rp 1 million), else at least the light step
    const v = r.fnet[p] ?? null, shown = v == null || Math.abs(v) < 1e6 ? 0 : v;
    return { r, v, text: amount(v), col: colorOf(shown / foreignScale(p, n), true) };
  }
  // the colour follows the return as written on the tile (2 decimals): gray exactly when it reads 0.00%
  const v = r.ret[p] ?? null, shown = v == null ? 0 : Math.round(v * 100) / 100;
  return { r, v, text: pct(v), col: colorOf(shown / perfScale(p, n), true) };
}
export interface SectorGroup { name: string; size: number; agg: number | null; tiles: Tile[] }
/** The universe's stocks with a size, grouped by sector, largest first; a sector's figure is its size-weighted return
    (Performance) or its summed foreign net (Foreign buy). */
export function mapGroups(rs: Row[], metric: MapMetric, p: TilePeriod, n?: number): SectorGroup[] {
  const by = new Map<string, Tile[]>();
  for (const r of rs) {
    if (!(r.size != null && r.size > 0)) continue;
    const g = by.get(r.sector) || [];
    g.push(tile(r, metric, p, n));
    by.set(r.sector, g);
  }
  return [...by.entries()].map(([name, tiles]) => {
    tiles.sort((a, b) => (b.r.size as number) - (a.r.size as number) || a.r.t.localeCompare(b.r.t));
    const size = tiles.reduce((a, x) => a + (x.r.size as number), 0), known = tiles.filter(x => x.v != null);
    let agg: number | null = null;
    if (known.length) {
      if (metric === 'fb') agg = known.reduce((a, x) => a + (x.v as number), 0);
      else { const w = known.reduce((a, x) => a + (x.r.size as number), 0); agg = known.reduce((a, x) => a + (x.r.size as number) * (x.v as number), 0) / w }
    }
    return { name, size, agg, tiles };
  }).sort((a, b) => b.size - a.size || a.name.localeCompare(b.name));
}

/** Squarified treemap (the design's): rectangles with areas proportional to v inside x, y, w, h. */
export interface Rect<T> { item: T; x: number; y: number; w: number; h: number }
export function squarify<T>(items: { v: number; item: T }[], x: number, y: number, w: number, h: number): Rect<T>[] {
  const out: Rect<T>[] = [], tot = items.reduce((a, b) => a + b.v, 0);
  if (!(tot > 0) || w <= 0 || h <= 0) return out;
  const k = (w * h) / tot, its = items.map(i => ({ item: i.item, a: i.v * k })).sort((a, b) => b.a - a.a);
  let row: typeof its = [], i = 0;
  const worst = (r: typeof its, s: number) => {
    const sum = r.reduce((a, b) => a + b.a, 0), mx = Math.max(...r.map(z => z.a)), mn = Math.min(...r.map(z => z.a));
    return Math.max((s * s * mx) / (sum * sum), (sum * sum) / (s * s * mn));
  };
  const lay = (r: typeof its) => {
    const sum = r.reduce((a, b) => a + b.a, 0);
    if (w >= h) { const rw = sum / h; let yy = y; r.forEach(z => { const rh = z.a / rw; out.push({ item: z.item, x, y: yy, w: rw, h: rh }); yy += rh }); x += rw; w -= rw }
    else { const rh = sum / w; let xx = x; r.forEach(z => { const rw2 = z.a / rh; out.push({ item: z.item, x: xx, y, w: rw2, h: rh }); xx += rw2 }); y += rh; h -= rh }
  };
  while (i < its.length) {
    const s = Math.min(w, h), c = its[i];
    if (!row.length || worst([...row, c], s) <= worst(row, s)) { row.push(c); i++ } else { lay(row); row = [] }
  }
  if (row.length) lay(row);
  return out;
}

/* ---------- top movers and foreign flow ---------- */
export function movers(rs: Row[], p: TilePeriod, n = 5) {
  const known = rs.filter(r => r.ret[p] != null).sort((a, b) => (b.ret[p] as number) - (a.ret[p] as number) || a.t.localeCompare(b.t));
  // the deepest fall first (QA 2026-11-15: the losers were listed mildest first)
  const up = known.filter(r => (r.ret[p] as number) > 0), down = known.filter(r => (r.ret[p] as number) < 0).reverse();
  return { up: up.slice(0, n), down: down.slice(0, n), count: known.length, ups: up.length, downs: down.length };
}
/** The n largest net foreign buyers and sellers of the period (Regular board, every stock of the day file). */
export function foreignTop(rs: Row[], p: FlowPeriod, n = 4) {
  const known = rs.filter(r => r.fnet[p] != null && r.fnet[p] !== 0);
  const buy = known.filter(r => (r.fnet[p] as number) > 0).sort((a, b) => (b.fnet[p] as number) - (a.fnet[p] as number) || a.t.localeCompare(b.t));
  const sell = known.filter(r => (r.fnet[p] as number) < 0).sort((a, b) => (a.fnet[p] as number) - (b.fnet[p] as number) || a.t.localeCompare(b.t));
  return { buy: buy.slice(0, n), sell: sell.slice(0, n) };
}

/* ---------- series up to the chosen date ---------- */
export type SectorPeriod = '20D' | '60D' | 'YTD' | '1Y';
export const YEAR = 252;
/** The index of the start point of a period that ends at series index `end`: n sessions back, or for YTD the last
    session of the previous calendar year. */
export function periodStart(dates: string[], end: number, p: SectorPeriod | number): number {
  if (typeof p === 'number') return Math.max(0, end - p);
  if (p === 'YTD') {
    const y = dates[end].slice(0, 4);
    for (let i = end; i >= 0; i--) if (dates[i].slice(0, 4) < y) return i;
    return 0;
  }
  return Math.max(0, end - ({ '20D': 20, '60D': 60, '1Y': YEAR } as Record<string, number>)[p]);
}
/** Cumulative return in percent from `start` to every point up to `end`; null where a close is missing. */
export function cumulative(closes: (number | null)[], start: number, end: number): (number | null)[] {
  const base = closes[start];
  return closes.slice(start, end + 1).map(v => (v == null || base == null || !(base > 0) ? null : (v / base - 1) * 100));
}
export const lastKnown = (a: (number | null)[]) => { for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null };

export interface SectorLine { name: string; a: (number | null)[]; last: number | null }
export function sectorLines(series: Series, market: string, end: number, p: SectorPeriod): { start: number; lines: SectorLine[]; market: (number | null)[] } {
  const start = periodStart(series.dates, end, p);
  const lines = Object.entries(series.sector).map(([name, c]) => { const a = cumulative(c, start, end); return { name, a, last: a[a.length - 1] } })
    .sort((x, y) => (y.last ?? -Infinity) - (x.last ?? -Infinity) || x.name.localeCompare(y.name));
  return { start, lines, market: cumulative(series.index[market] || [], start, end) };
}

export const SHORT: Record<string, string> = {
  'Basic Materials': 'Basic Mat.', 'Consumer Cyclicals': 'Cons. Cyc', 'Consumer Non-Cyclicals': 'Non-Cyc', 'Infrastructures': 'Infra',
  'Properties & Real Estate': 'Property', 'Transportation & Logistic': 'Transport', 'Healthcare': 'Health', 'Technology': 'Tech',
};

/* ---------- the IHSG chart ---------- */
export type IhsgPeriod = '1D' | '5D' | '1M' | '1Y';
export interface Pt { v: number; tip: string }
export interface IhsgChart { sub: string; pts: Pt[]; ref: number | null; prior: boolean; daily: boolean }
/** 1D: the session's 5-minute bars against the prior close; 5D: the 1-hour bars of the 5 sessions; 1M and 1Y: the
    daily closes of the 20 and 252 sessions back from the date (one point more: the start). */
export function ihsgChart(series: Series, day: Day, market: string, end: number, p: IhsgPeriod): IhsgChart {
  if (p === '1D' || p === '5D') {
    const b = day.intraday[p === '1D' ? '5m' : '1h'] || { t: [], c: [] };
    const pts: Pt[] = [];
    b.t.forEach((t, i) => {
      const v = b.c[i];
      if (v == null) return;
      const d = wibDate(t), hm = wibTime(t);
      pts.push({ v, tip: p === '1D' ? `${dateLabel(d)}, ${hm} WIB` : `${dateLabel(d, true)}, ${hm} WIB` });
    });
    // the reference is the close before the period, as every other 5D figure (QA 2026-11-15: 5D measured from the
    // first hourly bar read +5.17% where the close-to-close move was +5.82%)
    let prior: number | null = null;
    if (p === '1D') prior = day.index[market]?.prior_close ?? null;
    else if (b.t.length) { const i0 = series.dates.indexOf(wibDate(b.t[0])); prior = i0 > 0 ? (series.index[market] || [])[i0 - 1] ?? null : null }
    return { sub: p === '1D' ? 'Intraday' : '5 days', pts, ref: prior ?? (pts[0]?.v ?? null), prior: prior != null, daily: false };
  }
  const n = p === '1M' ? 20 : YEAR, start = periodStart(series.dates, end, n), c = series.index[market] || [];
  const pts: Pt[] = [];
  for (let i = start; i <= end; i++) { const v = c[i]; if (v != null) pts.push({ v, tip: dateLabel(series.dates[i], true) + ' ' + series.dates[i].slice(0, 4) }) }
  return { sub: p === '1M' ? '1 month' : '1 year', pts, ref: pts[0]?.v ?? null, prior: false, daily: true };
}

/** The series index of a date, or of the newest series date before it. */
export function seriesEnd(series: Series, date: string): number {
  let e = -1;
  for (let i = 0; i < series.dates.length; i++) if (series.dates[i] <= date) e = i;
  return e;
}
/** The flow series index of a broker date (the day file's market date), or -1. */
export const flowEnd = (series: Series, date: string | null | undefined) => (date ? series.flow.dates.lastIndexOf(date) : -1);

/* ---------- F1: Custom periods (user 2026-11-15: "1A Rentang tanggal dari–sampai ... 2 A — Semua 5 panel") ---------- */
export const CUSTOM_MAX_DAYS = 365;                        // "maksimal 1 tahun"
export interface Range { a: string; b: string }
/** The trading days of a range in `dates` (oldest first): the first date on or after a, the last on or before b, and
    the base (the session before the first, as 1D/5D/1M measure from the close before the period). null when the range
    holds no trading day. */
export function rangeIn(dates: string[], r: Range): { first: number; last: number; base: number; n: number } | null {
  let first = -1, last = -1;
  for (let i = 0; i < dates.length; i++) { if (first < 0 && dates[i] >= r.a) first = i; if (dates[i] <= r.b) last = i }
  if (first < 0 || last < first) return null;
  return { first, last, base: first - 1, n: last - first + 1 };
}
/** Why a range cannot be used (shown under the fields), or null. */
export function rangeProblem(r: Range, min: string, max: string): string | null {
  if (!r.a || !r.b) return 'Pick both dates.';
  if (r.a > r.b) return 'The start date is after the end date. Swap them.';
  if (r.a < min || r.b > max) return `Pick dates from ${dateLabel(min, false, true)} to ${dateLabel(max, false, true)}.`;
  const days = (utc(r.b).getTime() - utc(r.a).getTime()) / 86400000;
  if (days > CUSTOM_MAX_DAYS) return `The range is ${Math.round(days)} days. Pick at most 1 year (${CUSTOM_MAX_DAYS} days).`;
  return null;
}
/** The rows with ret.C and fnet.C over a range from overview-stocks: return = close on the last trading day / close of
    the session before the first - 1 (as Feature 01); foreign net = the sum of the daily Regular nets of the broker
    dates in the range (null when the stock has none). */
export function customRows(rs: Row[], st: StocksFile, r: Range): Row[] {
  const at = new Map(st.ticker.map((t, i) => [t, i] as [string, number])), d = rangeIn(st.dates, r);
  const fd = st.fnet_dates.map((x, i) => [x, i] as [string, number]).filter(([x]) => x >= r.a && x <= r.b).map(([, i]) => i);
  return rs.map(row => {
    const k = at.get(row.t);
    let ret: number | null = null, net: number | null = null;
    if (k != null && d && d.base >= 0) {
      const c0 = st.close[k][d.base], c1 = st.close[k][d.last];
      if (c0 != null && c1 != null && c0 > 0) ret = (c1 / c0 - 1) * 100;
    }
    if (k != null) for (const i of fd) { const v = st.fnet[k][i]; if (v != null) net = (net ?? 0) + v }
    return { ...row, ret: { ...row.ret, C: ret }, fnet: { ...row.fnet, C: net } };
  });
}
/** The market's foreign buying and selling over the broker dates of a range (series.flow), as the fixed periods. */
export function flowRange(series: Series, r: Range): { buy: number; sell: number; net: number; from: string; to: string; n: number } | null {
  const f = series.flow, idx = f.dates.map((x, i) => [x, i] as [string, number]).filter(([x]) => x >= r.a && x <= r.b);
  if (!idx.length) return null;
  let buy = 0, sell = 0;
  for (const [, i] of idx) { buy += f.foreign_buy[i] ?? 0; sell += f.foreign_sell[i] ?? 0 }
  return { buy, sell, net: buy - sell, from: idx[0][0], to: idx[idx.length - 1][0], n: idx.length };
}
/** Sector lines over a Custom range: from the session before its first trading day to its last. */
export function sectorLinesRange(series: Series, market: string, r: Range) {
  const d = rangeIn(series.dates, r);
  if (!d || d.base < 0) return null;
  const lines = Object.entries(series.sector).map(([name, c]) => { const a = cumulative(c, d.base, d.last); return { name, a, last: a[a.length - 1] } })
    .sort((x, y) => (y.last ?? -Infinity) - (x.last ?? -Infinity) || x.name.localeCompare(y.name));
  return { start: d.base, end: d.last, lines, market: cumulative(series.index[market] || [], d.base, d.last) };
}

