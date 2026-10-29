/* Match and the one near rule (report TARGET ARCHITECTURE 6.9; TEST PLAN 10b.6 "ALL, ANY, AT LEAST", "One near rule"):
   need = core entryNeed; met counts PASS only; near = !match && need >= 2 && met == need - 1; the planner's pruning
   threshold (report 6.10). */
import { describe, expect, it } from 'vitest';
import { entryNeed } from '../../../backtest/src/core/conditions.ts';
import { countCells, isMatch, isNear, needOf, previewStatus, rowStatus } from '../../src/core/match.ts';
import { canPrune, pruneThreshold } from '../../src/core/plan.ts';

describe('need, match and near', () => {
  it('need is the backtest core entryNeed: all, any, at_least (above the active count means all), 0 without conditions', () => {
    expect([needOf('all', undefined, 3), needOf('any', undefined, 3), needOf('at_least', 2, 3), needOf('at_least', 5, 3), needOf('all', undefined, 1)]).toEqual([3, 1, 2, 3, 1]);
    for (const [l, k, n] of [['all', undefined, 4], ['any', undefined, 4], ['at_least', 3, 4]] as const) expect(needOf(l, k, n)).toBe(entryNeed(l, k, n));
    expect(needOf('all', undefined, 0)).toBe(0);
  });
  it('one near rule: a miss by one, only when need >= 2', () => {
    expect([rowStatus(3, 3), rowStatus(2, 3), rowStatus(1, 3)]).toEqual(['match', 'near', null]);
    expect([rowStatus(1, 1), rowStatus(0, 1)]).toEqual(['match', null]);              // need 1: no near miss
    expect([rowStatus(1, 2), rowStatus(0, 2)]).toEqual(['near', null]);
    expect(rowStatus(0, 0)).toBe('match');                                            // universe_only lists the universe
    expect([isMatch(2, 2), isNear(2, 2), isNear(0, 1)]).toEqual([true, false, false]);
  });
  it('the preview status uses the same rule, and outside_universe first', () => {
    expect([previewStatus(true, 2, 2), previewStatus(true, 1, 2), previewStatus(true, 0, 2), previewStatus(false, 2, 2)]).toEqual(['match', 'near', 'fail', 'outside_universe']);
  });
  it('met counts PASS only; NA is counted apart and never adds', () => {
    const cells = [{ status: 'pass' }, { status: 'na' }, { status: 'fail' }, { status: 'not_evaluated' }, { status: 'pass' }] as const;
    expect(countCells(cells)).toEqual({ met: 2, na_count: 1 });
  });
});

describe('pruning threshold (report 6.10)', () => {
  it('theta = need - 1 from need 2, else need; prune iff m + r < theta', () => {
    expect([pruneThreshold(1), pruneThreshold(2), pruneThreshold(5)]).toEqual([1, 1, 4]);
    // ALL of 3 (need 3, theta 2): after two failures (m 0, r 1) it is pruned, after one (m 0, r 2) it is not
    expect([canPrune(0, 1, 2), canPrune(0, 2, 2), canPrune(1, 1, 2)]).toEqual([true, false, false]);
    // ANY (need 1, theta 1): only a ticker with nothing left and no pass, i.e. nothing to save
    expect([canPrune(0, 1, 1), canPrune(0, 0, 1)]).toEqual([false, true]);
  });
});
