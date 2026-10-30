// EXEC-TERMINAL-PANELS (user 2026-10-26): broker panel window, range calendar, chart range and panel order.
import { describe, expect, it } from 'vitest';
import { brokerData, panelStart, PANEL_YEARS } from '../../src/data/worker';
import { monthGrid } from '../../src/ui/calendar';
import { sessionsBetween } from '../../src/app/rangeSelect';
import { orderedKeys } from '../../src/ui/reorder';
import { niceTicks } from '../../src/app/broker';
import { brokerEnd } from '../../src/app/context';

const doc = (d: string[]) => ({ columns:['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl'], d, b:d.map(() => 'YP'),
  i:d.map(() => 'Domestic'), m:d.map(() => 'RG'), bv:d.map(() => 10), sv:d.map(() => 4), bl:d.map(() => 1), sl:d.map(() => 1) });

describe('Broker activity window (B1, two years)', () => {
  it('starts PANEL_YEARS years before the latest broker date', () => {
    expect(PANEL_YEARS).toBe(2);
    expect(panelStart('2026-10-23')).toBe('2024-10-23');
    expect(panelStart('2028-02-29')).toBe('2026-02-29');            // compared as text: 2026-03-01 is inside
  });
  it('keeps the broker dates after the start, from every file, not the last 30', () => {
    const old = ['2016-01-04', '2024-10-22', '2024-10-23'], recent = Array.from({ length:60 }, (_, k) => new Date(Date.UTC(2025, 0, 10 + k)).toISOString().slice(0, 10));
    const last = ['2026-10-23'];
    const b = brokerData([doc(old), doc(recent), doc(last)], []);
    expect(b.dates[0]).toBe('2025-01-10');
    expect(b.dates.includes('2024-10-23')).toBe(false);              // the start day itself is out (strictly after)
    expect(b.dates.at(-1)).toBe('2026-10-23');
    expect(b.dates.length).toBeGreaterThan(30);
    expect(b.rows[0][0]).toEqual(['YP', 'Domestic', 'Regular', 10, 4, 1, 1]);
  });
});

describe('range calendar month grid (D1)', () => {
  it('starts weeks on Monday and pads outside the month', () => {
    const g = monthGrid(2026, 9);                                     // October 2026 starts on a Thursday
    expect(g[0]).toEqual(['', '', '', '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04']);
    expect(g.flat().filter(Boolean)).toHaveLength(31);
    expect(g.every(w => w.length === 7)).toBe(true);
  });
  it('handles a leap February', () => {
    expect(monthGrid(2028, 1).flat().filter(Boolean).at(-1)).toBe('2028-02-29');
  });
});

describe('chart range to sessions (C1)', () => {
  const dates = ['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23'];
  it('rounds logical positions to sessions in either drag direction', () => {
    expect(sessionsBetween(dates, 3.4, 0.6)).toEqual(['2026-10-20', '2026-10-22']);
  });
  it('clamps to the chart and refuses a range outside it', () => {
    expect(sessionsBetween(dates, -5, 99)).toEqual(['2026-10-19', '2026-10-23']);
    expect(sessionsBetween(dates, 7, 9)).toBeNull();
    expect(sessionsBetween(dates, NaN, 2)).toBeNull();
  });
});

describe('panel order (A1)', () => {
  it('puts the saved order first and keeps sections the save does not name', () => {
    expect(orderedKeys(['bs', 'acc', 'inv', 'bd'], ['acc', 'bs'])).toEqual(['acc', 'bs', 'inv', 'bd']);
    expect(orderedKeys(['bs', 'acc'], ['gone', 'acc'])).toEqual(['acc', 'bs']);
    expect(orderedKeys(['bs', 'acc'], [])).toEqual(['bs', 'acc']);
  });
});

describe('Broker inventory y-axis ticks (C3)', () => {
  it('gives round steps that include zero and stay inside the range', () => {
    expect(niceTicks(-11500, 121000)).toEqual([0, 25000, 50000, 75000, 100000]);
    expect(niceTicks(-3, 9)).toEqual([-2, 0, 2, 4, 6, 8]);
    expect(niceTicks(-900000, 1700000)).toEqual([-500000, 0, 500000, 1000000, 1500000]);
    const t = niceTicks(0, 1);
    expect(t[0]).toBe(0); expect(t.at(-1)).toBeLessThanOrEqual(1);
  });
});

describe('broker data older than the prices (EXEC-TERMINAL-FRESH)', () => {
  const dates = ['2026-10-21', '2026-10-22', '2026-10-23', '2026-10-26', '2026-10-27'];
  it('ends on the last session on or before the broker date', () => {
    expect(brokerEnd(dates, '2026-10-23')).toBe(2);
    expect(brokerEnd(dates, '2026-10-24')).toBe(2);                    // a weekend date: the Friday before
    expect(brokerEnd(dates, '2026-10-27')).toBe(4);                    // current: nothing is masked
  });
  it('masks nothing when the date is unknown (the fixture) and everything when it is older than the chart', () => {
    expect(brokerEnd(dates, undefined)).toBe(4);
    expect(brokerEnd(dates, '2026-01-02')).toBe(-1);
  });
});

describe('Flow indicators raw rows (EXEC-TERMINAL-FLOW-IND, worker.ts flowRowsOf)', () => {
  it('keeps every row on its candle with the transaction counts, NaN where a file has none', () => {
    const dates = ['2026-10-20', '2026-10-21', '2026-10-22'];
    const withFreq = { ...doc(['2026-10-20', '2026-10-21']), columns:['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl', 'bf', 'sf'], bf:[3, null], sf:[1, 2] };
    const b = brokerData([withFreq, doc(['2026-10-22', '2026-10-30'])], dates);
    const R = b.flow;
    expect(R.n).toBe(3); expect(R.N).toBe(3); expect([...R.t]).toEqual([0, 1, 2]);       // 10-30 is not a candle
    expect(R.brokers).toEqual(['YP']); expect([...R.has]).toEqual([1, 1, 1]);
    expect(R.bf[0]).toBe(3); expect(Number.isNaN(R.bf[1])).toBe(true); expect(Number.isNaN(R.bf[2])).toBe(true);
    expect(R.brd[0]).toBe(0);                                            // board 'RG' reads as Regular
  });
  it('puts the sessions of a weekly candle on that candle', () => {
    const dates = ['2026-10-19', '2026-10-20', '2026-10-27'];
    const b = brokerData([doc(dates)], dates, { starts:[0, 2], of:[0, 0, 1], ends:['2026-10-20', '2026-10-27'] } as any);
    expect(b.flow.N).toBe(2); expect([...b.flow.t]).toEqual([0, 0, 1]);
  });
});
