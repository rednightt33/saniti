/* EXEC-BACKTEST-REVAMP P6.1: a small deterministic market for the look-ahead gate (no database, CI-safe). Weekday
   sessions with gaps (a suspension), a random walk with regimes, volume; broker rows on the Regular board with Nego and
   Cash crossings, both investor types, a broker that appears late and one that stops, and transaction counts. Sizes stay
   small (Agent 6: the gate's run time grows with the fixture). Pure functions of their seeds. */
import type { Bars } from '../../../edge-bff/terminal/src/calc/indicators.ts';

export const rng = (seed: number) => { let s = seed >>> 0; return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296 } };

/** `n` weekday sessions from `start`. */
export function sessions(start: string, n: number): string[] {
  const out: string[] = [], d = new Date(`${start}T00:00:00Z`);
  while (out.length < n) {
    const wd = d.getUTCDay();
    if (wd !== 0 && wd !== 6) out.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

export interface Ticker { ticker: string; dates: string[]; bars: Bars & { T: string[] } }

/** A price series on `dates`: a walk whose drift changes every 80 sessions; volume null for an index. */
export function ticker(name: string, seed: number, dates: string[], index = false): Ticker {
  const r = rng(seed), O: number[] = [], H: number[] = [], L: number[] = [], C: number[] = [], V: (number | null)[] = [];
  let c = 1000 + Math.floor(r() * 4000), drift = 0;
  for (let i = 0; i < dates.length; i++) {
    if (i % 80 === 0) drift = (r() - 0.5) * 0.004;
    const o = Math.max(50, Math.round(c * (1 + (r() - 0.5) * 0.01)));
    c = Math.max(50, Math.round(o * (1 + drift + (r() - 0.5) * 0.04)));
    const h = Math.max(o, c) + Math.round(r() * c * 0.015), l = Math.max(1, Math.min(o, c) - Math.round(r() * c * 0.015));
    O.push(o); H.push(h); L.push(l); C.push(c); V.push(index ? null : Math.round(1e5 + r() * 5e6));
  }
  return { ticker: name, dates, bars: { O, H, L, C, V: V as number[], T: dates } };
}

export interface Row { d: string; b: string; i: string; m: string; bv: number; sv: number; bl: number; sl: number; bf: number; sf: number }

/** Broker rows of a ticker on its own sessions: about 10 brokers a day on Regular, a Nego crossing on about 1 day in
    10 and a Cash one on 1 in 20; broker LATE trades only from session 200, broker GONE stops after session 350. */
export function brokerRows(t: Ticker, seed: number): Row[] {
  const r = rng(seed), codes = ['AA', 'BK', 'CC', 'DX', 'EP', 'FS', 'GR', 'HP', 'IF', 'KZ', 'LG', 'MG', 'NI', 'OD', 'PD', 'RX', 'SQ', 'TP', 'XL', 'YP', 'YU', 'ZP'];
  const out: Row[] = [];
  for (let i = 0; i < t.dates.length; i++) {
    const day = codes.filter(() => r() < 0.45);
    if (i >= 200) day.push('LATE');
    if (i <= 350) day.push('GONE');
    const px = t.bars.C[i] as number, bias = Math.sin(i / 37);
    for (const b of day) {
      const inv = r() < 0.35 ? 'Foreign' : 'Domestic', bl = Math.round(r() * 2000 * (1 + bias)), sl = Math.round(r() * 2000 * (1 - bias));
      out.push({ d: t.dates[i], b, i: inv, m: 'Regular', bv: Math.round(bl * 100 * px * (1 + (r() - 0.5) * 0.01)), sv: Math.round(sl * 100 * px * (1 + (r() - 0.5) * 0.01)),
        bl: Math.max(0, bl), sl: Math.max(0, sl), bf: 1 + Math.floor(r() * 40), sf: 1 + Math.floor(r() * 40) });
    }
    for (const [m, p] of [['Nego', 0.1], ['Cash', 0.05]] as const)
      if (r() < p) { const b = codes[Math.floor(r() * codes.length)], lots = Math.round(r() * 5000);
        out.push({ d: t.dates[i], b, i: 'Domestic', m, bv: Math.round(lots * 100 * px * (1 + (r() - 0.5) * 0.06)), sv: 0, bl: lots, sl: 0, bf: 1, sf: 0 }) }
  }
  return out.sort((a, b) => a.d < b.d ? -1 : a.d > b.d ? 1 : a.b < b.b ? -1 : a.b > b.b ? 1 : a.i < b.i ? -1 : a.i > b.i ? 1 : a.m < b.m ? -1 : 1);
}

/** The gate's market: IHSG (no volume) and three stocks, one with a suspension (12 sessions missing). */
export function market() {
  const N = 560, ALL = sessions('2018-01-02', N), skip = new Set(Array.from({ length: 12 }, (_, k) => 300 + k));
  const ihsg = ticker('IHSG', 11, ALL, true);
  const stocks = [ticker('AAAA', 21, ALL), ticker('BBBB', 22, ALL), ticker('SUSP', 23, ALL.filter((_, k) => !skip.has(k)))];
  return { ihsg, stocks, rows: Object.fromEntries(stocks.map((t, k) => [t.ticker, brokerRows(t, 31 + k)])) as Record<string, Row[]> };
}

/** The first `n` sessions of a ticker (the data cut at its session n-1). */
export function head(t: Ticker, n: number): Ticker {
  const k = Math.min(n, t.dates.length), cut = <T,>(a: ArrayLike<T>) => Array.from(a).slice(0, k);
  return { ticker: t.ticker, dates: t.dates.slice(0, k), bars: { O: cut(t.bars.O), H: cut(t.bars.H), L: cut(t.bars.L), C: cut(t.bars.C), V: cut(t.bars.V), T: t.dates.slice(0, k) } as Ticker['bars'] };
}
