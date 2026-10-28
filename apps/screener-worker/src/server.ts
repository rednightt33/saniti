/* The screener-worker's private HTTP API (report API CONTRACT 8.11; TARGET ARCHITECTURE 6.4-6.7, 6.16;
   MULTI-USER SCALE AND COST 6d.2-6d.6). edge-bff (app/screener.py ScreenerWorker) is its only caller, on the private
   network; the browser never reaches it.

   GET  /health        no key: {ok, versions, published_at, snapshot_age_seconds, refresh} (contract.ts WorkerHealth;
                       refresh 'loading' before the first snapshot, 'refreshing' while one is built, else the latest
                       publication's outcome)
   GET  /ready         no key (the Railway healthcheck sends none): 200 {ready: true} only with a loaded snapshot, else
                       503 SCREENER_NOT_READY with Retry-After
   every other route needs x-screener-worker-key (else 401 UNAUTHORIZED) and reads x-screener-owner (16 hex; the
   owner's lane; absent = one shared lane):
   GET  /v1/catalog    the publication's catalog (catalog.ts), ETag; If-None-Match -> 304
   GET  /v1/universe   every listed stock's attributes and remarks, ETag
   POST /v1/run        RunRequest -> RunResponse (gzip); POST /v1/preview PreviewRequest -> PreviewResponse (gzip);
   POST /v1/counts     CountsRequest -> CountsResponse (gzip); POST /v1/validate {schema_version, definition} ->
                       {valid, definition_hash, normalized}
   Versions (6d.4): data_version pins run, counts and preview to a snapshot: the current one, or the previous one for
   SCREENER_PREVIOUS_GRACE_S after a swap; a version older than both answers 409 DATA_VERSION_CHANGED; one the replica
   has not loaded yet (terminal-api names a newer publication) 409 DATA_VERSION_PENDING, which edge-bff retries.
   No snapshot: 503 SCREENER_NOT_READY with Retry-After while the first one loads; 424 DATA_INTEGRITY or
   DATA_UNAVAILABLE when the latest publication failed and none is held (8.8).
   Answers are written once the request body is read to its end (the connection stays usable for edge-bff's pool); a
   caller that leaves before its answer cancels its work (8.11). Logs: one `http` line per request and one `run`,
   `preview` or `counts` line that explains it (6.16): stages with tickers in and out and ms, conditions with their
   source, tickers evaluated and ms, pruned, the cache hit, queue and total ms, payload bytes. */
import crypto from 'node:crypto';
import http from 'node:http';
import zlib from 'node:zlib';
import { pathToFileURL } from 'node:url';
import type { Availability, CatalogPreset, Definition, Grouping, MetricRef, RefreshState, UniverseCounts } from '../../edge-bff/screener/src/core/contract.ts';
import { WORKER_KEY_HEADER, WORKER_OWNER_HEADER, WORKER_OWNER_TAG } from '../../edge-bff/screener/src/core/contract.ts';
import { ScreenerError } from '../../edge-bff/screener/src/core/errors.ts';
import { tailLength } from '../../edge-bff/screener/src/core/metrics.ts';
import type { CostTracker } from '../../edge-bff/screener/src/core/plan.ts';
import type { MetricsCatalog, ValidateContext } from '../../edge-bff/screener/src/core/validate.ts';
import { DataError } from '../../edge-bff/backtest/src/core/datafile.ts';
import { TerminalClient } from '../../backtest-worker/src/terminal.ts';
import type { TickerReference } from '../../backtest-worker/src/terminal.ts';
import { catalogDoc, definitionRefs, loadMetrics, loadPresets, metricAvailability, universeDoc } from './catalog.ts';
import type { Doc, PresetDef } from './catalog.ts';
import { cacheShare, describeConfig, loadConfig } from './config.ts';
import type { Config } from './config.ts';
import { HttpError, refuse, toApiError } from './errors.ts';
import { REPLICA, errorFields, log } from './log.ts';
import { OwnerBudget, Pool, SYSTEM, ThreadStopped } from './pool.ts';
import type { ComputeThread } from './pool.ts';
import type { PreviewOutcome, PreviewTask } from './preview.ts';
import { Refresher, TerminalApi } from './refresh.ts';
import type { Held, RefreshHost } from './refresh.ts';
import {
  countsEnvelope, estimateCost, inUniverse, newCostTracker, normalize, previewEnvelope, resultKey, runEnvelope, stage0, validateEnvelope,
} from './run.ts';
import type { ConditionCost, CountsEntryOut, CountsTask, Envelope, RunOutcome, RunTask } from './run.ts';
import { groupingsOf, materialize, referenceHash } from './snapshot.ts';
import type { BuildStats, PublicationState, SnapshotDesc, TickerEntry } from './snapshot.ts';
import type { BuildTask } from './thread.ts';
import { ENGINE_VERSION, REGISTRY_VERSION, SCREENER_REGISTRY_VERSION, checkStartup } from './version.ts';

export const LOADING_RETRY_SECONDS = 5;      // Retry-After while the first snapshot loads (not a limit: a hint)
export const PENDING_CHECK_MS = 5_000;       // an unknown data_version re-reads /state at most this often
const GZIP_MIN_BYTES = 1024;

/* ---- the main thread's half of the engine (DI: the worker's tests replace it; production uses run.ts) ----------- */
export interface Snap {
  sid: string; desc: SnapshotDesc; price_data: string; finished_at: string; files: Record<string, string>; refHash: string;
  vctx: ValidateContext; pinned: Set<string>; position: Map<string, number>;
  groupings: Grouping[]; availability: Map<string, { availability: Availability; reason: string | null }>;
  presets: CatalogPreset[]; catalog: Doc; universe: Doc; expiresAt: number | null;
}
export interface Planned { eligible: string[]; pending: number[]; counts: UniverseCounts; s0_ms: number; cost: { needed_ms: number; costliest: string | null; conditions: ConditionCost[] } }
export interface Engine {
  normalize(definition: unknown, snap: Snap, field?: string): Promise<{ normalized: Definition; hash: string }>;
  plan(def: Definition, snap: Snap, only?: string): Planned;
  observe(list: RunOutcome['observe']): void;
  validateContext(desc: SnapshotDesc, cfg: Config, groupings: Grouping[], metrics: MetricsCatalog | null, availability: Snap['availability']): ValidateContext;
}
export function coreEngine(cfg: Config): Engine {
  const tracker: CostTracker = newCostTracker();
  const ihsg = new WeakMap<Snap, ReturnType<typeof materialize>>();
  const ihsgOf = (snap: Snap) => { let b = ihsg.get(snap); if (!b) { b = materialize(snap.desc, snap.desc.index); ihsg.set(snap, b) } return b };
  return {
    normalize: (definition, snap, field) => normalize(definition, snap.vctx, field),
    plan(def, snap, only) {
      const t0 = performance.now();
      let eligible: string[], pending: number[], counts: UniverseCounts;
      if (only === undefined) {
        const r = stage0(snap.desc, def.universe);
        eligible = r.eligible.map(x => x.ticker); pending = r.pending; counts = r.counts;
      } else {
        const r = inUniverse(snap.desc, def.universe, only);
        eligible = r.eligible ? [only] : []; pending = r.pending;
        counts = { listed: 1, eligible: eligible.length, stale_hidden: 0, price_break_hidden: 0, filtered_out: 1 - eligible.length };
      }
      const s0_ms = performance.now() - t0;
      const cost = estimateCost(def, only === undefined ? eligible : [only], { desc: snap.desc, vctx: snap.vctx, pinned: snap.pinned, position: snap.position }, tracker,
        { capBudgetMs: cfg.limits.cap_budget_ms, index: ihsgOf(snap) });
      return { eligible, pending, counts, s0_ms, cost };
    },
    observe(list) { for (const o of list) { try { tracker.observe(o.key, o.ms, o.bars, o.length) } catch (e) { log('warn', 'cost_observe_failed', errorFields(e)) } } },
    validateContext(desc, c, groupings, metrics, availability) {
      return {
        limits: { max_conditions: c.limits.max_conditions, max_metric_filters: c.limits.max_metric_filters, within_max: c.limits.within_max },
        capBudgetMs: c.limits.cap_budget_ms, tickers: new Set(desc.rows.map(r => r.ticker)), groupings,
        metrics: metrics ?? ({ schema_version: 1, periods: null, metrics: [] } as unknown as MetricsCatalog), availability,
      };
    },
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
  set(key: string, sid: string, gzip: Uint8Array, etag: string, pinned = false): void {
    const bytes = gzip.byteLength + key.length + 64;
    if (!pinned && bytes > this.budget) return;
    this.delete(key);
    this.map.set(key, { sid, gzip, etag, bytes, pinned });
    if (!pinned) { this.lru += bytes; for (const [k, e] of this.map) { if (this.lru <= this.budget) break; if (!e.pinned) { this.map.delete(k); this.lru -= e.bytes } } }
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
function sendGzip(req: http.IncomingMessage, res: http.ServerResponse, gz: Uint8Array, etag: string, extra: Record<string, string> = {}): void {
  const base = { 'content-type': 'application/json', 'cache-control': 'no-store', etag, ...extra };
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

export interface AppOptions {
  engine?: Engine;                       // tests
  threadEngine?: string;                 // tests: thread.ts ThreadData.engine
  metrics?: MetricsCatalog | null; presets?: PresetDef[] | null;
  pollMs?: number; fetch?: typeof fetch;
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
  const metrics = opts.metrics === undefined ? loadMetrics() : opts.metrics;
  const presetDefs = (opts.presets === undefined ? loadPresets() : opts.presets) ?? [];
  const now = opts.now ?? Date.now;
  const L = cfg.limits, TAIL = tailLength(L.within_max);
  const env = { capBudgetMs: L.cap_budget_ms, withinMax: L.within_max, maxResponseBytes: L.max_response_bytes };
  const { fetch: _f, log: _l, ...terminal } = cfg.terminal;
  const script = new URL('./thread.ts', import.meta.url);
  const budget = new OwnerBudget(L.owner_cpu_ms, now);
  const pool = new Pool({ threads: cfg.threads, queue: L.queue, ownerInflight: L.owner_inflight, quantumMs: L.max_cpu_ms / 4, script,
    data: { env, terminal: null, ...(opts.threadEngine ? { engine: opts.threadEngine } : {}) }, budget });
  const results = new ResultCache(cacheShare(cfg));
  const counts = new Map<string, { match_count: number; near_count: number; sid: string }>();
  const key = Buffer.from(cfg.workerKey);
  const engineVersions = { screener_engine: ENGINE_VERSION, registry: REGISTRY_VERSION, screener_registry: SCREENER_REGISTRY_VERSION };
  const client = new TerminalClient({ ...cfg.terminal, ...(opts.fetch ? { fetch: opts.fetch } : {}), log: (event, fields) => log('info', event, { thread: 'http', ...fields }) });
  const api = new TerminalApi({ url: cfg.terminal.url, proxyKey: cfg.terminal.proxyKey, retries: cfg.terminal.retries, retryBaseMs: cfg.terminal.retryBaseMs,
    timeoutMs: cfg.terminal.timeoutMs, maxBytes: cfg.terminal.maxFileBytes, concurrency: cfg.terminal.concurrency, fetch: opts.fetch });

  let current: Snap | null = null, previous: Snap | null = null;
  let outcome: 'ready' | 'failed_keeping_previous' | 'failed' | 'loading' = 'loading';
  let failure: DataError | null = null;
  const retired = new Set<string>();             // price_data of snapshots dropped: older than any held (CHANGED)
  let graceTimer: NodeJS.Timeout | null = null;

  /* ---- the refresh host ---------------------------------------------------------------------------------------- */
  let builder: ComputeThread | null = null, staged: { desc: SnapshotDesc; entries: TickerEntry[]; stats: BuildStats; ref: TickerReference } | null = null;
  const lruBytes = cacheShare(cfg);
  const host: RefreshHost = {
    held: (): Held | null => current && { finished_at: current.finished_at, files: current.files, refHash: current.refHash, price_data: current.price_data },
    async build(input) {
      builder = pool.builder('builder', { role: 'builder', env, terminal, ...(opts.threadEngine ? { engine: opts.threadEngine } : {}) });
      const extra: MetricRef[] = presetDefs.flatMap(p => (!p.availability || p.availability === 'AVAILABLE') ? definitionRefs(p.definition) : []);
      const task: BuildTask = { kind: 'build', files: input.files, ref: input.ref, state: input.state, engine: engineVersions, tailLength: TAIL, extra };
      const { done } = await builder.run(task);
      const out = await done as { desc: SnapshotDesc; entries: TickerEntry[]; stats: BuildStats; cached: Record<string, boolean>; download_ms: number; decode_ms: number; downloads: number; download_bytes: number };
      staged = { desc: out.desc, entries: out.entries, stats: out.stats, ref: input.ref };
      return { entries: out.entries, stats: { download_ms: out.download_ms, decode_ms: out.decode_ms, downloaded_bytes: out.download_bytes, tickers: out.stats.tickers, stocks: out.stats.stocks,
        bars: out.stats.bars, dropped_rows: out.stats.dropped, no_price: out.stats.no_price, actions: out.stats.actions, pinned_series: out.stats.series, prewarm_skipped: out.stats.skipped } };
    },
    async complete(input) {
      if (!staged || !builder) throw new Error('complete: nothing staged');
      const { desc, ref } = staged, b = builder, fields: Record<string, unknown> = { data_version: desc.versions.price_data, orphans: 0 };
      // pre-warm: the builder alone while a snapshot serves; at a cold start the compute threads too (6d.4)
      const t0 = performance.now();
      const workers: ComputeThread[] = current ? [b] : [b, ...pool.threads];
      const T = desc.tickers.length, chunk = Math.max(1, Math.ceil(T / (workers.length * 4)));
      const chunks: [number, number][] = [];
      for (let a = 0; a < T; a += chunk) chunks.push([a, Math.min(T, a + chunk)]);
      await Promise.all(workers.map(async w => {
        for (let c = chunks.shift(); c; c = chunks.shift()) { const { done } = await w.run({ kind: 'prewarm', desc, from: c[0], to: c[1] }); await done }
      }));
      fields.defaults_ms = Math.round(performance.now() - t0);
      const { done } = await b.run({ kind: 'digest', desc });
      desc.digest = ((await done) as { digest: string }).digest;
      fields.snapshot_digest = desc.digest;
      await b.kill(); builder = null;
      // install everywhere (all-or-nothing), then the main thread's view, the presets and the documents
      const ti = performance.now();
      await pool.install(desc.sid, desc, lruBytes);
      fields.install_ms = Math.round(performance.now() - ti);
      try {
        const groupings = groupingsOf(ref), availability = metricAvailability(metrics, input.state.xsection);
        const snap: Snap = {
          sid: desc.sid, desc, price_data: desc.versions.price_data, finished_at: input.state.finished_at, files: input.files, refHash: referenceHash(ref),
          vctx: engine.validateContext(desc, cfg, groupings, metrics, availability), pinned: new Set(desc.series.map(s => s.key)),
          position: new Map(desc.tickers.map((t, j) => [t, j])), groupings, availability, presets: [], catalog: null as unknown as Doc, universe: universeDoc(desc), expiresAt: null,
        };
        const tp = performance.now();
        snap.presets = await presets(snap);
        fields.presets_ms = Math.round(performance.now() - tp);
        snap.catalog = catalogDoc({ desc, refresh: 'ready', limits: L, metrics, availability, groupings, presets: snap.presets });
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
      if (current && (state === 'ready' || state === 'failed_keeping_previous') && before !== state) rebuildDocs(current);
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
      if (old.price_data === s.price_data) retire(old);    // the same price_data (actions or reference changed): nothing to pin
      else {
        old.expiresAt = now() + L.previous_grace_s * 1000; previous = old;
        if (graceTimer) clearTimeout(graceTimer);
        graceTimer = setTimeout(() => { if (previous === old) { retire(old); previous = null } }, L.previous_grace_s * 1000);
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
  /** Each preset's availability, and for an available one its match and near counts, its full result kept pinned in
      the result cache (6.7, 6c.4); computed on the staged snapshot in the system lane before the swap. */
  async function presets(s: Snap): Promise<CatalogPreset[]> {
    return Promise.all(presetDefs.map(async (p): Promise<CatalogPreset> => {
      const base = { id: p.id, category: p.category, name: p.name, why: p.why, definition: p.definition };
      if (p.availability && p.availability !== 'AVAILABLE')
        return { ...base, availability: p.availability, reason: p.reason ?? null, match_count: null, near_count: null, unavailable_legs: p.unavailable_legs ?? [] };
      let n: { normalized: Definition; hash: string };
      try { n = await engine.normalize(p.definition, s) }
      catch (e) {
        if (e instanceof ScreenerError && e.code === 'METRIC_UNAVAILABLE') {
          const legs: string[] = [];
          for (const c of p.definition.conditions ?? []) {
            try { await engine.normalize({ ...p.definition, conditions: [c] }, s) } catch (x) { if (x instanceof ScreenerError && x.code === 'METRIC_UNAVAILABLE') legs.push(c.id) }
          }
          return { ...base, availability: (e.details?.availability as Availability) ?? 'REQUIRES_DATA', reason: e.message, match_count: null, near_count: null, unavailable_legs: legs };
        }
        log('error', 'preset_invalid', { preset: p.id, ...errorFields(e) });
        return { ...base, availability: 'REQUIRES_DECISION', reason: `This preset does not pass validation: ${(e as Error).message}`, match_count: null, near_count: null, unavailable_legs: [] };
      }
      try {
        const o = await compute(s, n.normalized, n.hash, { exhaustive: false, explain: false }, SYSTEM, null, null, performance.now() + L.deadline_ms * 4, true);
        return { ...base, definition: p.definition, availability: 'AVAILABLE', reason: null, match_count: o.match_count, near_count: o.near_count, unavailable_legs: [] };
      } catch (e) {
        log('error', 'preset_failed', { preset: p.id, ...errorFields(e, true) });
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
    if (!retired.has(version) && (previous?.price_data !== version)) {
      await refresher.latest(PENDING_CHECK_MS);
      if (refresher.behind())
        throw refuse('DATA_VERSION_PENDING', 'This replica has not loaded the publication the page shows yet; ask again shortly.', 'data_version');
    }
    throw refuse('DATA_VERSION_CHANGED', 'New data was published since the page loaded its catalog: read the catalog again and run the screen on it.', 'data_version');
  }

  /* ---- compute ---------------------------------------------------------------------------------------------- */
  /** One run (or a preset's) on a snapshot: the result cache, the budgets, the owner's lane. */
  async function compute(s: Snap, def: Definition, hash: string, options: { exhaustive: boolean; explain: boolean }, owner: string,
    order: Envelope['client_order'], res: http.ServerResponse | null, deadlineAt: number, system = false): Promise<{ gzip: Uint8Array; etag: string; match_count: number; near_count: number; cache_hit: boolean; outcome: RunOutcome | null; queue_ms: number; cost: number }> {
    const k = resultKey(s.desc, hash, options);
    const hit = results.get(k);
    if (hit) {
      const c = counts.get(resultKey(s.desc, hash, { exhaustive: false, explain: false }, 'counts'));
      return { gzip: hit.gzip, etag: hit.etag, match_count: c?.match_count ?? -1, near_count: c?.near_count ?? -1, cache_hit: true, outcome: null, queue_ms: 0, cost: 0 };
    }
    const p = engine.plan(def, s);
    if (!system && p.cost.needed_ms > L.max_cpu_ms)
      throw refuse('LIMIT_EXCEEDED', `This screen is predicted to need ${p.cost.needed_ms} ms of compute; the limit is ${L.max_cpu_ms} ms${p.cost.costliest ? `, and condition ${p.cost.costliest} is the costliest` : ''}. Use fewer custom conditions or shorter lengths.`,
        undefined, { limit: 'compute_budget', allowed: L.max_cpu_ms, needed: p.cost.needed_ms, ...(p.cost.costliest ? { costliest: p.cost.costliest } : {}) });
    if (!system) budget.check(owner, pool.reserved(owner), p.cost.needed_ms);
    const task: RunTask = { kind: 'run', sid: s.sid, definition: def, hash, options, eligible: p.eligible, pending: p.pending, counts: p.counts,
      predicted: Object.fromEntries(p.cost.conditions.map(c => [c.id, c.predictedMs])), queue_ms: 0, s0_ms: p.s0_ms, versions: s.desc.versions, data: s.desc.data };
    const job = pool.submit({ owner, kind: system ? 'system' : 'run', page: order?.page ?? null, order: order?.seq ?? null, cost: p.cost.needed_ms, deadlineAt, task });
    res?.once('close', () => { if (!res.writableFinished) job.cancel() });
    const { outcome: o, queue_ms } = await job.promise;
    const out = o as RunOutcome;
    budget.record(owner, out.busy_ms);
    engine.observe(out.observe);
    if (out.gzip && out.etag) results.set(k, s.sid, out.gzip, out.etag, system);
    counts.set(resultKey(s.desc, hash, { exhaustive: false, explain: false }, 'counts'), { match_count: out.match_count, near_count: out.near_count, sid: s.sid });
    return { gzip: out.gzip as Uint8Array, etag: out.etag as string, match_count: out.match_count, near_count: out.near_count, cache_hit: false, outcome: out, queue_ms, cost: p.cost.needed_ms };
  }

  /* ---- routes ------------------------------------------------------------------------------------------------- */
  function health() {
    const refresh = refresher.phase === 'refreshing' ? 'refreshing' : !current ? 'loading' : outcome === 'failed_keeping_previous' ? 'failed_keeping_previous' : 'ready';
    const published = current?.finished_at ?? null;
    return {
      ok: true, versions: current ? { ...current.desc.versions } : null, published_at: published,
      snapshot_age_seconds: published ? Math.max(0, Math.round((now() - Date.parse(published)) / 1000)) : null, refresh,
    };
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
    const owner = ownerOf(req);
    const deadlineAt = arrived + L.deadline_ms;
    if (path === '/v1/catalog') { allow('GET'); if (!current) throw notReady(); return sendDoc(req, res, current.catalog) }
    if (path === '/v1/universe') { allow('GET'); if (!current) throw notReady(); return sendDoc(req, res, current.universe) }
    if (path === '/v1/validate') {
      allow('POST');
      const e = validateEnvelope(parseJson(raw));
      if (!current) throw notReady();
      const n = await engine.normalize(e.definition, current);
      return sendJson(res, 200, { valid: true, definition_hash: n.hash, normalized: n.normalized });
    }
    if (path === '/v1/run') {
      allow('POST');
      const e = runEnvelope(parseJson(raw));
      const s = await pinned(e.data_version);
      const n = await engine.normalize(e.definition, s);
      const t0 = performance.now();
      let status = 'ok';
      try {
        const r = await compute(s, n.normalized, n.hash, e.options, owner, e.client_order, res, deadlineAt);
        if (res.destroyed) { status = 'caller_left'; return }
        sendGzip(req, res, r.gzip, r.etag);
        runLog(s, n.hash, owner, n.normalized, r, performance.now() - arrived, r.gzip.byteLength, status);
      } catch (x) {
        status = toApiError(x).error.code;
        runLog(s, n.hash, owner, n.normalized, null, performance.now() - arrived, 0, status, performance.now() - t0);
        throw x;
      }
      return;
    }
    if (path === '/v1/preview') {
      allow('POST');
      const e = previewEnvelope(parseJson(raw));
      const s = await pinned(e.data_version);
      const n = await engine.normalize(e.definition, s);
      const ticker = e.ticker as string;
      if (!s.desc.rows.some(r => r.ticker === ticker)) throw refuse('INVALID_INPUT', `${ticker} is not a listed stock of this publication; preview a ticker of GET universe.`, 'ticker');
      const k = resultKey(s.desc, n.hash, e.options, `preview:${ticker}`);
      const hit = results.get(k);
      if (hit) { sendGzip(req, res, hit.gzip, hit.etag); log('info', 'preview', { definition_hash: n.hash, data_version: s.price_data, ticker, owner_tag: owner, replica: REPLICA, cache_hit: true, total_ms: Math.round(performance.now() - arrived) }); return }
      const p = engine.plan(n.normalized, s, ticker);
      if (p.cost.needed_ms > L.max_cpu_ms)
        throw refuse('LIMIT_EXCEEDED', `This preview is predicted to need ${p.cost.needed_ms} ms of compute; the limit is ${L.max_cpu_ms} ms. Use fewer custom conditions or shorter lengths.`, undefined, { limit: 'compute_budget', allowed: L.max_cpu_ms, needed: p.cost.needed_ms, ...(p.cost.costliest ? { costliest: p.cost.costliest } : {}) });
      budget.check(owner, pool.reserved(owner), p.cost.needed_ms);
      const task: PreviewTask = { kind: 'preview', sid: s.sid, definition: n.normalized, ticker, s0: p.eligible.length === 1, pending: p.pending, periods: metrics?.periods ?? null, versions: { ...s.desc.versions }, data: { ...s.desc.data } };
      const job = pool.submit({ owner, kind: 'preview', page: e.client_order?.page ?? null, order: e.client_order?.seq ?? null, cost: p.cost.needed_ms, deadlineAt, task });
      res.once('close', () => { if (!res.writableFinished) job.cancel() });
      const { outcome: o, queue_ms } = await job.promise;
      const out = o as PreviewOutcome;
      budget.record(owner, out.busy_ms);
      results.set(k, s.sid, out.gzip, out.etag);
      if (res.destroyed) return;
      sendGzip(req, res, out.gzip, out.etag);
      log('info', 'preview', { definition_hash: n.hash, data_version: s.price_data, ticker, owner_tag: owner, replica: REPLICA, cache_hit: false, status: out.status, queue_ms: Math.round(queue_ms), busy_ms: out.busy_ms, total_ms: Math.round(performance.now() - arrived), payload_bytes: out.gzip.byteLength });
      return;
    }
    if (path === '/v1/counts') {
      allow('POST');
      const e = countsEnvelope(parseJson(raw), L.max_counts);
      const s = await pinned(e.data_version);
      const entries: (CountsEntryOut | null)[] = [];
      const items: CountsTask['items'] = [];
      let cost = 0, hits = 0;
      for (const [k, d] of (e.definitions ?? []).entries()) {
        try {
          const n = await engine.normalize(d.definition, s, `definitions[${k}].definition`);
          const c = counts.get(resultKey(s.desc, n.hash, { exhaustive: false, explain: false }, 'counts'));
          if (c) { hits++; entries.push({ item_id: d.item_id, match_count: c.match_count, near_count: c.near_count, busy_ms: 0 }); continue }
          const p = engine.plan(n.normalized, s);
          if (p.cost.needed_ms > L.max_cpu_ms)
            throw refuse('LIMIT_EXCEEDED', `This screen is predicted to need ${p.cost.needed_ms} ms of compute; the limit is ${L.max_cpu_ms} ms. Use fewer custom conditions or shorter lengths.`, undefined, { limit: 'compute_budget', allowed: L.max_cpu_ms, needed: p.cost.needed_ms, ...(p.cost.costliest ? { costliest: p.cost.costliest } : {}) });
          cost += p.cost.needed_ms;
          items.push({ item_id: d.item_id, definition: n.normalized, hash: n.hash, eligible: p.eligible, pending: p.pending, counts: p.counts,
            predicted: Object.fromEntries(p.cost.conditions.map(c => [c.id, c.predictedMs])), s0_ms: p.s0_ms });
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
        const got = (r.outcome as { counts: CountsEntryOut[] }).counts;
        for (const g of got) {
          busy += 'busy_ms' in g ? g.busy_ms : 0;
          const at = entries.findIndex((x, k) => x === null && (e.definitions ?? [])[k].item_id === g.item_id);
          if (at >= 0) entries[at] = g;
          const it = items.find(i => i.item_id === g.item_id);
          if (it && 'match_count' in g) counts.set(resultKey(s.desc, it.hash, { exhaustive: false, explain: false }, 'counts'), { match_count: g.match_count, near_count: g.near_count, sid: s.sid });
        }
        budget.record(owner, busy);
      }
      const body = { versions: { ...s.desc.versions }, data: { ...s.desc.data },
        counts: entries.map(x => x && ('error' in x ? { item_id: x.item_id, error: x.error } : { item_id: x.item_id, match_count: x.match_count, near_count: x.near_count })) };
      const json = Buffer.from(JSON.stringify(body));
      if (json.byteLength > L.max_response_bytes)
        throw refuse('LIMIT_EXCEEDED', `The answer would have ${json.byteLength} bytes of JSON; the limit is ${L.max_response_bytes}.`, undefined, { limit: 'max_response_bytes', allowed: L.max_response_bytes, needed: json.byteLength });
      if (res.destroyed) return;
      sendGzip(req, res, zlib.gzipSync(json), `"${crypto.createHash('sha256').update(json).digest('hex')}"`);
      log('info', 'counts', { data_version: s.price_data, owner_tag: owner, replica: REPLICA, definitions: entries.length, cache_hits: hits, computed: items.length, queue_ms: Math.round(queue_ms), busy_ms: busy, total_ms: Math.round(performance.now() - arrived) });
      return;
    }
    throw new HttpError(404, 'NOT_FOUND', 'No such route.');
  }
  function runLog(s: Snap, hash: string, owner: string, def: Definition, r: Awaited<ReturnType<typeof compute>> | null, total: number, bytes: number, status: string, ms = 0) {
    const o = r?.outcome;
    log(status === 'ok' ? 'info' : 'warn', 'run', {
      definition_hash: hash, data_version: s.price_data, owner_tag: owner, replica: REPLICA, n_conditions: def.conditions.filter(c => c.enabled).length,
      cache_hit: r?.cache_hit ?? false, predicted_ms: r?.cost ?? null, stages: o?.log.stages ?? [], conditions: o?.log.conditions ?? [], pruned: o?.log.pruned ?? 0,
      pinned_hits: o?.log.pinned_hits ?? 0, queue_ms: Math.round(r?.queue_ms ?? 0), busy_ms: o?.busy_ms ?? 0, total_ms: Math.round(total || ms), payload_bytes: bytes, status,
    });
  }

  const server = http.createServer((req, res) => {
    const t0 = performance.now(), path = (req.url ?? '/').split('?')[0];
    if (path !== '/health' && path !== '/ready') res.once('close', () => log('info', 'http', { method: req.method, path, status: res.statusCode, ms: Math.round(performance.now() - t0) }));
    const failed = (e: unknown) => {
      if ((e as Error)?.name === 'CallerLeft') return;
      const a = toApiError(e instanceof ThreadStopped ? new HttpError(500, e.code === 'ERR_WORKER_OUT_OF_MEMORY' ? 'OUT_OF_MEMORY' : 'INTERNAL_ERROR', 'The compute thread stopped; the error is in the worker log.') : e);
      if (!a.known) log('error', 'request_failed', { path, ...errorFields(e, true) });
      if (res.destroyed) return;
      if (!res.headersSent) sendJson(res, a.status, { error: a.error }, a.headers); else res.destroy();
    };
    // the body is read to its end before the answer (the connection stays usable), and at most
    // SCREENER_MAX_REQUEST_BYTES of it is kept; the body of a caller without the key is read and dropped
    const keep = path !== '/health' && path !== '/ready' && sameKey(req.headers[WORKER_KEY_HEADER], key), parts: Buffer[] = [];
    let size = 0, over = false;
    req.on('data', (c: Buffer) => { if (!keep || over) return; size += c.length; if (size > L.max_request_bytes) { over = true; parts.length = 0 } else parts.push(c) });
    req.on('end', () => {
      if (over) return failed(refuse('REQUEST_TOO_LARGE', `The request has more than ${L.max_request_bytes} bytes: remove conditions or filters.`, 'body', { limit: 'max_request_bytes', allowed: L.max_request_bytes }));
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
  const metrics = loadMetrics(), presets = loadPresets();
  if (!metrics || !presets) { log('error', 'startup_check_failed', { problems: [!metrics && 'apps/edge-bff/screener/src/core/screener-metrics.json is missing', !presets && 'apps/edge-bff/screener/src/core/presets.json is missing'].filter(Boolean) }); process.exit(1) }
  const app = createApp(cfg, { metrics, presets });
  const port = await app.listen();
  log('info', 'start', { ...describeConfig(cfg), port, screener_engine: ENGINE_VERSION, registry: REGISTRY_VERSION, screener_registry: SCREENER_REGISTRY_VERSION, node: process.version, replica: REPLICA });
  app.start();
  const stop = (signal: string) => { log('info', 'stop', { signal }); app.close().finally(() => process.exit(0)) };
  process.once('SIGTERM', () => stop('SIGTERM'));
  process.once('SIGINT', () => stop('SIGINT'));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
export type { RefreshState, PublicationState };
