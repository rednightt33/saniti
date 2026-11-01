// EXEC-INTRADAY-FEATURES C3-C4 (user 2026-11-01: "Opsi 1, 4A, 2A dan 3A ok"; "Sabtu kita pakai A, namun ini hanya berlaku
// intraday literally di hari terbaru. Kalau di hari sebelumnya, maka flow dan bandar harus di-show, tapi menggunakan time
// frame daily"): intraday candle keys, the daily session each candle shows, and the sums that count a day once.
import { describe, expect, it } from 'vitest';
import { barKey, dayOfCandles, dayOfKey, firstOfDay, isIntraday, markerOnCandles, onCandles, periodsPerYear, tfLabel, asTimeframe } from '../../src/data/timeframe';
import { fromChart, keyedMarkers, toChart } from '../../src/data/chartTime';
import { countedCandles, cumulativeFrom } from '../../src/app/flow';
import { barRows } from '../../src/data/worker';
import { onIntradayCandles } from '../../src/app/drawings';
import { keyOf } from '../../src/app/context';
import { F } from '../../src/calc/indicators';

const WIB = 7 * 3600;
const at = (iso: string) => Date.parse(iso) / 1000;                     // a bar's open in UTC seconds

describe('intraday timeframes and keys', () => {
  it('a timeframe is any <number><m|h>, never a list', () => {
    expect(['5m', '15m', '1h', '4h', '30m'].every(isIntraday)).toBe(true);
    expect(['D', 'W', 'M', '5x', '', null].some(isIntraday)).toBe(false);
    expect(asTimeframe('15m')).toBe('15m'); expect(asTimeframe('1d')).toBe('D');
    expect(tfLabel('1h')).toBe('1H'); expect(periodsPerYear('5m', 16017)).toBe(16017); expect(periodsPerYear('W')).toBe(52);
  });
  it('a key is the open time on the exchange clock and its first ten characters are the session', () => {
    const k = barKey(at('2026-10-30T02:00:00Z'), WIB);
    expect(k).toBe('2026-10-30T09:00'); expect(dayOfKey(k)).toBe('2026-10-30');
    expect('2026-10-30' < k && k < '2026-10-31').toBe(true);              // dates and keys keep their order
  });
  it('the chart gets the wall clock as UTC seconds and gives the same key back; a date passes unchanged', () => {
    expect(toChart('2026-10-30T09:00')).toBe(at('2026-10-30T09:00:00Z'));
    expect(fromChart(toChart('2026-10-30T13:30'))).toBe('2026-10-30T13:30');
    expect(keyOf(toChart('2026-10-30T15:55'))).toBe('2026-10-30T15:55');
    expect(toChart('2026-10-30')).toBe('2026-10-30');
    expect(keyedMarkers([{ time:'2026-10-30T09:05', shape:'arrowUp' }])[0].time).toBe(at('2026-10-30T09:05:00Z'));
  });
  it('bar files become rows keyed in WIB, in order, without a bar missing a price', () => {
    const rows = barRows([{ columns:['t'], t:[at('2026-10-30T02:05:00Z'), at('2026-10-30T02:00:00Z')], o:[2, 1], h:[2, 1], l:[2, 1], c:[2, 1], v:[5, 4] },
      { columns:['t'], t:[at('2026-10-29T08:00:00Z')], o:[null], h:[1], l:[1], c:[1], v:[1] }], WIB);
    expect(rows.map(r => r.d)).toEqual(['2026-10-30T09:00', '2026-10-30T09:05']);
  });
});

describe('the daily session each candle shows (C4)', () => {
  const days = ['2026-10-28', '2026-10-29', '2026-10-30'];
  const keys = ['2026-10-29T09:00', '2026-10-29T13:30', '2026-10-30T09:00', '2026-10-30T13:30', '2026-10-30T15:00'];
  it('an earlier day shows itself on all its candles; the latest day only on its last candle, the day before on the others', () => {
    expect([...dayOfCandles(keys, days)]).toEqual([1, 1, 1, 1, 2]);
  });
  it('a latest day without its daily session yet shows the day before on every candle', () => {
    expect([...dayOfCandles(keys, days.slice(0, 2))]).toEqual([1, 1, 1, 1, 1]);
  });
  it('a candle before the first session shows none', () => {
    expect([...dayOfCandles(['2026-10-27T09:00', ...keys], days)].slice(0, 2)).toEqual([-1, 1]);
  });
  it('values go on the candles, markers once per day, sums count a day once', () => {
    const dayOf = dayOfCandles(keys, days), daily = [100, 200, 300];
    expect(onCandles(daily, dayOf)).toEqual([200, 200, 200, 200, 300]);
    expect(markerOnCandles([1, 1, 1], dayOf)).toEqual([1, null, null, null, 1]);
    expect([...firstOfDay(dayOf)]).toEqual([1, 0, 0, 0, 1]);
    const net = Float64Array.from(onCandles(daily, dayOf) as number[]);
    expect(countedCandles(0, 4, dayOf)).toEqual([0, 4]);                  // day 29 once, day 30 once
    expect(countedCandles(1, 3, dayOf)).toEqual([1]);                     // a range starting inside a day counts it
    expect([...cumulativeFrom(net, 0, dayOf)]).toEqual([200, 200, 200, 200, 500]);
    expect([...cumulativeFrom(net, 0)]).toEqual([200, 400, 600, 800, 1100]);   // the daily chart is unchanged
  });
});

describe('intraday drawings (C7.2 A) and VWAP', () => {
  it('a point sits on the candle that holds its time; one outside the candles keeps its time', () => {
    const keys = ['2026-10-30T09:00', '2026-10-30T10:00', '2026-10-30T11:00'];
    const doc = [{ points:[{ time:toChart('2026-10-30T10:35'), price:1 }, { time:toChart('2026-10-31T09:00'), price:2 }] }];
    const out = JSON.parse(onIntradayCandles(JSON.stringify(doc), keys));
    expect(out[0].points[0].time).toBe(toChart('2026-10-30T10:00'));
    expect(out[0].points[1].time).toBe(toChart('2026-10-31T09:00'));
  });
  it('a Session VWAP restarts every trading day on intraday bars', () => {
    const T = ['2026-10-29T15:00', '2026-10-29T15:05', '2026-10-30T09:00'];
    const B = { O:[10, 20, 30], H:[10, 20, 30], L:[10, 20, 30], C:[10, 20, 30], V:[1, 1, 1], T };
    const out: any = (F as any).vwap(B, { anchor:'Session', source:'hlc3', band_1_multiplier:1, bands_mode:'None' });
    const line = out.vwap || Object.values(out)[0];
    expect(line[2]).toBeCloseTo(30);                                     // a new day: only its own bar
    expect(line[1]).toBeCloseTo(15);
  });
});
