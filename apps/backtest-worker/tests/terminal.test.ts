/* The worker's terminal-api client (src/terminal.ts) against tests/fake-terminal.mjs (terminal-api /bundle and
   /reference with main.py's answers and errors, and a presigned bucket), with files in the publisher's format:
   what a load returns, the explicit data errors, the retry rule, the sha256 cache, bounded concurrency, the key kept out
   of every message and log line, and no Postgres anywhere in the worker. */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { after, before, test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { DataError, brokerGaps, brokerRows, corporateActions, dataVersion, priceSeries } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { Columnar } from '../../edge-bff/backtest/src/core/datafile.ts';
import { flowData } from '../../edge-bff/backtest/src/core/flow.ts';
import http from 'node:http';
import type net from 'node:net';
import { describeConfig, loadConfig } from '../src/config.ts';
import { TerminalClient, checkDataThrough, checkPriceRange, fileOriginOf, optionsFromEnv } from '../src/terminal.ts';
import type { TerminalOptions } from '../src/terminal.ts';
import { EVENT_COLUMNS, brokerArchive, brokerDoc, brokersRef, encode, eventsDoc, priceDoc, pricePack, pyJson, startFakeTerminal, tickersRef } from './fake-terminal.mjs';

const KEY = 'test-proxy-key-'.padEnd(48, 'x');
const json = (doc: object) => JSON.parse(JSON.stringify(doc)) as Columnar;
const code = (c: string, field?: string) => (e: unknown) => {
  assert.ok(e instanceof DataError, String(e)); assert.equal((e as DataError).code, c, (e as Error).message);
  if (field !== undefined) assert.equal((e as DataError).field, field);
  return true;
};

/* ---- the published market of the tests --------------------------------------------------------------------------- */
const bar = (d: string, c: number, v: number | null = 1000) => [d, c - 1, c + 2, c - 3, c, v];
const P2025 = [bar('2025-12-29', 100), bar('2025-12-30', 101)], P2026 = [bar('2026-01-02', 102), bar('2026-01-05', 103), bar('2026-01-06', 104)];
const b = (d: string, br: string, i: string, m: string, bv: number, sv: number, gap = false) => [d, br, i, m, bv, sv, bv / 1e4, sv / 1e4, gap];
const ARCHIVE = [b('2024-12-30', 'AK', 'Foreign', 'Regular', 5e8, 1e8)];
const B2025 = [b('2025-12-29', 'AK', 'Foreign', 'Regular', 9e8, 1e8), b('2025-12-29', 'YP', 'Domestic', 'Tunai', 0, 3e8, true), b('2025-12-30', 'YP', 'Foreign', 'Nego', 2e8, 0)];
const B2026 = [b('2026-01-02', 'AK', 'Domestic', 'Regular', 4e8, 0), b('2026-01-05', 'YU', 'Foreign', 'Regular', 7e8, 2e8)];
const ev = (d: string, type: string) => EVENT_COLUMNS.map(c => ({ d, role: 'EX_DATE', family: 'CORPORATE_ACTION', type } as Record<string, unknown>)[c] ?? null);
const DOCS = {
  pack: pricePack('BBCA', [...P2025, ...P2026]), p2025: priceDoc('BBCA', 2025, P2025), p2026: priceDoc('BBCA', 2026, P2026),
  archive: brokerArchive('BBCA', ARCHIVE, [2016, 2024]), b2024: brokerDoc('BBCA', 2024, ARCHIVE), b2025: brokerDoc('BBCA', 2025, B2025), b2026: brokerDoc('BBCA', 2026, B2026),
  events: eventsDoc('BBCA', [ev('2025-06-02', 'DIVIDEND'), ev('2025-12-30', 'STOCK_SPLIT')]),
  ihsg: pricePack('IHSG', [bar('2025-12-29', 7000, null), bar('2025-12-30', 7010, null), bar('2026-01-02', 7020, null)]),
};
const price = (t: string, rows: unknown[][], extra = {}) => ({ data_through: '2026-01-06', first_year: 2025, files: [{ year: 2026, doc: priceDoc(t, 2026, rows), ...extra }] });
const MARKET = {
  BBCA: { generated_at: '2026-10-26T12:00:00+00:00', datasets: {
    price: { data_through: '2026-01-06', first_year: 2025, files: [{ pack: 'price', doc: DOCS.pack }, { year: 2025, doc: DOCS.p2025 }, { year: 2026, doc: DOCS.p2026 }] },
    broker: { data_through: '2026-01-05', first_year: 2016, files: [{ pack: 'broker-archive', doc: DOCS.archive }, { year: 2024, doc: DOCS.b2024 }, { year: 2025, doc: DOCS.b2025 }, { year: 2026, doc: DOCS.b2026 }] },
    events: { data_through: '2026-10-25 17:04:28+00', files: [{ doc: DOCS.events }] },
  } },
  IHSG: { datasets: { price: { data_through: '2026-01-02', first_year: 2025, files: [{ pack: 'price', doc: DOCS.ihsg }] } } },
  NOBR: { datasets: { price: price('NOBR', P2026) } },                                        // a stock without broker files
  GONE: { datasets: { price: { data_through: '2026-01-06', first_year: 2025, files: [{ year: 2025, doc: priceDoc('GONE', 2025, P2025), missing: true }, { year: 2026, doc: priceDoc('GONE', 2026, P2026) }] } } },
  DUPE: { datasets: { price: { data_through: '2026-01-06', first_year: 2025, files: [{ year: 2025, doc: priceDoc('DUPE', 2025, [...P2025, P2026[0]]) }, { year: 2026, doc: priceDoc('DUPE', 2026, P2026) }] } } },
  UNSO: { datasets: { price: price('UNSO', [P2026[1], P2026[0], P2026[2]]) } },
  BADS: { datasets: { price: price('BADS', P2026, { sha256: '0'.repeat(64) }) } },
  BADB: { datasets: { price: price('BADB', P2026, { bytes: 10 }) } },
  DENY: { datasets: { price: price('DENY', P2026, { status: 403 }) } },
  ...Object.fromEntries(['T1', 'T2', 'T3', 'T4', 'T5', 'T6'].map(t => [t, { datasets: { price: price(t, P2026) } }])),
};
const REFS = { tickers: tickersRef([['BBCA', 'Bank Central Asia', 'stock', 'Finance'], ['IHSG', 'Composite', 'index', null]]), brokers: brokersRef([['AK', 'UBS', 'Foreign'], ['YP', 'Mirae', 'Domestic']]) };

let fake: Awaited<ReturnType<typeof startFakeTerminal>>;
const logs: unknown[] = [];
const options = (extra: Partial<TerminalOptions> = {}): TerminalOptions => ({ url: fake.url, proxyKey: KEY, cacheBytes: 50_000_000, concurrency: 4, retries: 2, retryBaseMs: 1, timeoutMs: 5000,
  fileOrigin: fake.url, maxFileBytes: 10_000_000, log: (event, fields) => { logs.push({ event, ...fields }) }, ...extra });
const bucketGets = (from = 0) => fake.requests.slice(from).filter(r => r.path.startsWith('/bucket/'));
before(async () => { fake = await startFakeTerminal({ key: KEY, tickers: MARKET, refs: REFS }) });
after(() => fake.close());

test('a stock and the index load as the Terminal reads them: packs, verified files, bars, flow, corporate actions, data_version', async () => {
  const c = new TerminalClient(options()), seen = fake.requests.length;
  const r = await c.loadTickers(['BBCA', 'IHSG', 'BBCA'], ['price', 'broker', 'events'].slice(0, 3) as any).catch(e => e);
  assert.ok(r instanceof DataError && r.code === 'DATA_MISSING' && r.field === 'IHSG.broker', 'the index has no broker files: asking for them is DATA_MISSING');
  const s = await c.loadTickers(['BBCA'], ['price', 'broker', 'events']), i = await c.loadTickers(['IHSG'], ['price']);
  const t = s.tickers.BBCA;
  assert.deepEqual(t.prices, priceSeries('BBCA', [json(DOCS.pack)]));
  const docs = [DOCS.archive, DOCS.b2025, DOCS.b2026].map(json);                     // packs: the archive, then the years after it
  assert.deepEqual(t.broker_rows, brokerRows(docs));
  assert.deepEqual(t.broker_gaps, brokerGaps(docs));
  assert.deepEqual(t.flow, flowData(brokerRows(docs), t.prices!.dates, brokerGaps(docs)));
  assert.deepEqual(t.corporate_actions, [{ date: '2025-12-30', type: 'STOCK_SPLIT' }]);
  assert.deepEqual(t.data_through, { price: '2026-01-06', broker: '2026-01-05', events: '2026-10-25 17:04:28+00' });
  assert.equal(t.generated_at, '2026-10-26T12:00:00+00:00');
  const sha = (d: object) => encode(d).sha256;
  assert.deepEqual(t.files.map(f => [f.dataset, f.pack ?? f.year ?? 'all', f.sha256]).sort(), [
    ['broker', 'broker-archive', sha(DOCS.archive)], ['broker', 2025, sha(DOCS.b2025)], ['broker', 2026, sha(DOCS.b2026)], ['events', 'all', sha(DOCS.events)], ['price', 'price', sha(DOCS.pack)],
  ].sort() as any);
  assert.equal(s.data_version, await dataVersion(s.files));
  assert.deepEqual(i.tickers.IHSG.prices!.bars.V, [null, null, null]);
  assert.equal(i.tickers.IHSG.broker_rows, null);
  // the key goes to terminal-api only; the presigned URLs get no credential of any kind
  const mine = fake.requests.slice(seen);
  for (const q of mine.filter(q => q.path.startsWith('/api/'))) assert.equal(q.headers['x-terminal-proxy-key'], KEY);
  for (const q of bucketGets(seen)) for (const h of ['x-terminal-proxy-key', 'authorization', 'cookie']) assert.equal(q.headers[h], undefined, `${q.path} ${h}`);
  const light = await new TerminalClient(options()).loadTickers(['BBCA'], ['price', 'broker'], { keepBrokerRows: false });
  assert.equal(light.tickers.BBCA.broker_rows, null);
  assert.deepEqual(light.tickers.BBCA.flow, t.flow);
});

test('a missing ticker, dataset or file is DATA_MISSING; a period without bars too (the caller check)', async () => {
  const c = new TerminalClient(options()), n = fake.requests.length;
  await assert.rejects(c.loadTicker('NOPE', ['price']), code('DATA_MISSING', 'NOPE'));
  await assert.rejects(c.loadTicker('bbca', ['price']), code('DATA_MISSING', 'ticker'));
  assert.equal(fake.requests.length, n + 1, 'an invalid ticker is refused before any request');
  await assert.rejects(c.loadTicker('NOBR', ['price', 'broker']), code('DATA_MISSING', 'NOBR.broker'));
  assert.deepEqual((await c.loadTicker('NOBR', ['price', 'events'])).corporate_actions, []);   // no events file: no corporate action
  await assert.rejects(c.loadTicker('GONE', ['price']), code('DATA_MISSING', 'GONE.price'));    // a year the manifest names, not in the bucket
  await assert.rejects(c.loadTickers(['T1', 'NOPE', 'T2'], ['price']), code('DATA_MISSING', 'NOPE'));
  const t = await c.loadTicker('BBCA', ['price']);
  assert.throws(() => checkPriceRange(t, '2020-01-01', '2020-12-31'), code('DATA_MISSING', 'BBCA'));
  checkPriceRange(t, '2026-01-06', '2026-02-01');
});

test('a stale manifest (data_through before the period end) is an explicit error of the caller check', async () => {
  const t = await new TerminalClient(options()).loadTicker('BBCA', ['price', 'broker']);
  checkDataThrough(t, 'price', '2026-01-06');
  assert.throws(() => checkDataThrough(t, 'broker', '2026-01-06'), code('DATA_UNAVAILABLE', 'BBCA.broker'));
  assert.throws(() => checkDataThrough(t, 'events', '2026-01-06'), code('DATA_UNAVAILABLE', 'BBCA.events'));   // not read: no date
});

test('files that are not what the manifest says, duplicate or unsorted dates are DATA_INTEGRITY; a null volume stays null', async () => {
  const c = new TerminalClient(options());
  await assert.rejects(c.loadTicker('BADS', ['price']), code('DATA_INTEGRITY', 'BADS.price'));   // sha256 mismatch
  await assert.rejects(c.loadTicker('BADB', ['price']), code('DATA_INTEGRITY', 'BADB.price'));   // size mismatch
  await assert.rejects(c.loadTicker('DUPE', ['price']), code('DATA_INTEGRITY', 'DUPE'));        // 2026-01-02 in both years
  await assert.rejects(c.loadTicker('UNSO', ['price']), code('DATA_INTEGRITY', 'UNSO'));
  assert.deepEqual((await c.loadTicker('IHSG', ['price'])).prices!.bars.V, [null, null, null]);
});

test('network errors and 5xx are retried with backoff; a 4xx never is', async () => {
  const c = new TerminalClient(options()), count = (p: string, from: number) => fake.requests.slice(from).filter(q => q.path.startsWith(p)).length;
  let n = fake.requests.length;
  fake.fault('/api/terminal/v1/bundle', [503, 'reset']);
  assert.ok((await c.loadTicker('T1', ['price'])).prices);
  assert.equal(count('/api/terminal/v1/bundle', n), 3); assert.equal(c.stats.retries, 2);
  n = fake.requests.length;
  fake.fault('/api/terminal/v1/bundle', [502, 502, 502]);
  await assert.rejects(c.loadTicker('T1', ['price']), code('DATA_UNAVAILABLE', 'T1'));
  assert.equal(count('/api/terminal/v1/bundle', n), 3, 'retries: 2 -> three tries');
  n = fake.requests.length;
  fake.fault('/api/terminal/v1/bundle', [429]);
  const quota = await c.loadTicker('T1', ['price']).catch(e => e);
  assert.ok(quota instanceof DataError && quota.code === 'DATA_UNAVAILABLE' && quota.details?.status === 429 && quota.details?.code === 'quota_exceeded');
  assert.equal(count('/api/terminal/v1/bundle', n), 1);
  n = fake.requests.length;
  await assert.rejects(c.loadTicker('DENY', ['price']), code('DATA_UNAVAILABLE', 'DENY.price'));   // the bucket refuses the URL
  assert.equal(count('/bucket/', n), 1);
  n = fake.requests.length;
  const wrong = new TerminalClient(options({ proxyKey: 'w'.repeat(40) }));
  const refused = await wrong.loadTicker('T1', ['price']).catch(e => e);
  assert.ok(refused instanceof DataError && refused.code === 'DATA_UNAVAILABLE' && refused.details?.code === 'proxy_key_rejected');
  assert.equal(count('/api/', n), 1);
  n = fake.requests.length;
  fake.fault((q: any) => q.path.startsWith('/bucket/') && q.path.includes('/T2/'), ['reset', 500]);
  assert.ok((await c.loadTicker('T2', ['price'])).prices);
  assert.equal(count('/bucket/', n), 3);
});

test('files are cached by sha256: a second load downloads nothing, a new client finds them on disk, a damaged copy is downloaded again', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'terminal-cache-'));
  try {
    const c = new TerminalClient(options({ cacheDir: dir, cacheDirBytes: 10_000_000 }));
    let n = fake.requests.length;
    const first = await c.loadTicker('BBCA', ['price', 'broker', 'events']);
    assert.equal(bucketGets(n).length, 5);
    n = fake.requests.length;
    const again = await c.loadTicker('BBCA', ['price', 'broker', 'events']);
    assert.equal(bucketGets(n).length, 0);
    assert.equal(c.stats.cache_hits, 5);
    assert.ok(again.files.every(f => f.cached));
    assert.deepEqual({ ...again, files: [] }, { ...first, files: [] });
    assert.deepEqual(fs.readdirSync(dir).sort(), first.files.map(f => `${f.sha256}.json.gz`).sort());
    n = fake.requests.length;
    const fresh = new TerminalClient(options({ cacheDir: dir, cacheDirBytes: 10_000_000 }));
    assert.deepEqual((await fresh.loadTicker('BBCA', ['price'])).prices, first.prices);
    assert.equal(bucketGets(n).length, 0, 'read from the disk cache');
    const pack = first.files.find(f => f.pack === 'price')!;
    fs.writeFileSync(path.join(dir, `${pack.sha256}.json.gz`), 'damaged');
    n = fake.requests.length;
    assert.deepEqual((await new TerminalClient(options({ cacheDir: dir, cacheDirBytes: 10_000_000 })).loadTicker('BBCA', ['price'])).prices, first.prices);
    assert.equal(bucketGets(n).length, 1, 'the damaged copy is replaced');
    n = fake.requests.length;
    const none = new TerminalClient(options({ cacheBytes: 0 }));
    await none.loadTicker('IHSG', ['price']); await none.loadTicker('IHSG', ['price']);
    assert.equal(bucketGets(n).length, 2, 'cacheBytes 0: no memory cache');
  } finally { fs.rmSync(dir, { recursive: true, force: true }) }
});

test('at most `concurrency` requests are in flight', async () => {
  const slow = await startFakeTerminal({ key: KEY, tickers: MARKET, delayMs: 15 });
  try {
    const c = new TerminalClient({ ...options(), url: slow.url, fileOrigin: slow.url, concurrency: 2 });
    const r = await c.loadTickers(['T1', 'T2', 'T3', 'T4', 'T5', 'T6'], ['price']);
    assert.deepEqual(Object.keys(r.tickers), ['T1', 'T2', 'T3', 'T4', 'T5', 'T6']);
    assert.ok(slow.inflight.max <= 2 && slow.inflight.max >= 1, `max in flight ${slow.inflight.max}`);
  } finally { await slow.close() }
});

test('reference lists: tickers with type and sector, brokers with name and type', async () => {
  const c = new TerminalClient(options());
  assert.deepEqual(await c.reference('tickers'), [{ ticker: 'BBCA', name: 'Bank Central Asia', type: 'stock', sector: 'Finance' }, { ticker: 'IHSG', name: 'Composite', type: 'index', sector: null }]);
  assert.deepEqual(await c.reference('brokers'), [{ code: 'AK', name: 'UBS', type: 'Foreign' }, { code: 'YP', name: 'Mirae', type: 'Domestic' }]);
});

test('the proxy key and the presigned URLs never appear in an error message, its details or a log line', async () => {
  const c = new TerminalClient(options());
  const errors: unknown[] = [];
  fake.fault('/api/terminal/v1/bundle', [503, 503, 503]);
  for (const t of ['T3', 'NOPE', 'BADS', 'DENY', 'GONE']) errors.push(await c.loadTicker(t, ['price']).catch(e => e));
  errors.push(await new TerminalClient(options({ proxyKey: KEY + 'y' })).loadTicker('T1', ['price']).catch(e => e));
  const text = JSON.stringify([logs, errors.map(e => [String((e as Error).message), (e as DataError).details, (e as DataError).field])]);
  assert.ok(errors.every(e => e instanceof DataError));
  assert.ok(!text.includes(KEY) && !text.includes('X-Amz-Signature') && !text.includes('/bucket/'));
  assert.throws(() => optionsFromEnv({ TERMINAL_URL: 'http://terminal-api.railway.internal:8080', TERMINAL_PROXY_KEY: 'short' }), (e: Error) => !e.message.includes('short') && /TERMINAL_PROXY_KEY/.test(e.message));
});

test('optionsFromEnv reads every setting and assumes none', () => {
  const env = { TERMINAL_URL: 'http://terminal-api.railway.internal:8080/', TERMINAL_PROXY_KEY: KEY, BACKTEST_CACHE_BYTES: '200000000', BACKTEST_DOWNLOAD_CONCURRENCY: '6',
    BACKTEST_DOWNLOAD_RETRIES: '3', BACKTEST_RETRY_BASE_MS: '250', BACKTEST_HTTP_TIMEOUT_MS: '30000', BACKTEST_FILE_ORIGIN: 'https://*.t3.storageapi.dev',
    BACKTEST_MAX_FILE_BYTES: '50000000' };
  assert.deepEqual(optionsFromEnv(env), { url: 'http://terminal-api.railway.internal:8080', proxyKey: KEY, cacheBytes: 200000000, cacheDir: undefined, cacheDirBytes: undefined,
    concurrency: 6, retries: 3, retryBaseMs: 250, timeoutMs: 30000, fileOrigin: 'https://*.t3.storageapi.dev', maxFileBytes: 50000000 });
  assert.equal(optionsFromEnv({ ...env, BACKTEST_CACHE_DIR: '/data/cache', BACKTEST_CACHE_DIR_BYTES: '1000' }).cacheDirBytes, 1000);
  for (const k of Object.keys(env)) {
    const { [k]: _, ...rest } = env as Record<string, string>;
    assert.throws(() => optionsFromEnv(rest), new RegExp(k));
  }
  assert.throws(() => optionsFromEnv({ ...env, BACKTEST_CACHE_DIR: '/data/cache' }), /BACKTEST_CACHE_DIR_BYTES/);
  assert.throws(() => optionsFromEnv({ ...env, BACKTEST_DOWNLOAD_CONCURRENCY: '0' }), /BACKTEST_DOWNLOAD_CONCURRENCY/);
  assert.throws(() => optionsFromEnv({ ...env, TERMINAL_URL: 'http://terminal-api/api/terminal/v1' }), /TERMINAL_URL/);
});

/* ---- what the client accepts (review findings 2026-10-26: SEC-2, SEC-7, SEC-8) ---------------------------------------- */
const ENV_ALL = { TERMINAL_URL: 'http://terminal-api.railway.internal:8080', TERMINAL_PROXY_KEY: KEY, BACKTEST_CACHE_BYTES: '0', BACKTEST_DOWNLOAD_CONCURRENCY: '1',
  BACKTEST_DOWNLOAD_RETRIES: '0', BACKTEST_RETRY_BASE_MS: '0', BACKTEST_HTTP_TIMEOUT_MS: '1000', BACKTEST_FILE_ORIGIN: 'https://*.t3.storageapi.dev', BACKTEST_MAX_FILE_BYTES: '1000' };

test('TERMINAL_URL with a user name or password is refused without its value; the start log names the origin only (SEC-7)', () => {
  for (const url of ['http://user:s3cretpass@terminal-api.railway.internal:8080', 'http://s3cretpass@terminal-api.railway.internal:8080', 'http://:s3cretpass@terminal-api.railway.internal:8080'])
    assert.throws(() => optionsFromEnv({ ...ENV_ALL, TERMINAL_URL: url }), (e: Error) => /TERMINAL_URL must not contain a user name or password/.test(e.message) && !e.message.includes('s3cretpass'), url);
  const cfg = loadConfig({ ...ENV_ALL, BACKTEST_WORKER_KEY: 'w'.repeat(32), BACKTEST_MAX_DOWNLOAD_BYTES: '1', BACKTEST_MAX_BROKER_ROWS: '1', BACKTEST_TIMEOUT_SECONDS: '1',
    BACKTEST_MAX_CONDITIONS: '1', BACKTEST_MAX_RESULT_BYTES: '1' });
  assert.equal((describeConfig(cfg).terminal as { origin: string }).origin, 'http://terminal-api.railway.internal:8080');
  // whatever a URL holds, the log has its origin: no user name, password, path or query
  const text = JSON.stringify(describeConfig({ ...cfg, terminal: { ...cfg.terminal, url: 'http://user:s3cretpass@terminal-api.railway.internal:8080' } }));
  assert.ok(!text.includes('s3cretpass') && !text.includes('user@') && !text.includes(KEY), text);
});

test('fileOriginOf: scheme, host and port as a CSP host-source; every other URL is off the bucket origin (SEC-8)', () => {
  const on = fileOriginOf('https://*.t3.storageapi.dev')!;
  for (const u of ['https://abc.t3.storageapi.dev/k.json.gz?X-Amz-Signature=1', 'https://a.b.t3.storageapi.dev/k', 'https://abc.t3.storageapi.dev:443/k', 'https://ABC.t3.storageapi.dev/k'])
    assert.ok(on(u), u);
  for (const u of ['http://abc.t3.storageapi.dev/k', 'https://t3.storageapi.dev/k', 'https://abc.t3.storageapi.dev.evil.example/k', 'https://evilt3.storageapi.dev/k',
    'https://abc.t3.storageapi.dev:8443/k', 'https://user:pw@abc.t3.storageapi.dev/k', 'https://abc.t3.storageapi.dev./k', 'https://127.0.0.1/k',
    'http://169.254.169.254/latest/meta-data/', 'file:///etc/passwd', 'not a url'])
    assert.ok(!on(u), u);
  const local = fileOriginOf('http://127.0.0.1:9000')!;
  assert.ok(local('http://127.0.0.1:9000/bucket/v1/x'));
  for (const u of ['http://127.0.0.1:9001/x', 'http://127.0.0.1/x', 'http://localhost:9000/x', 'https://127.0.0.1:9000/x']) assert.ok(!local(u), u);
  for (const p of ['', 'https://', '*.t3.storageapi.dev', 'https://*.t3.storageapi.dev/', 'https://*.T3.storageapi.dev', 'https://*', 'ftp://x.example', 'https://a.*.example',
    'https://x.example:0', 'https://x.example:70000', 'https://user@x.example'])
    assert.equal(fileOriginOf(p), null, p);
  assert.throws(() => optionsFromEnv({ ...ENV_ALL, BACKTEST_FILE_ORIGIN: 'https://*.t3.storageapi.dev/path' }), /BACKTEST_FILE_ORIGIN/);
  assert.throws(() => new TerminalClient(options({ fileOrigin: 'anything' })), /fileOrigin/);
});

test('a file or reference URL off the bucket origin is DATA_INTEGRITY and never requested (SEC-8)', async () => {
  const hits: string[] = [];
  const internal = http.createServer((req, res) => { hits.push(req.url ?? ''); res.end('{}') });
  await new Promise<void>(ok => internal.listen(0, '127.0.0.1', ok));
  const inside = `http://127.0.0.1:${(internal.address() as net.AddressInfo).port}`;
  const evil = await startFakeTerminal({ key: KEY, tickers: { EVIL: { datasets: { price: price('EVIL', P2026, { url: `${inside}/internal-admin?x=1` }) } } }, refs: REFS });
  try {
    // a /bundle answer naming another host or port of the private network
    const c = new TerminalClient(options({ url: evil.url, fileOrigin: evil.url }));
    await assert.rejects(c.loadTicker('EVIL', ['price']), (e: unknown) => code('DATA_INTEGRITY', 'EVIL')(e) && /not on the bucket origin/.test((e as Error).message));
    assert.deepEqual(hits, [], 'the internal address is never contacted');
    // every file and reference URL of a terminal-api whose bucket is not the configured one
    const other = new TerminalClient(options({ fileOrigin: 'https://*.t3.storageapi.dev' })), n = fake.requests.length;
    await assert.rejects(other.loadTicker('T1', ['price']), code('DATA_INTEGRITY', 'T1'));
    await assert.rejects(other.reference('tickers'), code('DATA_INTEGRITY', 'tickers'));
    assert.deepEqual(fake.requests.slice(n).map(q => q.path), ['/api/terminal/v1/bundle', '/api/terminal/v1/reference/tickers'], 'no bucket request');
  } finally { await evil.close(); internal.closeAllConnections(); await new Promise(ok => internal.close(ok)) }
});

test('a body is read as a stream and dropped at its cap: a data file at its manifest bytes, an answer at maxFileBytes (SEC-2)', async () => {
  const CHUNK = 65536, CHUNKS = 200;
  let pulled = 0, cancelled = 0;
  const long = (status: number) => new Response(new ReadableStream<Uint8Array>({
    pull(c) { if (++pulled > CHUNKS) c.close(); else c.enqueue(new Uint8Array(CHUNK)) }, cancel() { cancelled++ },
  }), { status });
  const via = (pick: (url: string) => number | null): typeof fetch => (async (url: string | URL | Request, init?: RequestInit) => {
    const status = pick(String(url));
    return status === null ? fetch(url, init) : long(status);
  }) as typeof fetch;
  // a data file far longer than its manifest says: DATA_INTEGRITY once it passes the manifest bytes
  const file = new TerminalClient(options({ fetch: via(u => u.includes('/bucket/') && u.includes('/T4/') ? 200 : null) }));
  await assert.rejects(file.loadTicker('T4', ['price']), (e: unknown) => code('DATA_INTEGRITY', 'T4.price')(e) && /more than the \d+ bytes its manifest says/.test((e as Error).message));
  assert.ok(pulled <= 3 && cancelled === 1, `pulled ${pulled} of ${CHUNKS} chunks, cancelled ${cancelled}`);
  // an error answer of the bucket, and a terminal-api answer, longer than maxFileBytes: DATA_UNAVAILABLE, not retried
  for (const [pick, what] of [[(u: string) => u.includes('/bucket/') && u.includes('/T5/') ? 503 : null, 'T5.price'], [(u: string) => u.includes('/bundle') ? 200 : null, 'T5']] as const) {
    pulled = 0; cancelled = 0;
    const c = new TerminalClient(options({ maxFileBytes: CHUNK * 2, fetch: via(pick) }));
    await assert.rejects(c.loadTicker('T5', ['price']), (e: unknown) => code('DATA_UNAVAILABLE', what)(e) && /more than 131072 bytes/.test((e as Error).message));
    assert.ok(pulled <= 4 && cancelled === 1 && c.stats.retries === 0, `${what}: pulled ${pulled}, cancelled ${cancelled}, retries ${c.stats.retries}`);
  }
  // a declared length over the cap is refused before the body is read
  pulled = 0;
  const declared = new TerminalClient(options({ maxFileBytes: 10, fetch: (async () => new Response('x'.repeat(11), { status: 200, headers: { 'content-length': '11' } })) as typeof fetch }));
  await assert.rejects(declared.reference('tickers'), code('DATA_UNAVAILABLE', 'tickers'));
});

test('a reference file or a data file inflates to at most maxFileBytes, a reference download is at most maxFileBytes (SEC-2)', async () => {
  // a reference list and a price file that inflate about 20-fold, as a small file that inflates to a large one would
  const day = (k: number) => new Date(Date.UTC(2000, 0, 3) + k * 86400000).toISOString().slice(0, 10);
  const big = tickersRef(Array.from({ length: 3000 }, (_, k) => [`T${k}`, `Ticker number ${k}`, 'stock', 'Sector A']));
  const rows = Array.from({ length: 3000 }, (_, k) => bar(day(k), 100));
  const doc = priceDoc('BIGP', 2000, rows);
  const refGz = encode(big).body.length, refJson = Buffer.byteLength(pyJson(big)), fileJson = Buffer.byteLength(pyJson(doc));
  assert.ok(refJson > 5 * refGz, `${refGz} -> ${refJson}`);
  const bigFake = await startFakeTerminal({ key: KEY, tickers: { BIGP: { datasets: { price: { data_through: day(2999), first_year: 2000, files: [{ year: 2000, doc }] } } } }, refs: { tickers: big } });
  try {
    const client = (maxFileBytes: number) => new TerminalClient(options({ url: bigFake.url, fileOrigin: bigFake.url, maxFileBytes, cacheBytes: 0 }));
    const err = (details: Record<string, number>) => (e: unknown) => code('DATA_INTEGRITY')(e) && (assert.deepEqual((e as DataError).details, details), true);
    // the download over the cap: refused while it arrives
    await assert.rejects(client(refGz - 1).reference('tickers'), err({ max_file_bytes: refGz - 1 }));
    // the download within the cap, the inflated document over it: inflating stops there
    await assert.rejects(client(refGz).reference('tickers'), err({ max_inflated_bytes: refGz }));
    assert.equal((await client(refJson).reference('tickers')).length, 3000);
    // a data file (its download is capped by its manifest bytes): the inflated document at most maxFileBytes
    await assert.rejects(client(fileJson - 1).loadTicker('BIGP', ['price']), (e: unknown) => err({ max_inflated_bytes: fileJson - 1 })(e) && (e as DataError).field === 'BIGP.price');
    assert.equal((await client(fileJson).loadTicker('BIGP', ['price'])).prices!.dates.length, 3000);
  } finally { await bigFake.close() }
});

/* CONTRACT.md section 1: the worker has no Postgres credentials and reads market data only through terminal-api */
test('nothing under apps/backtest-worker imports a Postgres client or reads a database URL', () => {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..'), self = fileURLToPath(import.meta.url);
  const clients = ['pg', 'pg-promise', 'pg-pool', 'postgres', '@neondatabase/serverless', '@vercel/postgres', 'slonik', 'knex', 'kysely', 'sequelize', 'typeorm', '@prisma/client', 'drizzle-orm', 'mikro-orm', 'pg-native'];
  const importRe = /(?:\bimport\s[^'"]*?from\s*|\bimport\s*\(\s*|\brequire\s*\(\s*|\bimport\s+)['"]([^'"]+)['"]/g;
  const dbUrl = /\b[A-Z0-9_]*DATABASE_URL\b|\bPG(?:HOST|USER|PASSWORD|DATABASE|PORT)\b|postgres(?:ql)?:\/\//;
  const files: string[] = [];
  const walk = (d: string) => { for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    if (e.name === 'node_modules' || e.name.startsWith('.')) continue;
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p); else if (/\.(m?[jt]s|cjs|json)$/.test(e.name) && p !== self) files.push(p);
  } };
  walk(root);
  assert.ok(files.some(f => f.endsWith(path.join('src', 'terminal.ts'))));
  for (const f of files) {
    const text = fs.readFileSync(f, 'utf8');
    for (const m of text.matchAll(importRe)) assert.ok(!clients.includes(m[1].replace(/^node:/, '')) && !/^(pg|postgres)(\/|$)/.test(m[1]), `${path.relative(root, f)} imports ${m[1]}`);
    assert.ok(!dbUrl.test(text), `${path.relative(root, f)} names a database URL`);
    if (f.endsWith('package.json')) {
      const pkg = JSON.parse(text), deps = { ...pkg.dependencies, ...pkg.devDependencies, ...pkg.optionalDependencies, ...pkg.peerDependencies };
      for (const d of Object.keys(deps)) assert.ok(!clients.includes(d), `package.json depends on ${d}`);
    }
  }
});
