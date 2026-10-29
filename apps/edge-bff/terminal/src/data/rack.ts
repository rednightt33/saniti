/* EXEC-BACKTEST-LOAD (user 2026-10-27: "Idealnya sih kalau ini menggunakan satu source, which is the same storage atau
   same rack, harusnya ya sama aja sih prosesnya dengan terminal"; K3): what every page that reads the rack (the
   Terminal, the Backtest page, later macro or cross-asset pages) shares to get a published file into the browser:
   - the browser's file cache (EXEC-TERMINAL-SPEED step 3, user 2026-10-26: "Cache boleh, tapi jangan sampai cache itu
     terlalu menjadi besar"): IndexedDB 'terminal-files' version 1, store 'files' (keyPath 'sha', index 'used'), the
     record {sha, bytes, size, used}, at most CACHE_LIMIT bytes, the least recently used going first. edge-bff serves
     every page on one origin, so a file one page downloaded is read from the browser by the others. Only bytes whose
     sha256 (and size) are the ones /bundle announced are stored (the Backtest page's load.ts by inflateVerified, the
     Terminal by readVerified), and the Screener page's answer bytes under their own sha256, which equals the ETag
     edge-bff sends where it sends one (screener/src/api/boot-cache.ts). Any IndexedDB failure (no IndexedDB, a newer
     version of the database: VersionError, a blocked open, a full store) only means no cache, never a failed page;
     when another page asks for a newer version, this connection is closed (onversionchange) and the cache stays off
     for the page's life;
   - the download of a presigned file (ERRORS M251): a download that gets no answer, whose body is cut off on the way,
     or that the storage host answers 5xx is asked again FILE_RETRIES times (FILE_RETRY_MS, then twice that); a refusal
     (4xx: 403 an expired link, 404) is answered at once;
   - the check of a file against what terminal-api announced (EXEC-MU-RUNTIME T7, readVerified below).
   All run in a Web Worker as well as on the page. */
export const CACHE_DB = 'terminal-files', CACHE_VERSION = 1, CACHE_STORE = 'files';
export const CACHE_LIMIT = 50_000_000;
export const FILE_RETRIES = 2, FILE_RETRY_MS = 500;

export interface FileCache {
  /** the stored bytes of a sha256, or null (not stored, or no cache); a hit counts as a use */
  get(sha: string): Promise<Uint8Array | null>;
  /** store verified bytes under their sha256, then drop the least recently used files above the limit */
  put(sha: string, bytes: Uint8Array): Promise<void>;
}

const idbReq = <T>(req: IDBRequest<T>) => new Promise<T>((ok, no) => { req.onsuccess = () => ok(req.result); req.onerror = () => no(req.error) });

/** The cache of one page load or worker (`factory`: the browser's indexedDB; a test passes its own). */
export function fileCache(factory: IDBFactory | undefined = globalThis.indexedDB, limit = CACHE_LIMIT): FileCache {
  let db: Promise<IDBDatabase | null> | null = null;
  const open = (): Promise<IDBDatabase | null> => db ||= new Promise(ok => {
    let settled = false;
    // the first outcome decides; a connection that opens after a blocked open gave up is closed at once
    const done = (d: IDBDatabase | null) => { if (!settled) { settled = true; ok(d) } else d?.close() };
    try {
      if (!factory) return done(null);
      const req = factory.open(CACHE_DB, CACHE_VERSION);
      req.onupgradeneeded = () => req.result.createObjectStore(CACHE_STORE, { keyPath:'sha' }).createIndex('used', 'used');
      req.onsuccess = () => {
        const d = req.result;
        d.onversionchange = () => { d.close(); db = Promise.resolve(null) };
        done(d);
      };
      req.onerror = e => { e.preventDefault(); done(null) };       // VersionError and every other refusal: no cache
      req.onblocked = () => done(null);
    } catch { done(null) }
  });
  return {
    async get(sha) {
      const d = await open(); if (!d) return null;
      try {
        const store = d.transaction(CACHE_STORE, 'readwrite').objectStore(CACHE_STORE);
        const hit = await idbReq<any>(store.get(sha));
        if (!hit || !(hit.bytes instanceof ArrayBuffer)) return null;
        store.put({ ...hit, used:Date.now() });
        return new Uint8Array(hit.bytes);
      } catch { return null }
    },
    async put(sha, bytes) {
      const d = await open(); if (!d) return;
      try {
        const store = d.transaction(CACHE_STORE, 'readwrite').objectStore(CACHE_STORE);
        await idbReq(store.put({ sha, bytes:bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), size:bytes.byteLength, used:Date.now() }));
        const all = await idbReq<any[]>(store.index('used').getAll());   // oldest use first
        let total = all.reduce((t, r) => t + r.size, 0);
        for (const r of all) { if (total <= limit) break; if (r.sha === sha) continue; store.delete(r.sha); total -= r.size }
      } catch { /* a full or closed store only loses the cache */ }
    },
  };
}

/** A download the storage host refused or that never arrived whole: `status` 0 when there was no answer. */
export class DownloadError extends Error {
  readonly status: number;
  // a declared field, not a parameter property: Node's type stripping (backtest-worker tests) refuses parameter properties (ERRORS M262)
  constructor(status: number) { super(status ? `A data file could not be downloaded (${status}).` : 'A data file could not be downloaded.'); this.status = status }
}

/** The bytes of a presigned file (no cookies to the storage host), asked again as the header says. */
export async function fetchFile(url: string): Promise<Uint8Array<ArrayBuffer>> {
  let status = 0;
  for (let k = 0; ; k++) {
    try {
      const res = await fetch(url, { credentials:'omit' });
      status = res.status;
      if (res.ok) return new Uint8Array(await res.arrayBuffer());   // a body cut off on the way rejects here
      if (status < 500) break;
    } catch { status = 0 }
    if (k >= FILE_RETRIES) break;
    await new Promise(ok => setTimeout(ok, FILE_RETRY_MS * (k + 1)));
  }
  throw new DownloadError(status);
}

/** the hex sha256 of some bytes (WebCrypto, in a page and in a worker) */
export async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const d = await crypto.subtle.digest('SHA-256', bytes as Uint8Array<ArrayBuffer>);
  return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('');
}

/* EXEC-MU-RUNTIME T7 (accuracy; user option A 2026-10-28, Phase 1): the one check a rack page applies to a published
   file before it draws or stores it. A file terminal-api announces (/bundle; /reference when the publication's refs
   index names the file, T5) is a FileRef with the sha256 and the size of its gzip bytes: bytes of another length or
   sha256, downloaded or found in the cache, are refused (IntegrityError, DATA_INTEGRITY), never drawn and never stored;
   a stored copy that differs is not used and the download replaces it. The rule is the Backtest core's inflateVerified
   (apps/edge-bff/backtest/src/core/datafile.ts), which the Backtest page and both workers apply; the Terminal is built
   alone (apps/edge-bff/Dockerfile stage `terminal` copies terminal/ only), so its pages take the check from here. An
   announcement without a valid sha256 (64 hex) and size is refused too: nothing could be checked (the workers refuse
   it as well, backtest-worker src/terminal.ts bundle). A bare URL is a file no index describes (a reference file of a
   publication before the refs index, or an older terminal-api): it is read as it comes and never stored.
   A content key never names other bytes (ERRORS M250), so a mismatch means a stale answer or a damaged transfer: the
   page asks a new announcement once before it shows INTEGRITY_MESSAGE (live.ts). */
/** one published file: its presigned URL and, from terminal-api, the sha256 (the cache key) and size of its bytes */
export interface FileRef { url: string; sha?: string; bytes?: number; name?: string }
export const INTEGRITY_MESSAGE = 'A data file did not match its published checksum; reload the page.';
/** A file whose bytes are not the ones terminal-api announced. `detail` says what differed (no URL: it is a credential). */
export class IntegrityError extends Error {
  readonly code: 'DATA_INTEGRITY';
  readonly status: number;
  readonly detail: string;
  // declared fields, not parameter properties: Node's type stripping (backtest-worker tests import worker.ts) refuses them (ERRORS M262)
  constructor(detail: string) { super(INTEGRITY_MESSAGE); this.name = 'IntegrityError'; this.code = 'DATA_INTEGRITY'; this.status = 0; this.detail = detail }
}
/** whether an error (an IntegrityError, a worker's answer carrying its code, a TerminalError) is a failed check */
export const isIntegrity = (e: unknown): boolean => !!e && (e as { code?: unknown }).code === 'DATA_INTEGRITY';

/** the announced sha256 in lower case (the cache key, as the Backtest page's), or null when the announcement cannot be
    checked against: no sha256 of 64 hex, or no size (a whole number of bytes) */
const announced = (ref: FileRef): string | null =>
  typeof ref.sha === 'string' && /^[0-9a-f]{64}$/i.test(ref.sha) && Number.isSafeInteger(ref.bytes) && ref.bytes >= 0 ? ref.sha.toLowerCase() : null;

/** what is wrong with `bytes` as the file `ref` announces, or null when they are that file */
export async function mismatch(bytes: Uint8Array, ref: FileRef): Promise<string | null> {
  const sha = announced(ref);
  if (!sha) return 'terminal-api announced no valid sha256 and size';
  if (bytes.byteLength !== ref.bytes) return `${bytes.byteLength} bytes, ${ref.bytes} announced`;
  if (typeof crypto === 'undefined' || !crypto.subtle) return 'this browser cannot compute a sha256 here (no WebCrypto)';
  return await sha256Hex(bytes) === sha ? null : 'the sha256 differs from the announced one';
}

/** The bytes of a published file. A FileRef: from `cache` when the stored bytes are the announced file, else downloaded
    (fetchFile), checked (mismatch, else IntegrityError) and then stored; an announcement that cannot be checked is
    refused before any download. A bare URL: downloaded, unchecked, never stored. */
export async function readVerified(file: string | FileRef, cache: FileCache): Promise<{ bytes: Uint8Array; cached: boolean }> {
  if (typeof file === 'string') return { bytes:await fetchFile(file), cached:false };
  const name = file.name || 'a file', sha = announced(file);
  if (!sha) throw new IntegrityError(`${name}: terminal-api announced no valid sha256 and size`);
  const hit = await cache.get(sha);
  if (hit && !await mismatch(hit, file)) return { bytes:hit, cached:true };   // a stored copy that differs is not used
  const bytes = await fetchFile(file.url);                  // DownloadError carries the storage host's status
  const why = await mismatch(bytes, file);
  if (why) throw new IntegrityError(`${name}: ${why}`);
  cache.put(sha, bytes);                                     // replaces a stored copy that differed; not awaited: a failed store only loses the cache
  return { bytes, cached:false };
}
