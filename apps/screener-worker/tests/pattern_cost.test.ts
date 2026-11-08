/* A pattern's cost (QA unit C, QA4; verification/screener/BENCHMARK_FLOW_COST.md section 6): run.ts costUnits prices a
   pattern by what its core does, a fixed part per bar plus one step per session of the window the core reads
   (candles.ts candleLookback for a candlestick pattern, transforms.ts PATTERNS window for the others), never by a
   parameter value; the priors are the measured cost_model.pattern; a recursive pattern keeps the unit it had (M300: no
   class lowered without a reviewed reason). Each rule is checked on every pattern of the core, not only the Hammer QA
   observed, and a run teaches the model the two units' measured time. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { CANDLES, candleLookback } from '../../edge-bff/backtest/src/core/candles.ts';
import { METRICS_CATALOG } from '../../edge-bff/screener/src/core/catalog.ts';
import { availabilityMap } from '../../edge-bff/screener/src/core/validate.ts';
import type { ValidateContext } from '../../edge-bff/screener/src/core/validate.ts';
import { SCREENER_REGISTRY } from '../../edge-bff/screener/src/core/registry.ts';
import { IMPLEMENTED_PATTERNS, resolveSignal } from '../../edge-bff/screener/src/core/transforms.ts';
import { costPrior, costUnits, newCostTracker, normalize, predictMs, runTask } from '../src/run.ts';
import { ThreadSnapshot, buildSnapshot, groupingsOf } from '../src/snapshot.ts';
import { CAP, WITHIN, input, market } from './fixtures.ts';
import { captureLogs } from './helpers.ts';

captureLogs();
const PAT = SCREENER_REGISTRY.cost_model.pattern;
const pattern = (type: string, params: Record<string, unknown> = {}) => ({ kind: 'pattern', type, params });
const units = (type: string, params: Record<string, unknown> = {}) => costUnits(pattern(type, params));
const fixed = (type: string) => ({ key: `pattern:${type}`, costClass: 'O(N)', length: 1 });
const windowed = (type: string, length: number) => ({ key: `pattern:${type}:window`, costClass: 'O(N·n)', length });
/** the core's own window of a pattern (transforms.ts PATTERNS window at its completed parameters) */
const windowOf = (type: string, params: Record<string, unknown> = {}) => resolveSignal(pattern(type, params) as never, 'p', { capBudgetMs: CAP }).window;

test('a candlestick pattern: its fixed work per bar plus the window candles.ts candleLookback reads, for every pattern and parameter that moves it; a parameter that is no length moves nothing', () => {
  for (const p of CANDLES.patterns) {
    const keys = new Set(p.params.map(q => q.key));
    assert.deepEqual(units(p.id), [fixed(p.id), windowed(p.id, candleLookback(p.id))], p.id);
    // QA unit C: min_range_ticks 50 (and every percentage, ratio and tolerance) is no length
    for (const q of p.params.filter(x => !['trend_length', 'body_avg_length', 'trend'].includes(x.key) && typeof x.max === 'number'))
      assert.deepEqual(units(p.id, { [q.key]: q.max }), units(p.id), `${p.id} ${q.key} ${q.max}`);
    // the trend's sessions count where the trend is read (average: N, change: N + 1), not where it is off (marubozu)
    const trend100 = units(p.id, { trend_length: 100 })[1].length;
    assert.equal(trend100, candleLookback(p.id, { trend_length: 100 }), p.id);
    const trendOn = (p.params.find(q => q.key === 'trend')?.default ?? 'none') !== 'none';
    assert.equal(trend100 > units(p.id)[1].length, trendOn, `${p.id}: the trend's sessions are read only when the trend is`);
    if (keys.has('body_avg_length')) assert.equal(units(p.id, { body_avg_length: 100 })[1].length, p.bars + 100, `${p.id} average body`);
  }
  // the QA case: Hammer at its defaults reads 11 bars (1 candle and its 10-session trend), not 30 (its body percentage)
  assert.deepEqual(units('hammer'), [fixed('hammer'), windowed('hammer', 11)]);
  assert.deepEqual(units('hammer', { trend: 'change' })[1].length, 12);
});

test('the other patterns: the window transforms.ts PATTERNS reads (breakout N + 1, a stochastic cross k + s + d - 1, squeeze length + lookback - 1); a recursive one keeps its O(N·n) unit over its largest parameter (M300)', () => {
  const older = IMPLEMENTED_PATTERNS.filter(id => !CANDLES.patterns.some(p => p.id === id) && !METRICS_CATALOG.metrics.find(m => m.id === id)?.decision);
  assert.ok(older.length >= 9, older.join());
  for (const id of older) {
    const w = windowOf(id), u = units(id);
    assert.deepEqual(u[0], fixed(id), id);
    assert.deepEqual(u[1], Number.isFinite(w) ? windowed(id, w) : { key: `pattern:${id}:length`, costClass: 'O(N·n)', length: 26 }, id);
  }
  assert.equal(units('breakout', { length: 50 })[1].length, 51);
  assert.equal(units('stoch_cross_in_zone')[1].length, 14 + 3 + 3 - 1);
  assert.deepEqual(units('stoch_cross_in_zone', { zone_max: 80 }), units('stoch_cross_in_zone'), 'the zone is no length');
  assert.equal(units('squeeze', { length: 20, lookback: 60 })[1].length, 79);
  // macd_divergence reads the whole history (window Infinity): its class is not lowered here (a review first, M300)
  assert.equal(windowOf('macd_divergence'), Infinity);
  assert.deepEqual(units('macd_divergence', { slow_length: 200 })[1], { key: 'pattern:macd_divergence:length', costClass: 'O(N·n)', length: 200 });
});

test('the priors are the measured ones (cost_model.pattern), and a prediction follows the core\'s window, not a parameter value', () => {
  assert.ok(PAT.ns_per_bar > 0 && PAT.candle_ns_per_bar_session > 0);
  assert.match(PAT.evidence, /BENCHMARK_FLOW_COST\.md section 6/);
  // the fixed part of every pattern; a candlestick pattern's window at the candle prior (candles.ts's own loops), an
  // older pattern's window at the indicators' (a registry kernel: Donchian, a rolling extreme, the stochastic)
  for (const id of IMPLEMENTED_PATTERNS) assert.equal(costPrior(`pattern:${id}`), PAT.ns_per_bar, id);
  for (const p of CANDLES.patterns) assert.equal(costPrior(`pattern:${p.id}:window`), PAT.candle_ns_per_bar_session, p.id);
  for (const id of ['breakout', 'breakdown', 'stoch_cross_in_zone', 'new_high', 'silent']) assert.equal(costPrior(`pattern:${id}:window`), SCREENER_REGISTRY.cost_model.ns_per_bar_length, id);
  assert.equal(costPrior('pattern:macd_divergence:length'), SCREENER_REGISTRY.cost_model.ns_per_bar_length);
  const t = newCostTracker(), bars = 1330;
  const ms = (type: string, params: Record<string, unknown> = {}) => predictMs(t, { ref: pattern(type, params) as never, flowReach: undefined }, bars);
  assert.ok(Math.abs(ms('hammer') - bars * (PAT.ns_per_bar + 11 * PAT.candle_ns_per_bar_session) / 1e6) < 1e-12);
  assert.ok(Math.abs(ms('breakout', { length: 50 }) - bars * (PAT.ns_per_bar + 51 * SCREENER_REGISTRY.cost_model.ns_per_bar_length) / 1e6) < 1e-12);
  // QA unit C: min_range_ticks 50 was taken as a length (Hammer 1.7 times its default, Bullish Engulfing 5 times); now
  // it moves nothing
  for (const id of ['hammer', 'bullish_engulfing', 'three_white_soldiers']) assert.equal(ms(id, { min_range_ticks: 50 }), ms(id), id);
  // a 100-session trend reads 90 more sessions per bar: a fifth more, as measured (BENCHMARK_FLOW_COST.md section 6),
  // not ten times (the QA's 368 ms predicted for 115 measured)
  const r = ms('hanging_man', { trend_length: 100 }) / ms('hanging_man');
  assert.ok(r > 1.1 && r < 1.3, String(r));
});

test('a run observes a pattern series with its two units and the bars they ran over; the learned model predicts what it measured', async () => {
  const m = market(), base = await input(m.prices, m.ref);
  const { desc } = await buildSnapshot(base);
  const snap = new ThreadSnapshot(desc, 64 * 2 ** 20);
  const vctx: ValidateContext = { limits: { max_conditions: 20, max_metric_filters: 8, within_max: WITHIN }, capBudgetMs: CAP, tickers: new Set(desc.rows.map(r => r.ticker)),
    groupings: groupingsOf(base.ref), metrics: METRICS_CATALOG, availability: availabilityMap({}) };
  const def = { universe: { security_types: ['stock'], traded_on_eval_date: false, exclude_price_breaks: false }, logic: 'all',
    conditions: [{ id: 'a', enabled: true, test: { kind: 'event', within: 3, signal: { pattern: pattern('morning_star', { trend_length: 30 }) } } }] };
  const n = await normalize(def, vctx);
  const out = runTask({ kind: 'run', sid: desc.sid, definition: n.normalized, hash: n.hash, options: { exhaustive: true, explain: false }, queue_ms: 0, s0_ms: 0, versions: desc.versions, data: desc.data }, snap, { capBudgetMs: CAP, withinMax: WITHIN, maxResponseBytes: 2 ** 21 }, () => false);
  const o = out.observe.find(x => x.units[0].key === 'pattern:morning_star')!;
  assert.deepEqual(o.units, [fixed('morning_star'), windowed('morning_star', candleLookback('morning_star', { trend_length: 30 }))]);
  assert.equal(o.bars[0], o.bars[1], 'both units run over the stock\'s bars');
  assert.ok(o.series >= 5 && o.ms > 0);
  const t = newCostTracker();
  t.observeShared(o.units.map((u, k) => ({ ...u, bars: o.bars[k] })), o.ms);
  const again = o.units.reduce((s, u, k) => s + t.predict(u.key, u.costClass, u.length, o.bars[k]), 0);
  assert.ok(Math.abs(again - o.ms) <= 1e-9 * Math.max(1, o.ms), `${again} vs ${o.ms}`);
});
