/* EXEC-MU-RUNTIME T7 (accuracy): a rack page draws and stores a published file only when its bytes have the size and
   sha256 terminal-api announced (rack.ts readVerified, the Backtest core's inflateVerified rule); on a failed check the
   Terminal asks one new /bundle (or /reference) and then shows the plain message (live.ts). fetch is answered here: the
   session, /api/terminal/v1/reference, /bundle and the presigned files; vitest runs without Worker, so live.ts reads the
   files on the page with the same functions the worker runs (worker.ts download). */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { DownloadError, FILE_RETRIES, INTEGRITY_MESSAGE, IntegrityError, isIntegrity, mismatch, readVerified, sha256Hex, type FileCache, type FileRef } from '../../src/data/rack';
import { download } from '../../src/data/worker';
import { liveData, TerminalError } from '../../src/data/live';

const gz = async (doc: unknown) => new Uint8Array(await new Response(new Blob([JSON.stringify(doc)]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
const days = (n: number) => Array.from({ length:n }, (_, k) => `2026-10-${String(k + 1).padStart(2, '0')}`);
const priceDoc = (closes: number[]) => ({ schema_version:1, dataset:'price-pack', ticker:'MAPI', columns:['d', 'o', 'h', 'l', 'c', 'v'],
  d:days(closes.length), o:closes, h:closes, l:closes, c:closes, v:closes.map(() => 1000) });
const brokerDoc = (buy: number) => ({ schema_version:1, dataset:'broker', ticker:'MAPI', columns:['d', 'b', 'i', 'm', 'bv', 'sv', 'bl', 'sl'],
  d:days(2), b:['AK', 'AK'], i:['Foreign', 'Foreign'], m:['RG', 'RG'], bv:[buy, buy], sv:[0, 0], bl:[1, 1], sl:[0, 0], gap:[] });
const announce = async (bytes: Uint8Array, url: string, name = 'price/price'): Promise<FileRef> => ({ url, sha:await sha256Hex(bytes), bytes:bytes.byteLength, name });
const flip = (b: Uint8Array, at = b.length - 5) => { const c = b.slice(); c[at] ^= 0xff; return c };   // same size, other sha256

/* a FileCache in memory (one browser's IndexedDB `terminal-files`): what was stored under which sha256 */
function memCache() {
  const m = new Map<string, Uint8Array>(), puts: string[] = [];
  const cache: FileCache = { get:async sha => m.get(sha) ?? null, put:async (sha, bytes) => { puts.push(sha); m.set(sha, bytes.slice()) } };
  return { cache, m, puts };
}
/* the storage host: each URL answers the bytes it is given (fetch counted per URL) */
function storage(files: Record<string, Uint8Array | (() => Response)>) {
  const hits: Record<string, number> = {};
  vi.stubGlobal('fetch', async (url: string) => {
    hits[url] = (hits[url] || 0) + 1;
    const f = files[url];
    if (!f) return new Response('', { status:404 });
    return typeof f === 'function' ? f() : new Response(f.slice());
  });
  return hits;
}
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() });

describe('rack.ts readVerified: one check for every rack page reader', () => {
  it('a correct file is read, stored under its sha256, and read from the cache next time', async () => {
    const file = await gz(priceDoc([1, 2, 3])), ref = await announce(file, 'https://bucket.test/a');
    const hits = storage({ 'https://bucket.test/a':file }), { cache, m } = memCache();
    const first = await readVerified(ref, cache);
    expect([...first.bytes]).toEqual([...file]); expect(first.cached).toBe(false);
    expect([...m.get(ref.sha!)!]).toEqual([...file]);
    const second = await readVerified(ref, cache);
    expect(second.cached).toBe(true); expect(hits['https://bucket.test/a']).toBe(1);
  });
  it('a body of another size is refused (DATA_INTEGRITY, the plain message), never stored', async () => {
    const file = await gz(priceDoc([1, 2, 3])), ref = await announce(file, 'https://bucket.test/a');
    for (const body of [file.slice(0, -1), new Uint8Array([...file, 0])]) {
      storage({ 'https://bucket.test/a':body }); const { cache, puts } = memCache();
      const err = await readVerified(ref, cache).catch(e => e);
      expect(err).toBeInstanceOf(IntegrityError);
      expect([err.code, err.message, isIntegrity(err)]).toEqual(['DATA_INTEGRITY', INTEGRITY_MESSAGE, true]);
      expect(err.detail).toBe(`price/price: ${body.byteLength} bytes, ${file.byteLength} announced`);
      expect(puts).toEqual([]);
    }
  });
  it('a body of the announced size with another sha256 is refused, never stored', async () => {
    const file = await gz(priceDoc([1, 2, 3])), ref = await announce(file, 'https://bucket.test/a');
    storage({ 'https://bucket.test/a':flip(file) }); const { cache, puts } = memCache();
    const err = await readVerified(ref, cache).catch(e => e);
    expect(err.code).toBe('DATA_INTEGRITY'); expect(err.detail).toMatch(/sha256 differs/);
    expect(puts).toEqual([]);
  });
  it('a cached file whose bytes changed is not used: the file is downloaded, checked and stored again', async () => {
    const file = await gz(priceDoc([1, 2, 3])), ref = await announce(file, 'https://bucket.test/a');
    const hits = storage({ 'https://bucket.test/a':file }), { cache, m } = memCache();
    for (const damaged of [flip(file), file.slice(0, 20), await gz(priceDoc([9, 9, 9]))]) {
      m.set(ref.sha!, damaged);
      const got = await readVerified(ref, cache);
      expect(got.cached).toBe(false); expect([...got.bytes]).toEqual([...file]);
      expect([...m.get(ref.sha!)!]).toEqual([...file]);                       // the damaged copy is replaced
    }
    expect(hits['https://bucket.test/a']).toBe(3);
  });
  it('a damaged cached copy and a damaged download: refused, and the damaged bytes are never stored', async () => {
    const file = await gz(priceDoc([1, 2, 3])), ref = await announce(file, 'https://bucket.test/a');
    storage({ 'https://bucket.test/a':flip(file, 12) }); const { cache, m, puts } = memCache();
    m.set(ref.sha!, flip(file));
    expect((await readVerified(ref, cache).catch(e => e)).code).toBe('DATA_INTEGRITY');
    expect(puts).toEqual([]);
  });
  it('an announcement without a valid sha256 and size is refused before any download', async () => {
    const file = await gz(priceDoc([1])), good = await announce(file, 'https://bucket.test/a');
    const hits = storage({ 'https://bucket.test/a':file });
    for (const ref of [{ url:good.url, bytes:good.bytes }, { url:good.url, sha:good.sha }, { ...good, sha:'abc' }, { ...good, bytes:-1 }, { ...good, bytes:1.5 }]) {
      const err = await readVerified(ref, memCache().cache).catch(e => e);
      expect(err.code).toBe('DATA_INTEGRITY'); expect(err.detail).toMatch(/announced no valid sha256 and size/);
    }
    expect(hits['https://bucket.test/a']).toBeUndefined();
  });
  it('an upper-case sha256 is the same file (the cache key is lower case, as the Backtest page\'s)', async () => {
    const file = await gz(priceDoc([1])), ref = await announce(file, 'https://bucket.test/a');
    storage({ 'https://bucket.test/a':file }); const { cache, puts } = memCache();
    await readVerified({ ...ref, sha:ref.sha!.toUpperCase() }, cache);
    expect(puts).toEqual([ref.sha]);
  });
  it('a bare URL (a file no index describes) is read as it comes and never stored', async () => {
    storage({ 'https://bucket.test/ref':new Uint8Array([1, 2, 3]) }); const { cache, puts } = memCache();
    expect([...(await readVerified('https://bucket.test/ref', cache)).bytes]).toEqual([1, 2, 3]);
    expect(puts).toEqual([]);
  });
  it('a refused or failed download stays a DownloadError (no failed check), asked again only as M251 says', async () => {
    const file = await gz(priceDoc([1])), ref = await announce(file, 'https://bucket.test/a');
    let hits = storage({ 'https://bucket.test/a':() => new Response('', { status:403 }) });
    let err = await readVerified(ref, memCache().cache).catch(e => e);
    expect(err).toBeInstanceOf(DownloadError); expect(err.status).toBe(403); expect(isIntegrity(err)).toBe(false);
    expect(hits['https://bucket.test/a']).toBe(1);
    hits = storage({ 'https://bucket.test/a':() => new Response('', { status:503 }) });
    err = await readVerified(ref, memCache().cache).catch(e => e);
    expect(err.status).toBe(503); expect(hits['https://bucket.test/a']).toBe(FILE_RETRIES + 1);
  }, 10_000);
  it('mismatch names what differs, and null for the file itself', async () => {
    const file = await gz(priceDoc([1])), ref = await announce(file, 'u');
    expect(await mismatch(file, ref)).toBeNull();
    expect(await mismatch(file.slice(1), ref)).toBe(`${file.byteLength - 1} bytes, ${file.byteLength} announced`);
    expect(await mismatch(flip(file), ref)).toMatch(/sha256 differs/);
  });
});

describe('worker.ts download: the Terminal draws only checked bytes', () => {
  it('decodes a correct gzip file and refuses one whose bytes differ', async () => {
    const file = await gz(priceDoc([800, 810])), ref = await announce(file, 'https://bucket.test/p');
    storage({ 'https://bucket.test/p':file });
    expect((await download(ref)).c).toEqual([800, 810]);
    storage({ 'https://bucket.test/p':await gz(priceDoc([1, 2])) });           // other bytes: the old code drew these
    expect((await download(ref).catch(e => e)).code).toBe('DATA_INTEGRITY');
  });
});

/* ---- live.ts: one new /bundle, then the message ---------------------------------------------------------------- */
const TICKERS = { columns:['ticker', 'name', 'type', 'sector'], ticker:['MAPI', 'IHSG'], name:['Mitra Adiperkasa', 'Composite'], type:['stock', 'index'], sector:['Consumer', null] };
const BROKERS = { columns:['code', 'name', 'type'], code:['AK'], name:['UBS'], type:['Foreign'] };
/* EDGE and terminal-api as the page sees them: `bundles[k]` answers the k-th /bundle of a ticker (the last one again
   when they run out) as {dataset: [file]}; `refs` the /reference answers (with or without sha256 and bytes) */
async function edge(opts: { bundles: Record<string, Record<string, Uint8Array | { body: Uint8Array; announced: Uint8Array }>>[]; refs?: Record<string, { body: Uint8Array; announced?: Uint8Array | null }[]> }) {
  const files: Record<string, Uint8Array> = {}, seen = { bundle:0, bundleOf:{} as Record<string, number>, reference:{} as Record<string, number> };
  const tickers = await gz(TICKERS), brokers = await gz(BROKERS), logos = await gz({ columns:['ticker', 'sha256'], ticker:[], sha256:[] });
  const refs = opts.refs || {};
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    if (url === '/api/v1/auth/session') return Response.json({ csrf_token:'t' });
    const ref = url.match(/^\/api\/terminal\/v1\/reference\/(\w+)$/);
    if (ref) {
      const name = ref[1], k = seen.reference[name] = (seen.reference[name] || 0) + 1;
      const list = refs[name] || [{ body:{ tickers, brokers, logos }[name]!, announced:null }];
      const a = list[Math.min(k, list.length) - 1], u = `https://bucket.test/ref/${name}/${k}`;
      files[u] = a.body;
      return Response.json(a.announced ? { url:u, sha256:await sha256Hex(a.announced), bytes:a.announced.byteLength, rows:2 } : { url:u, sha256:null, bytes:null, rows:null });
    }
    if (url === '/api/terminal/v1/bundle') {
      const body = JSON.parse(String(init!.body));
      seen.bundle++; const k = seen.bundleOf[body.ticker] = (seen.bundleOf[body.ticker] || 0) + 1;
      const plan = opts.bundles[Math.min(k, opts.bundles.length) - 1][body.ticker] || {};
      const datasets: Record<string, unknown> = {};
      for (const d of body.datasets) {
        const f = plan[d];
        if (!f) { datasets[d] = { files:[], data_through:null }; continue }
        const { body:served, announced } = f instanceof Uint8Array ? { body:f, announced:f } : f;
        const u = `https://bucket.test/${body.ticker}/${d}/${k}`; files[u] = served;
        datasets[d] = { data_through:'2026-10-03', files:[{ url:u, sha256:await sha256Hex(announced), bytes:announced.byteLength, rows:3, pack:d === 'price' ? 'price' : undefined, year:d === 'broker' ? 2026 : undefined }] };
      }
      return Response.json({ ticker:body.ticker, datasets });
    }
    if (files[url]) return new Response(files[url].slice());
    return new Response('', { status:404 });
  });
  return seen;
}

describe('live.ts: a failed check asks one new /bundle, then shows the plain message', () => {
  it('correct files draw (one /bundle)', async () => {
    const seen = await edge({ bundles:[{ MAPI:{ price:await gz(priceDoc([800, 810, 820])), broker:await gz(brokerDoc(5)) } }] });
    const M = await liveData('MAPI');
    expect(M.ohlc.map(b => b.close)).toEqual([800, 810, 820]);
    expect((await M.later!.broker).combos.map(c => [c.broker, c.investor, Array.from(c.net)])).toEqual([['AK', 'Foreign', [5, 5, 0]]]);
    expect(seen.bundleOf.MAPI).toBe(1);
  });
  it('a price file of another size on the first answer: the second answer\'s file is drawn, never the first one\'s bytes', async () => {
    const good = await gz(priceDoc([800, 810, 820])), stale = await gz(priceDoc([1, 2, 3, 4]));
    const seen = await edge({ bundles:[{ MAPI:{ price:{ body:stale, announced:good } } }, { MAPI:{ price:good } }] });
    const M = await liveData('MAPI');
    expect(M.ohlc.map(b => b.close)).toEqual([800, 810, 820]);
    expect(seen.bundleOf.MAPI).toBe(2);
  });
  it('a broker file with another sha256: the chart keeps its price, the flow comes from the new answer', async () => {
    const price = await gz(priceDoc([800, 810, 820])), broker = await gz(brokerDoc(5));
    const seen = await edge({ bundles:[{ MAPI:{ price, broker:{ body:flip(broker), announced:broker } } }, { MAPI:{ price, broker } }] });
    const M = await liveData('MAPI');
    expect(M.ohlc.map(b => b.close)).toEqual([800, 810, 820]);
    expect(Array.from((await M.later!.broker).combos[0].net)).toEqual([5, 5, 0]);
    expect(Array.from((await M.later!.brokerAll).combos[0].net)).toEqual([5, 5, 0]);
    expect(seen.bundleOf.MAPI).toBe(2);
  });
  it('the same failure on the new answer: TerminalError DATA_INTEGRITY with the plain message, after exactly one new /bundle', async () => {
    const good = await gz(priceDoc([800, 810, 820]));
    const seen = await edge({ bundles:[{ MAPI:{ price:{ body:flip(good), announced:good } } }] });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const err = await liveData('MAPI').catch(e => e);
    expect(err).toBeInstanceOf(TerminalError);
    expect([err.code, err.message]).toEqual(['DATA_INTEGRITY', INTEGRITY_MESSAGE]);
    expect(seen.bundleOf.MAPI).toBe(2);
    expect(warn.mock.calls.map(c => String(c[0]))).toEqual(expect.arrayContaining([expect.stringMatching(/price\/price: the sha256 differs/)]));
    expect(warn.mock.calls.some(c => /https?:/.test(String(c[0])))).toBe(false);   // never a presigned URL
  });
  it('a broker file that fails twice: the chart is drawn, the flow fails with the message (no third /bundle)', async () => {
    const price = await gz(priceDoc([800, 810, 820])), broker = await gz(brokerDoc(5));
    const seen = await edge({ bundles:[{ MAPI:{ price, broker:{ body:broker.slice(0, -2), announced:broker } } }] });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const M = await liveData('MAPI');
    expect(M.ohlc.length).toBe(3);
    const err = await M.later!.broker.catch(e => e);
    expect([err.code, err.message]).toEqual(['DATA_INTEGRITY', INTEGRITY_MESSAGE]);
    expect((await M.later!.brokerAll.catch(e => e)).code).toBe('DATA_INTEGRITY');
    expect(seen.bundleOf.MAPI).toBe(2);
  });
  it('another ticker read later (IHSG for Statistics) has its own one new /bundle', async () => {
    const good = await gz(priceDoc([7000, 7010, 7020]));
    const seen = await edge({ bundles:[{ MAPI:{ price:await gz(priceDoc([800, 810, 820])) }, IHSG:{ price:{ body:flip(good), announced:good } } }, { IHSG:{ price:good } }] });
    const M = await liveData('MAPI');
    expect((await M.loadIhsg!()).map(p => p.value)).toEqual([7000, 7010, 7020]);
    expect([seen.bundleOf.MAPI, seen.bundleOf.IHSG]).toEqual([1, 2]);
  });
  it('a file the storage host refuses (403) is no failed check: no new /bundle', async () => {
    const seen = await edge({ bundles:[{ MAPI:{ price:await gz(priceDoc([800])) } }] });
    const fetch0 = globalThis.fetch;
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => url.startsWith('https://bucket.test/MAPI/') ? new Response('', { status:403 }) : fetch0(url, init));
    const err = await liveData('MAPI').catch(e => e);
    expect(err).toBeInstanceOf(DownloadError); expect(err.status).toBe(403);
    expect(seen.bundleOf.MAPI).toBe(1);
  });
  it('a reference file announced with sha256 and size (T5) is checked: one new /reference, then the message', async () => {
    const tickers = await gz(TICKERS), price = await gz(priceDoc([800, 810, 820]));
    let seen = await edge({ bundles:[{ MAPI:{ price } }], refs:{ tickers:[{ body:flip(tickers), announced:tickers }, { body:tickers, announced:tickers }] } });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    expect((await liveData('MAPI')).instruments.map(i => i[0])).toEqual(['MAPI', 'IHSG']);
    expect(seen.reference.tickers).toBe(2);
    seen = await edge({ bundles:[{ MAPI:{ price } }], refs:{ tickers:[{ body:tickers.slice(1), announced:tickers }] } });
    const err = await liveData('MAPI').catch(e => e);
    expect([err.code, err.message]).toEqual(['DATA_INTEGRITY', INTEGRITY_MESSAGE]);
    expect(seen.reference.tickers).toBe(2);
  });
  /* review of T7 (2026-10-29): the new answer may come from a later publication whose price has other sessions; the
     chart keeps the first answer's price, so the new answer's broker data must be put on those sessions */
  const priceOn = (d: string[], closes: number[]) => ({ ...priceDoc(closes), d });
  const brokerOn = (d: string[], buy: number[]) => ({ ...brokerDoc(0), d, b:d.map(() => 'AK'), i:d.map(() => 'Foreign'), m:d.map(() => 'RG'),
    bv:buy, sv:d.map(() => 0), bl:d.map(() => 1), sl:d.map(() => 0) });
  const flowOf = async (M: Awaited<ReturnType<typeof liveData>>) => ({
    recent:Array.from((await M.later!.broker).combos[0].net), all:Array.from((await M.later!.brokerAll).combos[0].net) });
  it('a retried broker answer from a publication whose year window moved stays on the chart\'s sessions', async () => {
    const p1 = await gz(priceOn(['2026-10-01', '2026-10-02', '2026-10-03'], [800, 810, 820]));
    const p2 = await gz(priceOn(['2026-10-02', '2026-10-03', '2026-10-04'], [810, 820, 830]));     // first session dropped, one added
    const b1 = await gz(brokerOn(['2026-10-02', '2026-10-03'], [5, 7])), b2 = await gz(brokerOn(['2026-10-02', '2026-10-03', '2026-10-04'], [5, 7, 9]));
    await edge({ bundles:[{ MAPI:{ price:p1, broker:{ body:flip(b1), announced:b1 } } }, { MAPI:{ price:p2, broker:b2 } }] });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const M = await liveData('MAPI');
    expect(M.ohlc.map(b => b.time)).toEqual(['2026-10-01', '2026-10-02', '2026-10-03']);
    // before the review: [5, 7, 9], every value one session early
    expect(await flowOf(M)).toEqual({ recent:[0, 5, 7], all:[0, 5, 7] });
  });
  it('a retried broker answer from a publication that removed a session stays on the chart\'s sessions', async () => {
    const p1 = await gz(priceOn(['2026-10-01', '2026-10-02', '2026-10-05', '2026-10-06'], [800, 810, 820, 830]));
    const p2 = await gz(priceOn(['2026-10-01', '2026-10-05', '2026-10-06'], [800, 820, 830]));     // 2 October corrected away
    const b = await gz(brokerOn(['2026-10-01', '2026-10-05', '2026-10-06'], [3, 4, 6]));
    await edge({ bundles:[{ MAPI:{ price:p1, broker:{ body:b.slice(0, -1), announced:b } } }, { MAPI:{ price:p2, broker:b } }] });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const M = await liveData('MAPI');
    expect(M.ohlc.length).toBe(4);
    expect(await flowOf(M)).toEqual({ recent:[3, 0, 4, 6], all:[3, 0, 4, 6] });              // before the review: [3, 4, 6]
  });
  it('when the first price failed too, the chart and the flow both take the new answer\'s sessions', async () => {
    const p1 = await gz(priceOn(['2026-10-01', '2026-10-02', '2026-10-03'], [800, 810, 820]));
    const p2 = await gz(priceOn(['2026-10-02', '2026-10-03', '2026-10-04'], [810, 820, 830]));
    const b2 = await gz(brokerOn(['2026-10-02', '2026-10-03', '2026-10-04'], [5, 7, 9]));
    await edge({ bundles:[{ MAPI:{ price:{ body:flip(p1), announced:p1 }, broker:b2 } }, { MAPI:{ price:p2, broker:b2 } }] });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const M = await liveData('MAPI');
    expect(M.ohlc.map(b => b.time)).toEqual(['2026-10-02', '2026-10-03', '2026-10-04']);
    expect(await flowOf(M)).toEqual({ recent:[5, 7, 9], all:[5, 7, 9] });
  });
  it('an added asset\'s Flow Timeline retried on a new /bundle stays on the chart\'s sessions (its answer has no price)', async () => {
    const b = await gz(brokerOn(['2026-10-02', '2026-10-03'], [4, 6]));
    const seen = await edge({ bundles:[{ MAPI:{ price:await gz(priceDoc([800, 810, 820])) }, IHSG:{ broker:{ body:flip(b), announced:b } } }, { IHSG:{ broker:b } }] });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const f = await (await liveData('MAPI')).loadAssetFlow!('IHSG');
    expect([Array.from((await f.recent).combos[0].net), Array.from((await f.all).combos[0].net)]).toEqual([[0, 4, 6], [0, 4, 6]]);
    expect(seen.bundleOf.IHSG).toBe(2);
  });
  it('a reference file without sha256 (an older terminal-api or publication) is read as before', async () => {
    const seen = await edge({ bundles:[{ MAPI:{ price:await gz(priceDoc([800, 810, 820])) } }] });
    expect((await liveData('MAPI')).instruments.length).toBe(2);
    expect(seen.reference.tickers).toBe(1);
  });
});
