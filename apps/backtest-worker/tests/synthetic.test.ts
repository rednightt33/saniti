/* Small hand-made bars with hand-computed answers: missing values, flat prices, the window rule, and the inputs the
   page's controls cannot produce (they are refused, not adjusted). */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Calc, combineEntry, combineExit, compare, conditionSeries, switchOns } from '../src/conditions.ts';
import { ValidationError } from '../src/registry.ts';

const bits = (s: Uint8Array) => Array.from(s).join('');
const codeOf = (f: () => unknown) => { try { f() } catch (e) { assert.ok(e instanceof ValidationError, String(e)); return (e as ValidationError).code } return null };

test('comparisons: bar 0 is never true, a missing value is false, a cross needs both bars', () => {
  const a = [5, 5, null, 7, 4, 6, 6];
  assert.equal(bits(compare(a, 'gt', null, 5, a.length)), '0001011');        // bar 0 skipped even though 5 > 5 is false anyway
  assert.equal(bits(compare(a, 'lt', null, 5.5, a.length)), '0100100');
  assert.equal(bits(compare(a, 'crosses_above', null, 5, a.length)), '0000010'); // bar 3 follows a missing bar: no cross
  assert.equal(bits(compare(a, 'crosses_below', null, 5, a.length)), '0000100');
  const b = [4, 6, 6, 6, 6, 5, 7];
  assert.equal(bits(compare(a, 'crosses_above', b, 0, a.length)), '0000010');
  assert.equal(bits(compare(a, 'crosses_below', b, 0, a.length)), '0100101');  // bar 1: 5 >= 4 then 5 < 6; bar 6: 6 >= 5 then 6 < 7
});

test('within N bars: each condition keeps its last true bar', () => {
  const s1 = Uint8Array.from([1, 0, 0, 0, 0, 0]), s2 = Uint8Array.from([0, 0, 1, 0, 0, 0]);
  assert.equal(bits(combineEntry([s1, s2], 'all', undefined, 1, 6)), '000000');
  assert.equal(bits(combineEntry([s1, s2], 'all', undefined, 3, 6)), '001000');  // s1 on bar 0 still counts on bar 2
  assert.equal(bits(combineEntry([s1, s2], 'all', undefined, 4, 6)), '001100');
  assert.equal(bits(combineEntry([s1, s2], 'any', undefined, 2, 6)), '111100');
  assert.equal(bits(combineEntry([s1, s2], 'at_least', 5, 3, 6)), '001000');     // above the active count = all (page)
  assert.deepEqual(switchOns(combineEntry([s1, s2], 'any', undefined, 2, 6), 1, 5), []); // already on before the range
  assert.equal(bits(combineExit([s1, s2], 'all', 6)), '000000');
  assert.equal(bits(combineExit([s1, s2], 'any', 6)), '101000');
});

test('entry inputs outside the page controls are refused', () => {
  const s = [Uint8Array.from([0, 1, 0])];
  assert.equal(codeOf(() => combineEntry(s, 'at_least', 0, 3, 3)), 'INVALID_ENTRY');
  assert.equal(codeOf(() => combineEntry(s, 'at_least', 1.5, 3, 3)), 'INVALID_ENTRY');
  assert.equal(codeOf(() => combineEntry(s, 'bogus' as any, 1, 3, 3)), 'INVALID_ENTRY');
  for (const w of [0, 2.9, 21, 500]) assert.equal(codeOf(() => combineEntry(s, 'any', undefined, w, 3)), 'INVALID_ENTRY', `window ${w}`);
  assert.equal(codeOf(() => combineExit(s, 'most' as any, 3)), 'INVALID_EXIT');
});

const flat = (n: number, px = 100) => ({ T: Array.from({ length: n }, (_, i) => `2024-01-${String(i + 1).padStart(2, '0')}`),
  O: Array(n).fill(px), H: Array(n).fill(px), L: Array(n).fill(px), C: Array(n).fill(px), V: Array(n).fill(1000) });

test('flat prices: RSI is 0 by the Terminal convention, so "RSI < 30" is true once RSI has a value', () => {
  const c = new Calc(flat(20));
  const s = conditionSeries(c, { id: 'r', kind: 'indicator', indicator: 'I13', params: { length: 14 }, lhs: { type: 'output', output: 'rsi' }, op: 'lt', rhs: { type: 'value', value: 30 } });
  assert.equal(bits(s), '0'.repeat(14) + '1'.repeat(6));                        // first RSI on bar 14
});

test('a missing bar is never a signal and restarts the indicator, as the Terminal module does', () => {
  const b = flat(8); b.C = [100, 101, 102, null as any, 104, 105, 106, 107]; b.H = b.C.map(x => x); b.L = b.C.map(x => x); b.O = b.C.map(x => x);
  const c = new Calc(b);
  const s = conditionSeries(c, { id: 's', kind: 'indicator', indicator: 'I01', params: { length: 2 }, lhs: { type: 'price' }, op: 'gt', rhs: { type: 'output', output: 'sma' } });
  assert.equal(bits(s), '01100111');                                             // SMA(2) null on bar 3 and bar 4 (restart)
  // SMA(2): 100.5 on bar 1 ... null on 3 and 4, 104.5 on 5: close > SMA on 1, 2, 5, 6, 7
});

test('parameters that leave an output empty, and thresholds in the wrong unit, are refused', () => {
  const n = 40, C = Array.from({ length: n }, (_, i) => 100 + 10 * Math.sin(i / 3));   // moving prices: CCI has a value
  const c = new Calc({ T: flat(n).T, O: C, H: C.map(x => x + 1), L: C.map(x => x - 1), C, V: Array(n).fill(1000) });
  assert.equal(codeOf(() => conditionSeries(c, { id: 'c', kind: 'indicator', indicator: 'I19', lhs: { type: 'output', output: 'cci' }, op: 'gt', rhs: { type: 'value', value: 100 } })), null);
  const cci = { id: 'c', kind: 'indicator', indicator: 'I19', params: { constant: 0 }, lhs: { type: 'output', output: 'cci' }, op: 'gt', rhs: { type: 'value', value: 100 } } as const;
  assert.equal(codeOf(() => conditionSeries(c, cci)), 'INDICATOR_OUTPUT_EMPTY');
  assert.equal(codeOf(() => conditionSeries(c, { ...cci, params: { length: 41 } })), 'INDICATOR_OUTPUT_EMPTY');   // longer than the history
  assert.equal(codeOf(() => conditionSeries(c, { id: 'd', kind: 'price_action', type: 'dip', value: -3 })), 'VALUE_OUT_OF_RANGE');
  assert.equal(codeOf(() => conditionSeries(c, { id: 'd', kind: 'price_action', type: 'dip', value: -0.03 })), null);
  assert.equal(codeOf(() => conditionSeries(c, { id: 'v', kind: 'price_action', type: 'volspike', value: -1 })), 'VALUE_OUT_OF_RANGE');
});
