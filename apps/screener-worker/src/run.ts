/* POST /v1/run and POST /v1/counts: a definition -> its result, through the screener core only (report TARGET
   ARCHITECTURE 6.9 condition engine, 6.10 planner; API CONTRACT 8.5, 8.6). The worker computes nothing of its own:
   validation and the definition hash (validate.ts), the stages S0-S4 with the pruning rule (screen.ts runScreen over
   condition.ts, evaluate.ts, plan.ts, xsection.ts, universe.ts), every series through the one series() path
   (metrics.ts) are the core's. This file is the worker's half around them:

   Main thread: the request envelope (fields outside the definition: schema_version, client_order, data_version,
   options; every object closed), normalize (validateDefinition + definitionHash), the result cache key (the snapshot,
   the engine and registry versions, the definition hash and the two options that change the answer's bytes; nothing of
   the owner, 6d.2), and the worst case before any compute (6.10 "Counts and budget"; estimateCost): S0 without the
   metric filters (an upper bound of the survivors), each enabled condition bound as screen.ts binds it, its stage
   (S1 cross-section; S2 when every series is pre-warmed or it reads a universe attribute; S3 otherwise), the predicted
   ms per ticker of its series that are not pre-warmed (plan.ts CostTracker), plan.ts costEstimate over the survivors,
   plus the metric filters' series on every survivor. A request above SCREENER_MAX_CPU_MS is refused before it reaches a
   lane (pool.ts).
   Compute thread (runTask): the snapshot as screen.ts's ScreenEnv (screenEnv): the listed rows, a ticker's bars
   materialized from the shared columns with a per-request Calc, the one series() path over the thread's SeriesCache
   (pinned snapshot tails and its custom-parameter LRU), IHSG for vs_index and its calendar, the cancel flag; the answer
   built there (schema_version, versions and data first: edge-bff reads them from the gzip head), held to
   SCREENER_MAX_RESPONSE_BYTES, gzipped there (no JSON work on the HTTP thread). The measured time of every series
   computed on a miss goes back to the main thread's cost model (observe). */
import zlib from 'node:zlib';
import crypto from 'node:crypto';
import type { DataStatus, Definition, MetricRef, RunResponse, UniverseCounts, UniverseDef, Versions } from '../../edge-bff/screener/src/core/contract.ts';
import { METRICS_CATALOG } from '../../edge-bff/screener/src/core/catalog.ts';
import { bindCondition, bindTest } from '../../edge-bff/screener/src/core/condition.ts';
import type { BindContext } from '../../edge-bff/screener/src/core/condition.ts';
import { series, seriesKey, tickerCalc } from '../../edge-bff/screener/src/core/metrics.ts';
import type { ResolvedSeries, SeriesSource, Tail, TickerBars, TickerCalc } from '../../edge-bff/screener/src/core/metrics.ts';
import { costEstimate, costTracker } from '../../edge-bff/screener/src/core/plan.ts';
import type { CostTracker, PlanCondition } from '../../edge-bff/screener/src/core/plan.ts';
import { SBY_ID, SCREENER_REGISTRY } from '../../edge-bff/screener/src/core/registry.ts';
import { runScreen } from '../../edge-bff/screener/src/core/screen.ts';
import type { ScreenEnv } from '../../edge-bff/screener/src/core/screen.ts';
import { applyUniverse } from '../../edge-bff/screener/src/core/universe.ts';
import { definitionHash, validateDefinition } from '../../edge-bff/screener/src/core/validate.ts';
import type { ValidateContext } from '../../edge-bff/screener/src/core/validate.ts';
import { canonicalJson } from '../../edge-bff/backtest/src/core/hash.ts';
import { barCount } from './snapshot.ts';
import type { SnapshotDesc, ThreadSnapshot } from './snapshot.ts';
import { refuse } from './errors.ts';

/* ================================================================================================================ */
/* the request envelope (report 8.5, 8.6; the definition itself is validate.ts's)                                  */
/* ================================================================================================================ */

const HEX64 = /^[0-9a-f]{64}$/;
const PAGE = /^[A-Za-z0-9._:-]{1,100}$/;             // edge-bff backtest.py preview_order (the page id it relays)
const obj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const bad = (field: string, message: string) => refuse('INVALID_INPUT', message, field);
function closed(v: Record<string, unknown>, allowed: readonly string[], at: string): void {
  for (const k of Object.keys(v)) if (!allowed.includes(k)) throw bad(at ? `${at}.${k}` : k, `${at ? `${at}.` : ''}${k} is not a field of this request; send only ${allowed.join(', ')}.`);
}
export interface RunOptionsN { exhaustive: boolean; explain: boolean }
export interface Envelope { client_order: { page: string; seq: number } | null; data_version: string | null; definition: unknown; options: RunOptionsN; ticker?: string; definitions?: { item_id: string; definition: unknown }[] }

function schema(b: Record<string, unknown>): void {
  if (b.schema_version !== 1) throw bad('schema_version', 'schema_version must be 1.');
}
function order(v: unknown): { page: string; seq: number } | null {
  if (v === undefined) return null;
  if (!obj(v) || typeof v.page !== 'string' || !PAGE.test(v.page) || !Number.isSafeInteger(v.seq) || (v.seq as number) < 0)
    throw bad('client_order', 'client_order is {page, seq}: page an id of 1-100 characters A-Z a-z 0-9 . _ : -, seq a whole number from 0.');
  closed(v, ['page', 'seq'], 'client_order');
  return { page: v.page, seq: v.seq as number };
}
function version(v: unknown, required: boolean): string | null {
  if (v === undefined || v === null) { if (required) throw bad('data_version', 'data_version is required: the price_data of the catalog the page shows.'); return null }
  if (typeof v !== 'string' || !HEX64.test(v)) throw bad('data_version', 'data_version must be the 64-hex price_data of the catalog.');
  return v;
}
/** POST /v1/run {schema_version, client_order, data_version?, definition, options?}. */
export function runEnvelope(b: unknown): Envelope {
  if (!obj(b)) throw bad('body', 'The body must be a run request {schema_version, client_order, definition, options}.');
  closed(b, ['schema_version', 'client_order', 'data_version', 'definition', 'options'], '');
  schema(b);
  let options: RunOptionsN = { exhaustive: false, explain: false };
  if (b.options !== undefined) {
    if (!obj(b.options)) throw bad('options', 'options must be {exhaustive?, explain?}.');
    closed(b.options, ['exhaustive', 'explain'], 'options');
    for (const k of ['exhaustive', 'explain'] as const) if (b.options[k] !== undefined && typeof b.options[k] !== 'boolean') throw bad(`options.${k}`, `options.${k} must be true or false.`);
    options = { exhaustive: b.options.exhaustive === true, explain: b.options.explain === true };
  }
  return { client_order: order(b.client_order), data_version: version(b.data_version, false), definition: b.definition, options };
}
/** POST /v1/preview {schema_version, client_order, definition, ticker, data_version}. */
export function previewEnvelope(b: unknown): Envelope {
  if (!obj(b)) throw bad('body', 'The body must be a preview request {schema_version, client_order, definition, ticker, data_version}.');
  closed(b, ['schema_version', 'client_order', 'data_version', 'definition', 'ticker'], '');
  schema(b);
  if (typeof b.ticker !== 'string' || !/^[A-Z0-9]{1,12}$/.test(b.ticker)) throw bad('ticker', 'ticker must be a listed ticker (1-12 capital letters or digits).');
  return { client_order: order(b.client_order), data_version: version(b.data_version, true), definition: b.definition, options: { exhaustive: true, explain: false }, ticker: b.ticker };
}
/** POST /v1/counts {schema_version, data_version?, definitions: [{item_id, definition}]} (at most max_counts). */
export function countsEnvelope(b: unknown, maxCounts: number): Envelope {
  if (!obj(b)) throw bad('body', 'The body must be a counts request {schema_version, definitions}.');
  closed(b, ['schema_version', 'data_version', 'definitions'], '');
  schema(b);
  if (!Array.isArray(b.definitions)) throw bad('definitions', 'definitions must be a list of {item_id, definition}.');
  if (b.definitions.length > maxCounts)
    throw refuse('LIMIT_EXCEEDED', `A counts request holds at most ${maxCounts} definitions; this one has ${b.definitions.length}. Ask for the rest in a second request.`, 'definitions', { limit: 'max_counts', allowed: maxCounts, needed: b.definitions.length });
  const seen = new Set<string>();
  const definitions = b.definitions.map((d: unknown, k: number) => {
    const f = `definitions[${k}]`;
    if (!obj(d) || typeof d.item_id !== 'string' || !d.item_id || d.item_id.length > 100) throw bad(`${f}.item_id`, `${f} must be {item_id, definition} with an item_id of 1-100 characters.`);
    closed(d, ['item_id', 'definition'], f);
    if (seen.has(d.item_id)) throw bad(`${f}.item_id`, `${f}.item_id ${d.item_id} appears twice.`);
    seen.add(d.item_id);
    return { item_id: d.item_id, definition: d.definition };
  });
  return { client_order: null, data_version: version(b.data_version, false), definition: null, options: { exhaustive: false, explain: false }, definitions };
}
/** POST /v1/validate {schema_version, definition}. */
export function validateEnvelope(b: unknown): Envelope {
  if (!obj(b)) throw bad('body', 'The body must be {schema_version, definition}.');
  closed(b, ['schema_version', 'definition'], '');
  schema(b);
  return { client_order: null, data_version: null, definition: b.definition, options: { exhaustive: false, explain: false } };
}

/* ================================================================================================================ */
/* main thread                                                                                                     */
/* ================================================================================================================ */

/** The normalized definition and its hash (validate.ts; 8.3), or the first refusal. */
export async function normalize(definition: unknown, vctx: ValidateContext, field = 'definition'): Promise<{ normalized: Definition; hash: string }> {
  const normalized = validateDefinition(definition, vctx, field);
  return { normalized, hash: await definitionHash(normalized) };
}

/** The result cache key (8.10, 6d.2): the snapshot, the engine and registry versions, the definition hash and the two
    options that change the answer's bytes (exhaustive counts, explain's plan). No owner, page or order. */
export const resultKey = (desc: SnapshotDesc, hash: string, options: RunOptionsN, kind = 'run'): string =>
  canonicalJson([kind, desc.sid, desc.versions.screener_engine, desc.versions.registry, desc.versions.screener_registry, hash, options.exhaustive, options.explain]);

/* ---- cost (6.10 "Counts and budget") ------------------------------------------------------------------------- */

export const COST_ALPHA = 0.2;          // weight of a new measurement in plan.ts's exponentially weighted mean
export const newCostTracker = (): CostTracker => costTracker(SCREENER_REGISTRY.cost_model.ns_per_bar_length, COST_ALPHA);

/** One kernel a series runs when it is computed: its cost key, class and length (the multiplier of an O(N·n) class). */
export interface CostUnit { key: string; costClass: 'O(N)' | 'O(N·n)'; length: number }
const maxNumber = (m: unknown): number => {
  let n = 1;
  if (obj(m)) for (const v of Object.values(m)) if (typeof v === 'number' && Number.isFinite(v) && v > n) n = v;
  return n;
};
/** The kernels computing a reference runs from the bars (a transform computes its operands in full, through the
    ticker's Calc, whatever is pre-warmed): an indicator with the registry's cost class and the largest value of its
    O(N·n) parameters; a transform or a pattern as O(N·n) over its largest numeric argument (conservative: a rolling
    window may be linear in its implementation; the measured mean corrects the prediction). */
export function costUnits(ref: unknown): CostUnit[] {
  if (!obj(ref)) return [];
  switch (ref.kind) {
    case 'indicator': {
      const ind = SBY_ID[ref.indicator as string];
      if (!ind) return [];
      const params = obj(ref.params) ? ref.params : {};
      const length = Math.max(1, ...ind.params.filter(p => p.cost_class === 'O(N·n)').map(p => Number(params[p.key] ?? p.default) || 1));
      return [{ key: `indicator:${ind.key}`, costClass: ind.cost_class === 'O(N·n)' ? 'O(N·n)' : 'O(N)', length }];
    }
    case 'transform': {
      const inner = costUnits(ref.of);
      if (obj(ref.args)) for (const a of Object.values(ref.args)) if (obj(a)) inner.push(...costUnits(a));
      return [...inner, { key: `transform:${String(ref.fn)}`, costClass: 'O(N·n)', length: maxNumber(ref.args) }];
    }
    case 'pattern': return [{ key: `pattern:${String(ref.type)}`, costClass: 'O(N·n)', length: maxNumber(ref.params) }];
  }
  return [];
}
/** Predicted ms of computing one series on one ticker of `bars` bars. */
export const predictMs = (tracker: CostTracker, r: Pick<ResolvedSeries, 'ref'>, bars: number): number =>
  costUnits(r.ref).reduce((s, u) => s + tracker.predict(u.key, u.costClass, u.length, bars), 0);

/** The parts of a held snapshot the estimate reads. */
export interface CostView { desc: SnapshotDesc; pinned: Set<string>; position: Map<string, number>; index: TickerBars }
export interface Estimate { needed_ms: number; costliest: string | null; perTicker: number; eligible: number; s0_ms: number }
/** The worst case of a definition on its S0 survivors (header). `only`: one ticker (a preview). */
export function estimateCost(def: Definition, held: CostView, tracker: CostTracker, env: { capBudgetMs: number; withinMax: number }, only?: string): Estimate {
  const t0 = performance.now();
  const u = only === undefined ? applyUniverse(held.desc.rows, def.universe) : null;
  const survivors = only === undefined ? (u as ReturnType<typeof applyUniverse>).eligible.map(r => r.ticker) : [only];
  const s0_ms = performance.now() - t0;
  let bars = 0;
  for (const t of survivors) { const j = held.position.get(t); if (j !== undefined) bars += barCount(held.desc, j) }
  const avg = survivors.length ? bars / survivors.length : 0;
  const dv = { price_data: held.desc.versions.price_data, screener_engine: held.desc.versions.screener_engine };
  const ctx: BindContext = { capBudgetMs: env.capBudgetMs, index: held.index, withinMax: env.withinMax, catalog: METRICS_CATALOG };
  const pinned = (r: ResolvedSeries) => r.kind === 'price' || held.pinned.has(seriesKey(dv, r));   // a bar field is the snapshot itself (screen.ts)
  const conds: PlanCondition[] = def.conditions.flatMap((c, k) => {
    if (!c.enabled) return [];
    const b = bindCondition(c, `definition.conditions[${k}]`, ctx);
    const stage = b.xsection ? 'S1' : b.universeAttr !== null || b.series.every(pinned) ? 'S2' : 'S3';
    const predictedMs = stage === 'S3' ? b.series.filter(r => !pinned(r)).reduce((ms, r) => ms + predictMs(tracker, r, avg), 0) : 0;
    return [{ id: c.id, stage, predictedMs, evaluate: () => { throw new Error('estimate only') } }];
  });
  const est = costEstimate(conds, survivors.length);
  // the metric filters the core evaluates in S0 (universe.ts pending): on every survivor, never pruned
  let filters = 0;
  if (u) for (const i of u.pending) {
    const b = bindTest(`f${i}`, (def.universe.metric_filters ?? [])[i], `definition.universe.metric_filters[${i}]`, ctx);
    filters += b.series.filter(r => !pinned(r)).reduce((ms, r) => ms + predictMs(tracker, r, avg), 0) * survivors.length;
  }
  const perTicker = conds.reduce((s, c) => s + c.predictedMs, 0);
  return { needed_ms: Math.ceil(est.needed_ms + filters), costliest: est.costliest, perTicker, eligible: survivors.length, s0_ms };
}

/* ================================================================================================================ */
/* compute thread                                                                                                  */
/* ================================================================================================================ */

export interface ThreadEnv { capBudgetMs: number; withinMax: number; maxResponseBytes: number }
export const CALC_KEEP = 256;          // tickers whose bars and Calc one request keeps (least recently used out)

/** What a request measured on the snapshot: pinned tails read, series computed (by cost key, for the cost model). */
export interface Measured { pinned_hits: number; lru_hits: number; computed: number; observe: Map<string, { ms: number; bars: number; length: number }> }

/** The snapshot as screen.ts reads it (header). */
export function screenEnv(snap: ThreadSnapshot, env: ThreadEnv, cancelled: () => boolean): { env: ScreenEnv; measured: Measured; calc(ticker: string): TickerCalc | undefined } {
  const calcs = new Map<string, TickerCalc>();
  const measured: Measured = { pinned_hits: 0, lru_hits: 0, computed: 0, observe: new Map() };
  const sctx = { versions: snap.dv, tailLength: snap.desc.tailLength, cache: snap.cache };
  const calc = (ticker: string): TickerCalc | undefined => {
    let c = calcs.get(ticker);
    if (c) { calcs.delete(ticker); calcs.set(ticker, c); return c }
    if (!snap.position.has(ticker)) return undefined;
    c = tickerCalc(snap.bars(ticker));
    calcs.set(ticker, c);
    if (calcs.size > CALC_KEEP) calcs.delete(calcs.keys().next().value as string);
    return c;
  };
  const screen: ScreenEnv = {
    capBudgetMs: env.capBudgetMs, index: snap.ihsg, withinMax: env.withinMax, catalog: METRICS_CATALOG,
    evaluationDate: snap.desc.data.evaluation_date, rows: snap.desc.rows, ihsgCalendar: snap.ihsgCalendar,
    bars: ticker => calc(ticker),
    series(r: ResolvedSeries, t: TickerBars): { tail: Tail; source: SeriesSource } {
      const hit = snap.cache.get(seriesKey(snap.dv, r), t.ticker);
      if (hit) { if (hit.pinned) measured.pinned_hits++; else measured.lru_hits++; return { tail: hit.tail, source: hit.pinned ? 'precomputed' : 'dynamic' } }
      const tc = (t as TickerCalc).calc ? t as TickerCalc : tickerCalc(t), t0 = performance.now();
      const out = series(sctx, tc, r);
      const ms = performance.now() - t0, units = costUnits(r.ref);
      measured.computed++;
      if (units.length === 1) {
        const o = measured.observe.get(units[0].key) ?? { ms: 0, bars: 0, length: units[0].length };
        if (o.length === units[0].length) { o.ms += ms; o.bars += t.dates.length; measured.observe.set(units[0].key, o) }
      }
      return out;
    },
    isPrewarmed: r => snap.pinned.has(seriesKey(snap.dv, r)),
    predictMs: (r, bars) => predictMs(threadTracker, r, bars),
    cacheHits: () => measured.pinned_hits + measured.lru_hits,
    cancelled,
  };
  return { env: screen, measured, calc };
}
/** The thread's own cost model orders S3 only (the budget was checked on the main thread with the measured one). */
const threadTracker = newCostTracker();

export interface RunTask {
  kind: 'run' | 'counts';
  sid: string; definition: Definition; hash: string; options: RunOptionsN;
  queue_ms: number; s0_ms: number;
  /** the answer's blocks, from the main thread (published_at advances without a new snapshot, 6d.2) */
  versions: Omit<Versions, 'definition_hash'>; data: Omit<DataStatus, 'refresh'>;
}
/** POST /v1/counts as one job: each definition's match and near counts (8.6), one after the other on one thread. */
export interface CountsTask { kind: 'counts_list'; sid: string; items: { item_id: string; definition: Definition; hash: string }[] }
export type CountsEntryOut = { item_id: string; match_count: number; near_count: number; busy_ms: number } | { item_id: string; error: { code: string; field?: string; message?: string; details?: Record<string, unknown> } };
export interface RunLog { stages: { name: string; in: number; out: number; ms: number }[]; conditions: { id: string; source: string; evaluated: number; exhaustive: boolean }[]; pruned: number; pinned_hits: number; lru_hits: number; computed: number }
export interface RunOutcome {
  kind: 'run' | 'counts';
  gzip: Uint8Array | null; etag: string | null; json_bytes: number;
  match_count: number; near_count: number; busy_ms: number;
  log: RunLog;
  observe: { key: string; ms: number; bars: number; length: number }[];
}

/** One screen (or one definition's counts) on a snapshot, through core runScreen; `cancelled` is checked between
    tickers (plan.ts). The plan is always asked for (it names the stages and survivors the log explains) and left out of
    the answer unless options.explain. */
export function runTask(task: RunTask, snap: ThreadSnapshot, env: ThreadEnv, cancelled: () => boolean): RunOutcome {
  const t0 = performance.now();
  const s = screenEnv(snap, env, cancelled);
  const r = runScreen(task.definition, s.env, { exhaustive: task.options.exhaustive, explain: true });
  const busy = () => Math.round(performance.now() - t0);
  const log: RunLog = {
    stages: (r.plan?.stages ?? []).map(x => ({ name: x.name, in: x.in, out: x.out, ms: Math.round(x.ms) })), pruned: r.plan?.pruned ?? 0,
    conditions: r.conditions.map(c => ({ id: c.id, source: c.source, evaluated: c.evaluated, exhaustive: c.exhaustive })),
    pinned_hits: s.measured.pinned_hits, lru_hits: s.measured.lru_hits, computed: s.measured.computed,
  };
  const observe = [...s.measured.observe].map(([key, o]) => ({ key, ...o }));
  if (task.kind === 'counts') return { kind: 'counts', gzip: null, etag: null, json_bytes: 0, match_count: r.match_count, near_count: r.near_count, busy_ms: busy(), log, observe };
  // the answer (8.5): schema_version, versions and data open it (edge-bff reads them from the gzip head)
  const answer: RunResponse = {
    schema_version: 1,
    versions: { ...task.versions, definition_hash: task.hash } as Versions,
    data: task.data as DataStatus,
    mode: r.mode, universe: r.universe as UniverseCounts, conditions: r.conditions, need: r.need, match_count: r.match_count, near_count: r.near_count,
    rows: r.rows, warnings: r.warnings,
    timings_ms: { queue: Math.round(task.queue_ms), s0: Math.round(r.timings.s0), s1: Math.round(r.timings.s1), s2: Math.round(r.timings.s2), s3: Math.round(r.timings.s3), s4: Math.round(r.timings.s4), total: 0 },
  };
  if (task.options.explain && r.plan) answer.plan = r.plan;
  answer.timings_ms.total = Math.round(task.queue_ms + task.s0_ms + performance.now() - t0);
  return { kind: 'run', ...pack(answer, env.maxResponseBytes), match_count: r.match_count, near_count: r.near_count, busy_ms: busy(), log, observe };
}

/** An answer's JSON as gzip with its ETag (sha256 of the JSON bytes), or LIMIT_EXCEEDED max_response_bytes. */
export function pack(answer: unknown, maxBytes: number): { gzip: Uint8Array; etag: string; json_bytes: number } {
  const json = Buffer.from(JSON.stringify(answer));
  if (json.byteLength > maxBytes)
    throw refuse('LIMIT_EXCEEDED', `The answer would have ${json.byteLength} bytes of JSON; the limit is ${maxBytes}. Narrow the universe (price, ADV20, sectors) or add a condition so fewer tickers match or come near.`, undefined, { limit: 'max_response_bytes', allowed: maxBytes, needed: json.byteLength });
  const packed = zlib.gzipSync(json, { level: 6 }), gzip = new Uint8Array(packed.byteLength);
  gzip.set(packed);
  return { gzip, etag: `"${crypto.createHash('sha256').update(json).digest('hex')}"`, json_bytes: json.byteLength };
}

/** A run stopped by its cancel flag (plan.ts PlanCancelledError; the caller left, or the deadline passed). */
export const isCancelled = (e: unknown): boolean => (e as Error)?.name === 'PlanCancelledError' || (e as Error)?.name === 'CancelledRun';
export class CancelledRun extends Error { constructor() { super('cancelled'); this.name = 'CancelledRun' } }

/** Every metric reference a definition reads (the presets' references; used where binding is not possible). */
export function definitionRefs(d: Definition | undefined): MetricRef[] {
  const out: MetricRef[] = [];
  const add = (s: unknown) => { if (obj(s) && typeof s.kind === 'string') out.push(s as unknown as MetricRef) };
  for (const c of d?.conditions ?? []) {
    const t = c?.test as unknown as Record<string, any> | undefined;
    if (!t) continue;
    if (t.kind === 'value') add(t.metric);
    else if (t.kind === 'state') { add(t.lhs); add(t.rhs); add(t.pattern) }
    else if (t.kind === 'event') { add(t.signal?.lhs); add(t.signal?.rhs); add(t.signal?.pattern) }
  }
  for (const t of d?.universe?.metric_filters ?? []) add(t?.metric);
  return out;
}
export type { UniverseDef };
