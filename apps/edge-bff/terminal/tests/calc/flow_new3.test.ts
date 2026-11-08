// EXEC-FLOW-NEW-3 and EXEC-RP-LOOK-2 (user go 2026-11-08): FL49 Daily Quadrant, FL50 Rotation, FL51 Loaders, FL52 Broker
// Inventory on the price chart, FL14's average line and the F×D window's Rupiah view, against hand-computed values.
import { describe, expect, it } from 'vitest';
import { computeFlow, flowRows, loadersTable, meanOfLast, type FlowContext } from '../../src/calc/flow';
import { fdNomShown, fdNomText, fdNomUnit, FD_QUADRANTS } from '../../src/data/brokerAgg';

type Row = { d: string; b: string; i: string; m: string; bv: number; sv: number; bl: number; sl: number; bf?: number | null; sf?: number | null };
const r = (d: string, b: string, bv: number, sv: number, bl: number, sl: number, i = 'Domestic', m = 'Regular'): Row => ({ d, b, i, m, bv, sv, bl, sl, bf:1, sf:1 });
const D = ['2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08', '2026-01-09'];
function ctx(rows: Row[], close = D.map(() => 100)): FlowContext {
  const at = new Map(D.map((d, k) => [d, k]));
  return { rows:flowRows(rows, D.length, d => at.get(d) ?? -1), dates:D, close, volume:D.map(() => 1000), insider:[], classification:{} };
}

/* day 0: AA buys Rp100 (60 foreign, 40 domestic), BB sells Rp100 to foreign clients; day 1: AA buys 50 foreign, CC sells 50
   domestic. Total buy value: 100 on day 0, 50 on day 1. */
const FD = [r(D[0], 'AA', 60, 0, 6, 0, 'Foreign'), r(D[0], 'AA', 40, 0, 4, 0), r(D[0], 'BB', 0, 100, 0, 10, 'Foreign'),
  r(D[1], 'AA', 50, 0, 5, 0, 'Foreign'), r(D[1], 'CC', 0, 50, 0, 5)];

describe('FL50 Foreign × Domestic · Rotation (formula locked 2026-11-08)', () => {
  const o = computeFlow('FL50', ctx(FD), { top:1, boards:['Regular'], window:1 });
  it('foreign and domestic net of the Top N buyers and sellers, in % of every broker\'s buy value', () => {
    // day 0: foreign 60 − 100 = −40, domestic 40 − 0 = +40, of 100; day 1: foreign +50, domestic −50, of 50
    expect(o.foreign[0]).toBeCloseTo(-40, 9); expect(o.domestic[0]).toBeCloseTo(40, 9); expect(o.verdict[0]).toBeCloseTo(0, 9);
    expect(o.foreign[1]).toBeCloseTo(100, 9); expect(o.domestic[1]).toBeCloseTo(-100, 9);
  });
  it('a rolling window sums both days before dividing (the BBRI 5D example\'s method)', () => {
    const w = computeFlow('FL50', ctx(FD), { top:1, boards:['Regular'], window:2 });
    // days 0-1: AA net +150 (foreign 110, domestic 40), the largest seller BB −100 (foreign −100); total buy 150
    // 6.667 and 26.667 shown with two decimals that add up to the verdict 33.33 (fdShown, as the map): 6.67 + 26.66
    expect([w.foreign[1], w.domestic[1], w.verdict[1]]).toEqual([6.67, 26.66, 33.33]);
    expect(w.foreign[0]).toBeNull();                                  // the window is not full yet
  });
  it('no buy value: no reading', () => expect(o.foreign[2]).toBeNull());
});

describe('FL49 Foreign × Domestic · Daily Quadrant', () => {
  it('the map\'s quadrant of each session', () => {
    const v = computeFlow('FL49', ctx(FD), { top:1, boards:['Regular'], window:1 }).value;
    expect(FD_QUADRANTS[v[0]!]).toBe('Domestic absorbing, foreign leaving');
    expect(FD_QUADRANTS[v[1]!]).toBe('Foreign absorbing, domestic leaving');
    expect(v[2]).toBeNull();
  });
});

describe('FL51 Loaders', () => {
  // AA buys 10 lots at 100 then 10 at 120 and sells 10 at 130; CC buys 5 at 100; BB sells 15
  const rows = [r(D[0], 'AA', 1e5, 0, 10, 0), r(D[0], 'BB', 0, 1e5, 0, 10), r(D[1], 'AA', 1.2e5, 0, 10, 0), r(D[1], 'BB', 0, 5e4, 0, 5),
    r(D[1], 'CC', 5e4, 0, 5, 0), r(D[2], 'AA', 0, 1.3e5, 0, 10), r(D[2], 'CC', 1.3e5, 0, 10, 0)];
  const c = ctx(rows, [100, 120, 132, 132, 132]);
  it('loaders by net lots, sellers after them, with cost, distance, buy days and the loaders\' share', () => {
    const T = loadersTable(c, { boards:['Regular'], start:D[0], end:D[2], cost:'avg' });
    expect(T.rows.map(x => [x.b, x.lots])).toEqual([['CC', 15], ['AA', 10], ['BB', -15]]);
    const aa = T.rows[1];
    expect(aa.cost).toBeCloseTo(2.2e5 / (100 * 20), 9);              // A: buy value ÷ buy lots, sells left out
    expect(aa.dist).toBeCloseTo(100 * (132 / 110 - 1), 9);
    expect([aa.buyDays, aa.days]).toEqual([2, 3]);
    expect(T.share).toBeCloseTo(100, 9);                              // the only two brokers that added are both loaders
  });
  it('B: the cost of the position still held (FL19\'s model, one broker)', () => {
    const aa = loadersTable(c, { boards:['Regular'], start:D[0], end:D[2], cost:'model' }).rows.find(x => x.b === 'AA')!;
    // 10 at 100 + 10 at 120 = 2,200 for 20; selling 10 keeps half the cost: 1,100 for 10 lots = 110 a share
    expect(aa.cost).toBeCloseTo(110, 9);
  });
  it('the period\'s end cuts the rows; the cost line starts at the period\'s start', () => {
    const T = loadersTable(c, { boards:['Regular'], start:D[1], end:D[1], cost:'avg' });
    expect(T.rows.map(x => [x.b, x.lots])).toEqual([['AA', 10], ['CC', 5], ['BB', -5]]);
    expect(T.rows[0].line[0]).toBeNull(); expect(T.rows[0].line[1]).toBeCloseTo(120, 9); expect(T.rows[0].line[2]).toBeNull();
  });
  it('option E: Show and Top N choose the rows; both sides list as many sellers, at most 5; the share is over the N shown', () => {
    const q = { boards:['Regular'], start:D[0], end:D[2], cost:'avg' };
    const both = loadersTable(c, { ...q, side:'both', top:'3' }), load = loadersTable(c, { ...q, side:'load', top:'3' }), sell = loadersTable(c, { ...q, side:'sell', top:'3' });
    expect([both.nl, both.ns, both.rows.map(x => x.b)]).toEqual([2, 1, ['CC', 'AA', 'BB']]);   // only 2 net buyers and 1 net seller exist
    expect([load.ns, load.rows.length, sell.nl, sell.share]).toEqual([0, 2, 0, null]);
    expect(Object.keys(computeFlow('FL51', c, { ...q, side:'sell', top:'3' }))).toEqual([]);   // no loader shown: no cost line
  });
  it('FL51 draws the loaders\' cost lines, keyed by broker', () => {
    expect(Object.keys(computeFlow('FL51', c, { boards:['Regular'], start:D[0], end:D[2], cost:'avg' }))).toEqual(['CC', 'AA']);
  });
});

describe('FL52 Broker Inventory on the price chart', () => {
  it('the brokers given, FL23\'s cumulative position from the start, no total', () => {
    const o = computeFlow('FL52', ctx(FD), { brokers:['AA'], unit:'lot', boards:['Regular'], start:D[0] });
    expect(Object.keys(o)).toEqual(['AA']);
    expect(o.AA[0]).toBeCloseTo(10, 9); expect(o.AA[1]).toBeCloseTo(15, 9);
  });
});

describe('FL14 average line', () => {
  it('the mean of the last 10 values where all 10 exist; a gap restarts it', () => {
    const a = [...Array(12).keys()].map(k => k + 1) as (number | null)[];
    const m = meanOfLast(a, 10);
    expect(m[8]).toBeNull(); expect(m[9]).toBeCloseTo(5.5, 9); expect(m[11]).toBeCloseTo(7.5, 9);
    expect(meanOfLast([1, 2, null, 4, 5], 2)).toEqual([null, 1.5, null, null, 4.5]);
  });
});

describe('F×D window, Nominal (Rp)', () => {
  it('one unit for the table, two decimals, the verdict the sum of the parts as shown', () => {
    const u = fdNomUnit([-599.46e9, 354.73e9, -244.73e9]);
    expect(u).toEqual([1e9, 'B']);
    const v = fdNomShown(-599.456e9, 354.734e9, u);
    expect(v.text).toEqual({ f:'−Rp 599.46B', d:'+Rp 354.73B', v:'−Rp 244.73B' });
    expect(fdNomText(3842.6e9, u)).toBe('Rp 3,842.60B');                // the total buy value in the same unit
    expect(fdNomShown(4e6, -1e5, fdNomUnit([4e6])).text.v).toBe('+Rp 3.90M');
    // a table with a part over Rp 1T stays in billions (Rp 0.60T would hide Rp 10B)
    expect(fdNomUnit([1.5e12, 2e9])).toEqual([1e9, 'B']);
    expect(fdNomShown(1234.567e9, -0.6e9, [1e9, 'B']).text).toEqual({ f:'+Rp 1,234.57B', d:'−Rp 0.60B', v:'+Rp 1,233.97B' });
  });
});
