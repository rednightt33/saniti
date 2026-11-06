// EXEC-BROKER-INV-PANEL (user 2026-11-06): Top brokers' Domestic / Foreign / Total lanes and the Foreign × Domestic map
import { describe, expect, it } from 'vitest';
import { fdQuadrant, fdSplit } from '../../src/data/brokerAgg';
import { mapLimit, mapSvg } from '../../src/app/fdMap';
import { bandarBalance } from '../../src/app/broker';

describe('Top N groups split by investor type', () => {
  // brokers' nets by investor type (domestic d, foreign f); total buy value 1,000
  const part = new Map([['NI', { d:500, f:-20 }], ['CC', { d:300, f:10 }], ['ZP', { d:30, f:-250 }], ['BB', { d:-40, f:-60 }]]);
  it('buy = the buyers\' net, sell = the sellers\' net sale, each split; domestic + foreign = total', () => {
    const s = fdSplit(['NI', 'CC'], ['ZP', 'BB'], part, 1000);
    expect(s.buy).toEqual({ t:790, d:800, f:-10 });             // NI 480 + CC 310; domestic 800, foreign −10 (against)
    expect(s.sell).toEqual({ t:320, d:10, f:310 });             // ZP −220 and BB −100 sold: domestic −30+40 = 10, foreign 310
    expect(s.net).toEqual({ t:470, d:790, f:-320 });
    expect(s.rd + s.rf).toBeCloseTo(s.ratio, 12);
    expect(s.ratio).toBeCloseTo(0.47, 12); expect(s.rd).toBeCloseTo(0.79, 12); expect(s.rf).toBeCloseTo(-0.32, 12);
  });
  it('the total equals the verdict\'s net for the same Top N', () => {
    const list = [{ b:'NI', bv:600, sv:120 }, { b:'CC', bv:400, sv:90 }, { b:'ZP', bv:0, sv:220 }, { b:'BB', bv:0, sv:100 }];
    const bal = bandarBalance(list, 2), s = fdSplit(bal.buyers, bal.sellers, part, bal.total);
    expect(s.net.t).toBe(bal.net); expect(s.ratio).toBeCloseTo(bal.ratio, 12);
  });
  it('no buy value: ratios 0, not NaN', () => {
    const s = fdSplit([], [], part, 0);
    expect([s.ratio, s.rd, s.rf]).toEqual([0, 0, 0]);
  });
});

describe('Foreign × Domestic map', () => {
  it('quadrants by sign (0 counts as positive)', () => {
    expect([fdQuadrant(1, 1), fdQuadrant(-1, 1), fdQuadrant(1, -1), fdQuadrant(-1, -1)]).toEqual([0, 1, 2, 3]);
    // QA round 3: a part that shows as 0.0% is flat (Nego 0.0 / 0.0 was "Both accumulating")
    expect([fdQuadrant(0, 0), fdQuadrant(-0.04, 0.04), fdQuadrant(0, 5), fdQuadrant(0.01, -5), fdQuadrant(5, 0), fdQuadrant(-5, -0.049)]).toEqual([4, 4, 5, 6, 7, 8]);
    expect([fdQuadrant(0.05, 0.05), fdQuadrant(-0.05, 0.05)]).toEqual([0, 1]);
  });
  it('the axis half-range: at least 12 % with room, rounded to 5 (10 above 40)', () => {
    expect(mapLimit([1, -3])).toBe(15); expect(mapLimit([24.2, -9.2, 15.1])).toBe(30); expect(mapLimit([60])).toBe(70);
  });
  it('a point beyond the range is drawn hollow at the edge; non-finite points are left out', () => {
    const svg = mapSvg([{ label:'5D', x:50, y:2, r:52, cur:true, tip:'' }, { label:'1D', x:NaN, y:1, r:1, cur:false, tip:'' }], 15);
    expect(svg).toContain('fill="var(--surface)" stroke="var(--text)" stroke-width="1.2"');
    expect(svg).not.toContain('>1D<');
  });
});
