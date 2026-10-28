// EXEC-TERMINAL-ASSETS (user 2026-10-28): an added asset's candles on the chart's candles, its legend figure and the
// settings a new asset starts with.
import { describe, expect, it } from 'vitest';
import { alignCandles, buckets } from '../../src/data/timeframe';
import { defaultOpts, legendPct, sourceOf } from '../../src/app/assets';
import type { PriceRow } from '../../src/data/worker';

const row = (d: string, o: number, h: number, l: number, c: number): PriceRow => ({ d, o, h, l, c, v:null });
// the chart's sessions: Mon 2026-03-02 … Tue 2026-03-10 (weekdays)
const S = ['2026-03-02', '2026-03-03', '2026-03-04', '2026-03-05', '2026-03-06', '2026-03-09', '2026-03-10'];

describe('alignCandles', () => {
  it('puts the asset on the chart sessions, repeats the last close on a session it did not trade, starts at its first close', () => {
    const rows = [row('2026-03-03', 10, 12, 9, 11), row('2026-03-05', 11, 13, 10, 12), row('2026-03-06', 12, 12, 11, 11.5), row('2026-03-07', 1, 1, 1, 1)];
    const out = alignCandles(S, buckets(S, 'D'), rows);
    expect(out.map(b => b.time)).toEqual(S.slice(1));                 // no candle before its first row; a Saturday row is dropped
    expect(out[1]).toEqual({ time:'2026-03-04', open:11, high:11, low:11, close:11 });   // not traded: flat at the last close
    expect(out.at(-1)!.close).toBe(11.5);
  });
  it('takes a close from before the chart\'s first session', () => {
    const out = alignCandles(S, buckets(S, 'D'), [row('2026-02-27', 5, 5, 5, 7), row('2026-03-04', 7, 8, 6, 8)]);
    expect(out[0]).toEqual({ time:'2026-03-02', open:7, high:7, low:7, close:7 });
    expect(out.length).toBe(S.length);
  });
  it('builds weekly candles labelled like the chart\'s', () => {
    const rows = S.map((d, k) => row(d, 10 + k, 12 + k, 9 + k, 11 + k));
    const out = alignCandles(S, buckets(S, 'W'), rows);
    expect(out).toEqual([
      { time:'2026-03-02', open:10, high:16, low:9, close:15 },
      { time:'2026-03-09', open:15, high:18, low:14, close:17 }
    ]);
  });
});

describe('legend figure', () => {
  const bars = [{ time:'a', open:100, high:110, low:90, close:100 }, { time:'b', open:100, high:120, low:95, close:110 }];
  it('is the change from the previous candle, or the return from the first in Return mode', () => {
    expect(legendPct(bars, 1, 'close', false)).toBeCloseTo(10);
    expect(legendPct(bars, 0, 'close', false)).toBeNull();
    expect(legendPct(bars, 1, 'high', true)).toBeCloseTo(9.0909, 3);
    expect(legendPct(bars, -1, 'close', false)).toBeNull();
  });
  it('reads the chosen price source', () => {
    expect(sourceOf(bars[1], 'hl2')).toBe(107.5);
    expect(sourceOf(bars[1], 'hlc3')).toBeCloseTo(108.333, 3);
    expect(sourceOf(bars[1], 'ohlc4')).toBe(106.25);
  });
});

describe('defaultOpts', () => {
  it('gives the first asset the right axis and the next its own scale, each with its slot colour', () => {
    const a = defaultOpts(0, []), b = defaultOpts(1, [a]);
    expect([a.scale, b.scale]).toEqual(['right', 'own']);
    expect(a.color).not.toBe(b.color);
    expect(a.flow && a.visible).toBe(true);
  });
});
