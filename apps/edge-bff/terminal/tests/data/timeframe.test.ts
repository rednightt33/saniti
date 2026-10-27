// EXEC-TERMINAL-WM (user 2026-10-27: weekly and monthly candles from the daily sessions; "G1", "K1").
import { describe, expect, it } from 'vitest';
import { aggregateRows, bucketKey, buckets, candleOf, PERIODS_PER_YEAR } from '../../src/data/timeframe';
import { onCandles } from '../../src/app/drawings';

const row = (d: string, o: number, h: number, l: number, c: number, v: number | null = 10) => ({ d, o, h, l, c, v });
const days = [row('2026-09-28', 10, 12, 9, 11), row('2026-09-30', 11, 15, 10, 14), row('2026-10-01', 14, 14, 8, 9),
  row('2026-10-02', 9, 10, 9, 10, null), row('2026-10-05', 10, 11, 10, 11)];

describe('candle keys', () => {
  it('weeks start on Monday, months are calendar months', () => {
    expect(bucketKey('2026-10-01', 'W')).toBe('2026-09-28');           // a Thursday
    expect(bucketKey('2026-10-04', 'W')).toBe('2026-09-28');           // the Sunday after belongs to the same week
    expect(bucketKey('2026-10-05', 'W')).toBe('2026-10-05');
    expect(bucketKey('2026-10-31', 'M')).toBe('2026-10');
    expect(PERIODS_PER_YEAR).toEqual({ D:252, W:52, M:12 });
  });
});

describe('weekly and monthly candles', () => {
  it('take the first open, the highest high, the lowest low, the last close and the summed volume', () => {
    expect(aggregateRows(days, 'W')).toEqual([row('2026-09-28', 10, 15, 8, 10, 30), row('2026-10-05', 10, 11, 10, 11)]);
    expect(aggregateRows(days, 'M')).toEqual([row('2026-09-28', 10, 15, 9, 14, 20), row('2026-10-01', 14, 14, 8, 11, 20)]);
  });
  it('leave daily rows as they are and keep the running week as it stands (K1)', () => {
    expect(aggregateRows(days, 'D')).toBe(days);
    expect(aggregateRows(days, 'W').at(-1)).toEqual(row('2026-10-05', 10, 11, 10, 11));
  });
  it('know each candle\'s first and last session and each session\'s candle', () => {
    const b = buckets(days.map(r => r.d), 'W');
    expect(b).toEqual({ starts:['2026-09-28', '2026-10-05'], ends:['2026-10-02', '2026-10-05'], of:[0, 0, 0, 0, 1] });
  });
  it('find the candle that holds a date, weekends and holidays included', () => {
    const s = days.map(r => r.d), b = buckets(s, 'W');
    expect(candleOf('2026-09-29', b, s)).toBe('2026-09-28');            // no session that day: the next one's week
    expect(candleOf('2026-10-03', b, s)).toBe('2026-10-05');            // Saturday: the next session is Monday
    expect(candleOf('2026-09-01', b, s)).toBe('2026-09-28');
  });
});

describe('drawings on weekly candles (G1)', () => {
  it('move each point to the candle that holds it and keep future points', () => {
    const b = buckets(days.map(r => r.d), 'W'), s = days.map(r => r.d);
    const json = JSON.stringify([{ id:'a', kind:'trend-line', points:[{ time:'2026-10-01', price:12 }, { time:{ year:2026, month:10, day:5 }, price:13 }, { time:'2026-12-01', price:14 }] }]);
    const out = JSON.parse(onCandles(json, d => candleOf(d, b, s), '2026-10-05'));
    expect(out[0].points.map((p: any) => p.time)).toEqual(['2026-09-28', '2026-10-05', '2026-12-01']);
  });
});
