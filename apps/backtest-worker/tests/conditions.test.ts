/* Conditions on real bars (the Terminal parity fixtures: BBCA, GOTO, IHSG and five random tickers, full stored history)
   against the backtest page's own condition code (tests/oracle.mjs). Indicator values are the Terminal module's, so
   these tests check the condition semantics; the formulas themselves are covered by edge-bff/terminal/tests/calc.
   Signals are 0/1, so the comparison is exact. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DEFAULTS } from '../../edge-bff/terminal/src/calc/indicators.ts';
import { loadFixtures } from '../../edge-bff/terminal/tests/calc/fixtures.mjs';
import { Calc, combineEntry, combineExit, conditionSeries, switchOns, trueBars } from '../src/conditions.ts';
import type { Condition, EntryLogic, Op, Signal } from '../src/conditions.ts';
import { REGISTRY, ValidationError } from '../src/registry.ts';
import * as O from './oracle.mjs';

const fixtures = loadFixtures().map((f: any) => ({ ticker: f.ticker, bars: { T: f.T, O: f.O, H: f.H, L: f.L, C: f.C, V: f.V } }));
const OP: Record<Op, string> = { gt: 'gt', lt: 'lt', crosses_above: 'ca', crosses_below: 'cb' };
const OPS = Object.keys(OP) as Op[];
const same = (a: Signal, b: Uint8Array, what: string) => {
  assert.equal(a.length, b.length, what);
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) assert.fail(`${what}: bar ${i} worker ${a[i]} page ${b[i]}`);
};
// the page's default threshold for a panel indicator is the output's own median (regMedian); use it so conditions switch
const median = (s: ReadonlyArray<number | null>) => { const v = s.filter(x => typeof x === 'number' && Number.isFinite(x)).sort((a, b) => (a as number) - (b as number)) as number[]; return v.length ? v[Math.floor(v.length / 2)] : 0 };
let seed = 20261026;
const rnd = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296);
const pick = <T>(a: T[]) => a[Math.floor(rnd() * a.length)];

/* every indicator, every output, every operator, against a value, the price (or volume) and a sibling output, with the
   defaults and with one non-default parameter set */
function indicatorCases() {
  const cases: { cond: Condition; oracle: (c: Calc) => Uint8Array }[] = [];
  for (const r of REGISTRY.indicators) {
    const variants = [{}, Object.fromEntries(r.params.filter(p => p.type === 'integer').map(p => [p.key, (p.default as number) + 1]))];
    for (const params of variants) for (const out of r.outputs) for (const op of OPS) {
      const sib = r.outputs.find(o => o !== out);
      const resolved = { ...DEFAULTS[r.key], ...params };
      const series = (c: Calc) => c.out(r.key, resolved);
      const price = (c: Calc) => O.toF(r.price_input === 'volume' ? c.bars.V : c.bars.C);
      cases.push({ cond: { id: `${r.id}-${out}-${op}-v`, kind: 'indicator', indicator: r.id, params, lhs: { type: 'output', output: out }, op, rhs: { type: 'value', value: NaN } },
        oracle: c => O.regEval(O.toF(series(c)[out]), null, (this_value_of(c, r.key, resolved, out)), OP[op]) });
      cases.push({ cond: { id: `${r.id}-${out}-${op}-p`, kind: 'indicator', indicator: r.id, params, lhs: { type: 'price' }, op, rhs: { type: 'output', output: out } },
        oracle: c => O.regEval(price(c), O.toF(series(c)[out]), 0, OP[op]) });
      if (sib) cases.push({ cond: { id: `${r.id}-${out}-${op}-${sib}`, kind: 'indicator', indicator: r.id, params, lhs: { type: 'output', output: out }, op, rhs: { type: 'output', output: sib } },
        oracle: c => O.regEval(O.toF(series(c)[out]), O.toF(series(c)[sib]), 0, OP[op]) });
    }
  }
  return cases;
}
const this_value_of = (c: Calc, key: string, params: any, out: string) => median(c.out(key, params)[out]);
const withValue = (cond: Condition, c: Calc): Condition => cond.kind === 'indicator' && cond.rhs.type === 'value'
  ? { ...cond, rhs: { type: 'value', value: this_value_of(c, REGISTRY.indicators.find(r => r.id === cond.indicator)!.key, { ...DEFAULTS[REGISTRY.indicators.find(r => r.id === cond.indicator)!.key], ...cond.params }, cond.lhs.output!) } }
  : cond;

const CASES = indicatorCases();

test(`indicator conditions equal the page's regEval (${CASES.length} conditions x ${fixtures.length} tickers)`, () => {
  let switched = 0;
  for (const { ticker, bars } of fixtures) {
    const c = new Calc(bars);
    for (const { cond, oracle } of CASES) {
      const s = conditionSeries(c, withValue(cond, c));
      same(s, oracle(c), `${ticker} ${cond.id}`);
      switched += switchOns(s, 0, s.length - 1).length;
    }
  }
  assert.ok(switched > 100000, 'the conditions do switch on (the comparison is not all zeros)');
});

test('price-action and pattern conditions equal the page', () => {
  for (const { ticker, bars } of fixtures) {
    const c = new Calc(bars), C = O.toF(bars.C), H = O.toF(bars.H), L = O.toF(bars.L), V = O.toF(bars.V);
    const m = c.out('macd', { ...DEFAULTS.macd });
    const checks: [Condition, Uint8Array][] = [
      [{ id: 'dip', kind: 'price_action', type: 'dip', value: -0.03 }, O.dip(C, -0.03)],
      [{ id: 'brk', kind: 'price_action', type: 'breakout', params: { length: 20 } }, O.breakout(H, C, 20)],
      [{ id: 'brk55', kind: 'price_action', type: 'breakout', params: { length: 55 } }, O.breakout(H, C, 55)],
      [{ id: 'gc', kind: 'price_action', type: 'macross', op: 'golden_cross' }, O.macross(C, 20, 50, 'golden')],
      [{ id: 'fa', kind: 'price_action', type: 'macross', op: 'fast_above_slow', params: { fast_length: 10, slow_length: 30 } }, O.macross(C, 10, 30, 'fabove')],
      [{ id: 'xs', kind: 'price_action', type: 'macd', op: 'crosses_above_signal' }, O.macdCond(O.toF(m.macd), O.toF(m.signal), O.toF(m.histogram), 'xsig')],
      [{ id: 'hp', kind: 'price_action', type: 'macd', op: 'histogram_positive' }, O.macdCond(O.toF(m.macd), O.toF(m.signal), O.toF(m.histogram), 'hpos')],
      [{ id: 'bd', kind: 'price_action', type: 'macd', op: 'bullish_divergence' }, O.bullDiv(L, O.toF(m.macd), 40)],
    ];
    if (ticker !== 'IHSG') checks.push([{ id: 'vs', kind: 'price_action', type: 'volspike', value: 2 }, O.volspike(V, 20, 2)]);
    for (const [cond, want] of checks) same(conditionSeries(c, cond), want, `${ticker} ${cond.id}`);
  }
});

test('combined entry ("within N bars"), its arrows, and exit signals equal the page', () => {
  const logics: EntryLogic[] = ['all', 'any', 'at_least'];
  for (const { ticker, bars } of fixtures) {
    const c = new Calc(bars), n = bars.C.length, idx = [...Array(n).keys()].slice(Math.floor(n / 3));
    for (let k = 0; k < 150; k++) {
      const chosen = Array.from({ length: 2 + Math.floor(rnd() * 4) }, () => pick(CASES));
      const ss = chosen.map(x => conditionSeries(c, withValue(x.cond, c)));
      const logic = pick(logics), atLeast = 1 + Math.floor(rnd() * ss.length), W = 1 + Math.floor(rnd() * 20);
      const want = O.signalsFor(ss, logic === 'at_least' ? 'n' : logic, atLeast, W);
      const got = combineEntry(ss, logic, atLeast, W, n);
      same(got, want, `${ticker} entry ${logic} ${atLeast} W${W}`);
      assert.deepEqual(switchOns(got, idx[0], idx.at(-1)!), O.markers(want, idx), `${ticker} entry arrows`);
      assert.equal(trueBars(got, idx[0], idx.at(-1)!), idx.filter(i => want[i]).length);
      const exitLogic = pick(['any', 'all'] as const);
      same(combineExit(ss, exitLogic, n), O.exitSeries(ss, exitLogic), `${ticker} exit ${exitLogic}`);
    }
  }
});

test('invalid conditions are refused with a field name', () => {
  const c = new Calc(fixtures[0].bars);
  const code = (cond: any) => { try { conditionSeries(c, cond) } catch (e) { assert.ok(e instanceof ValidationError); return [(e as ValidationError).code, (e as ValidationError).field] } return null };
  assert.deepEqual(code({ id: 'a', kind: 'indicator', indicator: 'I13', lhs: { type: 'output', output: 'macd' }, op: 'gt', rhs: { type: 'value', value: 30 } }), ['UNKNOWN_OUTPUT', 'condition.lhs.output']);
  assert.deepEqual(code({ id: 'a', kind: 'indicator', indicator: 'I13', lhs: { type: 'value', value: 1 }, op: 'gt', rhs: { type: 'value', value: 30 } }), ['INVALID_CONDITION', 'condition.lhs.type']);
  assert.deepEqual(code({ id: 'a', kind: 'indicator', indicator: 'I13', lhs: { type: 'output', output: 'rsi' }, op: 'ge', rhs: { type: 'value', value: 30 } }), ['INVALID_CONDITION', 'condition.op']);
  assert.deepEqual(code({ id: 'a', kind: 'flow', type: 'fnet' }), ['UNKNOWN_CONDITION', 'condition.kind']);
  assert.deepEqual(code({ id: 'a', kind: 'price_action', type: 'breakout', params: { length: 0 } }), ['INVALID_PARAM', 'condition.params.length']);
});
