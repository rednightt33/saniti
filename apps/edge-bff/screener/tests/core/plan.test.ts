/* The planner (report TARGET ARCHITECTURE 6.10; TEST PLAN 10b.6 "Planner property test", "Per-condition counts",
   "Stage order", "Budget"): over random definitions (ALL, ANY, AT LEAST; 1-20 conditions mixing S1, S2 and S3 stages;
   random PASS / FAIL / NA cells; many seeds) the pruned run equals brute force and the exhaustive run for the match set,
   the near set, every displayed cell, met and na_count; every condition marked exhaustive has the exhaustive run's
   counts; permuting the S3 order changes nothing; ANY never prunes; the cost model and the budget estimate behave. */
import { describe, expect, it } from 'vitest';
import type { Cell, Logic } from '../../src/core/contract.ts';
import { needOf, rowStatus } from '../../src/core/match.ts';
import { PlanCancelledError, costEstimate, costTracker, orderS3, runPlan } from '../../src/core/plan.ts';
import type { ConditionStage, PlanCondition } from '../../src/core/plan.ts';
import { rng } from './helpers.ts';

type Status = 'pass' | 'fail' | 'na';
interface Case { tickers: string[]; ids: string[]; stages: ConditionStage[]; grid: Status[][]; logic: Logic; atLeast?: number }

function randomCase(seed: number): Case {
  const r = rng(seed), T = 1 + Math.floor(r() * 40), K = 1 + Math.floor(r() * 20);
  const pPass = 0.15 + r() * 0.8, pNa = r() * 0.2;
  const tickers = Array.from({ length: T }, (_, i) => `T${String(i).padStart(3, '0')}`);
  const ids = Array.from({ length: K }, (_, k) => k.toString(36));
  const stages = ids.map(() => (['S1', 'S2', 'S3', 'S3', 'S3'] as const)[Math.floor(r() * 5)]);
  const grid = tickers.map(() => ids.map((): Status => { const x = r(); return x < pNa ? 'na' : x < pNa + pPass ? 'pass' : 'fail' }));
  const logic = (['all', 'any', 'at_least'] as const)[Math.floor(r() * 3)];
  return { tickers, ids, stages, grid, logic, ...(logic === 'at_least' ? { atLeast: 1 + Math.floor(r() * (K + 2)) } : {}) };
}
function conditionsOf(c: Case, costs: number[], calls?: Map<string, number>): PlanCondition[] {
  return c.ids.map((id, k) => ({
    id, stage: c.stages[k], predictedMs: c.stages[k] === 'S3' ? costs[k] : 0,
    evaluate: (ticker: string): Cell => {
      calls?.set(id, (calls.get(id) ?? 0) + 1);
      const s = c.grid[c.tickers.indexOf(ticker)][k];
      return { id, status: s, eval_date: '2026-10-27', value: s === 'na' ? null : k, reason: s === 'na' ? 'INSUFFICIENT_HISTORY' : null, remark: null };
    },
  }));
}
/** The brute-force answer: every cell evaluated, the one near rule. */
function bruteForce(c: Case) {
  const need = needOf(c.logic, c.atLeast, c.ids.length), rows = new Map<string, { status: string; met: number; na: number }>();
  c.tickers.forEach((t, i) => {
    const met = c.grid[i].filter(s => s === 'pass').length, na = c.grid[i].filter(s => s === 'na').length, st = rowStatus(met, need);
    if (st) rows.set(t, { status: st, met, na });
  });
  return { need, rows };
}

describe('runPlan: pruned output = exhaustive output = brute force (property test)', () => {
  it('for 600 random definitions over ALL, ANY and AT LEAST with 1-20 conditions', () => {
    let prunedTotal = 0, sawNear = 0;
    for (let seed = 1; seed <= 600; seed++) {
      const c = randomCase(seed), r = rng(seed * 7919);
      const costs = c.ids.map(() => Math.floor(r() * 5));                                                    // ties on purpose
      const pruned = runPlan({ tickers: c.tickers, conditions: conditionsOf(c, costs), logic: c.logic, atLeast: c.atLeast, exhaustive: false });
      const full = runPlan({ tickers: c.tickers, conditions: conditionsOf(c, costs), logic: c.logic, atLeast: c.atLeast, exhaustive: true });
      const bf = bruteForce(c);
      // same rows, statuses, met, na_count and every displayed cell
      expect(pruned.rows).toEqual(full.rows);
      expect(pruned.need).toBe(bf.need);
      expect(new Map(pruned.rows.map(x => [x.ticker, { status: x.status, met: x.met, na: x.na_count }]))).toEqual(bf.rows);
      for (const row of pruned.rows) {
        expect(row.cells.map(x => x.id)).toEqual(c.ids);                                                    // complete, in condition order
        expect(row.cells.every(x => x.status !== 'not_evaluated')).toBe(true);
      }
      // a condition marked exhaustive carries the exhaustive run's counts; S1 and S2 are always exhaustive
      for (const [k, id] of c.ids.entries()) {
        const p = pruned.summaries[id], f = full.summaries[id];
        expect(f.exhaustive).toBe(true);
        if (p.exhaustive) expect([p.evaluated, p.passed, p.na]).toEqual([f.evaluated, f.passed, f.na]);
        else expect(p.evaluated).toBeLessThan(c.tickers.length);
        if (c.stages[k] !== 'S3') expect(p.exhaustive).toBe(true);
      }
      if (c.logic === 'any' || bf.need <= 1) expect(pruned.pruned).toBe(0);                                // no safe pruning
      prunedTotal += pruned.pruned; sawNear += pruned.rows.filter(x => x.status === 'near').length;
    }
    expect(prunedTotal).toBeGreaterThan(1000);                                                               // the rule did prune
    expect(sawNear).toBeGreaterThan(100);
  });

  it('permuting the S3 order changes no result', () => {
    for (let seed = 1000; seed < 1200; seed++) {
      const c = randomCase(seed), r = rng(seed);
      const a = runPlan({ tickers: c.tickers, conditions: conditionsOf(c, c.ids.map(() => r())), logic: c.logic, atLeast: c.atLeast, exhaustive: false });
      const b = runPlan({ tickers: c.tickers, conditions: conditionsOf(c, c.ids.map(() => r())), logic: c.logic, atLeast: c.atLeast, exhaustive: false });
      expect(a.rows).toEqual(b.rows);
      expect(a.need).toBe(b.need);
    }
  });

  it('ALL prunes at the second failure; S3 conditions run cheapest first on the survivors only', () => {
    const c: Case = { tickers: ['A', 'B', 'C'], ids: ['x', 'y', 'z'], stages: ['S3', 'S3', 'S3'], logic: 'all',
      grid: [['fail', 'fail', 'pass'], ['pass', 'fail', 'pass'], ['pass', 'pass', 'pass']] };
    const calls = new Map<string, number>();
    const out = runPlan({ tickers: c.tickers, conditions: conditionsOf(c, [1, 2, 3], calls), logic: 'all', exhaustive: false, cancelled: () => false });
    expect(out.explain.order).toEqual(['x', 'y', 'z']);
    expect(Object.fromEntries(calls)).toEqual({ x: 3, y: 3, z: 2 });                                         // A pruned after its second failure
    expect([out.pruned, out.rows.map(r => [r.ticker, r.status])]).toEqual([1, [['B', 'near'], ['C', 'match']]]);
    expect([out.summaries.z.evaluated, out.summaries.z.exhaustive]).toEqual([2, false]);
    expect(out.explain.stages.map(s => [s.name, s.in, s.out])).toEqual([['S1', 3, 3], ['S2', 3, 3], ['S3', 3, 2], ['S4', 2, 2]]);
  });

  it('no condition: need 0, every survivor a match row with met 0 (universe_only)', () => {
    const out = runPlan({ tickers: ['A', 'B'], conditions: [], logic: 'all', exhaustive: false });
    expect(out.rows.map(r => [r.ticker, r.status, r.met, r.need, r.cells])).toEqual([['A', 'match', 0, 0, []], ['B', 'match', 0, 0, []]]);
  });

  it('a cancelled plan throws between tickers; a repeated condition id is a programming error', () => {
    const c = randomCase(5);
    let n = 0;
    expect(() => runPlan({ tickers: c.tickers, conditions: conditionsOf(c, c.ids.map(() => 1)), logic: c.logic, atLeast: c.atLeast, exhaustive: false, cancelled: () => ++n > 3 })).toThrow(PlanCancelledError);
    const dup = conditionsOf(c, c.ids.map(() => 1));
    expect(() => runPlan({ tickers: c.tickers, conditions: [...dup, dup[0]], logic: 'all', exhaustive: false })).toThrow(RangeError);
  });

  it('explains ANY: no safe pruning, and reports the cache hits it is given', () => {
    const c = randomCase(9);
    const out = runPlan({ tickers: c.tickers, conditions: conditionsOf(c, c.ids.map(() => 1)), logic: 'any', exhaustive: false, cacheHits: () => 42 });
    expect([out.explain.note, out.explain.cache_hits, out.pruned]).toEqual(['ANY: no safe pruning', 42, 0]);
  });
});

describe('order, cost model and budget', () => {
  const pc = (id: string, stage: ConditionStage, predictedMs: number): PlanCondition => ({ id, stage, predictedMs, evaluate: () => { throw new Error('not called') } });
  it('orders S3 by predicted cost, ties by id', () => {
    expect(orderS3([pc('b', 'S3', 2), pc('a', 'S3', 2), pc('c', 'S3', 1)]).map(c => c.id)).toEqual(['c', 'a', 'b']);
  });
  it('estimates the worst case over every survivor and names the costliest S3 condition (null without S3)', () => {
    expect(costEstimate([pc('a', 'S2', 0), pc('b', 'S3', 0.5), pc('c', 'S3', 2)], 300)).toEqual({ needed_ms: 750, costliest: 'c' });
    expect(costEstimate([pc('a', 'S2', 0), pc('x', 'S1', 0)], 300)).toEqual({ needed_ms: 0, costliest: null });
  });
  it('predicts (length for O(N·n), else 1) x bars x ns per bar-length, then learns from measurements (EWMA)', () => {
    const t = costTracker(5.96, 0.5);
    expect(t.predict('k', 'O(N·n)', 1000, 2000)).toBeCloseTo(1000 * 2000 * 5.96 / 1e6, 12);
    expect(t.predict('k', 'O(N)', 1000, 2000)).toBeCloseTo(2000 * 5.96 / 1e6, 12);
    t.observe('k', 4, 2000, 1);                                                                             // 2000 ns per bar
    expect(t.predict('k', 'O(N)', 1, 2000)).toBeCloseTo(4, 12);
    t.observe('k', 8, 2000, 1);                                                                             // 4000 -> mean 3000
    expect(t.predict('k', 'O(N)', 1, 1000)).toBeCloseTo(3, 12);
    expect(t.predict('other', 'O(N)', 1, 1000)).toBeCloseTo(5.96e-3, 12);
    expect(() => costTracker(0, 0.5)).toThrow(RangeError);
    expect(() => costTracker(1, 0)).toThrow(RangeError);
  });
});
