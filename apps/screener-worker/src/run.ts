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
import type { CountsEntry, DataStatus, Definition, MetricRef, PatternRef, RunResponse, UniverseCounts, UniverseDef, Versions } from '../../edge-bff/screener/src/core/contract.ts';
import { METRICS_CATALOG } from '../../edge-bff/screener/src/core/catalog.ts';
import { bindCondition, bindTest } from '../../edge-bff/screener/src/core/condition.ts';
import type { BindContext } from '../../edge-bff/screener/src/core/condition.ts';
import { series, seriesKey, tickerCalc } from '../../edge-bff/screener/src/core/metrics.ts';
import type { ResolvedSeries, SeriesSource, Tail, TickerBars, TickerCalc } from '../../edge-bff/screener/src/core/metrics.ts';
import { costEstimate, costTracker } from '../../edge-bff/screener/src/core/plan.ts';
import type { CostTracker, PlanCondition } from '../../edge-bff/screener/src/core/plan.ts';
import { SBY_ID, SCREENER_REGISTRY } from '../../edge-bff/screener/src/core/registry.ts';
import { CANDLE_IDS } from '../../edge-bff/backtest/src/core/candles.ts';
import { runScreen } from '../../edge-bff/screener/src/core/screen.ts';
import type { ScreenEnv } from '../../edge-bff/screener/src/core/screen.ts';
import { applyUniverse } from '../../edge-bff/screener/src/core/universe.ts';
import { FLOW_BY_ID, FLOW_PRESENCE } from '../../edge-bff/screener/src/core/flowmetrics.ts';
import { operandReach, resolveSignal } from '../../edge-bff/screener/src/core/transforms.ts';
import { definitionHash, validateDefinition } from '../../edge-bff/screener/src/core/validate.ts';
import type { ValidateContext } from '../../edge-bff/screener/src/core/validate.ts';
import { canonicalJson } from '../../edge-bff/backtest/src/core/hash.ts';
import { TickerView, barCount, brokerCounts, brokerRowCount, flowContextOf } from './snapshot.ts';
import { BROKER_DAY_SESSIONS } from './broker.ts';
import type { SnapshotDesc, ThreadSnapshot } from './snapshot.ts';
import { refuse, toApiError } from './errors.ts';

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
    options that change the answer's bytes (exhaustive counts, explain's plan), and flow_data (P4: the broker days the
    answer was computed with; sid names it too). No owner, page or order. */
export const resultKey = (desc: SnapshotDesc, hash: string, options: RunOptionsN, kind = 'run'): string =>
  canonicalJson([kind, desc.sid, desc.versions.screener_engine, desc.versions.registry, desc.versions.screener_registry, desc.versions.flow_data, hash, options.exhaustive, options.explain]);

/* ---- cost (6.10 "Counts and budget") ------------------------------------------------------------------------- */

export const COST_ALPHA = 0.2;          // weight of a new measurement in plan.ts's exponentially weighted mean
/** The cost key of the broker-data series (flowmetrics.ts FLOW_PRESENCE: the candles of a ticker with broker data, read
    once per ticker before its first flow series). */
export const PRESENCE_KEY = `flow:${String((FLOW_PRESENCE.ref as { metric: string }).metric)}`;
/** The cost key of a ticker's window context (flowmetrics.ts contextOf: its rows into FlowRows, once per view, timed
    apart by the thread's meter, snapshot.ts ThreadSnapshot.contexts). */
export const CONTEXT_KEY = 'flow:context';
const CONTEXT_UNIT: CostUnit = { key: CONTEXT_KEY, costClass: 'O(N)', length: 1, flow: { rows: 1, brokers: 0 } };
/** The suffixes of a pattern's unit keys (`pattern:<type>` is its fixed work per bar): the window its core reads, and
    for a recursive pattern (no window) the rule it had before QA unit C, kept (costUnits). */
const PATTERN_WINDOW = ':window', PATTERN_LENGTH = ':length';
/** The prior of a cost key before its first measurement (QA unit B, QA4; screener-overlay.json cost_model.flow,
    measured: verification/screener/BENCHMARK_FLOW_COST.md): a flow kernel's ns per unit of its work (CostUnit flow: a
    broker row read or a cell of the brokers x sessions grid) by how its entry is computed (the registry's `compute`:
    the Terminal's computeFlow, the anchor N sessions back, the Screener's Broker Inventory, the foreign net), a window
    context's and the broker-data series' per row; a pattern's (QA unit C; cost_model.pattern, measured: the same
    section 6) per bar for its fixed work, and a candlestick pattern's per bar and session of the window candles.ts reads
    (an older pattern's window, a registry kernel's, and every other kernel: the indicators' ns per bar and length,
    cost_model.ns_per_bar_length). */
export const costPrior = (key: string): number => {
  const m = SCREENER_REGISTRY.cost_model;
  if (key === PRESENCE_KEY) return m.flow.presence_ns_per_row;
  if (key === CONTEXT_KEY) return m.flow.context_ns_per_row;
  if (key.startsWith('pattern:')) {
    // a candlestick pattern's window is candles.ts's own loops (measured); an older pattern's a registry kernel's
    // (Calc.out: Donchian, a rolling extreme, the stochastic), priced as the indicators are
    if (key.endsWith(PATTERN_WINDOW)) return CANDLE_IDS.includes(key.slice(8, -PATTERN_WINDOW.length)) ? m.pattern.candle_ns_per_bar_session : m.ns_per_bar_length;
    return key.endsWith(PATTERN_LENGTH) ? m.ns_per_bar_length : m.pattern.ns_per_bar;
  }
  if (!key.startsWith('flow:')) return m.ns_per_bar_length;
  const e = FLOW_BY_ID[key.slice(5).split('{')[0]];
  return m.flow.ns_per_unit[e?.compute ?? 'terminal'] ?? m.flow.ns_per_unit.terminal;
};
export const newCostTracker = (): CostTracker => costTracker(costPrior, COST_ALPHA);

/** One kernel a series runs when it is computed: its cost key, class and length (the multiplier of an O(N·n) class);
    bars: the bars it runs over when they are not the ticker's (P5a: an operator on a flow series runs over the loaded
    broker window's sessions); flow: a flow kernel's count is the ticker's broker rows in the window times flow.rows
    plus its brokers in the window times flow.brokers (QA unit B, QA4, measured in BENCHMARK_FLOW_COST.md: computeFlow
    reads every row into its grid of brokers x (sessions + 1) cells per measure, and a Top-N ranking visits every broker
    on every session; the window's context, built once per stock, is costed apart, CONTEXT_KEY; a large stock holds
    some 13,000 rows of 100 brokers, a small one 500 rows of fewer brokers). */
export interface CostUnit { key: string; costClass: 'O(N)' | 'O(N·n)'; length: number; bars?: number; flow?: { rows: number; brokers: number } }
/** Whether a reference reads a flow indicator (directly or through operators). */
const readsFlowRef = (ref: unknown): boolean => obj(ref) && (ref.kind === 'flow' || (ref.kind === 'transform' && (readsFlowRef(ref.of) || (obj(ref.args) && Object.values(ref.args).some(readsFlowRef)))) || (ref.kind === 'rank' && readsFlowRef(ref.of)));
const maxNumber = (m: unknown): number => {
  let n = 1;
  if (obj(m)) for (const v of Object.values(m)) if (typeof v === 'number' && Number.isFinite(v) && v > n) n = v;
  return n;
};
/** The kernels computing a reference runs from the bars (a transform computes its operands in full, through the
    ticker's Calc, whatever is pre-warmed): an indicator with the registry's cost class and the largest value of its
    O(N·n) parameters; a transform as O(N·n) over its largest numeric argument (conservative: a rolling window may be
    linear in its implementation; the measured mean corrects the prediction); a pattern as its fixed work per bar plus
    the window its core reads (QA unit C). */
export function costUnits(ref: unknown, sessions = BROKER_DAY_SESSIONS, reach?: number | null): CostUnit[] {
  if (!obj(ref)) return [];
  switch (ref.kind) {
    // P5a: one computeFlow per (ticker, indicator, parameters) over the window's candles (QA unit B, QA4: a count of
    // sessions said nothing of the work, so a flow condition was predicted about 3000 times too low): its grid reads
    // every row once and holds brokers x (sessions + 1) cells per measure, and a Top-N ranking visits every broker on
    // every session. The window's context it reads is built once per ticker (CONTEXT_KEY, costed and observed apart).
    // The key names the indicator and its choices (the select and switch parameters that decide what it computes:
    // FL23's Top-K holders cost several times its selected brokers), so each is learned on its own.
    // P5b: an anchored entry (anchor_sessions N) runs one computeFlow over N + 1 candles per session it computes: every
    // session of the window from the N-th on, or, resolved for a screen under a reach R (metrics.ts flowReach), the
    // last R + 1 (flowmetrics.ts lazy series); each call reads its slice's rows, about rows x (N + 1) / sessions, and
    // its grid of brokers x (N + 2) cells. The broker-data series reads the rows' dates once.
    case 'flow': {
      const id = String(ref.metric), e = FLOW_BY_ID[id];
      if (`flow:${id}` === PRESENCE_KEY) return [{ key: PRESENCE_KEY, costClass: 'O(N)', length: 1, flow: { rows: 1, brokers: 0 } }];
      const p = obj(ref.params) ? ref.params : {};
      const choices = (e?.params ?? []).filter(q => q.condition && (q.kind === 'select' || q.kind === 'bool')).map(q => `${q.key}=${String(p[q.key] ?? q.default)}`);
      const key = `flow:${id}${choices.length ? `{${choices.join(',')}}` : ''}`;
      if (e?.compute === 'anchored') {
        const n = Number(p.anchor_sessions ?? e.params.find(q => q.key === 'anchor_sessions')?.default) || 1;
        const computed = Math.max(1, typeof reach === 'number' ? Math.min(sessions - n, reach + 1) : sessions - n);
        return [{ key, costClass: 'O(N)', length: 1, flow: { rows: computed * (n + 1) / sessions, brokers: computed * (n + 2) } }];
      }
      return [{ key, costClass: 'O(N)', length: 1, flow: { rows: 1, brokers: sessions + 1 } }];
    }
    case 'indicator': {
      const ind = SBY_ID[ref.indicator as string];
      if (!ind) return [];
      const params = obj(ref.params) ? ref.params : {};
      const length = Math.max(1, ...ind.params.filter(p => p.cost_class === 'O(N·n)').map(p => Number(params[p.key] ?? p.default) || 1));
      return [{ key: `indicator:${ind.key}`, costClass: ind.cost_class === 'O(N·n)' ? 'O(N·n)' : 'O(N)', length }];
    }
    case 'transform': {
      // its operands under the reach it gives them (transforms.ts operandReach, as the core resolves them)
      const r2 = operandReach(String(ref.fn), obj(ref.args) ? ref.args : {}, reach, obj(ref.of) ? ref.of.kind : null);
      const inner = costUnits(ref.of, sessions, r2);
      if (obj(ref.args)) for (const a of Object.values(ref.args)) if (obj(a)) inner.push(...costUnits(a, sessions, r2));
      // an operator on a flow series works on the window's values only (the bars before it are empty)
      return [...inner, { key: `transform:${String(ref.fn)}`, costClass: 'O(N·n)', length: maxNumber(ref.args), ...(readsFlowRef(ref) ? { bars: sessions } : {}) }];
    }
    // QA unit C (verification/screener/BENCHMARK_FLOW_COST.md section 6): a pattern's work per bar is a fixed part (its
    // guards, its rules and the copies of the bars: an O(N) unit) plus one step per session of the window its core reads
    // (an O(N·n) unit of that length: candles.ts candleLookback for a candlestick pattern, transforms.ts PATTERNS window
    // for the others; transforms.ts resolveSignal's window, its parameters completed), never the largest parameter value
    // (min_range_ticks 50 is no length; Hammer's 30 % body was taken as one, and its 10-session trend was not). The key
    // is the pattern's type, so each pattern is learned on its own. A recursive pattern (window Infinity, the
    // whole history: macd_divergence) keeps, beside its fixed part, the O(N·n) unit over its largest parameter it had:
    // its work was measured flat in its parameters, but dropping that unit lowers its class, which needs a reviewed
    // reason first (ERRORS M300).
    case 'pattern': {
      const s = resolveSignal(ref as unknown as PatternRef, 'pattern', { capBudgetMs: Infinity }), type = (s.ref as PatternRef).type;
      return [{ key: `pattern:${type}`, costClass: 'O(N)', length: 1 },
        Number.isFinite(s.window) ? { key: `pattern:${type}${PATTERN_WINDOW}`, costClass: 'O(N·n)', length: s.window }
          : { key: `pattern:${type}${PATTERN_LENGTH}`, costClass: 'O(N·n)', length: maxNumber((s.ref as PatternRef).params) }];
    }
    case 'rank': return costUnits(ref.of, sessions, reach);    // operator 11: the ranked series is what is computed
  }
  return [];
}
/** A ticker's broker data in the loaded window as the flow costs read it: its rows and its distinct brokers. */
export interface FlowSize { rows: number; brokers: number }
const NO_FLOW: FlowSize = { rows: 0, brokers: 0 };
/** What a unit runs over on a ticker of `bars` bars and broker data `f`. */
const unitBars = (u: CostUnit, bars: number, f: FlowSize): number => u.flow ? f.rows * u.flow.rows + f.brokers * u.flow.brokers : u.bars ?? bars;
/** Predicted ms of computing one series on one ticker of `bars` bars and broker data `f` in the loaded window (under the
    reach it was resolved with, P5b). */
export const predictMs = (tracker: CostTracker, r: Pick<ResolvedSeries, 'ref' | 'flowReach'>, bars: number, sessions = BROKER_DAY_SESSIONS, f: FlowSize = NO_FLOW): number =>
  costUnits(r.ref, sessions, r.flowReach).reduce((s, u) => s + tracker.predict(u.key, u.costClass, u.length, unitBars(u, bars, f)), 0);

/** The parts of a held snapshot the estimate reads. */
export interface CostView { desc: SnapshotDesc; pinned: Set<string>; position: Map<string, number>; index: TickerBars }
export interface Estimate { needed_ms: number; costliest: string | null; perTicker: number; eligible: number; s0_ms: number }
/** The worst case of a definition on its S0 survivors (header). `only`: one ticker (a preview). */
export function estimateCost(def: Definition, held: CostView, tracker: CostTracker, env: { capBudgetMs: number; withinMax: number }, only?: string): Estimate {
  const t0 = performance.now();
  const u = only === undefined ? applyUniverse(held.desc.rows, def.universe) : null;
  const survivors = only === undefined ? (u as ReturnType<typeof applyUniverse>).eligible.map(r => r.ticker) : [only];
  const s0_ms = performance.now() - t0;
  let bars = 0, rows = 0, brokers = 0;
  const counts = brokerCounts(held.desc);
  for (const t of survivors) { const j = held.position.get(t); if (j !== undefined) { bars += barCount(held.desc, j); rows += brokerRowCount(held.desc, j); brokers += counts[j] } }
  const n = survivors.length || 1, avg = bars / n, avgRows: FlowSize = { rows: rows / n, brokers: brokers / n };
  const dv = { price_data: held.desc.versions.price_data, screener_engine: held.desc.versions.screener_engine };
  const flow = flowContextOf(held.desc), sessions = flow.sessions || BROKER_DAY_SESSIONS;
  // bound as runScreen binds a screen (screen.ts screenBinding: an anchored flow series is computed where it is read)
  const ctx: BindContext = { capBudgetMs: env.capBudgetMs, index: held.index, withinMax: env.withinMax, catalog: METRICS_CATALOG, flow, flowLazy: true };
  const pinned = (r: ResolvedSeries) => r.kind === 'price' || held.pinned.has(seriesKey(dv, r));   // a bar field is the snapshot itself (screen.ts)
  let readsFlow = false;
  const conds: PlanCondition[] = def.conditions.flatMap((c, k) => {
    if (!c.enabled) return [];
    const b = bindCondition(c, `definition.conditions[${k}]`, ctx);
    const stage = b.xsection ? 'S1' : b.universeAttr !== null || b.series.every(pinned) ? 'S2' : 'S3';
    // a rank across stocks (S1, operator 11) computes its series on every survivor: costed as screen.ts does
    const computes = stage === 'S3' || !!b.xsection?.rankOf;
    if (computes && b.readsFlow) readsFlow = true;
    const predictedMs = computes ? b.series.filter(r => !pinned(r)).reduce((ms, r) => ms + predictMs(tracker, r, avg, sessions, avgRows), 0) : 0;
    return [{ id: c.id, stage, predictedMs, evaluate: () => { throw new Error('estimate only') } }];
  });
  const est = costEstimate(conds, survivors.length);
  // the metric filters the core evaluates in S0 (universe.ts pending): on every survivor, never pruned
  let filters = 0;
  if (u) for (const i of u.pending) {
    const b = bindTest(`f${i}`, (def.universe.metric_filters ?? [])[i], `definition.universe.metric_filters[${i}]`, { ...ctx, place: 'filter' });
    if (b.readsFlow) readsFlow = true;
    filters += b.series.filter(r => !pinned(r)).reduce((ms, r) => ms + predictMs(tracker, r, avg, sessions, avgRows), 0) * survivors.length;
  }
  // a flow condition first reads the broker-data series of each ticker (condition.ts withFlow), then builds the window's
  // context (CONTEXT_KEY): once per ticker, whatever the number of flow conditions
  const presence = readsFlow ? (predictMs(tracker, FLOW_PRESENCE, avg, sessions, avgRows) + tracker.predict(CONTEXT_KEY, 'O(N)', 1, unitBars(CONTEXT_UNIT, avg, avgRows))) * survivors.length : 0;
  const perTicker = conds.reduce((s, c) => s + c.predictedMs, 0);
  return { needed_ms: Math.ceil(est.needed_ms + filters + presence), costliest: est.costliest, perTicker, eligible: survivors.length, s0_ms };
}

/* ================================================================================================================ */
/* compute thread                                                                                                  */
/* ================================================================================================================ */

export interface ThreadEnv { capBudgetMs: number; withinMax: number; maxResponseBytes: number }
/** Tickers whose price columns and Calc (with its memo of full outputs) one request keeps: the planner holds every
    survivor's view to the end of the screen, so a view that falls out of this LRU (by its last use) is released
    (snapshot.ts TickerView.release) and makes them again if it is read later. Bounds a request's transient memory to
    about this many tickers' bars and outputs, whatever the number of custom series. */
export const CALC_KEEP = 256;

/** The measured time of the series of one cost signature (their units' keys, classes and lengths) a request computed
    cold: the sum of their ms and, per unit, of the bars (or broker rows) it ran over; the main thread shares the time
    among the units in proportion to their predicted cost (plan.ts observeShared), so a series of several kernels (a flow
    indicator under an operator) teaches the model too. */
export interface Observation { units: { key: string; costClass: 'O(N)' | 'O(N·n)'; length: number }[]; ms: number; bars: number[]; series: number }
/** What a request measured on the snapshot: pinned tails read, series computed, of them those that reused work made
    before (a memo entry of an earlier series: not a cold measurement, not observed), and the observations by cost
    signature. */
export interface Measured { pinned_hits: number; lru_hits: number; computed: number; reused: number; observe: Map<string, Observation> }

/** The snapshot as screen.ts reads it (header). A ticker is the thread's TickerView (dates kept by the thread, columns
    and Calc made on first use, missingInput from the snapshot's mask), so a screen of pre-warmed series is lookups
    only; the LRU of views is touched on every use and releases what falls out of it (CALC_KEEP). Each resolved
    series' cache key is computed once per request. */
export function screenEnv(snap: ThreadSnapshot, env: ThreadEnv, cancelled: () => boolean, keep = CALC_KEEP): { env: ScreenEnv; measured: Measured; calc(ticker: string): TickerCalc | undefined } {
  const calcs = new Map<string, TickerView>();
  const measured: Measured = { pinned_hits: 0, lru_hits: 0, computed: 0, reused: 0, observe: new Map() };
  const sctx = { versions: snap.dv, tailLength: snap.desc.tailLength, cache: snap.cache };
  const keys = new WeakMap<ResolvedSeries, string>();
  const keyOf = (r: ResolvedSeries): string => { let k = keys.get(r); if (k === undefined) keys.set(r, k = seriesKey(snap.dv, r)); return k };
  const touch = (ticker: string, c: TickerView): void => {
    calcs.delete(ticker); calcs.set(ticker, c);
    if (calcs.size > keep) { const [k, old] = calcs.entries().next().value as [string, TickerView]; calcs.delete(k); old.release() }
  };
  const calc = (ticker: string): TickerView | undefined => {
    const c = calcs.get(ticker) ?? snap.view(ticker);
    if (c) touch(ticker, c);
    return c;
  };
  // P5a: a flow condition is bound against the snapshot's loaded window (K1 depth, anchors); its availability (a
  // window still loading) was checked on the main thread with the current publication's data (validate.ts), so a
  // thread never refuses it again on its own copy of that data
  const flow = { ...snap.flowContext, complete: true }, sessions = flow.sessions || BROKER_DAY_SESSIONS, avgRows = snap.avgFlowSize;
  /** sums one measurement into its cost signature's observation (the units' keys, classes and lengths) */
  const record = (units: CostUnit[], ms: number, bars: number[], n: number): void => {
    const sig = units.map(u => `${u.key}|${u.costClass}|${u.length}`).join(';');
    let o = measured.observe.get(sig);
    if (!o) measured.observe.set(sig, o = { units: units.map(u => ({ key: u.key, costClass: u.costClass, length: u.length })), ms: 0, bars: units.map(() => 0), series: 0 });
    o.ms += Math.max(0, ms); o.series += n;
    bars.forEach((b, k) => { o.bars[k] += b });
  };
  const screen: ScreenEnv = {
    capBudgetMs: env.capBudgetMs, index: snap.ihsg, withinMax: env.withinMax, catalog: METRICS_CATALOG, flow,
    evaluationDate: snap.desc.data.evaluation_date, rows: snap.desc.rows, ihsgCalendar: snap.ihsgCalendar,
    bars: ticker => calc(ticker),
    series(r: ResolvedSeries, t: TickerBars): { tail: Tail; source: SeriesSource } {
      const hit = snap.cache.get(keyOf(r), t.ticker);
      if (hit) { if (hit.pinned) measured.pinned_hits++; else measured.lru_hits++; return { tail: hit.tail, source: hit.pinned ? 'precomputed' : 'dynamic' } }
      if (t instanceof TickerView) touch(t.ticker, t);
      const tc = t instanceof TickerView || (t as TickerCalc).calc ? t as TickerCalc : tickerCalc(t);
      snap.reuse.begin();
      const c0 = snap.contexts.ms, r0 = snap.contexts.rows, n0 = snap.contexts.built;
      const t0 = performance.now(), out = series(sctx, tc, r), ms = performance.now() - t0;
      measured.computed++;
      // the window's context this series built (once per view): its own cost, observed on its own
      if (snap.contexts.built > n0) record([{ ...CONTEXT_UNIT }], snap.contexts.ms - c0, [snap.contexts.rows - r0], snap.contexts.built - n0);
      // QA unit B, QA4: every series computed cold teaches the cost model, whatever the number of its kernels (one that
      // read a memo entry of an earlier series did less than its units say: not observed)
      if (snap.reuse.reused) { measured.reused++; return out }
      const units = costUnits(r.ref, sessions, r.flowReach);
      if (!units.length) return out;
      const f = t instanceof TickerView ? t.flowSize : NO_FLOW;
      record(units, ms - (snap.contexts.ms - c0), units.map(u => unitBars(u, t.dates.length, f)), 1);
      return out;
    },
    isPrewarmed: r => snap.pinned.has(keyOf(r)),
    predictMs: (r, bars) => predictMs(threadTracker, r, bars, sessions, avgRows),
    xsectionValues: need => snap.crossSection(need),
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
/** The counts answer's entries, one per requested definition in request order (contract.ts CountsEntry[]): its cached
    counts or its refusal (`settled[k]`, null while it waits for the thread), else the thread's answer for its item_id
    (item ids are unique, countsEnvelope); an item the thread did not answer becomes that entry's error, as an
    unexpected failure of the thread is (errors.ts toApiError: INTERNAL_ERROR, the detail in the log), never a null
    entry the contract does not allow. `missing` names those items for the log. */
export function countsAnswer(defs: readonly { item_id: string }[], settled: readonly (CountsEntryOut | null)[], computed: readonly CountsEntryOut[]): { counts: CountsEntry[]; missing: string[] } {
  const by = new Map(computed.map(g => [g.item_id, g])), missing: string[] = [];
  const counts = defs.map((d, k): CountsEntry => {
    const x = settled[k] ?? by.get(d.item_id);
    if (!x) { missing.push(d.item_id); return { item_id: d.item_id, error: toApiError(new Error('counts: the thread answered no entry for this item')).error } }
    return 'error' in x ? { item_id: x.item_id, error: x.error } : { item_id: x.item_id, match_count: x.match_count, near_count: x.near_count };
  });
  return { counts, missing };
}
export interface RunLog { stages: { name: string; in: number; out: number; ms: number }[]; conditions: { id: string; source: string; evaluated: number; exhaustive: boolean }[]; pruned: number; pinned_hits: number; lru_hits: number; computed: number; reused: number }
export interface RunOutcome {
  kind: 'run' | 'counts';
  gzip: Uint8Array | null; etag: string | null; json_bytes: number;
  match_count: number; near_count: number; busy_ms: number;
  log: RunLog;
  observe: Observation[];
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
    pinned_hits: s.measured.pinned_hits, lru_hits: s.measured.lru_hits, computed: s.measured.computed, reused: s.measured.reused,
  };
  const observe = [...s.measured.observe.values()];
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
    let t = c?.test as unknown as Record<string, any> | undefined;
    if (t?.kind === 'window') t = t.test;                     // operators 5, 9, 10: the inner comparison's references
    if (!t) continue;
    if (t.kind === 'value') add(t.metric);
    else if (t.kind === 'state') { add(t.lhs); add(t.rhs); add(t.pattern) }
    else if (t.kind === 'event') { add(t.signal?.lhs); add(t.signal?.rhs); add(t.signal?.pattern) }
  }
  for (const t of d?.universe?.metric_filters ?? []) add(t?.metric);
  return out;
}
export type { UniverseDef };
