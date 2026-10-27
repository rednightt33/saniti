/* The browser file cache shared with the Terminal (src/api/cache.ts) and the live BacktestApi's use of it (live.ts
   download), on fake-indexeddb, with fetch answered here: the session, /api/terminal/v1/bundle and the presigned file
   of one ticker's price data. One IDBFactory is one browser; a new liveApi on it is the next page load. Then a download
   that fails on the way (live.ts fetchFile): asked again, or answered at once, by what failed. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { IDBFactory } from 'fake-indexeddb';
import TERMINAL_WORKER from '../../terminal/src/data/worker.ts?raw';
import { sha256Bytes } from '../src/core/datafile.ts';
import { CACHE_DB, CACHE_LIMIT, CACHE_STORE, CACHE_VERSION, fileCache } from '../src/api/cache.ts';
import { FILE_RETRIES, liveApi } from '../src/api/live.ts';
import { ApiFailure } from '../src/api/types.ts';

const gz = async (doc: unknown) => new Uint8Array(await new Response(new Blob([JSON.stringify(doc)]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
const price = (closes: number[]) => gz({ schema_version:1, dataset:'price', ticker:'MAPI', columns:['d', 'o', 'h', 'l', 'c', 'v'],
  d:closes.map((_, k) => `2026-10-${String(k + 1).padStart(2, '0')}`), o:closes, h:closes, l:closes, c:closes, v:closes.map(() => 1000) });
const FILE = await price([800, 810, 805, 820]), FILE_SHA = await sha256Bytes(FILE), FILE_URL = 'https://bucket.example/MAPI/price.json.gz';

/* fetch as edge-bff and the storage host answer it; `served`: the bytes the presigned URL gives (the manifest names
   FILE); `downloads`: how often the file was fetched */
function network(served: Uint8Array = FILE) {
  const seen = { downloads:0 };
  vi.stubGlobal('fetch', async (url: string) => {
    if (url === '/api/v1/auth/session') return Response.json({ csrf_token:'t' });
    if (url === '/api/terminal/v1/bundle') return Response.json({ datasets:{ price:{ files:[{ url:FILE_URL, sha256:FILE_SHA, bytes:FILE.byteLength }] } } });
    if (url === FILE_URL) { seen.downloads++; return new Response(served.slice()) }
    return new Response('', { status:404 });
  });
  return seen;
}
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() });

/* the record under a sha256, read as the Terminal reads it (null: none, or no database) */
async function record(factory: IDBFactory, key: string): Promise<any> {
  const db = await new Promise<IDBDatabase>((ok, no) => { const r = factory.open(CACHE_DB); r.onsuccess = () => ok(r.result); r.onerror = () => no(r.error) });
  try {
    if (!db.objectStoreNames.contains(CACHE_STORE)) return null;
    return await new Promise((ok, no) => { const r = db.transaction(CACHE_STORE).objectStore(CACHE_STORE).get(key); r.onsuccess = () => ok(r.result ?? null); r.onerror = () => no(r.error) });
  } finally { db.close() }
}
/* the cache stores after the download returned (not awaited by the page): wait until `test` holds */
async function until(test: () => Promise<boolean>) {
  for (let k = 0; k < 100; k++) { if (await test()) return; await new Promise(ok => setTimeout(ok, 10)) }
  throw new Error('timed out');
}

describe('the database is the Terminal\'s (apps/edge-bff/terminal/src/data/worker.ts)', () => {
  const terminal: string = TERMINAL_WORKER;
  it('has its name, version, store, key, index and limit', () => {
    const m = terminal.match(/const CACHE_DB = '([^']+)', CACHE_STORE = '([^']+)', CACHE_LIMIT = ([\d_]+);/)!;
    expect([CACHE_DB, CACHE_STORE, CACHE_LIMIT]).toEqual([m[1], m[2], +m[3].replace(/_/g, '')]);
    expect(terminal).toContain(`indexedDB.open(CACHE_DB, ${CACHE_VERSION})`);
    expect(terminal).toContain(`createObjectStore(CACHE_STORE, { keyPath:'sha' }).createIndex('used', 'used')`);
  });
  it('stores the Terminal\'s record: {sha, bytes (an ArrayBuffer), size, used}', async () => {
    const factory = new IDBFactory(), bytes = new Uint8Array([1, 2, 3]);
    await fileCache(factory).put('ab', bytes);
    const r = await record(factory, 'ab');
    expect(Object.keys(r).sort()).toEqual(['bytes', 'sha', 'size', 'used']);
    expect(r.bytes).toBeInstanceOf(ArrayBuffer); expect([...new Uint8Array(r.bytes)]).toEqual([1, 2, 3]); expect(r.size).toBe(3);
  });
});

describe('the live page with the cache (live.ts)', () => {
  it('reads the file from the cache on the second page load', async () => {
    const factory = new IDBFactory(), seen = network();
    const first = await liveApi({ cache:fileCache(factory) }).bars('MAPI');
    expect(seen.downloads).toBe(1);
    await until(async () => !!await record(factory, FILE_SHA));
    const second = await liveApi({ cache:fileCache(factory) }).bars('MAPI');
    expect(seen.downloads).toBe(1);
    expect(Array.from(second.c)).toEqual(Array.from(first.c));
  });
  it('does not use a cached entry whose bytes do not match the manifest sha256, and replaces it', async () => {
    const factory = new IDBFactory(), seen = network();
    await fileCache(factory).put(FILE_SHA, await price([1, 2, 3, 4]));             // other bytes under the file's sha256
    const bars = await liveApi({ cache:fileCache(factory) }).bars('MAPI');
    expect(seen.downloads).toBe(1);
    expect(Array.from(bars.c)).toEqual([800, 810, 805, 820]);
    await until(async () => await sha256Bytes(new Uint8Array((await record(factory, FILE_SHA)).bytes)) === FILE_SHA);
  });
  it('stores only bytes that pass inflateVerified', async () => {
    const factory = new IDBFactory();
    network(await price([1, 2, 3, 4]));                                              // the storage host serves other bytes
    const err = await liveApi({ cache:fileCache(factory) }).bars('MAPI').catch(e => e);
    expect(err).toBeInstanceOf(ApiFailure); expect(err.code).toBe('DATA_INTEGRITY');
    await new Promise(ok => setTimeout(ok, 50));
    expect(await record(factory, FILE_SHA)).toBeNull();
  });
  it('has no cache, and still loads, when the browser holds a newer version of the database (VersionError)', async () => {
    const factory = new IDBFactory(), seen = network();
    await new Promise<void>(ok => { const r = factory.open(CACHE_DB, CACHE_VERSION + 1); r.onsuccess = () => { r.result.close(); ok() } });
    const cache = fileCache(factory);
    await liveApi({ cache }).bars('MAPI');
    await liveApi({ cache:fileCache(factory) }).bars('MAPI');
    expect(seen.downloads).toBe(2);
    expect(await cache.get(FILE_SHA)).toBeNull();
  });
  it('has no cache, and still loads, without IndexedDB', async () => {
    const seen = network(), cache = fileCache(undefined);
    await liveApi({ cache }).bars('MAPI');
    expect(seen.downloads).toBe(1);
    expect(await cache.get(FILE_SHA)).toBeNull();
    await expect(cache.put('ab', new Uint8Array([1]))).resolves.toBeUndefined();
  });
});

describe('fileCache (cache.ts)', () => {
  it('closes its connection when another page asks for a newer version, and is off from then on', async () => {
    const factory = new IDBFactory(), cache = fileCache(factory);
    await cache.put('ab', new Uint8Array([1]));
    expect(await cache.get('ab')).not.toBeNull();
    const upgraded = await new Promise<string>(ok => { const r = factory.open(CACHE_DB, CACHE_VERSION + 1); r.onblocked = () => ok('blocked'); r.onsuccess = () => { r.result.close(); ok('opened') } });
    expect(upgraded).toBe('opened');                                          // not blocked by this page's connection
    expect(await cache.get('ab')).toBeNull();
    await expect(cache.put('cd', new Uint8Array([2]))).resolves.toBeUndefined();
  });
  it('drops the least recently used files above the limit, a read counting as a use', async () => {
    let now = 1000; vi.spyOn(Date, 'now').mockImplementation(() => now++);
    const factory = new IDBFactory(), cache = fileCache(factory, 10), four = (v: number) => new Uint8Array(4).fill(v);
    await cache.put('a', four(1)); await cache.put('b', four(2));
    await cache.get('a');                                                     // b is now the least recently used
    await cache.put('c', four(3));                                            // 12 bytes > 10: b goes
    expect(await record(factory, 'b')).toBeNull();
    expect(await record(factory, 'a')).not.toBeNull(); expect(await record(factory, 'c')).not.toBeNull();
  });
});

describe('a download that fails on the way (live.ts fetchFile)', () => {
  const none = { get:async () => null, put:async () => {} };
  /* the presigned file answered in turn by `answers` (the last one again once they run out); the session and /bundle as
     network() */
  function storage(...answers: (() => Response)[]) {
    const seen = { downloads:0 };
    vi.stubGlobal('fetch', async (url: string) => {
      if (url === '/api/v1/auth/session') return Response.json({ csrf_token:'t' });
      if (url === '/api/terminal/v1/bundle') return Response.json({ datasets:{ price:{ files:[{ url:FILE_URL, sha256:FILE_SHA, bytes:FILE.byteLength }] } } });
      if (url === FILE_URL) return answers[Math.min(seen.downloads++, answers.length - 1)]();
      return new Response('', { status:404 });
    });
    return seen;
  }
  // a body that stops after ten bytes, as a connection closed on the way (Chromium: ERR_CONTENT_LENGTH_MISMATCH)
  const cut = () => new Response(new ReadableStream({ start(c) { c.enqueue(FILE.slice(0, 10)); c.error(new TypeError('network error')) } }));
  const whole = () => new Response(FILE.slice());

  it('asks a file again when its body is cut off on the way or the storage host answers 5xx, and uses the whole one', async () => {
    let seen = storage(cut, whole);
    expect((await liveApi({ cache:none }).bars('MAPI')).dates).toHaveLength(4);
    expect(seen.downloads).toBe(2);
    seen = storage(() => new Response('', { status:503 }), whole);
    expect((await liveApi({ cache:none }).bars('MAPI')).dates).toHaveLength(4);
    expect(seen.downloads).toBe(2);
  });
  it('a file cut off at every try is DATA_UNAVAILABLE after FILE_RETRIES more tries, never DATA_INTEGRITY', async () => {
    const seen = storage(cut);
    const err = await liveApi({ cache:none }).bars('MAPI').catch(e => e);
    expect(err).toBeInstanceOf(ApiFailure);
    expect([err.code, err.status, err.message]).toEqual(['DATA_UNAVAILABLE', 0, 'A data file could not be downloaded.']);
    expect(seen.downloads).toBe(FILE_RETRIES + 1);
  });
  it('a refusal (403: the link expired) is answered at once, and a whole file unlike its manifest entry is DATA_INTEGRITY, asked once', async () => {
    let seen = storage(() => new Response('', { status:403 }), whole);
    let err = await liveApi({ cache:none }).bars('MAPI').catch(e => e);
    expect([err.code, err.status]).toEqual(['DATA_UNAVAILABLE', 403]);
    expect(seen.downloads).toBe(1);
    const other = await price([1, 2, 3, 4]);
    seen = storage(() => new Response(other.slice()));
    err = await liveApi({ cache:none }).bars('MAPI').catch(e => e);
    expect(err.code).toBe('DATA_INTEGRITY');
    expect(seen.downloads).toBe(1);
  });
});
