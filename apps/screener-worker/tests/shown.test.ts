/* EXEC-MU-ACCOUNTS (CONTRACT 8b O3b-2, re-check R1-35, user 2026-11-19 "1a": Screener conditions on the attributes
   every result row and /universe show are not gated by id): the one definition of those attributes is the catalog's
   universe entries that name their /universe row field (screener-metrics.json `row`; catalog.ts SHOWN_ATTRIBUTES),
   which the allow walk (run.ts definitionItems) and edge-bff (app/catalog.py shown_attributes) read. Held here to the
   rows the worker actually answers, both ways, on a publication with the stock-lists file: every /universe row carries
   each named field, and no /universe or result row carries the value of a universe attribute the catalog does not name
   (a new attribute a row starts to show joins the set by its catalog entry, or this test fails). Then a plan holding no
   Screener metric runs a screen on each of them over HTTP. */
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { METRICS_CATALOG, SHOWN_ATTRIBUTES } from '../../edge-bff/screener/src/core/catalog.ts';
import { createApp } from '../src/server.ts';
import type { WorkerApp } from '../src/server.ts';
import { startFakeTerminal, universe } from './fake-terminal.mjs';
import { OWNER_A, PROXY, auth, call, captureLogs, configFor } from './helpers.ts';

captureLogs();
const AS_OF = '2026-11-09T13:31:48.255552+00:00';
const LISTS = [
  ['INDEX:550', 'INDEX', 'LQ45', 'LQ45', '45 saham likuid.', AS_OF, ['T000', 'T001', 'T002']],
  ['KONGLO:9', 'KONGLO', 'SALIM', 'Salim', 'Grup usaha versi Stockbit.', AS_OF, ['T001']],
];
const ALL = { indicator: '*', flow_indicator: '*', candle_pattern: '*', screener_metric: '*' };
const U = { security_types: ['stock'], price_min: null, adv20_min_idr: null };
let app: WorkerApp, fake: { close(): Promise<void> }, port: number;
before(async () => {
  fake = await startFakeTerminal({ key: PROXY, publication: { finished_at: '2026-10-27T13:03:23Z', ...universe(6, 300), actions: [], stockLists: LISTS } });
  app = createApp(configFor(fake.url, { SCREENER_THREADS: '1' }), { pollMs: 3_600_000 });
  port = await app.listen(0, '127.0.0.1');
  await app.refresher.tick();
  assert.ok(app.state().current, 'snapshot loaded');
});
after(async () => { await app?.close(); await fake?.close() });

const universeIds = new Set(METRICS_CATALOG.metrics.filter(m => m.kind === 'universe').map(m => m.id));

test('the shown attributes are the catalog\'s universe entries that name their row field, and each is a universe attribute', () => {
  assert.deepEqual([...SHOWN_ATTRIBUTES.entries()].sort(), [['adv20_idr', 'adv20_idr'], ['bars', 'bars'], ['chg_1d_pct', 'chg_1d_pct'],
    ['index_membership', 'indices'], ['last', 'last']]);
  for (const id of SHOWN_ATTRIBUTES.keys()) assert.ok(universeIds.has(id), id);
});

test('every /universe row carries each shown attribute\'s field, and no row of /universe or of a result carries an attribute the catalog does not name', async () => {
  const uni = await call(port, 'GET', '/v1/universe', undefined, auth(OWNER_A));
  assert.equal(uni.status, 200, JSON.stringify(uni.body));
  const rows = uni.body.rows as Record<string, unknown>[];
  assert.ok(rows.length >= 6);
  for (const [id, field] of SHOWN_ATTRIBUTES) {
    for (const r of rows) assert.ok(field in r, `${r.ticker} has no ${field} (${id})`);
  }
  const shownFields = new Set(SHOWN_ATTRIBUTES.values());
  const run = await call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'shown', seq: 1 }, definition: { universe: U, conditions: [], logic: 'all' },
    options: { exhaustive: true }, context: { allow: ALL } }, auth(OWNER_A));
  assert.equal(run.status, 200, JSON.stringify(run.body));
  const result = run.body.rows as Record<string, unknown>[];
  assert.ok(result.length >= 1);
  for (const r of [...rows, ...result]) {
    const carried = Object.keys(r).filter(k => universeIds.has(k) && r[k] !== undefined);
    assert.deepEqual(carried.filter(k => !SHOWN_ATTRIBUTES.has(k) && !shownFields.has(k)), [], `${r.ticker}: an attribute a row shows without its catalog row field`);
  }
  // a result row repeats these values of its /universe row
  const byTicker = new Map(rows.map(r => [r.ticker, r]));
  for (const r of result) for (const k of ['last', 'chg_1d_pct', 'adv20_idr']) assert.equal(r[k], byTicker.get(r.ticker)![k], `${r.ticker} ${k}`);
});

test('a plan holding no Screener metric screens on every shown attribute; another universe attribute is still gated', async () => {
  const on = (attr: string) => ({ universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true, test: { kind: 'value', metric: { kind: 'universe', attr }, op: 'gt', value: -1e18 } }] });
  let seq = 1;
  for (const attr of SHOWN_ATTRIBUTES.keys()) {
    if (attr === 'index_membership') continue;      // REQUIRES_DATA (no index constituent file): refused as unavailable, never by the plan
    const r = await call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'shown', seq: ++seq }, definition: on(attr),
      context: { allow: { ...ALL, screener_metric: [] } } }, auth(OWNER_A));
    assert.equal(r.status, 200, `${attr}: ${JSON.stringify(r.body)}`);
  }
  const membership = await call(port, 'POST', '/v1/validate', { schema_version: 1, definition: on('index_membership'), context: { allow: { ...ALL, screener_metric: [] } } }, auth(OWNER_A));
  assert.notEqual(membership.body?.error?.code, 'CAPABILITY_REQUIRED', JSON.stringify(membership.body));
  const other = await call(port, 'POST', '/v1/validate', { schema_version: 1, definition: { universe: U, logic: 'all', conditions: [{ id: 'a', enabled: true,
    test: { kind: 'value', metric: { kind: 'xsection', metric: 'return_rank', params: {} }, op: 'ge', value: 0 } }] }, context: { allow: { ...ALL, screener_metric: [] } } }, auth(OWNER_A));
  assert.deepEqual([other.status, other.body.error.code, other.body.error.details.capability], [403, 'CAPABILITY_REQUIRED', 'screener.metric:return_rank']);
});
