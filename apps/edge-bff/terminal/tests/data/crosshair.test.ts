/* ERRORS M419: a crosshair copied to a chart without a bar at that time must not throw (the throw stopped the broker load
   and left the right panel on "Loading" when the pointer rested on the price chart) */
import { describe, expect, it } from 'vitest';
import { safeCharts, safeCrosshair } from '../../src/data/chartTime';

const MAIN = import.meta.glob('../../src/main.ts', { query:'?raw', import:'default', eager:true }) as Record<string, string>;

const fake = (throws: boolean) => {
  const calls: string[] = [];
  const chart: any = {
    setCrosshairPosition: (p: number, t: any) => { calls.push(`set ${p} ${t}`); if (throws) throw new Error('Value is null') },
    clearCrosshairPosition: () => { calls.push('clear') },
  };
  return { chart, calls };
};

describe('safe crosshair', () => {
  it('clears instead of throwing when the chart has no bar at that time', () => {
    const { chart, calls } = fake(true);
    safeCrosshair(chart);
    expect(() => chart.setCrosshairPosition(1, '2026-11-09', {})).not.toThrow();
    expect(calls).toEqual(['set 1 2026-11-09', 'clear']);
  });
  it('passes a valid position through unchanged and wraps once', () => {
    const { chart, calls } = fake(false);
    safeCrosshair(safeCrosshair(chart));
    chart.setCrosshairPosition(2, '2026-11-06', {});
    expect(calls).toEqual(['set 2 2026-11-06']);
  });
  it('every chart the page creates is wrapped', () => {
    const { chart } = fake(true);
    const L = safeCharts({ createChart: () => chart });
    expect(() => L.createChart().setCrosshairPosition(0, 't', {})).not.toThrow();
    expect(Object.values(MAIN)[0]).toContain('L:safeCharts(');
  });
});
