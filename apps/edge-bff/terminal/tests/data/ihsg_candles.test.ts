/* ERRORS M565: with the Statistics panel open the console said "<line> attribute y1: Expected length, "NaN"" and
   "<polyline> attribute points: Expected number, "0.0,NaN 1.1,NaN …"" (Relative performance vs IHSG), on a fresh page
   and on a switched one: IHSG with no close on or before the chart's last candle became a series of NaN, and the panel
   drew it. Now there is no series then, and the panel says so. */
import { describe, expect, it } from 'vitest';
// @ts-expect-error: the Terminal's tsconfig has no Node types; vitest runs in Node
import { readFileSync } from 'node:fs';
import { ihsgOnCandles } from '../../src/data/live';

const dates = ['2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08'];

describe('IHSG on the chart\'s candles', () => {
  it('fills the candles before its first close with that close', () => {
    expect(ihsgOnCandles(dates, [{ time:'2026-01-07', value:7000 }, { time:'2026-01-08', value:7100 }]).map(p => p.value)).toEqual([7000, 7000, 7000, 7100]);
    expect(ihsgOnCandles(dates, dates.map((t, i) => ({ time:t, value:7000 + i }))).map(p => p.value)).toEqual([7000, 7001, 7002, 7003]);
  });

  it('is no series at all when IHSG has no close on these candles (before: every value NaN)', () => {
    expect(ihsgOnCandles(dates, [])).toEqual([]);
  });

  it('is what Relative performance reads, and an empty or non-finite answer is said, not drawn', () => {
    const live = readFileSync(new URL('../../src/data/live.ts', import.meta.url), 'utf8');
    expect(live).toMatch(/return ihsgOnCandles\(dates, alignTo\(dates, await ihsgRows\(\), intraday \? dates : ends\)\);/);
    expect(live).not.toMatch(/: NaN;/);
    const stats = readFileSync(new URL('../../src/app/stats.ts', import.meta.url), 'utf8');
    expect(stats).toMatch(/if \(sr\.some\(p => Number\.isFinite\(p\.value\)\)\) ihsgSeries = sr; else ihsgNone = true;/);
    expect(stats).toMatch(/ihsgNone \? empty\('No IHSG data for this chart'\)/);
  });
});
