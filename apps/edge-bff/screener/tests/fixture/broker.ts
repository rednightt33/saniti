/* FIXTURE ONLY (never in the production bundle; tests/bundle checks it): broker rows for the prototype's synthetic
   market (data.ts: each ticker's sample broker nets, traded value and closes), in the shape of the worker's broker store
   (P4 BrokerRows, core flowmetrics.ts BrokerRowsLike), so the page can show and smoke-test flow conditions
   (EXEC-SCREENER-FLOW-CANDLES P5c) without the worker. The flow values themselves are the core's: the fixture engine
   computes them with flowmetrics.ts (the Terminal's flow.ts), never a formula here. Sample data, not market data.
   The window is the 60 sessions that end one session before the last price day, so a flow value is a session older
   than the prices (its broker data date is shown); MTDL has no broker data (n/a). */
import type { BrokerRowsLike, FlowBindContext, TickerFlow } from '../../src/core/flowmetrics.ts';
import { BROKERS, DAYS, T } from './data.ts';

export const BROKER_SESSIONS = 60;
/** the loaded broker dates: the 60 sessions before the last price day */
export const BROKER_DAYS: string[] = DAYS.slice(DAYS.length - 1 - BROKER_SESSIONS, DAYS.length - 1);
export const BROKER_WINDOW = { first: BROKER_DAYS[0], last: BROKER_DAYS[BROKER_DAYS.length - 1], sessions: BROKER_SESSIONS, complete: true };
export const FLOW_CTX: FlowBindContext = { ...BROKER_WINDOW, classification: true };
/** stocks without broker data in the window */
export const NO_BROKER_DATA = new Set(['MTDL']);

const CODES: string[] = BROKERS.map((b: any[]) => String(b[0]));
const SORTED = [...CODES].sort();
/** the brokers' classification (the reference file `brokers`): the foreign houses institutional, the others retail */
export const CLASSIFICATION: Record<string, string> = Object.fromEntries(BROKERS.map((b: any[]) => [String(b[0]), b[2] ? 'Institutional-heavy' : 'Retail-heavy']));
const INVESTORS = ['Domestic', 'Foreign'], BOARDS = ['Regular', 'Nego', 'Tunai'];

const stores = new Map<string, BrokerRowsLike>();
/** One ticker's rows: per broker and session one Regular row (Foreign for the foreign houses, else Domestic) whose buy
    minus sell value is the sample net, and now and then a Nego row; lots at the close, transaction counts from the lots. */
export function brokerRows(ticker: string, dates: readonly string[]): BrokerRowsLike {
  const hit = stores.get(ticker); if (hit) return hit;
  const t = T[ticker], at = new Map(DAYS.map((d, i) => [d, i])), have = new Set(dates);
  const D: number[] = [], B: number[] = [], I: number[] = [], M: number[] = [], BV: number[] = [], SV: number[] = [], BL: number[] = [], SL: number[] = [], BF: number[] = [], SF: number[] = [];
  if (t && !NO_BROKER_DATA.has(ticker)) BROKER_DAYS.forEach((d, k) => {
    const i = at.get(d)!; if (!have.has(d)) return;                // a stale stock: no rows after its last session
    const px = t.c[i] || 1;
    for (const code of SORTED) {
      const j = CODES.indexOf(code), foreign = !!BROKERS[j][2], net = t.net[j][i] as number, g = (t.val[i] as number) * (foreign ? 0.06 : 0.04);
      const boards = (j + k) % 11 === 0 ? [0, 1] : [0];
      for (const m of boards) {
        const part = m === 0 ? 1 : 0.25, bv = (g + Math.max(net, 0)) * part, sv = (g + Math.max(-net, 0)) * part;
        const bl = Math.round(bv / (px * 100)), sl = Math.round(sv / (px * 100));
        D.push(k); B.push(SORTED.indexOf(code)); I.push(foreign ? 1 : 0); M.push(m);
        BV.push(Math.round(bv)); SV.push(Math.round(sv)); BL.push(bl); SL.push(sl); BF.push(Math.max(1, Math.round(bl / 40))); SF.push(Math.max(1, Math.round(sl / 40)));
      }
    }
  });
  const s: BrokerRowsLike = { rows: D.length, dates: BROKER_DAYS, brokers: SORTED, investor_types: INVESTORS, boards: BOARDS,
    D: Uint16Array.from(D), B: Uint16Array.from(B), I: Uint8Array.from(I), M: Uint8Array.from(M),
    BV: Float64Array.from(BV), SV: Float64Array.from(SV), BL: Float64Array.from(BL), SL: Float64Array.from(SL), BF: Float64Array.from(BF), SF: Float64Array.from(SF) };
  stores.set(ticker, s);
  return s;
}
const flows = new Map<string, TickerFlow>();
/** the ticker's broker data as the core's series path reads it (metrics.ts TickerBars.flow) */
export function tickerFlow(ticker: string, dates: readonly string[]): TickerFlow {
  let f = flows.get(ticker);
  if (!f) { f = { first: BROKER_WINDOW.first, last: BROKER_WINDOW.last, rows: () => brokerRows(ticker, dates), classification: CLASSIFICATION, memo: new Map() }; flows.set(ticker, f) }
  return f;
}
