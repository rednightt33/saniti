// T9 (user 2026-10-26): corporate-action detail values as the tooltip shows them; a blank value is "Unavailable".
import { describe, expect, it } from 'vitest';
import { detailText, longDates, UNAVAILABLE } from '../../src/data/live';

describe('detailText', () => {
  it('writes a blank or missing value as Unavailable', () => {
    for (const v of [null, undefined, '']) expect(detailText(v, 'idr')).toBe(UNAVAILABLE);
  });
  it('formats amounts, percentages, shares and dates like the reference tooltip', () => {
    expect(detailText(25, 'idr_per_share')).toBe('Rp 25 / share');
    expect(detailText(1464, 'idr')).toBe('Rp 1,464');
    expect(detailText(0.3861, 'pct')).toBe('0.39%');
    expect(detailText(238442293, 'shares')).toBe('238,442,293');
    expect(detailText('2026-08-28', 'date')).toBe('28 August 2026');
    expect(detailText('1 : 5', 'text')).toBe('1 : 5');
  });
});

/* EXEC-TERMINAL-UI-1026 U4: dates in event labels read "dd MMMM yyyy" (English), wherever they sit in the text */
describe('longDates', () => {
  it('writes every ISO date of a label as day, month name and year', () => {
    expect(longDates('2025-12-03')).toBe('03 December 2025');
    expect(longDates('2025-12-10 – 2026-06-10')).toBe('10 December 2025 – 10 June 2026');
    expect(detailText('2024-07-11 10:30', 'text')).toBe('11 July 2024 10:30');
    expect(longDates('2026-13-01 and BBCADRCM6A')).toBe('2026-13-01 and BBCADRCM6A');   // not a date: unchanged
  });
});
