/* The refresh and the swap (refresh.ts, server.ts; report 6.5 rules 1-5, 6d.2, 6d.4; TEST PLAN 10b.4 "Refresh
   integrity", "Version stability", 10b.11 "Version pinning and grace window"), end to end against the fake terminal-api
   with files in the publisher's format: the worker refreshes, verifies, swaps all-or-nothing and serves. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, test } from 'node:test';
import { createApp } from '../src/server.ts';
import type { WorkerApp } from '../src/server.ts';
import { encode } from '../../backtest-worker/tests/fake-terminal.mjs';
import { startFakeTerminal, universe, xsectionPriceDoc } from './fake-terminal.mjs';
import { OWNER_A, PROXY, auth, call, captureLogs, configFor, sleep } from './helpers.ts';

const logs = captureLogs();
const open: { app: WorkerApp; fake: { close(): Promise<void> } }[] = [];
after(async () => { for (const o of open) { await o.app.close(); await o.fake.close() } });

const RSI = { universe: { security_types: ['stock'], price_min: null, adv20_min_idr: null }, conditions: [{ id: 'a', enabled: true, test: { kind: 'value', op: 'lt', value: 101, metric: { kind: 'indicator', indicator: 'I13', params: {}, output: 'rsi' } } }], logic: 'all' };
const pubOf = (finished_at: string, u = universe(6, 300), extra: Record<string, unknown> = {}) => ({ finished_at, ...u, actions: [], ...extra });
async function start(publication: any, env: Record<string, string> = {}, fakeOpts: Record<string, unknown> = {}) {
  const fake = await startFakeTerminal({ key: PROXY, publication, ...fakeOpts });
  const app = createApp(configFor(fake.url, { SCREENER_THREADS: '1', ...env }), { pollMs: 3_600_000 });
  const port = await app.listen(0, '127.0.0.1');
  open.push({ app, fake });
  return { fake, app, port };
}
const grants = (fake: any) => fake.requests.filter((r: any) => r.path === '/api/terminal/v1/xsection').length;
const failures = () => logs.events('REFRESH_FAILED');

test('a publication loads: index read, files granted and verified, snapshot built, swapped; /ready, /health and the catalog follow', async () => {
  const { app, port, fake } = await start(pubOf('2026-10-27T13:03:23Z'));
  assert.equal((await call(port, 'GET', '/ready')).status, 503, 'not ready before the first snapshot');
  const loading = await call(port, 'GET', '/v1/catalog', undefined, auth());
  assert.equal(loading.status, 503); assert.equal(loading.body.error.code, 'SCREENER_NOT_READY'); assert.ok(Number(loading.headers['retry-after']) >= 1);
  await app.refresher.tick();
  assert.ok(app.state().current);
  assert.equal((await call(port, 'GET', '/ready')).status, 200);
  const h = await call(port, 'GET', '/health');
  assert.equal(h.body.refresh, 'ready'); assert.equal(h.body.published_at, '2026-10-27T13:03:23Z'); assert.equal(h.body.versions.price_data.length, 64);
  const line = logs.events('refresh').at(-1)!;
  for (const k of ['data_version', 'published_at', 'files', 'bytes', 'granted', 'cached', 'grant_ms', 'download_ms', 'decode_ms', 'check_ms', 'defaults_ms', 'snapshot_digest', 'rss', 'orphans'])
    assert.ok(k in line, `refresh log has ${k}`);
  assert.deepEqual(line.granted, ['price', 'actions']);
  assert.equal(grants(fake), 1, 'one /xsection grant for both files');
  const cat = await call(port, 'GET', '/v1/catalog', undefined, auth());
  assert.equal(cat.body.data.refresh, 'ready'); assert.equal(cat.body.versions.price_data, h.body.versions.price_data);
  assert.equal(cat.body.data.evaluation_date, '2026-10-27');
});

test('integrity: a wrong sha256 in the index fails the refresh (REFRESH_FAILED) and, with no earlier snapshot, the API answers 424 DATA_INTEGRITY', async () => {
  const before = failures().length;
  const { app, port } = await start(pubOf('2026-10-27T13:03:23Z', universe(6, 300), { files: { price: { sha256: 'f'.repeat(64) } } }));
  await app.refresher.tick();
  assert.equal(app.state().current, null);
  assert.equal(failures().length, before + 1);
  assert.equal(failures().at(-1)!.code, 'DATA_INTEGRITY');
  const r = await call(port, 'GET', '/v1/catalog', undefined, auth());
  assert.equal(r.status, 424); assert.equal(r.body.error.code, 'DATA_INTEGRITY');
  assert.equal((await call(port, 'GET', '/health')).body.refresh, 'loading');
});

test('integrity with a snapshot held: the failed publication keeps the previous one serving and the catalog says failed_keeping_previous', async () => {
  const { app, port, fake } = await start(pubOf('2026-10-27T13:03:23Z'));
  await app.refresher.tick();
  const v = app.state().current!.price_data;
  const u2 = universe(6, 301);
  fake.publish(pubOf('2026-10-28T13:03:23Z', u2, { files: { price: { body: encode(xsectionPriceDoc(u2.prices)).body.subarray(0, 1000) } } }));   // a truncated object
  await app.refresher.tick();
  assert.equal(app.state().current!.price_data, v, 'the previous snapshot still serves');
  assert.equal(failures().at(-1)!.keeping_previous, true);
  const cat = await call(port, 'GET', '/v1/catalog', undefined, auth());
  assert.equal(cat.body.data.refresh, 'failed_keeping_previous');
  const run = await call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'p', seq: 1 }, definition: RSI }, auth(OWNER_A));
  assert.equal(run.status, 200); assert.equal(run.body.versions.price_data, v);
  // the same publication is not retried before its backoff; a new one is tried at once
  const n = failures().length;
  await app.refresher.tick();
  assert.equal(failures().length, n, 'backoff: no second try of the same publication yet');
  fake.publish(pubOf('2026-10-29T13:03:23Z', universe(6, 302)));
  await app.refresher.tick();
  assert.notEqual(app.state().current!.price_data, v);
  assert.equal((await call(port, 'GET', '/v1/catalog', undefined, auth())).body.data.refresh, 'ready');
});

test('integrity: a ticker whose rows or last date disagree with its /manifest, and a price ticker missing from the reference file, abort the refresh', async () => {
  const u = universe(6, 300);
  const { app } = await start(pubOf('2026-10-27T13:03:23Z', u, { manifests: { T003: { 2026: { bytes: 10, rows: 1, first: '2026-01-02', last: '2026-10-27', sha256: 'a'.repeat(64) } } } }));
  await app.refresher.tick();
  assert.equal(app.state().current, null);
  assert.match(failures().at(-1)!.message, /T003: the price file has \d+ rows to 2026-10-27, its manifest 1 rows/);
  const u2 = universe(6, 300);
  const { app: app2 } = await start(pubOf('2026-10-27T13:03:23Z', { ...u2, ref: u2.ref.filter((r: unknown[]) => r[0] !== 'T004') }));
  await app2.refresher.tick();
  assert.equal(app2.state().current, null);
  assert.match(failures().at(-1)!.message, /not in the reference file/);
});

test('the caps: an indexed size above SCREENER_MAX_FILE_BYTES, or downloads above SCREENER_MAX_REFRESH_BYTES, are refused before any grant; a file inflating above SCREENER_MAX_INFLATED_BYTES aborts', async () => {
  const a = await start(pubOf('2026-10-27T13:03:23Z'), { SCREENER_MAX_FILE_BYTES: '1000' });
  await a.app.refresher.tick();
  assert.equal(grants(a.fake), 0, 'no grant');
  assert.equal(failures().at(-1)!.details.limit, 'file_bytes');
  const b = await start(pubOf('2026-10-27T13:03:23Z'), { SCREENER_MAX_REFRESH_BYTES: '2000' });
  await b.app.refresher.tick();
  assert.equal(grants(b.fake), 0, 'no grant');
  assert.equal(failures().at(-1)!.details.limit, 'refresh_bytes');
  const c = await start(pubOf('2026-10-27T13:03:23Z', universe(20, 400)), { SCREENER_MAX_INFLATED_BYTES: '300000' });
  await c.app.refresher.tick();
  assert.equal(c.app.state().current, null);
  assert.match(failures().at(-1)!.message, /inflates to more than 300000 bytes/);
});

test('the disk cache: a restart on a warm cache reads both files without a grant (a restart grants nothing)', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'screener-cache-'));
  const env = { SCREENER_CACHE_DIR: dir, SCREENER_CACHE_DIR_BYTES: String(64 * 1024 * 1024) };
  const pub = pubOf('2026-10-27T13:03:23Z');
  const first = await start(pub, env);
  await first.app.refresher.tick();
  assert.equal(grants(first.fake), 1);
  const second = await start(pub, env);
  await second.app.refresher.tick();
  assert.ok(second.app.state().current);
  assert.equal(grants(second.fake), 0, 'nothing granted');
  assert.deepEqual(logs.events('refresh').at(-1)!.cached, ['price', 'actions']);
  assert.equal(second.app.state().current!.price_data, first.app.state().current!.price_data);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('skew: /xsection from a terminal-api process still on the previous publication is asked again, then deferred, never a failure; it loads once the processes agree', async () => {
  const { app, fake } = await start(pubOf('2026-10-27T13:03:23Z'));
  fake.publish(pubOf('2026-10-28T13:03:23Z', universe(6, 301)));
  const old = fake.publication(0);
  fake.stateFor = (req: any) => req.path.endsWith('/xsection') ? old : fake.latest();
  const n = failures().length;
  await app.refresher.tick();
  assert.equal(app.state().current, null);
  assert.equal(failures().length, n, 'not a failure');
  assert.ok(logs.events('refresh_skew').length >= 2, 'asked again');
  assert.equal(logs.events('refresh_deferred').at(-1)!.published_at, '2026-10-28T13:03:23Z');
  fake.stateFor = () => fake.latest();
  await app.refresher.tick();
  assert.equal(app.state().current!.finished_at, '2026-10-28T13:03:23Z');
});

test('the same files on a new publication: no download, no recompute, no swap; only published_at advances (6d.2)', async () => {
  const pub = pubOf('2026-10-27T13:03:23Z');
  const { app, port, fake } = await start(pub);
  await app.refresher.tick();
  const sid = app.state().current!.sid, swaps = logs.events('swap').length;
  const body = { schema_version: 1, client_order: { page: 'p', seq: 1 }, definition: RSI };
  const before = await call(port, 'POST', '/v1/run', body, auth(OWNER_A));
  assert.equal(before.body.data.published_at, '2026-10-27T13:03:23Z');
  fake.publish({ ...pub, finished_at: '2026-10-27T23:00:00Z', broker_behind_sessions: 1 });
  await app.refresher.tick();
  assert.equal(app.state().current!.sid, sid);
  assert.equal(logs.events('swap').length, swaps, 'no swap');
  assert.equal(grants(fake), 1, 'no second grant');
  assert.equal(logs.events('refresh_skipped').at(-1)!.published_at, '2026-10-27T23:00:00Z');
  const cat = await call(port, 'GET', '/v1/catalog', undefined, auth());
  assert.equal(cat.body.data.published_at, '2026-10-27T23:00:00Z'); assert.equal(cat.body.data.broker_behind_sessions, 1);
  assert.equal((await call(port, 'GET', '/health')).body.published_at, '2026-10-27T23:00:00Z');
  // a cached answer is never served with the older publication's data block: the same numbers, the new published_at
  const after = await call(port, 'POST', '/v1/run', { ...body, client_order: { page: 'p', seq: 2 } }, auth(OWNER_A));
  assert.equal(after.status, 200, JSON.stringify(after.body));
  assert.equal(after.body.data.published_at, '2026-10-27T23:00:00Z'); assert.equal(after.body.data.broker_behind_sessions, 1);
  assert.deepEqual(after.body.rows, before.body.rows);
  // the presets are computed again (pinned, so a preset click stays a cache hit) and the catalog keeps their counts
  let presets: any[] = [];
  for (let i = 0; i < 100 && !presets.some(p => p.availability === 'AVAILABLE' && typeof p.match_count === 'number'); i++) {
    await sleep(50);
    presets = (await call(port, 'GET', '/v1/catalog', undefined, auth())).body.presets;
  }
  assert.ok(presets.some(p => p.availability === 'AVAILABLE' && typeof p.match_count === 'number'));
});

test('one refresh at a time: a poll while a refresh runs does nothing', async () => {
  const { app, fake } = await start(pubOf('2026-10-27T13:03:23Z'));
  await Promise.all([app.refresher.tick(), app.refresher.tick(), app.refresher.tick()]);
  assert.equal(grants(fake), 1);
  assert.equal(logs.events('swap').filter(l => l.published_at === '2026-10-27T13:03:23Z').length >= 1, true);
});

test('versions: a run pinned to the previous snapshot is served in the grace window and refused after it (DATA_VERSION_CHANGED); one the replica has not loaded is DATA_VERSION_PENDING', async () => {
  const { app, port, fake } = await start(pubOf('2026-10-27T13:03:23Z'), { SCREENER_PREVIOUS_GRACE_S: '1' });
  await app.refresher.tick();
  const vA = app.state().current!.price_data;
  fake.publish(pubOf('2026-10-28T13:03:23Z', universe(6, 301)));
  await app.refresher.tick();
  const vB = app.state().current!.price_data;
  assert.notEqual(vA, vB);
  const run = (v: string, seq: number) => call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'p', seq }, data_version: v, definition: RSI }, auth(OWNER_A));
  const a = await run(vA, 1), b = await run(vB, 2);
  assert.equal(a.status, 200); assert.equal(a.body.versions.price_data, vA, 'served on the previous snapshot');
  assert.equal(b.status, 200); assert.equal(b.body.versions.price_data, vB);
  const unknown = await run('0'.repeat(64), 3);
  assert.equal(unknown.status, 409); assert.equal(unknown.body.error.code, 'DATA_VERSION_CHANGED');
  // a publication terminal-api names but this replica has not loaded: an unknown version is PENDING
  fake.publish(pubOf('2026-10-29T13:03:23Z', universe(6, 302)));
  await sleep(5100);                                           // past PENDING_CHECK_MS and the 1 s grace
  const pending = await run('1'.repeat(64), 4);
  assert.equal(pending.status, 409); assert.equal(pending.body.error.code, 'DATA_VERSION_PENDING');
  const gone = await run(vA, 5);
  assert.equal(gone.status, 409); assert.equal(gone.body.error.code, 'DATA_VERSION_CHANGED', 'the grace window has passed');
  const preview = await call(port, 'POST', '/v1/preview', { schema_version: 1, client_order: { page: 'p', seq: 6 }, data_version: vA, definition: RSI, ticker: 'T001' }, auth(OWNER_A));
  assert.equal(preview.status, 409); assert.equal(preview.body.error.code, 'DATA_VERSION_CHANGED');
});
