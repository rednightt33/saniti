/* The screener-worker's private HTTP API (report API CONTRACT 8.11; TARGET ARCHITECTURE 6.4-6.7, 6.16;
   MULTI-USER SCALE AND COST 6d.2-6d.6). edge-bff (app/screener.py ScreenerWorker) is its only caller, on the private
   network; the browser never reaches it.

   GET  /health        no key: {ok, versions, published_at, snapshot_age_seconds, refresh} (contract.ts WorkerHealth;
                       refresh 'loading' before the first snapshot, 'refreshing' while one is built, else the latest
                       publication's outcome)
   GET  /ready         no key (a Railway healthcheck sends no header): 200 {ready: true} only with a loaded snapshot,
                       else 503 SCREENER_NOT_READY with Retry-After
   every other route needs x-screener-worker-key (else 401 UNAUTHORIZED) and reads x-screener-owner (16 hex; the
   owner's lane; absent = one shared lane '-'):
   GET  /v1/catalog    the publication's catalog (catalog.ts), ETag; If-None-Match -> 304
   GET  /v1/universe   every listed stock's attributes and remarks, ETag
   POST /v1/run        RunRequest -> RunResponse (gzip); POST /v1/preview PreviewRequest -> PreviewResponse (gzip);
   POST /v1/counts     CountsRequest -> CountsResponse (gzip); POST /v1/validate {schema_version, definition} ->
                       {valid, definition_hash, normalized, versions}
   Versions (6d.4): data_version pins run, counts and preview to a snapshot: the current one, or the previous one for
   SCREENER_PREVIOUS_GRACE_S after a swap; a version older than both answers 409 DATA_VERSION_CHANGED; one the replica
   has not loaded yet (terminal-api names a newer publication) 409 DATA_VERSION_PENDING, which edge-bff retries.
   No snapshot: 503 SCREENER_NOT_READY with Retry-After while the first one loads; 424 DATA_INTEGRITY or
   DATA_UNAVAILABLE when the latest publication failed and none is held (8.8).
   Admission of a computing request (pool.ts header): result cache hit at once; else the per-request compute budget
   (422 compute_budget), the owner's budget (P33, 422 owner_cpu_budget), the queue (409 BUSY), the owner's lane.
   Answers are written once the request body is read to its end (the connection stays usable for edge-bff's pool); a
   caller that leaves before its answer cancels its work (8.11). Logs: one `http` line per request and one `run`,
   `preview` or `counts` line that explains it (6.16): stages with tickers in and out and ms, conditions with their
   source and the tickers evaluated, pruned, cache hits, queue, busy and total ms, payload bytes. */
import crypto from 'node:crypto';
import http from 'node:http';
import zlib from 'node:zlib';
import { pathToFileURL } from 'node:url';
import type { Availability, CatalogPreset, Definition, Grouping } from '../../edge-bff/screener/src/core/contract.ts';
import { WORKER_KEY_HEADER, WORKER_OWNER_HEADER, WORKER_OWNER_TAG } from '../../edge-bff/screener/src/core/contract.ts';
import { METRICS_CATALOG } from '../../edge-bff/screener/src/core/catalog.ts';
import type { MetricsCatalog, PresetDefinition } from '../../edge-bff/screener/src/core/catalog.ts';
import { tailLength } from '../../edge-bff/screener/src/core/metrics.ts';
import type { TickerBars } from '../../edge-bff/screener/src/core/metrics.ts';
import type { CostTracker } from '../../edge-bff/screener/src/core/plan.ts';
import { presetAvailability, presetDefinitions } from '../../edge-bff/screener/src/core/validate.ts';
import type { ValidateContext } from '../../edge-bff/screener/src/core/validate.ts';
import { ScreenerError } from '../../edge-bff/screener/src/core/errors.ts';
import { DataError } from '../../edge-bff/backtest/src/core/datafile.ts';
import { TerminalClient } from '../../backtest-worker/src/terminal.ts';
import type { TickerReference } from '../../backtest-worker/src/terminal.ts';
import { catalogDoc, metricAvailability, universeDoc } from './catalog.ts';
import type { Doc } from './catalog.ts';
import { cacheShare, describeConfig, loadConfig } from './config.ts';
import type { Config } from './config.ts';
import { HttpError, fromSerial, refuse, toApiError } from './errors.ts';
import { REPLICA, errorFields, log } from './log.ts';
import { OwnerBudget, Pool, SYSTEM, TaskFailed, ThreadStopped } from './pool.ts';
import type { ComputeThread } from './pool.ts';
import type { PreviewOutcome, PreviewTask } from './preview.ts';
import { Refresher, TerminalApi } from './refresh.ts';
import type { Held, RefreshHost } from './refresh.ts';
import { countsEnvelope, estimateCost, newCostTracker, normalize, previewEnvelope, resultKey, runEnvelope, validateEnvelope } from './run.ts';
import type { CountsEntryOut, CountsTask, Envelope, Estimate, RunOptionsN, RunOutcome, RunTask } from './run.ts';
import { groupingsOf, materialize, referenceHash } from './snapshot.ts';
import type { BuildStats, SnapshotDesc, TickerEntry } from './snapshot.ts';
import type { BuildTask } from './thread.ts';
import { ENGINE_VERSION, REGISTRY_VERSION, SCREENER_REGISTRY_VERSION, checkStartup } from './version.ts';

export const LOADING_RETRY_SECONDS = 5;      // Retry-After while the first snapshot loads (a hint, not a limit)
export const PENDING_CHECK_MS = 5_000;       // an unknown data_version re-reads /state at most this often
const GZIP_MIN_BYTES = 1024;
const NO_OPTIONS: RunOptionsN = { exhaustive: false, explain: false };

/** One snapshot as the HTTP thread holds it. */
export interface Snap {
  sid: string; desc: SnapshotDesc; price_data: string; finished_at: string; files: Record<string, string>; refHash: string;
  vctx: ValidateContext; pinned: Set<string>; position: Map<string, number>; index: TickerBars;
  groupings: Grouping[]; availability: Map<string, { availability: Availability; reason: string | null }>;
  presets: CatalogPreset[]; catalog: Doc; universe: Doc; expiresAt: number | null;
}

/* ---- the main thread's half of the engine (the worker's tests replace it; production uses run.ts and the core) ---- */
export interface Engine {
  normalize(definition: unknown, snap: Snap, field?: string): Promise<{ normalized: Definition; hash: string }>;
  estimate(def: Definition, snap: Snap, only?: string): Estimate;
  observe(list: RunOutcome['observe']): void;
  validateContext(desc: SnapshotDesc, groupings: Grouping[], metrics: MetricsCatalog, availability: Snap['availability']): ValidateContext;
}
export function coreEngine(cfg: Config): Engine {
  const tracker: CostTracker = newCostTracker();
  const env = { capBudgetMs: cfg.limits.cap_budget_ms, withinMax: cfg.limits.within_max };
  return {
    normalize: (definition, snap, field) => normalize(definition, snap.vctx, field),
    estimate: (def, snap, only) => estimateCost(def, snap, tracker, env, only),
    observe(list) { for (const o of list) tracker.observe(o.key, o.ms, o.bars, o.length) },
    validateContext: (desc, groupings, metrics, availability) => ({
      limits: { max_conditions: cfg.limits.max_conditions, max_metric_filters: cfg.limits.max_metric_filters, within_max: cfg.limits.within_max },
      capBudgetMs: cfg.limits.cap_budget_ms, tickers: new Set(desc.rows.map(r => r.ticker)), groupings, metrics, availability,
    }),
  };
}

/* ---- the result cache (8.10; 6d.2: keyed by the publication, versions and definition, nothing of the owner) ----- */
interface Cached { sid: string; gzip: Uint8Array; etag: string; bytes: number; pinned: boolean }
export class ResultCache {
  private map = new Map<string, Cached>(); private lru = 0; private budget: number;
  hits = 0; misses = 0;
  constructor(budget: number) { this.budget = budget }
  get(key: string): Cached | undefined {
    const e = this.map.get(key);
    if (!e) { this.misses++; return undefined }
    this.hits++;
    if (!e.pinned) { this.map.delete(key); this.map.set(key, e) }
    return e;
  }
  /** pinned: the publication's own results (the presets), never evicted, dropped with their snapshot. */
  set(key: string, sid: string, gzip: Uint8Array, etag: string, pinned = false): void {
    const bytes = gzip.byteLength + key.length + 64;
    if (!pinned && bytes > this.budget) return;
    this.delete(key);
    this.map.set(key, { sid, gzip, etag, bytes, pinned });
    if (!pinned) {
      this.lru += bytes;
      for (const [k, e] of this.map) { if (this.lru <= this.budget) break; if (!e.pinned) { this.map.delete(k); this.lru -= e.bytes } }
    }
  }
  delete(key: string): void { const e = this.map.get(key); if (e) { this.map.delete(key); if (!e.pinned) this.lru -= e.bytes } }
  dropSnapshot(sid: string): void { for (const [k, e] of [...this.map]) if (e.sid === sid) this.delete(k) }
  get size(): { entries: number; lru_bytes: number } { return { entries: this.map.size, lru_bytes: this.lru } }
}

/* ---- HTTP helpers ------------------------------------------------------------------------------------------------- */
const sameKey = (given: string | string[] | undefined, key: Buffer) => {
  if (typeof given !== 'string') return false;
  const g = Buffer.from(given);
  return g.length === key.length && crypto.timingSafeEqual(g, key);
};
const acceptsGzip = (req: http.IncomingMessage) => /\bgzip\b/.test(String(req.headers['accept-encoding'] ?? ''));
function sendJson(res: http.ServerResponse, status: number, body: unknown, headers: Record<string, string> = {}): void {
  const b = Buffer.from(JSON.stringify(body));
  res.writeHead(status, { 'content-type': 'application/json', 'content-length': String(b.length), 'cache-control': 'no-store', ...headers });
  res.end(b);
}
/** A gzip answer as it is, or inflated for a caller that takes no gzip. */
function sendGzip(req: http.IncomingMessage, res: http.ServerResponse, gz: Uint8Array, etag: string): void {
  const base = { 'content-type': 'application/json', 'cache-control': 'no-store', etag };
  if (acceptsGzip(req)) { res.writeHead(200, { ...base, 'content-encoding': 'gzip', 'content-length': String(gz.byteLength) }); res.end(gz); return }
  const plain = zlib.gunzipSync(gz);
  res.writeHead(200, { ...base, 'content-length': String(plain.byteLength) }); res.end(plain);
}
function sendDoc(req: http.IncomingMessage, res: http.ServerResponse, d: Doc): void {
  const inm = String(req.headers['if-none-match'] ?? '');
  if (inm && inm.split(',').some(t => { const x = t.trim(); return x === '*' || x.replace(/^W\//, '') === d.etag })) { res.writeHead(304, { etag: d.etag, 'cache-control': 'no-store' }); res.end(); return }
  if (acceptsGzip(req) && d.json.byteLength >= GZIP_MIN_BYTES) { res.writeHead(200, { 'content-type': 'application/json', 'content-encoding': 'gzip', 'content-length': String(d.gzip.byteLength), etag: d.etag, 'cache-control': 'no-store' }); res.end(d.gzip); return }
  res.writeHead(200, { 'content-type': 'application/json', 'content-length': String(d.json.byteLength), etag: d.etag, 'cache-control': 'no-store' });
  res.end(d.json);
}
function parseJson(body: Buffer | null): unknown {
  const text = body ? body.toString('utf8') : '';
  try { return text ? JSON.parse(text) : null } catch { throw refuse('INVALID_INPUT', 'The request body is not JSON.', 'body') }
}
const budgetRefusal = (what: string, e: Estimate, max: number) => refuse('LIMIT_EXCEEDED',
  `This ${what} is predicted to need ${e.needed_ms} ms of compute, above the ${max} ms budget${e.costliest ? `; the costliest condition is ${e.costliest}` : ''}. Use default parameters, shorter lengths, fewer custom conditions or a narrower universe.`,
  undefined, { limit: 'compute_budget', allowed: max, needed: e.needed_ms, ...(e.costliest ? { costliest: e.costliest } : {}) });

export interface AppOptions {
  engine?: Engine;                       // tests
  metrics?: MetricsCatalog; presets?: PresetDefinition[];
  pollMs?: number;
  now?: () => number;
}
export interface WorkerApp {
  server: http.Server; pool: Pool; refresher: Refresher; results: ResultCache; budget: OwnerBudget;
  state(): { current: Snap | null; previous: Snap | null; outcome: string };
  listen(port?: number, host?: string): Promise<number>;
  start(): void;
  close(): Promise<void>;
}

export function createApp(cfg: Config, opts: AppOptions = {}): WorkerApp {
  const engine = opts.engine ?? coreEngine(cfg);
  const metrics = opts.metrics ?? METRICS_CATALOG;
  const presetDefs: PresetDefinition[] = [...(opts.presets ?? presetDefinitions())];
  const now = opts.now ?? Date.now;
  const L = cfg.limits, TAIL = tailLength(L.within_max);
  const env = { capBudgetMs: L.cap_budget_ms, withinMax: L.within_max, maxResponseBytes: L.max_response_bytes };
  const { fetch: _f, log: _l, ...terminal } = cfg.terminal;
  const script = new URL('./thread.ts', import.meta.url);
  const budget = new OwnerBudget(L.owner_cpu_ms, now);
  const pool = new Pool({ threads: cfg.threads, queue: L.queue, ownerInflight: L.owner_inflight, quantumMs: L.max_cpu_ms / 4, script, data: { env, terminal: null }, budget });
  const results = new ResultCache(cacheShare(cfg));
  const counts = new Map<string, { match_count: number; near_count: number; sid: string }>();
  const key = Buffer.from(cfg.workerKey);
  const engineVersions = { screener_engine: ENGINE_VERSION, registry: REGISTRY_VERSION, screener_registry: SCREENER_REGISTRY_VERSION };
  const client = new TerminalClient({ ...cfg.terminal, log: (event, fields) => log('info', event, { thread: 'http', ...fields }) });
  const api = new TerminalApi({ url: cfg.terminal.url, proxyKey: cfg.terminal.proxyKey, retries: cfg.terminal.retries, retryBaseMs: cfg.terminal.retryBaseMs,
    timeoutMs: cfg.terminal.timeoutMs, maxBytes: cfg.terminal.maxFileBytes, concurrency: cfg.terminal.concurrency });

  let current: Snap | null = null, previous: Snap | null = null;
  let outcome: 'ready' | 'failed_keeping_previous' | 'failed' | 'loading' = 'loading';
  let failure: DataError | null = null;
  const retired = new Set<string>();             // price_data of snapshots dropped: older than any held (CHANGED)
  let graceTimer: NodeJS.Timeout | null = null;
  const countsKey = (s: Snap, hash: string) => resultKey(s.desc, hash, NO_OPTIONS, 'counts');

  /* ---- the refresh host (refresh.ts drives it) ------------------------------------------------------------------ */
  /** A builder thread's failure as the error it was: a file or snapshot problem is the DataError the refresh classifies
      (DATA_INTEGRITY keeps the previous snapshot and is reported as such; anything else is DATA_UNAVAILABLE). */
  const builderError = (e: unknown): unknown => {
    if (!(e instanceof TaskFailed)) return e;
    const x = e.serial.error;
    if (x.code === 'DATA_INTEGRITY' || x.code === 'DATA_UNAVAILABLE' || x.code === 'DATA_MISSING') return new DataError(x.code, x.message ?? x.code, x.field, x.details);
    return fromSerial(e.serial);
  };
  const onBuilder = async <T>(work: () => Promise<T>): Promise<T> => { try { return await work() } catch (e) { throw builderError(e) } };
  let builder: ComputeThread | null = null, staged: { desc: SnapshotDesc; entries: TickerEntry[]; stats: BuildStats; ref: TickerReference } | null = null;
  const lruBytes = cacheShare(cfg);
  const host: RefreshHost = {
    held: (): Held | null => current && { finished_at: current.finished_at, files: current.files, refHash: current.refHash, price_data: current.price_data },
    async build(input) {
      builder = pool.builder('builder', { role: 'builder', env, terminal });
      const task: BuildTask = { kind: 'build', files: input.files, ref: input.ref, state: input.state, engine: engineVersions, tailLength: TAIL, presets: presetDefs };
      const { done } = await builder.run(task);
      const out = await onBuilder(() => done) as { desc: SnapshotDesc; entries: TickerEntry[]; stats: BuildStats; download_ms: number; decode_ms: number; download_bytes: number };
      staged = { desc: out.desc, entries: out.entries, stats: out.stats, ref: input.ref };
      const st = out.stats;
      return { entries: out.entries, stats: { download_ms: out.download_ms, decode_ms: out.decode_ms, downloaded_bytes: out.download_bytes, tickers: st.tickers, stocks: st.stocks,
        bars: st.bars, dropped_rows: st.dropped, no_price: st.no_price, actions: st.actions, pinned_series: st.series,
        pinned_skipped: st.skipped.length, pinned_skipped_first: st.skipped.slice(0, 3) } };
    },
    async complete(input) {
      if (!staged || !builder) throw new Error('complete: nothing staged');
      const { desc, ref } = staged, b = builder, fields: Record<string, unknown> = { data_version: desc.versions.price_data, orphans: 0 };
      // pre-warm: the builder alone while a snapshot serves; at a cold start the compute threads with it (6d.4)
      const t0 = performance.now();
      const workers: ComputeThread[] = current ? [b] : [b, ...pool.threads];
      const T = desc.tickers.length, size = Math.max(1, Math.ceil(T / (workers.length * 4))), chunks: [number, number][] = [];
      for (let a = 0; a < T; a += size) chunks.push([a, Math.min(T, a + size)]);
      await Promise.all(workers.map(async w => {
        for (let c = chunks.shift(); c; c = chunks.shift()) { const { done } = await w.run({ kind: 'prewarm', desc, from: c[0], to: c[1] }); await onBuilder(() => done) }
      }));
      fields.defaults_ms = Math.round(performance.now() - t0);
      const { done } = await b.run({ kind: 'digest', desc });
      desc.digest = ((await done) as { digest: string }).digest;
      fields.snapshot_digest = desc.digest;
      await b.kill(); builder = null;
      // install everywhere (all-or-nothing), then the HTTP thread's view, the presets and the documents, then the swap
      const ti = performance.now();
      await pool.install(desc.sid, desc, lruBytes);
      fields.install_ms = Math.round(performance.now() - ti);
      try {
        const groupings = groupingsOf(ref), availability = metricAvailability(metrics, input.state.xsection);
        const snap: Snap = {
          sid: desc.sid, desc, price_data: desc.versions.price_data, finished_at: input.state.finished_at, files: input.files, refHash: referenceHash(ref),
          vctx: engine.validateContext(desc, groupings, metrics, availability), pinned: new Set(desc.series.map(s => s.key)),
          position: new Map(desc.tickers.map((t, j) => [t, j])), index: materialize(desc, desc.index), groupings, availability,
          presets: [], catalog: null as unknown as Doc, universe: universeDoc(desc), expiresAt: null,
        };
        const tp = performance.now();
        snap.presets = await presets(snap);
        fields.presets_ms = Math.round(performance.now() - tp);
        snap.catalog = catalogDoc({ desc, refresh: 'ready', limits: L, metrics, availability, groupings, presets: snap.presets });
        fields.catalog_bytes = snap.catalog.json.byteLength; fields.universe_bytes = snap.universe.json.byteLength;
        swap(snap);
      } catch (e) { pool.drop(desc.sid); results.dropSnapshot(desc.sid); throw e }
      staged = null;
      return fields;
    },
    abandon() { if (builder) builder.kill().catch(() => {}); builder = null; staged = null },
    advance(st) {
      if (!current) return;
      current.finished_at = st.finished_at;
      current.desc.data = { ...current.desc.data, published_at: st.finished_at, price_through: st.price_through ?? current.desc.data.price_through, broker_behind_sessions: st.broker_behind_sessions };
      rebuildDocs(current);
    },
    outcome(state, error) {
      const before = outcome;
      outcome = state; failure = error;
      if (current && before !== state && (state === 'ready' || state === 'failed_keeping_previous')) rebuildDocs(current);
    },
  };
  function rebuildDocs(s: Snap): void {
    s.catalog = catalogDoc({ desc: s.desc, refresh: outcome === 'failed_keeping_previous' ? 'failed_keeping_previous' : 'ready', limits: L, metrics, availability: s.availability, groupings: s.groupings, presets: s.presets });
    s.universe = universeDoc(s.desc);
  }
  /** The swap (6.5 rule 5, 6d.4 rule 2): the new snapshot serves; the one it replaces serves requests pinned to it for
      SCREENER_PREVIOUS_GRACE_S; an older previous one is dropped at once. */
  function swap(s: Snap): void {
    const old = current;
    if (previous) retire(previous);
    current = s; outcome = 'ready'; failure = null;
    if (old) {
      if (old.price_data === s.price_data) retire(old);    // same price_data (actions or reference changed): nothing to pin
      else {
        old.expiresAt = now() + L.previous_grace_s * 1000; previous = old;
        if (graceTimer) clearTimeout(graceTimer);
        graceTimer = setTimeout(() => { if (previous === old) retire(old) }, L.previous_grace_s * 1000);
        graceTimer.unref?.();
      }
    }
    log('info', 'swap', { data_version: s.price_data, published_at: s.finished_at, sid: s.sid, previous: previous?.price_data ?? null, grace_s: L.previous_grace_s });
  }
  function retire(s: Snap): void {
    pool.drop(s.sid); results.dropSnapshot(s.sid);
    for (const [k, v] of counts) if (v.sid === s.sid) counts.delete(k);
    if (s.price_data !== current?.price_data) retired.add(s.price_data);
    if (previous === s) previous = null;
  }
  /** Each preset's availability (validate.ts presetAvailability), and for an available one its match and near counts and
      its full result kept pinned in the result cache (6.7, 6c.4), computed on the staged snapshot in the system lane
      before the swap. */
  async function presets(s: Snap): Promise<CatalogPreset[]> {
    return Promise.all(presetDefs.map(async (p): Promise<CatalogPreset> => {
      const base = { id: p.id, category: p.category, name: p.name, why: p.why, definition: p.definition, ...(p.view ? { view: p.view } : {}) };
      const a = presetAvailability(p, s.availability, metrics);
      if (a.availability !== 'AVAILABLE') return { ...base, availability: a.availability, reason: a.reason, match_count: null, near_count: null, unavailable_legs: a.unavailable_legs };
      try {
        const n = await engine.normalize(p.definition, s, `presets.${p.id}`);
        const o = await compute(s, n.normalized, n.hash, NO_OPTIONS, SYSTEM, null, null, performance.now() + Math.max(L.deadline_ms, 60_000), true);
        return { ...base, availability: 'AVAILABLE', reason: null, match_count: o.match_count, near_count: o.near_count, unavailable_legs: [] };
      } catch (e) {
        log('error', 'preset_failed', { preset: p.id, ...errorFields(e, !(e instanceof ScreenerError)) });
        return { ...base, availability: 'AVAILABLE', reason: null, match_count: null, near_count: null, unavailable_legs: [] };
      }
    }));
  }

  /* ---- versions (6d.4) ------------------------------------------------------------------------------------------ */
  function notReady(): ScreenerError {
    if (outcome === 'failed' && failure) {
      const integrity = failure.code === 'DATA_INTEGRITY';
      return refuse(integrity ? 'DATA_INTEGRITY' : 'DATA_UNAVAILABLE', integrity
        ? 'The latest publication failed its checks and no earlier one is loaded; it retries at the next publication.'
        : 'No published data is loaded yet; it loads after the next publication or within minutes of a restart; try again later.');
    }
    return refuse('SCREENER_NOT_READY', `The screener is loading the published data; retry in ${LOADING_RETRY_SECONDS} s.`, undefined, { retry_after_seconds: LOADING_RETRY_SECONDS });
  }
  async function pinned(version: string | null): Promise<Snap> {
    if (!current) throw notReady();
    if (version === null || version === current.price_data) return current;
    if (previous && version === previous.price_data && previous.expiresAt !== null && now() < previous.expiresAt) return previous;
    if (!retired.has(version) && previous?.price_data !== version) {
      await refresher.latest(PENDING_CHECK_MS);
      if (refresher.behind()) throw refuse('DATA_VERSION_PENDING', 'This replica has not loaded the publication the page shows yet; ask again shortly.', 'data_version');
    }
    throw refuse('DATA_VERSION_CHANGED', 'New data was published since the page loaded its catalog: read the catalog again and run the screen on it.', 'data_version');
  }

  /* ---- compute ---------------------------------------------------------------------------------------------- */
  interface Computed { gzip: Uint8Array; etag: string; match_count: number; near_count: number; cache_hit: boolean; outcome: RunOutcome | null; queue_ms: number; predicted_ms: number }
  /** One run (or a preset's) on a snapshot: the result cache, the budgets, the owner's lane (pool.ts). */
  async function compute(s: Snap, def: Definition, hash: string, options: RunOptionsN, owner: string, order: Envelope['client_order'], res: http.ServerResponse | null, deadlineAt: number, system = false): Promise<Computed> {
    const k = resultKey(s.desc, hash, options);
    const hit = results.get(k);
    const c = counts.get(countsKey(s, hash));
    if (hit && c) return { gzip: hit.gzip, etag: hit.etag, match_count: c.match_count, near_count: c.near_count, cache_hit: true, outcome: null, queue_ms: 0, predicted_ms: 0 };
    const e = engine.estimate(def, s);
    if (!system && e.needed_ms > L.max_cpu_ms) throw budgetRefusal('screen', e, L.max_cpu_ms);
    if (!system) budget.check(owner, pool.reserved(owner), e.needed_ms);
    const task: RunTask = { kind: 'run', sid: s.sid, definition: def, hash, options, queue_ms: 0, s0_ms: e.s0_ms, versions: s.desc.versions, data: s.desc.data };
    const job = pool.submit({ owner, kind: system ? 'system' : 'run', page: order?.page ?? null, order: order?.seq ?? null, cost: e.needed_ms, deadlineAt, task });
    res?.once('close', () => { if (!res.writableFinished) job.cancel() });
    const { outcome: o, queue_ms } = await job.promise;
    const out = o as RunOutcome;
    budget.record(owner, out.busy_ms);
    engine.observe(out.observe);
    if (out.gzip && out.etag) results.set(k, s.sid, out.gzip, out.etag, system);
    counts.set(countsKey(s, hash), { match_count: out.match_count, near_count: out.near_count, sid: s.sid });
    return { gzip: out.gzip as Uint8Array, etag: out.etag as string, match_count: out.match_count, near_count: out.near_count, cache_hit: false, outcome: out, queue_ms, predicted_ms: e.needed_ms };
  }

  /* ---- routes ------------------------------------------------------------------------------------------------- */
  function health() {
    const refresh = refresher.phase === 'refreshing' ? 'refreshing' : !current ? 'loading' : outcome === 'failed_keeping_previous' ? 'failed_keeping_previous' : 'ready';
    const published = current?.finished_at ?? null;
    return { ok: true, versions: current ? { ...current.desc.versions } : null, published_at: published,
      snapshot_age_seconds: published ? Math.max(0, Math.round((now() - Date.parse(published)) / 1000)) : null, refresh };
  }
  function ownerOf(req: http.IncomingMessage): string {
    const tag = req.headers[WORKER_OWNER_HEADER];
    if (tag === undefined) return '-';
    if (typeof tag !== 'string' || !WORKER_OWNER_TAG.test(tag)) throw refuse('INVALID_INPUT', `${WORKER_OWNER_HEADER} must be 16 lowercase hex characters (the first 16 hex of HMAC-SHA256(SCREENER_WORKER_KEY, owner_key)).`, WORKER_OWNER_HEADER);
    return tag;
  }
  async function route(req: http.IncomingMessage, res: http.ServerResponse, path: string, raw: Buffer | null, arrived: number): Promise<void> {
    const method = req.method ?? 'GET';
    const allow = (m: string) => { if (method !== m) throw new HttpError(405, 'METHOD_NOT_ALLOWED', `Use ${m}.`) };
    if (path === '/health') { allow('GET'); return sendJson(res, 200, health()) }
    if (path === '/ready') {
      allow('GET');
      if (current) return sendJson(res, 200, { ready: true });
      return sendJson(res, 503, { ready: false, retry_after_seconds: LOADING_RETRY_SECONDS, error: { code: 'SCREENER_NOT_READY', message: 'No snapshot is loaded yet.' } }, { 'retry-after': String(LOADING_RETRY_SECONDS) });
    }
    if (!sameKey(req.headers[WORKER_KEY_HEADER], key)) throw new HttpError(401, 'UNAUTHORIZED');
    const owner = ownerOf(req), deadlineAt = arrived + L.deadline_ms;
    if (path === '/v1/catalog') { allow('GET'); if (!current) throw notReady(); return sendDoc(req, res, current.catalog) }
    if (path === '/v1/universe') { allow('GET'); if (!current) throw notReady(); return sendDoc(req, res, current.universe) }
    if (path === '/v1/validate') {
      allow('POST');
      const e = validateEnvelope(parseJson(raw));
      const s = current;
      if (!s) throw notReady();
      const n = await engine.normalize(e.definition, s);
      // versions (additive): the registries the definition was checked against, so edge-bff stores them with the item
      return sendJson(res, 200, { valid: true, definition_hash: n.hash, normalized: n.normalized, versions: { ...s.desc.versions } });
    }
    if (path === '/v1/run') {
      allow('POST');
      const e = runEnvelope(parseJson(raw));
      const s = await pinned(e.data_version);
      const n = await engine.normalize(e.definition, s);
      let r: Computed | null = null, status = 'ok';
      try {
        r = await compute(s, n.normalized, n.hash, e.options, owner, e.client_order, res, deadlineAt);
        if (res.destroyed) { status = 'caller_left'; return }
        sendGzip(req, res, r.gzip, r.etag);
      } catch (x) { status = (x as Error)?.name === 'CallerLeft' ? 'caller_left' : toApiError(x).error.code; throw x }
      finally { runLog(s, n.hash, owner, n.normalized, r, performance.now() - arrived, status) }
      return;
    }
    if (path === '/v1/preview') {
      allow('POST');
      const e = previewEnvelope(parseJson(raw));
      const s = await pinned(e.data_version);
      const n = await engine.normalize(e.definition, s);
      const ticker = e.ticker as string;
      if (!s.position.has(ticker) || !s.desc.rows.some(r => r.ticker === ticker)) throw refuse('INVALID_INPUT', `${ticker} is not a listed stock of this publication; preview a ticker of GET universe.`, 'ticker');
      const k = resultKey(s.desc, n.hash, e.options, `preview:${ticker}`), hit = results.get(k);
      const line = (o: Record<string, unknown>) => log('info', 'preview', { definition_hash: n.hash, data_version: s.price_data, ticker, owner_tag: owner, replica: REPLICA, ...o, total_ms: Math.round(performance.now() - arrived) });
      if (hit) { sendGzip(req, res, hit.gzip, hit.etag); line({ cache_hit: true }); return }
      const est = engine.estimate(n.normalized, s, ticker);
      if (est.needed_ms > L.max_cpu_ms) throw budgetRefusal('preview', est, L.max_cpu_ms);
      budget.check(owner, pool.reserved(owner), est.needed_ms);
      const task: PreviewTask = { kind: 'preview', sid: s.sid, definition: n.normalized, ticker, periods: metrics.periods ?? null, versions: { ...s.desc.versions }, data: { ...s.desc.data } };
      const job = pool.submit({ owner, kind: 'preview', page: e.client_order?.page ?? null, order: e.client_order?.seq ?? null, cost: est.needed_ms, deadlineAt, task });
      res.once('close', () => { if (!res.writableFinished) job.cancel() });
      const { outcome: o, queue_ms } = await job.promise;
      const out = o as PreviewOutcome;
      budget.record(owner, out.busy_ms);
      results.set(k, s.sid, out.gzip, out.etag);
      if (res.destroyed) return;
      sendGzip(req, res, out.gzip, out.etag);
      line({ cache_hit: false, status: out.status, predicted_ms: est.needed_ms, queue_ms: Math.round(queue_ms), busy_ms: out.busy_ms, payload_bytes: out.gzip.byteLength });
      return;
    }
    if (path === '/v1/counts') {
      allow('POST');
      const e = countsEnvelope(parseJson(raw), L.max_counts);
      const s = await pinned(e.data_version);
      const defs = e.definitions ?? [];
      const entries: (CountsEntryOut | null)[] = [], items: CountsTask['items'] = [];
      let cost = 0, hits = 0;
      for (const [k, d] of defs.entries()) {
        try {
          const n = await engine.normalize(d.definition, s, `definitions[${k}].definition`);
          const c = counts.get(countsKey(s, n.hash));
          if (c) { hits++; entries.push({ item_id: d.item_id, match_count: c.match_count, near_count: c.near_count, busy_ms: 0 }); continue }
          const est = engine.estimate(n.normalized, s);
          if (est.needed_ms > L.max_cpu_ms) throw budgetRefusal('screen', est, L.max_cpu_ms);
          cost += est.needed_ms;
          items.push({ item_id: d.item_id, definition: n.normalized, hash: n.hash });
          entries.push(null);
        } catch (x) {
          const a = toApiError(x);
          if (!a.known) throw x;
          entries.push({ item_id: d.item_id, error: a.error });
        }
      }
      let queue_ms = 0, busy = 0;
      if (items.length) {
        budget.check(owner, pool.reserved(owner), cost);
        const job = pool.submit({ owner, kind: 'counts', page: null, order: null, cost, deadlineAt, task: { kind: 'counts_list', sid: s.sid, items } });
        res.once('close', () => { if (!res.writableFinished) job.cancel() });
        const r = await job.promise;
        queue_ms = r.queue_ms;
        for (const g of (r.outcome as { counts: CountsEntryOut[] }).counts) {
          const at = defs.findIndex((x, k) => entries[k] === null && x.item_id === g.item_id);
          if (at >= 0) entries[at] = g;
          if ('match_count' in g) {
            busy += g.busy_ms;
            const it = items.find(i => i.item_id === g.item_id)!;
            counts.set(countsKey(s, it.hash), { match_count: g.match_count, near_count: g.near_count, sid: s.sid });
          }
        }
        budget.record(owner, busy);
      }
      const body = { versions: { ...s.desc.versions }, data: { ...s.desc.data },
        counts: entries.map(x => !x ? null : 'error' in x ? { item_id: x.item_id, error: x.error } : { item_id: x.item_id, match_count: x.match_count, near_count: x.near_count }) };
      const json = Buffer.from(JSON.stringify(body));
      if (json.byteLength > L.max_response_bytes)
        throw refuse('LIMIT_EXCEEDED', `The answer would have ${json.byteLength} bytes of JSON; the limit is ${L.max_response_bytes}.`, undefined, { limit: 'max_response_bytes', allowed: L.max_response_bytes, needed: json.byteLength });
      if (res.destroyed) return;
      sendGzip(req, res, zlib.gzipSync(json), `"${crypto.createHash('sha256').update(json).digest('hex')}"`);
      log('info', 'counts', { data_version: s.price_data, owner_tag: owner, replica: REPLICA, definitions: defs.length, cache_hits: hits, computed: items.length, predicted_ms: cost, queue_ms: Math.round(queue_ms), busy_ms: busy, total_ms: Math.round(performance.now() - arrived) });
      return;
    }
    throw new HttpError(404, 'NOT_FOUND', 'No such route.');
  }
  function runLog(s: Snap, hash: string, owner: string, def: Definition, r: Computed | null, total: number, status: string): void {
    const o = r?.outcome;
    log(status === 'ok' ? 'info' : 'warn', 'run', {
      definition_hash: hash, data_version: s.price_data, owner_tag: owner, replica: REPLICA, n_conditions: def.conditions.filter(c => c.enabled).length,
      cache_hit: r?.cache_hit ?? false, predicted_ms: r?.predicted_ms ?? null, stages: o?.log.stages ?? [], conditions: o?.log.conditions ?? [], pruned: o?.log.pruned ?? 0,
      pinned_hits: o?.log.pinned_hits ?? 0, lru_hits: o?.log.lru_hits ?? 0, series_computed: o?.log.computed ?? 0,
      queue_ms: Math.round(r?.queue_ms ?? 0), busy_ms: o?.busy_ms ?? 0, total_ms: Math.round(total), payload_bytes: r?.gzip.byteLength ?? 0, status,
    });
  }

  const server = http.createServer((req, res) => {
    const t0 = performance.now(), path = (req.url ?? '/').split('?')[0];
    if (path !== '/health' && path !== '/ready') res.once('close', () => log('info', 'http', { method: req.method, path, status: res.statusCode, ms: Math.round(performance.now() - t0) }));
    const failed = (e: unknown) => {
      if ((e as Error)?.name === 'CallerLeft') return;
      const x = e instanceof ThreadStopped ? new HttpError(500, e.code === 'ERR_WORKER_OUT_OF_MEMORY' ? 'OUT_OF_MEMORY' : 'INTERNAL_ERROR', 'The compute thread stopped; the error is in the worker log.') : e;
      const a = toApiError(x);
      if (!a.known) log('error', 'request_failed', { path, ...errorFields(e, true) });
      if (res.destroyed) return;
      if (!res.headersSent) sendJson(res, a.status, { error: a.error }, a.headers); else res.destroy();
    };
    // the body is read to its end before the answer (the connection stays usable), at most SCREENER_MAX_REQUEST_BYTES
    // of it kept; the body of a caller without the key is read and dropped
    const keep = path !== '/health' && path !== '/ready' && sameKey(req.headers[WORKER_KEY_HEADER], key), parts: Buffer[] = [];
    let size = 0, over = false;
    req.on('data', (c: Buffer) => { if (!keep || over) return; size += c.length; if (size > L.max_request_bytes) { over = true; parts.length = 0 } else parts.push(c) });
    req.on('end', () => {
      if (over) return failed(refuse('REQUEST_TOO_LARGE', `The request has more than ${L.max_request_bytes} bytes: remove conditions or filters.`, 'body', { limit: 'request_bytes', allowed: L.max_request_bytes }));
      route(req, res, path, keep && parts.length ? Buffer.concat(parts) : null, performance.now()).catch(failed);
    });
    req.on('error', () => res.destroy());
  });
  server.keepAliveTimeout = 5000;

  const refresher = new Refresher({ api, client, host, limits: L, fileOrigin: cfg.terminal.fileOrigin, pollMs: opts.pollMs });
  return {
    server, pool, refresher, results, budget,
    state: () => ({ current, previous, outcome }),
    start: () => refresher.start(),
    listen: (port = cfg.port, hostName = '0.0.0.0') => new Promise((ok, no) => {
      server.once('error', no);
      server.listen(port, hostName, () => { server.off('error', no); ok((server.address() as { port: number }).port) });
    }),
    close: async () => {
      refresher.stop();
      if (graceTimer) clearTimeout(graceTimer);
      await new Promise<void>(ok => { server.close(() => ok()); server.closeAllConnections() });
      if (builder) await builder.kill();
      await pool.close();
    },
  };
}

async function main(): Promise<void> {
  let cfg: Config;
  try { cfg = loadConfig() } catch (e) { log('error', 'config_invalid', { message: (e as Error).message }); process.exit(1) }
  const check = await checkStartup();
  if (!check.ok) { log('error', 'startup_check_failed', { problems: check.problems }); process.exit(1) }
  const app = createApp(cfg);
  const port = await app.listen();
  log('info', 'start', { ...describeConfig(cfg), port, screener_engine: ENGINE_VERSION, registry: REGISTRY_VERSION, screener_registry: SCREENER_REGISTRY_VERSION, node: process.version, replica: REPLICA });
  app.start();
  const stop = (signal: string) => { log('info', 'stop', { signal }); app.close().finally(() => process.exit(0)) };
  process.once('SIGTERM', () => stop('SIGTERM'));
  process.once('SIGINT', () => stop('SIGINT'));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
