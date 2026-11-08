/* The refresh: one rack publication -> the next snapshot (report TARGET ARCHITECTURE 6.5 "Worker refresh rules";
   MULTI-USER SCALE AND COST 6d.2, 6d.4; API CONTRACT 8.9 refresh caps, 8.12 terminal-api routes; TEST PLAN 10b.4).

   The thin terminal-api client (TerminalApi): GET /state (the publication and its xsection index; no grant, no quota),
   POST /xsection {names} (presigned URLs for the named files of the current publication; proxy key only; one audit row
   under REF), GET /manifest/{ticker} (rows and last date of the ticker's yearly price files; no grant). The backtest
   worker's TerminalClient cannot serve these (its api() is private, terminal.ts:414, and publication() keeps only three
   fields), and changing terminal.ts would change the Backtest's engine_version, so they are read here with the same
   rules: the gateway key only to terminal-api and never logged, network errors and 5xx retried with backoff, every body
   read as a stream under a cap, 404 DATA_MISSING, other failures DATA_UNAVAILABLE, a malformed answer DATA_INTEGRITY.
   The files themselves are downloaded, cached by sha256 and verified (sha256 and size, then inflated under
   SCREENER_MAX_INFLATED_BYTES) by TerminalClient.file and inflateVerified, on the builder thread.

   Rules (6.5 rules 1-5, in order):
   1. /state is read every POLL_MS (60 s) and acted on only when finished_at changes, never while a refresh runs; after
      a failed refresh of a publication the next try waits a backoff (60 s doubling to 16 min) unless another one arrives;
   2. the index must name every Phase 1 file (price, actions); an indexed size above SCREENER_MAX_FILE_BYTES, or files
      to download above SCREENER_MAX_REFRESH_BYTES in total, fail the refresh before any grant;
   3. when the index names exactly the files the replica holds (same sha256 for price and actions) and the reference
      file reads the same, nothing is downloaded, recomputed or swapped: only published_at and the state.json fields
      advance (6d.2 "skip the recompute");
   4. POST /xsection only for the files neither cache holds (a cached file is read without a grant: a restart with a warm
      disk cache grants nothing); its answer must name the publication /state named (finished_at, and each file's
      sha256 and size equal to the index): terminal-api runs two processes that each re-read state.json at most every
      60 s, so for up to a minute after a run the two can disagree; a skewed answer is asked again
      (SCREENER_DOWNLOAD_RETRIES times, SCREENER_RETRY_BASE_MS x 2^k apart) and then left to SKEW_RETRY_MS later,
      logged refresh_deferred, never a failure; every URL must be on SCREENER_FILE_ORIGIN;
   5. the builder thread downloads, verifies and decodes (snapshot.ts buildSnapshot: slices through priceSeries, every
      ticker in the reference file, IHSG present); then every ticker of the price file is checked against its
      /manifest (its rows = the sum of its yearly files' rows, its last date = their newest last), then the pre-warm,
      the digest, the install on every compute thread, the presets and the documents, and the swap, all-or-nothing:
      any failure keeps the previous snapshot serving, logs REFRESH_FAILED with the reason, and is retried (rule 1).
   EXEC-U4-WORKERS (user go 2026-11-02: "Jalankan U4 sekarang"): with a snapshot loaded, rule 1's poll pauses once no
   keyed request came for idleMs (SCREENER_IDLE_POLL_S): a poll is outbound traffic, and Railway puts a service to sleep
   only after minutes without any, so the poll alone kept the worker awake all day. The next keyed request (touch)
   resumes it at once with one poll; a worker woken from sleep starts afresh and loads the newest publication (start).
   While paused, a publication made meanwhile is seen on that first request, which is served from the snapshot held (the
   DATA_VERSION_PENDING rule of `latest` still applies to a page pinned to a newer version). With no snapshot loaded the
   poll never pauses. Logs refresh_poll_paused and refresh_poll_resumed.
   EXEC-SCREENER-FLOW-CANDLES P4 (user 2026-11-07: per-date broker files, worker limits unchanged, K1 window 60 sessions;
   verification/screener/P4_BROKER_DAYS.md section 3): beside the Phase 1 files the index may name broker days
   (broker-YYYY-MM-DD, broker.ts brokerWindow: the newest 60 by date), optional. Rule 2's per-file cap applies to them
   as to every file; within SCREENER_MAX_REFRESH_BYTES the Phase 1 downloads come first, then the broker days newest
   first (brokerPlan): a day the snapshot holds with the same sha256 is carried, one in the disk cache is read without a
   grant, the others are downloaded while they fit; from the first that does not fit the rest wait for a follow-up
   refresh of the same publication, which starts at once (FOLLOW_UP_MS, not after the poll) until the window is complete
   or nothing more fits. Rule 3 compares the broker days this refresh would hold (names and sha256) with the snapshot's
   too. Rule 4 asks /xsection in batches of at most XSECTION_MAX_NAMES (16, terminal-api MAX_XSECTION_NAMES).
   Logs: refresh {data_version, published_at, files, bytes, granted, cached, grant_ms, download_ms, decode_ms,
   check_ms, defaults_ms, install_ms, presets_ms, orphans, snapshot_digest, rss, broker_days {window, loaded, carried,
   cached, granted, missing, bytes, first, last, read, rows, dropped_tickers, dropped_rows, store_bytes}} (6.16; P4
   broker_days: days, except bytes, the gzip bytes of the broker days downloaded); REFRESH_FAILED adds the
   failure, integrity_failures (DATA_INTEGRITY failures since the start), keeping_previous and retry_in_ms. */
import { DataError } from '../../edge-bff/backtest/src/core/datafile.ts';
import type { FileEntry } from '../../edge-bff/backtest/src/core/datafile.ts';
import { isIsoDate } from '../../edge-bff/backtest/src/core/signals.ts';
import { fileOriginOf } from '../../backtest-worker/src/terminal.ts';
import type { TerminalClient, TickerReference } from '../../backtest-worker/src/terminal.ts';
import type { Limits } from './config.ts';
import { errorFields, log } from './log.ts';
import { PHASE1_FILES, PRICE_FILE, referenceHash } from './snapshot.ts';
import type { BrokerRef } from '../../edge-bff/screener/src/core/contract.ts';
import type { IndexEntry, PublicationState, ReadFile, SnapshotReference, TickerEntry } from './snapshot.ts';
import { brokerWindow } from './broker.ts';
import type { WindowDay } from './broker.ts';

export const API = '/api/terminal/v1';
export const PROXY_HEADER = 'x-terminal-proxy-key';
export const POLL_MS = 60_000;                 // report 6.5 rule 1
export const SKEW_RETRY_MS = 15_000;           // a skewed publication is tried again this much later (rule 4)
export const BACKOFF_MAX_STEPS = 4;            // 60 s, 120 s, 240 s, 480 s, 960 s at most (rule 1)
const NAME = /^[a-z0-9][a-z0-9_-]{0,31}$/;     // terminal-api XSECTION_NAME
export const XSECTION_MAX_NAMES = 16;          // terminal-api MAX_XSECTION_NAMES: names per /xsection call (P4 batches)
export const FOLLOW_UP_MS = 0;                 // P4: broker days that did not fit load on a refresh started at once

const sleep = (ms: number) => new Promise<void>(r => setTimeout(r, ms));

/* ---- the thin terminal-api client --------------------------------------------------------------------------------- */
export interface ApiOptions { url: string; proxyKey: string; retries: number; retryBaseMs: number; timeoutMs: number; maxBytes: number; concurrency: number; fetch?: typeof fetch }
export interface Grant { finished_at: string; expires_in_seconds: number | null; files: (IndexEntry & { name: string; url: string })[] }

class Gate {
  private free: number; private queue: (() => void)[] = [];
  constructor(n: number) { this.free = n }
  async run<T>(task: () => Promise<T>): Promise<T> {
    if (this.free > 0) this.free--; else await new Promise<void>(ok => this.queue.push(ok));
    try { return await task() } finally { const next = this.queue.shift(); if (next) next(); else this.free++ }
  }
}

export class TerminalApi {
  private o: ApiOptions; private fetch: typeof fetch; private gate: Gate;
  stats = { requests: 0, retries: 0 };
  constructor(o: ApiOptions) { this.o = { ...o, url: o.url.replace(/\/+$/, '') }; this.fetch = o.fetch ?? globalThis.fetch; this.gate = new Gate(o.concurrency) }
  get retries(): number { return this.o.retries }
  get retryBaseMs(): number { return this.o.retryBaseMs }

  /** One call with the retry rule (network errors and 5xx retried; any other status answered as it is). */
  private async call(method: 'GET' | 'POST', p: string, body: unknown, what: string, field?: string): Promise<any> {
    const headers: Record<string, string> = { [PROXY_HEADER]: this.o.proxyKey, accept: 'application/json' };
    if (body !== undefined) headers['content-type'] = 'application/json';
    for (let attempt = 0; ; attempt++) {
      let status = 0, text = '', failure = '';
      try {
        this.stats.requests++;
        ({ status, text } = await this.gate.run(async () => {
          const res = await this.fetch(this.o.url + API + p, { method, headers, body: body === undefined ? undefined : JSON.stringify(body), redirect: 'error', signal: AbortSignal.timeout(this.o.timeoutMs) });
          return { status: res.status, text: await readCapped(res, this.o.maxBytes, what, field) };
        }));
      } catch (e) { if (e instanceof DataError) throw e; failure = (e as Error)?.name || 'Error' }
      if (status && status < 500) {
        let j: any = null;
        try { j = text ? JSON.parse(text) : null } catch { /* below */ }
        if (status === 200) {
          if (!j || typeof j !== 'object') throw new DataError('DATA_INTEGRITY', `${what}: terminal-api answered something that is not JSON.`, field);
          return j;
        }
        const code = j && typeof j.error === 'string' ? j.error : null;
        throw new DataError(status === 404 ? 'DATA_MISSING' : 'DATA_UNAVAILABLE', `${what}: terminal-api answered ${status}${code ? ` (${code})` : ''}.`, field, { status, ...(code ? { upstream: code } : {}) });
      }
      if (attempt >= this.o.retries)
        throw new DataError('DATA_UNAVAILABLE', `${what} ${status ? `answered ${status}` : `could not be reached (${failure})`}${attempt ? ` after ${attempt + 1} tries` : ''}.`, field, status ? { status } : { network: failure });
      this.stats.retries++;
      log('info', 'terminal_retry', { what, attempt: attempt + 1, ...(status ? { status } : { error: failure }) });
      await sleep(this.o.retryBaseMs * 2 ** attempt);
    }
  }

  /** GET /state, checked (bucket.py STATE_FIELDS; xsection null before the publisher writes an index). */
  async state(): Promise<PublicationState> {
    const j = await this.call('GET', '/state', undefined, 'The publication state', 'state');
    const bad = (why: string) => new DataError('DATA_INTEGRITY', `terminal-api /state: ${why}.`, 'state');
    if (typeof j.finished_at !== 'string' || !j.finished_at) throw bad('no finished_at');
    const day = (v: unknown) => typeof v === 'string' && isIsoDate(v) ? v : null;
    let xsection: Record<string, IndexEntry> | null = null;
    if (j.xsection !== null && j.xsection !== undefined) {
      if (typeof j.xsection !== 'object' || Array.isArray(j.xsection)) throw bad('xsection is not an index');
      xsection = {};
      for (const [name, e] of Object.entries(j.xsection as Record<string, any>)) {
        if (!NAME.test(name) || !indexEntry(e)) throw bad(`the xsection entry ${JSON.stringify(name).slice(0, 40)} is not {key, sha256, bytes, rows, as_of}`);
        xsection[name] = { key: e.key, sha256: e.sha256, bytes: e.bytes, rows: e.rows, as_of: typeof e.as_of === 'string' ? e.as_of : null };
      }
    }
    const behind = j.broker_behind_sessions;
    return { finished_at: j.finished_at, price_through: day(j.price_through), broker_through: day(j.broker_through),
      broker_behind_sessions: Number.isSafeInteger(behind) && behind >= 0 ? behind : null, xsection };
  }
  /** POST /xsection {names}: presigned URLs (main.py xsection). */
  async xsection(names: readonly string[]): Promise<Grant> {
    const j = await this.call('POST', '/xsection', { names }, 'The cross-sectional files', 'xsection');
    const bad = (why: string) => new DataError('DATA_INTEGRITY', `terminal-api /xsection: ${why}.`, 'xsection');
    if (typeof j.finished_at !== 'string' || !Array.isArray(j.files)) throw bad('no finished_at or files');
    const files = j.files.map((f: any, k: number) => {
      if (!f || typeof f.name !== 'string' || typeof f.url !== 'string' || !/^https?:\/\//.test(f.url) || !indexEntry({ key: 'v1/xsection/x.0000000000000000.json.gz', ...f }))
        throw bad(`file ${k + 1} has no valid name, url, sha256, bytes or rows`);
      return { name: f.name, url: f.url, key: '', sha256: f.sha256, bytes: f.bytes, rows: f.rows, as_of: typeof f.as_of === 'string' ? f.as_of : null };
    });
    const ttl = j.expires_in_seconds;
    return { finished_at: j.finished_at, expires_in_seconds: typeof ttl === 'number' && Number.isFinite(ttl) ? ttl : null, files };
  }
  /** GET /reference/{name} (main.py reference): the presigned URL of a reference file and, when the publication's refs
      index names it, its sha256 and size (null otherwise). P5a reads `brokers` for the brokers' classification. */
  async referenceFile(name: string): Promise<{ url: string; sha256: string | null; bytes: number | null }> {
    const j = await this.call('GET', `/reference/${encodeURIComponent(name)}`, undefined, `The ${name} reference`, name);
    if (typeof j.url !== 'string' || !/^https?:\/\//.test(j.url)) throw new DataError('DATA_INTEGRITY', `terminal-api /reference/${name}: no URL.`, name);
    const sha = typeof j.sha256 === 'string' && /^[0-9a-f]{64}$/.test(j.sha256) ? j.sha256 : null, bytes = Number.isSafeInteger(j.bytes) && j.bytes > 0 ? j.bytes as number : null;
    return { url: j.url, sha256: sha, bytes };
  }
  /** GET /manifest/{ticker}: the rows and the newest last date of its yearly price files (null without price files). */
  async manifest(ticker: string): Promise<{ rows: number; last: string } | null> {
    const m = await this.call('GET', `/manifest/${encodeURIComponent(ticker)}`, undefined, `The manifest of ${ticker}`, ticker);
    const bad = (why: string) => new DataError('DATA_INTEGRITY', `terminal-api /manifest for ${ticker}: ${why}.`, ticker);
    if (m.ticker !== ticker || !m.datasets || typeof m.datasets !== 'object') throw bad(`not the manifest of ${ticker}`);
    const years = m.datasets.price?.years;
    if (!years || typeof years !== 'object' || Array.isArray(years)) return null;
    let rows = 0, last = '';
    for (const [y, f] of Object.entries(years as Record<string, any>)) {
      if (!f || !Number.isSafeInteger(f.rows) || typeof f.last !== 'string' || !isIsoDate(f.last)) throw bad(`the price file of ${y} has no rows or last date`);
      rows += f.rows; if (f.last > last) last = f.last;
    }
    return last ? { rows, last } : null;
  }
}
/** P4: whether the broker days a refresh would hold are those the snapshot holds (the same names and sha256). */
function sameDays(loaded: Record<string, string>, held: Held['broker']): boolean {
  const names = Object.keys(loaded);
  return names.length === Object.keys(held).length && names.every(n => held[n]?.sha256 === loaded[n]);
}
function indexEntry(e: any): boolean {
  return !!e && typeof e === 'object' && typeof e.key === 'string' && typeof e.sha256 === 'string' && /^[0-9a-f]{64}$/.test(e.sha256)
    && Number.isSafeInteger(e.bytes) && e.bytes >= 1 && Number.isSafeInteger(e.rows) && e.rows >= 0 && (e.as_of === null || e.as_of === undefined || typeof e.as_of === 'string');
}
async function readCapped(res: Response, cap: number, what: string, field?: string): Promise<string> {
  const declared = Number(res.headers.get('content-length'));
  const over = () => new DataError('DATA_UNAVAILABLE', `${what}: terminal-api answered more than ${cap} bytes.`, field);
  if (Number.isFinite(declared) && declared > cap) { await res.body?.cancel().catch(() => {}); throw over() }
  const reader = res.body?.getReader();
  if (!reader) return '';
  const parts: Uint8Array[] = []; let n = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    n += value.byteLength;
    if (n > cap) { await reader.cancel().catch(() => {}); throw over() }
    parts.push(value);
  }
  return Buffer.concat(parts).toString('utf8');
}

/* ---- the refresh ----------------------------------------------------------------------------------------------- */

/** What the replica holds (server.ts). P4: broker, the broker days its snapshot loaded (name -> sha256 and how many
    tickers were dropped from it for having no price), and brokerMissing, the days of its window it could not load. */
export interface Held {
  finished_at: string; files: Record<string, string>; refHash: string; price_data: string;
  broker: Record<string, { sha256: string; dropped: number }>; brokerMissing: number;
}
/** P4: the broker days one build reads (cached or granted, with their entries), carries from the held snapshot, and
    leaves missing (brokerPlan). */
export interface BrokerInput { read: { name: string; date: string; file: FileEntry }[]; carry: string[]; missing: number }
/** The parts of the app the refresh drives (server.ts implements them on the pool and the builder thread). */
export interface RefreshHost {
  held(): Held | null;
  /** download, verify and decode on a builder thread -> the staged snapshot's entries (for the cross-check) */
  build(input: { files: Record<ReadFile, FileEntry>; broker: BrokerInput; ref: SnapshotReference; state: PublicationState }): Promise<{ entries: TickerEntry[]; stats: Record<string, unknown> }>;
  /** pre-warm, digest, install, presets, documents, swap; throws to abort (nothing changes) */
  complete(input: { state: PublicationState; ref: SnapshotReference; files: Record<string, string> }): Promise<Record<string, unknown>>;
  /** the builder's work is dropped (a failure before complete() succeeded) */
  abandon(): void;
  /** rule 3: the same files and reference; published_at and the state fields advance (P4: and the window's missing days) */
  advance(state: PublicationState, broker: { missing: number }): void;
  /** the outcome of the latest publication changed (ready, failed_keeping_previous, or failed with no snapshot) */
  outcome(state: 'ready' | 'failed_keeping_previous' | 'failed', error: DataError | null): void;
}
/** A publication that cannot be read consistently yet (terminal-api's processes disagree): tried again soon. */
export class Deferred extends Error { constructor(reason: string) { super(reason); this.name = 'Deferred' } }

export class Refresher {
  api: TerminalApi; client: TerminalClient; host: RefreshHost; limits: Limits; fileOrigin: (u: string) => boolean;
  running = false;
  phase: 'loading' | 'refreshing' | 'idle' = 'loading';
  lastState: PublicationState | null = null;
  private stateAt = -Infinity;
  private failedFor: string | null = null; private failures = 0; private retryAt = 0;
  private timer: NodeJS.Timeout | null = null; private soon: NodeJS.Timeout | null = null;
  private checking: Promise<PublicationState | null> | null = null;
  pollMs: number;
  idleMs: number;
  private lastUse = performance.now(); private paused = false;
  /** P4: the publication whose missing broker days cannot be loaded by another refresh (nothing more fits) */
  private waitingFor: string | null = null;
  integrityFailures = 0;

  constructor(o: { api: TerminalApi; client: TerminalClient; host: RefreshHost; limits: Limits; fileOrigin: string; pollMs?: number; idleMs?: number }) {
    this.api = o.api; this.client = o.client; this.host = o.host; this.limits = o.limits; this.pollMs = o.pollMs ?? POLL_MS;
    this.idleMs = o.idleMs ?? 0;
    const f = fileOriginOf(o.fileOrigin);
    if (!f) throw new Error('Refresher: fileOrigin must be an origin pattern.');
    this.fileOrigin = f;
  }
  /** Polls now and every pollMs. */
  start(): void {
    this.tick();
    this.timer = setInterval(() => this.tick(), this.pollMs);
    this.timer.unref?.();
  }
  stop(): void { if (this.timer) clearInterval(this.timer); if (this.soon) clearTimeout(this.soon); this.timer = this.soon = null }
  private later(ms: number): void {
    if (this.soon) clearTimeout(this.soon);
    this.soon = setTimeout(() => { this.soon = null; this.tick() }, ms);
    this.soon.unref?.();
  }
  /** EXEC-U4-WORKERS: a keyed request came; a paused poll resumes with one poll at once */
  touch(): void {
    this.lastUse = performance.now();
    if (!this.paused) return;
    this.paused = false;
    log('info', 'refresh_poll_resumed', {});
    void this.tick();
  }
  /** One poll (never two at once). Resolves when it is done. */
  async tick(): Promise<void> {
    if (this.idleMs > 0 && this.host.held() && performance.now() - this.lastUse > this.idleMs) {
      if (!this.paused) { this.paused = true; log('info', 'refresh_poll_paused', { idle_s: Math.round(this.idleMs / 1000) }) }
      return;
    }
    if (this.running) return;
    this.running = true;
    try { await this.refresh() }
    catch (e) { log('error', 'refresh_crashed', errorFields(e, true)) }
    finally { this.running = false; if (this.phase === 'refreshing') this.phase = 'idle' }
  }
  /** The publication terminal-api names now, read again at most every minIntervalMs (a request pinned to a version the
      replica does not know asks whether a newer publication exists: DATA_VERSION_PENDING vs DATA_VERSION_CHANGED). */
  async latest(minIntervalMs: number): Promise<PublicationState | null> {
    if (performance.now() - this.stateAt < minIntervalMs) return this.lastState;
    return this.checking ??= (async () => {
      try { const s = await this.api.state(); this.lastState = s; this.stateAt = performance.now(); return s }
      catch { return this.lastState }
      finally { this.checking = null }
    })();
  }
  /** Whether the replica is behind the publication terminal-api names (a refresh pending, running or failed). */
  behind(): boolean {
    const held = this.host.held(), s = this.lastState;
    return !!s && (!held || s.finished_at !== held.finished_at);
  }

  private async refresh(): Promise<void> {
    let st: PublicationState;
    try { st = await this.api.state(); this.lastState = st; this.stateAt = performance.now() }
    catch (e) {
      log('warn', 'refresh_state_unavailable', errorFields(e));
      if (!this.host.held()) this.host.outcome('failed', e instanceof DataError ? e : new DataError('DATA_UNAVAILABLE', 'terminal-api /state could not be read.', 'state'));
      return;
    }
    const held = this.host.held();
    // the publication held: nothing to do, unless broker days of its window wait and another refresh can load some (P4)
    if (held && st.finished_at === held.finished_at && (held.brokerMissing === 0 || this.waitingFor === st.finished_at)) return;
    if (this.failedFor === st.finished_at && Date.now() < this.retryAt) return;
    this.phase = 'refreshing';
    const t0 = performance.now(), fields: Record<string, unknown> = { published_at: st.finished_at };
    let built = false;
    try {
      const index = st.xsection ?? {};
      for (const name of PHASE1_FILES)
        if (!index[name]) throw new DataError('DATA_UNAVAILABLE', `The publication of ${st.finished_at} indexes no ${name} cross-sectional file (indexed: ${Object.keys(index).join(', ') || 'none'}).`, name);
      const files: Record<string, string> = Object.fromEntries(PHASE1_FILES.map(n => [n, index[n].sha256]));
      const window = brokerWindow(index);
      // rule 2: the per-file cap, before any grant, on every file this refresh may read (P4: the window's broker days too)
      for (const name of [...PHASE1_FILES, ...window.map(w => w.name)]) {
        const e = index[name];
        if (e.bytes > this.limits.max_file_bytes)
          throw new DataError('DATA_INTEGRITY', `The ${name} file has ${e.bytes} bytes; SCREENER_MAX_FILE_BYTES allows ${this.limits.max_file_bytes}.`, name, { limit: 'file_bytes', allowed: this.limits.max_file_bytes, needed: e.bytes });
      }
      const cached: string[] = [], missing: string[] = [];
      for (const name of PHASE1_FILES) (await this.isCached(index[name]) ? cached : missing).push(name);
      const toDownload = missing.reduce((s, n) => s + index[n].bytes, 0);
      // P4: the broker days, newest first, within what the Phase 1 downloads leave of SCREENER_MAX_REFRESH_BYTES
      const plan = await this.brokerPlan(window, held, held?.files[PRICE_FILE] === files[PRICE_FILE], this.limits.max_refresh_bytes - toDownload);
      const loaded = [...plan.carried, ...plan.cached, ...plan.granted].map(w => w.date).sort();
      const days: Record<string, unknown> = { window: window.length, loaded: loaded.length, carried: plan.carried.length, cached: plan.cached.length,
        granted: plan.granted.length, missing: plan.missing.length, bytes: plan.bytes, first: loaded[0] ?? null, last: loaded[loaded.length - 1] ?? null };
      fields.broker_days = days;
      // rule 3: the same files (P4: the same broker days too) and the same reference file: keep the snapshot, advance
      // the publication
      let ref: SnapshotReference | null = null;
      if (held && PHASE1_FILES.every(n => held.files[n] === files[n]) && sameDays(plan.loaded, held.broker)) {
        if (st.finished_at === held.finished_at) {
          // a follow-up of the publication held: none of its missing broker days fits; they wait for the next publication
          this.waitingFor = st.finished_at;
          log('info', 'refresh_broker_waiting', { published_at: st.finished_at, broker_days: days, ms: Math.round(performance.now() - t0) });
          return;
        }
        ref = await this.reference();
        if (referenceHash(ref) === held.refHash) {
          this.host.advance(st, { missing: plan.missing.length });
          if (plan.missing.length) this.waitingFor = st.finished_at;
          this.succeeded();
          log('info', 'refresh_skipped', { published_at: st.finished_at, data_version: held.price_data, reason: 'same files and reference', broker_days: days, ms: Math.round(performance.now() - t0) });
          return;
        }
      }
      // rule 2: the refresh cap on the Phase 1 downloads (the broker days were planned within what they leave)
      if (toDownload > this.limits.max_refresh_bytes)
        throw new DataError('DATA_INTEGRITY', `The refresh would download ${toDownload} bytes; SCREENER_MAX_REFRESH_BYTES allows ${this.limits.max_refresh_bytes}.`, 'xsection', { limit: 'refresh_bytes', allowed: this.limits.max_refresh_bytes, needed: toDownload });
      Object.assign(fields, { files: PHASE1_FILES.length, bytes: PHASE1_FILES.reduce((s, n) => s + index[n].bytes, 0), cached, granted: missing });
      // rule 4: grant what the caches lack, from the publication /state named, in batches of XSECTION_MAX_NAMES
      const urls: Record<string, string> = {};
      const names = [...missing, ...plan.granted.map(w => w.name)];
      if (names.length) {
        const tg = performance.now();
        const grant = await this.grant(st, names);
        for (const f of grant.files) {
          if (!this.fileOrigin(f.url)) throw new DataError('DATA_INTEGRITY', `terminal-api /xsection answered a URL for ${f.name} that is not on the bucket origin (SCREENER_FILE_ORIGIN).`, f.name);
          urls[f.name] = f.url;
        }
        fields.grant_ms = Math.round(performance.now() - tg);
        fields.grants = Math.ceil(names.length / XSECTION_MAX_NAMES);
      }
      ref ??= await this.reference();
      const entry = (n: string): FileEntry => ({ url: urls[n] ?? '', sha256: index[n].sha256, bytes: index[n].bytes });
      // rule 5: build, check, pre-warm, install, swap
      built = true;
      const broker: BrokerInput = { read: [...plan.cached, ...plan.granted].map(w => ({ name: w.name, date: w.date, file: entry(w.name) })), carry: plan.carried.map(w => w.name), missing: plan.missing.length };
      const b = await this.host.build({ files: Object.fromEntries(PHASE1_FILES.map(n => [n, entry(n)])) as Record<ReadFile, FileEntry>, broker, ref, state: st });
      const { broker_days: builtDays, ...stats } = b.stats as Record<string, unknown> & { broker_days?: Record<string, unknown> };
      Object.assign(fields, stats); Object.assign(days, builtDays ?? {});
      const tc = performance.now();
      await this.crossCheck(b.entries);
      fields.check_ms = Math.round(performance.now() - tc);
      Object.assign(fields, await this.host.complete({ state: st, ref, files }));
      built = false;
      this.succeeded();
      log('info', 'refresh', { ...fields, ms: Math.round(performance.now() - t0), rss: process.memoryUsage().rss });
      // P4: the days that did not fit are loaded by a refresh started at once, not after the poll (until none fits)
      if (plan.missing.length) this.later(FOLLOW_UP_MS);
    } catch (e) {
      if (built) this.host.abandon();
      if (e instanceof Deferred) {
        log('warn', 'refresh_deferred', { published_at: st.finished_at, reason: e.message, retry_in_ms: SKEW_RETRY_MS });
        this.later(SKEW_RETRY_MS);
        return;
      }
      this.failed(st, e, fields, t0);
    }
  }
  /** P4: the window's broker days this refresh loads, newest first: a day the snapshot holds with the same sha256 is
      carried when reading it again would give the same rows (no ticker was dropped from it for having no price, or the
      price file is the same); a day in the disk cache is read without a grant; the others are downloaded while they fit
      in `budget` (SCREENER_MAX_REFRESH_BYTES less the Phase 1 downloads); from the first one that does not fit, the
      days left to download wait (missing). loaded: name -> sha256 of the days the snapshot will hold. */
  private async brokerPlan(window: (WindowDay & { entry: IndexEntry })[], held: Held | null, samePrice: boolean, budget: number) {
    const carried: WindowDay[] = [], cached: WindowDay[] = [], granted: WindowDay[] = [], missing: WindowDay[] = [];
    let full = false, bytes = 0;
    for (const w of window) {
      const h = held?.broker[w.name];
      if (h && h.sha256 === w.entry.sha256 && (h.dropped === 0 || samePrice)) { carried.push(w); continue }
      if (await this.isCached(w.entry)) { cached.push(w); continue }
      if (!full && bytes + w.entry.bytes <= budget) { granted.push(w); bytes += w.entry.bytes; continue }
      full = true; missing.push(w);
    }
    const loaded: Record<string, string> = Object.fromEntries([...carried, ...cached, ...granted].map(w => [w.name, w.entry.sha256]));
    return { carried, cached, granted, missing, bytes, loaded };
  }
  /** The reference the build reads: the tickers file, and (P5a) the brokers' classification (brokerClasses). */
  private async reference(): Promise<SnapshotReference> {
    const ref: SnapshotReference = await this.client.reference('tickers');
    const b = await this.brokerClasses();
    return b ? { ...ref, brokerClasses: b.classes, brokerList: b.list } : ref;
  }
  /** EXEC-SCREENER-FLOW-CANDLES P5a: the brokers' classification of the reference file `brokers` (code -> its
      `classification`, IDX_Broker_Profile; every row whose classification is a text, as the Terminal's live.ts reads it),
      for FL34. The file is read as every data file is (TerminalClient.file: sha256 and size, the disk cache) from a URL on
      the bucket origin; a publication whose refs index does not name it (no sha256) or a failure leaves it out (null,
      logged broker_classes_unavailable): FL34 is then REQUIRES_DATA, the refresh goes on. */
  /* EXEC-SCREENER-BROKER-PICK (user 2026-11-08): the same file's code, name and domicile too, for the page's broker list
     (catalog data.brokers); a file without a name column gives codes only */
  private async brokerClasses(): Promise<{ classes: Record<string, string>; list: BrokerRef[] } | null> {
    try {
      const r = await this.api.referenceFile('brokers');
      if (!r.sha256 || !r.bytes) { log('warn', 'broker_classes_unavailable', { reason: 'the publication does not index the brokers reference (no sha256)' }); return null }
      if (!this.fileOrigin(r.url)) throw new DataError('DATA_INTEGRITY', 'terminal-api /reference/brokers answered a URL that is not on the bucket origin (SCREENER_FILE_ORIGIN).', 'brokers');
      const { doc } = await this.client.file({ url: r.url, sha256: r.sha256, bytes: r.bytes }, 'The brokers reference', 'brokers');
      const code = doc.code as unknown[] | undefined, cls = doc.classification as unknown[] | undefined;
      if (!Array.isArray(code) || !Array.isArray(cls)) { log('warn', 'broker_classes_unavailable', { reason: 'the brokers reference has no code or classification column' }); return null }
      const out: Record<string, string> = {};
      for (let k = 0; k < code.length; k++) if (typeof code[k] === 'string' && code[k] && typeof cls[k] === 'string') out[code[k] as string] = cls[k] as string;
      const nm = (Array.isArray(doc.name) ? doc.name : []) as unknown[], ty = (Array.isArray(doc.type) ? doc.type : []) as unknown[];
      const list: BrokerRef[] = [];
      for (let k = 0; k < code.length; k++) if (typeof code[k] === 'string' && code[k])
        list.push({ code: code[k] as string, name: typeof nm[k] === 'string' ? nm[k] as string : '', ...(typeof ty[k] === 'string' ? { type: ty[k] as string } : {}) });
      return { classes: out, list };
    } catch (e) { log('warn', 'broker_classes_unavailable', errorFields(e)); return null }
  }
  private succeeded(): void { this.failedFor = null; this.failures = 0; this.retryAt = 0; this.host.outcome('ready', null) }
  private failed(st: PublicationState, e: unknown, fields: Record<string, unknown>, t0: number): void {
    const data = e instanceof DataError ? e : null;
    if (data?.code === 'DATA_INTEGRITY') this.integrityFailures++;
    this.failures = this.failedFor === st.finished_at ? this.failures + 1 : 1;
    this.failedFor = st.finished_at;
    const wait = this.pollMs * 2 ** Math.min(this.failures - 1, BACKOFF_MAX_STEPS);
    this.retryAt = Date.now() + wait;
    log('error', 'REFRESH_FAILED', { ...fields, ...errorFields(e, !data), field: data?.field ?? null, details: data?.details ?? null,
      integrity_failures: this.integrityFailures, keeping_previous: !!this.host.held(), retry_in_ms: wait, ms: Math.round(performance.now() - t0) });
    this.host.outcome(this.host.held() ? 'failed_keeping_previous' : 'failed', data ?? new DataError('DATA_UNAVAILABLE', 'The latest publication could not be loaded.', 'xsection'));
  }

  /** Whether the file is in the disk cache by sha256 (TerminalClient.cached over a one-file answer: memory, then disk). */
  private async isCached(e: IndexEntry): Promise<boolean> {
    return this.client.cached({ ticker: 'XSECTION', generated_at: null, granted_at: 0, expires_in_seconds: null,
      datasets: { price: { data_through: null, first_year: null, files: [{ url: '', sha256: e.sha256, bytes: e.bytes }] } } } as never);
  }
  /** POST /xsection for `names` in batches of at most XSECTION_MAX_NAMES (P4; terminal-api refuses more in one call),
      each held to the publication `st` names (rule 4). */
  private async grant(st: PublicationState, names: string[]): Promise<Grant> {
    const out: Grant = { finished_at: st.finished_at, expires_in_seconds: null, files: [] };
    for (let k = 0; k < names.length; k += XSECTION_MAX_NAMES) {
      const g = await this.grantBatch(st, names.slice(k, k + XSECTION_MAX_NAMES));
      out.files.push(...g.files);
      if (g.expires_in_seconds !== null) out.expires_in_seconds = Math.min(out.expires_in_seconds ?? Infinity, g.expires_in_seconds);
    }
    return out;
  }
  private async grantBatch(st: PublicationState, names: string[]): Promise<Grant> {
    const index = st.xsection ?? {};
    for (let attempt = 0; ; attempt++) {
      const g = await this.api.xsection(names);
      const skew = g.finished_at !== st.finished_at || names.some(n => {
        const f = g.files.find(x => x.name === n);
        return !f || f.sha256 !== index[n].sha256 || f.bytes !== index[n].bytes;
      });
      if (!skew) return g;
      log('warn', 'refresh_skew', { attempt: attempt + 1, state_finished_at: st.finished_at, xsection_finished_at: g.finished_at });
      if (attempt >= this.api.retries) throw new Deferred(`terminal-api /xsection answered the publication of ${g.finished_at}, /state names ${st.finished_at}`);
      await sleep(this.api.retryBaseMs * 2 ** attempt);
    }
  }
  /** Rule 5's cross-check: every ticker of the price file against its /manifest (rows and last date). */
  private async crossCheck(entries: TickerEntry[]): Promise<void> {
    const problems: string[] = [];
    await Promise.all(entries.map(async e => {
      const m = await this.api.manifest(e.t);
      if (!m) problems.push(`${e.t}: no price files in its manifest`);
      else if (m.rows !== e.rows || m.last !== e.last) problems.push(`${e.t}: the price file has ${e.rows} rows to ${e.last}, its manifest ${m.rows} rows to ${m.last}`);
    }));
    if (problems.length)
      throw new DataError('DATA_INTEGRITY', `${problems.length} ticker(s) of the price file disagree with their manifests: ${problems.slice(0, 5).join('; ')}${problems.length > 5 ? '; ...' : ''}.`, 'price', { mismatches: problems.length });
  }
}
