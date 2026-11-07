/* The universal operators over HTTP (EXEC-SCREENER-FLOW-CANDLES P2-P3; QA4 2026-11-07 D3: they were tested only in the
   core): GET /catalog carries the operators block with each measure's transform arguments; /v1/validate and /v1/run
   take every new shape (value operators, the measures, window tests with a value, state or cross inside, a rank) and
   /v1/counts agrees with /v1/run; a bad shape is the core's refusal with its code, field and HTTP 422; a rank of a costly
   series is refused before compute under a small budget. On the fake terminal (tests/fake-terminal.mjs). */
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { createApp } from '../src/server.ts';
import { startFakeTerminal, universe } from './fake-terminal.mjs';
import { PROXY, OWNER_A, auth, call, configFor } from './helpers.ts';

const apps: { app: ReturnType<typeof createApp>; fake: { close(): Promise<void>; url: string } }[] = [];
after(async () => { for (const o of apps) { await o.app.close(); await o.fake.close() } });
async function start(env: Record<string, string> = {}) {
  const fake = await startFakeTerminal({ key: PROXY, publication: { finished_at: '2026-10-27T13:03:23Z', ...universe(10, 320), actions: [] } });
  const app = createApp(configFor(fake.url, { SCREENER_THREADS: '2', ...env }), { pollMs: 3_600_000 });
  const port = await app.listen(0, '127.0.0.1'); apps.push({ app, fake });
  await app.refresher.tick();
  return port;
}
const U = { security_types: ['stock'], price_min: null, adv20_min_idr: null };
const rsi = { kind: 'indicator', indicator: 'I13', output: 'rsi' };
const val = (metric: unknown, op: string, value: number, value2?: number) => ({ kind: 'value', metric, op, value, ...(value2 !== undefined ? { value2 } : {}) });
const def = (test: unknown) => ({ universe: U, conditions: [{ id: 'a', enabled: true, test }], logic: 'all' });
let port = 0, seq = 0;
before(async () => { port = await start() });
const validate = (d: unknown) => call(port, 'POST', '/v1/validate', { schema_version: 1, definition: d }, auth(OWNER_A));
const run = (d: unknown) => call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'ops', seq: ++seq }, definition: d }, auth(OWNER_A));

test('GET /catalog carries the operators block, each measure with its transform arguments', async () => {
  const r = await call(port, 'GET', '/v1/catalog', undefined, auth(OWNER_A));
  assert.equal(r.status, 200);
  const ops = (r.body as any).operators;
  assert.ok(ops && Array.isArray(ops.measures) && Array.isArray(ops.tests) && ops.types.P && ops.types.D);
  assert.deepEqual(ops.tests.map((t: any) => t.key).sort(), ['at_least', 'cross', 'ever', 'range', 'rank', 'streak', 'value']);
  const pct = ops.measures.find((m: any) => m.fn === 'percentile');
  assert.deepEqual(pct.args.map((a: any) => [a.key, a.min, a.max, a.default]), [['length', 1, 260, 60]]);
});

test('every new shape validates and runs; counts agree with the run', async () => {
  const shapes: Record<string, unknown> = {
    ge: val(rsi, 'ge', 50), outside: val(rsi, 'outside', 40, 60),
    percentile: val({ kind: 'transform', fn: 'percentile', of: rsi, args: { length: 60 } }, 'ge', 50),
    zscore: val({ kind: 'transform', fn: 'zscore', of: rsi, args: { length: 20 } }, 'gt', 0),
    slope: val({ kind: 'transform', fn: 'slope', of: rsi, args: { length: 20 } }, 'gt', 0),
    at_least: { kind: 'window', mode: 'at_least', length: 5, count: 3, test: val(rsi, 'gt', 50) },
    cross_in_window: { kind: 'window', mode: 'ever', length: 10, test: { kind: 'event', within: 1, signal: { lhs: rsi, op: 'crosses_above', rhs: { value: 50 } } } },
    state_in_window: { kind: 'window', mode: 'streak', length: 3, test: { kind: 'state', lhs: { kind: 'price', field: 'close' }, op: 'gt', rhs: { kind: 'indicator', indicator: 'I01', output: 'sma', params: { length: 20 } } } },
    rank: val({ kind: 'rank', of: rsi }, 'between', 0, 100),
  };
  for (const [name, t] of Object.entries(shapes)) {
    const v = await validate(def(t));
    assert.equal(v.status, 200, `${name}: validate ${JSON.stringify(v.body).slice(0, 200)}`);
    const r = await run(def(t));
    assert.equal(r.status, 200, `${name}: run ${JSON.stringify(r.body).slice(0, 200)}`);
    const c = await call(port, 'POST', '/v1/counts', { schema_version: 1, definitions: [{ item_id: 'x', definition: def(t) }] }, auth(OWNER_A));
    assert.equal(c.status, 200);
    assert.equal((c.body as any).counts[0].match_count, (r.body as any).match_count, `${name}: counts and run disagree`);
  }
  // the rank of every eligible stock is 0..100 and covers both ends (the filtered universe, decision C)
  const r = await run(def(val({ kind: 'rank', of: rsi }, 'between', 0, 100)));
  const ranks = (r.body as any).rows.map((x: any) => x.cells[0].value).sort((a: number, b: number) => a - b);
  assert.equal(ranks[0], 0); assert.equal(ranks.at(-1), 100);
});

test('a bad shape is the core refusal: code, field, HTTP 422', async () => {
  const bad: [unknown, string, string][] = [
    [val(rsi, 'eq', 50), 'INVALID_CONDITION', 'definition.conditions[0].test.op'],
    [{ kind: 'window', mode: 'at_least', length: 5, test: val(rsi, 'gt', 50) }, 'INVALID_CONDITION', 'definition.conditions[0].test.count'],
    [{ kind: 'window', mode: 'ever', length: 131, test: val(rsi, 'gt', 50) }, 'LIMIT_EXCEEDED', 'definition.conditions[0].test.length'],
    [val({ kind: 'rank', of: { kind: 'price', field: 'close' } }, 'ge', 90), 'INVALID_CONDITION', 'definition.conditions[0].test.metric.of'],
    [val({ kind: 'transform', fn: 'percentile', of: rsi, args: { length: 300 } }, 'ge', 90), 'PARAM_OUT_OF_RANGE', 'definition.conditions[0].test.metric.args.length'],
  ];
  for (const [t, code, field] of bad) {
    const v = await validate(def(t));
    assert.equal(v.status, 422);
    assert.deepEqual([(v.body as any).error.code, (v.body as any).error.field], [code, field]);
  }
});

test('a rank of a costly series is refused before compute under a small budget', async () => {
  const small = await start({ SCREENER_MAX_CPU_MS: '1' });
  const wr = { kind: 'indicator', indicator: 'I16', output: 'williams_r', params: { length: 500 } };
  const r = await call(small, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'ops', seq: 1 }, definition: def(val({ kind: 'rank', of: wr }, 'ge', 90)) }, auth(OWNER_A));
  assert.equal(r.status, 422);
  assert.deepEqual([(r.body as any).error.code, (r.body as any).error.details.limit], ['LIMIT_EXCEEDED', 'compute_budget']);
});
