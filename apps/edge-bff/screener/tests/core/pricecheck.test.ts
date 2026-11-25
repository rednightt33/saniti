/* EXEC-PRICE-DISTORTION: the two checks on the real cases of 2026-11-24 (dev, read-only; verification/price_break_basis/):
   the closes either side of each ex-date as stored now (pulled again: adjusted) and before the pull (raw), the WGSH bar,
   the one-tick rule, the small actions. The publisher's Python twin is held to the same cases
   (apps/terminal-publisher/tests/test_price_check.py). */
import { describe, expect, it } from 'vitest';
import { capAnomalies, checkActions, termsFactor, verdictOf } from '../../src/core/pricecheck';

describe('check 2: the ex-date jump against the action', () => {
  it('reads the stocks pulled again as adjusted and the same actions before the pull as raw', () => {
    // the terms in idx_event_annotation (ratio old, new, exercise price) and the stored closes, dev 2026-11-24; the raw
    // close before the pull is the stored one times the factor (VKTR 835, AHAP 88, FORU 2560 as ERRORS D22 recorded)
    const cases: [string, number, number, number, number, number, number][] = [
      // ticker, old, new, exercise, before (now), on ex, before (raw, before the pull)
      ['VKTR', 35, 12, 200, 626.91466, 670, 835], ['AHAP', 7, 5, 50, 72.1666, 78, 88],
      ['BUVA', 4, 1, 250, 521.99955, 520, 590], ['FORU', 100, 46235, 126, 131.25376, 176, 2560]];
    for (const [t, old, nw, x, now, ex, raw] of cases) {
      const f = termsFactor('RIGHT_ISSUE', old, nw, ex, x)!;          // the same factor either way: from the ex-date's close
      expect(f, t).toBeGreaterThan(1.1);
      expect(verdictOf(now, ex, f).verdict, `${t} now`).toBe('adjusted');
      expect(verdictOf(raw, ex, f).verdict, `${t} before the pull`).toBe('raw');
    }
    expect(verdictOf(422.5, 384, termsFactor('STOCK_SPLIT', 1, 2, 384)).verdict).toBe('adjusted');
    expect(verdictOf(845, 384, termsFactor('STOCK_SPLIT', 1, 2, 384)).verdict).toBe('raw');
    expect(termsFactor('RIGHT_ISSUE', 100, 46235, 176, 126)).toBeGreaterThan(19);   // FORU: a huge action stays huge
  });
  it('a 50 % drop on a split is raw whatever the day did; a real crash without an action is not this check', () => {
    expect(verdictOf(1000, 550, 2).verdict).toBe('raw');       // split 1:2, the stock +10 % that day
    expect(verdictOf(500, 550, 2).verdict).toBe('adjusted');
  });
  it('an action under 10 % is small (its size named), one without a close or a term is unknown', () => {
    expect(verdictOf(336, 334, termsFactor('BONUS_SHARE', 30, 1, 334))).toEqual({ verdict:'small', jump:336 / 334 });   // PSSI 3.3 %
    expect(verdictOf(null, 334, 1.2).verdict).toBe('unknown');
    expect(termsFactor('RIGHT_ISSUE', 7, 5, 78, null)).toBeNull();
  });
  it('checkActions finds the sessions either side of an ex-date on a day without a session', () => {
    const dates = ['2026-10-06', '2026-10-07', '2026-10-10'], closes = [100, 99, 50];
    const r = checkActions(dates, closes, [{ ex:'2026-10-08', type:'STOCK_SPLIT', ratio_old:1, ratio_new:2 }, { ex:'2026-10-08', type:'DIVIDEND', ratio_old:null, ratio_new:null }]);
    expect(r).toEqual([{ ex:'2026-10-08', type:'STOCK_SPLIT', factor:2, verdict:'raw', jump:99 / 50 }]);
  });
});

describe('check 1: the 35 % cap', () => {
  it('marks WGSH 2026-03-31 and 2026-04-01 and nothing around them', () => {
    const dates = ['2026-03-27', '2026-03-30', '2026-03-31', '2026-04-01', '2026-04-02'], closes = [132, 125, 65, 128, 117];
    expect(capAnomalies(dates, closes).map(a => a.date)).toEqual(['2026-03-31', '2026-04-01']);
  });
  it('leaves a legitimate ARA (+35 % of Rp11-200 rounded down), a one-tick move at Rp10 or below and a recorded ex-date', () => {
    expect(capAnomalies(['a', 'b'], [100, 135])).toEqual([]);
    expect(capAnomalies(['a', 'b', 'c'], [2, 3, 2])).toEqual([]);                  // Rp2 -> Rp3 -> Rp2: one tick each
    expect(capAnomalies(['a', 'b'], [9, 4]).map(x => x.date)).toEqual(['b']);       // five ticks down
    expect(capAnomalies(['2026-10-13', '2026-10-14'], [845, 384], ['2026-10-14'])).toEqual([]);   // PBSA's split: check 2's
    expect(capAnomalies(['2026-10-13', '2026-10-15'], [845, 384], ['2026-10-14'])).toEqual([]);   // ex on a day off
  });
});

describe('a rights issue above the market (re-check 2026-11-25, finding A)', () => {
  it('cannot be told: small, no factor, so no size; a reverse split below 1 still reads', async () => {
    const { checkActions, measurable } = await import('../../src/core/pricecheck.ts');
    const dates = ['2026-01-05', '2026-01-06'];
    const [c] = checkActions(dates, [101, 100], [{ ex: '2026-01-06', type: 'RIGHT_ISSUE', ratio_old: 2, ratio_new: 1, exercise: 140 }]);
    expect([c.verdict, c.factor]).toEqual(['small', null]);
    expect(measurable('REVERSE_SPLIT', 0.1)).toBe(true);
    const [r] = checkActions(dates, [100, 1000], [{ ex: '2026-01-06', type: 'REVERSE_SPLIT', ratio_old: 10, ratio_new: 1 }]);
    expect(r.verdict).toBe('raw');
  });
});
