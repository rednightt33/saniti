// EXEC-IHSG-FLOW (user 2026-11-03: "FL28 tetap hitung"): on an index FL28 is the buy value of every broker per day
import { describe, expect, it } from 'vitest';
import { computeFlow, flowRows } from '../../src/calc/flow';

const dates = ['2026-01-02', '2026-01-05', '2026-01-06'];
const rows = flowRows([
  { d:'2026-01-02', b:'AK', i:'Foreign', m:'Regular', bv:100, sv:40, bl:1, sl:0.4 },
  { d:'2026-01-02', b:'YP', i:'Domestic', m:'Nego', bv:40, sv:100, bl:0.4, sl:1 },
  { d:'2026-01-05', b:'AK', i:'Foreign', m:'Regular', bv:300, sv:300, bl:3, sl:3 },
  { d:'2026-01-06', b:'YP', i:'Domestic', m:'Regular', bv:20, sv:20, bl:0.2, sl:0.2 },
], 3, d => dates.indexOf(d));
const ctx = (index: boolean) => ({ rows, dates, close:[7000, 7010, 7020], volume:[null, null, null], insider:[], classification:{}, index });

describe('FL28 Average Daily Value', () => {
  it('an index: the mean of the daily buy value of every broker, board and investor', () => {
    expect(computeFlow('FL28', ctx(true), { window:2 }).value).toEqual([null, 220, 160]);
  });
  it('a ticker without volume that is not an index still has no value (close x volume)', () => {
    expect(computeFlow('FL28', ctx(false), { window:2 }).value).toEqual([null, null, null]);
  });
});
