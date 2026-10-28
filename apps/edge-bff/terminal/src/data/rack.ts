/* EXEC-BACKTEST-LOAD (user 2026-10-27: "Idealnya sih kalau ini menggunakan satu source, which is the same storage atau
   same rack, harusnya ya sama aja sih prosesnya dengan terminal"; K3): what every page that reads the rack (the
   Terminal, the Backtest page, later macro or cross-asset pages) shares to get a published file into the browser:
   - the browser's file cache (EXEC-TERMINAL-SPEED step 3, user 2026-10-26: "Cache boleh, tapi jangan sampai cache itu
     terlalu menjadi besar"): IndexedDB 'terminal-files' version 1, store 'files' (keyPath 'sha', index 'used'), the
     record {sha, bytes, size, used}, at most CACHE_LIMIT bytes, the least recently used going first. edge-bff serves
     every page on one origin, so a file one page downloaded is read from the browser by the others. Only bytes whose
     sha256 is the one /bundle announced are stored. Any IndexedDB failure (no IndexedDB, a newer version of the
     database: VersionError, a blocked open, a full store) only means no cache, never a failed page; when another page
     asks for a newer version, this connection is closed (onversionchange) and the cache stays off for the page's life;
   - the download of a presigned file (ERRORS M251): a download that gets no answer, whose body is cut off on the way,
     or that the storage host answers 5xx is asked again FILE_RETRIES times (FILE_RETRY_MS, then twice that); a refusal
     (4xx: 403 an expired link, 404) is answered at once.
   Both run in a Web Worker as well as on the page. */
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
