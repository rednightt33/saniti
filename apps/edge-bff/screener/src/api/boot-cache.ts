/* The page's cached paint (report PAGE LOAD SEQUENCE 6c.3-6c.5; P24 a, built to its recommendation): the last
   catalog, universe and last open screen's result are kept as their JSON bytes in the browser's shared file cache
   (IndexedDB 'terminal-files' through the Terminal's rack.ts fileCache, keyed by sha256 = the ETag edge-bff sends),
   and one pointer in localStorage scr.boot names them with their versions and the login.
   Rules (6c.3, 6c.5; tests/page/boot-cache.test.ts):
   - nothing cached is drawn before an authenticated answer of this page load (app.ts calls read() after one);
   - a pointer of another login is dropped and never read (its bytes age out of the shared LRU);
   - a cached result is used only when its versions equal the cached catalog's, field by field;
   - bytes are stored only when their sha256 equals the announced ETag (a result, which has none, under its own sha). */
import type { CatalogResponse, Definition, RunResponse, UniverseResponse, Versions } from '../core/contract.ts';
import type { FileCache } from '../../../terminal/src/data/rack.ts';
import { sha256Hex } from '../../../terminal/src/data/rack.ts';
import { KEYS, store } from '../storage.ts';

export interface BootPointer {
  login: string;
  versions: Omit<Versions, 'definition_hash'>;
  published_at: string;
  catalog_sha: string | null;
  universe_sha: string | null;
  last: { definition: Definition; definition_hash: string; result_sha: string } | null;
}
/** the fields of `versions` that decide numbers (6c.5 item 1) */
export const VERSION_FIELDS = ['price_data', 'flow_data', 'screener_engine', 'registry', 'screener_registry'] as const;
export const sameVersions = (a: Partial<Versions> | null | undefined, b: Partial<Versions> | null | undefined) =>
  !!a && !!b && VERSION_FIELDS.every(k => (a[k] ?? null) === (b[k] ?? null));

export interface Cached { catalog: CatalogResponse | null; universe: UniverseResponse | null; result: RunResponse | null }

const decode = <T>(b: Uint8Array | null): T | null => { if (!b) return null; try { return JSON.parse(new TextDecoder().decode(b)) as T } catch { return null } };

export class BootCache {
  private ptr: BootPointer | null;
  constructor(private cache: FileCache, private storage: { get<T>(k: string, d: T): T; set(k: string, v: unknown): void; del(k: string): void } = store) {
    const p = storage.get<BootPointer | null>(KEYS.boot, null);
    this.ptr = p && typeof p === 'object' && typeof p.login === 'string' && p.versions ? p : null;
  }
  /** the pointer's ETags for If-None-Match (sent before the login is known: a 304 only confirms bytes the browser has) */
  etags() { return { catalog:this.ptr?.catalog_sha ?? null, universe:this.ptr?.universe_sha ?? null } }
  pointer() { return this.ptr }

  /** The cached objects for `login`, after an authenticated answer (6c.4 S3). Another login's pointer is dropped. */
  async read(login: string): Promise<Cached> {
    const none: Cached = { catalog:null, universe:null, result:null };
    const p = this.ptr;
    if (!p) return none;
    if (p.login !== login) { this.drop(); return none }
    const [cb, ub] = await Promise.all([p.catalog_sha ? this.cache.get(p.catalog_sha) : null, p.universe_sha ? this.cache.get(p.universe_sha) : null]);
    const catalog = decode<CatalogResponse>(cb), universe = decode<UniverseResponse>(ub);
    if (!catalog || !sameVersions(catalog.versions, p.versions)) return none;
    const uOk = universe && sameVersions(universe.versions, p.versions) ? universe : null;
    let result: RunResponse | null = null;
    if (p.last) {
      const r = decode<RunResponse>(await this.cache.get(p.last.result_sha));
      if (r && sameVersions(r.versions, catalog.versions)) result = r;
    }
    return { catalog, universe:uOk, result };
  }

  /** Store verified bytes (sha256 = etag) and point at them. A new version drops the rest of the pointer (6c.5 item 2). */
  async putCatalog(login: string, bytes: Uint8Array, etag: string | null, body: CatalogResponse): Promise<boolean> {
    if (!etag || await sha256Hex(bytes) !== etag) return false;
    await this.cache.put(etag, bytes);
    const v = strip(body.versions), p = this.ptr;
    const keep = p && p.login === login && sameVersions(p.versions, v);
    this.write({ login, versions:v, published_at:body.data.published_at, catalog_sha:etag,
      universe_sha:keep ? p!.universe_sha : null, last:keep ? p!.last : null });
    return true;
  }
  async putUniverse(login: string, bytes: Uint8Array, etag: string | null, body: UniverseResponse): Promise<boolean> {
    const p = this.ptr;
    if (!etag || !p || p.login !== login || !sameVersions(p.versions, body.versions)) return false;
    if (await sha256Hex(bytes) !== etag) return false;
    await this.cache.put(etag, bytes);
    this.write({ ...p, universe_sha:etag });
    return true;
  }
  /** the last open screen's result (no ETag: stored under the sha256 of its own bytes) */
  async putResult(login: string, definition: Definition, bytes: Uint8Array, body: RunResponse): Promise<boolean> {
    const p = this.ptr;
    if (!p || p.login !== login || !sameVersions(p.versions, body.versions) || !body.versions.definition_hash) return false;
    const sha = await sha256Hex(bytes);
    await this.cache.put(sha, bytes);
    this.write({ ...p, last:{ definition, definition_hash:body.versions.definition_hash, result_sha:sha } });
    return true;
  }
  /** a 304 confirms the cached bytes; nothing to store */
  drop() { this.ptr = null; this.storage.del(KEYS.boot) }
  private write(p: BootPointer) { this.ptr = p; this.storage.set(KEYS.boot, p) }
}
const strip = (v: Versions): Omit<Versions, 'definition_hash'> => { const { definition_hash, ...rest } = v; return rest };
