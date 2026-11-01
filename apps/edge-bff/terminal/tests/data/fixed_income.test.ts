// EXEC-FI-TERMINAL (user go 2026-11-01, "nomor 3 juga pakai your advice"): a bond added to a stock chart carries its last
// value at most three sessions, marked with its date; a longer gap breaks the line; nothing is invented before its first
// value. The rule lives in alignCandlesCarry (timeframe.ts), the asset loader's alignment for a bond (live.ts loadAsset).
import { describe, expect, it } from 'vitest';
import { alignCandlesCarry, buckets, CARRY_SESSIONS } from '../../src/data/timeframe';
import { legendBp } from '../../src/app/assets';
import type { PriceRow } from '../../src/data/worker';

const S = ['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23', '2026-10-26', '2026-10-27', '2026-10-28'];
const row = (d: string, c: number, o = c, h = c, l = c): PriceRow => ({ d, o, h, l, c, v:null } as any);
const flat = (time: string, c: number, carriedFrom?: string) => ({ time, open:c, high:c, low:c, close:c, ...(carriedFrom ? { carriedFrom } : {}) });

describe('a bond on the stock sessions (daily)', () => {
  it('takes the bond row of the same date and carries it up to three sessions, marked with its date', () => {
    const out = alignCandlesCarry(S, buckets(S, 'D'), [row('2026-10-20', 7.1, 7, 7.2, 6.9), row('2026-10-27', 7.3)]);
    expect(CARRY_SESSIONS).toBe(3);
    expect(out[0]).toEqual({ time:'2026-10-20', open:7, high:7.2, low:6.9, close:7.1 });   // nothing before the first value
    expect(out.slice(1, 4)).toEqual(['2026-10-21', '2026-10-22', '2026-10-23'].map(t => flat(t, 7.1, '2026-10-20')));
    expect(out[4]).toMatchObject({ time:'2026-10-26', gap:true });                     // a fourth session: the line breaks
    expect(Number.isNaN(out[4].close)).toBe(true);
    expect(out[5]).toEqual(flat('2026-10-27', 7.3));
    expect(out[6]).toEqual(flat('2026-10-28', 7.3, '2026-10-27'));
  });
  it('a bond row on a date the bourse was closed is carried from that date, not shown as the next session own value', () => {
    const d = ['2026-10-23', '2026-10-27'];
    const out = alignCandlesCarry(d, buckets(d, 'D'), [row('2026-10-23', 7), row('2026-10-26', 7.2)]);
    expect(out[1]).toEqual(flat('2026-10-27', 7.2, '2026-10-26'));
  });
  it('a longer allowance is a parameter, not a second rule', () => {
    const out = alignCandlesCarry(S, buckets(S, 'D'), [row('2026-10-19', 7)], 5);
    expect(out.filter(b => b.carriedFrom).length).toBe(5);
    expect(out.filter(b => b.gap).length).toBe(2);
  });
});

describe('a bond on weekly candles', () => {
  const W = [...S, '2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06'];
  it('a week with any own session is the bond own candle (its high and low over the week)', () => {
    const out = alignCandlesCarry(W, buckets(W, 'W'), [row('2026-10-21', 7, 7, 7.2, 6.8), row('2026-10-28', 7.4, 7.3, 7.5, 7.1)]);
    expect(out[0]).toEqual({ time:'2026-10-19', open:7, high:7.2, low:6.8, close:7 });
    expect(out[1]).toEqual({ time:'2026-10-26', open:7.3, high:7.5, low:7.1, close:7.4 });   // 26 Oct carried: not in the week's numbers
  });
  it('a week of carried sessions only is marked carried; a week of no value is a gap', () => {
    const out = alignCandlesCarry(W, buckets(W, 'W'), [row('2026-10-23', 7)]);
    expect(out[0]).toEqual({ time:'2026-10-19', open:7, high:7, low:7, close:7 });
    expect(out[1]).toEqual(flat('2026-10-26', 7, '2026-10-23'));                       // 26-28 Oct carried, then a gap
    expect(out[2]).toMatchObject({ time:'2026-11-02', gap:true });
  });
});

describe('legendBp: a yield moves in basis points', () => {
  const bars = [flat('2026-10-20', 7.1), flat('2026-10-21', 7.1, '2026-10-20'),
                { time:'2026-10-22', open:NaN, high:NaN, low:NaN, close:NaN, gap:true }, flat('2026-10-23', 7.25)];
  it('change from the previous candle with a value, gaps skipped', () => {
    expect(legendBp(bars, 1, 'close', false)).toBeCloseTo(0);
    expect(legendBp(bars, 2, 'close', false)).toBeNull();
    expect(legendBp(bars, 3, 'close', false)).toBeCloseTo(15);
    expect(legendBp(bars, 0, 'close', false)).toBeNull();
  });
  it('in Return mode the change from the first candle, never a percent of the yield', () => {
    expect(legendBp(bars, 3, 'close', true)).toBeCloseTo(15);
  });
});
