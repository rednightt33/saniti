// EXEC-TERMINAL-POPOUT W1 + I2 (user 2026-10-27): the sums behind the panel windows and the window box.
import { describe, expect, it } from 'vitest';
import { aggregate, avgPrice, inventory, invStats, sessionSpan, summaryTable, toCsv } from '../../src/data/brokerAgg';
import { clampBox } from '../../src/ui/floatwin';
import type { BrokerRow } from '../../src/data/types';

// three sessions; [broker, investor, board, buyValue, sellValue, buyLots, sellLots]
const DAYS: BrokerRow[][] = [
  [['YU', 'Foreign', 'Regular', 1000, 400, 2, 1], ['NI', 'Domestic', 'Regular', 300, 900, 1, 3], ['YU', 'Domestic', 'Nego', 500, 0, 1, 0]],
  [['YU', 'Foreign', 'Regular', 200, 600, 1, 2], ['XL', 'Foreign', 'Cash', 50, 0, 1, 0]],
  [['NI', 'Domestic', 'Regular', 800, 100, 2, 1]]
];
const rowsOf = (d: number) => DAYS[d] || [];

describe('aggregate', () => {
  it('sums every investor type and board of the period per broker', () => {
    const m = Object.fromEntries(aggregate(rowsOf, 0, 2).map(o => [o.b, o]));
    expect(m.YU).toEqual({ b:'YU', bv:1700, sv:1000, bl:4, sl:3 });
    expect(m.NI).toEqual({ b:'NI', bv:1100, sv:1000, bl:3, sl:4 });
    expect(m.XL.bv).toBe(50);
  });
  it('keeps one investor type and one board', () => {
    expect(aggregate(rowsOf, 0, 2, 'Foreign', 'Regular')).toEqual([{ b:'YU', bv:1200, sv:1000, bl:3, sl:3 }]);
    expect(aggregate(rowsOf, 0, 0, 'All', 'Nego')).toEqual([{ b:'YU', bv:500, sv:0, bl:1, sl:0 }]);
    expect(aggregate(rowsOf, 1, 1, 'Domestic')).toEqual([]);
  });
});

describe('avgPrice and sessionSpan', () => {
  it('is value over lots of 100 shares, none without lots', () => {
    expect(avgPrice(510000, 1)).toBe(5100);
    expect(avgPrice(100, 0)).toBeNull();
  });
  it('maps a date span to the sessions inside it', () => {
    const d = ['2026-10-20', '2026-10-21', '2026-10-23'];
    expect(sessionSpan(d, '2026-10-21', '2026-10-30')).toEqual([1, 2]);
    expect(sessionSpan(d, '2026-10-22', '2026-10-22')).toBeNull();          // no session that day
    expect(sessionSpan(d, '2026-10-01', '2026-10-19')).toBeNull();
    expect(sessionSpan(d, '2026-10-01', '2026-10-20')).toEqual([0, 0]);
  });
});

describe('summaryTable (Broker summary window)', () => {
  const list = [
    { b:'AA', bv:900, sv:100, bl:9, sl:1 }, { b:'BB', bv:500, sv:200, bl:5, sl:2 }, { b:'CC', bv:300, sv:300, bl:3, sl:3 },
    { b:'DD', bv:100, sv:600, bl:1, sl:6 }, { b:'EE', bv:0, sv:600, bl:0, sl:6 }
  ];
  it('gives each broker its share of the period value; the shares and the totals add up', () => {
    const t = summaryTable(list, { sort:'nv', desc:true, limit:null });
    expect(t.rows.map(r => r.b)).toEqual(['AA', 'BB', 'CC', 'DD', 'EE']);
    expect(t.rows.reduce((s, r) => s + r.share, 0)).toBeCloseTo(100, 9);
    expect(t.total).toMatchObject({ bv:1800, sv:1800, bl:18, sl:18, nv:0, nl:0, share:100 });
    expect(t.rows[0]).toMatchObject({ nv:800, nl:8, ba:1, sa:1 });
    expect(t.rows[4].ba).toBeNull();
  });
  it('keeps the top net buyers and the top net sellers with a limit on a net column', () => {
    const t = summaryTable(list, { sort:'nv', desc:true, limit:1 });
    expect(t.rows.map(r => r.b)).toEqual(['AA', 'EE']);
    expect(t.split).toBe(1); expect(t.count).toBe(5);
  });
  it('keeps the first rows for another column, and the search finds a code', () => {
    expect(summaryTable(list, { sort:'share', desc:true, limit:2 }).rows.map(r => r.b)).toEqual(['AA', 'BB']);
    expect(summaryTable(list, { sort:'b', desc:false, limit:null }).rows.map(r => r.b)).toEqual(['AA', 'BB', 'CC', 'DD', 'EE']);
    const s = summaryTable(list, { sort:'nv', desc:true, limit:1, search:'d' });
    expect(s.rows.map(r => r.b)).toEqual(['DD']); expect(s.split).toBe(-1);
  });
});

describe('inventory (Broker inventory window)', () => {
  it('gives each broker its daily net and running sum, in lots or value, with its period sums', () => {
    const [yu, ni] = inventory(rowsOf, 0, 2, ['YU', 'NI'], 'All', 'All', 'lot');
    expect(yu.daily).toEqual([2, -1, 0]); expect(yu.cum).toEqual([2, 1, 1]);
    expect(ni.cum).toEqual([-2, -2, -1]);
    expect(yu.agg).toEqual({ b:'YU', bv:1700, sv:1000, bl:4, sl:3 });
    const [v] = inventory(rowsOf, 0, 1, ['YU'], 'Foreign', 'Regular', 'value');
    expect(v.daily).toEqual([600, -400]); expect(v.cum).toEqual([600, 200]);
    expect(invStats(v.cum)).toEqual({ end:200, hi:600, lo:200 });
    expect(invStats([])).toEqual({ end:0, hi:0, lo:0 });
  });
});

describe('toCsv and clampBox', () => {
  it('quotes a cell with a comma or a quote', () => {
    expect(toCsv(['a', 'b'], [['x,y', 1], ['say "hi"', null]])).toBe('a,b\n"x,y",1\n"say ""hi""",');
  });
  it('keeps a window inside the page with its title bar reachable', () => {
    expect(clampBox({ x:-900, y:-50, w:800, h:500 }, 1400, 900)).toEqual({ x:-752, y:0, w:800, h:500 });
    expect(clampBox({ x:1390, y:2000, w:3000, h:3000 }, 1400, 900)).toEqual({ x:1352, y:868, w:1400, h:900 });
    expect(clampBox({ x:10, y:10, w:100, h:50 }, 1400, 900, 360, 240)).toEqual({ x:10, y:10, w:360, h:240 });
  });
});
