/* The flow fixture of the core's flow tests (EXEC-SCREENER-FLOW-CANDLES P5a, P5b; tests/core/flow.test.ts,
   flow-screener.test.ts, old-formulas.test.ts): several stocks over a 60-session broker window in P4's store layout (per
   ticker, rows ordered by date then broker, investor type and board; investor types Domestic=0, Foreign=1; boards
   Regular, Nego, Tunai), with a Nego-only day, a broker day without a price bar, a stock without broker data and price
   bars after the last broker day, and the Terminal's way of computing a flow value on the same rows (flow.ts flowRows
   on the rows as objects, the Terminal's context, the anchor and Broker Inventory's start at the first candle). */
import { flowRows } from '../../../terminal/src/calc/flow.ts';
import type { FlowContext } from '../../../terminal/src/calc/flow.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { FLOW_BY_ID } from '../../src/core/flowmetrics.ts';
import type { BrokerRowsLike, FlowBindContext, TickerFlow } from '../../src/core/flowmetrics.ts';
import type { TickerBars } from '../../src/core/metrics.ts';
import { rng, synth } from './helpers.ts';

/* ---- the fixture ---------------------------------------------------------------------------------------------- */

export const BROKERS = ['AK', 'BK', 'CC', 'DX', 'KK', 'LG', 'MG', 'NI', 'PD', 'RX', 'XC', 'XL', 'YP', 'ZP'];
export const INVESTORS = ['Domestic', 'Foreign'] as const, BOARDS = ['Regular', 'Nego', 'Tunai'] as const;   // the P4 file's tables
export const CLASS: Record<string, string> = Object.fromEntries(BROKERS.map((b, k) => [b, k % 3 === 0 ? 'Institutional-heavy' : k % 3 === 1 ? 'Retail-heavy' : 'Mixed']));
export const PRICE_BARS = 84, LEAD = 22;                  // 84 weekday bars: 22 before the window, 60 in it, 2 after it
export const MARKET = synth('MKT', 1, PRICE_BARS, '2026-07-01').dates as string[];
export const WINDOW = MARKET.slice(LEAD, LEAD + 60);      // the 60 loaded broker dates
export const FIRST = WINDOW[0], LAST = WINDOW[59];
export const FLOW_CTX: FlowBindContext = { sessions: 60, first: FIRST, last: LAST, complete: true, classification: true };
export const E = MARKET[PRICE_BARS - 1];                  // price_through: two sessions after the last broker day

export interface Row { d: string; b: string; i: string; m: string; bv: number; sv: number; bl: number; sl: number; bf: number | null; sf: number | null }
/** Deterministic broker rows of one stock on its broker dates: 6 to 10 brokers, both investor types, the Regular board
    and now and then Nego and Tunai, whole and odd lots, a missing transaction count now and then. `negoOnly`: that date
    holds Nego rows only. */
export function rowsOf(seed: number, dates: readonly string[], negoOnly?: string): Row[] {
  const r = rng(seed), out: Row[] = [];
  for (const d of dates) {
    const n = 6 + Math.floor(r() * 5), picked = [...BROKERS].sort(() => r() - 0.5).slice(0, n);
    for (const b of picked) for (const i of INVESTORS) {
      const boards = d === negoOnly ? ['Nego'] : r() < 0.25 ? ['Regular', 'Nego'] : r() < 0.1 ? ['Regular', 'Tunai'] : ['Regular'];
      for (const m of boards) {
        const bl = r() < 0.2 ? Math.round(r() * 5e4) / 100 : Math.round(r() * 5e3), sl = r() < 0.2 ? Math.round(r() * 5e4) / 100 : Math.round(r() * 5e3);
        const px = 900 + 200 * r();
        out.push({ d, b, i, m, bv: Math.round(bl * 100 * px), sv: Math.round(sl * 100 * (px + 10 * r())), bl, sl,
          bf: r() < 0.03 ? null : 1 + Math.floor(r() * 300), sf: r() < 0.03 ? null : 1 + Math.floor(r() * 300) });
      }
    }
  }
  return out;
}
/** P4's store for one ticker (broker.ts BrokerRows): every row of the window's dates, ordered by date, then broker,
    investor type and board in text order (the files' primary key order); D into WINDOW, B into the union of brokers. */
export function storeOf(rows: readonly Row[]): BrokerRowsLike {
  const sorted = [...rows].sort((x, y) => x.d < y.d ? -1 : x.d > y.d ? 1 : x.b < y.b ? -1 : x.b > y.b ? 1 : x.i < y.i ? -1 : x.i > y.i ? 1 : x.m < y.m ? -1 : x.m > y.m ? 1 : 0);
  const brokers = [...BROKERS].sort(), nan = (v: number | null) => v === null ? NaN : v;
  return {
    rows: sorted.length, dates: WINDOW, brokers, investor_types: INVESTORS, boards: BOARDS,
    D: Uint16Array.from(sorted, x => WINDOW.indexOf(x.d)), B: Uint16Array.from(sorted, x => brokers.indexOf(x.b)),
    I: Uint8Array.from(sorted, x => INVESTORS.indexOf(x.i as never)), M: Uint8Array.from(sorted, x => BOARDS.indexOf(x.m as never)),
    BV: Float64Array.from(sorted, x => x.bv), SV: Float64Array.from(sorted, x => x.sv), BL: Float64Array.from(sorted, x => x.bl), SL: Float64Array.from(sorted, x => x.sl),
    BF: Float64Array.from(sorted, x => nan(x.bf)), SF: Float64Array.from(sorted, x => nan(x.sf)),
  };
}
/** A stock's price bars without the bars of `drop` (a broker day without a price bar). */
export function without(t: TickerBars, drop: readonly string[]): TickerBars {
  const keep = t.dates.map((d, k) => drop.includes(d) ? -1 : k).filter(k => k >= 0), cut = (a: ArrayLike<unknown>) => keep.map(k => a[k]) as any;
  return { ticker: t.ticker, dates: keep.map(k => t.dates[k]), bars: { O: cut(t.bars.O), H: cut(t.bars.H), L: cut(t.bars.L), C: cut(t.bars.C), V: cut(t.bars.V), T: keep.map(k => t.dates[k]) } };
}
export interface Stock { t: TickerBars; rows: Row[]; store: BrokerRowsLike }
export const PK = (x: Row, y: Row) => x.d < y.d ? -1 : x.d > y.d ? 1 : x.b < y.b ? -1 : x.b > y.b ? 1 : x.i < y.i ? -1 : x.i > y.i ? 1 : x.m < y.m ? -1 : x.m > y.m ? 1 : 0;
/** A stock: its price bars (without `drop`), its broker rows in the files' order (date, then the primary key: broker,
    investor type, board) as the Terminal's files and the Screener's store hold them, and the store. */
export const stock = (ticker: string, seed: number, unsorted: Row[], drop: string[] = []): Stock => {
  const rows = [...unsorted].sort(PK);
  const t = without(synth(ticker, seed, PRICE_BARS, '2026-07-01'), drop), store = storeOf(rows);
  const flow: TickerFlow = { first: FIRST, last: LAST, rows: () => store, classification: CLASS, memo: new Map() };
  return { t: { ...t, flow }, rows, store };
};
/** AAAA: every window date; BBBB: broker rows on its last broker day, which has no price bar; CCCC: a Nego-only day;
    DDDD: no broker data; EEEE: broker data on the last 30 dates only. */
export const NEGO_DAY = WINDOW[37];
export const STOCKS: Record<string, Stock> = {
  AAAA: stock('AAAA', 11, rowsOf(101, WINDOW)),
  BBBB: stock('BBBB', 12, rowsOf(102, WINDOW), [LAST]),
  CCCC: stock('CCCC', 13, rowsOf(103, WINDOW, NEGO_DAY)),
  DDDD: stock('DDDD', 14, []),
  EEEE: stock('EEEE', 15, rowsOf(105, WINDOW.slice(30))),
};
export const WITH_DATA = ['AAAA', 'BBBB', 'CCCC', 'EEEE'];

/** The Terminal's way: flow.ts flowRows on the rows as objects (names, a missing count null), the candles the stock's
    price bars inside the window, its context, and the anchor and start of the first visible candle. */
export function terminal(s: Stock): { ctx: FlowContext; lo: number; candles: string[] } {
  const D = s.t.dates, lo = D.findIndex(d => d >= FIRST), candles = D.filter(d => d >= FIRST && d <= LAST) as string[];
  const at = new Map(candles.map((d, k) => [d, k]));
  const rows = flowRows(s.rows, candles.length, d => at.get(d) ?? -1);
  const num = (x: unknown) => typeof x === 'number' && Number.isFinite(x) ? x : null;
  const close = candles.map((_, k) => num(s.t.bars.C[lo + k])), volume = candles.map((_, k) => num(s.t.bars.V[lo + k]));
  return { ctx: { rows, dates: candles, close, volume, insider: [], classification: CLASS }, lo, candles };
}
export const terminalParams = (id: string, p: Record<string, unknown>, first: string) => {
  const q: Record<string, unknown> = { ...p };
  for (const k of Object.keys(q)) if (FLOW_BY_ID[id].params.find(x => x.key === k)?.kind === 'date' && q[k] === 'view') q[k] = first;
  if (id === 'FL23') q.start = first;
  return q;
};
export const code = (f: () => unknown) => { try { f(); return null } catch (e) { const x = e as ScreenerError; return { code: x.code, field: x.field, message: x.message, details: x.details } } };
export const same = (a: ArrayLike<unknown>, b: ArrayLike<unknown>) => a.length === b.length && Array.from(a).every((v, k) => Object.is(v, b[k]));
