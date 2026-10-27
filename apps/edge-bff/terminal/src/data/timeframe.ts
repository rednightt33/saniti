/* EXEC-TERMINAL-WM (user 2026-10-27: "time frame ditambah weekly dan monthly"; "G1", "K1"): the database keeps daily
   prices only, so a weekly or monthly candle is built here from the daily sessions already loaded: open of the first
   session, highest high, lowest low, close of the last session, summed volume. A week runs Monday–Friday (its key is
   the Monday), a month is a calendar month. The candle carries the date of its first session (`starts`) and of its last
   one (`ends`); the running week or month is shown as it stands (K1). */
import type { PriceRow } from './worker';

export type Timeframe = 'D' | 'W' | 'M';
export const TIMEFRAMES: Timeframe[] = ['D', 'W', 'M'];
/** periods per year for annualising (Statistics' realized volatility) */
export const PERIODS_PER_YEAR: Record<Timeframe, number> = { D:252, W:52, M:12 };
/** the word for one candle in panel labels */
export const UNIT: Record<Timeframe, { one: string; many: string; adj: string }> = {
  D:{ one:'day', many:'sessions', adj:'daily' }, W:{ one:'week', many:'weeks', adj:'weekly' }, M:{ one:'month', many:'months', adj:'monthly' }
};

export const asTimeframe = (v: unknown): Timeframe => v === 'W' || v === 'M' ? v : 'D';

/** the key of the candle that holds a session date: the date itself (D), the Monday of its week (W), its month (M) */
export function bucketKey(date: string, tf: Timeframe): string {
  if (tf === 'D') return date;
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
  if (tf === 'D') return rows;
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
