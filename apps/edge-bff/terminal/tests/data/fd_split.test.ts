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

// EXEC-FD-WINDOW (user 2026-11-07): the window's trail, its per-session changes and the map's marked point
import { fdAt, fdTrail } from '../../src/app/broker';
import { trailDeltas, trailSvg } from '../../src/app/fdMap';
describe('Foreign × Domestic window', () => {
  // four sessions; per session each broker's buy and sell value by investor type (F foreign, D domestic)
  const DAYS: Record<string, { F: [number, number]; D: [number, number] }>[] = [
    { AA:{ F:[100, 0], D:[0, 20] }, BB:{ F:[0, 60], D:[10, 0] } },
    { AA:{ F:[50, 0], D:[30, 0] }, BB:{ F:[0, 0], D:[0, 90] } },
    { AA:{ F:[0, 40], D:[0, 0] }, BB:{ F:[70, 0], D:[0, 10] } },
    { AA:{ F:[10, 0], D:[60, 0] }, BB:{ F:[0, 30], D:[0, 20] } }
  ];
  const agg = (f: number, t: number, inv: string) => {
    const m = new Map<string, { b: string; bv: number; sv: number }>();
    for (let d = f; d <= t; d++) for (const [b, s] of Object.entries(DAYS[d])) for (const k of ['F', 'D'] as const) {
      if (inv !== 'All' && inv !== (k === 'F' ? 'Foreign' : 'Domestic')) continue;
      const o = m.get(b) || { b, bv:0, sv:0 }; o.bv += s[k][0]; o.sv += s[k][1]; m.set(b, o);
    }
    return [...m.values()];
  };
  it('one point per session, each the rolling period ending there; foreign + domestic = the verdict', () => {
    const T = fdTrail(agg, 3, 2, 20, 1);
    expect(T.map(p => [p.f, p.t])).toEqual([[0, 1], [1, 2], [2, 3]]);       // a session with fewer than 2 before it starts none
    for (const p of T) { expect(p.x + p.y).toBeCloseTo(p.r, 10); expect(p).toEqual(fdAt(agg, p.f, p.t, 1)) }
    expect(fdTrail(agg, 3, 1, 2, 1).map(p => p.t)).toEqual([2, 3]);       // the last `span` sessions only
    expect(fdTrail(agg, 1, 5, 20, 1).map(p => [p.f, p.t])).toEqual([[0, 1]]);   // fewer sessions than one period: all of them
  });
  it('the change of each session: Δ verdict = Δ foreign + Δ domestic, the larger side drives, newest first', () => {
    const D = trailDeltas([{ d:'2026-11-02', x:-5, y:2, r:-3 }, { d:'2026-11-03', x:-6, y:6, r:0 }, { d:'2026-11-04', x:-1, y:4, r:3 }]);
    expect(D.map(s => s.d)).toEqual(['2026-11-04', '2026-11-03']);
    expect(D[0]).toMatchObject({ i:2, dx:5, dy:-2, dr:3, driver:'fx' });
    expect(D[1]).toMatchObject({ i:1, dx:-1, dy:4, dr:3, driver:'dm' });
    for (const s of D) expect(s.dx + s.dy).toBeCloseTo(s.dr, 10);
  });
  it('the map marks the row under the pointer and names the newest point "now"', () => {
    const T = [{ d:'2026-11-02', x:-5, y:2, r:-3 }, { d:'2026-11-03', x:-6, y:6, r:0 }, { d:'2026-11-04', x:-1, y:4, r:3 }];
    expect(trailSvg(T, 15)).toContain('>now<');
    const h = trailSvg(T, 15, 1);
    expect(h).toContain('class="fdw-pt hl"'); expect(h).toContain('>03 Nov<');
  });
});
