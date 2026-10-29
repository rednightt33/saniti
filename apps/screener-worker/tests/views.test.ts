/* A request's view of the snapshot (snapshot.ts TickerView, run.ts screenEnv; report 6.7: a screen of pre-warmed series
   is a lookup, 6.10 stage S2 "O(1) per ticker"; performance review 2026-10-29, verification/screener/BENCHMARK_LOCAL.md).
   Locks the three rules that keep a screen fast and its memory bounded without changing an answer:
   - missingInput is answered from the snapshot's per-ticker mask, equal to the core's scan of the same bars;
   - a screen whose every series is pre-warmed makes no price column (dates come from the thread's own copy);
   - a request releases the Calc of a ticker that falls out of its LRU (CALC_KEEP), so the planner, which holds every
     survivor's view to the end, does not keep every custom output of the whole market; the answer is the same. */
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { METRICS_CATALOG } from '../../edge-bff/screener/src/core/catalog.ts';
import { scanMissingInput, tickerCalc } from '../../edge-bff/screener/src/core/metrics.ts';
import { BAR_FIELDS } from '../../edge-bff/screener/src/core/registry.ts';
import type { BarField } from '../../edge-bff/screener/src/core/registry.ts';
import { runScreen } from '../../edge-bff/screener/src/core/screen.ts';
import { availabilityMap } from '../../edge-bff/screener/src/core/validate.ts';
import type { ValidateContext } from '../../edge-bff/screener/src/core/validate.ts';
import { normalize, runTask, screenEnv } from '../src/run.ts';
import { ThreadSnapshot, TickerView, buildSnapshot, groupingsOf, materialize, prewarmChunk } from '../src/snapshot.ts';
import { CAP, WITHIN, input, market } from './fixtures.ts';

const ENV = { capBudgetMs: CAP, withinMax: WITHIN, maxResponseBytes: 2 * 2 ** 20 };
async function setup() {
  const u = market(), inp = await input(u.prices, u.ref), { desc } = await buildSnapshot(inp);
  prewarmChunk(desc, 0, desc.tickers.length, CAP);
  const vctx: ValidateContext = { limits: { max_conditions: 20, max_metric_filters: 8, within_max: WITHIN }, capBudgetMs: CAP, tickers: new Set(desc.rows.map(r => r.ticker)),
    groupings: groupingsOf(inp.ref), metrics: METRICS_CATALOG, availability: availabilityMap({}, METRICS_CATALOG) };
  return { desc, vctx };
}
const ind = (indicator: string, output: string, params: Record<string, unknown> = {}) => ({ kind: 'indicator', indicator, output, params });
const close = { kind: 'price', field: 'close' };
const def = (tests: unknown[], logic = 'all') => ({ universe: { security_types: ['stock'], traded_on_eval_date: false, exclude_price_breaks: false },
  conditions: tests.map((test, k) => ({ id: String.fromCharCode(97 + k), enabled: true, test })), logic });
const DEFAULTS = def([
  { kind: 'value', metric: ind('I13', 'rsi'), op: 'lt', value: 55 }, { kind: 'state', lhs: close, op: 'gt', rhs: ind('I01', 'sma') },
  { kind: 'state', lhs: close, op: 'gt', rhs: ind('I42', 'vwma') }, { kind: 'event', within: 20, signal: { lhs: ind('I06', 'macd'), op: 'crosses_above', rhs: ind('I06', 'signal') } },
], 'any');
const CUSTOM = def([
  { kind: 'value', metric: ind('I13', 'rsi', { length: 9 }), op: 'lt', value: 55 }, { kind: 'state', lhs: close, op: 'gt', rhs: ind('I01', 'sma', { length: 33 }) },
  { kind: 'state', lhs: ind('I06', 'macd', { fast_length: 7 }), op: 'gt', rhs: ind('I06', 'signal', { fast_length: 7 }) },
], 'any');
const answer = (o: ReturnType<typeof runScreen>) => JSON.stringify({ rows: o.rows, conditions: o.conditions.map(c => ({ ...c })), universe: o.universe, need: o.need });

test('TickerView.missing (the snapshot\'s mask) equals the core\'s scan of the same bars for every ticker, field set and bar', async () => {
  const { desc } = await setup();
  const snap = new ThreadSnapshot(desc, 1e6);
  const sets: BarField[][] = [...BAR_FIELDS.map(f => [f]), [...BAR_FIELDS], ['C', 'V'], ['V', 'H']];
  let compared = 0, found = 0;
  for (const t of desc.tickers) {
    const v = snap.view(t)!, plain = materialize(desc, desc.tickers.indexOf(t)), n = v.dates.length;
    for (const inputs of sets) for (const at of new Set([n - 1, n - 2, Math.floor(n / 2), 0, -1])) {
      const want = scanMissingInput(plain, inputs, at), got = v.missing(inputs, at);
      assert.equal(got, want, `${t} ${inputs.join('')} at ${at}`);
      compared++; if (want) found++;
    }
  }
  assert.ok(found > 0 && compared > found, 'the fixture has missing inputs (IHSG volume) and present ones');
  assert.equal(snap.view('IHSG')!.missing(['C', 'V'], desc.offsets[desc.index + 1] - desc.offsets[desc.index] - 1), 'V', 'IHSG has no volume');
});

test('a screen of pre-warmed series makes no price column and answers as the plain-array path does; a custom one makes them', async () => {
  const { desc, vctx } = await setup();
  const snap = new ThreadSnapshot(desc, 64 * 2 ** 20);
  const n = await normalize(DEFAULTS, vctx);
  const r = runTask({ kind: 'run', sid: desc.sid, definition: n.normalized, hash: n.hash, options: { exhaustive: true, explain: false }, queue_ms: 0, s0_ms: 0, versions: desc.versions, data: desc.data }, snap, ENV, () => false);
  assert.equal(snap.stats.columns, 0, 'no bar column read for lookups (dates, mask and pinned tails only)');
  assert.equal(r.log.computed, 0);
  // the same screen through plain materialized bars and a scanning missingInput (the path before the views)
  const plain = new ThreadSnapshot(desc, 64 * 2 ** 20);
  plain.view = (t: string) => { const j = desc.tickers.indexOf(t); return j < 0 ? undefined : tickerCalc(materialize(desc, j)) as unknown as TickerView };
  const a = runScreen(n.normalized, screenEnv(snap, ENV, () => false).env, { exhaustive: true });
  const b = runScreen(n.normalized, screenEnv(plain, ENV, () => false).env, { exhaustive: true });
  assert.equal(answer(a), answer(b));
  assert.ok(a.rows.some(x => x.cells.some(c => c.status === 'na')) || a.rows.length > 0, 'the screen answers rows');
  const c = await normalize(CUSTOM, vctx);
  runScreen(c.normalized, screenEnv(snap, ENV, () => false).env, { exhaustive: true });
  assert.ok(snap.stats.columns > 0, 'a custom series computes on materialized columns');
});

test('a request releases the Calc of the tickers that fall out of its LRU (CALC_KEEP): same answer, at most `keep` tickers hold computed outputs', async () => {
  const { desc, vctx } = await setup();
  const c = await normalize(CUSTOM, vctx);
  const run = (keep: number) => {
    const snap = new ThreadSnapshot(desc, 0);                 // no series LRU: every custom tail is computed on its view
    const views: TickerView[] = [], view = snap.view.bind(snap);
    snap.view = (t: string) => { const v = view(t); if (v) views.push(v); return v };
    const out = runScreen(c.normalized, screenEnv(snap, ENV, () => false, keep).env, { exhaustive: true });
    return { out, holding: views.filter(v => v.holding).length, views: views.length };
  };
  const wide = run(10_000), tight = run(2);
  assert.equal(answer(tight.out), answer(wide.out), 'releasing a view never changes a value');
  assert.ok(wide.holding > 2, `without a bound every survivor keeps its outputs (${wide.holding})`);
  assert.ok(tight.holding <= 2, `with keep 2 at most two views hold a Calc (${tight.holding})`);
  assert.ok(tight.out.rows.length > 0 && tight.views >= wide.views);
});

test('return_rank (stage S1) is computed once per thread and snapshot by the core\'s functions: the same ranks as screen.ts computes, no column on the next request', async () => {
  const { desc, vctx } = await setup();
  const RS = def([{ kind: 'value', metric: { kind: 'xsection', metric: 'return_rank', params: { window: 60 } }, op: 'gt', value: 40 },
    { kind: 'value', metric: ind('I13', 'rsi'), op: 'lt', value: 70 }], 'any');
  const n = await normalize(RS, vctx);
  const snap = new ThreadSnapshot(desc, 64 * 2 ** 20);
  const first = runScreen(n.normalized, screenEnv(snap, ENV, () => false).env, { exhaustive: true });
  const made = snap.stats.columns;
  assert.ok(made > 0, 'the first request reads the closes');
  const second = runScreen(n.normalized, screenEnv(snap, ENV, () => false).env, { exhaustive: true });
  assert.equal(snap.stats.columns, made, 'the second request reads no column: the ranks are the thread\'s');
  // the same screen with the core computing the cross-section itself (no xsectionValues)
  const core = new ThreadSnapshot(desc, 64 * 2 ** 20), e = screenEnv(core, ENV, () => false).env;
  const plain = runScreen(n.normalized, { ...e, xsectionValues: undefined }, { exhaustive: true });
  assert.equal(answer(first), answer(plain));
  assert.equal(answer(second), answer(plain));
  assert.ok(plain.rows.some(r => r.cells[0].status === 'pass') && plain.rows.some(r => r.cells[0].status !== 'pass'), 'the ranks split the market');
});
