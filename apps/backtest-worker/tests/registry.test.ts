import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'node:test';
import { DEFAULTS, F } from '../../edge-bff/terminal/src/calc/indicators.ts';
import { build, serialize } from '../scripts/build-registry.mjs';
import { BY_ID, REGISTRY, REGISTRY_VERSION, ValidationError, indicator, resolveParams } from '../src/registry.ts';

const source = JSON.parse(fs.readFileSync(new URL('../../edge-bff/terminal/src/data/indRegistry.json', import.meta.url), 'utf8'));

test('the committed registry is the one the sources build (npm run registry)', async () => {
  assert.equal(fs.readFileSync(new URL('../registry/backtest-registry.json', import.meta.url), 'utf8'), serialize(await build()));
});

test('53 indicators, each mapped to a function of the calculation module with its outputs', () => {
  assert.equal(REGISTRY.indicators.length, 53);
  assert.deepEqual(REGISTRY.indicators.map(r => r.id), source.map((r: any) => r.id));
  const bars = { O: [1, 2, 3], H: [2, 3, 4], L: [0.5, 1, 2], C: [1.5, 2.5, 3.5], V: [10, 20, 30], T: ['2024-01-02', '2024-01-03', '2024-01-04'] };
  for (const r of REGISTRY.indicators) {
    assert.equal(typeof F[r.key], 'function', r.id);
    assert.deepEqual(Object.keys(F[r.key](bars, {})).filter(k => k !== '_breaks').sort(), [...r.outputs].sort(), r.id);
  }
});

test('accepted parameters are exactly the ones the module reads, with its executable defaults', () => {
  for (const r of REGISTRY.indicators) {
    const defs = DEFAULTS[r.key] || {};
    assert.deepEqual(r.params.map(p => p.key).sort(), Object.keys(defs).sort(), r.id);
    for (const p of r.params) assert.deepEqual(p.default, defs[p.key], `${r.id}.${p.key}`);
  }
  // the workbook parameters the module does not read are listed, not silently dropped
  assert.deepEqual(BY_ID.I37.not_accepted.map(n => n.key).sort(), ['include_current_bar', 'reference_method']);
});

test('no visual settings in the registry', () => {
  const allowed = new Set(['id', 'key', 'name', 'category', 'function', 'inputs', 'price_input', 'outputs', 'params', 'not_accepted', 'available_for_backtest']);
  for (const r of REGISTRY.indicators) for (const k of Object.keys(r)) assert.ok(allowed.has(k), `${r.id}.${k}`);
});

test('parameter validation refuses instead of rounding or clamping', () => {
  const adx = indicator('I07');
  assert.deepEqual(resolveParams(adx, undefined), { di_length: 14, adx_smoothing: 14 });
  assert.deepEqual(resolveParams(adx, { adx_smoothing: 5 }), { di_length: 14, adx_smoothing: 5 });
  const code = (f: () => unknown) => { try { f() } catch (e) { assert.ok(e instanceof ValidationError); return (e as ValidationError).code } return null };
  assert.equal(code(() => resolveParams(adx, { di_length: 0 })), 'PARAM_OUT_OF_RANGE');
  assert.equal(code(() => resolveParams(adx, { di_length: 14.5 })), 'INVALID_PARAM');
  assert.equal(code(() => resolveParams(adx, { di_length: '14' })), 'INVALID_PARAM');
  assert.equal(code(() => resolveParams(adx, { color: 'red' })), 'PARAM_NOT_ACCEPTED');
  assert.equal(code(() => resolveParams(indicator('I37'), { include_current_bar: false })), 'PARAM_NOT_ACCEPTED');
  assert.equal(code(() => resolveParams(indicator('I30'), { smoothing_type: 'HMA' })), 'INVALID_PARAM');
  assert.equal(code(() => resolveParams(indicator('I43'), { anchor: 'Week', band_1_multiplier: 1.5 })), null);
  assert.equal(code(() => indicator('I54')), 'UNKNOWN_INDICATOR');
});

test('the registry version is a content hash', () => {
  assert.match(REGISTRY_VERSION, /^[0-9a-f]{16}$/);
});
