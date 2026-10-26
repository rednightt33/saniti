// T9 (user 2026-10-26): corporate-action detail values as the tooltip shows them; a blank value is "Unavailable".
import { describe, expect, it } from 'vitest';
import { detailText, UNAVAILABLE } from '../../src/data/live';

describe('detailText', () => {
  it('writes a blank or missing value as Unavailable', () => {
    for (const v of [null, undefined, '']) expect(detailText(v, 'idr')).toBe(UNAVAILABLE);
  });
  it('formats amounts, percentages, shares and dates like the reference tooltip', () => {
    expect(detailText(25, 'idr_per_share')).toBe('Rp 25 / share');
    expect(detailText(1464, 'idr')).toBe('Rp 1,464');
    expect(detailText(0.3861, 'pct')).toBe('0.39%');
    expect(detailText(238442293, 'shares')).toBe('238,442,293');
    expect(detailText('2026-08-28', 'date')).toBe('2026-08-28');
    expect(detailText('1 : 5', 'text')).toBe('1 : 5');
  });
});
