/* EXEC-BACKTEST-REVAMP P2: one condition language. Every indicator condition of the Backtest (every registry indicator,
   output and operator against a constant, the price and a sibling output) written in the Screener's grammar, where the
   Screener's validation accepts that form, gives the same entry signal on every bar of the Terminal parity fixtures
   (the old form with the entry window W, the grammar form with its own window: EVENT within W for a cross, a window
   "ever" over W sessions for gt / lt) and hashes as the same trial (src/canonical.ts, K7 a). Also: grammar forms
   without an indicator equivalent keep a shape of their own at every depth (ERRORS M450), and window_bars counts only
   where a condition reads it. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DEFAULTS } from '../../edge-bff/terminal/src/calc/indicators.ts';
import { loadFixtures } from '../../edge-bff/terminal/tests/calc/fixtures.mjs';
import { Calc, combineEntry, conditionSeries } from '../../edge-bff/backtest/src/core/conditions.ts';
import type { BacktestRequest, Condition, IndicatorCondition } from '../../edge-bff/backtest/src/core/contract.ts';
import { lineageKey, variantHash } from '../../edge-bff/backtest/src/core/hash.ts';
import { REGISTRY, ValidationError } from '../../edge-bff/backtest/src/core/registry.ts';
import { hashForm } from '../src/canonical.ts';
import { checkTest, installBacktestGrammar } from '../src/grammar.ts';

installBacktestGrammar();
const fixtures = loadFixtures().map((f: any) => ({ ticker: f.ticker as string, dates: f.T as string[], bars: { T: f.T, O: f.O, H: f.H, L: f.L, C: f.C, V: f.V } }));
const IX = fixtures.find(f => f.ticker === 'IHSG')!;
const calcOf = (f: typeof fixtures[number]) => new Calc(f.bars as never, undefined, { ticker: f.ticker, dates: f.dates, index: { dates: IX.dates, bars: IX.bars as never } });
const median = (s: ArrayLike<unknown>) => { const v = Array.from(s).filter((x): x is number => typeof x === 'number' && Number.isFinite(x)).sort((a, b) => a - b); return v.length ? v[Math.floor(v.length / 2)] : 0 };

/** The grammar form of an indicator condition under the entry window W (the inverse of canonical.ts, written here). */
function grammarOf(c: IndicatorCondition, W: number, priceField: string): Record<string, unknown> {
  const ref = (output: string) => ({ kind: 'indicator', indicator: c.indicator, output, params: c.params ?? {} });
  const lhs = c.lhs.type === 'price' ? { kind: 'price', field: priceField } : ref(c.lhs.output);
  const rhs = c.rhs.type === 'value' ? { value: c.rhs.value } : ref(c.rhs.output);
  if (c.op === 'crosses_above' || c.op === 'crosses_below') return { kind: 'event', within: W, signal: { lhs, op: c.op, rhs } };
  const level = c.rhs.type === 'value' && c.lhs.type === 'output' ? { kind: 'value', metric: lhs, op: c.op, value: c.rhs.value } : { kind: 'state', lhs, op: c.op, rhs };
  return W === 1 ? level : { kind: 'window', mode: 'ever', length: W, test: level };
}
const request = (conditions: Condition[], W: number): BacktestRequest => ({
  schema_version: 1, mode: 'single', single: { ticker: 'BBCA', benchmark: 'buy_and_hold' }, period: { from: '2020-01-02', to: '2026-10-23', oos_fraction: 0 },
  entry: { logic: 'all', at_least: 1, window_bars: W, conditions },
  exit: { atr_length: 14, stop: { mode: 'pct', pct: 0.07, atr_mult: 2, reward_risk_x: 2, line: { indicator: 'I09', output: 'supertrend' } }, take_profit: { mode: 'none', pct: 0.15, r_multiple: 2, atr_mult: 3 },
    trailing: { mode: 'none', pct: 0.05, chandelier_length: 22, chandelier_mult: 3, line: { indicator: 'I01', output: 'sma' } }, max_hold_bars: 20, signals: { logic: 'any', conditions: [] } },
  sizing: { capital_idr: 100e6, allocation_fraction: 1 }, costs: { buy_fee: 0.0015, sell_fee: 0.0025, slippage: 0.0005, skip_ara_open_gap: false, ara_gap_fraction: 0.2 },
  robustness: { monte_carlo_runs: 0, seed: 7, sensitivity: false },
} as BacktestRequest);

test('every indicator condition the grammar accepts: the same entry signal on every bar and the same trial', async () => {
  const ref = fixtures[0];
  let same = 0, refused = 0;
  const refusedCodes = new Map<string, number>();
  for (const r of REGISTRY.indicators) {
    const params = Object.fromEntries(r.params.filter(p => p.type === 'integer').map(p => [p.key, p.default]));
    const out = calcOf(ref).out(r.key, { ...DEFAULTS[r.key] });
    for (const o of r.outputs) for (const op of ['gt', 'lt', 'crosses_above', 'crosses_below'] as const) {
      const sib = r.outputs.find(x => x !== o);
      const forms: IndicatorCondition[] = [
        { id: 'a', kind: 'indicator', indicator: r.id, params, lhs: { type: 'output', output: o }, op, rhs: { type: 'value', value: median(out[o]) } },
        { id: 'a', kind: 'indicator', indicator: r.id, params, lhs: { type: 'price' }, op, rhs: { type: 'output', output: o } },
        ...(sib ? [{ id: 'a', kind: 'indicator', indicator: r.id, params, lhs: { type: 'output', output: o }, op, rhs: { type: 'output', output: sib } } as IndicatorCondition] : []),
      ];
      for (const legacy of forms) for (const W of [1, 4]) {
        const g = { id: 'a', kind: 'test', test: grammarOf(legacy, W, r.price_input) } as Condition;
        try { checkTest(g, 'f') } catch (e) {
          if (!(e instanceof ValidationError)) throw e;
          refused++; refusedCodes.set(e.code, (refusedCodes.get(e.code) ?? 0) + 1); continue;
        }
        const what = `${r.id} ${legacy.lhs.type === 'price' ? 'price' : o} ${op} ${legacy.rhs.type === 'value' ? 'value' : legacy.rhs.output} W${W}`;
        for (const f of fixtures) {
          const c = calcOf(f), n = c.n;
          let ls: Uint8Array | null = null, gs: Uint8Array | null = null;
          try { ls = combineEntry([conditionSeries(c, legacy, 'f')], 'all', 1, W, n) } catch (e) { if (!(e instanceof ValidationError)) throw e }
          try { gs = combineEntry([conditionSeries(c, g, 'f')], 'all', 1, W, n, [1]) } catch (e) { if (!(e instanceof ValidationError)) throw e }
          assert.equal(gs === null, ls === null, `${what} on ${f.ticker}: one form refused (${ls === null ? 'old' : 'grammar'})`);
          if (ls && gs) for (let i = 0; i < n; i++) if (ls[i] !== gs[i]) assert.fail(`${what} on ${f.ticker}: bar ${i} old ${ls[i]} grammar ${gs[i]}`);
        }
        const [a, b] = [hashForm(request([legacy], W)), hashForm(request([g], W))];
        assert.equal(await variantHash(b), await variantHash(a), `${what}: not one trial`);
        assert.equal(await lineageKey(b), await lineageKey(a), `${what}: not one line`);
        same++;
      }
    }
  }
  console.log(`one language: ${same} forms equal on ${fixtures.length} tickers; ${refused} forms the Screener does not offer (${[...refusedCodes].map(([k, v]) => `${k} ${v}`).join(', ')})`);
  assert.ok(same > 300, `${same} equal forms`);
});

test('grammar forms without an indicator equivalent: a shape of their own at every depth, thresholds and lengths are variants of one line', async () => {
  const z = (len: number, v: number, of = { kind: 'price', field: 'close' }) => ({ id: 'z', kind: 'test', test: { kind: 'value', metric: { kind: 'transform', fn: 'zscore', of, args: { length: len } }, op: 'gt', value: v } }) as Condition;
  const L = async (c: Condition) => lineageKey(hashForm(request([c], 1))), V = async (c: Condition) => variantHash(hashForm(request([c], 1)));
  assert.equal(await L(z(20, 1)), await L(z(60, 2)));
  assert.notEqual(await V(z(20, 1)), await V(z(60, 2)));
  assert.notEqual(await L(z(20, 1)), await L(z(20, 1, { kind: 'price', field: 'volume' })), 'another series is another line');
  const rsi = (ind: string, out: string) => ({ id: 'e', kind: 'test', test: { kind: 'event', within: 2, signal: { lhs: { kind: 'transform', fn: 'change', of: { kind: 'indicator', indicator: ind, output: out, params: {} }, args: { bars: 5 } }, op: 'crosses_above', rhs: { value: 0 } } } }) as Condition;
  assert.notEqual(await L(rsi('I13', 'rsi')), await L(rsi('I47', 'mfi')), 'RSI and MFI are two lines');
  // window_bars is read only by a condition of another kind
  assert.equal(await V(z(20, 1)), await variantHash(hashForm(request([z(20, 1)], 7))));
  const legacy: Condition = { id: 'r', kind: 'indicator', indicator: 'I13', params: {}, lhs: { type: 'output', output: 'rsi' }, op: 'lt', rhs: { type: 'value', value: 30 } } as Condition;
  assert.notEqual(await variantHash(hashForm(request([legacy, z(20, 1)], 1))), await variantHash(hashForm(request([legacy, z(20, 1)], 7))));
});
