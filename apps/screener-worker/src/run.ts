/* POST /v1/run and POST /v1/counts: a definition -> its result, through the screener core only (report TARGET
   ARCHITECTURE 6.9 condition engine, 6.10 planner; API CONTRACT 8.5, 8.6). The worker computes nothing of its own:
   validation (validate.ts), S0 (universe.ts applyUniverse), every series (metrics.ts series(), the one path), every
   test (evaluate.ts), the cross-section (xsection.ts), patterns (transforms.ts), match and near (match.ts) and the
   planner (plan.ts runPlan) are the core's. This file binds them: it turns each enabled condition of a validated
   definition into a plan.ts PlanCondition whose evaluate(ticker) is pure, and turns the plan's rows into the wire answer.

   Main thread (prepare): the request envelope, validateDefinition, definition_hash, the result cache (keyed by the
   snapshot, the engine and registry versions, the definition hash and the options that change the answer; nothing of the
   owner), S0, and the worst-case cost (6.10 "Counts and budget") before any compute.
   Compute thread (runScreen): the plan on the snapshot the request is pinned to, the answer built and gzipped there (no
   JSON work on the HTTP thread), its size held to SCREENER_MAX_RESPONSE_BYTES.

   Binding rules the core leaves to its caller (each from the report, cited):
   - evaluation bar: each ticker at its own last bar on or before E (evaluate.ts evaluationBar; 6.5);
   - a series side is viewOfTail(series(...).tail, missing input) (INTERFACES "For the core-logic and worker agents");
     the snapshot holds each ticker's missing bar fields over its whole history, which is missingInput at its last bar;
   - same-bar comparison lag (6.8, review item 7): a STATE or EVENT that compares a price field with an indicator output
     whose price_compare_lag for that direction is 1 (Donchian's bands) reads the output through transform
     lag(output, 1), resolved as a series of its own, never a shifted view;
   - PRICE_BREAK_IN_LOOKBACK (P4.1 A, 6.12): only on a row with PRICE_BREAK remarks; each series side's lookback from
     evaluate.ts lookbackStart (an EVENT's sides extended by `within`); a pattern side reads the whole history
     (conservative: a remark may be over-set, never missed); return_rank from at - window (xsection.ts); universe
     attributes and flow never;
   - stages: S1 cross-section, S2 every series pre-warmed (pinned), S3 the rest, ordered by predicted cost;
   - source: 'xsection', 'precomputed' (every series of the condition pinned) or 'dynamic' (8.5);
   - is_default: every indicator the condition reads is at its registry defaults (registry.ts isDefaultParams). */
import zlib from 'node:zlib';
import crypto from 'node:crypto';
import type {
  Cell, ConditionDef, ConditionSummary, Definition, DataStatus, IndicatorRef, MetricRef, ParamMap, PatternRef, PlanExplain,
  ResultRow, RunResponse, Side, Test, UniverseCounts, UniverseDef, UniverseRow, ValueTest, Versions, Warning, XsectionRef,
} from '../../edge-bff/screener/src/core/contract.ts';
import { CONDITION_ID } from '../../edge-bff/screener/src/core/contract.ts';
import { ScreenerError } from '../../edge-bff/screener/src/core/errors.ts';
import {
  crossSignal, evaluateEvent, evaluateState, evaluateStatePattern, evaluateValue, evaluationBar, lookbackStart, priceBreakRemark,
  round12, toCell, viewOfTail,
} from '../../edge-bff/screener/src/core/evaluate.ts';
import type { BarView, Evaluation, Operand } from '../../edge-bff/screener/src/core/evaluate.ts';
import { needOf, rowStatus } from '../../edge-bff/screener/src/core/match.ts';
import { missingInput, resolveSeries, series, seriesKey, tickerCalc } from '../../edge-bff/screener/src/core/metrics.ts';
import type { ResolvedIndicator, ResolvedSeries, Tail, TickerCalc } from '../../edge-bff/screener/src/core/metrics.ts';
import { costTracker, runPlan } from '../../edge-bff/screener/src/core/plan.ts';
import type { CostTracker, PlanCondition, PlanOutput } from '../../edge-bff/screener/src/core/plan.ts';
import { SBY_ID, SCREENER_REGISTRY } from '../../edge-bff/screener/src/core/registry.ts';
import type { ParamOptions } from '../../edge-bff/screener/src/core/registry.ts';
import { patternSignal } from '../../edge-bff/screener/src/core/transforms.ts';
import { applyUniverse } from '../../edge-bff/screener/src/core/universe.ts';
import { definitionHash, validateDefinition } from '../../edge-bff/screener/src/core/validate.ts';
import type { ValidateContext } from '../../edge-bff/screener/src/core/validate.ts';
import { rankPopulation, returnRank } from '../../edge-bff/screener/src/core/xsection.ts';
import { canonicalJson } from '../../edge-bff/backtest/src/core/hash.ts';
import { byTicker } from '../../edge-bff/backtest/src/core/signals.ts';
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
/* main thread: what a held snapshot needs to validate, cost and cache                                             */
/* ================================================================================================================ */

/** The parts of a snapshot the HTTP thread reads (server.ts Held). */
export interface HeldView {
  desc: SnapshotDesc;
  vctx: ValidateContext;
  pinned: Set<string>;                // SeriesCache keys of the pre-warmed series
  position: Map<string, number>;
}

/** The normalized definition and its hash (validate.ts; 8.3), or the first refusal. */
export async function normalize(definition: unknown, vctx: ValidateContext, field = 'definition'): Promise<{ normalized: Definition; hash: string }> {
  const normalized = validateDefinition(definition, vctx, field);
  return { normalized, hash: await definitionHash(normalized) };
}

/** The result cache key (8.10, 6d.2): the snapshot, the engine and registry versions, the definition hash and the two
    options that change the answer's bytes (exhaustive counts, explain's plan). No owner, page or order. */
export const resultKey = (desc: SnapshotDesc, hash: string, options: RunOptionsN, kind = 'run'): string =>
  canonicalJson([kind, desc.sid, desc.versions.screener_engine, desc.versions.registry, desc.versions.screener_registry, hash, options.exhaustive, options.explain]);

/** S0 on the snapshot's universe rows (the page's own function, universe.ts). */
export function stage0(desc: SnapshotDesc, universe: UniverseDef) {
  const t0 = performance.now();
  const r = applyUniverse(desc.rows, universe);
  return { ...r, ms: performance.now() - t0 };
}

/* ---- cost (6.10 "Counts and budget": the worst case, costed before running) ------------------------------------ */

export const COST_ALPHA = 0.2;          // weight of a new measurement in plan.ts's exponentially weighted mean
export const newCostTracker = (): CostTracker => costTracker(SCREENER_REGISTRY.cost_model.ns_per_bar_length, COST_ALPHA);

/** One series a condition may have to compute: its cost key (what plan.ts calibrates by), class and length. */
interface CostUnit { key: string; costClass: 'O(N)' | 'O(N·n)'; length: number }
const maxNumber = (m: Record<string, unknown> | undefined): number => {
  let n = 1;
  for (const v of Object.values(m ?? {})) if (typeof v === 'number' && Number.isFinite(v) && v > n) n = v;
  return n;
};
/** The cost units of a reference that are not pre-warmed (a pinned series costs a lookup). Indicators: the registry's
    cost class and the largest value of its O(N·n) parameters; a transform: its operands plus itself, a pattern: itself,
    both costed as O(N·n) over their largest numeric argument (conservative: their kernels are the core's). */
export function costUnits(ref: MetricRef | Side, field: string, held: Pick<HeldView, 'pinned' | 'desc'>, opts: ParamOptions & { index: any }): CostUnit[] {
  if (!ref || typeof ref !== 'object' || !('kind' in ref)) return [];
  const dv = { price_data: held.desc.versions.price_data, screener_engine: held.desc.versions.screener_engine };
  const pinnedRef = (r: MetricRef) => { try { return held.pinned.has(seriesKey(dv, resolveSeries(r, field, opts))) } catch { return false } };
  switch (ref.kind) {
    case 'price': case 'universe': case 'flow': case 'xsection': return [];
    case 'indicator': {
      if (pinnedRef(ref)) return [];
      const ind = SBY_ID[ref.indicator];
      if (!ind) return [];
      const r = resolveSeries(ref, field, opts) as ResolvedIndicator;
      const length = Math.max(1, ...ind.params.filter(p => p.cost_class === 'O(N·n)').map(p => Number(r.params[p.key]) || 1));
      return [{ key: `indicator:${ind.key}`, costClass: ind.cost_class === 'O(N·n)' ? 'O(N·n)' : 'O(N)', length }];
    }
    case 'transform': {
      if (pinnedRef(ref)) return [];
      const inner = costUnits(ref.of, `${field}.of`, held, opts);
      for (const [k, a] of Object.entries(ref.args ?? {})) if (a && typeof a === 'object') inner.push(...costUnits(a as MetricRef, `${field}.args.${k}`, held, opts));
      return [...inner, { key: `transform:${ref.fn}`, costClass: 'O(N·n)', length: maxNumber(ref.args as Record<string, unknown>) }];
    }
    case 'pattern': return [{ key: `pattern:${ref.type}`, costClass: 'O(N·n)', length: maxNumber(ref.params) }];
  }
  return [];
}
/** The references a test reads. */
export function testRefs(t: Test): { ref: MetricRef | Side; path: string }[] {
  if (t.kind === 'value') return [{ ref: t.metric, path: 'metric' }];
  if (t.kind === 'state') return 'pattern' in t ? [{ ref: t.pattern, path: 'pattern' }] : [{ ref: t.lhs, path: 'lhs' }, { ref: t.rhs, path: 'rhs' }];
  const s = t.signal;
  return 'pattern' in s ? [{ ref: s.pattern, path: 'signal.pattern' }] : [{ ref: s.lhs, path: 'signal.lhs' }, { ref: s.rhs, path: 'signal.rhs' }];
}
export interface ConditionCost { id: string; predictedMs: number; units: CostUnit[] }
/** The worst case of a definition on its S0 survivors: every non-pinned series of every enabled condition (and of every
    pending metric filter) computed on every survivor's full history; costliest = the condition with the largest share. */
export function estimateCost(def: Definition, survivors: readonly string[], held: HeldView, tracker: CostTracker, opts: ParamOptions & { index: any }): { needed_ms: number; costliest: string | null; conditions: ConditionCost[] } {
  let bars = 0;
  for (const t of survivors) { const j = held.position.get(t); if (j !== undefined) bars += barCount(held.desc, j) }
  const list: ConditionCost[] = [];
  const cost = (id: string, test: Test, field: string) => {
    const units = testRefs(test).flatMap(x => costUnits(x.ref, `${field}.${x.path}`, held, opts));
    list.push({ id, units, predictedMs: units.reduce((s, u) => s + tracker.predict(u.key, u.costClass, u.length, bars), 0) });
  };
  def.conditions.forEach((c, k) => { if (c.enabled) cost(c.id, c.test, `definition.conditions[${k}].test`) });
  (def.universe.metric_filters ?? []).forEach((t, k) => cost(`universe.metric_filters[${k}]`, t, `definition.universe.metric_filters[${k}]`));
  let needed = 0, costliest: string | null = null, top = 0;
  for (const c of list) { needed += c.predictedMs; if (c.predictedMs > top) { top = c.predictedMs; costliest = c.id } }
  return { needed_ms: Math.ceil(needed), costliest, conditions: list };
}

/* ================================================================================================================ */
/* compute thread: the binding                                                                                    */
/* ================================================================================================================ */

export interface ThreadEnv { capBudgetMs: number; withinMax: number; maxResponseBytes: number }
interface TickerCtx { ticker: string; tc: TickerCalc; at: number; dates: readonly string[]; missing: Set<string>; exDates: string[] | null; n: number }

/** A short name of a reference for summaries and overlays: I01.sma, close, pct_distance(I01.sma), pattern.breakout. */
export function refName(r: MetricRef): string {
  switch (r.kind) {
    case 'indicator': return `${r.indicator}.${r.output}`;
    case 'price': return r.field;
    case 'transform': return `${r.fn}(${refName(r.of)})`;
    case 'pattern': return `pattern.${r.type}`;
    case 'flow': return `flow.${r.metric}`;
    case 'xsection': return `xsection.${r.metric}`;
    case 'universe': return `universe.${r.attr}`;
  }
}
const isRef = (s: Side | undefined): s is MetricRef => !!s && typeof s === 'object' && 'kind' in s;
const isSeriesRef = (s: Side): s is MetricRef => isRef(s) && (s.kind === 'indicator' || s.kind === 'price' || s.kind === 'transform');

/** A bound side: a constant, or a series with its resolution. */
type BoundSide = { kind: 'const'; value: number } | { kind: 'series'; r: ResolvedSeries; ref: MetricRef };
export interface BoundCondition {
  id: string; def: ConditionDef | null; test: Test;
  stage: 'S1' | 'S2' | 'S3'; source: ConditionSummary['source'];
  metric: string; params_resolved: ParamMap; is_default: boolean; unit: string | null;
  sides: BoundSide[];                  // the series sides (overlays, keys)
  keys: string[];                      // SeriesCache keys of its series
  evaluate(c: TickerCtx): { e: Evaluation; starts: (number | null)[] | null; marker: ((i: number) => boolean) | null };
  ms: number; tickers: number;        // measured on this request (log, cost calibration)
}

/** The lag rule (header): the lag of `output` op price for a compared price field, from the registry's probe. */
function compareLag(r: ResolvedSeries, op: string, priceIsLhs: boolean): number {
  const lagOf = (r as Partial<ResolvedIndicator>).output?.price_compare_lag ?? (r as { priceCompareLag?: { gt: number; lt: number } }).priceCompareLag;
  if (!lagOf) return 0;
  const up = op === 'gt' || op === 'crosses_above';
  // price gt output -> lag.gt; output gt price = price lt output -> lag.lt
  return (priceIsLhs ? up : !up) ? lagOf.gt : lagOf.lt;
}

/** Everything one request needs on one snapshot: the resolved conditions, per-ticker contexts, the cross-section. */
export class Binder {
  snap: ThreadSnapshot; env: ThreadEnv; def: Definition; opts: ParamOptions & { index: any };
  conditions: BoundCondition[] = [];
  filters: BoundCondition[] = [];
  xsMs = 0;
  private ctxs = new Map<string, TickerCtx>();
  private xs = new Map<string, { window: number; ranks: Map<string, number | null> }>();
  private sctx: { versions: { price_data: string; screener_engine: string }; tailLength: number; cache: ThreadSnapshot['cache'] };
  pinnedHits = 0;
  static CTX_KEEP = 256;              // tickers whose bars and Calc are kept during one request (LRU)

  constructor(snap: ThreadSnapshot, env: ThreadEnv, def: Definition, pending: readonly number[] = []) {
    this.snap = snap; this.env = env; this.def = def;
    this.opts = { capBudgetMs: env.capBudgetMs, index: snap.ihsg };
    this.sctx = { versions: snap.dv, tailLength: snap.desc.tailLength, cache: snap.cache };
    def.conditions.forEach((c, k) => { if (c.enabled) this.conditions.push(this.bind(c.id, c, c.test, `definition.conditions[${k}].test`)) });
    for (const k of pending) {
      const t = (def.universe.metric_filters ?? [])[k];
      if (t) this.filters.push(this.bind(`f${k}`, null, t, `definition.universe.metric_filters[${k}]`));
    }
  }

  /** The ticker's context (bars materialized and a Calc, kept for CTX_KEEP tickers). */
  ctx(ticker: string): TickerCtx {
    let c = this.ctxs.get(ticker);
    if (c) { this.ctxs.delete(ticker); this.ctxs.set(ticker, c); return c }
    const tb = this.snap.bars(ticker), tc = tickerCalc(tb), dates = tb.dates;
    c = { ticker, tc, at: evaluationBar(dates, this.snap.desc.data.evaluation_date), dates, n: dates.length,
      missing: new Set(this.snap.missingFields(ticker)), exDates: this.snap.breaks.get(ticker) ?? null };
    this.ctxs.set(ticker, c);
    if (this.ctxs.size > Binder.CTX_KEEP) this.ctxs.delete(this.ctxs.keys().next().value as string);
    return c;
  }

  private resolve(ref: MetricRef, field: string): ResolvedSeries { return resolveSeries(ref, field, this.opts) }
  private sideOf(s: Side, field: string): BoundSide {
    if (isSeriesRef(s)) return { kind: 'series', r: this.resolve(s, field), ref: s };
    if (!isRef(s) && typeof (s as { value?: unknown }).value === 'number') return { kind: 'const', value: (s as { value: number }).value };
    throw new ScreenerError('INVALID_CONDITION', `${field}: a ${JSON.stringify((s as { kind?: unknown }).kind)} reference cannot be a side of a comparison.`, field);
  }
  /** lhs and rhs of a comparison with the lag rule applied (header). */
  private compared(lhs: Side, rhs: Side, op: string, field: string): [BoundSide, BoundSide] {
    let l = this.sideOf(lhs, `${field}.lhs`), r = this.sideOf(rhs, `${field}.rhs`);
    const lagged = (b: BoundSide, f: string): BoundSide => b.kind === 'series'
      ? { kind: 'series', ref: { kind: 'transform', fn: 'lag', of: b.ref, args: { bars: 1 } }, r: this.resolve({ kind: 'transform', fn: 'lag', of: b.ref, args: { bars: 1 } }, f) } : b;
    if (l.kind === 'series' && l.r.kind === 'price' && r.kind === 'series' && r.r.kind === 'indicator' && compareLag(r.r, op, true) === 1) r = lagged(r, `${field}.rhs`);
    else if (r.kind === 'series' && r.r.kind === 'price' && l.kind === 'series' && l.r.kind === 'indicator' && compareLag(l.r, op, false) === 1) l = lagged(l, `${field}.lhs`);
    return [l, r];
  }
  /** The tail, its view and where it came from. */
  private view(b: Extract<BoundSide, { kind: 'series' }>, c: TickerCtx): { view: BarView; tail: Tail } {
    const { tail, source } = series(this.sctx, c.tc, b.r);
    if (source === 'precomputed') this.pinnedHits++;
    const missing = c.at === c.n - 1 ? b.r.inputs.some(f => c.missing.has(f)) : missingInput(c.tc, b.r.inputs, c.at) !== null;
    return { view: viewOfTail(tail, missing), tail };
  }
  private operand(b: BoundSide, c: TickerCtx, extra: number): { op: Operand; start: number | null } {
    if (b.kind === 'const') return { op: b.value, start: c.at };
    const { view, tail } = this.view(b, c);
    return { op: view, start: lookbackStart(b.r.historyClass, tail.firstValid, c.at, extra) };
  }

  /** return_rank on the fixed population (P7; xsection.ts), once per window and request: the population is the
      tickers with a finite return at E among the rows rankPopulation keeps (stale and price-break rows out). */
  private ranks(ref: XsectionRef, field: string): { window: number; ranks: Map<string, number | null> } {
    const window = Number(ref.params?.window);
    if (!Number.isSafeInteger(window) || window < 1) throw new ScreenerError('INVALID_CONDITION', `${field}.params.window must be a whole number of sessions.`, `${field}.params.window`);
    const k = `${ref.metric}:${window}`;
    let x = this.xs.get(k);
    if (x) return x;
    const t0 = performance.now(), d = this.snap.desc;
    const closes = new Map<string, { at: number; close: ArrayLike<number | null> }>();
    for (const r of d.rows) {
      const j = this.snap.position.get(r.ticker)!, a = d.offsets[j], n = d.offsets[j + 1] - a;
      closes.set(r.ticker, { at: evaluationBarOf(d, j, d.data.evaluation_date), close: d.C.subarray(a, a + n) });
    }
    const everyone = new Set(d.rows.map(r => r.ticker));
    const finite = new Map<string, number>();
    for (const [t, v] of returnRank(closes, window, everyone)) if (typeof v === 'number' && Number.isFinite(v)) finite.set(t, v);
    const population = rankPopulation(d.rows, finite, d.data.evaluation_date);
    x = { window, ranks: returnRank(closes, window, population) };
    this.xs.set(k, x);
    this.xsMs += performance.now() - t0;
    return x;
  }

  /** One test bound to the snapshot (header rules). */
  private bind(id: string, def: ConditionDef | null, test: Test, field: string): BoundCondition {
    const withinMax = this.env.withinMax;
    const indicatorsOf = (refs: (Side | MetricRef)[]): ResolvedIndicator[] => {
      const out: ResolvedIndicator[] = [];
      const walk = (s: Side | MetricRef | undefined, f: string) => {
        if (!isRef(s as Side)) return;
        const r = s as MetricRef;
        if (r.kind === 'indicator') out.push(this.resolve(r, f) as ResolvedIndicator);
        else if (r.kind === 'transform') { walk(r.of, `${f}.of`); for (const [k, a] of Object.entries(r.args ?? {})) if (a && typeof a === 'object') walk(a as MetricRef, `${f}.args.${k}`) }
      };
      refs.forEach((s, k) => walk(s, `${field}.${k}`));
      return out;
    };
    const base = (sides: BoundSide[], extra: Partial<BoundCondition>): BoundCondition => {
      const series = sides.filter((s): s is Extract<BoundSide, { kind: 'series' }> => s.kind === 'series');
      const keys = series.map(s => seriesKey(this.snap.dv, s.r));
      const allPinned = keys.length > 0 && keys.every(k => this.snap.pinned.has(k));
      const inds = indicatorsOf(testRefs(test).map(x => x.ref));
      const first = series.find(s => s.r.kind !== 'price') ?? series[0];
      return {
        id, def, test, sides, keys, stage: allPinned ? 'S2' : 'S3', source: allPinned ? 'precomputed' : 'dynamic',
        metric: '', params_resolved: inds.length ? { ...inds[0].params } as ParamMap : {}, is_default: inds.every(i => i.isDefault),
        unit: first ? (first.r.unit as string | null) : null, ms: 0, tickers: 0,
        evaluate: () => { throw new Error('unbound') }, ...extra,
      };
    };
    if (test.kind === 'value') {
      const m = test.metric, f = `${field}.metric`;
      if (m.kind === 'xsection') {
        return { ...base([], { stage: 'S1', source: 'xsection', metric: refName(m), unit: null, params_resolved: { ...(m.params ?? {}) } as ParamMap, is_default: true }),
          evaluate: c => {
            const { window, ranks } = this.ranks(m, f);
            const v = ranks.get(c.ticker);
            const value = typeof v === 'number' ? v : null;
            const view = constView(value, c.at, c.at - window >= 0);
            return { e: evaluateValue(view, test, c.at), starts: [c.at - window], marker: null };
          } };
      }
      if (m.kind === 'universe') {
        return { ...base([], { stage: 'S2', source: 'precomputed', metric: refName(m), unit: null, is_default: true }),
          evaluate: c => {
            const row = this.snap.rows.get(c.ticker) as unknown as Record<string, unknown> | undefined;
            const v = row?.[m.attr];
            return { e: evaluateValue(constView(typeof v === 'number' && Number.isFinite(v) ? v : null, c.at, true), test, c.at), starts: null, marker: null };
          } };
      }
      const side = this.sideOf(m, f);
      return { ...base([side], { metric: refName(m) }),
        evaluate: c => { const o = this.operand(side, c, 0); return { e: evaluateValue(o.op as BarView, test, c.at), starts: [o.start], marker: null } } };
    }
    if (test.kind === 'state' && 'pattern' in test) {
      const p = test.pattern, f = `${field}.pattern`;
      return { ...base([], { stage: 'S3', source: 'dynamic', metric: refName(p), unit: null, params_resolved: { ...(p.params ?? {}) } }),
        evaluate: c => { const sig = patternSignal(c.tc, p, f, this.opts); return { e: evaluateStatePattern(sig, c.at), starts: [null], marker: null } } };
    }
    if (test.kind === 'state') {
      const [l, r] = this.compared(test.lhs, test.rhs, test.op, field);
      return { ...base([l, r], { metric: compareName(test.lhs, test.rhs) }),
        evaluate: c => {
          const a = this.operand(l, c, 0), b = this.operand(r, c, 0);
          return { e: evaluateState(a.op, test.op, b.op, c.at), starts: [a.start, b.start], marker: null };
        } };
    }
    const s = test.signal, within = test.within;
    if ('pattern' in s) {
      const p = s.pattern, f = `${field}.signal.pattern`;
      return { ...base([], { stage: 'S3', source: 'dynamic', metric: refName(p), unit: null, params_resolved: { ...(p.params ?? {}) } }),
        evaluate: c => {
          const sig = patternSignal(c.tc, p, f, this.opts), at = (i: number) => sig[i] === 1;
          return { e: evaluateEvent(at, within, withinMax, c.at), starts: [null], marker: at };
        } };
    }
    const [l, r] = this.compared(s.lhs, s.rhs, s.op, `${field}.signal`);
    return { ...base([l, r], { metric: compareName(s.lhs, s.rhs) }),
      evaluate: c => {
        const a = this.operand(l, c, within), b = this.operand(r, c, within);
        const sig = crossSignal(a.op, s.op, b.op);
        return { e: evaluateEvent(sig, within, withinMax, c.at, { lhs: a.op, rhs: b.op }), starts: [a.start, b.start], marker: sig };
      } };
  }

  /** The wire cell of a bound condition on one ticker (the remark only on a PRICE_BREAK row). */
  cell(bc: BoundCondition, ticker: string): Cell {
    const t0 = performance.now();
    try {
      const c = this.ctx(ticker);
      const { e, starts } = bc.evaluate(c);
      const remark = c.exDates && starts ? priceBreakRemark(starts, c.dates, c.at, c.exDates) : null;
      return toCell(bc.id, e, { dates: c.dates, at: c.at, ihsgCalendar: this.snap.ihsgCalendar, unit: bc.unit, remark });
    } finally { bc.ms += performance.now() - t0; bc.tickers++ }
  }
}

/** The evaluation bar of ticker j in the shared columns: evaluate.ts evaluationBar over a lazy view of its dates (a
    binary search reads about log2(n) of them, so no date list is built per ticker). -1 when it has none. */
function evaluationBarOf(d: SnapshotDesc, j: number, E: string): number {
  const a = d.offsets[j], n = d.offsets[j + 1] - a;
  const dates = new Proxy([] as string[], { get: (_t, k) => k === 'length' ? n : typeof k === 'string' && /^\d+$/.test(k) ? d.dates[d.T[a + Number(k)]] : undefined });
  return evaluationBar(dates, E);
}
/** A one-value view at `at` (a cross-sectional rank, a universe attribute): NA INSUFFICIENT_HISTORY when the ticker
    has too few bars for it (hadHistory false), else NULL_AT_EVALUATION when the value is missing (evaluate.ts naReason). */
function constView(value: number | null, at: number, hadHistory: boolean): BarView {
  const ok = value !== null;
  return { n: at + 1, from: 0, firstValid: ok ? at : hadHistory ? 0 : -1, lastValid: ok ? at : -1, inputMissing: false, get: i => i === at && ok ? value as number : NaN };
}
function compareName(lhs: Side, rhs: Side): string {
  const names = [lhs, rhs].filter((s): s is MetricRef => isRef(s) && s.kind !== 'price').map(refName);
  if (names.length) return names.join(' x ');
  const prices = [lhs, rhs].filter((s): s is MetricRef => isRef(s)).map(refName);
  return prices.join(' x ') || 'value';
}

/* ================================================================================================================ */
/* compute thread: the run                                                                                         */
/* ================================================================================================================ */

export interface RunTask {
  kind: 'run' | 'counts';
  sid: string; definition: Definition; hash: string; options: RunOptionsN;
  eligible: string[]; pending: number[]; counts: UniverseCounts; predicted: Record<string, number>;
  queue_ms: number; s0_ms: number; arrived_at: number;
}
export interface RunOutcome {
  kind: 'run' | 'counts';
  gzip: Uint8Array | null; etag: string | null; json_bytes: number;
  match_count: number; near_count: number;
  busy_ms: number;
  log: { stages: { name: string; in: number; out: number; ms: number }[]; conditions: { id: string; source: string; stage: string; tickers_evaluated: number; cpu_ms: number }[]; pruned: number; pinned_hits: number };
  observe: { key: string; ms: number; bars: number; length: number }[];
}

/** One screen (or one definition's counts) on a snapshot; `cancelled` is checked between tickers (plan.ts). */
export function runScreen(task: RunTask, snap: ThreadSnapshot, env: ThreadEnv, cancelled: () => boolean): RunOutcome {
  const t0 = performance.now(), def = task.definition;
  const b = new Binder(snap, env, def, task.pending);
  // the pending metric filters (universe.ts leaves those that need a formula to the worker), on the S0 survivors
  const tf = performance.now();
  let eligible = task.eligible;
  if (b.filters.length) {
    eligible = eligible.filter(t => { if (cancelled()) throw new CancelledRun(); return b.filters.every(f => b.cell(f, t).status === 'pass') });
  }
  const filterMs = performance.now() - tf;
  const universe: UniverseCounts = { ...task.counts, eligible: eligible.length, filtered_out: task.counts.filtered_out + (task.eligible.length - eligible.length) };
  const active = b.conditions.length;
  let plan: PlanOutput | null = null;
  let rowsOut: { ticker: string; status: 'match' | 'near'; met: number; need: number; na_count: number; cells: Cell[] }[];
  let need = 0;
  if (!active) {
    rowsOut = eligible.map(t => ({ ticker: t, status: 'match' as const, met: 0, need: 0, na_count: 0, cells: [] }));
  } else {
    const conditions: PlanCondition[] = b.conditions.map(bc => ({ id: bc.id, stage: bc.stage, predictedMs: task.predicted[bc.id] ?? 0, evaluate: (t: string) => b.cell(bc, t) }));
    plan = runPlan({ tickers: [...eligible].sort(byTicker), conditions, logic: def.logic, atLeast: def.at_least, exhaustive: task.options.exhaustive, cancelled });
    need = plan.need;
    rowsOut = plan.rows;
  }
  if (need === 0 && active) need = needOf(def.logic, def.at_least, active);
  let match = 0, near = 0;
  for (const r of rowsOut) { if (r.status === 'match') match++; else if (r.status === 'near') near++ }
  const busy = () => Math.round(performance.now() - t0);
  const stages = [{ name: 'S0', in: task.counts.listed, out: eligible.length, ms: Math.round(task.s0_ms + filterMs) },
    ...(plan ? plan.explain.stages.map(s => ({ ...s, ms: Math.round(s.ms + (s.name === 'S1' ? b.xsMs : 0)) })) : [])];
  const log = {
    stages, pruned: plan?.pruned ?? 0, pinned_hits: b.pinnedHits,
    conditions: b.conditions.map(c => ({ id: c.id, source: c.source, stage: c.stage, tickers_evaluated: c.tickers, cpu_ms: Math.round(c.ms) })),
  };
  const observe = b.conditions.filter(c => c.stage === 'S3' && c.tickers > 0).flatMap(c => {
    const units = c.sides.filter(s => s.kind === 'series' && s.r.kind === 'indicator') as Extract<BoundSide, { kind: 'series' }>[];
    if (units.length !== 1) return [];
    const r = units[0].r as ResolvedIndicator, ind = r.indicator;
    const length = Math.max(1, ...ind.params.filter(p => p.cost_class === 'O(N·n)').map(p => Number(r.params[p.key]) || 1));
    let bars = 0;
    for (const t of eligible) { const j = snap.position.get(t); if (j !== undefined) bars += barCount(snap.desc, j) }
    return [{ key: `indicator:${ind.key}`, ms: c.ms, bars: Math.round(bars * c.tickers / Math.max(1, eligible.length)), length }];
  });
  if (task.kind === 'counts') return { kind: 'counts', gzip: null, etag: null, json_bytes: 0, match_count: match, near_count: near, busy_ms: busy(), log, observe };

  // the answer (8.5): versions and data open it (edge-bff reads them from its head without inflating the rest)
  const d = snap.desc;
  const rows: ResultRow[] = rowsOut.map(r => {
    const u = snap.rows.get(r.ticker) as UniverseRow;
    return {
      ticker: r.ticker, name: u.name, sector: u.sector, industry: u.industry, board: null, market_cap: null,
      last: round12(u.last), chg_1d_pct: round12(u.chg_1d_pct), adv20_idr: round12(u.adv20_idr), last_bar_date: u.last_bar, stale: u.stale,
      remarks: u.remarks, status: r.status, met: r.met, need: r.need, na_count: r.na_count, cells: r.cells,
    };
  });
  rows.sort(defaultOrder);
  const summaries: ConditionSummary[] = b.conditions.map(c => {
    const s = plan?.summaries[c.id];
    return {
      id: c.id, source: c.source, metric: c.metric, params_resolved: c.params_resolved, is_default: c.is_default, kind: c.test.kind,
      unit: c.unit, evaluated: s?.evaluated ?? 0, passed: s?.passed ?? 0, na: s?.na ?? 0, exhaustive: s?.exhaustive ?? true, eval_date_basis: 'ticker_last_bar',
    };
  });
  const warnings: Warning[] = [];
  if (def.logic === 'any' && active >= 2 && !task.options.exhaustive)
    warnings.push({ code: 'NO_PRUNING_FOR_ANY', message: 'With ANY no ticker can be left out early, so every condition is evaluated on every eligible ticker (TARGET ARCHITECTURE 6.10).' });
  const brokenRows = rows.filter(r => r.remarks.some(x => x.code === 'PRICE_BREAK')).length;
  const brokenCells = rows.reduce((n, r) => n + r.cells.filter(c => c.remark === 'PRICE_BREAK_IN_LOOKBACK').length, 0);
  if (brokenRows || brokenCells)
    warnings.push({ code: 'PRICE_BREAKS_IN_RESULT', message: `${brokenRows} row(s) have an unadjusted price break; ${brokenCells} value(s) read across it are shown and marked.`, count: brokenRows, details: { rows: brokenRows, cells: brokenCells } });
  const sm = (n: string) => stages.find(s => s.name === n)?.ms ?? 0;
  const answer: RunResponse = {
    schema_version: 1,
    versions: { ...d.versions, definition_hash: task.hash } as Versions,
    data: d.data as DataStatus,
    mode: active ? 'screen' : 'universe_only',
    universe, conditions: summaries, need, match_count: match, near_count: near, rows, warnings,
    timings_ms: { queue: Math.round(task.queue_ms), s0: sm('S0'), s1: sm('S1'), s2: sm('S2'), s3: sm('S3'), s4: sm('S4'), total: 0 },
  };
  if (task.options.explain) {
    const explain: PlanExplain = {
      stages: stages.map(s => ({ name: s.name as PlanExplain['stages'][number]['name'], in: s.in, out: s.out, ms: s.ms })),
      order: plan?.explain.order ?? [], pruned: plan?.pruned ?? 0, cache_hits: b.pinnedHits, exhaustive: task.options.exhaustive,
      ...(plan?.explain.note ? { note: plan.explain.note } : {}),
    };
    answer.plan = explain;
  }
  answer.timings_ms.total = Math.round(task.queue_ms + task.s0_ms + performance.now() - t0);
  return { ...pack(answer, env.maxResponseBytes), match_count: match, near_count: near, busy_ms: busy(), log, observe, kind: 'run' };
}

/** Default row order (6.9 Sort): match first, then met descending, then ADV20 descending (nulls last), then ticker. */
export function defaultOrder(a: ResultRow, b: ResultRow): number {
  if (a.status !== b.status) return a.status === 'match' ? -1 : 1;
  if (a.met !== b.met) return b.met - a.met;
  const x = a.adv20_idr, y = b.adv20_idr;
  if (x !== y) { if (x === null) return 1; if (y === null) return -1; return y - x }
  return byTicker(a.ticker, b.ticker);
}

/** An answer's JSON as gzip with its ETag (sha256 of the JSON bytes), or LIMIT_EXCEEDED max_response_bytes. */
export function pack(answer: unknown, maxBytes: number): { gzip: Uint8Array; etag: string; json_bytes: number } {
  const text = JSON.stringify(answer), json = Buffer.from(text);
  if (json.byteLength > maxBytes)
    throw refuse('LIMIT_EXCEEDED', `The answer would have ${json.byteLength} bytes of JSON; the limit is ${maxBytes}. Narrow the universe (price, ADV20, sectors) or add a condition so fewer tickers match or come near.`, undefined, { limit: 'max_response_bytes', allowed: maxBytes, needed: json.byteLength });
  const packed = zlib.gzipSync(json, { level: 6 }), gzip = new Uint8Array(packed.byteLength);
  gzip.set(packed);
  return { gzip, etag: `"${crypto.createHash('sha256').update(json).digest('hex')}"`, json_bytes: json.byteLength };
}

/** A run stopped by its cancel flag (the caller left, or the deadline passed). */
export class CancelledRun extends Error { constructor() { super('cancelled'); this.name = 'CancelledRun' } }
export const isCancelled = (e: unknown): boolean => e instanceof CancelledRun || (e as Error)?.name === 'CancelledRun' || /cancel/i.test(String((e as Error)?.message ?? ''));

/** Shared by preview.ts: the definition's universe check of one ticker on the main thread's S0 rows. */
export const inUniverse = (desc: SnapshotDesc, universe: UniverseDef, ticker: string): { eligible: boolean; pending: number[] } => {
  const r = applyUniverse(desc.rows.filter(x => x.ticker === ticker), universe);
  return { eligible: r.eligible.length === 1, pending: r.pending };
};
export { rowStatus };
export type { IndicatorRef, PatternRef, ValueTest };
