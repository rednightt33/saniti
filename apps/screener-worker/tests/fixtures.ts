/* Snapshot inputs for the tests: files in the publisher's format (tests/fake-terminal.mjs) decoded by the backtest core
   as the builder thread decodes them, and a small market with the cases the rules name: a short history (74 bars,
   RANS), a flat window, IHSG without volume, a stock that stopped trading before E (stale). */
import { inflateVerified } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { Columnar } from '../../edge-bff/backtest/src/core/datafile.ts';
import { tailLength } from '../../edge-bff/screener/src/core/metrics.ts';
import type { TickerReference } from '../../backtest-worker/src/terminal.ts';
import { classification } from '../../backtest-worker/src/terminal.ts';
import type { BuildInput, PublicationState } from '../src/snapshot.ts';
import { encode, tickersRef } from '../../backtest-worker/tests/fake-terminal.mjs';
import { universe, walk, xsectionActionsDoc, xsectionPriceDoc } from './fake-terminal.mjs';

export const CAP = 10000, WITHIN = 130;
export const decode = async (doc: object): Promise<Columnar> => { const { body, sha256 } = encode(doc); return inflateVerified(new Uint8Array(body), { sha256, bytes: body.length }) };
/** The reference file as TerminalClient.reference reads it (groups through terminal.ts classification). */
export const refOf = (rows: unknown[][]): TickerReference => {
  const doc = tickersRef(rows) as unknown as Record<string, unknown[]>, groupings = ['sector', 'industry'];
  return { groupings, tickers: (doc.ticker as string[]).map((t, i) => ({ ticker: t, name: doc.name[i] as string, type: doc.type[i] as string, groups: { sector: classification(doc.sector[i]), industry: classification(doc.industry[i]) } })) };
};
export const state = (over: Partial<PublicationState> = {}): PublicationState => ({ finished_at: '2026-10-27T13:03:23Z', price_through: '2026-10-27', broker_through: null, broker_behind_sessions: 0, xsection: null, ...over });
export async function input(prices: Record<string, unknown[][]>, ref: unknown[][], actions: unknown[][] = [], over: Partial<BuildInput> = {}): Promise<BuildInput> {
  return { price: await decode(xsectionPriceDoc(prices)), actions: await decode(xsectionActionsDoc(actions)), ref: refOf(ref), state: state(),
    engine: { screener_engine: 'e'.repeat(16), registry: 'r'.repeat(16), screener_registry: 's'.repeat(16) }, tailLength: tailLength(WITHIN), capBudgetMs: CAP, withinMax: WITHIN, presets: [], ...over };
}
export function market() {
  const u = universe(5, 320);
  u.prices.SHORT = walk(3, 74);
  u.prices.FLAT = walk(4, 300).map(([d]: unknown[], i: number) => [d, 500, 500, 500, 500, i % 2 ? 0 : 1000]);
  u.prices.STALE = walk(5, 300, { last: '2026-08-21' });
  u.ref.push(['SHORT', 'Short history', 'stock', 'Energy', 'Coal'], ['FLAT', 'Flat', 'stock', 'Undefined', 'Undefined'], ['STALE', 'Stale', 'stock', 'Energy', 'Coal']);
  return u;
}
