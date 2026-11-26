/* EXEC-SECTOR-ANALYSIS S4: the arithmetic of the page, pure functions (tests/model.test.ts). Every input is a figure of
   the sector files (CONTRACT section 3); this module computes only what depends on the viewer's choice: returns over a
   period, ranks, the rotation map, pair spreads, correlations, beta, breadth shares, advancers and decliners of a horizon,
   industry aggregates of the day. The formulas are the user's final prototype's (verification/sector_analysis/final/
   formulas.md, the logic.js line numbers there), with the decisions of CONTRACT section 1 (periods E, no EMA20 C1, weights D1). */
import type { Breadth, Day, Meta, N, SectorInfo, Series } from './types.ts';
export type { N };

/* ===================== numbers and dates (en-US digits, U+2212 minus; the design system's formats) ===================== */
export const MINUS = '−';
const NB = ' ';
export const sign = (v: number) => (v > 0 ? '+' : v < 0 ? MINUS : '');
const fin = (v: N | undefined): v is number => v != null && Number.isFinite(v);
/** "+1.23%" */
export const pct = (v: N | undefined, d = 2) => (!fin(v) ? '—' : sign(+v.toFixed(d) === 0 ? 0 : v) + Math.abs(v).toFixed(d) + '%');
/** "+1.23 pp" (percentage points) */
export const pp = (v: N | undefined, d = 2) => (!fin(v) ? '—' : sign(+v.toFixed(d) === 0 ? 0 : v) + Math.abs(v).toFixed(d) + ' pp');
/** a signed number without a unit; a value that rounds to 0 has no sign */
export const ppx = (v: N | undefined, d = 1) => (!fin(v) ? '—' : +Math.abs(v).toFixed(d) === 0 ? (0).toFixed(d) : sign(v) + Math.abs(v).toFixed(d));
/** a number with a minus sign and no plus ("0.92", "−0.14") */
export const fnum = (v: N | undefined, d = 2) => (!fin(v) ? '—' : (v < 0 && +Math.abs(v).toFixed(d) !== 0 ? MINUS : '') + Math.abs(v).toFixed(d));
/** an index level or a price with thousands commas */
export const level = (v: N | undefined, d = 2) => (!fin(v) ? '—' : (v < 0 ? MINUS : '') + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d }));
export const cls = (v: N | undefined) => (!fin(v) ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '');
function scaled(a: number, decimals: (unit: string) => number): string | null {
  for (const [u, f] of [['T', 1e12], ['B', 1e9], ['M', 1e6]] as const) {
    const x = a / f, d = decimals(u), r = Number(x.toFixed(d));
    if (r >= 1) return r.toFixed(d) + u;
  }
  return null;
}
/** Rupiah: "Rp 8.15T", "Rp 116.6B", "Rp 4.2M" (the Overview's rp) */
export function rp(v: N | undefined, signed = false) {
  if (!fin(v)) return '—';
  const a = Math.abs(v), s = signed ? sign(v) : v < 0 ? MINUS : '';
  return s + 'Rp ' + (scaled(a, u => (u === 'T' ? 2 : 1)) ?? Math.round(a).toLocaleString('en-US'));
}
/** A share count: "1.2B", "35.6M", "820K" */
export function shares(v: N | undefined) {
  if (!fin(v)) return '—';
  const a = Math.abs(v);
  return a >= 1e9 ? (a / 1e9).toFixed(1) + 'B' : a >= 1e6 ? (a / 1e6).toFixed(1) + 'M' : a >= 1e3 ? (a / 1e3).toFixed(0) + 'K' : a.toFixed(0);
}
/** A stock's weight as its basis reads (decision D1: the basis and its label come from the file; a per-day value of the
    traded-value basis reads "/day", any other basis, market cap later, plain rupiah) */
export const PER_DAY_BASES = new Set(['adv20_value']);
export const weightText = (basis: string | null | undefined, v: N | undefined) => (!fin(v) ? '—' : rp(v) + (basis && PER_DAY_BASES.has(basis) ? '/day' : ''));

export const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WD = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const utc = (iso: string) => new Date(iso + 'T00:00:00Z');
/** "13 Nov", "Fri 13 Nov", "13 Nov 2026" (no-break spaces) */
export const dateLabel = (iso: string | null | undefined, weekday = false, year = false) => {
  if (!iso) return '—';
  const d = utc(iso);
  return (weekday ? WD[d.getUTCDay()] + NB : '') + d.getUTCDate() + NB + MON[d.getUTCMonth()] + (year ? NB + d.getUTCFullYear() : '');
};
/** "20 Aug – 13 Nov"; both ends carry their year when the range crosses a year (defect D11) */
export const rangeLabel = (a: string, b: string) => {
  const y = !!a && !!b && a.slice(0, 4) !== b.slice(0, 4);
  return a === b ? dateLabel(b, false, y) : `${dateLabel(a, false, y)} – ${dateLabel(b, false, y)}`;
};
/** the date tag under a chart's hover line: "Mon 16 Nov '26" */
export const tagDate = (iso: string) => { const d = utc(iso); return `${WD[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]} '${String(d.getUTCFullYear()).slice(2)}` };
/** axis labels of a date axis: the first carries the year when the range crosses years (charts.md) */
export const axisDates = (dates: string[], picks: number[]) => {
  const y = dates.length > 1 && dates[0].slice(0, 4) !== dates[dates.length - 1].slice(0, 4);
  return picks.map((i, k) => dateLabel(dates[i], false, y && k === 0));
};
/** "nice" ticks in steps of 1 / 2 / 2.5 / 5 / 10 x 10^n */
export function ticks(lo: number, hi: number, n = 4): number[] {
  const raw = (hi - lo) / n || 1, p = 10 ** Math.floor(Math.log10(raw)), st = [1, 2, 2.5, 5, 10].map(m => m * p).find(m => m >= raw) as number;
  const t: number[] = [];
  for (let v = Math.ceil(lo / st) * st; v <= hi + 1e-9; v += st) t.push(+v.toFixed(6));
  return t;
}
export const axPct = (v: number) => sign(v) + +Math.abs(v).toFixed(1) + '%';

/* ===================== periods (decision E: as the Overview) ===================== */
/** sessions of each period key (CONTRACT 3.1 meta.periods; this is the contract's table, used when a key is missing) */
export const PERIODS: Record<string, number> = { '1D': 1, '3D': 3, '1W': 5, '2W': 10, '1M': 20, '3M': 60, '6M': 120, '1Y': 252 };
export type Hz = number | 'YTD';
/** the last session of the previous calendar year before `end` (the Overview's periodStart YTD), 0 when there is none */
export function ytdBase(dates: string[], end: number): number {
  const y = dates[end].slice(0, 4);
  for (let i = end; i >= 0; i--) if (dates[i].slice(0, 4) < y) return i;
  return 0;
}
/** the index of the start of a period that ends at `end`: n sessions back, or the YTD base */
export const periodStart = (dates: string[], end: number, p: Hz) => (p === 'YTD' ? ytdBase(dates, end) : Math.max(0, end - p));

/* Custom range (decision E: "capped and anchored as the Overview's Custom (F1)"): the first trading day on or after From,
   the last on or before To; a return is measured from the session before the first (base), at most 365 days */
export const CUSTOM_MAX_DAYS = 365;
export interface Range { a: string; b: string }
export interface Span { base: number; first: number; last: number; n: number }
export function rangeIn(dates: string[], r: Range, end = dates.length - 1): Span | null {
  let first = -1, last = -1;
  for (let i = 0; i <= end; i++) { if (first < 0 && dates[i] >= r.a) first = i; if (dates[i] <= r.b) last = i }
  if (first < 0 || last < first) return null;
  return { first, last, base: first - 1, n: last - first + 1 };
}
export interface RangeCheck { ok: boolean; msg: string; span?: Span }
/** Why a range cannot be used, or its span and a note ("19 Aug → 17 Nov · 60 trading days"). `min` sessions; `max`
    sessions when the card can show no more (the weekly heatmap: 26 weeks, defect D09) */
export function checkRange(dates: string[], end: number, a: string, b: string, o: { min?: number; max?: number; maxWhy?: string } = {}): RangeCheck {
  const lo = dates[1], hi = dates[end];
  if (!a || !b) return { ok: false, msg: 'Pick both dates.' };
  if (a > b) return { ok: false, msg: 'The start date is after the end date. Swap them.' };
  if (b < lo || a > hi) return { ok: false, msg: `Pick dates from ${dateLabel(lo, false, true)} to ${dateLabel(hi, false, true)}.` };
  const days = (utc(b).getTime() - utc(a).getTime()) / 86400000;
  if (days > CUSTOM_MAX_DAYS) return { ok: false, msg: `The range is ${Math.round(days)} days. Pick at most 1 year (${CUSTOM_MAX_DAYS} days).` };
  const s = rangeIn(dates, { a: a < lo ? lo : a, b }, end);
  if (!s || s.base < 0) return { ok: false, msg: 'There is no trading day in this range. Pick another.' };
  const min = o.min ?? 5;
  if (s.n < min) return { ok: false, msg: `Pick a range of at least ${min} trading days.` };
  if (o.max && s.n > o.max) return { ok: false, msg: o.maxWhy || `Pick at most ${o.max} trading days.` };
  return { ok: true, span: s, msg: `${rangeLabel(dates[s.first], dates[s.last])} · ${s.n} trading day${s.n > 1 ? 's' : ''}` };
}

/* ===================== returns and ranks ===================== */
/** % return over n sessions ending at i (logic.js L25) */
export const ret = (a: N[], i: number, n: number): N => (i - n >= 0 && fin(a[i]) && fin(a[i - n]) && (a[i - n] as number) > 0 ? ((a[i] as number) / (a[i - n] as number) - 1) * 100 : null);
/** % return from index b to e */
export const retAt = (a: N[], b: number, e: number): N => (b >= 0 && fin(a[e]) && fin(a[b]) && (a[b] as number) > 0 ? ((a[e] as number) / (a[b] as number) - 1) * 100 : null);
/** cumulative % from b at every index b..e (null where a close is missing) */
export const path = (a: N[], b: number, e: number): N[] => { const out: N[] = []; for (let i = b; i <= e; i++) out.push(retAt(a, b, i)); return out };
export const minus = (x: N, y: N): N => (fin(x) && fin(y) ? x - y : null);
/** rank 1..N, highest value first; a missing value ranks last (logic.js L27) */
export function rankOf(names: string[], val: (n: string) => N): Record<string, number> {
  const o = names.map((n, k) => ({ n, k, v: val(n) })).sort((p, q) => (q.v ?? -Infinity) - (p.v ?? -Infinity) || p.k - q.k);
  const r: Record<string, number> = {};
  o.forEach((x, k) => (r[x.n] = k + 1));
  return r;
}
/** rating 1-99 by `key`, highest first (logic.js L278): round(1 + 98 (N-1-k)/(N-1)); rows without a value get none */
export function rate<T extends Record<string, any>>(list: T[], key: string, out = 'rt'): void {
  const o = list.filter(x => fin(x[key])).sort((p, q) => q[key] - p[key]), n = o.length;
  list.forEach(x => ((x as any)[out] = null));
  o.forEach((x, k) => ((x as any)[out] = n > 1 ? Math.round(1 + (98 * (n - 1 - k)) / (n - 1)) : 99));
}
/** momentum tag (logic.js L279): g = 1W excess − the average week of the 1M excess (1M excess x 5 / 1M sessions) */
export function momTag(e1: N, eM: N, monthSessions = 20): ['Gaining' | 'Steady' | 'Fading', number] | null {
  if (!fin(e1) || !fin(eM)) return null;
  const g = e1 - (eM * 5) / monthSessions;
  return [g > 0.5 ? 'Gaining' : g < -0.5 ? 'Fading' : 'Steady', g];
}
/** weekly blocks of 5 sessions ending at e1 (the newest last), each with 5 sessions before it */
export const weekEnds = (e1: number, nw: number) => Array.from({ length: nw }, (_, k) => e1 - 5 * (nw - 1 - k)).filter(e => e - 5 >= 0);
/** the latest run of weeks with the same sign: +n ahead, −n behind */
export function streak(v: number[]): number {
  let s = 0;
  for (let j = v.length - 1; j >= 0; j--) {
    if (!s) s = v[j] > 0 ? 1 : -1;
    else if ((v[j] > 0) !== (s > 0)) break;
    else s += s > 0 ? 1 : -1;
  }
  return s;
}
/** the deepest fall from a peak inside [b, e], % (logic.js L1424) */
export function maxDrawdown(a: N[], b: number, e: number): N {
  let pk: number | null = null, dd = 0;
  for (let i = b; i <= e; i++) { const v = a[i]; if (!fin(v)) continue; pk = pk == null ? v : Math.max(pk, v); dd = Math.min(dd, (v / pk - 1) * 100) }
  return pk == null ? null : dd;
}

/* ===================== the rotation map (decision A, UD67 2A: our own names; the formula is the prototype's D11) ===================== */
export type Quad = 'Leading' | 'Weakening' | 'Lagging' | 'Improving';
export const QUADS: Quad[] = ['Leading', 'Weakening', 'Lagging', 'Improving'];
/** relative strength = 100 x (sector / benchmark) / its 20-session mean; momentum = 100 x relative strength / its value
    5 sessions earlier (logic.js L29-33, L171-173) */
export function rotation(sec: N[], bench: N[], mean = 20, lag = 5): { rs: N[]; mom: N[] } {
  const n = Math.min(sec.length, bench.length), r: N[] = [], rs: N[] = [], mom: N[] = [];
  for (let i = 0; i < n; i++) r.push(fin(sec[i]) && fin(bench[i]) && (bench[i] as number) > 0 ? (sec[i] as number) / (bench[i] as number) : null);
  for (let i = 0; i < n; i++) {
    let s = 0, ok = i >= mean - 1;
    for (let k = i - mean + 1; ok && k <= i; k++) { if (!fin(r[k])) ok = false; else s += r[k] as number }
    rs.push(ok && fin(r[i]) ? (100 * (r[i] as number)) / (s / mean) : null);
  }
  for (let i = 0; i < n; i++) mom.push(i >= lag && fin(rs[i]) && fin(rs[i - lag]) ? (100 * (rs[i] as number)) / (rs[i - lag] as number) : null);
  return { rs, mom };
}
export const quad = (x: N | undefined, m: N | undefined): Quad | null => (!fin(x) || !fin(m) ? null : x >= 100 ? (m >= 100 ? 'Leading' : 'Weakening') : m >= 100 ? 'Improving' : 'Lagging');
/** the move on the map from i-lb to i: direction 0-360 degrees (0 = relative strength up only, 90 = momentum up only), speed */
export function move(g: { rs: N[]; mom: N[] }, i: number, lb: number): { dx: number; dy: number; deg: number; sp: number } | null {
  const a = g.rs[i], b = g.rs[i - lb], c = g.mom[i], d = g.mom[i - lb];
  if (!fin(a) || !fin(b) || !fin(c) || !fin(d)) return null;
  const dx = a - b, dy = c - d;
  return { dx, dy, deg: ((Math.atan2(dy, dx) * 180) / Math.PI + 360) % 360, sp: Math.hypot(dx, dy) };
}
/** "Strengthening", "Turning up", ... (logic.js L1498): the compass reading of a direction in 45-degree slices */
export const heading = (d: number) => (d < 22.5 || d >= 337.5 ? 'Strength up' : d < 67.5 ? 'Strengthening' : d < 112.5 ? 'Momentum up' : d < 157.5 ? 'Turning up' : d < 202.5 ? 'Strength down' : d < 247.5 ? 'Weakening' : d < 292.5 ? 'Momentum down' : 'Rolling over');
/** one step along Lagging -> Improving -> Leading -> Weakening */
export const clockwise = (a: Quad, b: Quad) => { const o: Quad[] = ['Lagging', 'Improving', 'Leading', 'Weakening']; return (o.indexOf(b) - o.indexOf(a) + 4) % 4 === 1 };

/* ===================== pairs, correlation, beta ===================== */
/** daily simple returns of the sessions (from, to] (null where a close is missing) */
export function dailyRets(a: N[], from: number, to: number): N[] {
  const o: N[] = [];
  for (let i = from + 1; i <= to; i++) o.push(i >= 1 && fin(a[i]) && fin(a[i - 1]) && (a[i - 1] as number) > 0 ? (a[i] as number) / (a[i - 1] as number) - 1 : null);
  return o;
}
/** the pairs where both values are known */
function paired(xa: N[], xb: N[]): [number[], number[]] {
  const a: number[] = [], b: number[] = [];
  for (let i = 0; i < Math.min(xa.length, xb.length); i++) if (fin(xa[i]) && fin(xb[i])) { a.push(xa[i] as number); b.push(xb[i] as number) }
  return [a, b];
}
const mean = (x: number[]) => x.reduce((s, v) => s + v, 0) / x.length;
/** population standard deviation */
export const sdPop = (x: number[]) => { if (!x.length) return NaN; const m = mean(x); return Math.sqrt(x.reduce((s, v) => s + (v - m) ** 2, 0) / x.length) };
/** Pearson correlation of the paired values; null with fewer than 3 pairs or no spread */
export function corr(xa: N[], xb: N[]): N {
  const [a, b] = paired(xa, xb), n = a.length;
  if (n < 3) return null;
  const ma = mean(a), mb = mean(b);
  let c = 0, va = 0, vb = 0;
  for (let i = 0; i < n; i++) { c += (a[i] - ma) * (b[i] - mb); va += (a[i] - ma) ** 2; vb += (b[i] - mb) ** 2 }
  return va > 0 && vb > 0 ? c / Math.sqrt(va * vb) : null;
}
/** beta = correlation x sd(asset) / sd(benchmark) (population; = cov / var, logic.js L653-654) */
export function beta(xa: N[], xb: N[]): N {
  const [a, b] = paired(xa, xb), c = corr(a, b), sa = sdPop(a), sb = sdPop(b);
  return c == null || !(sb > 0) ? null : (c * sa) / sb;
}
/** the ratio A / B rebased to 100 at i0 with its moving average and the +-2 sd band of the same window (logic.js L609-613) */
export function ratioBand(A: N[], B: N[], i0: number, i1: number, ma: number) {
  const ra: N[] = A.map((v, i) => (fin(v) && fin(B[i]) && (B[i] as number) > 0 ? v / (B[i] as number) : null));
  const stat = (i: number) => {
    const w: number[] = [];
    for (let k = i - ma + 1; k <= i; k++) { if (k < 0 || !fin(ra[k])) return null; w.push(ra[k] as number) }
    const mu = mean(w);
    return { mu, sd: Math.sqrt(w.reduce((s, v) => s + (v - mu) ** 2, 0) / ma) };
  };
  const base = ra[i0], v: N[] = [], m: N[] = [], up: N[] = [], dn: N[] = [], z: N[] = [];
  for (let i = i0; i <= i1; i++) {
    const s = stat(i), x = ra[i];
    const rb = (q: number) => (fin(base) && base > 0 ? (q / base) * 100 : null);
    v.push(fin(x) ? rb(x) : null);
    m.push(s ? rb(s.mu) : null); up.push(s ? rb(s.mu + 2 * s.sd) : null); dn.push(s ? rb(s.mu - 2 * s.sd) : null);
    z.push(s && s.sd > 0 && fin(x) ? (x - s.mu) / s.sd : null);
  }
  return { v, m, up, dn, z, ra };
}
/** z of the ratio A / B at e against its own w-session mean and population sd (logic.js L559) */
export function pairZ(A: N[], B: N[], w: number, e: number): N {
  const r: number[] = [];
  for (let i = e - w + 1; i <= e; i++) { if (i < 0 || !fin(A[i]) || !fin(B[i]) || !(B[i] as number > 0)) return null; r.push((A[i] as number) / (B[i] as number)) }
  const m = mean(r), sd = Math.sqrt(r.reduce((s, x) => s + (x - m) ** 2, 0) / w);
  return sd ? (r[w - 1] - m) / sd : null;
}

/* ===================== breadth (Feature_08_Group_Daily counts) ===================== */
export const share = (a: N | undefined, n: N | undefined): N => (fin(a) && fin(n) && n > 0 ? (a / n) * 100 : null);
/** % of a group's members above their EMA50 or EMA200 on every date (members with that EMA only, as the Overview) */
export const breadthLine = (b: Breadth | undefined, ms: 50 | 200): N[] => (!b ? [] : (ms === 50 ? b.a50 : b.a200).map((a, i) => share(a, (ms === 50 ? b.n50 : b.n200)[i])));
export interface Counts { u: number; f: number; d: number; N: number }
/** advancers, unchanged and decliners of a return column: a stock without the return is not counted (as the publisher's
    day breadth and the series' adv/unch/dec) */
export function aud(values: N[]): Counts {
  let u = 0, f = 0, d = 0;
  for (const v of values) { if (!fin(v)) continue; if (Math.abs(v) < 1e-9) f++; else if (v > 0) u++; else d++ }
  return { u, f, d, N: u + f + d };
}
/** a share of flags: 1s over the known flags (a null flag is not counted, as the series' n50 / a50) */
export function flagShare(flags: (0 | 1 | null)[]): { a: number; n: number; p: N } {
  let a = 0, n = 0;
  for (const f of flags) if (f === 0 || f === 1) { n++; a += f }
  return { a, n, p: share(a, n) };
}

/* ===================== the treemap (logic.js L1195-1205, the squarified layout) ===================== */
export interface Box<T> { o: T; v: number; x: number; y: number; w: number; h: number }
export function squarify<T>(items: { v: number; o: T }[], x: number, y: number, w: number, h: number): Box<T>[] {
  const out: Box<T>[] = [];
  let rest = items.filter(i => i.v > 0), X = x, Y = y, Wd = w, Hh = h;
  while (rest.length && Wd > 0 && Hh > 0) {
    const sh = Math.min(Wd, Hh), area = Wd * Hh, sum0 = rest.reduce((p, i) => p + i.v, 0);
    let row: typeof rest = [], best = Infinity;
    for (const it of rest) {
      const r2 = [...row, it], sm = (r2.reduce((p, i) => p + i.v, 0) / sum0) * area;
      const worst = Math.max(...r2.map(i => { const q = (i.v / sum0) * area; return Math.max((sh * sh * q) / (sm * sm), (sm * sm) / (sh * sh * q)) }));
      if (worst <= best) { best = worst; row = r2 } else break;
    }
    const sm = (row.reduce((p, i) => p + i.v, 0) / sum0) * area, thick = sm / sh;
    let off = 0;
    row.forEach(i => { const len = (i.v / sum0) * area / thick; if (Wd >= Hh) out.push({ ...i, x: X, y: Y + off, w: thick, h: len }); else out.push({ ...i, x: X + off, y: Y, w: len, h: thick }); off += len });
    if (Wd >= Hh) { X += thick; Wd -= thick } else { Y += thick; Hh -= thick }
    rest = rest.slice(row.length);
  }
  return out;
}

/* ===================== the shared multi-column sort (logic.js L563-576) ===================== */
/** a level: [key, dir, first dir]; dir 1 = high to low for numbers, A to Z for text */
export type Level = [string, number, number?];
export const MAX_LEVELS = 3;
export const ascending = (dir: number, txt: boolean) => (txt ? dir > 0 : dir < 0);
export function msCmp(p: any, q: any, L: Level[], txt: Record<string, any> = {}): number {
  for (const [k, dir] of L) {
    const a = p[k], b = q[k];
    if (a == null && b == null) continue;
    if (a == null) return 1;
    if (b == null) return -1;
    const c = txt[k] ? dir * String(a).localeCompare(String(b)) : -dir * (a - b);
    if (c) return c;
  }
  return 0;
}
export const msSort = <T>(rows: T[], SK: Level[], txt: Record<string, any> = {}, def: Level | null = null): T[] =>
  rows.sort((p, q) => msCmp(p, q, SK.length ? SK : def ? [def] : [], txt) || (SK.length && def ? msCmp(p, q, [def], txt) : 0));
/** a header click: a new column joins as the next level (the oldest drops past 3); again reverses; a third time removes */
export function msClick(SK: Level[], key: string, def: Level | null): void {
  const ix = SK.findIndex(x => x[0] === key);
  if (ix < 0) {
    const d0 = !SK.length && def && def[0] === key ? -def[1] : 1;
    if (SK.length >= MAX_LEVELS) SK.shift();
    SK.push([key, d0, d0]);
  } else if (SK[ix][1] === (SK[ix][2] ?? 1)) SK[ix][1] = -SK[ix][1];
  else SK.splice(ix, 1);
}
export const msKeep = (SK: Level[], ok: (k: string) => boolean) => { for (let i = SK.length - 1; i >= 0; i--) if (!ok(SK[i][0])) SK.splice(i, 1); return SK };

/* ===================== the files of one date, arranged for the cards ===================== */
export interface Row {
  i: number; t: string; n: string; sec: string; ind: string | null;
  close: N; vol: N; r1d: N; r5d: N; r1m: N; r3m: N; w: N;
  e50: 0 | 1 | null; e200: 0 | 1 | null; d50: N; d200: N; days50: N; days200: N; since50: string | null; since200: string | null;
}
export const SHORT: Record<string, string> = {
  'Basic Materials': 'Basic Mat.', 'Consumer Cyclicals': 'Cons. Cyc', 'Consumer Non-Cyclicals': 'Non-Cyc', 'Infrastructures': 'Infra',
  'Properties & Real Estate': 'Property', 'Transportation & Logistic': 'Transport', 'Healthcare': 'Health', 'Technology': 'Tech',
};
/** the matrix column heads (logic.js L692) */
export const ABBR: Record<string, string> = {
  'Basic Materials': 'Basic', 'Consumer Cyclicals': 'Cyc', 'Consumer Non-Cyclicals': 'NonCyc', 'Energy': 'Energy', 'Financials': 'Fin',
  'Healthcare': 'Health', 'Industrials': 'Indus', 'Infrastructures': 'Infra', 'Properties & Real Estate': 'Prop', 'Technology': 'Tech', 'Transportation & Logistic': 'Trans',
};
export const MARKET = 'IHSG';
export interface Data {
  meta: Meta; series: Series; day: Day;
  dates: string[]; E: number; market: string; IH: N[];
  names: string[]; info: Record<string, SectorInfo>;
  /** sessions of a period key ('1W', '1M', ...) */
  P(key: string): number;
  sec(name: string): N[];
  short(name: string): string;
  abbr(name: string): string;
  rows: Row[];
  /** the day's stocks of a sector, or every stock for the market ('IHSG') */
  members(name: string): Row[];
  breadth(group: string): Breadth | undefined;
  weightBasis: string | null; weightLabel: string;
  ytd(end?: number): number;
  industries(sector: string): string[];
}
/** the series index of a date, or of the newest series date before it */
export function seriesEnd(dates: string[], date: string): number {
  let e = -1;
  for (let i = 0; i < dates.length; i++) if (dates[i] <= date) e = i;
  return e;
}
export function makeData(meta: Meta, series: Series, day: Day): Data {
  const dates = series.dates, E = seriesEnd(dates, day.date), market = meta.market || MARKET;
  const names = meta.sectors.map(s => s.name).filter(n => series.sector[n]);
  const info = Object.fromEntries(meta.sectors.map(s => [s.name, s]));
  const s = day.stocks, rows: Row[] = [];
  for (let k = 0; k < s.i.length; k++) {
    const i = s.i[k], t = meta.stocks.ticker[i];
    if (t == null) continue;                    // a position another publication's meta does not hold: no row
    rows.push({ i, t, n: meta.stocks.name[i], sec: meta.stocks.sector[i], ind: meta.stocks.industry?.[i] ?? null,
                close: s.close?.[k] ?? null, vol: s.volume?.[k] ?? null, r1d: s.r1d?.[k] ?? null, r5d: s.r5d?.[k] ?? null,
                r1m: s.r1m?.[k] ?? null, r3m: s.r3m?.[k] ?? null, w: s.weight?.[k] ?? null,
                e50: s.above_ema50?.[k] ?? null, e200: s.above_ema200?.[k] ?? null, d50: s.d_ema50?.[k] ?? null, d200: s.d_ema200?.[k] ?? null,
                days50: s.days50?.[k] ?? null, days200: s.days200?.[k] ?? null, since50: s.since50?.[k] ?? null, since200: s.since200?.[k] ?? null });
  }
  const bySec = new Map<string, Row[]>();
  for (const r of rows) { const g = bySec.get(r.sec) || []; g.push(r); bySec.set(r.sec, g) }
  const indOf = new Map<string, string[]>();
  for (const x of meta.industries || []) { const g = indOf.get(x.sector) || []; g.push(x.name); indOf.set(x.sector, g) }
  return {
    meta, series, day, dates, E, market, IH: series.index[market] || [],
    names, info,
    P: key => meta.periods?.[key] ?? PERIODS[key] ?? (/^\d+D$/.test(key) ? parseInt(key, 10) : NaN),
    sec: n => series.sector[n] || [],
    short: n => (n === market ? market : info[n]?.short && info[n].short !== n ? info[n].short : SHORT[n] || n),
    abbr: n => ABBR[n] || (info[n]?.short || n).slice(0, 6),
    rows,
    members: n => (n === market || n === MARKET ? rows : bySec.get(n) || []),
    breadth: g => series.breadth?.[g === MARKET ? market : g],
    weightBasis: meta.weight_basis ?? null,
    weightLabel: meta.weight_label || 'weight',
    ytd: (end = E) => ytdBase(dates, end),
    industries: sec => indOf.get(sec) || [],
  };
}
