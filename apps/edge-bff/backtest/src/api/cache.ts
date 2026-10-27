/* The browser's file cache, shared with the Terminal (apps/edge-bff/terminal/src/data/worker.ts, EXEC-TERMINAL-SPEED
   step 3, user 2026-10-26: "Cache boleh, tapi jangan sampai cache itu terlalu menjadi besar"): the same IndexedDB
   database 'terminal-files' version 1, store 'files' (keyPath 'sha', index 'used'), the same record {sha, bytes, size,
   used} and the same limit, the least recently used going first. edge-bff serves both pages on one origin, so a file
   one of them downloaded is read from the browser by the other. A file is kept under the sha256 of its bytes; the page
   stores only bytes that passed inflateVerified (live.ts), and a cached file goes through inflateVerified again before
   it is used, so an entry whose bytes do not match the manifest is never used (the download that follows replaces it).
   Any IndexedDB failure (no IndexedDB, a newer version of the database: VersionError, a blocked open, a full store)
   only means no cache, never a failed page; when another page asks for a newer version, this connection is closed
   (onversionchange) and the cache stays off for the rest of the page's life. */
export const CACHE_DB = 'terminal-files', CACHE_VERSION = 1, CACHE_STORE = 'files';
/** the Terminal's CACHE_LIMIT (bytes of every stored file together); tests/cache.test.ts checks the two are equal */
export const CACHE_LIMIT = 50_000_000;

export interface FileCache {
  /** the stored bytes of a sha256, or null (not stored, or no cache); a hit counts as a use */
  get(sha: string): Promise<Uint8Array | null>;
  /** store verified bytes under their sha256, then drop the least recently used files above the limit */
  put(sha: string, bytes: Uint8Array): Promise<void>;
}

const idbReq = <T>(req: IDBRequest<T>) => new Promise<T>((ok, no) => { req.onsuccess = () => ok(req.result); req.onerror = () => no(req.error) });

/** The cache of one page load (`factory`: the browser's indexedDB; a test passes its own; `limit`: CACHE_LIMIT). */
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
