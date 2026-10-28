/* Cross-sectional ranks on the fixed population (report TARGET ARCHITECTURE 6.9 rs_rank, P7 a with P4; TEST PLAN 10b.5
   "Hidden tickers and the rank population"): the population is active, non-stale stocks without a price break and with
   a finite value; pct = 100 x #(strictly lower) / (P - 1) for a member, / P for a shown hidden ticker, so every rank is
   in [0, 100]; NaN is excluded (the prototype counted it); ties share a rank; P < 2 gives null; showing a hidden ticker
   moves no other rank. */
import { describe, expect, it } from 'vitest';
import type { UniverseRow } from '../../src/core/contract.ts';
import { percentRank, rankPopulation, returnRankAll, returnsOf } from '../../src/core/xsection.ts';

const E = '2026-10-27';
const row = (ticker: string, o: Partial<UniverseRow> = {}): UniverseRow => ({ ticker, name: null, sector: null, industry: null, last: 1, chg_1d_pct: 0, adv20_idr: 1,
  first_bar: '2018-01-02', last_bar: E, bars: 2000, stale: false, remarks: [], ...o });

describe('population and percent rank', () => {
  const rows = [row('A'), row('B'), row('C'), row('D'), row('S', { stale: true, last_bar: '2026-08-21' }),
    row('P', { remarks: [{ code: 'PRICE_BREAK', action: 'STOCK_SPLIT', ex_date: '2026-10-14', ratio_old: 1, ratio_new: 2, close_ratio: 0.45 }] }), row('N')];
  const values = new Map<string, number | null>([['A', 10], ['B', 20], ['C', 20], ['D', 40], ['S', 99], ['P', 5], ['N', NaN]]);
  it('keeps active, non-stale stocks without a price break and with a finite value', () => {
    expect([...rankPopulation(rows, values, E)].sort()).toEqual(['A', 'B', 'C', 'D']);
  });
  it('ranks members over P - 1, shown hidden tickers over P, ties alike, NaN null; every rank in [0, 100]', () => {
    const r = percentRank(values, rankPopulation(rows, values, E));
    expect(Object.fromEntries(r)).toEqual({ A: 0, B: 100 / 3, C: 100 / 3, D: 100, S: 100, P: 0, N: null });
    for (const v of r.values()) if (v !== null) expect(v >= 0 && v <= 100).toBe(true);
  });
  it('P < 2 gives null; a population of two ranks 0 and 100', () => {
    expect(Object.fromEntries(percentRank(new Map([['A', 1], ['B', 5]]), new Set(['A'])))).toEqual({ A: null, B: null });
    expect(Object.fromEntries(percentRank(new Map([['A', 1], ['B', 5]]), new Set(['A', 'B'])))).toEqual({ A: 0, B: 100 });
  });
  it('showing a hidden ticker (adding it to the ranked set) moves no other rank: the population is fixed', () => {
    const pop = rankPopulation(rows, values, E);
    const without = percentRank(new Map([...values].filter(([t]) => t !== 'S' && t !== 'P')), pop);
    const withHidden = percentRank(values, pop);
    for (const [t, v] of without) expect([t, withHidden.get(t)]).toEqual([t, v]);
  });
});

describe('return_rank', () => {
  it('returns (close[at] / close[at - window] - 1) x 100 at each ticker\'s own evaluation bar; null without enough bars', () => {
    const closes = new Map([['A', { at: 3, close: [100, 105, 110, 121] }], ['B', { at: 1, close: [50, 40] }], ['C', { at: 3, close: [5, 0, 2, 3] }]]);
    const r = returnsOf(closes, 2);
    expect(r.get('A')).toBeCloseTo((121 / 105 - 1) * 100, 12);
    expect([r.get('B'), r.get('C')]).toEqual([null, null]);                                      // too few bars; a zero base
  });
  it('ranks the returns on the population the returns define, stale and price-break tickers outside it', () => {
    const rows = [row('A'), row('B'), row('C'), row('S', { stale: true, last_bar: '2026-10-20' })];
    const closes = new Map([['A', { at: 2, close: [10, 10, 11] }], ['B', { at: 2, close: [10, 10, 12] }], ['C', { at: 2, close: [10, 10, 13] }], ['S', { at: 2, close: [10, 10, 20] }]]);
    const out = returnRankAll(rows, closes, 1, E);
    expect([...out.population].sort()).toEqual(['A', 'B', 'C']);
    expect(Object.fromEntries(out.ranks)).toEqual({ A: 0, B: 50, C: 100, S: 100 });
  });
});
