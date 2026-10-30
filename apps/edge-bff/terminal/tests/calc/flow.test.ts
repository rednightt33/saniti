// EXEC-TERMINAL-FLOW-IND (user go 2026-10-30): the Flow indicators against hand-computed values, the spreadsheet's own
// illustrations (FLOW_INDICATORS_SPEC.xlsx, column "Example Illustration") and the conventions of FORMULAS.md.
import { describe, expect, it } from 'vitest';
import { above, atLeast, atMost, computeFlow, defaultInventoryBrokers, flowRows, percentile, type FlowContext } from '../../src/calc/flow';
import REG from '../../src/data/flowRegistry.json';

type Row = { d: string; b: string; i: string; m: string; bv: number; sv: number; bl: number; sl: number; bf?: number | null; sf?: number | null };
const r = (d: string, b: string, bv: number, sv: number, bl: number, sl: number, bf: number | null = 1, sf: number | null = 1, i = 'Domestic', m = 'Regular'): Row =>
  ({ d, b, i, m, bv, sv, bl, sl, bf, sf });
function ctx(rows: Row[], dates: string[], extra: Partial<FlowContext> = {}): FlowContext {
  const at = new Map(dates.map((d, k) => [d, k]));
  return { rows:flowRows(rows, dates.length, d => at.get(d) ?? -1), dates, close:dates.map(() => 100), volume:dates.map(() => 1000),
    insider:[], classification:{}, ...extra };
}
const D = ['2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08', '2026-01-09'];
const near = (a: number | null, b: number) => { expect(a).not.toBeNull(); expect(a!).toBeCloseTo(b, 9) };

describe('registry', () => {
  it('has one function per indicator of the agreed spreadsheet (39), with its outputs', () => {
    const ids = (REG as any).indicators.map((i: any) => i.id);
    expect(ids).toEqual(Array.from({ length:39 }, (_, k) => `FL${String(k + 1).padStart(2, '0')}`));
    const c = ctx([r(D[0], 'AA', 100, 0, 1, 0)], D);
    for (const ind of (REG as any).indicators) {
      const p = Object.fromEntries(ind.params.filter((q: any) => q.default !== undefined).map((q: any) => [q.key, q.default]));
      expect(Object.keys(computeFlow(ind.id, c, p)).length, ind.id).toBeGreaterThan(0);
    }
  });
});

describe('transaction size and shares', () => {
  // spreadsheet #1: "Buy 2,000,000 shares melalui 500 transaksi = 4,000 shares/trade" = 20,000 lots / 500 = 40 lots
  const rows = [r(D[0], 'AA', 2.4e9, 0, 20000, 0, 500, 0), r(D[0], 'BB', 0, 6e8, 0, 5000, 0, 500), r(D[0], 'CC', 1e8, 1e8, 1000, 1000, 100, 100)];
  const c = ctx(rows, D);
  it('FL01 lots per buy transaction of the Top-1 net buyer, and the sell side of a chosen broker', () => {
    near(computeFlow('FL01', c, { scope:'topn', top:1, rank:'net_buy', window:1, side:'buy' }).buy[0], 40);
    near(computeFlow('FL01', c, { scope:'selected', brokers:['BB'], window:1, side:'sell' }).sell[0], 10);
    expect(computeFlow('FL01', c, { scope:'topn', top:1, window:1, side:'both' })).toHaveProperty('sell');
  });
  it('FL02 rupiah per transaction (#3: Rp2.4bn / 500 = Rp4.8mn)', () => {
    near(computeFlow('FL02', c, { scope:'selected', brokers:['AA'], window:1, side:'buy' }).buy[0], 4.8e6);
  });
  it('FL03 / FL04 / FL05: share of lots, of transactions, and their ratio (#9: 20% / 5% = 4.0x)', () => {
    const b = [r(D[0], 'AA', 0, 0, 2000, 0, 50, 0), r(D[0], 'ZZ', 0, 0, 8000, 0, 950, 0)];
    const c2 = ctx(b, D), p = { scope:'selected', brokers:['AA'], window:1, side:'buy' };
    near(computeFlow('FL03', c2, p).buy[0], 20);
    near(computeFlow('FL04', c2, p).buy[0], 5);
    near(computeFlow('FL05', c2, p).buy[0], 4);
  });
  it('FL06 buy over sell lots per transaction (#11: 4,000 vs 1,000 = 4.0x) and FL10 the transaction imbalance', () => {
    const c2 = ctx([r(D[0], 'AA', 0, 0, 40, 10, 1, 1)], D), p = { scope:'selected', brokers:['AA'], window:1 };
    near(computeFlow('FL06', c2, p).ratio[0], 4);
    const c3 = ctx([r(D[0], 'AA', 0, 0, 1, 1, 30, 10)], D);
    near(computeFlow('FL10', c3, p).value[0], 0.5);
  });
  it('FL07 against the board volume of every investor by default, or of the filter', () => {
    const c2 = ctx([r(D[0], 'AA', 0, 0, 2000, 0, 1, 0, 'Foreign'), r(D[0], 'BB', 0, 0, 10000, 0, 1, 0, 'Domestic')], D);
    const p = { scope:'all', window:1, investors:['Foreign'] };
    near(computeFlow('FL07', c2, { ...p, denom:'board' }).value[0], 2000 / 12000 * 100);
    near(computeFlow('FL07', c2, { ...p, denom:'filter' }).value[0], 100);
  });
  it('a row without a transaction count makes the frequency figures null, never a guess', () => {
    const c2 = ctx([r(D[0], 'AA', 100, 0, 10, 0, null, null)], D);
    expect(computeFlow('FL01', c2, { scope:'all', window:1, side:'buy' }).buy[0]).toBeNull();
    near(computeFlow('FL03', c2, { scope:'all', window:1, side:'buy' }).buy[0], 100);
  });
});

describe('cohort, window and missing candles', () => {
  it('re-ranks Top-N on every candle over the window ending there', () => {
    const rows = [r(D[0], 'AA', 100, 0, 1, 0), r(D[0], 'BB', 50, 0, 1, 0), r(D[1], 'AA', 0, 10, 0, 1), r(D[1], 'BB', 80, 0, 1, 0)];
    const v = computeFlow('FL11', ctx(rows, D), { scope:'topn', top:1, rank:'net_buy', window:1 }).value;
    near(v[0], 100 / 150 * 100);                    // AA on day 1
    near(v[1], 80 / 80 * 100);                      // BB on day 2
  });
  it('gives null on a candle without broker data and before a full window, never 0', () => {
    const rows = [r(D[0], 'AA', 100, 0, 1, 0), r(D[2], 'AA', 100, 0, 1, 0), r(D[3], 'AA', 100, 0, 1, 0)];
    const v = computeFlow('FL11', ctx(rows, D), { scope:'all', window:2 }).value;
    expect(v).toEqual([null, null, 100, 100, null]);
  });
  it('the board and investor filter apply to the cohort and the sums', () => {
    const rows = [r(D[0], 'AA', 100, 0, 1, 0, 1, 1, 'Foreign', 'Nego'), r(D[0], 'AA', 300, 0, 3, 0, 1, 1, 'Foreign', 'Regular')];
    near(computeFlow('FL03', ctx(rows, D), { scope:'all', window:1, boards:['Nego'], side:'buy' }).buy[0], 100);
  });
});

describe('concentration and breadth', () => {
  const four = (vals: number[]) => vals.map((v, k) => r(D[0], 'B' + k, v, 0, v, 0));
  it('FL13 HHI of buy lots (#18: 40/30/20/10 = 0.30) and FL15 the Top-2 share (#21: 70%)', () => {
    const c = ctx(four([40, 30, 20, 10]), D);
    near(computeFlow('FL13', c, { window:1, side:'buy' }).buy[0], 0.30);
    near(computeFlow('FL15', c, { window:1, top:2 }).value[0], 70);
  });
  it('FL16 Top-2 of the positive net buys (#22: Rp7bn of Rp10bn = 70%) and FL38 their HHI', () => {
    const c = ctx([r(D[0], 'A', 4e9, 0, 1, 0), r(D[0], 'B', 3e9, 0, 1, 0), r(D[0], 'C', 3e9, 0, 1, 0), r(D[0], 'D', 0, 5e9, 0, 1)], D);
    near(computeFlow('FL16', c, { window:1, top:2 }).value[0], 70);
    near(computeFlow('FL38', c, { window:1 }).value[0], 0.16 + 0.09 + 0.09);
  });
  it('FL22 counts a broker with zero net as active (D10: XL +100, BK -50, CC 0, DR none = 33.3%)', () => {
    const c = ctx([r(D[0], 'XL', 100, 0, 1, 0), r(D[0], 'BK', 0, 50, 0, 1), r(D[0], 'CC', 30, 30, 1, 1)], D);
    near(computeFlow('FL22', c, { window:1 }).value[0], 100 / 3);
  });
});

describe('bandar balance', () => {
  // Top 3 buyers +30 (20, 6, 4), Top 3 sellers -20 (10, 6, 4); G bought and sold 10 (net 0); traded value = total buy 40
  const rows = [r(D[0], 'A', 20, 0, 1, 0), r(D[0], 'B', 6, 0, 1, 0), r(D[0], 'C', 4, 0, 1, 0), r(D[0], 'D', 0, 10, 0, 1),
    r(D[0], 'E', 0, 6, 0, 1), r(D[0], 'F', 0, 4, 0, 1), r(D[0], 'G', 10, 10, 1, 1)];
  const c = ctx(rows, D);
  it('FL25 is the buyers net plus the sellers net, FL24 that over the traded value', () => {
    expect(computeFlow('FL25', c, { top:3, window:1 }).value[0]).toBe(30 - 20);
    near(computeFlow('FL24', c, { top:3, window:1 }).value[0], 100 * 10 / 40);
  });
  it('FL29 counts the candles whose own balance is above the threshold', () => {
    const rows2 = [r(D[0], 'A', 10, 0, 1, 0), r(D[0], 'B', 0, 5, 0, 1), r(D[1], 'A', 0, 10, 0, 1), r(D[1], 'B', 5, 0, 1, 0)];
    near(computeFlow('FL29', ctx(rows2, D), { top:1, window:2, threshold:0 }).value[1], 50);
  });
});

describe('cost basis', () => {
  // #24/#26: 1mn shares @ Rp2,400 then 2mn @ Rp2,500 -> Rp2,466.7; then 1mn sold -> the cost stays Rp2,466.7
  const rows = [r(D[0], 'AA', 2.4e9, 0, 10000, 0), r(D[1], 'AA', 5e9, 0, 20000, 0), r(D[2], 'AA', 0, 2.6e9, 0, 10000)];
  const c = ctx(rows, D, { close:[2400, 2500, 2550, 2550, 2550] });
  const p = { scope:'selected', brokers:['AA'], anchor:D[0] };
  it('FL18 anchored buy VWAP and FL17 the rolling one', () => {
    near(computeFlow('FL18', c, p).value[1], 7.4e9 / 3e6);
    near(computeFlow('FL17', c, { ...p, window:2 }).value[1], 7.4e9 / 3e6);
  });
  it('FL19 keeps the average cost when inventory is sold, FL20 the distance of the close (#27: +3.38%)', () => {
    const v = computeFlow('FL19', c, p).value;
    near(v[1], 7.4e9 / 3e6); near(v[2], 7.4e9 / 3e6);
    near(computeFlow('FL20', c, p).value[2], 100 * (2550 / (7.4e9 / 3e6) - 1));
  });
  it('FL19 has no cost while the modelled inventory is 0 or less', () => {
    const c2 = ctx([r(D[0], 'AA', 0, 1e6, 0, 10)], D);
    expect(computeFlow('FL19', c2, p).value[0]).toBeNull();
  });
  it('FL18 freezes the Top-N from the anchor to the last candle', () => {
    const rows2 = [r(D[0], 'AA', 100, 0, 1, 0), r(D[0], 'BB', 50, 0, 1, 0), r(D[1], 'BB', 200, 0, 1, 0)];
    near(computeFlow('FL18', ctx(rows2, D), { scope:'topn', top:1, rank:'net_buy', anchor:D[0] }).value[0], 50 / 100);
  });
});

describe('streaks, persistence, spikes and percentiles', () => {
  it('FL26 counts consecutive net buying (+) or selling (-) days, capped at the limit', () => {
    const rows = [r(D[0], 'A', 10, 0, 1, 0), r(D[1], 'A', 10, 0, 1, 0), r(D[2], 'A', 0, 5, 0, 1), r(D[3], 'A', 0, 5, 0, 1), r(D[4], 'A', 1, 1, 1, 1)];
    const all = ['Foreign', 'Domestic'];          // FL26's agreed default investor is Foreign; these rows are Domestic
    expect(computeFlow('FL26', ctx(rows, D), { scope:'all', window:60, investors:all }).value).toEqual([1, 2, -1, -2, 0]);
    expect(computeFlow('FL26', ctx(rows, D), { scope:'all', window:1, investors:all }).value.slice(0, 2)).toEqual([1, 1]);
    // a parameter left out takes the registry default (Reviewer A, A4: without `scope` FL26 ranked a Top-3 cohort)
    expect(computeFlow('FL26', ctx(rows, D), { window:60, investors:all }).value).toEqual([1, 2, -1, -2, 0]);
    // the default Foreign filter on Domestic rows: the candles have data but no net, so the streak is 0 (not null)
    expect(computeFlow('FL26', ctx(rows, D), { scope:'all', window:60 }).value).toEqual([0, 0, 0, 0, 0]);
  });
  it('FL12 the share of window days the cohort bought (#17: 4 of 5 = 80%)', () => {
    const rows = [0, 1, 2, 3].map(k => r(D[k], 'A', 10, 0, 1, 0)).concat([r(D[4], 'A', 0, 1, 0, 1), r(D[4], 'B', 0, 0, 1, 1)]);
    near(computeFlow('FL12', ctx(rows, D), { scope:'all', window:5 }).value[4], 80);
  });
  it('FL32 today\'s transactions over the mean of the baseline before it', () => {
    const rows = [r(D[0], 'A', 1, 0, 1, 0, 10, 0), r(D[1], 'A', 1, 0, 1, 0, 30, 0), r(D[2], 'A', 1, 0, 1, 0, 60, 0)];
    near(computeFlow('FL32', ctx(rows, D), { baseline:2 }).value[2], 60 / 20);
  });
  it('the mid-rank percentile uses only earlier values', () => {
    expect(percentile([1, 2, 3, 2], 3)).toEqual([null, null, null, 100 * (1 + 0.5) / 3]);
  });
  it('FL31 adds insider buys and subtracts sells within the window', () => {
    const c = ctx([r(D[0], 'A', 1, 0, 1, 0)], D, { insider:[{ t:1, value:5e9 }, { t:2, value:-2e9 }] });
    expect(computeFlow('FL31', c, { window:2 }).value).toEqual([null, 5e9, 3e9, -2e9, 0]);
  });
});

describe('Broker Inventory and the classification lists', () => {
  const rows = [r(D[0], 'AA', 0, 0, 10, 0), r(D[1], 'AA', 0, 0, 0, 4), r(D[0], 'BB', 0, 0, 5, 0)];
  it('FL23 cumulative lots per broker from the start candle, and the cohort total', () => {
    const o = computeFlow('FL23', ctx(rows, D), { brokers:['AA', 'BB'], unit:'lot', view:'cum', total:true, start:D[0] });
    expect(o.AA.slice(0, 2)).toEqual([10, 6]); expect(o.total.slice(0, 2)).toEqual([15, 11]);
  });
  it('FL23 defaults to the three largest net buyers of the last 20 candles', () => {
    const c = ctx([r(D[0], 'A', 30, 0, 1, 0), r(D[0], 'B', 20, 0, 1, 0), r(D[0], 'C', 10, 0, 1, 0), r(D[0], 'D', 5, 0, 1, 0)], D);
    expect(defaultInventoryBrokers(c.rows)).toEqual(['A', 'B', 'C']);
  });
  it('FL34 institutional minus retail net over the traded value; a broker in both lists gives nothing', () => {
    const c = ctx([r(D[0], 'II', 60, 0, 1, 0), r(D[0], 'RR', 0, 40, 0, 1), r(D[0], 'XX', 40, 60, 1, 1)], D,
      { classification:{ II:'Institutional-heavy', RR:'Retail-heavy', XX:'Mixed' } });
    near(computeFlow('FL34', c, { window:1, inst:'class:Institutional-heavy', retail:'class:Retail-heavy' }).value[0], 100 * (60 + 40) / 100);
    expect(computeFlow('FL34', c, { window:1, inst:['II'], retail:['II'] }).value[0]).toBeNull();
    // the classification has not arrived (no list at all): no value, not a 0
    const bare = ctx([r(D[0], 'II', 100, 40, 1, 1)], D);
    expect(computeFlow('FL34', bare, { window:1, inst:'class:Institutional-heavy', retail:'class:Retail-heavy' }).value[0]).toBeNull();
  });
});

// Found by the oracle comparison of 2026-10-30 (verification/terminal_api/flow_indicators/oracle_compare.ts): the class of
// each defect, on a case other than the one observed.
describe('exact sums and thresholds', () => {
  it('a one-candle sum stays exact after a large running total with fractions (lots: odd lots, adjusted lots)', () => {
    const dates = Array.from({ length:400 }, (_, k) => new Date(Date.UTC(2020, 0, 1 + k)).toISOString().slice(0, 10));
    const rows = dates.map((d, k) => r(d, 'AA', 1e12, 0, k < 399 ? 123456789.37 : 0.26, 0, 1, 0));
    const c = ctx(rows, dates);
    expect(computeFlow('FL01', c, { scope:'selected', brokers:['AA'], window:1, side:'buy' }).buy[399]).toBe(0.26);
    expect(computeFlow('FL17', c, { scope:'selected', brokers:['AA'], window:1 }).value[399]).toBe(1e12 / 26);
  });
  it('a value equal to the threshold in exact arithmetic passes >= and <=, and fails >', () => {
    const move = 100 * Math.abs(1030 / 1000 - 1);                     // 3.0000000000000027 in floating point
    expect(move > 3).toBe(true);
    expect(atMost(move, 3)).toBe(true);
    expect(atLeast(100 * (0.7 / 0.1 / 7), 100)).toBe(true);           // 99.99999999999999
    expect(above(100 + 1e-13, 100)).toBe(false);
    expect(above(100.001, 100)).toBe(true);
    expect(above(1e-20, 0)).toBe(true);                                // a threshold of 0 stays exact
    expect(atLeast(-1e-20, 0)).toBe(false);
  });
  it('FL27 counts a move of exactly the maximum as quiet (DAYA 2025-10-02: 1000 -> 1030, max 3%)', () => {
    const dates = D.concat(['2026-01-12', '2026-01-13']), close = [1000, 1000, 1000, 1000, 1000, 1000, 1030];
    const c = ctx([], dates, { close, volume:[100, 100, 100, 100, 100, 300, 300] });
    expect(computeFlow('FL27', c, { recent:2, baseline:2, volx:3, move:3 }).value[6]).toBe(1);
    expect(computeFlow('FL27', c, { recent:2, baseline:2, volx:3, move:2.9 }).value[6]).toBe(0);
  });
});
