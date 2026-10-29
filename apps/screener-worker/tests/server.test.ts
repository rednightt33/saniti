/* The private API (server.ts; report API CONTRACT 8.4-8.11; TEST PLAN 10b.11): the key and the owner tag, the
   protocol errors, the request envelope, the published limits and their refusals, the catalog's ETag, the result cache
   shared across owners with nothing user-specific in it, preview and counts, all on the real screener core over a
   snapshot loaded from the fake terminal-api. */
import assert from 'node:assert/strict';
import http from 'node:http';
import { after, before, test } from 'node:test';
import { countsAnswer } from '../src/run.ts';
import { createApp } from '../src/server.ts';
import type { WorkerApp } from '../src/server.ts';
import { startFakeTerminal, universe, walk } from './fake-terminal.mjs';
import { KEY, OWNER_A, OWNER_B, PROXY, auth, call, captureLogs, configFor, envFor } from './helpers.ts';

const logs = captureLogs();
const apps: { app: WorkerApp; fake: { close(): Promise<void> } }[] = [];
after(async () => { for (const o of apps) { await o.app.close(); await o.fake.close() } });

const U = { security_types: ['stock'], price_min: null, adv20_min_idr: null };
const RSI = (length?: number, value = 50) => ({ universe: U, conditions: [{ id: 'a', enabled: true, test: { kind: 'value', op: 'lt', value, metric: { kind: 'indicator', indicator: 'I13', params: length !== undefined ? { length } : {}, output: 'rsi' } } }], logic: 'all' });
const runBody = (definition: unknown, seq = 1, extra: Record<string, unknown> = {}) => ({ schema_version: 1, client_order: { page: 'pg1', seq }, definition, ...extra });

async function start(env: Record<string, string> = {}) {
  const fake = await startFakeTerminal({ key: PROXY, publication: { finished_at: '2026-10-27T13:03:23Z', ...universe(10, 320), actions: [] } });
  const app = createApp(configFor(fake.url, { SCREENER_THREADS: '2', ...env }), { pollMs: 3_600_000 });
  const port = await app.listen(0, '127.0.0.1');
  apps.push({ app, fake });
  await app.refresher.tick();
  assert.ok(app.state().current, 'snapshot loaded');
  return { app, port };
}
let main: { app: WorkerApp; port: number };
before(async () => { main = await start() });

test('the key: every route but /health and /ready needs x-screener-worker-key (401 UNAUTHORIZED); /health and /ready answer without it', async () => {
  const { port } = main;
  assert.equal((await call(port, 'GET', '/health')).status, 200);
  assert.equal((await call(port, 'GET', '/ready')).status, 200);
  for (const [m, p] of [['GET', '/v1/catalog'], ['GET', '/v1/universe'], ['POST', '/v1/run'], ['POST', '/v1/preview'], ['POST', '/v1/validate'], ['POST', '/v1/counts']]) {
    const none = await call(port, m, p, m === 'POST' ? runBody(RSI()) : undefined);
    assert.equal(none.status, 401, `${m} ${p}`); assert.equal(none.body.error.code, 'UNAUTHORIZED');
    const wrong = await call(port, m, p, undefined, { 'x-screener-worker-key': 'x'.repeat(40) });
    assert.equal(wrong.status, 401);
  }
  const h = await call(port, 'GET', '/health');
  assert.deepEqual(Object.keys(h.body).sort(), ['ok', 'published_at', 'refresh', 'snapshot_age_seconds', 'versions']);
  assert.ok(!JSON.stringify(h.body).includes(KEY) && !JSON.stringify(h.body).includes(PROXY));
});

test('protocol errors: an unknown route 404, a wrong method 405, a body that is not JSON 422 INVALID_INPUT, a body above SCREENER_MAX_REQUEST_BYTES 413, a malformed owner tag 422', async () => {
  const { port } = main;
  assert.equal((await call(port, 'GET', '/v1/nothing', undefined, auth())).status, 404);
  assert.equal((await call(port, 'GET', '/v1/run', undefined, auth())).status, 405);
  const notJson = await call(port, 'POST', '/v1/run', '{not json', auth());
  assert.equal(notJson.status, 422); assert.equal(notJson.body.error.code, 'INVALID_INPUT'); assert.equal(notJson.body.error.field, 'body');
  const big = await call(port, 'POST', '/v1/run', { pad: 'x'.repeat(140_000) }, auth());
  assert.equal(big.status, 413); assert.equal(big.body.error.code, 'REQUEST_TOO_LARGE');
  const tag = await call(port, 'POST', '/v1/run', runBody(RSI()), { ...auth(), 'x-screener-owner': 'NOT-HEX' });
  assert.equal(tag.status, 422); assert.equal(tag.body.error.field, 'x-screener-owner');
  // the connection stays usable after a refused body (read to its end before the answer)
  const agent = new http.Agent({ keepAlive: true, maxSockets: 1 });
  for (let i = 0; i < 2; i++) await new Promise<void>((ok, no) => { const r = http.request({ host: '127.0.0.1', port, path: '/v1/run', method: 'POST', agent, headers: { ...auth(), 'content-type': 'application/json' } }, res => { res.resume(); res.on('end', () => ok()) }); r.on('error', no); r.end('{"x":1}') });
  agent.destroy();
});

test('the envelope: schema_version, unknown fields, client_order, data_version and options are refused with the field and the fix', async () => {
  const { port } = main;
  const bad = async (body: unknown, field: string) => {
    const r = await call(port, 'POST', '/v1/run', body, auth(OWNER_A));
    assert.equal(r.status, 422, JSON.stringify(r.body)); assert.equal(r.body.error.code, 'INVALID_INPUT'); assert.equal(r.body.error.field, field); assert.ok(r.body.error.message.length > 10);
  };
  await bad({ ...runBody(RSI()), schema_version: 2 }, 'schema_version');
  await bad({ ...runBody(RSI()), extra: 1 }, 'extra');
  await bad({ ...runBody(RSI()), client_order: { page: 'p', seq: -1 } }, 'client_order');
  await bad({ ...runBody(RSI()), data_version: 'abc' }, 'data_version');
  await bad({ ...runBody(RSI()), options: { exhaustive: 'yes' } }, 'options.exhaustive');
  await bad({ ...runBody(RSI()), options: { fast: true } }, 'options.fast');
  // the definition is the core's: its refusal names the field (validate.ts)
  const r = await call(port, 'POST', '/v1/run', runBody({ ...RSI(), logic: 'most' }), auth(OWNER_A));
  assert.equal(r.status, 422); assert.equal(r.body.error.field, 'definition.logic');
  const p = await call(port, 'POST', '/v1/run', runBody(RSI(0)), auth(OWNER_A));
  assert.equal(p.status, 422); assert.equal(p.body.error.code, 'PARAM_OUT_OF_RANGE'); assert.equal(p.body.error.field, 'definition.conditions[0].test.metric.params.length');
});

test('the catalog: versions and data first, every worker limit with its rule and examples generated from the environment value, ETag and 304', async () => {
  const { port } = main;
  const c = await call(port, 'GET', '/v1/catalog', undefined, auth());
  assert.equal(c.status, 200);
  assert.deepEqual(Object.keys(c.body).slice(0, 2), ['versions', 'data']);
  const env = envFor('http://x');
  const want: Record<string, string> = { max_conditions: 'SCREENER_MAX_CONDITIONS', max_metric_filters: 'SCREENER_MAX_METRIC_FILTERS', within_max: 'SCREENER_WITHIN_MAX',
    cap_budget_ms: 'SCREENER_CAP_BUDGET_MS', compute_budget: 'SCREENER_MAX_CPU_MS', deadline_ms: 'SCREENER_DEADLINE_MS', owner_inflight: 'SCREENER_OWNER_INFLIGHT',
    owner_cpu_budget: 'SCREENER_OWNER_CPU_MS', previous_grace_s: 'SCREENER_PREVIOUS_GRACE_S', queue: 'SCREENER_QUEUE', max_counts: 'SCREENER_MAX_COUNTS',
    max_response_bytes: 'SCREENER_MAX_RESPONSE_BYTES', max_file_bytes: 'SCREENER_MAX_FILE_BYTES', max_inflated_bytes: 'SCREENER_MAX_INFLATED_BYTES', max_refresh_bytes: 'SCREENER_MAX_REFRESH_BYTES' };
  for (const [name, variable] of Object.entries(want)) {
    const l = c.body.limits.find((x: any) => x.name === name);
    assert.ok(l, name);
    assert.equal(l.value, Number(env[variable]), name);
    assert.ok(typeof l.unit === 'string' && l.unit.length > 0, `${name}.unit`);
    for (const k of ['rule', 'example_ok', 'example_refused']) assert.ok(typeof l[k] === 'string' && l[k].length > 10, `${name}.${k}`);
    assert.ok(l.rule.includes(String(l.value)), `${name}: the rule names the value`);
  }
  assert.equal(c.body.indicators.length, 53);
  assert.ok(c.body.indicators.every((i: any) => typeof i.description === 'string' && i.description.length >= 20 && 'short' in i), 'description and short (page O1, O5)');
  assert.deepEqual(c.body.presets.find((p: any) => p.id === 'oversold').view, { sort: { key: 'c:b', dir: 'asc' } }, 'a preset\'s default sort (page O2)');
  assert.equal(c.body.presets.find((p: any) => p.id === 'golden').view, undefined);
  assert.ok(c.body.presets.length > 0 && c.body.presets.every((p: any) => 'availability' in p && 'match_count' in p));
  assert.ok(c.body.presets.some((p: any) => p.availability === 'AVAILABLE' && typeof p.match_count === 'number'));
  assert.ok(c.body.presets.filter((p: any) => p.availability !== 'AVAILABLE').every((p: any) => p.reason && p.match_count === null));
  assert.deepEqual(c.body.periods, { '1M': 21, '3M': 63, '6M': 126, '1Y': 252 });
  assert.equal(c.body.groupings[0].key, 'sector');
  const etag = c.headers.etag as string;
  assert.match(etag, /^"[0-9a-f]{64}"$/);
  const again = await call(port, 'GET', '/v1/catalog', undefined, { ...auth(), 'if-none-match': etag });
  assert.equal(again.status, 304); assert.equal(again.raw.length, 0);
  const u = await call(port, 'GET', '/v1/universe', undefined, auth());
  assert.equal(u.status, 200); assert.equal(u.body.rows.length, 10); assert.ok(!u.body.rows.some((r: any) => r.ticker === 'IHSG'));
  const plain = await call(port, 'GET', '/v1/universe', undefined, { ...auth(), 'accept-encoding': 'identity' });
  assert.equal(plain.headers['content-encoding'], undefined); assert.deepEqual(plain.body, u.body);
});

test('the result cache: two owners with one definition share one computation, byte for byte; computed fresh for each, the answers differ only in timings_ms; nothing of the owner is in them', async () => {
  const { app, port } = main;
  const a = await call(port, 'POST', '/v1/run', runBody(RSI(9)), auth(OWNER_A));
  const b = await call(port, 'POST', '/v1/run', runBody(RSI(9), 7), auth(OWNER_B));
  assert.equal(a.status, 200); assert.ok(a.raw.equals(b.raw), 'one computation');
  assert.equal(logs.events('run').at(-1)!.cache_hit, true);
  app.results.dropSnapshot(app.state().current!.sid);
  const c = await call(port, 'POST', '/v1/run', runBody(RSI(9), 8), auth(OWNER_B));
  const strip = (x: any) => ({ ...x, timings_ms: null });
  assert.deepEqual(strip(c.body), strip(a.body));
  const text = a.raw.toString();
  for (const s of [OWNER_A, OWNER_B, 'pg1', 'client_order', KEY]) assert.ok(!text.includes(s), `no ${s} in an answer`);
  assert.deepEqual(Object.keys(a.body).slice(0, 3), ['schema_version', 'versions', 'data']);
  assert.match(a.body.versions.definition_hash, /^[0-9a-f]{64}$/);
  // options change the bytes, so they are part of the key
  const ex = await call(port, 'POST', '/v1/run', runBody(RSI(9), 9, { options: { explain: true } }), auth(OWNER_A));
  assert.ok(ex.body.plan && !a.body.plan);
});

test('a screen without conditions lists the universe (universe_only)', async () => {
  const { port } = main;
  const r = await call(port, 'POST', '/v1/run', runBody({ universe: U, conditions: [], logic: 'all' }), auth(OWNER_A));
  assert.equal(r.body.mode, 'universe_only'); assert.equal(r.body.need, 0); assert.equal(r.body.rows.length, r.body.universe.eligible);
  assert.ok(r.body.rows.every((x: any) => x.status === 'match' && x.met === 0 && x.cells.length === 0));
});

test('P4: stale and price-break tickers are hidden by default and counted; shown through the chips, they carry their remarks and their values, a price-derived cell across the ex-date marked PRICE_BREAK_IN_LOOKBACK', async () => {
  const u = universe(6, 320);
  u.prices.OLD = walk(9, 300, { last: '2026-08-21' });
  u.ref.push(['OLD', 'Stale', 'stock', 'Energy', 'Coal']);
  const ex = u.prices.T002[u.prices.T002.length - 5][0];
  const fake = await startFakeTerminal({ key: PROXY, publication: { finished_at: '2026-10-27T13:03:23Z', ...u, actions: [['T002', ex, 'STOCK_SPLIT', 1, 5, null, null]] } });
  const app = createApp(configFor(fake.url, { SCREENER_THREADS: '1' }), { pollMs: 3_600_000 });
  const port = await app.listen(0, '127.0.0.1');
  apps.push({ app, fake });
  await app.refresher.tick();
  const def = (chips: Record<string, boolean>) => ({ universe: { ...U, ...chips }, logic: 'all', conditions: [{ id: 'a', enabled: true, test: { kind: 'value', op: 'lt', value: 101, metric: { kind: 'indicator', indicator: 'I13', params: {}, output: 'rsi' } } }] });
  const hidden = await call(port, 'POST', '/v1/run', runBody(def({})), auth(OWNER_A));
  assert.deepEqual(hidden.body.universe, { listed: 7, eligible: 5, stale_hidden: 1, price_break_hidden: 1, filtered_out: 0 });
  assert.ok(!hidden.body.rows.some((r: any) => r.ticker === 'OLD' || r.ticker === 'T002'));
  const shown = await call(port, 'POST', '/v1/run', runBody(def({ traded_on_eval_date: false, exclude_price_breaks: false }), 2), auth(OWNER_A));
  assert.equal(shown.body.universe.eligible, 7);
  const old = shown.body.rows.find((r: any) => r.ticker === 'OLD'), split = shown.body.rows.find((r: any) => r.ticker === 'T002');
  assert.deepEqual(old.remarks, [{ code: 'STALE', last_bar_date: '2026-08-21' }]);
  assert.equal(old.cells[0].eval_date, '2026-08-21', 'evaluated at its own last bar, never NA for being stale');
  assert.equal(split.remarks[0].code, 'PRICE_BREAK'); assert.equal(split.remarks[0].ex_date, ex);
  assert.equal(split.cells[0].remark, 'PRICE_BREAK_IN_LOOKBACK'); assert.equal(typeof split.cells[0].value, 'number', 'the value is shown (P4.1 A)');
  assert.ok(shown.body.warnings.some((w: any) => w.code === 'PRICE_BREAKS_IN_RESULT'));
  const universeRows = (await call(port, 'GET', '/v1/universe', undefined, auth())).body.rows;
  assert.equal(universeRows.length, 7, 'GET universe lists the hidden tickers too, so the chips can count them');
});

test('compute_budget: a screen whose worst case is above SCREENER_MAX_CPU_MS is refused before compute, naming its costliest condition; a pre-warmed one passes', async () => {
  const { port } = await start({ SCREENER_MAX_CPU_MS: '1', SCREENER_OWNER_CPU_MS: '1' });
  const donchian = { universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test: { kind: 'value', op: 'gt', value: -50, metric: { kind: 'indicator', indicator: 'I16', params: { length: 500 }, output: 'williams_r' } } }] };
  const custom = await call(port, 'POST', '/v1/run', runBody(donchian), auth(OWNER_A));
  assert.equal(custom.status, 422);
  assert.equal(custom.body.error.code, 'LIMIT_EXCEEDED');
  assert.equal(custom.body.error.details.limit, 'compute_budget'); assert.equal(custom.body.error.details.allowed, 1); assert.equal(custom.body.error.details.costliest, 'a');
  assert.ok(custom.body.error.details.needed > 1);
  const pinned = await call(port, 'POST', '/v1/run', runBody(RSI()), auth(OWNER_A));
  assert.equal(pinned.status, 200, JSON.stringify(pinned.body));
});

test('P33: an owner over SCREENER_OWNER_CPU_MS per minute is refused with the seconds to wait; another owner is not; a cache hit is never refused', async () => {
  const { app, port } = await start({ SCREENER_MAX_CPU_MS: '100', SCREENER_OWNER_CPU_MS: '100' });
  const ok = await call(port, 'POST', '/v1/run', runBody(RSI(5)), auth(OWNER_A));
  assert.equal(ok.status, 200);
  assert.ok(app.budget.spent(OWNER_A) > 0, 'the run\'s thread time is counted for its owner');
  app.budget.record(OWNER_A, 100);                               // the owner's minute is used up
  const refused = await call(port, 'POST', '/v1/run', runBody(RSI(6)), auth(OWNER_A));
  assert.equal(refused.status, 422); assert.equal(refused.body.error.code, 'LIMIT_EXCEEDED');
  assert.equal(refused.body.error.details.limit, 'owner_cpu_budget'); assert.equal(refused.body.error.details.allowed, 100);
  assert.ok(refused.body.error.details.retry_after_seconds >= 1 && refused.body.error.details.retry_after_seconds <= 60); assert.match(refused.body.error.message, /Wait \d+ s/);
  const other = await call(port, 'POST', '/v1/run', runBody(RSI(6)), auth(OWNER_B));
  assert.equal(other.status, 200, 'another owner has its own minute');
  const hit = await call(port, 'POST', '/v1/run', runBody(RSI(5), 3), auth(OWNER_A));
  assert.equal(hit.status, 200, 'a cache hit is answered outside the budgets');
  assert.ok(hit.raw.equals(ok.raw));
});

test('the response cap and the counts cap are refused with their limit names', async () => {
  const { port } = await start({ SCREENER_MAX_RESPONSE_BYTES: '1500', SCREENER_MAX_COUNTS: '2' });
  const r = await call(port, 'POST', '/v1/run', runBody(RSI(undefined, 101)), auth(OWNER_A));
  assert.equal(r.status, 422); assert.equal(r.body.error.details.limit, 'max_response_bytes');
  const c = await call(port, 'POST', '/v1/counts', { schema_version: 1, definitions: [1, 2, 3].map(i => ({ item_id: `s${i}`, definition: RSI() })) }, auth(OWNER_A));
  assert.equal(c.status, 422); assert.equal(c.body.error.details.limit, 'max_counts'); assert.equal(c.body.error.details.needed, 3);
});

test('counts: each definition counted (cached per definition), an invalid one is that entry\'s error; validate answers the normalized definition and its hash', async () => {
  const { port } = main;
  const c = await call(port, 'POST', '/v1/counts', { schema_version: 1, definitions: [{ item_id: 'x', definition: RSI(11) }, { item_id: 'y', definition: { ...RSI(), logic: 'most' } }, { item_id: 'z', definition: RSI() }] }, auth(OWNER_A));
  assert.equal(c.status, 200);
  assert.deepEqual(Object.keys(c.body), ['versions', 'data', 'counts']);
  assert.deepEqual(c.body.counts.map((x: any) => x.item_id), ['x', 'y', 'z']);
  assert.ok(Number.isInteger(c.body.counts[0].match_count) && Number.isInteger(c.body.counts[0].near_count));
  assert.equal(c.body.counts[1].error.code, 'INVALID_CONDITION');
  const run = await call(port, 'POST', '/v1/run', runBody(RSI(11)), auth(OWNER_B));
  assert.equal(run.body.match_count, c.body.counts[0].match_count, 'counts = the run');
  const v = await call(port, 'POST', '/v1/validate', { schema_version: 1, definition: RSI(11) }, auth(OWNER_A));
  assert.equal(v.status, 200); assert.equal(v.body.valid, true); assert.equal(v.body.definition_hash, run.body.versions.definition_hash);
  assert.equal(v.body.normalized.conditions[0].test.metric.params.source, 'close', 'parameters completed');
  // the versions it was checked against (edge-bff stores registry and screener_registry with a saved item from them)
  const { definition_hash: _h, ...runVersions } = run.body.versions;
  assert.deepEqual(v.body.versions, runVersions);
});

test('counts: every entry of the answer is counts or an error in request order (contract CountsEntry); an item the thread did not answer is that entry\'s error, never a null', () => {
  const ok = (item_id: string, n: number) => ({ item_id, match_count: n, near_count: 1, busy_ms: 7 });
  const refused = { item_id: 'c', error: { code: 'INVALID_CONDITION', field: 'definitions[2].definition.logic', message: 'logic must be one of all, any, at_least.' } };
  // a: from the counts cache; b: computed; c: refused before compute; d: sent to the thread, which answered nothing for
  // it; the thread's answers in another order, one for an item already settled and one for an item never asked
  const a = countsAnswer([{ item_id: 'a' }, { item_id: 'b' }, { item_id: 'c' }, { item_id: 'd' }], [ok('a', 3), null, refused, null], [ok('zz', 5), ok('b', 4), ok('a', 99)]);
  assert.deepEqual(a.missing, ['d']);
  assert.deepEqual(a.counts, [
    { item_id: 'a', match_count: 3, near_count: 1 }, { item_id: 'b', match_count: 4, near_count: 1 }, { item_id: 'c', error: refused.error },
    { item_id: 'd', error: { code: 'INTERNAL_ERROR', message: 'The worker failed; the error is in its log.' } },
  ]);
  for (const x of a.counts) assert.ok(x && typeof x.item_id === 'string' && ('error' in x ? typeof x.error.code === 'string' : Number.isInteger(x.match_count) && Number.isInteger(x.near_count)), JSON.stringify(x));
  assert.deepEqual(countsAnswer([], [], []), { counts: [], missing: [] });
});

test('preview: one ticker\'s cells and status (match.ts), bars, IHSG aligned, overlays, markers, perf; pinned to its data_version; an unknown ticker is refused', async () => {
  const { app, port } = main;
  const v = app.state().current!.price_data;
  const def = { universe: U, logic: 'all', conditions: [
    { id: 'a', enabled: true, test: { kind: 'value', op: 'lt', value: 101, metric: { kind: 'indicator', indicator: 'I13', params: {}, output: 'rsi' } } },
    { id: 'b', enabled: true, test: { kind: 'event', within: 130, signal: { op: 'crosses_above', lhs: { kind: 'price', field: 'close' }, rhs: { kind: 'indicator', indicator: 'I01', params: {}, output: 'sma' } } } }] };
  const p = await call(port, 'POST', '/v1/preview', { schema_version: 1, client_order: { page: 'pg1', seq: 1 }, data_version: v, definition: def, ticker: 'T003' }, auth(OWNER_A));
  assert.equal(p.status, 200, JSON.stringify(p.body));
  assert.deepEqual(Object.keys(p.body).slice(0, 2), ['versions', 'data']);
  assert.equal(p.body.cells.length, 2); assert.ok(['match', 'near', 'fail'].includes(p.body.status));
  assert.equal(p.body.bars.d.length, 260); assert.equal(p.body.ihsg_close.length, 260);
  assert.ok(p.body.overlays.some((o: any) => o.condition_id === 'a') && p.body.overlays.every((o: any) => o.values.length === 260));
  assert.equal(p.body.markers.length, 1); assert.ok(p.body.markers[0].bars.every((m: any) => m.kind === 'crosses_above'));
  assert.deepEqual(Object.keys(p.body.perf), ['1M', '3M', '6M', '1Y']);
  assert.equal(typeof p.body.perf['1M'].stock_pct, 'number');
  const none = await call(port, 'POST', '/v1/preview', { schema_version: 1, client_order: { page: 'pg1', seq: 2 }, data_version: v, definition: def, ticker: 'ZZZZ' }, auth(OWNER_A));
  assert.equal(none.status, 422); assert.equal(none.body.error.field, 'ticker');
  const noVersion = await call(port, 'POST', '/v1/preview', { schema_version: 1, client_order: { page: 'pg1', seq: 3 }, definition: def, ticker: 'T003' }, auth(OWNER_A));
  assert.equal(noVersion.status, 422); assert.equal(noVersion.body.error.field, 'data_version');
});

test('logs explain a request: stages with tickers in and out, conditions with their source, cache hits, queue and total ms; no key or URL in any line', async () => {
  const { port } = main;
  await call(port, 'POST', '/v1/run', runBody(RSI(13)), auth(OWNER_A));
  const l = logs.events('run').at(-1)!;
  assert.equal(l.owner_tag, OWNER_A);
  assert.deepEqual(l.stages.map((s: any) => s.name), ['S0', 'S1', 'S2', 'S3', 'S4']);
  assert.ok(l.stages.every((s: any) => Number.isInteger(s.in) && Number.isInteger(s.out) && Number.isInteger(s.ms)));
  assert.equal(l.conditions[0].source, 'dynamic'); assert.equal(l.series_computed, 10);
  for (const k of ['definition_hash', 'data_version', 'replica', 'n_conditions', 'pruned', 'queue_ms', 'total_ms', 'payload_bytes', 'status', 'cache_hit']) assert.ok(k in l, k);
  const all = JSON.stringify(logs.lines);
  assert.ok(!all.includes(KEY) && !all.includes(PROXY), 'no key in the logs');
  assert.ok(!/X-Amz-Signature/.test(all), 'no presigned URL in the logs');
});
