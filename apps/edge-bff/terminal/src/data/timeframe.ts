/* EXEC-TERMINAL-WM (user 2026-10-27: "time frame ditambah weekly dan monthly"; "G1", "K1"): the database keeps daily
   prices only, so a weekly or monthly candle is built here from the daily sessions already loaded: open of the first
   session, highest high, lowest low, close of the last session, summed volume. A week runs Monday–Friday (its key is
   the Monday), a month is a calendar month. The candle carries the date of its first session (`starts`) and of its last
   one (`ends`); the running week or month is shown as it stands (K1). */
import type { PriceRow } from './worker';
import type { Bar } from './types';

/* EXEC-INTRADAY-FEATURES C3 (user 2026-11-01): intraday timeframes are the manifest's ('5m', '15m', '1h', '4h' today),
   never a list here: any `<number><m|h>` is one, and the page offers those the ticker's /bundle answer lists. */
export type IntradayTf = `${number}${'m' | 'h'}`;
export type Timeframe = 'D' | 'W' | 'M' | IntradayTf;
export const TIMEFRAMES: Timeframe[] = ['D', 'W', 'M'];
const INTRADAY = /^[0-9]{1,3}[mh]$/;
export const isIntraday = (tf: unknown): tf is IntradayTf => typeof tf === 'string' && INTRADAY.test(tf);
/** periods per year for annualising (Statistics' realized volatility); an intraday timeframe's comes from its manifest
    (`bars_per_year`, the same definition Feature 01 uses) */
export const PERIODS_PER_YEAR: Record<string, number> = { D:252, W:52, M:12 };
export const periodsPerYear = (tf: Timeframe, barsPerYear?: number) => isIntraday(tf) ? (barsPerYear || 252) : PERIODS_PER_YEAR[tf];
/** the word for one candle in panel labels */
const UNITS: Record<string, { one: string; many: string; adj: string }> = {
  D:{ one:'day', many:'sessions', adj:'daily' }, W:{ one:'week', many:'weeks', adj:'weekly' }, M:{ one:'month', many:'months', adj:'monthly' }
};
export const UNIT = new Proxy(UNITS, { get:(t, k: string) => t[k] || { one:'bar', many:'bars', adj:'per-bar' } });
/** '5m' -> '5M', '1h' -> '1H' (the button), 'D' as is */
export const tfLabel = (tf: Timeframe) => tf.toUpperCase();
export const tfTitle = (tf: Timeframe) => isIntraday(tf)
  ? `${parseInt(tf)} ${tf.endsWith('h') ? (parseInt(tf) === 1 ? 'hour' : 'hours') : 'minutes'}` : ({ D:'Daily', W:'Weekly', M:'Monthly' } as Record<string, string>)[tf];

export const asTimeframe = (v: unknown): Timeframe => v === 'W' || v === 'M' || isIntraday(v) ? v as Timeframe : 'D';

/* An intraday candle's key is its open time on the exchange's clock, 'YYYY-MM-DDTHH:MM': it sorts like the time, and its
   first ten characters are its session date, so every comparison with a session date keeps working (dayOfKey). */
export const dayOfKey = (key: string) => key.slice(0, 10);
export function barKey(epochSeconds: number, offsetSeconds: number): string {
  return new Date((epochSeconds + offsetSeconds) * 1000).toISOString().slice(0, 16);
}

/** the key of the candle that holds a session date: the date itself (D), the Monday of its week (W), its month (M) */
export function bucketKey(date: string, tf: Timeframe): string {
  if (tf === 'D' || isIntraday(tf)) return date;
  if (tf === 'M') return date.slice(0, 7);
  const t = new Date(date + 'T00:00:00Z'), back = (t.getUTCDay() + 6) % 7;      // days since Monday
  return new Date(t.getTime() - back * 86400000).toISOString().slice(0, 10);
}

export interface Buckets { starts: string[]; ends: string[]; of: number[] }

/** sessions (ascending dates) grouped into candles: each candle's first and last session, and each session's candle */
export function buckets(dates: string[], tf: Timeframe): Buckets {
  const starts: string[] = [], ends: string[] = [], of: number[] = [];
  let last = '';
  for (const d of dates) {
    const k = bucketKey(d, tf);
    if (k !== last) { starts.push(d); ends.push(d); last = k } else ends[ends.length - 1] = d;
    of.push(starts.length - 1);
  }
  return { starts, ends, of };
}

/** daily price rows (ascending) as candles of the timeframe */
export function aggregateRows(rows: PriceRow[], tf: Timeframe): PriceRow[] {
  if (tf === 'D' || isIntraday(tf)) return rows;
  const out: PriceRow[] = [];
  let last = '';
  for (const r of rows) {
    const k = bucketKey(r.d, tf), c = out[out.length - 1];
    if (k !== last || !c) { out.push({ ...r }); last = k; continue }
    c.h = Math.max(c.h, r.h); c.l = Math.min(c.l, r.l); c.c = r.c;
    c.v = c.v === null && r.v === null ? null : (c.v ?? 0) + (r.v ?? 0);
  }
  return out;
}

/** the candle start (a date in `starts`) for any date: the candle that holds the first session on or after it; the
    last candle for a date after every session; null before the first session's candle */
export function candleOf(date: string, b: Buckets, sessions: string[]): string | null {
  if (!sessions.length) return null;
  let lo = 0, hi = sessions.length;                       // first session on or after `date`
  while (lo < hi) { const m = (lo + hi) >> 1; if (sessions[m] < date) lo = m + 1; else hi = m }
  return lo >= sessions.length ? b.starts[b.starts.length - 1] : b.starts[b.of[lo]];
}

/** EXEC-TERMINAL-ASSETS: another ticker's daily rows as candles of the chart (`starts`: each candle's date, `of`: the
    candle of each chart session). A session the ticker did not trade repeats its last close; candles before its first
    row are left out. */
export function alignCandles(sessions: string[], groups: { starts: string[]; of: number[] }, rows: PriceRow[]): Bar[] {
  const byDate = new Map(rows.map(r => [r.d, r]));
  const out: Bar[] = [];
  let last: number | null = null, k = 0;
  while (k < rows.length && rows[k].d < sessions[0]) last = rows[k++].c;       // a close before the chart's first session
  sessions.forEach((d, i) => {
    const r = byDate.get(d);
    const bar = r ? { o:r.o, h:r.h, l:r.l, c:r.c } : last !== null ? { o:last, h:last, l:last, c:last } : null;
    if (!bar) return;
    last = bar.c;
    const time = groups.starts[groups.of[i]], cur = out[out.length - 1];
    if (cur && cur.time === time) { cur.high = Math.max(cur.high, bar.h); cur.low = Math.min(cur.low, bar.l); cur.close = bar.c }
    else out.push({ time, open:bar.o, high:bar.h, low:bar.l, close:bar.c });
  });
  return out;
}

/* EXEC-INTRADAY-FEATURES C4 (user 2026-11-01: "Sabtu kita pakai A, namun ini hanya berlaku intraday literally di hari
   terbaru. Kalau di hari sebelumnya, maka flow dan bandar harus di-show, tapi menggunakan time frame daily"; "Opsi 1"):
   which daily session each intraday candle shows for the daily figures (Flow, Bandar, Broker, a daily-only indicator).
   An earlier day shows its own session on every one of its candles; the chart's latest day shows its own figure only on
   its last candle (a daily figure exists only after the close) and the day before's on the candles before it. -1: no
   session (a candle before the first daily session). */
export function dayOfCandles(keys: string[], days: string[]): Int32Array {
  const out = new Int32Array(keys.length).fill(-1), at = new Map(days.map((d, i) => [d, i]));
  if (!keys.length) return out;
  const latest = dayOfKey(keys[keys.length - 1]);
  let j = 0;                                                   // the last day on or before the candle's day
  keys.forEach((k, i) => {
    const d = dayOfKey(k);
    while (j + 1 < days.length && days[j + 1] <= d) j++;
    const own = at.get(d) ?? (days[j] <= d ? j : -1);
    out[i] = d === latest && i < keys.length - 1 ? (at.has(d) ? own - 1 : own) : own;
  });
  return out;
}

/** a daily series on the candles (dayOfCandles); null where a candle shows no session */
export function onCandles<T>(daily: ArrayLike<T | null>, dayOf: Int32Array): (T | null)[] {
  return Array.from(dayOf, d => d >= 0 && d < daily.length ? daily[d] ?? null : null);
}

/** a daily marker on the candles: only on the first candle that shows its session, so a day is marked once */
export function markerOnCandles<T>(daily: ArrayLike<T | null>, dayOf: Int32Array): (T | null)[] {
  return Array.from(dayOf, (d, i) => d >= 0 && d < daily.length && (i === 0 || dayOf[i - 1] !== d) ? daily[d] ?? null : null);
}

/** true at the first candle of each run of candles that show the same session: sums over candles count a day once */
export function firstOfDay(dayOf: Int32Array): Uint8Array {
  return Uint8Array.from(dayOf, (d, i) => d >= 0 && (i === 0 || dayOf[i - 1] !== d) ? 1 : 0);
}
