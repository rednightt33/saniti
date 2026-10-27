/* The loader (src/load.ts loadMarket) against tests/fake-terminal.mjs with presigned URLs that expire (ttl, refused by
   the bucket with S3's 403 once their lifetime has passed) and slow downloads: a ticker's /bundle answer of step 1 is
   used for its download while its URLs can still serve it (terminal.ts usable), otherwise it is asked again right
   before the download; a new answer from a later publish is the run's data (data_version, limits). */
import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { test } from 'node:test';
import { dataVersion } from '../../edge-bff/backtest/src/core/datafile.ts';
import { WorkerError } from '../src/errors.ts';
import { PlannedClient, loadMarket } from '../src/load.ts';
import type { LoadGroup } from '../src/load.ts';
import { EVENT_COLUMNS, encode, eventsDoc, pricePack, startFakeTerminal } from './fake-terminal.mjs';

const KEY = 'load-test-proxy-key-'.padEnd(48, 'x');
const TICKERS = Array.from({ length: 16 }, (_, k) => `S${String(k + 1).padStart(2, '0')}`);
const bar = (d: string, c: number) => [d, c - 1, c + 2, c - 3, c, 1000];
const ev = (d: string, type: string) => EVENT_COLUMNS.map(c => ({ d, role: 'EX_DATE', family: 'CORPORATE_ACTION', type } as Record<string, unknown>)[c] ?? null);
/** A stock's documents: its price pack and its events file (two downloads a ticker). */
const docs = (t: string, rows = [bar('2026-01-02', 100), bar('2026-01-05', 101)]) => ({ pack: pricePack(t, rows), events: eventsDoc(t, [ev('2026-01-05', 'DIVIDEND')]) });
const stock = (d: ReturnType<typeof docs>) => ({ datasets: {
  price: { data_through: '2026-01-05', first_year: 2026, files: [{ pack: 'price', doc: d.pack }] },
  events: { data_through: '2026-10-25 17:04:28+00', files: [{ doc: d.events }] },
} });
const DOCS = new Map(TICKERS.map(t => [t, docs(t)]));
const market = () => Object.fromEntries(TICKERS.map(t => [t, stock(DOCS.get(t)!)]));
const GROUP: LoadGroup = { tickers: TICKERS, datasets: ['price', 'events'], skipUnpublished: true };
const LIMITS = { max_download_bytes: 1e9, max_broker_rows: 1e9 };
/** data_version of these documents (datafile.ts dataVersion over ticker, dataset and sha256) */
const versionOf = (all: Map<string, ReturnType<typeof docs>>) =>
  dataVersion([...all].flatMap(([ticker, d]) => [{ ticker, dataset: 'price', sha256: encode(d.pack).sha256 }, { ticker, dataset: 'events', sha256: encode(d.events).sha256 }]));
const bytesOf = (all: Map<string, ReturnType<typeof docs>>) => [...all.values()].reduce((n, d) => n + encode(d.pack).body.length + encode(d.events).body.length, 0);

type Fake = Awaited<ReturnType<typeof startFakeTerminal>>;
const client = (fake: Fake, timeoutMs: number) => new PlannedClient({ url: fake.url, proxyKey: KEY, cacheBytes: 50_000_000, concurrency: 2, retries: 0, retryBaseMs: 0,
  timeoutMs, fileOrigin: fake.url, maxFileBytes: 10_000_000 });
/** terminal-api /bundle answers per ticker, from the fake's request log */
const bundles = (fake: Fake) => {
  const n = new Map<string, number>();
  for (const r of fake.requests) if (r.path === '/api/terminal/v1/bundle') { const t = JSON.parse(r.body).ticker; n.set(t, (n.get(t) ?? 0) + 1) }
  return n;
};

test('a step-1 manifest whose URLs can still serve the download is used for it: one /bundle per ticker', async () => {
  const fake = await startFakeTerminal({ key: KEY, tickers: market() });           // ttl 120 s, terminal-api's answer in dev
  try {
    const l = await loadMarket(client(fake, 5000), [GROUP], LIMITS, 'portfolio.tickers', 2);
    assert.deepEqual([...l.tickers.keys()].sort(), TICKERS);
    assert.equal(l.data_version, await versionOf(DOCS));
    assert.deepEqual([...bundles(fake)].sort(), TICKERS.map(t => [t, 1]), 'no ticker asked twice');
    assert.equal(fake.expired, 0);
  } finally { await fake.close() }
});

test('a load whose later tickers would be downloaded after their URLs expire succeeds: those are asked again right before the download', async () => {
  // URLs live 1 s and a file takes 100 ms: two at a time, the 16 tickers (32 files) take about 1.6 s after their
  // step-1 manifests, which all come in the first few tens of milliseconds. With a 500 ms HTTP timeout a manifest
  // is usable while it is younger than 500 ms: the first tickers use theirs, the later ones are asked again.
  const fake = await startFakeTerminal({ key: KEY, tickers: market(), ttl: 1, fileDelayMs: 100 });
  try {
    const l = await loadMarket(client(fake, 500), [GROUP], LIMITS, 'portfolio.tickers', 2);
    assert.deepEqual([...l.tickers.keys()].sort(), TICKERS);
    assert.deepEqual(l.excluded, []);
    assert.equal(l.data_version, await versionOf(DOCS));
    assert.equal(fake.expired, 0, 'no URL reached the bucket after its lifetime');
    const n = bundles(fake);
    assert.ok(TICKERS.every(t => (n.get(t) ?? 0) >= 1 && (n.get(t) ?? 0) <= 2), JSON.stringify([...n]));
    assert.equal(n.get(TICKERS[0]), 1, 'the first ticker downloads from its step-1 manifest');
    assert.equal(n.get(TICKERS[TICKERS.length - 1]), 2, 'the last ticker is asked again just in time');
  } finally { await fake.close() }
});

test('a manifest asked again from a later publish is the run\'s data: data_version of the files read, the limits held before their download', async () => {
  // a 1 s lifetime under a 1 s HTTP timeout: no manifest of step 1 is usable, every ticker is asked again before its
  // download; S05 is published again between the two (hooks.planned runs after step 1, before any download)
  const later = docs('S05', [bar('2026-01-02', 200), bar('2026-01-05', 201), bar('2026-01-06', 202)]);
  const republish = (fake: Fake) => () => { fake.publish('S05', stock(later)) };
  const fake = await startFakeTerminal({ key: KEY, tickers: market(), ttl: 1 });
  try {
    const l = await loadMarket(client(fake, 1000), [GROUP], LIMITS, 'portfolio.tickers', 2, { planned: republish(fake) });
    const read = new Map(DOCS).set('S05', later);
    assert.equal(l.data_version, await versionOf(read));
    assert.notEqual(l.data_version, await versionOf(DOCS));
    assert.equal(l.bytes, bytesOf(read));
    assert.deepEqual(l.tickers.get('S05')!.prices!.dates, ['2026-01-02', '2026-01-05', '2026-01-06']);
    assert.deepEqual([...bundles(fake)].sort(), TICKERS.map(t => [t, 2]));
  } finally { await fake.close() }
  // the step-1 manifests are exactly at the limit; S05's new files pass it: refused before they are downloaded
  const tight = await startFakeTerminal({ key: KEY, tickers: market(), ttl: 1 });
  try {
    const limit = bytesOf(DOCS), r0 = tight.requests.length;
    const e = await loadMarket(client(tight, 1000), [GROUP], { ...LIMITS, max_download_bytes: limit }, 'portfolio.tickers', 2, { planned: republish(tight) }).catch(x => x);
    assert.ok(e instanceof WorkerError && e.code === 'LIMIT_EXCEEDED' && e.status === 422 && e.field === 'portfolio.tickers', String(e));
    assert.deepEqual(e.details, { limit: 'max_download_bytes', allowed: limit, needed: limit - encode(DOCS.get('S05')!.pack).body.length + encode(later.pack).body.length });
    assert.ok(!tight.requests.slice(r0).some(r => r.path.startsWith('/bucket/') && r.path.includes('/S05/')), 'S05 downloaded nothing');
  } finally { await tight.close() }
});

test('a ticker whose every file is cached is loaded from its step-1 answer however old: one /bundle per ticker (review COST-1)', async () => {
  // a 1 s lifetime under a 1 s HTTP timeout: no step-1 answer is ever usable; the first load fills the cache
  const fake = await startFakeTerminal({ key: KEY, tickers: market(), ttl: 1 });
  try {
    const c = client(fake, 1000);
    await loadMarket(c, [GROUP], LIMITS, 'portfolio.tickers', 2);
    assert.deepEqual([...bundles(fake)].sort(), TICKERS.map(t => [t, 2]), 'cold: each ticker asked again before its downloads');
    const r0 = fake.requests.length;
    const l = await loadMarket(c, [GROUP], LIMITS, 'portfolio.tickers', 2);
    const second = fake.requests.slice(r0);
    assert.equal(second.filter(r => r.path === '/api/terminal/v1/bundle').length, TICKERS.length, 'warm: one answer per ticker, its URLs unused');
    assert.equal(second.filter(r => r.path.startsWith('/bucket/')).length, 0);
    assert.ok(l.files.every(f => f.cached));
    assert.equal(l.data_version, await versionOf(DOCS));
  } finally { await fake.close() }
});

test('a cached copy that fails its check is downloaded with the step-1 URL; once that has expired, from a new answer', async () => {
  // disk cache only (no memory cache); S03's price pack is damaged on disk after the first load; the second load
  // waits past the URLs' 1 s lifetime after step 1 (hooks.planned), so S03's download with its step-1 URL is refused
  const dir = await mkdtemp(path.join(os.tmpdir(), 'bt-load-test-'));
  const fake = await startFakeTerminal({ key: KEY, tickers: market(), ttl: 1 });
  try {
    const c = new PlannedClient({ url: fake.url, proxyKey: KEY, cacheBytes: 0, cacheDir: dir, cacheDirBytes: 50_000_000, concurrency: 2, retries: 0, retryBaseMs: 0,
      timeoutMs: 1000, fileOrigin: fake.url, maxFileBytes: 10_000_000 });
    await loadMarket(c, [GROUP], LIMITS, 'portfolio.tickers', 2);
    const sha = encode(DOCS.get('S03')!.pack).sha256;
    await writeFile(path.join(dir, `${sha}.json.gz`), new Uint8Array(encode(DOCS.get('S03')!.pack).body.length));
    const r0 = fake.requests.length, expired0 = fake.expired;
    const l = await loadMarket(c, [GROUP], LIMITS, 'portfolio.tickers', 2, { planned: () => new Promise(ok => setTimeout(ok, 1100)) });
    const n = new Map<string, number>();
    for (const r of fake.requests.slice(r0)) if (r.path === '/api/terminal/v1/bundle') { const t = JSON.parse(r.body).ticker; n.set(t, (n.get(t) ?? 0) + 1) }
    assert.deepEqual([...n].sort(), TICKERS.map(t => [t, t === 'S03' ? 2 : 1]));
    assert.equal(fake.expired - expired0, 1, 'S03\'s step-1 URL was refused once');
    assert.deepEqual(l.files.filter(f => !f.cached).map(f => [f.ticker, f.dataset]), [['S03', 'price']]);
    assert.equal(l.data_version, await versionOf(DOCS));
  } finally { await fake.close(); await rm(dir, { recursive: true, force: true }) }
});
