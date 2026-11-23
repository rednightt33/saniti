/* EXEC-MU-ACCOUNTS step 3 (the user's sequence of 2026-11-23): the lab Flow indicator's registration point. A formula
   registered from src/lab/index.ts with registerFlow and flowKit computes as the released formulas do: the wrap sets
   the call's rows before the shared helpers read them (a formula called after another context's call reads its own
   rows), and an id that already has a formula, or that is no FL id, is refused. */
import { describe, expect, it } from 'vitest';
import { FLOW, computeFlow, flowKit as K, flowRows, registerFlow, type FlowContext, type FlowParams } from '../../src/calc/flow';

type Row = { d: string; b: string; i: string; m: string; bv: number; sv: number; bl: number; sl: number; bf?: number | null; sf?: number | null };
const r = (d: string, b: string, bv: number, sv: number, bl: number, sl: number): Row => ({ d, b, i:'Domestic', m:'Regular', bv, sv, bl, sl, bf:1, sf:1 });
function ctx(rows: Row[], dates: string[]): FlowContext {
  const at = new Map(dates.map((d, k) => [d, k]));
  return { rows:flowRows(rows, dates.length, d => at.get(d) ?? -1), dates, close:dates.map(() => 100), volume:dates.map(() => 1000), insider:[], classification:{} };
}
const D = ['2026-01-05', '2026-01-06', '2026-01-07', '2026-01-08'];
const A = ctx([r(D[0], 'AA', 100, 40, 2, 1), r(D[1], 'AA', 60, 0, 1, 0), r(D[1], 'BB', 0, 30, 0, 1), r(D[2], 'BB', 90, 10, 3, 1), r(D[3], 'AA', 10, 70, 1, 2)], D);
const B = ctx([r(D[0], 'CC', 5, 5, 1, 1), r(D[1], 'CC', 7, 1, 1, 1)], D);

/** the cohort's net buying over the window as a share of its buying, built from the kit only (a lab formula's shape) */
const netShare = (c: FlowContext, p: FlowParams) => {
  const g = K.grid0(p);
  return { value:K.each(c.rows, K.W(p, 2), (a, t) => { const C = K.cohort(g, c.rows, p, a, t);
    return K.cmiss(g, C, a, t) ? null : K.div(100 * (K.cw(g, C, 'bv', a, t) - K.cw(g, C, 'sv', a, t)), K.cw(g, C, 'bv', a, t)) }) };
};

describe('registerFlow', () => {
  it('registers a formula made of the kit that reads its own call rows', () => {
    registerFlow('FL97', netShare);
    const p = { window:2, scope:'all' };
    const want = computeFlow('FL97', A, p);
    computeFlow('FL01', B, {});                             // another context's call in between (the helpers' rows move)
    expect(computeFlow('FL97', A, p)).toEqual(want);       // the wrap set A's rows again: the value is A's
    expect(want.value.filter(v => v !== null).length).toBeGreaterThan(0);
    expect(want.value[1]).toBeCloseTo(100 * ((100 + 60) - (40 + 30)) / (100 + 60), 9);
    expect(computeFlow('FL97', B, p)).not.toEqual(want);
  });
  it('refuses an id that already has a formula, and anything but an FL id', () => {
    expect(() => registerFlow('FL01', netShare)).toThrow(/FL01 already has a formula/);
    expect(() => registerFlow('FL97', netShare)).toThrow(/already has a formula/);
    expect(() => registerFlow('I54', netShare)).toThrow(/not a Flow indicator id/);
    expect(typeof FLOW.FL01).toBe('function');
  });
});
