/* Re-check 2026-11-25 (rule 8, EXEC-PRICE-DISTORTION; ERRORS M559 "Class" lists the 1D change remark): the 1-day change
   note is worded by the break's kind, and found by last_session (the break between the last two sessions, an ex date on
   a day without a session included), or on an older worker's row by the date of the last bar. The CSV names the kind. */
import { describe, expect, it } from 'vitest';
import { chg1dBreakText, remarkCsv } from '../../src/texts.ts';
import { distortionRemarks } from '../../src/core/universe.ts';

const R = (o: object) => ({ code: 'PRICE_BREAK', action: 'STOCK_SPLIT', ex_date: '2026-03-31', ratio_old: 1, ratio_new: 2, close_ratio: 0.52, ...o }) as never;

describe('the 1D change note by kind', () => {
  it('words an anomaly, an uncertain break and an unadjusted one each by what it is', () => {
    expect(chg1dBreakText([R({ kind: 'anomaly', action: 'PRICE_ANOMALY', ratio_old: null, ratio_new: null })], '2026-03-31')).toBe('Distorted: the last session 2026-03-31 moved −48.0% with no corporate action recorded (a price anomaly).');
    expect(chg1dBreakText([R({ kind: 'uncertain', action: 'BONUS_SHARE' })], '2026-03-31')).toMatch(/^Possibly distorted: .* too small to confirm/);
    expect(chg1dBreakText([R({ kind: 'unadjusted' })], '2026-03-31')).toMatch(/not adjusted in the price history\.$/);
    expect(chg1dBreakText([R({})], '2026-03-31')).toMatch(/not adjusted/);              // a remark from before the kinds
    expect(chg1dBreakText([R({ kind: 'unadjusted' })], '2026-04-01')).toBeNull();
  });
  it('finds a break whose ex date has no session through last_session', () => {
    expect(chg1dBreakText([R({ kind: 'unadjusted', ex_date: '2026-03-29', last_session: true })], '2026-03-30')).toMatch(/of 2026-03-29/);
  });
  it('the core marks the break that falls between the last two sessions, and no other', () => {
    const dates = ['2026-03-26', '2026-03-27', '2026-03-30'], closes = [200, 202, 101];
    const on = distortionRemarks([{ ticker: 'X', type: 'STOCK_SPLIT', ex_date: '2026-03-29', ratio_old: 1, ratio_new: 2 }], dates, closes, { boundary: '2026-09-12' });
    expect(on.map(r => [r.kind, r.ex_date, r.last_session])).toEqual([['unadjusted', '2026-03-29', true]]);
    const old = distortionRemarks([{ ticker: 'X', type: 'STOCK_SPLIT', ex_date: '2026-03-27', ratio_old: 1, ratio_new: 2 }], dates, [400, 202, 202], { boundary: '2026-09-12' });
    expect(old.map(r => [r.kind, r.last_session])).toEqual([['unadjusted', undefined]]);
  });
  it('the CSV names the kind', () => {
    expect(remarkCsv([R({ kind: 'anomaly', action: 'PRICE_ANOMALY' })])).toBe('PRICE_BREAK anomaly PRICE_ANOMALY 2026-03-31');
  });
});
