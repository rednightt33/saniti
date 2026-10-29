/* The page's display of a timestamp (src/format.ts timeText; ERRORS M302): every ISO 8601 spelling a source writes is
   shown the same way, in WIB, on the head's data line, the preview's Data facts and a saved screen's date. The live
   dev publication of 2026-10-29 wrote '2026-10-29T12:59:56.101946+00:00' (the publisher's isoformat), which the old
   data line, made only for 'Z', printed raw. */
import { describe, expect, it } from 'vitest';
import { timeText } from '../../src/format.ts';
import { dataLine } from '../../src/texts.ts';

describe('timeText', () => {
  it('reads every spelling of the same instant to the same WIB time', () => {
    for (const s of ['2026-10-29T12:59:56.101946+00:00', '2026-10-29T12:59:56Z', '2026-10-29T12:59:56.1Z',
      '2026-10-29T12:59:56', '2026-10-29 12:59:56+00:00', '2026-10-29T19:59:56+07:00', '2026-10-29T12:59+0000'])
      expect(timeText(s), s).toBe('2026-10-29 19:59 WIB');
  });
  it('takes the WIB date, not the UTC one, for a screen saved in the late UTC evening', () => {
    expect(timeText('2026-10-28T23:30:00+00:00', true)).toBe('2026-10-29');
    expect(timeText('2026-10-28T16:59:59Z', true)).toBe('2026-10-28');
  });
  it('keeps a text that is not a timestamp and marks a missing one', () => {
    expect(timeText('not yet')).toBe('not yet');
    expect(timeText('2026-13-45T99:99:99Z')).toBe('2026-13-45T99:99:99Z');
    expect(timeText(null)).toBe('—');
    expect(timeText('')).toBe('—');
  });
});

describe('the data line', () => {
  it('shows the publisher\'s timestamp as a readable WIB time, never the raw text', () => {
    const line = dataLine(844, '2026-10-29', '2026-10-29T12:59:56.101946+00:00');
    expect(line).toBe('IDX equities (844 listings) · close 2026-10-29 · published 2026-10-29 19:59 WIB');
    expect(line).not.toMatch(/\+00:00|\.\d{3,}|T\d/);
  });
});
