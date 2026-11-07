/* The cost model of flow conditions (QA unit B, QA4; verification/screener/BENCHMARK_FLOW_COST.md). The defect: a flow
   condition was costed by its window's sessions at the indicators' prior (60 x 5.96 ns per stock), while computeFlow's
   work grows with the stock's broker rows and brokers (about 1 ms per stock), and a series of more than one kernel (a
   flow indicator under an operator) never taught the model, so the 4500 ms budget did not protect (an anchored screen
   of 16 s was predicted at 18 ms). Locked here: the units over the rows and the brokers x sessions grid (an anchored
   one per session it computes over its N + 1 sessions), keyed by the indicator and its choices, the measured flow
   priors of the registry, the broker-data series and the window's context once per stock in the estimate and timed
   apart, every cold series observed with its time shared among its kernels, a series that reused memo work (a
   computeFlow answer) not observed, counts teach the model as runs do, and the budget's refusal naming how to pass. */
import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { inflateVerified } from '../../edge-bff/backtest/src/core/datafile.ts';
import { METRICS_CATALOG } from '../../edge-bff/screener/src/core/catalog.ts';
import { SCREENER_REGISTRY } from '../../edge-bff/screener/src/core/registry.ts';
import { costTracker } from '../../edge-bff/screener/src/core/plan.ts';
import { applyUniverse } from '../../edge-bff/screener/src/core/universe.ts';
import { availabilityMap } from '../../edge-bff/screener/src/core/validate.ts';
import type { ValidateContext } from '../../edge-bff/screener/src/core/validate.ts';
import { decodeBrokerDay } from '../src/broker.ts';
import { limitEntries } from '../src/catalog.ts';
import { CONTEXT_KEY, PRESENCE_KEY, costPrior, costUnits, estimateCost, newCostTracker, normalize, predictMs, runTask } from '../src/run.ts';
import { coreEngine, createApp } from '../src/server.ts';
import type { WorkerApp } from '../src/server.ts';
import { ThreadSnapshot, brokerCounts, brokerRowCount, buildSnapshot, flowContextOf, groupingsOf, materialize } from '../src/snapshot.ts';
import { brokerRowsOf as fakeRows, encodeBrokerDay, startFakeTerminal, universe, xsectionBrokerDoc } from './fake-terminal.mjs';
import { CAP, WITHIN, input, market } from './fixtures.ts';
import { OWNER_A, PROXY, auth, call, captureLogs, configFor } from './helpers.ts';

captureLogs();
const FLOW = SCREENER_REGISTRY.cost_model.flow, NS = FLOW.ns_per_unit.terminal, SESSIONS = 60;
const flow = (metric: string, params: Record<string, unknown> = {}) => ({ kind: 'flow', metric, params });
const pct = (of: unknown, length: number) => ({ kind: 'transform', fn: 'percentile', of, args: { length } });

test('a flow kernel is costed over what it computes: its rows and its brokers x (sessions + 1) grid; an anchored call per session it computes over its N + 1 sessions; keyed by the indicator and its choices; an operator over the window\'s sessions', () => {
  assert.deepEqual(costUnits(flow('FL24'), SESSIONS), [{ key: 'flow:FL24', costClass: 'O(N)', length: 1, flow: { rows: 1, brokers: SESSIONS + 1 } }]);
  // the choices (the select and switch parameters that decide what is computed) name the key, so each is learned apart:
  // FL23's Top-K holders and its selected brokers; the parameters that only scale the work do not
  const key = (m: string, p: Record<string, unknown> = {}) => costUnits(flow(m, p), SESSIONS)[0].key;
  assert.equal(key('FL10'), 'flow:FL10{scope=topn,rank=net_buy}');
  assert.equal(key('FL10', { window: 7 }), key('FL10'));
  assert.notEqual(key('FL23', { holders: 'top' }), key('FL23', { holders: 'selected', brokers: ['YP'] }));
  assert.ok(!key('FL26').includes('plot'), 'a display-only parameter is not a choice');
  // FL18 with its anchor 20 sessions back: a value test reads its last session (1 call), a percentile over 10 reads 11,
  // the whole series every session from the 20th (40 calls), each over 21 sessions of rows and a grid of 22
  const at = (reach: number | null) => costUnits(flow('FL18', { anchor_sessions: 20 }), SESSIONS, reach)[0];
  assert.deepEqual(at(0), { key: 'flow:FL18{scope=topn,rank=net_buy}', costClass: 'O(N)', length: 1, flow: { rows: 21 / SESSIONS, brokers: 22 } });
  assert.deepEqual(at(10).flow, { rows: 11 * 21 / SESSIONS, brokers: 11 * 22 });
  assert.deepEqual(at(null).flow, { rows: 40 * 21 / SESSIONS, brokers: 40 * 22 });
  assert.deepEqual(costUnits(pct(flow('FL24'), 20), SESSIONS).map(u => [u.key, u.flow ?? null, u.bars ?? null]), [['flow:FL24', { rows: 1, brokers: SESSIONS + 1 }, null], ['transform:percentile', null, SESSIONS]]);
  assert.deepEqual(costUnits({ kind: 'flow', metric: 'broker_data' }, SESSIONS), [{ key: PRESENCE_KEY, costClass: 'O(N)', length: 1, flow: { rows: 1, brokers: 0 } }]);
  // the prediction follows the stock: a large one's 13,000 rows of 100 brokers against a small one's 500 rows of 20
  const t = newCostTracker(), r = { ref: flow('FL24') as never, flowReach: undefined };
  const large = { rows: 13000, brokers: 100 }, small = { rows: 500, brokers: 20 };
  assert.equal(predictMs(t, r, 300, SESSIONS, large), (13000 + 100 * 61) * NS / 1e6);
  assert.equal(predictMs(t, r, 300, SESSIONS, small), (500 + 20 * 61) * NS / 1e6);
  const a = (n: number) => predictMs(t, { ref: flow('FL18', { anchor_sessions: n }) as never, flowReach: 10 }, 300, SESSIONS, large);
  assert.ok(Math.abs(a(40) / a(20) - (13000 * 11 * 41 / 60 + 100 * 11 * 42) / (13000 * 11 * 21 / 60 + 100 * 11 * 22)) < 1e-12, 'a deeper anchor reads more rows and a larger grid per session');
});

test('the priors: a flow kernel per unit of its work and the broker-data series per row, measured (screener-overlay.json cost_model.flow), every other kernel the indicators\' prior', () => {
  assert.ok(FLOW.context_ns_per_row > 0 && FLOW.presence_ns_per_row > 0);
  // one prior per way an entry is computed (the registry's compute), so a new entry of a known way has its prior
  assert.deepEqual(Object.keys(FLOW.ns_per_unit).sort(), [...new Set(SCREENER_REGISTRY.flows.map(f => f.compute).filter(c => c !== 'none'))].sort());
  for (const f of SCREENER_REGISTRY.flows.filter(x => x.compute !== 'none')) assert.equal(costPrior(costUnits(flow(f.id), SESSIONS)[0].key), FLOW.ns_per_unit[f.compute], f.id);
  assert.equal(costPrior(CONTEXT_KEY), FLOW.context_ns_per_row);
  assert.match(FLOW.evidence, /BENCHMARK_FLOW_COST\.md/);
  assert.equal(costPrior('flow:FL10'), NS);
  assert.equal(costPrior(PRESENCE_KEY), FLOW.presence_ns_per_row);
  assert.equal(PRESENCE_KEY, 'flow:broker_data');
  assert.equal(costPrior('indicator:rsi'), SCREENER_REGISTRY.cost_model.ns_per_bar_length);
  assert.equal(costPrior('transform:percentile'), SCREENER_REGISTRY.cost_model.ns_per_bar_length);
  assert.throws(() => costTracker(() => 0, 0.2).predict('k', 'O(N)', 1, 1), RangeError);
});

/* a snapshot with 20 broker days (a complete window of 20 sessions) on the fixtures' market */
async function snapshotWithBroker() {
  const m = market(), base = await input(m.prices, m.ref), dates = (m.prices.IHSG as unknown[][]).map(r => r[0] as string).slice(-22, -2);
  const tickers = Object.keys(m.prices).filter(t => t !== 'IHSG' && t !== 'SHORT');
  const days = await Promise.all(dates.map(async (d, k) => {
    const e = encodeBrokerDay(xsectionBrokerDoc(d, fakeRows(k + 1, d, tickers)));
    return decodeBrokerDay(await inflateVerified(new Uint8Array(e.body), { sha256: e.sha256, bytes: e.body.length }), `broker-${d}`, e.sha256);
  }));
  const { desc } = await buildSnapshot({ ...base, broker: { days, carry: null, missing: 0 } });
  const vctx: ValidateContext = { limits: { max_conditions: 20, max_metric_filters: 8, within_max: WITHIN }, capBudgetMs: CAP, tickers: new Set(desc.rows.map(r => r.ticker)),
    groupings: groupingsOf(base.ref), metrics: METRICS_CATALOG, availability: availabilityMap({}, METRICS_CATALOG, undefined, flowContextOf(desc)), flow: flowContextOf(desc) };
  return { desc, vctx };
}
const ENV = { capBudgetMs: CAP, withinMax: WITHIN, maxResponseBytes: 2 * 2 ** 20 };
const def = (tests: unknown[], universe: Record<string, unknown> = {}) => ({ universe: { security_types: ['stock'], traded_on_eval_date: false, exclude_price_breaks: false, ...universe },
  logic: 'all', conditions: tests.map((test, k) => ({ id: String.fromCharCode(97 + k), enabled: true, test })) });
const task = async (desc: any, vctx: ValidateContext, d: unknown) => {
  const n = await normalize(d, vctx);
  return { kind: 'run' as const, sid: desc.sid, definition: n.normalized, hash: n.hash, options: { exhaustive: true, explain: false }, queue_ms: 0, s0_ms: 0, versions: desc.versions, data: desc.data };
};

test('every series a run computes cold is observed with its kernels and their rows, a flow indicator under an operator included; one that read a memo entry of an earlier series is not; the next prediction of the same series is what it measured', async () => {
  const { desc, vctx } = await snapshotWithBroker();
  const snap = new ThreadSnapshot(desc, 64 * 2 ** 20), d0 = def([]);
  // the survivors with broker data on their own sessions (a stale stock's rows fall after its last bar)
  const onBars = (t: string) => { const b = snap.brokerRows(t)!, ds = new Set(snap.view(t)!.dates); for (let k = 0; k < b.rows; k++) if (ds.has(b.dates[b.D[k]])) return true; return false };
  const S = desc.data.broker_window!.sessions, counts = brokerCounts(desc);
  const eligible = applyUniverse(desc.rows, (await normalize(d0, vctx)).normalized.universe).eligible.map(r => { const j = desc.tickers.indexOf(r.ticker); return [r.ticker, brokerRowCount(desc, j), counts[j]] as const });
  const withRows = eligible.filter(([t]) => onBars(t));
  assert.ok(withRows.length >= 4, 'the stocks with broker rows');
  const first = runTask(await task(desc, vctx, def([{ kind: 'value', metric: pct(flow('FL24', { window: 5 }), 5), op: 'ge', value: 0 }])), snap, ENV, () => false);
  const mixed = first.observe.find(o => o.units.length === 2)!;
  assert.deepEqual(mixed.units.map(u => u.key), ['flow:FL24', 'transform:percentile'], 'the operator\'s series is observed (it was dropped before)');
  // the window's context of each stock, built by its flow series, is timed apart and observed on its own
  const context = first.observe.find(o => o.units[0].key === CONTEXT_KEY)!;
  assert.deepEqual([context.series, context.bars[0]], [withRows.length, withRows.reduce((s, [, r]) => s + r, 0)]);
  assert.equal(mixed.series, withRows.length);
  assert.equal(mixed.bars[0], withRows.reduce((s, [, r, b]) => s + r + b * (S + 1), 0), 'the flow kernel over the stocks\' rows and grids');
  assert.equal(mixed.bars[1], withRows.length * S, 'the operator over the window\'s sessions');
  const presence = first.observe.find(o => o.units[0].key === PRESENCE_KEY)!;
  assert.equal(presence.bars[0], eligible.reduce((s, [, r]) => s + r, 0), 'the broker-data series of every survivor, over its rows');
  assert.ok(presence.bars[0] > withRows.reduce((s, [, r]) => s + r, 0), 'a stale stock\'s rows after its last bar: read for its broker data, no flow value');
  assert.equal(first.log.reused, 0);
  // the same FL24 alone on the same thread: its computeFlow answer is the memo's, made by the first run: not observed
  // (each stock's view is new, so the window's context is built again: the memo is what makes it warm)
  const second = runTask(await task(desc, vctx, def([{ kind: 'value', metric: flow('FL24', { window: 5 }), op: 'gt', value: -1e12 }])), snap, ENV, () => false);
  assert.equal(second.log.computed, withRows.length);
  assert.equal(second.log.reused, withRows.length);
  assert.equal(second.observe.filter(o => o.units.some(u => u.key === 'flow:FL24')).length, 0, 'a warm series teaches nothing');
  // a learned model predicts the same series at what it measured: the time shared in proportion to the prediction
  const t = newCostTracker();
  t.observeShared(mixed.units.map((u, k) => ({ ...u, bars: mixed.bars[k] })), mixed.ms);
  const again = mixed.units.reduce((s, u, k) => s + t.predict(u.key, u.costClass, u.length, mixed.bars[k]), 0);
  assert.ok(Math.abs(again - mixed.ms) <= 1e-9 * Math.max(1, mixed.ms), `${again} vs ${mixed.ms}`);
});

test('the estimate: a flow condition over the survivors\' broker rows and grids, plus the broker-data series and the window\'s context once per survivor; a narrower universe of fewer rows costs less', async () => {
  const { desc, vctx } = await snapshotWithBroker();
  const held = { desc, pinned: new Set(desc.series.map(s => s.key)), position: new Map(desc.tickers.map((t, j) => [t, j])), index: materialize(desc, desc.index) };
  const tracker = newCostTracker(), env = { capBudgetMs: CAP, withinMax: WITHIN };
  const one = (await normalize(def([{ kind: 'value', metric: flow('FL24'), op: 'gt', value: 0 }]), vctx)).normalized;
  const two = (await normalize(def([{ kind: 'value', metric: flow('FL24'), op: 'gt', value: 0 }, { kind: 'value', metric: flow('FL10'), op: 'gt', value: -1e12 }]), vctx)).normalized;
  const e1 = estimateCost(one, held, tracker, env), e2 = estimateCost(two, held, tracker, env);
  const eligible = applyUniverse(desc.rows, one.universe).eligible, survivors = eligible.length, S = desc.data.broker_window!.sessions, counts = brokerCounts(desc);
  const avg = eligible.reduce((s, r) => s + brokerRowCount(desc, desc.tickers.indexOf(r.ticker)), 0) / survivors;
  const avgB = eligible.reduce((s, r) => s + counts[desc.tickers.indexOf(r.ticker)], 0) / survivors;
  const flowMs = (avg + avgB * (S + 1)) * NS / 1e6, presenceMs = avg * (FLOW.presence_ns_per_row + FLOW.context_ns_per_row) / 1e6;
  assert.equal(e1.eligible, survivors);
  assert.ok(Math.abs(e1.perTicker - flowMs) < 1e-12, `${e1.perTicker} vs ${flowMs}`);
  const near = (got: number, want: number) => assert.ok(Math.abs(got - Math.ceil(want)) <= 1, `${got} vs ${want}`);
  near(e1.needed_ms, (flowMs + presenceMs) * survivors);
  near(e2.needed_ms, (2 * flowMs + presenceMs) * survivors);      // the broker-data series and the context once, whatever the number of flow conditions
  // the stocks with the most rows against those with the fewest
  const byRows = desc.rows.map(r => r.ticker).sort((a, b) => brokerRowCount(desc, desc.tickers.indexOf(b)) - brokerRowCount(desc, desc.tickers.indexOf(a)));
  const of = async (tickers: string[]) => estimateCost((await normalize(def([{ kind: 'value', metric: flow('FL24'), op: 'gt', value: 0 }], { tickers }), vctx)).normalized, held, tracker, env).perTicker;
  assert.ok(await of(byRows.slice(0, 2)) > await of(byRows.slice(-2)));
});

/* end to end: counts teach the model as runs do; the budget's refusal names how to pass */
const open: { app: WorkerApp; fake: { close(): Promise<void> } }[] = [];
after(async () => { for (const o of open) { await o.app.close(); await o.fake.close() } });
async function worker(env: Record<string, string>) {
  const u = universe(6, 300), all = u.prices.IHSG.map((r: unknown[]) => r[0] as string), days = all.slice(-62, -2), tickers = Object.keys(u.prices).filter(t => t !== 'IHSG');
  const broker = Object.fromEntries(days.map((d: string, k: number) => [d, fakeRows(k + 1, d, tickers)]));
  const fake = await startFakeTerminal({ key: PROXY, publication: { finished_at: '2026-10-27T13:03:23Z', ...u, actions: [], broker, brokers: [['AK', 'A', 'Local', 'Institutional-heavy'], ['YP', 'Y', 'Local', 'Retail-heavy']] } });
  const cfg = configFor(fake.url, { SCREENER_THREADS: '1', ...env }), core = coreEngine(cfg), seen: { units: { key: string }[] }[] = [];
  const app = createApp(cfg, { pollMs: 3_600_000, engine: { ...core, observe(list) { seen.push(...list); core.observe(list) } } });
  const port = await app.listen(0, '127.0.0.1');
  open.push({ app, fake });
  await app.refresher.tick(); await app.refresher.tick();
  return { port, seen };
}
const U = { security_types: ['stock'], price_min: null, adv20_min_idr: null };

test('a counts request teaches the cost model as a run does', async () => {
  const { port, seen } = await worker({});
  await new Promise(r => setTimeout(r, 500));
  seen.length = 0;
  const definition = { universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test: { kind: 'value', metric: flow('FL10', { window: 7 }), op: 'gt', value: -1e12 } }] };
  const r = await call(port, 'POST', '/v1/counts', { schema_version: 1, definitions: [{ item_id: 'x', definition }] }, auth(OWNER_A));
  assert.equal(r.status, 200, JSON.stringify(r.body));
  assert.ok(seen.some(o => o.units.some(u => u.key.startsWith('flow:FL10{'))), JSON.stringify(seen).slice(0, 300));
});

test('compute_budget on a flow screen: refused before compute with how to pass (fewer custom or flow conditions, shorter windows or anchors, a narrower universe) and a right and a wrong example; the catalog\'s limit entry states the same fix before', async () => {
  const { port } = await worker({ SCREENER_MAX_CPU_MS: '1' });
  const definition = { universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test: { kind: 'value', metric: pct(flow('FL18', { anchor_sessions: 40 }), 10), op: 'ge', value: 50 } }] };
  const r = await call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'p', seq: 1 }, definition, options: { exhaustive: true } }, auth(OWNER_A));
  assert.equal(r.status, 422);
  assert.deepEqual([r.body.error.code, r.body.error.details.limit, r.body.error.details.allowed, r.body.error.details.costliest], ['LIMIT_EXCEEDED', 'compute_budget', 1, 'a']);
  assert.match(r.body.error.message, /above the 1 ms budget; the costliest is condition 1\. To pass, use default parameters, fewer custom or flow conditions, shorter lengths, windows or anchors, or a narrower universe \(right: .*; wrong: .*anchored.*\)\.$/);
  const entry = limitEntries({ ...configFor('http://x').limits, max_cpu_ms: 4500 }).find(e => e.name === 'compute_budget')!;
  assert.match(entry.example_refused, /\(use fewer custom or flow conditions, shorter lengths, windows or anchors, or a narrower universe\)$/);
});
