// EXEC-FI-TERMINAL (user go 2026-11-01, "nomor 3 juga pakai your advice"): a bond on a stock chart carries its last value
// at most three sessions, faded and dated; a longer gap breaks the line; nothing is invented before its first value.
import { describe, expect, it } from 'vitest';
import { alignCarry, CARRY_SESSIONS } from '../../src/data/live';

const S = ['2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23', '2026-10-26', '2026-10-27', '2026-10-28'];

describe('bond compare series on the stock sessions', () => {
  it('takes the bond value of the same date and carries it up to three sessions, marked with its date', () => {
    const rows = [{ d:'2026-10-20', c:7.1 }, { d:'2026-10-27', c:7.3 }];          // traded 20 Oct, then 27 Oct only
    const out = alignCarry(S, rows, S, CARRY_SESSIONS, 'faded');
    expect(CARRY_SESSIONS).toBe(3);
    expect(out[0]).toEqual({ time:'2026-10-20', value:7.1 });                       // nothing before the first value
    expect(out.slice(1, 4)).toEqual(['2026-10-21', '2026-10-22', '2026-10-23'].map(time =>
      ({ time, value:7.1, color:'faded', customValues:{ carriedFrom:'2026-10-20' } })));
    expect(out[4]).toEqual({ time:'2026-10-26' });                                  // a fourth session: the line breaks
    expect(out[5]).toEqual({ time:'2026-10-27', value:7.3 });
    expect(out[6]).toEqual({ time:'2026-10-28', value:7.3, color:'faded', customValues:{ carriedFrom:'2026-10-27' } });
  });
  it('a bond value on a date the stock did not trade is carried, not shown as the next session own value', () => {
    const out = alignCarry(['2026-10-23', '2026-10-27'], [{ d:'2026-10-23', c:7 }, { d:'2026-10-26', c:7.2 }]);
    expect(out[1]).toMatchObject({ time:'2026-10-27', value:7.2, customValues:{ carriedFrom:'2026-10-26' } });
  });
  it('a weekly candle takes any value of its week as its own', () => {
    const weeks = ['2026-10-19', '2026-10-26'], ends = ['2026-10-23', '2026-10-30'];
    const out = alignCarry(weeks, [{ d:'2026-10-21', c:7 }, { d:'2026-10-28', c:7.4 }], ends);
    expect(out).toEqual([{ time:'2026-10-19', value:7 }, { time:'2026-10-26', value:7.4 }]);
  });
});
