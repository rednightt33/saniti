/* The flow cost benchmark's market (verification/screener/BENCHMARK_FLOW_COST.md; QA unit B, QA4's harness): 900 stocks
   with 300 price bars and 60 broker days of about 25,000 rows each (the publisher's real size: about 24,500 rows a day,
   1.47 M in the window, P4_BROKER_DAYS.md), the first 100 stocks traded by 50 to 100 of 100 brokers, the other 800 by 2
   to 5; both investor types; a fifth of the broker pairs on Nego too; deterministic (xorshift seed 12345). LARGE are the
   100 stocks with many brokers, SMALL the 800 others. */
import { universe } from '../fake-terminal.mjs';

export const N_STOCKS = 900, N_LARGE = 100;
export const U0 = universe(N_STOCKS, 300);
const all = U0.prices.IHSG.map((r: unknown[]) => r[0] as string);
export const DAYS: string[] = all.slice(-62, -2);
let seed = 12345;
const rnd = () => { seed ^= seed << 13; seed >>>= 0; seed ^= seed >>> 17; seed ^= seed << 5; seed >>>= 0; return seed / 4294967296 };
const CODES = Array.from({ length: 100 }, (_, k) => String.fromCharCode(65 + (k / 26 | 0)) + String.fromCharCode(65 + k % 26));
export const CLASSES = CODES.map((c, k) => [c, 'ABCDYZ'[k % 6], k % 5 === 0 ? 'Foreign' : 'Local', ['Institutional-heavy', 'Retail-heavy', 'Mixed'][k % 3]]);
export const TICKERS = Array.from({ length: N_STOCKS }, (_, k) => `T${String(k).padStart(3, '0')}`);
export const LARGE = TICKERS.slice(0, N_LARGE), SMALL = TICKERS.slice(N_LARGE);
function day(): unknown[][] {
  const rows: unknown[][] = [];
  for (let k = 0; k < N_STOCKS; k++) {
    const t = TICKERS[k], nb = k < N_LARGE ? 50 + Math.floor(rnd() * 51) : 2 + Math.floor(rnd() * 4);
    const picked = [...CODES].sort(() => rnd() - 0.5).slice(0, nb).sort();
    for (const b of picked) for (const i of ['Domestic', 'Foreign']) for (const m of (rnd() < 0.2 ? ['Nego', 'Regular'] : ['Regular'])) {
      const bl = Math.round(rnd() * 1e4), sl = Math.round(rnd() * 1e4);
      rows.push([t, b, i, m, Math.round(bl * 100 * (500 + rnd() * 100)), Math.round(sl * 100 * (500 + rnd() * 100)), bl, sl, Math.round(rnd() * 300), Math.round(rnd() * 300), false]);
    }
  }
  return rows;
}
export const BROKER: Record<string, unknown[][]> = {};
for (const d of DAYS) BROKER[d] = day();
