/* EXEC-BACKTEST-REVAMP P1: conditions in the Screener's grammar (kind 'test') computed per bar by the worker
   (src/grammar.ts). The oracle is the Screener itself: for sampled days t, runScreen with the evaluation date t on the
   data cut at t (only what was known that day) must pass a ticker exactly when the backtest's series is 1 on day t
   computed from the whole history. One check covers parity with the Screener and the absence of look-ahead. Also: the
   refusals (reference kinds without a per-day value, the Screener's own validation as the Backtest's ValidationError),
   EVENT within as a rolling window, bar 0, INDICATOR_OUTPUT_EMPTY, the series memo, and the start-up check. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Calc, conditionSeries } from '../../edge-bff/backtest/src/core/conditions.ts';
import { ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import type { Definition } from '../../edge-bff/screener/src/core/contract.ts';
import { UNIVERSE_DEFAULTS } from '../../edge-bff/screener/src/core/contract.ts';
import { runScreen } from '../../edge-bff/screener/src/core/screen.ts';
import { headBars, memoryEnv, rowOf, synth } from '../../edge-bff/screener/tests/core/helpers.ts';
import { GRAMMAR_DEFAULTS, checkTest, grammarProblems, installBacktestGrammar } from '../src/grammar.ts';
import { REPO_ROOT } from '../src/version.ts';
import { toApiError } from '../src/errors.ts';

installBacktestGrammar();

const IX = (() => { const t = synth('IHSG', 3, 420, '2024-06-03'); return { ...t, bars: { ...t.bars, V: t.bars.V.map(() => null) } } })();
const A = synth('GA01', 701, 420, '2024-06-03');
const rsi = { kind: 'indicator', indicator: 'I13', output: 'rsi', params: {} };
const close = { kind: 'price', field: 'close' };
const kamaState = { kind: 'indicator', indicator: 'I58', output: 'color_state', params: {} };
const TESTS: Record<string, unknown> = {
  value_between: { kind: 'value', metric: rsi, op: 'between', value: 40, value2: 60 },
  state_cross_line: { kind: 'state', lhs: close, op: 'gt', rhs: { kind: 'indicator', indicator: 'I01', output: 'sma', params: {} } },
  event_cross_donchian: { kind: 'event', within: 2, signal: { lhs: close, op: 'crosses_above', rhs: { kind: 'indicator', indicator: 'I10', output: 'upper', params: { length: 20 } } } },
  event_cross_within: { kind: 'event', within: 5, signal: { lhs: rsi, op: 'crosses_above', rhs: { value: 50 } } },
  state_pattern: { kind: 'state', pattern: { kind: 'pattern', type: 'volspike', params: { length: 20, threshold: 1.5 } } },
  event_pattern: { kind: 'event', within: 3, signal: { pattern: { kind: 'pattern', type: 'breakout', params: { length: 60 } } } },
  value_transform: { kind: 'value', metric: { kind: 'transform', fn: 'zscore', of: close, args: { length: 20 } }, op: 'gt', value: 0.5 },
  value_vs_index: { kind: 'value', metric: { kind: 'transform', fn: 'vs_index', of: close, args: {} }, op: 'gt', value: 0 },
  window_at_least: { kind: 'window', mode: 'at_least', length: 10, count: 3, test: { kind: 'value', metric: rsi, op: 'gt', value: 55 } },
  // the category forms (EXEC-PINE-INDICATORS, Alpha KAMA's colour; a lab indicator, which the worker computes)
  category_state: { kind: 'value', metric: { kind: 'transform', fn: 'in_categories', of: kamaState, args: { categories: 'yellow,yellow_green,green' } }, op: 'gt', value: 0.5 },
  category_change_within: { kind: 'window', mode: 'ever', length: 10, test: { kind: 'value', metric: { kind: 'transform', fn: 'category_change', of: kamaState,
    args: { changes: 'red>orange,orange>yellow,yellow>yellow_green,yellow_green>green,green>yellow_green,yellow_green>yellow,yellow>orange,orange>red' } }, op: 'gt', value: 0.5 } },
};
const U = { ...UNIVERSE_DEFAULTS, price_min: null, adv20_min_idr: null } as Definition['universe'];
const calcOf = (t = A) => new Calc(t.bars as never, undefined, { ticker: t.ticker, dates: t.dates, index: { dates: IX.dates, bars: IX.bars as never } });
const cond = (id: string, t: unknown) => ({ id, kind: 'test', test: t }) as never;

/** The Screener's verdict for ticker t on its day `at`, from the data cut there (ticker and IHSG). */
function screenerPasses(test: unknown, at: number): boolean {
  const E = A.dates[at], t = headBars(A, at + 1), ix = headBars(IX, IX.dates.indexOf(E) + 1);
  const r = runScreen({ universe: U, conditions: [{ id: 'a', enabled: true, test }], logic: 'all' } as unknown as Definition, memoryEnv([t], ix, [rowOf(t, E)], E));
  const row = r.rows.find(x => x.ticker === A.ticker);
  return !!row && row.cells.length === 1 && row.cells[0].status === 'pass';
}

test('every grammar form: the per-bar series equals the Screener on the data cut at each sampled day', () => {
  const days = Array.from({ length: 24 }, (_, k) => 30 + k * 16).filter(i => i < A.dates.length);
  let on = 0, off = 0;
  for (const [name, t] of Object.entries(TESTS)) {
    const s = conditionSeries(calcOf(), cond('a', t), `entry.conditions[0]`);
    for (const i of days) { assert.equal(!!s[i], screenerPasses(t, i), `${name} on ${A.dates[i]} (bar ${i})`); if (s[i]) on++; else off++ }
    assert.ok(s.reduce((a, b) => a + b, 0) > 0, `${name} is true somewhere (a test that never passes proves nothing)`);
  }
  console.log(`parity: ${on} passing and ${off} failing sampled days`);
  assert.ok(on >= 20 && off >= 20, `both verdicts are sampled (${on} pass, ${off} fail)`);
});

test('EVENT within is a rolling window over the markers, bar 0 is never true', () => {
  const t1 = { kind: 'event', within: 1, signal: { lhs: rsi, op: 'crosses_above', rhs: { value: 50 } } };
  const t5 = { ...t1, within: 5 };
  const m = conditionSeries(calcOf(), cond('a', t1), 'f'), w = conditionSeries(calcOf(), cond('a', t5), 'f');
  for (let i = 0; i < m.length; i++) {
    let any = 0; for (let k = Math.max(1, i - 4); k <= i; k++) any |= m[k];
    assert.equal(w[i], i === 0 ? 0 : any, `bar ${i}`);
  }
  assert.equal(conditionSeries(calcOf(), cond('a', TESTS.state_cross_line), 'f')[0], 0);
});

test('reference kinds without a per-day value are refused with their reason, before any computation', () => {
  const refused: [string, unknown][] = [
    ['universe', { kind: 'value', metric: { kind: 'universe', attribute: 'adv20_idr' }, op: 'gt', value: 1 }],
    ['xsection', { kind: 'value', metric: { kind: 'xsection', metric: 'return_rank', params: {} }, op: 'gt', value: 50 }],
    ['rank', { kind: 'value', metric: { kind: 'rank', of: rsi }, op: 'gt', value: 50 }],
    // P3: Flow indicators are read per bar; refused are the ones without a point-in-time value yet, with their reason
    ['flow FL31', { kind: 'value', metric: { kind: 'flow', metric: 'FL31', params: {} }, op: 'gt', value: 0 }],
    ['flow fnet', { kind: 'value', metric: { kind: 'flow', metric: 'fnet', params: {} }, op: 'gt', value: 0 }],
  ];
  for (const [kind, t] of refused) {
    assert.throws(() => conditionSeries(calcOf(), cond('a', t), 'entry.conditions[0]'), (e: unknown) => {
      assert.ok(e instanceof ValidationError, kind);
      assert.equal((e as ValidationError).code, 'CONDITION_UNAVAILABLE', kind);
      assert.match((e as ValidationError).field ?? '', /^entry\.conditions\[0\]\.test\.metric/, kind);
      return true;
    }, kind);
  }
});

test('the Screener\'s validation answers as the Backtest\'s ValidationError, with its code and field', () => {
  assert.throws(() => conditionSeries(calcOf(), cond('a', { kind: 'value', metric: rsi, op: 'between', value: 8, value2: 2 }), 'entry.conditions[1]'),
    (e: unknown) => e instanceof ValidationError && e.code === 'INVALID_CONDITION' && e.field === 'entry.conditions[1].test.value2');
  assert.throws(() => conditionSeries(calcOf(), cond('a', { kind: 'event', within: GRAMMAR_DEFAULTS.withinMax + 1, signal: { lhs: rsi, op: 'crosses_above', rhs: { value: 50 } } }), 'f'),
    (e: unknown) => e instanceof ValidationError && e.code === 'LIMIT_EXCEEDED');
  assert.throws(() => conditionSeries(calcOf(), cond('a', { kind: 'nope' }), 'f'), (e: unknown) => e instanceof ValidationError);
  // parameters completed (normalized): the same condition with and without its defaults is one test
  assert.deepEqual(checkTest(cond('a', TESTS.value_between), 'f'), checkTest(cond('a', { ...(TESTS.value_between as object), metric: { ...rsi, params: { length: 14 } } }), 'f'));
});

test('a series without any value up to the period end is INDICATOR_OUTPUT_EMPTY (the validation path on no bars too)', () => {
  const short = headBars(A, 10);
  assert.throws(() => conditionSeries(calcOf(short), cond('a', TESTS.value_transform), 'f'), (e: unknown) => e instanceof ValidationError && e.code === 'INDICATOR_OUTPUT_EMPTY');
  const empty = new Calc({ O: [], H: [], L: [], C: [], V: [] } as never);
  assert.throws(() => conditionSeries(empty, cond('a', TESTS.value_between), 'f'), (e: unknown) => e instanceof ValidationError && e.code === 'INDICATOR_OUTPUT_EMPTY');
  // up to `last`: values only after the period end do not count
  assert.throws(() => conditionSeries(calcOf(), cond('a', TESTS.value_transform), 'f', 5), (e: unknown) => e instanceof ValidationError && e.code === 'INDICATOR_OUTPUT_EMPTY');
});

test('series are kept per ticker under their resolved key: two conditions on one series compute it once', () => {
  const c = calcOf();
  conditionSeries(c, cond('a', TESTS.value_between), 'f');
  const n = c.seriesMemo.size;
  conditionSeries(c, cond('b', { kind: 'value', metric: rsi, op: 'gt', value: 70 }), 'f');
  assert.equal(c.seriesMemo.size, n);
});

test('start-up: the Screener registry, catalog and their sources agree in this tree', () => {
  assert.deepEqual(grammarProblems(REPO_ROOT), []);
});

test('Stage C F9: a refusal of the Screener\'s validation keeps its details in the worker\'s answer', () => {
  const rsi = { kind: 'indicator', indicator: 'I13', output: 'rsi', params: {} };
  let err: unknown;
  try { checkTest({ id: 'a', kind: 'test', test: { kind: 'event', within: 500, signal: { lhs: rsi, op: 'crosses_above', rhs: { value: 50 } } } }, 'entry.conditions[0]') } catch (e) { err = e }
  assert.ok(err instanceof ValidationError);
  const { status, error } = toApiError(err);
  assert.equal(status, 422); assert.equal(error.code, 'LIMIT_EXCEEDED'); assert.equal(error.field, 'entry.conditions[0].test.within');
  assert.ok(error.details && typeof error.details === 'object' && Object.keys(error.details).length > 0, JSON.stringify(error));
});

test('Stage C F1: the empty-series refusal is decided on the bars up to the period\'s end only', () => {
  const s = synth('AAAA', 3, 400), c = new Calc(s.bars as never, undefined, { ticker: 'AAAA', dates: s.dates });
  const cond = { id: 'a', kind: 'test', test: { kind: 'state', lhs: { kind: 'price', field: 'close' }, op: 'gt', rhs: { kind: 'indicator', indicator: 'I01', output: 'sma', params: { length: 200 } } } } as never;
  // the SMA(200) has its first value on bar 199: a period ending before it is refused, whatever the later bars hold
  assert.throws(() => conditionSeries(c, cond, 'f', 150), (e: unknown) => e instanceof ValidationError && e.code === 'INDICATOR_OUTPUT_EMPTY' && /up to the end of the period/.test(e.message));
  const h = headBars(s, 151);
  assert.throws(() => conditionSeries(new Calc(h.bars as never, undefined, { ticker: 'AAAA', dates: h.dates }), cond, 'f', 150), (e: unknown) => e instanceof ValidationError && e.code === 'INDICATOR_OUTPUT_EMPTY');
  assert.ok(conditionSeries(c, cond, 'f', 250).some(Boolean));
});
