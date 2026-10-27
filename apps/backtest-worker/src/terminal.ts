/* The backtest worker's market-data client: terminal-api (apps/terminal-api/app/main.py) and the presigned bucket
   files it hands out are the only way the worker reads market data (CONTRACT.md sections 1-2). No Postgres, no
   bucket credentials.

   POST {TERMINAL_URL}/api/terminal/v1/bundle {ticker, datasets, packs: true} with header x-terminal-proxy-key =
   TERMINAL_PROXY_KEY (the gateway key, D-U1: terminal-api counts the requests against its TERMINAL_PROXY_SUBSCRIBER
   account) answers, per dataset, data_through, first_year and every published file (oldest first; packs: the price
   pack, the broker archive plus the yearly broker files after it) as {year, url, sha256, bytes, rows, pack?}. The
   files are downloaded from their presigned URLs without any credential, checked against that sha256 and size,
   inflated and decoded by the shared core (datafile.ts), so the worker reads the bars the Terminal draws.
   terminal-api answers errors as {error: code, message} (400 invalid_request also lists fields): 404 unknown_ticker,
   401 proxy_key_rejected / session_ended, 429 quota_exceeded; GET /reference/{tickers|brokers} answers {url} only
   (no sha256: a reference file cannot be checked against a manifest); GET /manifest/{ticker} answers the ticker's
   manifest per dataset (data_through, the years' sha256, bytes, rows and first and last row dates) without granting a
   file (no quota, no audit row, no URL); /bundle and /reference count every file they grant in the subscriber's quota
   and write an audit row (main.py grant, reference).

   Errors are DataError (datafile.ts): a ticker, dataset or file that is not published is DATA_MISSING; a file that is
   not what the manifest says is DATA_INTEGRITY; terminal-api or the bucket refusing or failing (4xx other than 404,
   5xx after the retries, network) is DATA_UNAVAILABLE. Only network errors and 5xx are retried (backoff base x 2^k);
   a 4xx never is. The key is sent only to terminal-api and never written to a message or a log line; presigned URLs
   (temporary credentials in their query) are not logged either.

   Cache: files by sha256 (content addressed, so a cached file can never belong to another data version), the verified
   gzip bytes in memory (LRU, byte budget) and optionally on disk (LRU, byte budget); a cached file is checked again
   (sha256, size) every time it is used, a damaged disk copy is dropped and downloaded again.

   What the client accepts from terminal-api and the bucket (a wrong or compromised answer must not turn the worker into
   a client of anything else, nor fill its memory):
   - a file or reference URL must be on the bucket origin BACKTEST_FILE_ORIGIN (scheme, host and port; a host may
     start with '*.' as in the CSP host-source the edge-bff pages allow for the same downloads, connect-src
     https://*.t3.storageapi.dev); any other URL is DATA_INTEGRITY and is never requested;
   - a body is read as a stream and dropped once it passes its size: a data file's manifest bytes (DATA_INTEGRITY),
     anything else BACKTEST_MAX_FILE_BYTES (a reference file: DATA_INTEGRITY; a terminal-api answer: DATA_UNAVAILABLE);
   - a file inflates to at most BACKTEST_MAX_FILE_BYTES (datafile.ts, DATA_INTEGRITY).

   Configuration (optionsFromEnv; no value is assumed, the limits are measured in the dev E2E, K7b):
   TERMINAL_URL (an origin without user name or password), TERMINAL_PROXY_KEY (>= 32 characters, as terminal-api and
   edge-bff require), BACKTEST_CACHE_BYTES, BACKTEST_DOWNLOAD_CONCURRENCY (HTTP requests in flight),
   BACKTEST_DOWNLOAD_RETRIES (retries after the first try), BACKTEST_RETRY_BASE_MS, BACKTEST_HTTP_TIMEOUT_MS (per
   request), BACKTEST_FILE_ORIGIN, BACKTEST_MAX_FILE_BYTES, optional BACKTEST_CACHE_DIR with BACKTEST_CACHE_DIR_BYTES. */
import { mkdir, readFile, readdir, rename, stat, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';
import {
  DataError, brokerGaps, brokerRows, corporateActions, dataVersion, decodeColumnar, inflateVerified, priceSeries,
} from '../../edge-bff/backtest/src/core/datafile.ts';
import type { BrokerGap, BrokerRow, Columnar, CorporateAction, FileEntry, PriceSeries } from '../../edge-bff/backtest/src/core/datafile.ts';
import { flowData } from '../../edge-bff/backtest/src/core/flow.ts';
import type { FlowData } from '../../edge-bff/backtest/src/core/flow.ts';
import { isIsoDate } from '../../edge-bff/backtest/src/core/signals.ts';

export const API = '/api/terminal/v1';
export const PROXY_HEADER = 'x-terminal-proxy-key';
export const TICKER = /^[A-Z0-9]{1,12}$/;                  // terminal-api TICKER
export type Dataset = 'price' | 'broker' | 'events';
export const DATASETS: readonly Dataset[] = ['price', 'broker', 'events'];

export interface TerminalOptions {
  url: string;                       // terminal-api base URL (TERMINAL_URL), without the API path
  proxyKey: string;                  // TERMINAL_PROXY_KEY
  cacheBytes: number;                // memory cache budget (bytes of gzip files); 0 = no memory cache
  cacheDir?: string;                 // disk cache directory
  cacheDirBytes?: number;            // disk cache budget, required with cacheDir
  concurrency: number;               // HTTP requests in flight (terminal-api and bucket together)
  retries: number;                   // retries of a network error or a 5xx answer
  retryBaseMs: number;               // backoff: retryBaseMs x 2^k before retry k (0-based)
  timeoutMs: number;                 // per HTTP request, body included
  fileOrigin: string;                // the origin every file and reference URL must have (BACKTEST_FILE_ORIGIN, fileOriginOf)
  maxFileBytes: number;              // the most bytes of one body that is not a data file, and of any inflated file
  fetch?: typeof fetch;              // tests
  log?: (event: string, fields: Record<string, unknown>) => void;
}

/** The options from the environment; a missing or invalid variable is a configuration error naming the variable
    (never its value). */
export function optionsFromEnv(env: Record<string, string | undefined> = process.env): TerminalOptions {
  const need = (k: string) => { const v = (env[k] ?? '').trim(); if (!v) throw new Error(`${k} is required.`); return v };
  const whole = (k: string, min: number) => {
    const v = Number(need(k));
    if (!Number.isSafeInteger(v) || v < min) throw new Error(`${k} must be a whole number of at least ${min}.`);
    return v;
  };
  const url = need('TERMINAL_URL').replace(/\/+$/, '');
  if (!/^https?:\/\/[^/?#]+$/.test(url)) throw new Error('TERMINAL_URL must be an http(s) origin without a path.');
  // credentials in the URL would reach the start log (config.ts describeConfig) and fetch refuses them anyway
  let parsed: URL | null = null;
  try { parsed = new URL(url) } catch { /* refused below */ }
  if (!parsed) throw new Error('TERMINAL_URL must be an http(s) origin without a path.');
  if (parsed.username || parsed.password) throw new Error('TERMINAL_URL must not contain a user name or password.');
  const proxyKey = need('TERMINAL_PROXY_KEY');
  if (proxyKey.length < 32) throw new Error('TERMINAL_PROXY_KEY must be at least 32 characters.');
  const fileOrigin = need('BACKTEST_FILE_ORIGIN');
  if (!fileOriginOf(fileOrigin)) throw new Error(FILE_ORIGIN_FORMAT);
  const cacheDir = (env.BACKTEST_CACHE_DIR ?? '').trim() || undefined;
  return {
    url, proxyKey, cacheBytes: whole('BACKTEST_CACHE_BYTES', 0), cacheDir, cacheDirBytes: cacheDir ? whole('BACKTEST_CACHE_DIR_BYTES', 1) : undefined,
    concurrency: whole('BACKTEST_DOWNLOAD_CONCURRENCY', 1), retries: whole('BACKTEST_DOWNLOAD_RETRIES', 0),
    retryBaseMs: whole('BACKTEST_RETRY_BASE_MS', 0), timeoutMs: whole('BACKTEST_HTTP_TIMEOUT_MS', 1),
    fileOrigin, maxFileBytes: whole('BACKTEST_MAX_FILE_BYTES', 1),
  };
}

/* ---- the bucket origin -------------------------------------------------------------------------------------------- */
const FILE_ORIGIN_FORMAT = 'BACKTEST_FILE_ORIGIN must be scheme://host[:port], http or https, the host lowercase and optionally starting with *. (as the CSP host-source https://*.t3.storageapi.dev).';
/** An origin pattern as a CSP host-source without a path: scheme, host (a leading '*.' matches one or more labels, never
    the bare suffix) and port (none: the scheme's default port only). Null when the text is not one. */
export function fileOriginOf(pattern: string): ((url: string) => boolean) | null {
  const m = /^(https?):\/\/(\*\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)*)(?::(\d{1,5}))?$/.exec(pattern);
  if (!m) return null;
  const [, scheme, wild, host, port = ''] = m;
  if (port && (+port < 1 || +port > 65535)) return null;
  const defaultPort = (p: string) => p === '' || (scheme === 'https' && p === '443') || (scheme === 'http' && p === '80');
  return (url: string) => {
    let u: URL;
    try { u = new URL(url) } catch { return false }
    if (u.protocol !== `${scheme}:` || u.username || u.password) return false;
    if (port ? u.port !== port && !(defaultPort(port) && u.port === '') : u.port !== '') return false;
    return wild ? u.hostname.endsWith(`.${host}`) : u.hostname === host;
  };
}

/* ---- results -------------------------------------------------------------------------------------------------- */
/** A file a load read: what data_version is computed over, plus what it was. */
export interface ReadFile { ticker: string; dataset: Dataset; sha256: string; bytes: number; rows: number | null; year: number | null; pack: string | null; cached: boolean }
export interface LoadedTicker {
  ticker: string;
  prices: PriceSeries | null;                    // 'price' read
  broker_rows: BrokerRow[] | null;               // 'broker' read (null as well with keepBrokerRows: false)
  broker_gaps: BrokerGap[] | null;               // the publisher's gap markers
  flow: FlowData | null;                         // 'price' and 'broker' read: flow.ts on the ticker's price bars
  corporate_actions: CorporateAction[] | null;   // 'events' read; a ticker without events has an empty list
  data_through: Partial<Record<Dataset, string | null>>;   // per dataset, as the manifest has it
  first_year: Partial<Record<Dataset, number | null>>;
  generated_at: string | null;                   // the manifest's generated_at
  files: ReadFile[];
}
export interface Loaded {
  tickers: Record<string, LoadedTicker>;         // in the order asked
  files: ReadFile[];                             // every file read, sorted by ticker, dataset, sha256
  data_version: string;                          // datafile.ts dataVersion over `files`
}
export interface LoadOptions { keepBrokerRows?: boolean }   // false: only the flow is kept (portfolio memory)
export interface TickerRef { ticker: string; name: string | null; type: string | null; sector: string | null }
export interface BrokerRef { code: string; name: string | null; type: string | null }

/** The caller's freshness check (CONTRACT.md sections 2-3, FLOW_DATA_CHECK.md): a dataset whose manifest data_through is
    before `to` (or has none) cannot serve a period that ends on `to`. */
export function checkDataThrough(t: LoadedTicker, dataset: Dataset, to: string): void {
  const through = t.data_through[dataset];
  if (!through || through < to)
    throw new DataError('DATA_UNAVAILABLE', `${t.ticker} ${dataset} is published through ${through ?? 'no date'}; the period ends on ${to}.`, `${t.ticker}.${dataset}`, { data_through: through ?? null, to });
}
/** What a /bundle answer says is not published for the datasets asked: the first dataset other than events without any
    file (the publisher writes an events file only for a ticker with events, so no events file = no corporate action),
    as the DataError loadTicker raises for it; null when every dataset has its files. */
export function unpublished(b: { ticker: string; datasets: Partial<Record<Dataset, { files: readonly unknown[] }>> }, datasets: readonly Dataset[]): DataError | null {
  for (const name of datasets) if (name !== 'events' && !b.datasets[name]?.files.length) return new DataError('DATA_MISSING', `No ${name} file is published for ${b.ticker}.`, `${b.ticker}.${name}`);
  return null;
}
/** The caller's range check: the ticker has a price bar inside [from, to]. */
export function checkPriceRange(t: LoadedTicker, from: string, to: string): void {
  const d = t.prices?.dates;
  if (!d || !d.some(x => x >= from && x <= to))
    throw new DataError('DATA_MISSING', `${t.ticker} has no published price bar from ${from} to ${to}.`, t.ticker, { from, to, first: d?.[0] ?? null, last: d?.[d.length - 1] ?? null });
}

/* ---- plumbing -------------------------------------------------------------------------------------------------- */
const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms));

/** At most n tasks at a time, first come first served. */
class Gate {
  private free: number; private queue: (() => void)[] = [];
  constructor(n: number) { this.free = n }
  async run<T>(task: () => Promise<T>): Promise<T> {
    if (this.free > 0) this.free--; else await new Promise<void>(ok => this.queue.push(ok));
    try { return await task() } finally { const next = this.queue.shift(); if (next) next(); else this.free++ }
  }
}

class MemoryCache {
  private map = new Map<string, Uint8Array>(); private budget: number; size = 0;
  constructor(budget: number) { this.budget = budget }
  get(sha: string): Uint8Array | undefined {
    const v = this.map.get(sha);
    if (v) { this.map.delete(sha); this.map.set(sha, v) }          // most recently used last
    return v;
  }
  set(sha: string, v: Uint8Array): void {
    if (v.byteLength > this.budget) return;
    this.delete(sha);
    this.map.set(sha, v); this.size += v.byteLength;
    for (const [k, old] of this.map) { if (this.size <= this.budget) break; this.map.delete(k); this.size -= old.byteLength }
  }
  delete(sha: string): void { const v = this.map.get(sha); if (v) { this.map.delete(sha); this.size -= v.byteLength } }
}

/** Files <sha256>.json.gz in one directory, least recently used dropped first (recency: write time at start, then use). */
class DiskCache {
  private index = new Map<string, number>(); private size = 0; private ready: Promise<void> | null = null;
  private dir: string; private budget: number;
  constructor(dir: string, budget: number) { this.dir = dir; this.budget = budget }
  private file = (sha: string) => path.join(this.dir, `${sha}.json.gz`);
  private init(): Promise<void> {
    return this.ready ||= (async () => {
      await mkdir(this.dir, { recursive: true });
      const found: [string, number, number][] = [];
      for (const name of await readdir(this.dir)) {
        const m = /^([0-9a-f]{64})\.json\.gz$/.exec(name);
        if (!m) continue;
        try { const s = await stat(path.join(this.dir, name)); found.push([m[1], s.size, s.mtimeMs]) } catch { /* removed meanwhile */ }
      }
      for (const [sha, bytes] of found.sort((a, b) => a[2] - b[2])) { this.index.set(sha, bytes); this.size += bytes }
    })();
  }
  async get(sha: string): Promise<Uint8Array | null> {
    await this.init();
    if (!this.index.has(sha)) return null;
    try {
      const b = new Uint8Array(await readFile(this.file(sha)));
      const n = this.index.get(sha) as number; this.index.delete(sha); this.index.set(sha, n);
      return b;
    } catch { await this.drop(sha); return null }
  }
  async put(sha: string, bytes: Uint8Array): Promise<void> {
    await this.init();
    if (bytes.byteLength > this.budget || this.index.has(sha)) return;
    const tmp = `${this.file(sha)}.${process.pid}.${Math.random().toString(36).slice(2)}.tmp`;
    await writeFile(tmp, bytes);
    await rename(tmp, this.file(sha));                                  // a reader never sees half a file
    this.index.set(sha, bytes.byteLength); this.size += bytes.byteLength;
    for (const old of [...this.index.keys()]) { if (this.size <= this.budget) break; if (old !== sha) await this.drop(old) }
  }
  async drop(sha: string): Promise<void> {
    const n = this.index.get(sha);
    if (n !== undefined) { this.index.delete(sha); this.size -= n }
    await unlink(this.file(sha)).catch(() => {});
  }
}

interface Answer { status: number; bytes: Uint8Array }
interface BundleFile extends FileEntry { rows?: number; year?: number; pack?: string }
interface BundleDataset { data_through: string | null; first_year: number | null; files: BundleFile[] }
interface Bundle { ticker: string; generated_at: string | null; expires_in_seconds: number; datasets: Partial<Record<Dataset, BundleDataset>> }

const json = (b: Uint8Array): any => { try { return JSON.parse(new TextDecoder().decode(b)) } catch { return null } };
/** The most bytes a body may have by its status, and the error when it has more (http reads no further). */
type Cap = (status: number) => { bytes: number; error: () => DataError };
/** A body read as a stream, dropped once it passes the cap (the connection is cancelled; nothing more is buffered). */
async function readBody(res: Response, cap: ReturnType<Cap>): Promise<Uint8Array> {
  const declared = Number(res.headers.get('content-length'));
  if (Number.isFinite(declared) && declared > cap.bytes) { await res.body?.cancel().catch(() => {}); throw cap.error() }
  const reader = res.body?.getReader();
  if (!reader) return new Uint8Array(0);
  const parts: Uint8Array[] = []; let n = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    n += value.byteLength;
    if (n > cap.bytes) { await reader.cancel().catch(() => {}); throw cap.error() }
    parts.push(value);
  }
  const out = new Uint8Array(n); let at = 0;
  for (const p of parts) { out.set(p, at); at += p.byteLength }
  return out;
}
const upstream = (b: Uint8Array) => {
  const j = json(b), code = j && typeof j.error === 'string' ? j.error : null, message = j && typeof j.message === 'string' ? j.message : null;
  return { code, message };
};

/* ---- the client ------------------------------------------------------------------------------------------------ */
export class TerminalClient {
  private o: TerminalOptions; private gate: Gate; private mem: MemoryCache; private disk: DiskCache | null;
  private fetch: typeof fetch; private inflight = new Map<string, Promise<{ doc: Columnar; cached: boolean }>>();
  private onBucket: (url: string) => boolean;
  stats = { bundles: 0, downloads: 0, download_bytes: 0, cache_hits: 0, retries: 0 };

  constructor(o: TerminalOptions) {
    for (const [k, min] of [['cacheBytes', 0], ['concurrency', 1], ['retries', 0], ['retryBaseMs', 0], ['timeoutMs', 1], ['maxFileBytes', 1]] as const)
      if (!Number.isSafeInteger(o[k]) || (o[k] as number) < min) throw new Error(`TerminalClient: ${k} must be a whole number of at least ${min}.`);
    if (!o.url || !o.proxyKey) throw new Error('TerminalClient: url and proxyKey are required.');
    const onBucket = typeof o.fileOrigin === 'string' ? fileOriginOf(o.fileOrigin) : null;
    if (!onBucket) throw new Error('TerminalClient: fileOrigin must be an origin pattern (fileOriginOf).');
    this.onBucket = onBucket;
    if (o.cacheDir && !(Number.isSafeInteger(o.cacheDirBytes) && (o.cacheDirBytes as number) >= 1)) throw new Error('TerminalClient: cacheDirBytes is required with cacheDir.');
    this.o = { ...o, url: o.url.replace(/\/+$/, '') };
    this.gate = new Gate(o.concurrency); this.mem = new MemoryCache(o.cacheBytes);
    this.disk = o.cacheDir ? new DiskCache(o.cacheDir, o.cacheDirBytes as number) : null;
    this.fetch = o.fetch ?? globalThis.fetch;
  }
  private log(event: string, fields: Record<string, unknown>) { try { this.o.log?.(event, fields) } catch { /* logging never fails a load */ } }

  /** One HTTP exchange with the retry rule: network errors (timeouts included) and 5xx are retried, anything else is
      answered as it is. The body is read inside the attempt, so a connection lost mid-body is a network error; a body
      over its cap is the cap's error at once (never retried, never read to its end). */
  private async http(url: string, init: RequestInit, what: string, field: string | undefined, cap: Cap): Promise<Answer> {
    for (let attempt = 0; ; attempt++) {
      let answer: Answer | null = null, failure = '';
      try {
        answer = await this.gate.run(async () => {
          const res = await this.fetch(url, { ...init, redirect: 'error', signal: AbortSignal.timeout(this.o.timeoutMs) });
          return { status: res.status, bytes: await readBody(res, cap(res.status)) };
        });
      } catch (e) { if (e instanceof DataError) throw e; failure = (e as Error)?.name || 'Error' }
      if (answer && answer.status < 500) return answer;
      if (attempt >= this.o.retries) {
        const why = answer ? `answered ${answer.status}` : `could not be reached (${failure})`;
        throw new DataError('DATA_UNAVAILABLE', `${what} ${why}${attempt ? ` after ${attempt + 1} tries` : ''}.`, field, answer ? { status: answer.status, ...upstream(answer.bytes) } : { network: failure });
      }
      this.stats.retries++;
      this.log('terminal_retry', { what, attempt: attempt + 1, ...(answer ? { status: answer.status } : { error: failure }) });
      await sleep(this.o.retryBaseMs * 2 ** attempt);
    }
  }

  private async api(method: 'GET' | 'POST', p: string, body: unknown, what: string, field?: string): Promise<any> {
    const headers: Record<string, string> = { [PROXY_HEADER]: this.o.proxyKey, accept: 'application/json' };
    if (body !== undefined) headers['content-type'] = 'application/json';
    const max = this.o.maxFileBytes, cap: Cap = () => ({ bytes: max, error: () => new DataError('DATA_UNAVAILABLE', `${what}: terminal-api answered more than ${max} bytes.`, field) });
    const a = await this.http(this.o.url + API + p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) }, what, field, cap);
    if (a.status === 200) {
      const j = json(a.bytes);
      if (!j || typeof j !== 'object') throw new DataError('DATA_UNAVAILABLE', `${what}: terminal-api answered something that is not JSON.`, field);
      return j;
    }
    const u = upstream(a.bytes), said = u.code ? ` (${u.code}${u.message ? `: ${u.message}` : ''})` : '';
    throw new DataError(a.status === 404 ? 'DATA_MISSING' : 'DATA_UNAVAILABLE', `${what}: terminal-api answered ${a.status}${said}.`, field, { status: a.status, ...u });
  }

  /** terminal-api /bundle of one ticker (packs: true), checked for the shape the decoders rely on. */
  async bundle(ticker: string, datasets: readonly Dataset[]): Promise<Bundle> {
    if (typeof ticker !== 'string' || !TICKER.test(ticker)) throw new DataError('DATA_MISSING', `${JSON.stringify(ticker)} is not a ticker terminal-api publishes.`, 'ticker');
    const asked = [...new Set(datasets)];
    if (!asked.length || asked.some(d => !DATASETS.includes(d))) throw new TypeError(`bundle: datasets must be some of ${DATASETS.join(', ')}.`);
    const t0 = Date.now();
    this.stats.bundles++;
    const b = await this.api('POST', '/bundle', { ticker, datasets: asked, packs: true }, `The data of ${ticker}`, ticker);
    const bad = (why: string) => new DataError('DATA_INTEGRITY', `terminal-api /bundle for ${ticker}: ${why}.`, ticker);
    if (b.ticker !== ticker) throw bad(`answered for ${JSON.stringify(b.ticker)}`);
    if (!b.datasets || typeof b.datasets !== 'object') throw bad('no datasets');
    const out: Bundle = { ticker, generated_at: typeof b.generated_at === 'string' ? b.generated_at : null, expires_in_seconds: b.expires_in_seconds, datasets: {} };
    for (const name of asked) {
      const ds = b.datasets[name];
      if (!ds || !Array.isArray(ds.files)) throw bad(`no ${name} entry`);
      const files = ds.files.map((f: any, k: number): BundleFile => {
        if (!f || typeof f.url !== 'string' || !/^https?:\/\//.test(f.url) || typeof f.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(f.sha256)
          || !Number.isSafeInteger(f.bytes) || f.bytes < 0) throw bad(`${name} file ${k + 1} has no valid url, sha256 or bytes`);
        if (!this.onBucket(f.url)) throw bad(`${name} file ${k + 1} is not on the bucket origin ${this.o.fileOrigin} (BACKTEST_FILE_ORIGIN)`);
        return { url: f.url, sha256: f.sha256, bytes: f.bytes, ...(Number.isSafeInteger(f.rows) ? { rows: f.rows } : {}),
                 ...(Number.isSafeInteger(f.year) ? { year: f.year } : {}), ...(typeof f.pack === 'string' ? { pack: f.pack } : {}) };
      });
      out.datasets[name] = { data_through: typeof ds.data_through === 'string' ? ds.data_through : null, first_year: Number.isSafeInteger(ds.first_year) ? ds.first_year : null, files };
    }
    this.log('terminal_bundle', { ticker, datasets: asked, files: asked.reduce((n, d) => n + (out.datasets[d]?.files.length ?? 0), 0), ms: Date.now() - t0 });
    return out;
  }

  /** One file: from the cache (checked again) or downloaded from its presigned URL without credentials, then checked
      against its sha256 and size (inflateVerified) and kept in the cache. */
  async file(f: FileEntry, what: string, field?: string): Promise<{ doc: Columnar; cached: boolean }> {
    let p = this.inflight.get(f.sha256);
    if (!p) {
      p = this.fetchFile(f, what, field).finally(() => this.inflight.delete(f.sha256));
      this.inflight.set(f.sha256, p);
    }
    return p;
  }
  private async fetchFile(f: FileEntry, what: string, field?: string): Promise<{ doc: Columnar; cached: boolean }> {
    for (const where of ['memory', 'disk'] as const) {
      const bytes = where === 'memory' ? this.mem.get(f.sha256) : this.disk ? await this.disk.get(f.sha256) : null;
      if (!bytes) continue;
      try {
        const doc = await inflateVerified(bytes, f, what, this.o.maxFileBytes);
        if (where === 'disk') this.mem.set(f.sha256, bytes);
        this.stats.cache_hits++;
        this.log('terminal_file', { what, bytes: f.bytes, cached: where });
        return { doc, cached: true };
      } catch {                                                         // a damaged copy is never used: drop it and download
        if (where === 'memory') this.mem.delete(f.sha256); else await this.disk?.drop(f.sha256);
      }
    }
    const t0 = Date.now();
    // no header: the URL is the only credential; the file has its manifest size, an error answer at most maxFileBytes
    const cap: Cap = status => status === 200
      ? { bytes: f.bytes, error: () => new DataError('DATA_INTEGRITY', `${what} has more than the ${f.bytes} bytes its manifest says.`, field) }
      : { bytes: this.o.maxFileBytes, error: () => new DataError('DATA_UNAVAILABLE', `${what}: the bucket answered ${status} with more than ${this.o.maxFileBytes} bytes.`, field, { status }) };
    const a = await this.http(f.url, { method: 'GET' }, what, field, cap);
    if (a.status !== 200) {
      const missing = a.status === 404;
      throw new DataError(missing ? 'DATA_MISSING' : 'DATA_UNAVAILABLE', missing ? `${what} is named by the manifest but not in the bucket (404).`
        : `${what}: the bucket refused the presigned URL (${a.status}${a.status === 403 ? '; it may have expired' : ''}).`, field, { status: a.status });
    }
    this.stats.downloads++; this.stats.download_bytes += a.bytes.byteLength;
    let doc: Columnar;
    try { doc = await inflateVerified(a.bytes, f, what, this.o.maxFileBytes) }
    catch (e) { if (e instanceof DataError && !e.field) e.field = field; throw e }
    this.mem.set(f.sha256, a.bytes);
    if (this.disk) await this.disk.put(f.sha256, a.bytes).catch(e => this.log('terminal_cache_error', { error: (e as { code?: string })?.code ?? (e as Error)?.name }));
    this.log('terminal_file', { what, bytes: f.bytes, ms: Date.now() - t0, cached: false });
    return { doc, cached: false };
  }

  /** One ticker's datasets, decoded. Every dataset asked must have a file (DATA_MISSING otherwise), except events: the
      publisher writes an events file only for a ticker with events (no file = no corporate action). */
  async loadTicker(ticker: string, datasets: readonly Dataset[], opts: LoadOptions = {}): Promise<LoadedTicker> {
    const b = await this.bundle(ticker, datasets), files: ReadFile[] = [], docs: Partial<Record<Dataset, Columnar[]>> = {};
    const t: LoadedTicker = { ticker, prices: null, broker_rows: null, broker_gaps: null, flow: null, corporate_actions: null,
      data_through: {}, first_year: {}, generated_at: b.generated_at, files };
    const none = unpublished(b, Object.keys(b.datasets) as Dataset[]);
    if (none) throw none;
    await Promise.all((Object.keys(b.datasets) as Dataset[]).map(async name => {
      const ds = b.datasets[name] as BundleDataset;
      t.data_through[name] = ds.data_through; t.first_year[name] = ds.first_year;
      docs[name] = await Promise.all(ds.files.map(async f => {
        const label = `${ticker} ${name} ${f.pack ?? f.year ?? 'all'}`;
        const { doc, cached } = await this.file(f, label, `${ticker}.${name}`);
        files.push({ ticker, dataset: name, sha256: f.sha256, bytes: f.bytes, rows: f.rows ?? null, year: f.year ?? null, pack: f.pack ?? null, cached });
        return doc;
      }));
    }));
    if (docs.price) t.prices = priceSeries(ticker, docs.price);
    if (docs.broker) {
      const rows = brokerRows(docs.broker), gaps = brokerGaps(docs.broker);
      t.broker_gaps = gaps;
      if (opts.keepBrokerRows !== false) t.broker_rows = rows;
      if (t.prices) t.flow = flowData(rows, t.prices.dates, gaps);
    }
    if (docs.events) t.corporate_actions = corporateActions(docs.events);
    files.sort(byFile);
    return t;
  }

  /** Several tickers (each once, in the order asked), at most `concurrency` of them in flight; the first error stops the
      load (no further ticker is started) and is thrown. */
  async loadTickers(tickers: readonly string[], datasets: readonly Dataset[], opts: LoadOptions = {}): Promise<Loaded> {
    const list = [...new Set(tickers)], out: (LoadedTicker | undefined)[] = new Array(list.length);
    let next = 0, failed: unknown = null;
    const lane = async () => {
      while (!failed && next < list.length) {
        const k = next++;
        try { out[k] = await this.loadTicker(list[k], datasets, opts) } catch (e) { failed ||= e }
      }
    };
    await Promise.all(Array.from({ length: Math.min(this.o.concurrency, list.length) }, lane));
    if (failed) throw failed;
    const loaded = out as LoadedTicker[], files = loaded.flatMap(t => t.files).sort(byFile);
    return { tickers: Object.fromEntries(loaded.map(t => [t.ticker, t])), files, data_version: await dataVersion(files) };
  }

  /** One ticker's manifest (terminal-api GET /manifest/{ticker}) without granting any file: data_through per dataset, as
      /bundle reports it, and last_bar, the date of the newest row of its yearly price files (the newest `last` of the
      price years: publisher.py publish writes each file's last row date; the price pack /bundle hands out holds the
      same rows, publish_packs), null without a price file. A ticker terminal-api does not publish is DATA_MISSING
      (its 404). */
  async manifest(ticker: string): Promise<{ ticker: string; data_through: Partial<Record<Dataset, string | null>>; last_bar: string | null }> {
    if (typeof ticker !== 'string' || !TICKER.test(ticker)) throw new DataError('DATA_MISSING', `${JSON.stringify(ticker)} is not a ticker terminal-api publishes.`, 'ticker');
    const m = await this.api('GET', `/manifest/${ticker}`, undefined, `The manifest of ${ticker}`, ticker);
    const bad = (why: string) => new DataError('DATA_INTEGRITY', `terminal-api /manifest for ${ticker}: ${why}.`, ticker);
    if (m.ticker !== ticker || !m.datasets || typeof m.datasets !== 'object') throw bad(`not the manifest of ${ticker}`);
    const data_through: Partial<Record<Dataset, string | null>> = {};
    for (const name of DATASETS) if (m.datasets[name]) data_through[name] = typeof m.datasets[name].data_through === 'string' ? m.datasets[name].data_through : null;
    const years = m.datasets.price?.years ?? {};
    if (!years || typeof years !== 'object' || Array.isArray(years)) throw bad('the price years are not a list of files');
    let last_bar: string | null = null;
    for (const [y, f] of Object.entries(years as Record<string, { last?: unknown }>)) {
      if (!f || typeof f.last !== 'string' || !isIsoDate(f.last)) throw bad(`the price file of ${y} has no last date`);
      if (last_bar === null || f.last > last_bar) last_bar = f.last;
    }
    return { ticker, data_through, last_bar };
  }

  /** A reference list (terminal-api /reference/{name}): tickers with type and sector, or brokers with name and type. */
  async reference(name: 'tickers'): Promise<TickerRef[]>;
  async reference(name: 'brokers'): Promise<BrokerRef[]>;
  async reference(name: 'tickers' | 'brokers'): Promise<TickerRef[] | BrokerRef[]> {
    if (name !== 'tickers' && name !== 'brokers') throw new TypeError('reference: tickers or brokers.');
    const what = `The ${name} reference`, j = await this.api('GET', `/reference/${name}`, undefined, what, name);
    if (typeof j.url !== 'string' || !/^https?:\/\//.test(j.url)) throw new DataError('DATA_INTEGRITY', `${what}: terminal-api answered no URL.`, name);
    if (!this.onBucket(j.url)) throw new DataError('DATA_INTEGRITY', `${what}: terminal-api answered a URL that is not on the bucket origin ${this.o.fileOrigin} (BACKTEST_FILE_ORIGIN).`, name);
    // no manifest gives a reference file's size: BACKTEST_MAX_FILE_BYTES caps the download and the inflated document
    const max = this.o.maxFileBytes;
    const a = await this.http(j.url, { method: 'GET' }, what, name, () => ({ bytes: max, error: () => new DataError('DATA_INTEGRITY', `${what} has more than ${max} bytes, the most one file may have.`, name, { max_file_bytes: max }) }));
    if (a.status !== 200) throw new DataError(a.status === 404 ? 'DATA_MISSING' : 'DATA_UNAVAILABLE', `${what}: the bucket answered ${a.status}.`, name, { status: a.status });
    const doc = await decodeColumnar(a.bytes, what, max);
    const keys = name === 'tickers' ? ['ticker', 'name', 'type', 'sector'] : ['code', 'name', 'type'];
    for (const k of keys) if (!doc.columns.includes(k)) throw new DataError('DATA_INTEGRITY', `${what}: column ${k} is missing.`, name);
    const c = keys.map(k => doc[k] as unknown[]), str = (v: unknown) => typeof v === 'string' ? v : null;
    return c[0].map((id, i) => {
      if (typeof id !== 'string' || !id) throw new DataError('DATA_INTEGRITY', `${what}: row ${i + 1} has no ${keys[0]}.`, name);
      return name === 'tickers' ? { ticker: id, name: str(c[1][i]), type: str(c[2][i]), sector: str(c[3][i]) } : { code: id, name: str(c[1][i]), type: str(c[2][i]) };
    }) as TickerRef[] | BrokerRef[];
  }
}

const byFile = (a: ReadFile, b: ReadFile) => a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : a.dataset < b.dataset ? -1 : a.dataset > b.dataset ? 1 : a.sha256 < b.sha256 ? -1 : a.sha256 > b.sha256 ? 1 : 0;
