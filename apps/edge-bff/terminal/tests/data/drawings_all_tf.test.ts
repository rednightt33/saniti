// EXEC-DRAW-ALL-TF (user 2026-11-01, "Ok C", replacing C7.2 A): one set of drawings for every timeframe. A point keeps its
// own time; each timeframe shows it on its candle that holds it, and saving puts back every point the user did not move.
import { describe, expect, it } from 'vitest';
import { mergeSets, onDailyCandles, onIntradayCandles, shownTimes, storedTimes } from '../../src/app/drawings';
import { toChart } from '../../src/data/chartTime';

const line = (id: string, a: any, b: any) => ({ id, type:'trend-line', points:[{ time:a, price:5000 }, { time:b, price:5100 }] });
const H1 = ['2026-10-27T09:00', '2026-10-27T10:00', '2026-10-27T13:30', '2026-10-28T09:00', '2026-10-28T10:00', '2026-10-28T13:30'];
const week = (d: string) => d >= '2026-10-26' ? '2026-10-26' : '2026-10-19';            // barOf of a weekly chart
const day = (d: string) => d;                                                             // barOf of a daily chart

describe('a drawing made on an intraday chart, on daily, weekly and monthly charts', () => {
  const doc = JSON.stringify([line('a', toChart('2026-10-27T10:05'), toChart('2026-10-28T13:35'))]);
  it('daily: each point on its session', () => {
    expect(JSON.parse(onDailyCandles(doc, day, '2026-10-30', false))[0].points.map((p: any) => p.time)).toEqual(['2026-10-27', '2026-10-28']);
  });
  it('weekly: each point on the week that holds its session', () => {
    expect(JSON.parse(onDailyCandles(doc, week, '2026-10-30', true))[0].points.map((p: any) => p.time)).toEqual(['2026-10-26', '2026-10-26']);
  });
  it('a point after the last session keeps its date', () => {
    const fut = JSON.stringify([line('f', toChart('2026-10-28T10:00'), toChart('2026-11-05T10:00'))]);
    expect(JSON.parse(onDailyCandles(fut, day, '2026-10-30', false))[0].points[1].time).toBe('2026-11-05');
  });
  it('a daily drawing on a daily chart is left as it is', () => {
    const d = JSON.stringify([line('d', '2026-10-27', '2026-10-30')]);
    expect(JSON.parse(onDailyCandles(d, day, '2026-10-30', false))).toEqual(JSON.parse(d));
  });
});

describe('a drawing made on a daily chart, on an intraday chart', () => {
  it('each point on the first candle of its day; a day without intraday candles at its 09:00 open', () => {
    const doc = JSON.stringify([line('d', '2026-10-28', '2026-10-15'), line('o', { year:2026, month:10, day:27 }, '2026-10-27')]);
    const out = JSON.parse(onIntradayCandles(doc, H1));
    expect(out[0].points.map((p: any) => p.time)).toEqual([toChart('2026-10-28T09:00'), toChart('2026-10-15T09:00')]);
    expect(out[1].points[0].time).toBe(toChart('2026-10-27T09:00'));
  });
});

describe('one set saved from any timeframe', () => {
  it('saving on 1H puts back the daily dates and the 5M times of every point the user did not move', () => {
    const stored = JSON.stringify([line('d', '2026-10-27', '2026-10-28'), line('m', toChart('2026-10-27T10:05'), toChart('2026-10-28T13:35'))]);
    const shown = onIntradayCandles(stored, H1), memo = shownTimes(stored, shown);
    expect(JSON.parse(storedTimes(shown, memo))).toEqual(JSON.parse(stored));
    const moved = JSON.parse(shown); moved[1].points[0].time = toChart('2026-10-28T09:00');   // the user moves one point
    const back = JSON.parse(storedTimes(JSON.stringify(moved), memo));
    expect(back[1].points[0].time).toBe(toChart('2026-10-28T09:00'));
    expect(back[1].points[1].time).toBe(toChart('2026-10-28T13:35'));
    expect(back[0].points.map((p: any) => p.time)).toEqual(['2026-10-27', '2026-10-28']);
  });
  it('saving on D puts back the 5M times', () => {
    const stored = JSON.stringify([line('m', toChart('2026-10-27T10:05'), toChart('2026-10-28T13:35'))]);
    const shown = onDailyCandles(stored, day, '2026-10-30', false);
    expect(JSON.parse(storedTimes(shown, shownTimes(stored, shown)))).toEqual(JSON.parse(stored));
  });
  it('the two sets kept before merge once: every drawing once, by id', () => {
    const daily = JSON.stringify([line('a', '2026-10-27', '2026-10-28'), line('b', '2026-10-20', '2026-10-21')]);
    const intra = JSON.stringify([line('b', 1, 2), line('c', toChart('2026-10-27T10:00'), toChart('2026-10-27T11:00'))]);
    expect(JSON.parse(mergeSets(daily, intra)).map((d: any) => d.id)).toEqual(['a', 'b', 'c']);
    expect(JSON.parse(mergeSets('not json', intra)).map((d: any) => d.id)).toEqual(['b', 'c']);
    expect(JSON.parse(mergeSets(daily, ''))).toHaveLength(2);
  });
});
