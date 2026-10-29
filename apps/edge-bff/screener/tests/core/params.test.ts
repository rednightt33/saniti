/* Parameter validation against the registry, through the wire (semantic review, EXEC-SCREENER; report TARGET
   ARCHITECTURE 6.1 I7 "refused, never clamped", 6.8 narrowing and caps; API CONTRACT 8.4 catalog params, 8.8
   PARAM_OUT_OF_RANGE {field, min, max, exclusive_min, integer}; TEST PLAN 10b.2 "a custom length above the default cap
   is refused", 10b.10). For every parameter of the 53 indicators, the catalog the page builds its form from
   (catalogIndicators) and validateDefinition agree at every edge, in a real condition of the output's own form: the
   minimum (inclusive or exclusive), the maximum or the derived cap of an O(N·n) parameter, whole numbers, every offered
   option and a bogus one, booleans, an unknown key; each refusal names the field path in the request and carries the
   catalog's own range. The caps move with SCREENER_CAP_BUDGET_MS and are never below a default. */
import { describe, expect, it } from 'vitest';
import type { CatalogIndicator } from '../../src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../src/core/contract.ts';
import { ScreenerError } from '../../src/core/errors.ts';
import { INDICATORS, capOf, capProblems, catalogIndicators } from '../../src/core/registry.ts';
import type { ScreenerIndicator } from '../../src/core/registry.ts';
import { validateDefinition } from '../../src/core/validate.ts';
import { vctx } from './helpers.ts';

const CTX = vctx(['AAAA']);
const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null };
const refusal = (fn: () => unknown): ScreenerError | null => { try { fn(); return null } catch (e) { if (e instanceof ScreenerError) return e; throw e } };

/** A condition of the output's first offered form with `params` on the indicator reference, and the path of that
    reference in the request. */
function conditionOf(ind: ScreenerIndicator, params: Record<string, unknown>): { test: unknown; at: string } | null {
  for (const o of ind.outputs) {
    // an output an option may leave empty (I43 upper1 at bands_mode None) would refuse for that reason instead
    if (Object.values(o.inputs_by_source).some(by => Object.values(by).some(x => !x.length))) continue;
    for (const t of o.tests) {
      const ref = { kind: 'indicator', indicator: ind.id, output: o.key, params }, op = t.ops[0], bar = { kind: 'price', field: o.comparable_with ?? 'close' };
      switch (t.form) {
        case 'value': return { test: { kind: 'value', metric: ref, op, value: 0, ...(op === 'between' ? { value2: 1 } : {}) }, at: 'test.metric' };
        case 'value_pct_distance': return { test: { kind: 'value', metric: { kind: 'transform', fn: 'pct_distance', of: ref }, op, value: 0, ...(op === 'between' ? { value2: 1 } : {}) }, at: 'test.metric.of' };
        case 'state_level': return { test: { kind: 'state', lhs: bar, op, rhs: ref }, at: 'test.rhs' };
        case 'event_value': return { test: { kind: 'event', within: 5, signal: { lhs: ref, op, rhs: { value: 0 } } }, at: 'test.signal.lhs' };
        case 'state_value': return { test: { kind: 'state', lhs: ref, op, rhs: { value: 0 } }, at: 'test.lhs' };
        case 'state_rising': return { test: { kind: 'state', lhs: ref, op, rhs: { kind: 'transform', fn: 'lag', of: ref, args: { bars: 5 } } }, at: 'test.lhs' };
        case 'state_vs_ma': return { test: { kind: 'state', lhs: ref, op, rhs: { kind: 'transform', fn: 'ma', of: ref, args: { ma: 'EMA', length: 20 } } }, at: 'test.lhs' };
      }
    }
  }
  return null;
}
const run = (ind: ScreenerIndicator, params: Record<string, unknown>, ctx = CTX) => {
  const c = conditionOf(ind, params)!;
  return { at: `definition.conditions[0].${c.at}.params`, error: refusal(() => validateDefinition({ universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test: c.test }] }, ctx)) };
};

describe('every parameter of the 53: the catalog the page reads and the validation agree at every edge', () => {
  const catalog = new Map<string, CatalogIndicator>(catalogIndicators({ capBudgetMs: CTX.capBudgetMs }).map(x => [x.id, x]));
  for (const ind of INDICATORS) {
    it(`${ind.id} ${ind.key}`, () => {
      expect(conditionOf(ind, {}), `${ind.id} has a form to test its parameters in`).not.toBeNull();
      const base = { ...ind.start_params } as Record<string, unknown>, cat = catalog.get(ind.id)!;
      expect(run(ind, base).error, 'the start configuration validates').toBeNull();
      for (const p of cat.params) {
        const f = (v: unknown) => run(ind, { ...base, [p.key]: v }), field = (e: { at: string }) => `${e.at}.${p.key}`;
        const ok = (v: unknown) => { const r = f(v); expect([p.key, v, r.error?.code ?? null, r.error?.message ?? null]).toEqual([p.key, v, null, null]) };
        const out = (v: unknown, code = 'PARAM_OUT_OF_RANGE') => {
          const r = f(v);
          expect([p.key, v, r.error?.code, r.error?.field]).toEqual([p.key, v, code, field(r)]);
          if (code === 'PARAM_OUT_OF_RANGE') expect(r.error!.details).toMatchObject({ field: field(r), integer: p.integer, exclusive_min: p.exclusive_min, ...(p.min !== undefined ? { min: p.min } : {}), ...(p.max !== undefined ? { max: p.max } : {}) });
        };
        expect([p.key, p.default]).toEqual([p.key, base[p.key] ?? p.default]);                 // the card opens with the start value
        if (p.type === 'integer' || p.type === 'number') {
          const step = p.integer ? 1 : 1e-6;
          if (p.min !== undefined) { if (p.exclusive_min) { out(p.min); ok(p.min + step) } else { ok(p.min); out(p.min - step) } }
          if (p.max !== undefined) { ok(p.max); out(p.max + step) }
          if (p.integer) out((p.min ?? 0) + 2.5);
          out('20', 'INVALID_CONDITION');                                                         // a wrong JSON type: the field and its range named
          if (p.max === undefined && !p.integer) ok(1e6);
          const cap = capOf(ind.params.find(x => x.key === p.key)!, CTX.capBudgetMs);
          if (cap !== undefined) { expect(p.max).toBe(cap); expect(typeof p.default === 'number' && p.default <= cap).toBe(true) }
        } else if (p.type === 'enum') {
          for (const o of p.options!) ok(o);
          const r = f('Bogus');
          expect([r.error?.code, r.error?.field, r.error?.details?.allowed]).toEqual(['INVALID_CONDITION', field(r), p.options]);
        } else if (p.type === 'boolean') { ok(true); ok(false); out('yes', 'INVALID_CONDITION') }
      }
      const extra = run(ind, { ...base, not_a_param: 1 });
      expect([extra.error?.code, extra.error?.field]).toEqual(['INVALID_CONDITION', `${extra.at}.not_a_param`]);
      for (const h of ind.hidden_params) {
        const r = run(ind, { ...base, [h.key]: 1 });
        expect([h.key, r.error?.code]).toEqual([h.key, 'INVALID_CONDITION']);                  // a hidden parameter is never accepted
      }
    });
  }
  it('the caps follow SCREENER_CAP_BUDGET_MS: a smaller budget lowers them and the catalog says so; none falls below a default', () => {
    const low = 500, ctx = { ...CTX, capBudgetMs: low }, i10 = INDICATORS.find(x => x.id === 'I10')!;
    const cap = capOf(i10.params[0], low)!;
    expect(cap).toBeLessThan(capOf(i10.params[0], CTX.capBudgetMs)!);
    expect(catalogIndicators({ capBudgetMs: low }).find(x => x.id === 'I10')!.params[0].max).toBe(cap);
    expect(run(i10, { length: cap }, ctx).error).toBeNull();
    expect(run(i10, { length: cap + 1 }, ctx).error?.details).toMatchObject({ max: cap });
    expect(capProblems(low)).toEqual([]);
    expect(capProblems(80).length).toBeGreaterThan(0);                                            // a budget that would refuse a default
  });
});
