/* EXEC-SCREENER-QUICK-UI (user 2026-11-25): the close date in the data line as DD MMMM YYYY, the row's remarks as one
   badge on the ticker (the Remark column removed), the Sector column off by default and offered in "Add column". */
import { describe, expect, it } from 'vitest';
import { dataLine, longDate, rowRemarkLabel, rowRemarkTitle } from '../../src/texts.ts';
import { LOCAL_COLUMNS, chosenColumns, shownLocal } from '../../src/extra-columns.ts';

describe('quick UI of 2026-11-25', () => {
  it('writes the close date as DD MMMM YYYY, leaves anything else as it is', () => {
    expect(longDate('2026-11-24')).toBe('24 November 2026');
    expect(longDate('2026-01-05')).toBe('05 January 2026');
    expect(longDate('not a date')).toBe('not a date');
    expect(dataLine(862, '2026-11-24', '2026-11-25T00:35:00Z')).toContain('close 24 November 2026 · published ');
  });
  it('one title for every remark of a row: its badge, date and why', () => {
    const t = rowRemarkTitle([
      { code: 'PRICE_BREAK', kind: 'unadjusted', action: 'STOCK_SPLIT', ex_date: '2026-10-14', ratio_old: 1, ratio_new: 2, close_ratio: 0.5, effect: 1 } as never,
      { code: 'STALE', last_bar_date: '2026-08-21' } as never,
    ]);
    expect(t).toMatch(/^Price break · 2026-10-14\n/);
    expect(t).toContain('\n\nStale · 2026-08-21\n');
  });
  it('the badge names each kind of remark once, the title every remark (re-check round 3, G3-1)', () => {
    const a = (ex: string, r: number) => ({ code: 'PRICE_BREAK', kind: 'anomaly', ex_date: ex, close_ratio: r } as never);
    const two = [a('2026-03-31', 0.52), a('2026-04-01', 1.969)];
    expect(rowRemarkLabel(two)).toBe('Price anomaly');
    expect(rowRemarkTitle(two).match(/^Price anomaly · /gm)).toHaveLength(2);
    expect(rowRemarkLabel([...two, { code: 'STALE', last_bar_date: '2026-08-21' } as never])).toBe('Price anomaly, Stale');
  });
  it('Sector is a column of the picker, not shown until chosen', () => {
    expect(LOCAL_COLUMNS.map(c => [c.id, c.label])).toEqual([['local:sector', 'Sector']]);
    expect(shownLocal()).toEqual([]);
    expect(chosenColumns()).toEqual([]);
  });
});
