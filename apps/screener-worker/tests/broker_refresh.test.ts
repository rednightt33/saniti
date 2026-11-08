/* EXEC-SCREENER-FLOW-CANDLES P4 (user 2026-11-07: per-date broker files; worker limits unchanged; K1 window 60
   sessions; verification/screener/P4_BROKER_DAYS.md sections 3 and 4), end to end against the fake terminal-api with
   broker day files in the publisher's format (tests/fake-terminal.mjs xsectionBrokerDoc, encodeBrokerDay): the days
   load beside the Phase 1 files; the download budget takes the Phase 1 files first, then the days newest first, and
   the rest load on follow-up refreshes started at once; /xsection is asked in batches of at most 16 names; the same
   files and days skip; a changed or new day downloads that day only (the others carried); a day dropped of a ticker
   without price is read again when the price file changes; a broken day or one above the per-file cap fails the
   refresh and keeps the previous snapshot; versions.flow_data, data.flow_through, data.broker_window and the result
   cache key follow the days. */
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, test } from 'node:test';
import { createApp } from '../src/server.ts';
import type { WorkerApp } from '../src/server.ts';
import { brokerRowsOf as fakeRows, startFakeTerminal, universe, xsectionBrokerDoc } from './fake-terminal.mjs';
import { OWNER_A, PROXY, auth, call, captureLogs, configFor, until } from './helpers.ts';

const logs = captureLogs();
const open: { app: WorkerApp; fake: { close(): Promise<void> } }[] = [];
after(async () => { for (const o of open) { await o.app.close(); await o.fake.close() } });

const RSI = { universe: { security_types: ['stock'], price_min: null, adv20_min_idr: null }, conditions: [{ id: 'a', enabled: true, test: { kind: 'value', op: 'lt', value: 101, metric: { kind: 'indicator', indicator: 'I13', params: {}, output: 'rsi' } } }], logic: 'all' };
const STOCKS = ['T000', 'T001', 'T002', 'T003', 'T004', 'T005'];
/** the last n sessions of the fake calendar (IHSG's dates), oldest first */
const sessions = (u: ReturnType<typeof universe>, n: number): string[] => u.prices.IHSG.slice(-n).map((r: unknown[]) => r[0] as string);
/** broker rows per date: rows(date) or the fake's deterministic rows for the six stocks */
const brokerOf = (dates: string[], rows: (date: string, k: number) => unknown[][] = (d, k) => fakeRows(k + 1, d, STOCKS)) => Object.fromEntries(dates.map((d, k) => [d, rows(d, k)]));
const pubOf = (finished_at: string, u: ReturnType<typeof universe>, broker: Record<string, unknown[][]>, extra: Record<string, unknown> = {}) => ({ finished_at, ...u, actions: [], broker, ...extra });
async function start(publication: any, env: Record<string, string> = {}) {
  const fake = await startFakeTerminal({ key: PROXY, publication });
  const app = createApp(configFor(fake.url, { SCREENER_THREADS: '1', ...env }), { pollMs: 3_600_000 });
  const port = await app.listen(0, '127.0.0.1');
  open.push({ app, fake });
  return { fake, app, port };
}
const xsectionCalls = (fake: any): string[][] => fake.requests.filter((r: any) => r.path === '/api/terminal/v1/xsection').map((r: any) => JSON.parse(r.body).names);
const refreshes = (published_at: string) => logs.events('refresh').filter(l => l.published_at === published_at);
const flowDataOf = (index: Record<string, { sha256: string }>, names: string[]) => crypto.createHash('sha256').update(names.map(n => `${n}:${index[n].sha256}`).sort().join('\n')).digest('hex');
const brokerNames = (index: Record<string, unknown>) => Object.keys(index).filter(n => n.startsWith('broker-')).sort();

test('broker days load beside the Phase 1 files: versions.flow_data, data.flow_through and data.broker_window on every answer, the refresh line counts them, a ticker without price is not loaded', async () => {
  const u = universe(6, 300), dates = sessions(u, 5);
  // the newest day also names a ticker the price file does not have
  const broker = brokerOf(dates, (d, k) => k === 4 ? [...fakeRows(k + 1, d, STOCKS), ...fakeRows(99, d, ['ZZZZ'])] : fakeRows(k + 1, d, STOCKS));
  const { app, port, fake } = await start(pubOf('2026-10-27T13:03:23Z', u, broker));
  await app.refresher.tick();
  const s = app.state().current!, index = fake.latest().state.xsection;
  assert.deepEqual(s.desc.broker.dates, dates);
  const names = brokerNames(index), flow = flowDataOf(index, names);
  const cat = await call(port, 'GET', '/v1/catalog', undefined, auth());
  assert.equal(cat.body.versions.flow_data, flow);
  assert.equal(cat.body.data.flow_through, dates[4]);
  assert.deepEqual(cat.body.data.broker_window, { first: dates[0], last: dates[4], sessions: 5, complete: true });
  assert.equal((await call(port, 'GET', '/health')).body.versions.flow_data, flow);
  const run = await call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'p', seq: 1 }, definition: RSI }, auth(OWNER_A));
  assert.equal(run.status, 200);
  assert.equal(run.body.versions.flow_data, flow); assert.deepEqual(run.body.data.broker_window, cat.body.data.broker_window);
  const line = refreshes('2026-10-27T13:03:23Z').at(-1)!;
  assert.deepEqual(line.granted, ['price', 'actions'], 'the Phase 1 fields keep their meaning');
  const bytes = names.reduce((n, k) => n + index[k].bytes, 0);
  assert.deepEqual({ ...line.broker_days, store_bytes: 0, rows: 0 }, { window: 5, loaded: 5, carried: 0, cached: 0, granted: 5, missing: 0, bytes, first: dates[0], last: dates[4],
    read: 5, rows: 0, dropped_tickers: 1, dropped_rows: fakeRows(99, dates[4], ['ZZZZ']).length, store_bytes: 0 });
  assert.ok(line.broker_days.store_bytes > 0 && line.broker_days.rows > 0);
  assert.deepEqual(s.desc.broker.days[4].dropped, ['ZZZZ']);
  assert.equal(s.desc.broker.offsets.length, s.desc.tickers.length + 1);
  assert.equal(s.desc.broker.tickers.indexOf('ZZZZ'), -1);
});

test('the budget: the Phase 1 files first, then the broker days newest first while they fit; the rest load on follow-up refreshes started at once, until the window is complete', async () => {
  const u = universe(6, 300), dates = sessions(u, 6);
  const probe = await startFakeTerminal({ key: PROXY, publication: pubOf('x', u, brokerOf(dates)) });
  const index = probe.latest().state.xsection;
  await probe.close();
  const phase1 = index.price.bytes + index.actions.bytes, day = (k: number) => index[`broker-${dates[k]}`].bytes;
  // room for the two newest days and half the third
  const cap = phase1 + day(5) + day(4) + Math.floor(day(3) / 2);
  const { app, port } = await start(pubOf('2026-10-27T14:00:00Z', u, brokerOf(dates)), { SCREENER_MAX_REFRESH_BYTES: String(cap) });
  await app.refresher.tick();
  const first = refreshes('2026-10-27T14:00:00Z')[0];
  assert.deepEqual([first.broker_days.granted, first.broker_days.missing, first.broker_days.first, first.broker_days.last], [2, 4, dates[4], dates[5]]);
  const cat = await call(port, 'GET', '/v1/catalog', undefined, auth());
  assert.deepEqual(cat.body.data.broker_window, { first: dates[4], last: dates[5], sessions: 2, complete: false });
  // no tick and a poll of an hour: the follow-ups start by themselves
  await until(() => app.state().current!.desc.data.broker_window!.complete, 60_000);
  const lines = refreshes('2026-10-27T14:00:00Z');
  assert.ok(lines.length >= 3, `${lines.length} refreshes`);
  for (const l of lines) assert.ok(phase1 + l.broker_days.bytes <= cap, 'every refresh within SCREENER_MAX_REFRESH_BYTES');
  assert.ok(lines.slice(1).every((l, k) => l.broker_days.carried >= lines[k].broker_days.loaded), 'the days loaded before are carried, not downloaded again');
  assert.deepEqual(app.state().current!.desc.broker.dates, dates);
  assert.equal(lines.reduce((n, l) => n + l.broker_days.granted, 0), 6, 'each day downloaded once');
});

test('the follow-up stops when no missing day fits: the window stays incomplete, the poll does not rebuild, the next publication with the same files skips', async () => {
  const u = universe(6, 300), dates = sessions(u, 3);
  // the newest day names one stock, the older ones six: only the newest fits beside the Phase 1 files
  const broker = brokerOf(dates, (d, k) => fakeRows(k + 1, d, k === 2 ? STOCKS.slice(0, 1) : STOCKS));
  const probe = await startFakeTerminal({ key: PROXY, publication: pubOf('x', u, broker) });
  const index = probe.latest().state.xsection;
  await probe.close();
  const cap = index.price.bytes + index.actions.bytes + index[`broker-${dates[2]}`].bytes + 10;
  assert.ok(index[`broker-${dates[1]}`].bytes > index[`broker-${dates[2]}`].bytes + 10 && index[`broker-${dates[0]}`].bytes > index[`broker-${dates[2]}`].bytes + 10);
  const { app, fake } = await start(pubOf('2026-10-27T15:00:00Z', u, broker), { SCREENER_MAX_REFRESH_BYTES: String(cap) });
  await app.refresher.tick();
  await until(() => logs.events('refresh_broker_waiting').some(l => l.published_at === '2026-10-27T15:00:00Z'), 30_000);
  const sid = app.state().current!.sid, calls = xsectionCalls(fake).length;
  assert.deepEqual(app.state().current!.desc.data.broker_window, { first: dates[2], last: dates[2], sessions: 1, complete: false });
  await app.refresher.tick();                                           // a poll of the same publication: nothing
  assert.equal(app.state().current!.sid, sid);
  assert.equal(xsectionCalls(fake).length, calls);
  fake.publish(pubOf('2026-10-27T23:00:00Z', u, broker));
  await app.refresher.tick();
  const skipped = logs.events('refresh_skipped').at(-1)!;
  assert.equal(skipped.published_at, '2026-10-27T23:00:00Z');
  assert.deepEqual([skipped.broker_days.carried, skipped.broker_days.missing], [1, 2]);
  assert.equal(app.state().current!.sid, sid, 'no swap');
  assert.equal(app.state().current!.desc.data.broker_window!.complete, false);
});

test('batches of 16: /xsection is asked for at most 16 names per call (terminal-api MAX_XSECTION_NAMES); of 62 indexed days the newest 60 load', async () => {
  const u = universe(6, 300), dates = sessions(u, 62);
  const { app, fake } = await start(pubOf('2026-10-27T16:00:00Z', u, brokerOf(dates, (d, k) => fakeRows(k + 1, d, STOCKS.slice(0, 2)))));
  await app.refresher.tick();
  const calls = xsectionCalls(fake);
  assert.deepEqual(calls.map(c => c.length), [16, 16, 16, 14], 'price, actions and 60 days');
  assert.ok(!calls.flat().includes(`broker-${dates[0]}`) && !calls.flat().includes(`broker-${dates[1]}`), 'the two oldest are outside the window');
  assert.deepEqual(app.state().current!.desc.broker.dates, dates.slice(2));
  assert.equal(refreshes('2026-10-27T16:00:00Z').at(-1)!.grants, 4);
  assert.deepEqual(app.state().current!.desc.data.broker_window, { first: dates[2], last: dates[61], sessions: 60, complete: true });
});

test('skip-unchanged with broker days; a changed day downloads that day only (the others carried) and changes flow_data, sid and the result cache key; a new day adds itself', async () => {
  const u = universe(6, 300), dates = sessions(u, 5);
  const { app, port, fake } = await start(pubOf('2026-10-27T17:00:00Z', u, brokerOf(dates.slice(0, 4))));
  await app.refresher.tick();
  const run = (seq: number) => call(port, 'POST', '/v1/run', { schema_version: 1, client_order: { page: 'p', seq }, definition: RSI }, auth(OWNER_A));
  const s0 = app.state().current!;
  assert.equal((await run(1)).status, 200);
  assert.equal((await run(2)).status, 200);
  assert.equal(logs.events('run').at(-1)!.cache_hit, true, 'the second run is a cache hit');
  // the same Phase 1 files and the same days on a new publication: skipped
  fake.publish(pubOf('2026-10-27T23:30:00Z', u, brokerOf(dates.slice(0, 4))));
  await app.refresher.tick();
  assert.equal(logs.events('refresh_skipped').at(-1)!.published_at, '2026-10-27T23:30:00Z');
  assert.equal(app.state().current!.sid, s0.sid);
  // a broker round changed one date: that file is replaced, the others carried
  const calls = xsectionCalls(fake).length;
  fake.publish(pubOf('2026-10-28T01:00:00Z', u, brokerOf(dates.slice(0, 4), (d, k) => fakeRows(k === 1 ? 77 : k + 1, d, STOCKS))));
  await app.refresher.tick();
  const changed = refreshes('2026-10-28T01:00:00Z').at(-1)!;
  assert.deepEqual([changed.broker_days.granted, changed.broker_days.carried, changed.broker_days.cached], [1, 3, 0]);
  assert.deepEqual(xsectionCalls(fake).slice(calls), [['price', 'actions', `broker-${dates[1]}`]]);
  const s1 = app.state().current!;
  assert.equal(s1.price_data, s0.price_data, 'the prices are the same');
  assert.notEqual(s1.desc.versions.flow_data, s0.desc.versions.flow_data);
  assert.notEqual(s1.sid, s0.sid, 'another snapshot');
  assert.equal(s1.desc.versions.flow_data, flowDataOf(fake.latest().state.xsection, brokerNames(fake.latest().state.xsection)));
  const after = await run(3);
  assert.equal(after.status, 200);
  assert.equal(logs.events('run').at(-1)!.cache_hit, false, 'the cached answer of the other broker days is not served');
  assert.equal(after.body.versions.flow_data, s1.desc.versions.flow_data);
  // the rows of the replaced date are the new file's
  const want = xsectionBrokerDoc(dates[1], fakeRows(77, dates[1], STOCKS));
  assert.equal(s1.desc.broker.days[1].file_rows, want.check.rows);
  // a new date: that file alone is downloaded
  fake.publish(pubOf('2026-10-28T12:00:00Z', u, brokerOf(dates, (d, k) => fakeRows(k === 1 ? 77 : k + 1, d, STOCKS))));
  await app.refresher.tick();
  const added = refreshes('2026-10-28T12:00:00Z').at(-1)!;
  assert.deepEqual([added.broker_days.granted, added.broker_days.carried], [1, 4]);
  assert.equal((await call(port, 'GET', '/v1/catalog', undefined, auth())).body.data.flow_through, dates[4]);
});

test('carrying: a day from which a ticker without price was dropped is read again when the price file changes (the ticker may have a price now), carried while it is the same', async () => {
  const u = universe(6, 300), dates = sessions(u, 3);
  const broker = brokerOf(dates, (d, k) => k === 0 ? [...fakeRows(1, d, STOCKS), ...fakeRows(5, d, ['ZZZZ'])] : fakeRows(k + 1, d, STOCKS));
  const { app, fake } = await start(pubOf('2026-10-27T18:00:00Z', u, broker));
  await app.refresher.tick();
  assert.deepEqual(app.state().current!.desc.broker.days[0].dropped, ['ZZZZ']);
  // ZZZZ now has prices: the price file changes, so the day that dropped it is read again
  const u2 = universe(6, 300);
  u2.prices.ZZZZ = u2.prices.T000.map((r: unknown[]) => [...r]);
  u2.ref.push(['ZZZZ', 'Z', 'stock', 'Energy', 'Coal']);
  fake.publish(pubOf('2026-10-28T13:03:23Z', u2, broker));
  await app.refresher.tick();
  const line = refreshes('2026-10-28T13:03:23Z').at(-1)!;
  assert.deepEqual([line.broker_days.granted, line.broker_days.carried, line.broker_days.dropped_tickers], [1, 2, 0]);
  const s = app.state().current!;
  assert.deepEqual(s.desc.broker.days[0].dropped, []);
  const j = s.desc.broker.tickers.indexOf('ZZZZ');
  assert.equal(s.desc.broker.offsets[j + 1] - s.desc.broker.offsets[j], fakeRows(5, dates[0], ['ZZZZ']).length, 'ZZZZ\'s rows are loaded now');
});

test('integrity: a broken broker day fails the refresh (REFRESH_FAILED DATA_INTEGRITY naming the file) and keeps the previous snapshot; a day above SCREENER_MAX_FILE_BYTES fails before any grant', async () => {
  const u = universe(6, 300), dates = sessions(u, 3);
  const { app, port, fake } = await start(pubOf('2026-10-27T19:00:00Z', u, brokerOf(dates)));
  await app.refresher.tick();
  const v = app.state().current!.price_data, flow = app.state().current!.desc.versions.flow_data;
  const bad = xsectionBrokerDoc(dates[2], fakeRows(3, dates[2], STOCKS));
  bad.check.bv *= 1.01;
  const u2 = universe(6, 301);
  fake.publish(pubOf('2026-10-28T13:03:23Z', u2, brokerOf(sessions(u2, 3)), { files: { [`broker-${sessions(u2, 3)[2]}`]: { doc: { ...bad, name: `broker-${sessions(u2, 3)[2]}`, date: sessions(u2, 3)[2] } } } }));
  await app.refresher.tick();
  const f = logs.events('REFRESH_FAILED').at(-1)!;
  assert.deepEqual([f.code, f.field, f.keeping_previous], ['DATA_INTEGRITY', `broker-${sessions(u2, 3)[2]}`, true]);
  assert.match(f.message, /has check\.bv .*; its rows add up to/);
  assert.equal(app.state().current!.price_data, v, 'the previous snapshot serves');
  assert.equal(app.state().current!.desc.versions.flow_data, flow);
  assert.equal((await call(port, 'GET', '/v1/catalog', undefined, auth())).body.data.refresh, 'failed_keeping_previous');
  // the per-file cap: the index names a day larger than SCREENER_MAX_FILE_BYTES
  const c = await start(pubOf('2026-10-27T19:00:00Z', u, brokerOf(dates), { files: { [`broker-${dates[0]}`]: { bytes: 5_000_000 } } }), { SCREENER_MAX_FILE_BYTES: '1000000' });
  await c.app.refresher.tick();
  assert.equal(xsectionCalls(c.fake).length, 0, 'no grant');
  const g = logs.events('REFRESH_FAILED').at(-1)!;
  assert.deepEqual([g.details.limit, g.field], ['file_bytes', `broker-${dates[0]}`]);
  assert.equal(c.app.state().current, null);
});

test('the disk cache: a restart reads the broker days it holds without a grant', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'screener-cache-'));
  const env = { SCREENER_CACHE_DIR: dir, SCREENER_CACHE_DIR_BYTES: String(64 * 1024 * 1024) };
  const u = universe(6, 300), pub = pubOf('2026-10-27T20:00:00Z', u, brokerOf(sessions(u, 4)));
  const first = await start(pub, env);
  await first.app.refresher.tick();
  const second = await start(pub, env);
  await second.app.refresher.tick();
  assert.equal(xsectionCalls(second.fake).length, 0, 'nothing granted');
  const line = logs.events('refresh').at(-1)!;
  assert.deepEqual([line.broker_days.cached, line.broker_days.granted, line.broker_days.loaded], [4, 0, 4]);
  assert.equal(second.app.state().current!.desc.versions.flow_data, first.app.state().current!.desc.versions.flow_data);
  fs.rmSync(dir, { recursive: true, force: true });
});
