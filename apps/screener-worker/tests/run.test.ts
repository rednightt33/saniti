/* Screens through the worker against a direct computation through F and the backtest core's compare on the same bars
   (report I1: one formula path; 6.7: precomputed and dynamic are one call; 6.9-6.10: VALUE / STATE / EVENT, ALL / ANY /
   AT LEAST with the one near rule). The universe is the fake terminal-api's; the expected sets are computed here from
   the published rows with priceSeries, F and compare, never with the worker's code. */
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { compare } from '../../edge-bff/backtest/src/core/conditions.ts';
import { priceSeries } from '../../edge-bff/backtest/src/core/datafile.ts';
import { F } from '../../edge-bff/terminal/src/calc/indicators.ts';
import type { Bars } from '../../edge-bff/terminal/src/calc/indicators.ts';
import { createApp } from '../src/server.ts';
import type { WorkerApp } from '../src/server.ts';
import { pricePack } from '../../backtest-worker/tests/fake-terminal.mjs';
import { startFakeTerminal, universe } from './fake-terminal.mjs';
import { OWNER_A, PROXY, auth, call, configFor } from './helpers.ts';

let app: WorkerApp, fake: any, port: number;
const u = universe(30, 400);
const bars: Record<string, Bars> = {};
for (const t of Object.keys(u.prices)) if (t !== 'IHSG') bars[t] = priceSeries(t, [JSON.parse(JSON.stringify(pricePack(t, u.prices[t])))]).bars;
before(async () => {
  fake = await startFakeTerminal({ key: PROXY, publication: { finished_at: '2026-10-27T13:03:23Z', ...u, actions: [] } });
  app = createApp(configFor(fake.url, { SCREENER_THREADS: '2' }), { pollMs: 3_600_000 });
  port = await app.listen(0, '127.0.0.1');
  await app.refresher.tick();
});
after(async () => { await app.close(); await fake.close() });

const U = { security_types: ['stock'], price_min: null, adv20_min_idr: null };
const ind = (indicator: string, output: string, params: Record<string, unknown> = {}) => ({ kind: 'indicator', indicator, params, output });
let seq = 0;
const run = async (conditions: unknown[], logic = 'all', at_least?: number) => {
  const r = await call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'p', seq: ++seq }, definition: { universe: U, conditions, logic, ...(at_least ? { at_least } : {}) }, options: { exhaustive: true } }, auth(OWNER_A));
  assert.equal(r.status, 200, JSON.stringify(r.body));
  return r.body;
};
const last = (xs: ArrayLike<number | null>) => xs[xs.length - 1] as number;
const sorted = (xs: string[]) => [...xs].sort();
const matches = (body: any) => sorted(body.rows.filter((r: any) => r.status === 'match').map((r: any) => r.ticker));
const tickers = Object.keys(bars);

const C = {
  rsi14: { id: 'a', enabled: true, test: { kind: 'value', op: 'lt', value: 50, metric: ind('I13', 'rsi') } },
  rsi7: { id: 'b', enabled: true, test: { kind: 'value', op: 'gt', value: 55, metric: ind('I13', 'rsi', { length: 7 }) } },
  sma50: { id: 'c', enabled: true, test: { kind: 'state', op: 'gt', lhs: { kind: 'price', field: 'close' }, rhs: ind('I01', 'sma', { length: 50 }) } },
  macd: { id: 'd', enabled: true, test: { kind: 'event', within: 5, signal: { op: 'crosses_above', lhs: ind('I06', 'macd'), rhs: ind('I06', 'signal') } } },
};
const truth = {
  a: (t: string) => last(F.rsi(bars[t], { length: 14, source: 'close' }).rsi) < 50,
  b: (t: string) => last(F.rsi(bars[t], { length: 7, source: 'close' }).rsi) > 55,
  c: (t: string) => last(bars[t].C as number[]) > last(F.sma(bars[t], { length: 50, source: 'close' }).sma),
  d: (t: string) => {
    const m = F.macd(bars[t], { fast_length: 12, slow_length: 26, signal_length: 9, source: 'close' }), n = bars[t].C.length;
    const s = compare(m.macd, 'crosses_above', m.signal, 0, n);
    for (let i = n - 5; i < n; i++) if (s[i] === 1) return true;
    return false;
  },
};

test('VALUE on a pre-warmed default (RSI 14) and a custom length (RSI 7) equal F at the last bar; values on the wire are F rounded to 12 digits', async () => {
  const a = await run([C.rsi14]);
  assert.deepEqual(matches(a), sorted(tickers.filter(truth.a)));
  assert.equal(a.conditions[0].source, 'precomputed'); assert.equal(a.conditions[0].is_default, true);
  for (const r of a.rows) assert.equal(r.cells[0].value, Number(last(F.rsi(bars[r.ticker], { length: 14, source: 'close' }).rsi).toPrecision(12)));
  const b = await run([C.rsi7]);
  assert.deepEqual(matches(b), sorted(tickers.filter(truth.b)));
  assert.equal(b.conditions[0].source, 'dynamic'); assert.equal(b.conditions[0].is_default, false);
  // explicit default parameters are the pre-warmed series (one key): precomputed, is_default
  const c = await run([{ ...C.rsi14, test: { ...C.rsi14.test, metric: ind('I13', 'rsi', { length: 14, source: 'close' }) } }]);
  assert.deepEqual(c.rows, a.rows); assert.equal(c.conditions[0].source, 'precomputed');
});

test('STATE close > SMA(50) and EVENT MACD crosses above its signal within 5 bars equal the backtest core\'s compare on F', async () => {
  assert.deepEqual(matches(await run([C.sma50])), sorted(tickers.filter(truth.c)));
  const d = await run([C.macd]);
  assert.deepEqual(matches(d), sorted(tickers.filter(truth.d)));
  for (const r of d.rows) { assert.ok(r.cells[0].bars_ago >= 0 && r.cells[0].bars_ago < 5); assert.equal(typeof r.cells[0].event_date, 'string') }
});

test('ALL, ANY and AT LEAST 2 with the one near rule (near = not a match, need >= 2, met = need - 1), equal a brute force over the four conditions', async () => {
  const conds = [C.rsi14, C.rsi7, C.sma50, C.macd], ids = ['a', 'b', 'c', 'd'] as const;
  const met = (t: string) => ids.filter(k => truth[k](t)).length;
  for (const [logic, need] of [['all', 4], ['any', 1], ['at_least', 2]] as const) {
    const body = await run(conds, logic, logic === 'at_least' ? 2 : undefined);
    assert.equal(body.need, need, logic);
    const wantMatch = tickers.filter(t => met(t) >= need), wantNear = tickers.filter(t => met(t) < need && need >= 2 && met(t) === need - 1);
    assert.deepEqual(matches(body), sorted(wantMatch), `${logic} matches`);
    assert.deepEqual(sorted(body.rows.filter((r: any) => r.status === 'near').map((r: any) => r.ticker)), sorted(wantNear), `${logic} near`);
    assert.equal(body.match_count, wantMatch.length); assert.equal(body.near_count, wantNear.length);
    for (const r of body.rows) { assert.equal(r.met, met(r.ticker)); assert.equal(r.cells.length, 4); assert.ok(r.cells.every((c: any) => c.status !== 'not_evaluated'), 'displayed rows are complete (S4)') }
  }
});

test('pruning never changes the result: the pruned run equals the exhaustive one for the match and near sets and every displayed row', async () => {
  const conds = [C.rsi14, C.rsi7, C.sma50, C.macd];
  for (const [logic, k] of [['all', undefined], ['at_least', 3]] as const) {
    const ex = await run(conds, logic, k);
    const pr = await call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'p', seq: ++seq }, definition: { universe: U, conditions: conds, logic, ...(k ? { at_least: k } : {}) } }, auth(OWNER_A));
    assert.deepEqual(pr.body.rows, ex.rows, logic);
    assert.equal(pr.body.match_count, ex.match_count); assert.equal(pr.body.near_count, ex.near_count);
  }
});
